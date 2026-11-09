"""第 7 步之后：校验 AI 起草的 drafts.json，不通过就不能生成审核表。

用法：
    python scripts/validate_drafts.py --drafts triage_runs/<run_id>/drafts.json \
        --groups triage_runs/<run_id>/groups.json --config config/config.yaml

检查项（任一错误都会以退出码 1 结束）：
 1. 每个需要建单的组都有草稿；草稿的 group_id 必须存在。
 2. Summary 符合 ROTQA 格式，市场、模块、系统与组信息一致，case/cases 单复数正确，长度不超过 255。
 3. Summary 中的根因短语必须能在证据中找到（词语重合度 >= 60%），防止编造原因。
 4. Description 包含全部 8 个小节；列出了组内用例（超过上限时需说明见附件）。
 5. Description 中引用的截图文件名必须真实存在于该组截图中。
 6. claims 中的每条事实（fact）都要有证据编号，且编号存在于该组证据中；有推测时第 8 节不能为空。
 7. Summary 和 Description 中不能出现证件号、手机号、邮箱、银行卡号。
 8. Priority 是合法值；Labels 不含空格。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import load_config, mask_pii, read_json, setup_logging

log = setup_logging()

SUMMARY_RE = re.compile(
    r"^\[(?P<system>[A-Za-z0-9 ]+) Regression\] (?P<market>[A-Za-z/]+) - (?P<module>.+?) "
    r"(?P<noun>cases?) failed due to (?P<cause>.+)$")
SECTIONS = ["h3. 1. 现象", "h3. 2. 受影响的用例", "h3. 3. 重现步骤", "h3. 4. 预期结果",
            "h3. 5. 实际结果", "h3. 6. 已做的排查", "h3. 7. 测试数据", "h3. 8. 推测与待确认"]
PRIORITIES = {"Highest", "High", "Medium", "Low", "Lowest"}
IMG_RE = re.compile(r"!([^!|\n]+?)(?:\|[^!\n]*)?!")
WORD_RE = re.compile(r"[a-z0-9一-鿿]+")
STOP = {"the", "a", "an", "of", "to", "is", "on", "in", "and", "for", "with", "when", "at"}
# 描述现象的通用词，不要求出现在证据中
GENERIC = {"test", "environment", "env", "returned", "returns", "return", "error", "errors", "mismatch",
           "page", "not", "displayed", "missing", "version", "unexpected", "failure", "issue", "value"}


def words(text: str) -> set[str]:
    return {w for w in WORD_RE.findall((text or "").lower()) if w not in STOP}


def section_body(desc: str, idx: int) -> str:
    start = desc.find(SECTIONS[idx])
    if start < 0:
        return ""
    end = desc.find(SECTIONS[idx + 1]) if idx + 1 < len(SECTIONS) else len(desc)
    return desc[start + len(SECTIONS[idx]):end if end > 0 else len(desc)].strip()


def check_draft(d: dict, g: dict, cfg: dict) -> list[str]:
    errs = []
    gid = g["group_id"]
    summary, desc = d.get("summary") or "", d.get("description") or ""

    # 2. Summary 格式
    m = SUMMARY_RE.match(summary)
    if not m:
        errs.append(f"{gid} Summary 格式不符合模板：{summary!r}")
    else:
        if g["system"] != "Unknown" and m["system"].strip() != g["system"]:
            errs.append(f"{gid} Summary 中的系统 {m['system']!r} 与组信息 {g['system']!r} 不一致")
        if g["market"] not in ("Unknown", "Multiple") and m["market"] != g["market"]:
            errs.append(f"{gid} Summary 中的市场 {m['market']!r} 与组信息 {g['market']!r} 不一致")
        if g["module"] not in ("Unknown", "Multiple") and g["module"] not in m["module"]:
            errs.append(f"{gid} Summary 中的模块 {m['module']!r} 与组信息 {g['module']!r} 不一致")
        expected_noun = "case" if len(g["case_ids"]) == 1 else "cases"
        if m["noun"] != expected_noun:
            errs.append(f"{gid} 组内有 {len(g['case_ids'])} 个用例，应写 {expected_noun!r}")
        cause = m["cause"]
        if len(cause.split()) > 12:
            errs.append(f"{gid} 根因短语超过 12 个单词：{cause!r}")
        # 3. 根因必须有证据支撑：除通用描述词外，根因中的词要能在证据、用例名、失败步骤、环境信息中找到
        pool = " ".join([g["root_cause_hint"], g["system"], g["market"], g["module"], g.get("environment", "")]
                        + [e.get("content", "") for e in g["evidence"]]
                        + [f"{c.get('case_name') or ''} {c.get('failed_step') or ''}" for c in g.get("cases", [])])
        evidence_words = words(pool)
        cw = words(cause) - GENERIC
        if cw:
            overlap = len(cw & evidence_words) / len(cw)
            if overlap < 0.6:
                errs.append(f"{gid} 根因短语 {cause!r} 中只有 {overlap:.0%} 的词能在证据中找到，"
                            f"请使用证据原文（参考：{g['root_cause_hint']!r}）")
    if len(summary) > 255:
        errs.append(f"{gid} Summary 超过 255 个字符")

    # 4. Description 小节与用例列表
    for s in SECTIONS:
        if s not in desc:
            errs.append(f"{gid} Description 缺少小节：{s}")
    limit = int(cfg.get("jira", {}).get("max_cases_in_table", 20))
    listed = g["case_ids"][:limit]
    missing = [c for c in listed if c not in desc]
    if missing:
        errs.append(f"{gid} Description 中没有列出这些用例：{', '.join(missing[:10])}")
    if len(g["case_ids"]) > limit and "affected_cases.csv" not in desc:
        errs.append(f"{gid} 用例超过 {limit} 个，需注明“其余用例见附件 affected_cases.csv”")

    # 5. 截图引用
    shot_names = {Path(p).name for p in g.get("screenshots", [])}
    for ref in IMG_RE.findall(desc):
        if ref not in shot_names:
            errs.append(f"{gid} Description 引用了不存在的截图：{ref}")

    # 6. claims
    ev_ids = {e["id"] for e in g["evidence"]}
    claims = d.get("claims") or []
    if not claims:
        errs.append(f"{gid} 缺少 claims，无法核对事实来源")
    has_inference = False
    for i, c in enumerate(claims, 1):
        ctype = c.get("type")
        if ctype not in ("fact", "inference"):
            errs.append(f"{gid} claims 第 {i} 条 type 必须是 fact 或 inference")
            continue
        if ctype == "fact":
            ids = c.get("evidence_ids") or []
            if not ids:
                errs.append(f"{gid} 事实“{c.get('text', '')[:40]}”没有证据编号，请补充或改为 inference")
            bad = [x for x in ids if x not in ev_ids]
            if bad:
                errs.append(f"{gid} 事实“{c.get('text', '')[:40]}”引用了不存在的证据：{', '.join(bad)}")
        else:
            has_inference = True
    if has_inference:
        body = section_body(desc, 7)
        if not body or body.startswith("无"):
            errs.append(f"{gid} 有推测（inference），但第 8 节“推测与待确认”为空")

    # 7. 个人信息
    for name, text in (("Summary", summary), ("Description", desc)):
        masked = mask_pii(text)
        if masked != text:
            errs.append(f"{gid} {name} 中疑似包含个人信息（证件号/电话/邮箱/卡号），请删除或替换")

    # 8. 其他字段
    if d.get("priority") and d["priority"] not in PRIORITIES:
        errs.append(f"{gid} Priority 不合法：{d['priority']!r}")
    for lb in d.get("labels") or []:
        if " " in lb:
            errs.append(f"{gid} Label 不能包含空格：{lb!r}")
    return errs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    drafts = read_json(args.drafts).get("drafts", [])
    groups = {g["group_id"]: g for g in read_json(args.groups)["groups"]}
    cfg = load_config(args.config)

    errors = []
    by_gid = {}
    for d in drafts:
        gid = d.get("group_id")
        if gid not in groups:
            errors.append(f"草稿的 group_id {gid!r} 在 groups.json 中不存在")
            continue
        if gid in by_gid:
            errors.append(f"{gid} 有重复的草稿")
        by_gid[gid] = d
        errors.extend(check_draft(d, groups[gid], cfg))
    for gid, g in groups.items():
        if g["needs_jira"] and gid not in by_gid:
            errors.append(f"{gid}（{g['category_cn']}）需要建单，但没有草稿")

    if errors:
        print(f"校验未通过，共 {len(errors)} 个问题：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    log.info("校验通过：%d 份草稿", len(by_gid))


if __name__ == "__main__":
    main()
