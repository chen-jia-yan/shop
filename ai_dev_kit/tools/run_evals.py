"""评估运行器：用真实事故做成的用例，确认工具包的防线一直有效（改了技能、规则、检查之后必跑）。

用例类型（evals/cases/*.json）：
    guard   给守卫一个模拟的工具调用，期望 deny 或 none
    prompt  给提示词体检一段草稿，期望识别出缺少的维度
    static  在临时 git 仓库里重现事故（before → after），期望静态检查报出问题（fail）或不报（pass）
    output  给一段测试命令的输出，期望一键验证判定为失败（例如 0 条测试、收集中断）或通过
    agent   真正调用 Copilot 的某个自定义代理（非交互模式），用正则检查回答里该有/不该有的内容
            这类会消耗额度，默认不跑，加 --agent 才跑

依据：Anthropic 的评估实践建议从 20～50 个真实失败案例起步；能用代码判分就用代码判分；
回归用例的通过率应接近 100%；分数之外还要读执行记录。agent 类的完整输出会保存下来供阅读。

用法：
    python tools/run_evals.py                 # 跑 guard / prompt / static
    python tools/run_evals.py --only guard
    python tools/run_evals.py --agent --profile latest   # 额外跑 agent 类
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import checks
import kitlib
import prompt_lint
from guard import Guard

CASE_DIR = kitlib.KIT_ROOT / "evals" / "cases"


def _fill_cwd(value: Any, cwd: str) -> Any:
    """把用例里的 {cwd} 换成临时目录，方便写“项目内的绝对路径”。"""
    if isinstance(value, str):
        return value.replace("{cwd}", cwd.replace("\\", "/"))
    if isinstance(value, list):
        return [_fill_cwd(v, cwd) for v in value]
    if isinstance(value, dict):
        return {k: _fill_cwd(v, cwd) for k, v in value.items()}
    return value


def run_guard(case: dict[str, Any]) -> tuple[bool, str]:
    cwd = tempfile.mkdtemp(prefix="kit-eval-")
    projects = []
    if case.get("protected"):
        projects.append({"name": "eval", "path": cwd, "protected": case["protected"],
                         "protected_allow": case.get("protected_allow", [])})
    if case.get("scope"):
        kitlib.save_json(Path(cwd) / kitlib.SCOPE_DIRNAME / kitlib.SCOPE_FILENAME, case["scope"])
    guard = Guard({"guard": case.get("guard_config", {}), "projects": projects})
    payload = _fill_cwd(dict(case["payload"]), cwd)
    payload["cwd"] = cwd
    decision, reason, rule = guard.decide(payload)
    return decision == case["expect"], f"期望 {case['expect']}，实际 {decision} {rule}"


def run_output(case: dict[str, Any]) -> tuple[bool, str]:
    """把一段测试命令的输出交给 run_checks 的结果判断，确认假通过能被识别。"""
    import run_checks

    res = run_checks._summarize(case.get("check_name", "tests"), int(case.get("exit_code", 0)), case["output"])
    flagged = not res["ok"]
    ok = flagged if case["expect"] == "fail" else not flagged
    return ok, f"判定 {'失败' if flagged else '通过'}；识别出：{res['problems'] or '无'}"


def _write_fixture(path: Path, content: Any) -> None:
    """内容可以是字符串（UTF-8 写入），也可以是 {"text": ..., "encoding": "utf-16"} 来制造编码事故。"""
    if isinstance(content, dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(str(content["text"]).encode(content.get("encoding", "utf-8")))
    else:
        kitlib.write_text(path, content)


def run_prompt(case: dict[str, Any]) -> tuple[bool, str]:
    rep = prompt_lint.analyze(case["text"])
    missing = {d["key"] for d in rep["dimensions"] if not d["ok"]}
    expected = set(case.get("expect_missing", []))
    not_flagged = expected - missing
    ok = not not_flagged
    if "expect_max_score" in case:
        ok = ok and rep["score"] <= case["expect_max_score"]
    if "expect_min_score" in case:
        ok = ok and rep["score"] >= case["expect_min_score"]
    return ok, f"得分 {rep['score']}，识别为缺少：{sorted(missing)}" + (f"；没识别出：{sorted(not_flagged)}" if not_flagged else "")


def _git(args: list[str], cwd: Path) -> None:
    code, out = kitlib.git(["-c", "user.name=kit", "-c", "user.email=kit@local"] + args, cwd)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{out[:200]}")


def run_static(case: dict[str, Any]) -> tuple[bool, str]:
    tmp = Path(tempfile.mkdtemp(prefix="kit-eval-repo-"))
    _git(["init", "-q"], tmp)
    for rel, content in case.get("before", {}).items():
        _write_fixture(tmp / rel, content)
    kitlib.write_text(tmp / ".gitkeep", "")
    _git(["add", "-A"], tmp)
    _git(["commit", "-q", "-m", "before"], tmp)
    for rel, content in case.get("after", {}).items():
        if content is None:
            (tmp / rel).unlink(missing_ok=True)
        else:
            _write_fixture(tmp / rel, content)
    if case.get("scope"):
        kitlib.save_json(tmp / kitlib.SCOPE_DIRNAME / kitlib.SCOPE_FILENAME, case["scope"])
    project = {"name": "eval", "path": str(tmp), "source_dirs": ["src"], "test_dirs": ["tests"]}
    project.update(case.get("project", {}))
    ctx = checks.Ctx(project, tmp, tmp, "HEAD", {"projects": [project]})
    result = checks.run_checks(ctx, [case["check"]])[0]
    flagged = (not result.ok) and not result.skipped
    ok = flagged if case["expect"] == "fail" else not flagged
    return ok, f"{result.summary}" + (f"；{result.findings[0]}" if result.findings else "")


def run_agent(case: dict[str, Any], profile_name: str | None) -> tuple[bool, str]:
    cfg = kitlib.load_config()
    profile = kitlib.get_profile(cfg, profile_name)
    template = profile.get("noninteractive_cmd")
    if not template:
        return False, f"配置 {profile['_name']} 没有 noninteractive_cmd，无法自动运行"
    ctx = kitlib.base_ctx(cfg)
    ctx.update({"agent": case["agent"], "prompt": case["prompt"], "launcher": profile.get("launcher", "copilot")})
    cmd = kitlib.expand_cmd(list(template), ctx)
    started = time.time()
    code, out = kitlib.run(cmd, cwd=tempfile.mkdtemp(prefix="kit-eval-agent-"), timeout=int(case.get("timeout", 600)))
    log = kitlib.DATA_DIR / "evals" / f"{case['id']}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    kitlib.write_text(log, f"命令：{cmd}\n退出码：{code}\n耗时：{time.time() - started:.0f}s\n\n{out}")
    missing = [p for p in case.get("expect_all", []) if not re.search(p, out, re.I | re.S)]
    present = [p for p in case.get("expect_none", []) if re.search(p, out, re.I | re.S)]
    ok = code == 0 and not missing and not present
    detail = f"输出已保存：{log}"
    if missing:
        detail += f"；缺少：{missing}"
    if present:
        detail += f"；不该出现：{present}"
    return ok, detail


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="运行评估用例")
    parser.add_argument("--only", help="只跑某类：guard,prompt,static,output,agent")
    parser.add_argument("--agent", action="store_true", help="同时运行 agent 类（会消耗额度）")
    parser.add_argument("--profile", help="agent 类使用的配置，默认 default_profile")
    parser.add_argument("--case", help="只跑某个用例 id")
    args = parser.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    cases = []
    for path in sorted(CASE_DIR.glob("*.json")):
        case = kitlib.load_json(path)
        case.setdefault("id", path.stem)
        cases.append(case)
    stats: dict[str, list[int]] = {}
    for case in cases:
        ctype = case.get("type", "")
        if args.case and case["id"] != args.case:
            continue
        if only and ctype not in only:
            continue
        if ctype == "agent" and not args.agent:
            continue
        try:
            if ctype == "guard":
                ok, detail = run_guard(case)
            elif ctype == "prompt":
                ok, detail = run_prompt(case)
            elif ctype == "static":
                ok, detail = run_static(case)
            elif ctype == "output":
                ok, detail = run_output(case)
            elif ctype == "agent":
                ok, detail = run_agent(case, args.profile)
            else:
                ok, detail = False, f"未知类型 {ctype}"
        except Exception as exc:
            ok, detail = False, f"用例运行出错：{exc!r}"
        s = stats.setdefault(ctype, [0, 0])
        s[0] += int(ok)
        s[1] += 1
        print(f"[{'通过' if ok else '失败'}] {case['id']}（{ctype}）{case.get('title', '')}\n       {detail}")
    total_ok = sum(v[0] for v in stats.values())
    total = sum(v[1] for v in stats.values())
    print("\n" + "，".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(stats.items())))
    print(f"总计 {total_ok}/{total} 通过。" + ("" if args.agent else "（agent 类未运行，加 --agent 运行）"))
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
