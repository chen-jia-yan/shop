"""第 6 步：整理成“提单单元”。默认一个失败用例一张 Jira 单；同一原因的其他用例列在 related_case_ids 里，供分派和查重。

用法：
    python scripts/group_by_cause.py --classified triage_runs/<run_id>/classified.json \
        --config config/config.yaml --out triage_runs/<run_id>/groups.json \
        [--rerun triage_runs/<run_id>/rerun.json]

规则（全部是确定性计算）：
- 分类（AI 复核意见为 high 置信度时使用复核后的分类，并在组里标注）
- 原因特征：有业务报错时用标准化后的业务报错文字；否则用“异常类型 + 标准化报错信息”
- grouping.one_case_per_ticket = true（默认）：一个用例一个组（一张单）；false：同一原因的用例合成一组
- 环境问题默认跨市场、跨模块合并为一组（grouping.merge_environment_across_modules），交给环境负责人
- 重跑结果：pass → 不提单（needs_jira = false）；fail_same → 同一张单写第 1 次和第 2 次；
  fail_diff → 第 2 次单独成一组（group_id 以 -2 结尾），分类为需人工判断，单独分析、单独提单
"""
from __future__ import annotations

import argparse
from collections import OrderedDict, defaultdict
from pathlib import Path

from common import (CATEGORIES, OWNERS, load_config, match_any, normalize_signature, now_iso,
                    parse_time, read_json, setup_logging, short_exception_name, write_json)

log = setup_logging()

CATEGORY_ORDER = ["PRODUCT_DEFECT", "ENVIRONMENT", "TEST_DATA", "SCRIPT_ISSUE",
                  "POPUP_INTERFERENCE", "NEEDS_HUMAN"]
# 写进 Jira 的证据种类（classify_rules.py 输出的 evidence[].kind）；完整日志、截图路径等不进组证据
GROUP_EVIDENCE_KINDS = {"error_message", "popup_text", "system_message", "root_exception", "step_log",
                        "screenshot_observation", "screenshot_text", "data_check", "rerun"}


def effective_category(case: dict) -> tuple[str, bool]:
    """返回 (采用的分类, 是否采用了 AI 复核意见)。只有规则结论为 suspected 且 AI 置信度为 high 时才采用。"""
    ai = case.get("ai_review") or {}
    if (case["status"] == "suspected" and ai.get("confidence") == "high"
            and ai.get("proposed_category") in CATEGORIES and ai.get("evidence_ids")):
        return ai["proposed_category"], True
    return case["category"], False


def root_text(case: dict) -> str | None:
    pe = case.get("popup_evidence") or {}
    for t in [case.get("business_error_text"), pe.get("alert_text")] + [d.get("text") for d in pe.get("dialogs") or []]:
        if t:
            return t.strip()
    return None


def signature(case: dict) -> tuple[str, str]:
    """返回 (用于合并的特征, 根因短语提示)。"""
    # 分类规则已经给出统一的分组键（例如所有“桌面不可用”的用例），直接使用，不再按报错文字细分
    if case.get("group_key"):
        return case["group_key"], case["group_key"].split(":", 1)[-1].replace("-", " ")
    text = root_text(case)
    if text:
        hint = text.splitlines()[0].strip().rstrip(".。!！").lower()[:100]
        return "biz:" + normalize_signature(text, 150), hint
    exc = short_exception_name(case.get("error_type")) or "unknown"
    return f"exc:{exc}|{normalize_signature(case.get('error_message'), 120)}", exc


def join_values(values: list) -> str:
    vals = sorted({v for v in values if v})
    if not vals:
        return "Unknown"
    return vals[0] if len(vals) == 1 else "/".join(vals) if len(vals) <= 3 else "Multiple"


def suggest_priority(category: str, cases: list, jcfg: dict, same_cause: int = 0) -> str:
    """same_cause：同一原因的失败用例总数（一个用例一张单时，看的是同原因用例有多少，而不是这张单里有几个）。"""
    pr = jcfg.get("priority_rules", {})
    if category in pr.get("low_categories", []):
        return "Low"
    if max(len(cases), same_cause) >= int(pr.get("high_if_cases_at_least", 10)):
        return "High"
    if category == "ENVIRONMENT":
        return "High"
    if category == "PRODUCT_DEFECT":
        modules = {c.get("module") for c in cases}
        if modules & set(pr.get("high_impact_modules", [])):
            return "High"
        text = " ".join(f"{c.get('case_name') or ''} {c.get('failed_step') or ''} {c.get('error_message') or ''}"
                        for c in cases)
        if match_any(text, pr.get("high_impact_keywords", [])):
            return "High"
    return pr.get("default", "Medium")


def environment_block(env: dict, run_id: str, cases: list) -> str:
    times = sorted(t for t in (parse_time(c.get("started_at")) for c in cases) if t)
    executed = f"{times[0]:%Y-%m-%d %H:%M} – {times[-1]:%H:%M} (UTC+8)" if times else "待补充"
    lines = [
        f"Environment: {env.get('env_name') or '待补充'}",
        f"Browser: {env.get('browser') or '待补充'} {env.get('browser_version') or ''}".rstrip(),
        f"Driver: {env.get('driver_version') or '待补充'}",
        f"OS: {env.get('os') or '待补充'}",
        f"Run ID: {run_id}",
        f"Build: {env.get('build') or '待补充'}",
        f"Executed at: {executed}",
    ]
    return "\n".join(lines)


def case_entry(c: dict, rerun: dict) -> dict:
    rr = (rerun.get("results") or {}).get(c["case_id"]) or {}
    return {"case_id": c["case_id"], "case_name": c.get("case_name"),
            "failed_step": c.get("failed_step"), "case_steps": c.get("case_steps") or [],
            "reason": c.get("reason"), "rule_id": c.get("rule_id"),
            "screenshots": c.get("screenshots") or [], "page_url": c.get("page_url"),
            "started_at": c.get("started_at"), "flags": c.get("flags", []),
            "rerun_result": c.get("rerun_result"), "rerun_attempts": rr.get("attempts", []),
            "ai_review": c.get("ai_review")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classified", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--rerun", help="rerun.json（可选）：用于在单里写第 2 次执行的报错和截图")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = read_json(args.classified)
    cfg = load_config(args.config)
    rerun = read_json(args.rerun) if args.rerun and Path(args.rerun).exists() else {"results": {}}
    jcfg, gcfg = cfg.get("jira", {}), cfg.get("grouping", {})
    keys = gcfg.get("keys", ["category", "signature", "failed_step", "market", "module"])
    merge_env = gcfg.get("merge_environment_across_modules", True)
    one_case = gcfg.get("one_case_per_ticket", True)
    create_for = set(jcfg.get("create_for_categories", ["PRODUCT_DEFECT", "ENVIRONMENT", "TEST_DATA"]))

    buckets: "OrderedDict[tuple, dict]" = OrderedDict()
    cause_members = defaultdict(list)
    for case in data["cases"]:
        cat, used_ai = effective_category(case)
        sig, hint = signature(case)
        parts = {"category": cat, "signature": sig,
                 "failed_step": normalize_signature(case.get("failed_step"), 80),
                 "market": case.get("market"), "module": case.get("module")}
        env_merged = cat == "ENVIRONMENT" and merge_env
        cause_key = (cat,) if env_merged else tuple(parts[k] for k in keys)
        cause_members[cause_key].append(case["case_id"])
        key = cause_key if (env_merged or not one_case) else cause_key + (case["case_id"],)
        b = buckets.setdefault(key, {"category": cat, "signature": sig, "hint": hint, "cause_key": cause_key,
                                     "cases": [], "used_ai": [], "rules": set(), "statuses": set()})
        b["cases"].append(case)
        b["rules"].add(case["rule_id"])
        b["statuses"].add(case["status"])
        if used_ai:
            b["used_ai"].append(case["case_id"])

    ordered = sorted(buckets.values(),
                     key=lambda b: (CATEGORY_ORDER.index(b["category"]), -len(b["cases"])))
    groups = []
    for i, b in enumerate(ordered, 1):
        gid = f"G{i:02d}"
        cases = b["cases"]
        evidence, seen = [], set()
        for c in cases:
            for e in c.get("evidence", []):
                if e["kind"] not in GROUP_EVIDENCE_KINDS:
                    continue
                dedup = (e["kind"], e.get("content"))
                if e["kind"] == "data_check" and dedup in seen:
                    continue
                seen.add(dedup)
                evidence.append({"id": f"{gid}-E{len(evidence) + 1}", "case_id": c["case_id"],
                                 "ref": e["id"], "kind": e["kind"], "content": (e.get("content") or "")[:1500]})
        screenshots = [p for c in cases for p in (c.get("screenshots") or [])]
        test_data = {}
        for c in cases:
            for k, v in (c.get("test_data") or {}).items():
                if v is not None and str(v) not in test_data.setdefault(k, []):
                    test_data[k].append(str(v))
        ids = [c["case_id"] for c in cases]
        # 重跑通过的用例是偶发，不提单
        live = [c for c in cases if c.get("rerun_result") != "pass"]
        group = {
            "group_id": gid,
            "attempt": 1,
            "category": b["category"],
            "category_cn": CATEGORIES[b["category"]],
            "owner": OWNERS[b["category"]],
            "status": "confirmed" if b["statuses"] == {"confirmed"} else "suspected",
            "rule_ids": sorted(b["rules"]),
            "ai_adjusted_cases": b["used_ai"],
            "system": join_values([c.get("system") for c in cases]),
            "market": join_values([c.get("market") for c in cases]),
            "module": join_values([c.get("module") for c in cases]),
            "signature": b["signature"],
            "root_cause_hint": b["hint"],
            "case_ids": ids,
            "related_case_ids": [x for x in cause_members[b["cause_key"]] if x not in ids],
            "rerun_results": {c["case_id"]: c.get("rerun_result") for c in cases if c.get("rerun_result")},
            "cases": [case_entry(c, rerun) for c in cases],
            "evidence": evidence,
            "screenshots": screenshots,
            "test_data": test_data,
            "suggested_priority": suggest_priority(b["category"], cases, jcfg, len(cause_members[b["cause_key"]])),
            "needs_jira": b["category"] in create_for and bool(live),
            "environment": environment_block(data.get("environment", {}), data["run_id"], cases),
        }
        groups.append(group)
        # 重跑失败但报错与第一次不同：第 2 次单独成组，单独分析、单独提单
        for c in cases:
            if c.get("rerun_result") != "fail_diff":
                continue
            att = [a for a in ((rerun.get("results") or {}).get(c["case_id"]) or {}).get("attempts", []) if a.get("status") == "failed"]
            last = att[-1] if att else {}
            err = f"{last.get('error_type') or ''}: {last.get('error_message') or ''}".strip(": ")
            g2 = f"{gid}-2" if len(cases) == 1 else f"{gid}-{c['case_id']}-2"
            groups.append({
                **{k: group[k] for k in ("system", "market", "module", "test_data", "environment")},
                "group_id": g2, "attempt": 2, "first_attempt_group": gid,
                "category": "NEEDS_HUMAN", "category_cn": CATEGORIES["NEEDS_HUMAN"], "owner": OWNERS["NEEDS_HUMAN"],
                "status": "suspected", "rule_ids": ["RERUN-DIFF"], "ai_adjusted_cases": [],
                "signature": "rerun2:" + normalize_signature(err, 120), "root_cause_hint": (err.splitlines() or [""])[0][:100],
                "case_ids": [c["case_id"]], "related_case_ids": [], "rerun_results": {c["case_id"]: "fail_diff"},
                "cases": [case_entry(c, rerun)],
                "evidence": [{"id": f"{g2}-E1", "case_id": c["case_id"], "ref": "rerun", "kind": "rerun",
                              "content": f"第 2 次（重跑，{last.get('started_at') or '时间未知'}）报错：{err[:1400]}"}],
                "screenshots": [], "suggested_priority": jcfg.get("priority_rules", {}).get("default", "Medium"),
                "needs_jira": True,
            })

    out = {"run_id": data["run_id"], "generated_at": now_iso(), "groups": groups,
           "one_case_per_ticket": one_case,
           "environment": environment_block(data.get("environment", {}), data["run_id"], data["cases"])}
    write_json(args.out, out)
    need = sum(1 for g in groups if g["needs_jira"])
    skipped = sum(1 for c in data["cases"] if c.get("rerun_result") == "pass")
    log.info("%d 个失败用例整理为 %d 个提单单元（%s），其中 %d 个需要建 Jira；重跑通过不提单 %d 个。写入 %s",
             len(data["cases"]), len(groups), "一个用例一张单" if one_case else "同一原因合并", need, skipped, args.out)
    for g in groups:
        log.info("  %s %-6s %3d 个用例  %s", g["group_id"], g["category_cn"], len(g["case_ids"]),
                 g["root_cause_hint"][:60])


if __name__ == "__main__":
    main()
