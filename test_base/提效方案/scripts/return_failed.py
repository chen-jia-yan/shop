"""第 2 步：自动重跑失败用例，记录每次尝试的结果。

用法：
    python scripts/rerun_failed.py --failures triage_runs/<run_id>/failures.json \
        --config config/config.yaml --out triage_runs/<run_id>/rerun.json [--skip] [--only Case7,Case9]

说明：
- 使用 config.yaml 中 rerun.command 的命令模板逐个重跑，{nodeid} 和 {junit_out} 会被替换。
- 通过解析每次重跑产生的 JUnit XML 判断结果，而不是只看命令的退出码。
- 默认串行执行（rerun.parallel = 1），避免共用测试环境时互相影响。
- 某一次重跑通过后，不再继续重跑该用例。
- 加 --skip 时只生成空的 rerun.json（并标记 skipped），用于环境已下线等不能重跑的情况。
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import (fail, load_config, mask_pii, now_iso, read_json, setup_logging,
                    short_exception_name, write_json)

log = setup_logging()


def parse_junit_result(path: Path) -> tuple[str, str | None, str | None]:
    """返回 (status, error_type, error_message)。status 为 passed / failed / skipped / unknown。"""
    if not path.exists():
        return "unknown", None, "重跑没有生成 JUnit 结果文件"
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return "unknown", None, f"JUnit 结果无法解析：{exc}"
    cases = list(root.iter("testcase"))
    if not cases:
        return "unknown", None, "JUnit 结果中没有用例（nodeid 可能不正确）"
    for tc in cases:
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        if bad is not None:
            return "failed", short_exception_name(bad.get("type")), (bad.get("message") or "")[:1500]
    if all(tc.find("skipped") is not None for tc in cases):
        return "skipped", None, None
    return "passed", None, None


def run_once(case: dict, attempt: int, cfg: dict, tmpdir: Path) -> dict:
    rcfg = cfg["rerun"]
    junit_out = tmpdir / f"{case['case_id'].replace('/', '_').replace('#', '_')}_{attempt}.xml"
    cmd = rcfg["command"].format(nodeid=case["nodeid"], junit_out=str(junit_out))
    started = now_iso()
    t0 = time.monotonic()
    try:
        # 命令模板来自本地 config.yaml（由测试人员维护），用 shell 执行以兼容 Windows 路径和引号
        proc = subprocess.run(
            cmd, shell=True,
            cwd=rcfg.get("workdir") or None,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=rcfg.get("timeout_sec", 900),
        )
        status, etype, emsg = parse_junit_result(junit_out)
        tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
    except subprocess.TimeoutExpired:
        status, etype, emsg, tail = "failed", "RerunTimeout", f"重跑超过 {rcfg.get('timeout_sec')} 秒", ""
    except FileNotFoundError as exc:
        fail(f"重跑命令无法执行：{exc}。请检查 config.yaml 中 rerun.command 和 rerun.workdir。")
    return {
        "attempt": attempt,
        "status": status,
        "started_at": started,
        "duration_sec": round(time.monotonic() - t0, 1),
        "error_type": etype,
        "error_message": mask_pii(emsg),
        "output_tail": mask_pii(tail) if status == "unknown" else None,
    }


def rerun_case(case: dict, cfg: dict, tmpdir: Path) -> tuple[str, dict]:
    attempts = []
    for i in range(1, int(cfg["rerun"].get("attempts", 1)) + 1):
        res = run_once(case, i, cfg, tmpdir)
        attempts.append(res)
        log.info("重跑 %s 第 %d 次：%s", case["case_id"], i, res["status"])
        if res["status"] == "passed":
            break
    return case["case_id"], {
        "attempts": attempts,
        "passed_on_rerun": any(a["status"] == "passed" for a in attempts),
        "all_unknown": all(a["status"] == "unknown" for a in attempts),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--failures", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip", action="store_true", help="不重跑，只生成标记为 skipped 的结果")
    ap.add_argument("--only", help="只重跑这些用例，逗号分隔")
    args = ap.parse_args()

    data = read_json(args.failures)
    out = {"run_id": data["run_id"], "generated_at": now_iso(), "skipped": args.skip, "results": {}}
    if args.skip:
        write_json(args.out, out)
        log.warning("已跳过重跑。分类时不会出现“重跑可过”，请在汇报中说明。")
        return

    cfg = load_config(args.config)
    if "rerun" not in cfg or "command" not in cfg["rerun"]:
        fail("config.yaml 缺少 rerun.command")

    cases = data["cases"]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c["case_id"] in wanted]
    missing = [c["case_id"] for c in cases if not c.get("nodeid")]
    if missing:
        log.warning("以下用例没有 nodeid，无法重跑：%s", ", ".join(missing))
    cases = [c for c in cases if c.get("nodeid")]

    with tempfile.TemporaryDirectory(prefix="rerun_") as tmp:
        tmpdir = Path(tmp)
        workers = max(1, int(cfg["rerun"].get("parallel", 1)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for case_id, result in pool.map(lambda c: rerun_case(c, cfg, tmpdir), cases):
                out["results"][case_id] = result

    write_json(args.out, out)
    passed = sum(1 for r in out["results"].values() if r["passed_on_rerun"])
    unknown = sum(1 for r in out["results"].values() if r["all_unknown"])
    log.info("重跑 %d 个，通过 %d 个，结果未知 %d 个。写入 %s", len(out["results"]), passed, unknown, args.out)
    if unknown:
        log.warning("有 %d 个用例重跑结果未知，请检查 rerun.command 是否正确生成了 JUnit 结果", unknown)


if __name__ == "__main__":
    main()
