"""一键验收：按 kit.config.json 里登记的命令跑测试、lint、类型检查和静态检查，输出精简报告。

为什么不让模型直接跑 pytest：
- 完整测试输出动辄几千行，全塞进上下文既费 token，又容易让模型抓不住重点；
- 这里只保留"失败行 + 汇总行 + 最后几行"，完整输出存到文件里，需要时再看；
- 工作区指纹（HEAD + 改动文件内容的哈希）没变时，直接复用上一次结果，不重复跑。

还会主动识别这几种"看起来通过、其实没跑"的情况：
    0 个测试被收集 / 收集阶段报错 / 全部被跳过 / 命令找不到

用法：
    python run_checks.py                                   # 在项目目录里运行：所有登记的命令 + 快速静态检查
    python run_checks.py --project tap-ai-backend --only tests,lint
    python run_checks.py --force                           # 忽略缓存，强制重跑
    python run_checks.py --full                            # 额外跑较慢的静态检查
    python run_checks.py --shared-baseline                 # 改共享模块之前：记录测试基线
    python run_checks.py --shared-baseline clear           # 共享模块的改动结束后：清除基线
所有命令都在“禁删保护”下运行（见 runtime/kit_nodelete.py）：测试误连真库也删不掉数据。
改过共享模块时，会把测试通过数和基线对比：通过数变少或失败数变多就判为失败。
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
BLOCKED_LINE = re.compile(r"KitDeleteBlocked|ai-dev-kit 禁删保护")


def count_tests(out: str) -> dict[str, int]:
    """从 pytest 的汇总行里取出 passed / failed / error / skipped 的数量。"""
    low = out.lower()
    result: dict[str, int] = {}
    for key in ("passed", "failed", "error", "skipped"):
        found = re.findall(rf"(\d+) {key}s?\b", low)
        result[key] = int(found[-1]) if found else 0
    return result


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
    blocked = [ln for ln in lines if BLOCKED_LINE.search(ln)]
    if blocked:
        problems.append("禁删保护拦下了删除数据的操作（测试或代码在删真实数据）：" + blocked[0].strip()[:160])
    ok = code == 0 and not problems
    return {
        "name": name, "ok": ok, "code": code, "problems": problems,
        "fail_lines": fails[:40], "summary_lines": summary[-5:], "tail": lines[-tail:],
    }


def run_project(project_name: str, only: list[str] | None, force: bool, full: bool) -> tuple[bool, str]:
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, project_name)
    if not project:
        return False, f"找不到项目：{project_name}（当前目录不在 git 仓库里，也没有在 kit.config.json 登记）"
    project_name = str(project.get("name") or project_name)  # “.” 换成真正的项目名，用于缓存和日志文件名
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
    report_parts: list[str] = [f"项目：{project_name}  目录：{root}  指纹：{fingerprint}  禁删保护：开"]
    full_log: list[str] = []
    test_counts: dict[str, int] | None = None
    all_ok = True
    for name in selected:
        cmd = kitlib.expand_cmd(list(commands[name]), ctx)
        started = time.time()
        code, out = kitlib.run(cmd, cwd=root, timeout=int(project.get("check_timeout", 1800)), nodelete=True)
        elapsed = time.time() - started
        full_log.append(f"===== {name}: {' '.join(cmd)} （退出码 {code}，{elapsed:.1f}s）\n{out}")
        s = _summarize(name, code, out)
        if name == "tests":
            test_counts = count_tests(out)
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

    shared_ok, shared_lines = compare_shared(project, root, cfg, test_counts)
    report_parts.extend(shared_lines)
    all_ok = all_ok and shared_ok

    report = "\n".join(report_parts)
    log_path = kitlib.DATA_DIR / "verify" / f"{project_name}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    kitlib.write_text(log_path, "\n\n".join(full_log) + "\n\n" + report + "\n")
    report += f"\n完整输出：{log_path}"
    report += "\n结论：" + ("全部通过" if all_ok else "有失败，见上面带 > 的行")
    kitlib.cache_put("verify", fingerprint, {"ok": all_ok, "ts": kitlib.now(), "report": report})
    return all_ok, report


# ---------------------------------------------------------------- 共享模块的基线


def _shared_changed(project: dict[str, Any], root: Path, cfg: dict[str, Any]) -> list[str]:
    areas, allow = kitlib.shared_areas(project)
    if not areas:
        return []
    cctx = checks.Ctx(project, root, Path(project.get("git_root") or root), "HEAD", cfg)
    changed: list[str] = []
    for path in checks.changed_files(cctx):
        rel = kitlib.rel_posix(path, root)
        if kitlib.match_any(rel, areas) and not kitlib.match_any(rel, allow):
            changed.append(rel)
    return changed


def _shared_test_cmd(project: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    cmd = project.get("shared_tests") or (project.get("checks", {}) or {}).get("tests") or []
    return kitlib.expand_cmd(list(cmd), kitlib.base_ctx(cfg, project))


def compare_shared(project: dict[str, Any], root: Path, cfg: dict[str, Any],
                   test_counts: dict[str, int] | None) -> tuple[bool, list[str]]:
    """改过共享模块时：和改之前记录的基线比，通过数不能少，失败数不能多。"""
    changed = _shared_changed(project, root, cfg)
    if not changed:
        return True, []
    lines = [f"共享模块：本次改动了 {len(changed)} 个文件（{'、'.join(changed[:5])}{'……' if len(changed) > 5 else ''}）"]
    base = (kitlib.read_shared_state(project) or {}).get("baseline")
    if not base:
        lines.append("    ! 没有找到改之前的测试基线，无法确认有没有改坏。请告诉用户这一点，由用户判断；"
                     "以后改共享模块前先运行 run_checks.py --shared-baseline")
        return False, lines
    if project.get("shared_tests"):
        _, out = kitlib.run(_shared_test_cmd(project, cfg), cwd=root, timeout=int(project.get("check_timeout", 1800)),
                            nodelete=True)
        test_counts = count_tests(out)
    if test_counts is None:
        lines.append("    ! 这次没有运行测试，无法和基线对比（去掉 --only 再跑一次）")
        return False, lines
    ok = test_counts["passed"] >= base["passed"] and test_counts["failed"] + test_counts["error"] <= base["failed"] + base["error"]
    lines.append(f"    = 基线（{base['ts']}）：通过 {base['passed']}，失败 {base['failed'] + base['error']}；"
                 f"现在：通过 {test_counts['passed']}，失败 {test_counts['failed'] + test_counts['error']}")
    lines.append("    " + ("[通过] 没有比改之前更差" if ok else "[失败] 共享模块的测试比改之前更差：通过数变少或失败数变多"))
    lines.append("    提醒：评审时检查对外的函数名、参数、返回字段、配置名有没有变（同事的代码可能依赖它们）")
    return ok, lines


def record_shared_baseline(project_name: str, clear: bool = False) -> int:
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, project_name)
    if not project:
        print(f"找不到项目：{project_name}")
        return 1
    path = kitlib.shared_state_path(project)
    if clear:
        if path.exists():
            path.unlink()
        print("已清除共享模块的测试基线。")
        return 0
    areas, _ = kitlib.shared_areas(project)
    if not areas:
        print("这个项目没有配置共享模块（kit.config.json 里项目的 shared 字段），不需要基线。")
        return 0
    cmd = _shared_test_cmd(project, cfg)
    if not cmd:
        print("没有登记测试命令（checks.tests 或 shared_tests），无法记录基线。")
        return 1
    root = Path(project["path"])
    print(f"记录基线：{' '.join(cmd)}")
    code, out = kitlib.run(cmd, cwd=root, timeout=int(project.get("check_timeout", 1800)), nodelete=True)
    counts = count_tests(out)
    if counts["passed"] == 0 and counts["failed"] == 0:
        print("没有识别出测试结果（0 条通过、0 条失败），基线没有记录。最后几行输出：")
        print("\n".join(out.splitlines()[-10:]))
        return 1
    git_root = Path(project.get("git_root") or root)
    head = kitlib.git(["rev-parse", "--short", "HEAD"], git_root)[1].strip()
    kitlib.save_json(path, {"baseline": dict(counts, ts=kitlib.now(), head=head, cmd=" ".join(cmd))})
    exclude = git_root / ".git" / "info" / "exclude"
    if exclude.parent.is_dir():
        text = kitlib.read_text(exclude) if exclude.exists() else ""
        if ".ai-dev-kit/" not in text.split():
            kitlib.write_text(exclude, text.rstrip("\n") + ("\n" if text else "") + ".ai-dev-kit/\n")
    print(f"基线已记录：通过 {counts['passed']}，失败 {counts['failed'] + counts['error']}，跳过 {counts['skipped']}（HEAD {head}）")
    print("现在可以修改共享模块了；改完运行一键验证，会自动和基线对比。")
    return 0


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="一键验收（测试 + lint + 类型 + 静态检查）")
    parser.add_argument("--project", default=".", help="项目名；不填表示当前目录（登记过的用登记设置，没登记的自动识别）")
    parser.add_argument("--only", help="逗号分隔：tests,lint,types,chars,static 或某个静态检查名")
    parser.add_argument("--force", action="store_true", help="忽略缓存")
    parser.add_argument("--full", action="store_true", help="包含较慢的静态检查")
    parser.add_argument("--shared-baseline", nargs="?", const="record", choices=["record", "clear"],
                        help="改共享模块前记录测试基线；clear 清除")
    args = parser.parse_args(argv)
    if args.shared_baseline:
        return record_shared_baseline(args.project, clear=args.shared_baseline == "clear")
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    ok, report = run_project(args.project, only, args.force, args.full)
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
