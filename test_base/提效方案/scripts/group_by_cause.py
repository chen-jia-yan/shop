"""第 5 步：把同一根因的失败用例合并成组，一组对应一张 Jira 单。

用法：
    python scripts/group_by_cause.py --classified triage_runs/<run_id>/classified.json \
        --config config/config.yaml --out triage_runs/<run_id>/groups.json

合并依据（全部是确定性计算）：
- 分类（AI 复核意见为 high 置信度时使用复核后的分类，并在组里标注）
- 根因特征：有业务报错时用标准化后的业务报错文字；否则用“异常类型 + 标准化报错信息”
- 失败步骤、市场、模块（可在 config.yaml 的 grouping.keys 中调整）
- 环境问题默认跨市场、跨模块合并为一组
"""
from __future__ import annotations

import argparse
from collections import OrderedDict

from common import (CATEGORIES, OWNERS, load_config, match_any, normalize_signature, now_iso,
                    parse_time, read_json, setup_logging, short_exception_name, write_json)

log = setup_logging()

CATEGORY_ORDER = ["PRODUCT_DEFECT", "ENVIRONMENT", "TEST_DATA", "SCRIPT_ISSUE",
                  "POPUP_INTERFERENCE", "RERUN_PASS", "NEEDS_HUMAN"]
GROUP_EVIDENCE_KINDS = {"error_message", "alert_text", "popup_text", "business_error_text",
                        "data_check", "rerun", "mass_failure", "intercepting_element"}


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


def suggest_priority(category: str, cases: list, jcfg: dict) -> str:
    pr = jcfg.get("priority_rules", {})
    if category in pr.get("low_categories", []):
        return "Low"
    if len(cases) >= int(pr.get("high_if_cases_at_least", 10)):
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classified", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = read_json(args.classified)
    cfg = load_config(args.config)
    jcfg, gcfg = cfg.get("jira", {}), cfg.get("grouping", {})
    keys = gcfg.get("keys", ["category", "signature", "failed_step", "market", "module"])
    merge_env = gcfg.get("merge_environment_across_modules", True)
    create_for = set(jcfg.get("create_for_categories", ["PRODUCT_DEFECT", "ENVIRONMENT", "TEST_DATA"]))

    buckets: "OrderedDict[tuple, dict]" = OrderedDict()
    for case in data["cases"]:
        cat, used_ai = effective_category(case)
        sig, hint = signature(case)
        parts = {"category": cat, "signature": sig,
                 "failed_step": normalize_signature(case.get("failed_step"), 80),
                 "market": case.get("market"), "module": case.get("module")}
        key = (cat,) if (cat == "ENVIRONMENT" and merge_env) else tuple(parts[k] for k in keys)
        b = buckets.setdefault(key, {"category": cat, "signature": sig, "hint": hint,
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
                if e["kind"] in ("data_check", "mass_failure") and dedup in seen:
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
        groups.append({
            "group_id": gid,
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
            "case_ids": [c["case_id"] for c in cases],
            "cases": [{"case_id": c["case_id"], "case_name": c.get("case_name"),
                       "failed_step": c.get("failed_step"), "case_steps": c.get("case_steps") or [],
                       "reason": c.get("reason"), "rule_id": c.get("rule_id"),
                       "screenshots": c.get("screenshots") or [], "page_url": c.get("page_url"),
                       "started_at": c.get("started_at"), "flags": c.get("flags", {}),
                       "ai_review": c.get("ai_review")} for c in cases],
            "evidence": evidence,
            "screenshots": screenshots,
            "test_data": test_data,
            "suggested_priority": suggest_priority(b["category"], cases, jcfg),
            "needs_jira": b["category"] in create_for,
            "environment": environment_block(data.get("environment", {}), data["run_id"], cases),
        })

    out = {"run_id": data["run_id"], "generated_at": now_iso(), "groups": groups,
           "environment": environment_block(data.get("environment", {}), data["run_id"], data["cases"])}
    write_json(args.out, out)
    need = sum(1 for g in groups if g["needs_jira"])
    log.info("%d 个失败用例合并为 %d 组，其中 %d 组需要建 Jira。写入 %s",
             len(data["cases"]), len(groups), need, args.out)
    for g in groups:
        log.info("  %s %-6s %3d 个用例  %s", g["group_id"], g["category_cn"], len(g["case_ids"]),
                 g["root_cause_hint"][:60])


if __name__ == "__main__":
    main()
