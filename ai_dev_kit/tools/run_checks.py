"""一键验收：按 kit.config.json 里登记的命令跑测试、lint、类型检查和静态检查，输出精简报告。

为什么不让模型直接跑 pytest：
- 完整测试输出动辄几千行，全塞进上下文既费 token，又容易让模型抓不住重点；
- 这里只保留"失败行 + 汇总行 + 最后几行"，完整输出存到文件里，需要时再看；
- 工作区指纹（HEAD + 改动文件内容的哈希）没变时，直接复用上一次结果，不重复跑。

还会主动识别这几种"看起来通过、其实没跑"的情况：
    0 个测试被收集 / 收集阶段报错 / 全部被跳过 / 命令找不到

用法：
    python run_checks.py --project tap-ai-backend          # 默认：所有登记的命令 + 快速静态检查
    python run_checks.py --project tap-ai-backend --only tests,lint
    python run_checks.py --project tap-ai-backend --force  # 忽略缓存，强制重跑
    python run_checks.py --project tap-ai-backend --full   # 额外跑较慢的静态检查
退出码：0 全部通过；1 有失败。
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

import checks
import kitlib

FAIL_LINE = re.compile(r"^(FAILED|ERROR|E\s{3}|.*\berror\b:|.*: error:|Found \d+ error|\S+\.py:\d+:\d+: [A-Z]+\d+)", re.I)
SUMMARY_LINE = re.compile(r"(\d+ (passed|failed|error|errors|skipped|xfailed|xpassed|deselected|warnings?)|"
                          r"no tests ran|tests? collected|Success: no issues|All checks passed|Found \d+ errors?|"
                          r"扫描 \d+ 个文件)", re.I)


def _summarize(name: str, code: int, out: str, tail: int = 8) -> dict[str, Any]:
    lines = out.splitlines()
    fails = [ln for ln in lines if FAIL_LINE.search(ln)]
    summary = [ln for ln in lines if SUMMARY_LINE.search(ln)]
    problems: list[str] = []
    low = out.lower()
    if name == "tests":
        if "no tests ran" in low or re.search(r"\b0 (tests? )?(passed|collected)\b", low) or "collected 0 items" in low:
            problems.append("一个测试都没有运行：请检查工作目录和测试路径")
        if "interrupted" in low and "error" in low:
            problems.append("测试在收集阶段被中断：报错的测试文件一个都没跑")
        m_pass = re.search(r"(\d+) passed", low)
        m_skip = re.search(r"(\d+) skipped", low)
        if m_skip and not m_pass:
            problems.append("所有测试都被跳过，等于没跑")
    if code == 127:
        problems.append("命令找不到：检查 kit.config.json 里的命令和 PATH")
    ok = code == 0 and not problems
    return {
        "name": name, "ok": ok, "code": code, "problems": problems,
        "fail_lines": fails[:40], "summary_lines": summary[-5:], "tail": lines[-tail:],
    }


def run_project(project_name: str, only: list[str] | None, force: bool, full: bool) -> tuple[bool, str]:
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, project_name)
    if not project:
        return False, f"kit.config.json 里没有登记项目：{project_name}"
    root = Path(project["path"])
    if not root.is_dir():
        return False, f"项目目录不存在：{root}"
    commands: dict[str, list[str]] = dict(project.get("checks", {}))
    commands.pop("collect", None)
    selected = [n for n in commands if not only or n in only]
    static_names = (list(checks.CHECKS) if full else list(checks.FAST_CHECKS))
    if only:
        static_names = [n for n in static_names if n in only or "static" in only]
    key_extra = f"{project_name}|{','.join(selected)}|{','.join(static_names)}|{kitlib.load_json(kitlib.CONFIG_PATH, {}).get('kit_version', '')}"
    fingerprint = kitlib.tree_fingerprint(root, key_extra)
    cached = None if force else kitlib.cache_get("verify", fingerprint)
    if cached and cached.get("ok"):
        return True, (f"[缓存命中] 工作区自 {cached['ts']} 验收通过后没有任何变化（指纹 {fingerprint}），直接复用结果。\n"
                      + cached["report"] + "\n（需要强制重跑请加 --force）")

    ctx = kitlib.base_ctx(cfg, project)
    report_parts: list[str] = [f"项目：{project_name}　目录：{root}　指纹：{fingerprint}"]
    full_log: list[str] = []
    all_ok = True
    for name in selected:
        cmd = kitlib.expand_cmd(list(commands[name]), ctx)
        started = time.time()
        code, out = kitlib.run(cmd, cwd=root, timeout=int(project.get("check_timeout", 1800)))
        elapsed = time.time() - started
        full_log.append(f"===== {name}: {' '.join(cmd)} （退出码 {code}，{elapsed:.1f}s）\n{out}")
        s = _summarize(name, code, out)
        all_ok = all_ok and s["ok"]
        mark = "通过" if s["ok"] else "失败"
        report_parts.append(f"[{mark}] {name}（退出码 {code}，{elapsed:.0f}s）：{' '.join(cmd)}")
        for p in s["problems"]:
            report_parts.append(f"    ! {p}")
        for ln in s["summary_lines"]:
            report_parts.append(f"    = {ln.strip()[:200]}")
        if not s["ok"]:
            for ln in s["fail_lines"][:25] or s["tail"]:
                report_parts.append(f"    > {ln.rstrip()[:220]}")

    if static_names:
        cctx = checks.Ctx(project, root, Path(project.get("git_root") or root), "HEAD", cfg)
        results = checks.run_checks(cctx, static_names)
        report_parts.append("静态检查：")
        report_parts.append(checks.format_results(results))
        all_ok = all_ok and not any((not r.ok) and (not r.skipped) and r.severity == "error" for r in results)

    report = "\n".join(report_parts)
    log_path = kitlib.DATA_DIR / "verify" / f"{project_name}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    kitlib.write_text(log_path, "\n\n".join(full_log) + "\n\n" + report + "\n")
    report += f"\n完整输出：{log_path}"
    report += "\n结论：" + ("全部通过" if all_ok else "有失败，见上面带 > 的行")
    kitlib.cache_put("verify", fingerprint, {"ok": all_ok, "ts": kitlib.now(), "report": report})
    return all_ok, report


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="一键验收（测试 + lint + 类型 + 静态检查）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--only", help="逗号分隔：tests,lint,types,chars,static 或某个静态检查名")
    parser.add_argument("--force", action="store_true", help="忽略缓存")
    parser.add_argument("--full", action="store_true", help="包含较慢的静态检查")
    args = parser.parse_args(argv)
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    ok, report = run_project(args.project, only, args.force, args.full)
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
