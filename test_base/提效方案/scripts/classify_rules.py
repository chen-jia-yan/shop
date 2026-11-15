"""第 2 步：分析每个失败用例的根本原因，并给出重跑建议。

判断逻辑与“测试分析助手”页面完全相同（同一套规则编号、判断顺序、结论文字）：
- 判断代码：scripts/ta_engine.py（页面 engine.js 的 Python 版），用 evals/check_consistency.py 确认两边一致；
- 规则内容：config/rules.json（页面“配置 → 判断规则 → 下载规则文件”得到的就是这个文件）；
- 人工记录：工作文件 workspace.json（页面“保存工作文件”得到；本脚本也会写出一份，页面可以直接打开）。

用法：
    python scripts/classify_rules.py --failures triage_runs/<run_id>/failures.json \
        --out triage_runs/<run_id>/classified.json \
        [--rules config/rules.json] [--workspace <页面保存的工作文件>] [--ocr <截图识别结果.ocr.json> ...] \
        [--data-checks triage_runs/<run_id>/data_checks.yaml] [--rerun triage_runs/<run_id>/rerun.json] \
        [--config config/config.yaml]

顺序：先分类，再判断要不要重跑。第一次运行不需要 --rerun；重跑完成后（第 4 步）带上 --rerun 再运行一次。
重跑结果不改变分类，只决定后续处理：pass 偶发不提单；fail_same 问题必现；fail_diff 第 2 次单独分析、单独提单。

人工记录（截图观察、数据核查、人工改判、重跑结果）从哪里来：
- 工作文件（--workspace）：在页面里看截图、选核查结果后“保存工作文件”，按用例编号对应；
- data_checks.yaml：直接填写核查结果（格式见 data-contract.md 第 4 节）；工作文件里已有的以工作文件为准；
- rerun.json：rerun_failed.py 的重跑结果；有它时以它为准。
截图文字：--ocr 指定「识别截图.bat」的结果文件，按截图指纹对应；没有时使用工作文件里的截图文字。

输出（与 out 同目录）：
- classified.json：每个用例的分类、规则、状态、一句话结论、判断依据、证据、重跑建议；
- workspace.json：同样的数据，页面“打开工作文件”可以直接打开，在页面上看截图、补人工记录；
- rerun_plan.json：建议立即重跑（go）和处理后再重跑（fix）的名单；
- data_checks.todo.yaml：需要人工核查的清单。
所有写出的文字都已脱敏。本脚本不调用任何模型，同样的输入永远得到同样的输出。
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import ta_engine as T
from common import (CATEGORIES, OWNERS, mask_pii, normalize_signature, now_iso, read_json,
                    read_yaml, setup_logging, short_exception_name, write_json, write_yaml)

log = setup_logging()

DATA_KEYS = ("agent_code", "product_code", "policy_no", "proposal_no", "plan_code")
# data_checks.yaml 的旧写法 → 页面的核查结果
CHECK_ALIAS = {"invalid_state": "invalid"}
ALL_CHECKS = {v for k in T.CHECK_KINDS.values() for v in k["options"]}


# ---------------------------------------------------------------- 输入整理

def data_keys(case: dict) -> list[str]:
    td = case.get("test_data") or {}
    return [f"{k}={td[k]}" for k in DATA_KEYS if td.get(k)]


def rerun_result(case: dict, rr: dict | None) -> str | None:
    """pass / fail_same（报错与第一次相同）/ fail_diff（报错不同，第 2 次单独分析）。"""
    if not rr or rr.get("all_unknown"):
        return None
    if rr.get("passed_on_rerun"):
        return "pass"
    failed = [a for a in rr.get("attempts", []) if a.get("status") == "failed"]
    if not failed:
        return None
    last = failed[-1]
    same_type = (short_exception_name(last.get("error_type")) or "") == (short_exception_name(case.get("error_type")) or "")
    a, b = normalize_signature(last.get("error_message"), 80), normalize_signature(case.get("error_message"), 80)
    return "fail_same" if same_type and (not a or not b or a == b) else "fail_diff"


def to_engine_case(f: dict, seq: int, run_id: str, rules: dict) -> dict:
    """failures.json 的一条用例 → 页面字段。"""
    pe = f.get("popup_evidence") or {}
    page = [f.get("business_error_text"), pe.get("alert_text")] + [d.get("text") for d in pe.get("dialogs") or []]
    err, stack = f.get("error_message") or "", f.get("stack_trace") or ""
    # 有 Python 异常链时，异常类型由分析核心从链的第一段取（与页面相同）；没有时才用结果文件里的异常类型
    raw = "" if re.search(r"Traceback|During handling", err + "\n" + stack) else (f.get("error_type") or "")
    c = T.make_case({
        "uid": f.get("ws_uid") or f"{run_id}#{seq}", "run": f.get("ws_run") or run_id, "seq": seq,
        "id": f["case_id"], "name": f.get("case_name"), "result": "failed", "failed": True,
        "error": err, "stack": stack, "exceptionRaw": raw,
        "pageText": "\n".join(dict.fromkeys(t.strip() for t in page if t and t.strip())),
        "screenshot": ";".join(f.get("screenshots") or []), "start": f.get("started_at"), "module": f.get("module"),
    }, rules)
    if not c["alertText"] and pe.get("alert_text"):
        c["alertText"] = pe["alert_text"]
    return c


def build_cases(data: dict, ws: dict | None, rules: dict) -> list[dict]:
    """组成整批用例（含通过的用例）。整批规律（环境中断的起点、大面积相同报错）需要知道通过的用例在哪里。"""
    run_id = data["run_id"]
    fails = data["cases"]
    ws_run = None
    if ws:
        ids = {f["case_id"] for f in fails}
        runs = [r["id"] for r in ws.get("runs") or []]
        # 选和 failures.json 用例重合最多的批次
        ws_run = max(runs, key=lambda r: sum(1 for c in ws["cases"] if c.get("run") == r and c.get("id") in ids), default=None)
    ws_cases = [c for c in (ws or {}).get("cases", []) if c.get("run") == ws_run and not c.get("parent")]
    ws_by_id = {c["id"]: c for c in ws_cases}

    if all(ws_by_id.get(f["case_id"]) for f in fails) and ws_cases:
        seq_of = {f["case_id"]: ws_by_id[f["case_id"]]["seq"] for f in fails}
        for f in fails:
            f.setdefault("ws_uid", ws_by_id[f["case_id"]].get("uid"))
            f.setdefault("ws_run", ws_run)
        passed = [T.make_case(dict(c), rules) for c in ws_cases if c["id"] not in seq_of]
    elif fails and all(f.get("execution_index") for f in fails):
        seq_of = {f["case_id"]: int(f["execution_index"]) for f in fails}
        total = int(data.get("total_cases") or max(seq_of.values()))
        used = set(seq_of.values())
        # 结果文件里没有通过用例的详情：按执行序号补上占位，保证“连续到运行结束”的判断与页面相同
        passed = [T.make_case({"uid": f"{run_id}#{n}", "run": run_id, "seq": n, "id": f"（通过）#{n}", "result": "passed",
                               "failed": False, "name": "（结果文件里没有通过用例的详情）"}, rules)
                  for n in range(1, total + 1) if n not in used]
    else:
        seq_of = {f["case_id"]: i for i, f in enumerate(fails, 1)}
        passed = []
        if data.get("total_cases"):
            log.warning("failures.json 没有 execution_index（执行序号），无法判断“环境中断后一直没恢复”；只按失败用例的顺序分析")
    return [to_engine_case(f, seq_of[f["case_id"]], run_id, rules) for f in fails] + passed


def apply_human(cases, ws, checks, rerun, ocr_index, fails_by_id):
    """把人工记录和截图文字写进用例。返回 {来源: 条数}。"""
    stat = Counter()
    ws_by_id = {c["id"]: c for c in (ws or {}).get("cases", []) if not c.get("parent")}
    for c in cases:
        if not c.get("failed"):
            continue
        w = ws_by_id.get(c["id"]) or {}
        for k in T.WS_HUMAN_FIELDS:
            if w.get(k) not in (None, ""):
                c[k] = w[k]
                stat["工作文件 " + k] += 1
        f = fails_by_id.get(c["id"]) or {}
        if not c.get("dataCheck"):
            r, note = check_from_yaml(c["id"], data_keys(f), checks)
            if r:
                c["dataCheck"], c["dataNote"] = r, note
                stat["data_checks.yaml"] += 1
        rr = rerun_result(f, (rerun.get("results") or {}).get(c["id"]))
        if rr:
            c["rerun"] = "pass" if rr == "pass" else "fail"
            c["r2"] = {"same": None} if rr == "pass" else {"same": rr == "fail_same"}
            c["rerunNote"] = "rerun.json"
            stat["rerun.json"] += 1
        if ocr_index and f.get("screenshots"):
            t = T.ocr_for_files(f["screenshots"], ocr_index)
            if t:
                c["ocrText"] = t
                stat["截图识别结果"] += 1
    return stat


def check_from_yaml(case_id: str, keys: list[str], checks: dict) -> tuple[str | None, str]:
    """data_checks.yaml → 页面的核查结果。
    按用例填写的（key: case=<用例编号>）直接使用；按数据填写的：有一项有问题就用那一项，全部核查过且都正常才算“正常”。"""
    res = lambda k: CHECK_ALIAS.get((checks.get(k) or {}).get("result"), (checks.get(k) or {}).get("result"))
    note = lambda ks: "；".join(f"{k}：{checks[k].get('note')}" for k in ks if checks.get(k, {}).get("note"))
    k = f"case={case_id}"
    if res(k) in ALL_CHECKS:
        return res(k), note([k])
    bad = [k for k in keys if res(k) in ALL_CHECKS and res(k) != "ok"]
    if bad:
        return res(bad[0]), note(bad)
    if keys and all(res(k) == "ok" for k in keys):
        return "ok", note(keys)
    return None, ""


def load_checks(path: str | None) -> dict:
    items = read_yaml(path, default=[]) if path and Path(path).exists() else []
    return {str(i["key"]).strip(): i for i in items or [] if i.get("key")}


# ---------------------------------------------------------------- 输出

KIND_OF = {"msg": "error_message", "page": "popup_text", "sys": "system_message", "root": "root_exception",
           "step": "step_log", "loc": "failure_location", "win": "open_windows", "handler": "handler_error",
           "stack": "stack_trace", "exc": "error_type", "shot": "screenshot", "obs": "screenshot_observation",
           "ocr": "screenshot_text", "rerun": "rerun", "data": "data_check"}


def out_case(f: dict, c: dict, prev_review: dict, mask) -> dict:
    r = T.mask_deep(T.result_of(c), mask)
    final = r["category"]
    rr = None
    if c.get("rerun"):
        rr = "pass" if c["rerun"] == "pass" else "fail_diff" if (c.get("r2") or {}).get("same") is False else "fail_same"
    return {
        **f,
        "category": final, "category_cn": CATEGORIES[final], "owner": OWNERS[final],
        "auto_category": r["auto_category"], "status": r["status"], "rule_id": r["rule_id"], "rule_name": r["rule_name"],
        "reason": r["brief"], "brief": r["brief"], "why": r["why"], "need": r["need"],
        "needs_human_reason": r["reason_code"] if final == "NEEDS_HUMAN" else None,
        "flags": r["flags"], "check_kind": r["check_kind"], "phase": r["phase"], "from_ocr": r["from_ocr"],
        "group_key": c["auto"].get("groupKey"),
        # 证据编号与“判断依据”里的 E1、E2 对应
        "evidence": [{"id": e["id"], "kind": KIND_OF.get(e["kind"], e["kind"]), "label": e["label"], "content": e["text"]} for e in r["evidence"]],
        "evidence_ids": [e["id"] for e in r["evidence"]],
        "human": {k: T.mask_deep(c[k], mask) for k in ("obs", "dataCheck", "dataNote", "override") if c.get(k)},
        "log_summary": {"test_function": c["L"]["testFn"], "failure_path": c["L"]["path"], "screen": c["L"]["screen"],
                        "success_marks": c["L"]["success"], "open_windows": c["L"]["windows"]} if c.get("L") else None,
        "rerun_result": rr, "rerun_plan": r["rerun_plan"], "ai_review": prev_review.get(f["case_id"]),
    }


def todo_items(out_cases: list, fails_by_id: dict) -> list:
    todo = {}
    for oc in out_cases:
        kind = oc.get("check_kind")
        if not kind or oc["human"].get("dataCheck") or oc["human"].get("override"):
            continue
        keys = data_keys(fails_by_id[oc["case_id"]]) if kind == "biz" else []
        for key in keys or [f"case={oc['case_id']}"]:
            item = todo.setdefault(key, {"key": key, "kind": kind, "question": T.CHECK_KINDS[kind]["name"],
                                         "options": {v: o[0] for v, o in T.CHECK_KINDS[kind]["options"].items()},
                                         "result": None, "checked_by": None, "checked_at": None, "method": None, "note": None, "cases": []})
            item["cases"].append(oc["case_id"])
    return list(todo.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--failures", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rules", default=str(T.RULES_FILE))
    ap.add_argument("--workspace")
    ap.add_argument("--ocr", nargs="*")
    ap.add_argument("--data-checks")
    ap.add_argument("--rerun")
    ap.add_argument("--config", default="config/config.yaml", help="保留参数，便于沿用旧命令；分类不再读取它")
    args = ap.parse_args()

    data = read_json(args.failures)
    rules = T.load_rules(args.rules)
    names = [n for n in rules.get("pii_names") or []]
    mask = lambda s: mask_pii(s, names) if isinstance(s, str) else s
    ws = T.read_workspace(args.workspace) if args.workspace else None
    if ws and ws.get("rules"):
        diff = sorted(k for k in set(ws["rules"]) | set(rules) if ws["rules"].get(k) != rules.get(k))
        if diff:
            log.warning("工作文件里的规则与 %s 不同（%s）。以 %s 为准；如要采用页面上的规则，在页面“下载规则文件”覆盖它",
                        args.rules, "、".join(diff[:8]), args.rules)
    rerun = read_json(args.rerun) if args.rerun and Path(args.rerun).exists() else {"results": {}, "skipped": True}
    ocr_index = T.load_ocr_index(args.ocr) if args.ocr else None

    fails_by_id = {f["case_id"]: f for f in data["cases"]}
    cases = build_cases(data, ws, rules)
    stat = apply_human(cases, ws, load_checks(args.data_checks), rerun, ocr_index, fails_by_id)
    if stat:
        log.info("读取人工记录：%s", "，".join(f"{k} {n}" for k, n in stat.items()))
    T.classify_all(cases, rules)

    prev_review = {}
    if Path(args.out).exists():  # 第 5 步重新分类时保留第 3 步写下的 AI 复核意见
        prev_review = {c["case_id"]: c.get("ai_review") for c in read_json(args.out).get("cases", []) if c.get("ai_review")}
    by_id = {c["id"]: c for c in cases if c.get("failed")}
    out_cases = [out_case(f, by_id[f["case_id"]], prev_review, mask) for f in data["cases"]]

    by_cat = Counter(c["category"] for c in out_cases)
    by_status = Counter(c["status"] for c in out_cases)
    write_json(args.out, {
        "run_id": data["run_id"], "generated_at": now_iso(), "engine": "ta_engine（与页面 engine.js 相同）",
        "rules_file": str(Path(args.rules).resolve()), "environment": data.get("environment", {}),
        "rerun_skipped": bool(rerun.get("skipped")), "cases": out_cases,
        "summary": {"total_failed": len(out_cases), "by_category": {k: by_cat.get(k, 0) for k in CATEGORIES},
                    "by_status": dict(by_status), "by_rule": dict(Counter(c["rule_id"] for c in out_cases)),
                    "by_rerun_advice": dict(Counter(c["rerun_plan"]["advice"] for c in out_cases)),
                    "needs_human_reasons": dict(Counter(c["needs_human_reason"] for c in out_cases if c["needs_human_reason"]))},
    })

    run_dir = Path(args.out).parent
    runs = [{"id": cases[0]["run"] if cases else data["run_id"], "name": data["run_id"], "total": len(cases), "at": data.get("loaded_at")}]
    T.write_workspace(run_dir / "workspace.json", runs, sorted(cases, key=lambda c: c["seq"]), rules, mask)

    write_json(run_dir / "rerun_plan.json", {
        "run_id": data["run_id"], "generated_at": now_iso(),
        "go": [c["case_id"] for c in out_cases if c["rerun_plan"]["advice"] == "go"],
        "fix": [c["case_id"] for c in out_cases if c["rerun_plan"]["advice"] == "fix"],
        "items": [{"case_id": c["case_id"], "category": c["category"], **c["rerun_plan"]} for c in out_cases]})

    todo_path = run_dir / "data_checks.todo.yaml"
    todo = todo_items(out_cases, fails_by_id)
    if todo:
        write_yaml(todo_path, todo)
        log.info("有 %d 项需要人工核查，清单：%s（也可以在页面打开 workspace.json 直接选择核查结果）", len(todo), todo_path)
    elif todo_path.exists():
        todo_path.unlink()

    log.info("分类完成：%s", "，".join(f"{CATEGORIES[k]} {n}" for k, n in by_cat.items() if n))
    log.info("已确认 %d / 待复核 %d；重跑建议：%s", by_status.get("confirmed", 0), by_status.get("suspected", 0),
             "，".join(f"{k} {n}" for k, n in Counter(c["rerun_plan"]["advice"] for c in out_cases).items()))
    log.info("工作文件：%s（可在页面“打开工作文件”查看截图、补充人工记录）", run_dir / "workspace.json")


if __name__ == "__main__":
    main()
