# -*- coding: utf-8 -*-
"""
变更影响分析 —— 第 3 步：评估重要度、影响度与级别

用法：
  python score.py changes.json [--refs refs.json] [--notes notes.json] -o scored.json

评分模型（全部参数在 tap-config/impact.json 与 rules.json，报告会逐条写出依据）：
  重要度 = 类别权重（涉及多个类别取最高） + 信号加分
           信号：数值变化、数值变动幅度大、义务表述、否定词、适用范围、日期、删除含术语内容、新增含术语条款
           只改措辞 / 只调整位置：重要度不超过 minor_cap
  影响度 = 知识库中含旧值的内容（每处 stale_ref，封顶 stale_cap）
         + 需复核的相关内容（每处 related_ref，封顶 related_cap）
         + 对客（customer）+ 涉及系统参数（system）+ 距生效日越近加分越多（urgent_days）
  综合分 = 重要度 × weights.importance + 影响度 × weights.impact，按 levels 阈值定级
  级别下限：floors 中的高风险情形（如保险责任里出现否定词变化）级别不低于指定值
  人工复核：notes.json 的 overrides 可改级别、类别、处置事项或忽略某条（须写明原因，报告中保留痕迹）

这套评分是**初筛**：给模型一个起点、给报告一个可解释的参照，不是结论。
最终结论来自 --judgments（模型按 reference/methods.md 读原文作出的判断，经 judgments.py 护栏检查）；
初筛结果保留在每条变更的 prior 字段，报告里与分析结论并列，便于看出判断改了什么。
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import add_cli_args, configure     # noqa: E402

import judgments                              # noqa: E402

from ci_common import (L, R, cat_by_key, categories, fallback_category, find_terms, fmt_date, imp, level_name,  # noqa: E402
                       level_of, level_order, load_json, more_severe, parse_date, save_json, today)
import datetime as dt                         # noqa: E402


def _categories_of(ch):
    """类别来源（按权重从高到低排序）：
    ① 被改动的文字里的术语（没有时用整段术语）；② 数值的上下文词；③ 所在章节标题里的术语。
    ③ 用来纠正“改动处只有一个词、却在‘责任免除’一章里”这类情况。"""
    sig = ch["signals"]
    keys = list((sig.get("changed_terms") or {}).keys()) or list((sig.get("terms") or {}).keys())
    for n in sig["numbers"]:                 # 数值的上下文词也算
        for c in categories():
            if n.get("ctx") in c["keywords"] and c["key"] not in keys:
                keys.append(c["key"])
    ref = ch.get("new") or ch.get("old") or {}
    for k in find_terms(" ".join(ref.get("path") or [])):
        if k not in keys:
            keys.append(k)
    cats = [cat_by_key(k) for k in keys] or [fallback_category()]
    return sorted(cats, key=lambda c: -c["weight"])


def importance(ch, cats):
    s = imp()["signals"]
    RS = L("reasons")
    sig = ch["signals"]
    pts, reasons, fired = cats[0]["weight"], [RS["category"].format(name=cats[0]["name"], w=cats[0]["weight"])], []
    nums = [n for n in sig["numbers"] if n.get("old") or n.get("new")]
    if nums:
        pts += s["number"]
        items = "、".join("%s %s→%s" % (n["ctx"], n["old"] or "—", n["new"] or "—") for n in nums[:3])
        reasons.append(RS["number"].format(items=items, p=s["number"]))
        fired.append("number")
        if any(n["ratio"] >= s["number_big_ratio"] for n in nums):
            pts += s["number_big"]
            reasons.append(RS["number_big"].format(r=int(s["number_big_ratio"] * 100), p=s["number_big"]))
    if sig.get("obligation"):
        pts += s["obligation"]
        reasons.append(RS["obligation"].format(p=s["obligation"]))
        fired.append("obligation")
    if sig.get("negation"):
        pts += s["negation"]
        reasons.append(RS["negation"].format(p=s["negation"]))
        fired.append("negation")
    if sig.get("scope"):
        pts += s["scope"]
        reasons.append(RS["scope"].format(p=s["scope"]))
        fired.append("scope")
    if any(d.get("old") or d.get("new") for d in sig["dates"]):
        pts += s["date"]
        reasons.append(RS["date"].format(p=s["date"]))
        fired.append("date")
    has_terms = cats[0]["key"] != fallback_category()["key"]
    if (ch["type"] == "removed" or sig.get("removed_text")) and has_terms:
        pts += s["removed_term"]
        reasons.append(RS["removed_term"].format(p=s["removed_term"]))
        fired.append("removed_term")
    if (ch["type"] == "added" or sig.get("added_text")) and has_terms:
        pts += s["added_clause"]
        reasons.append(RS["added_clause"].format(p=s["added_clause"]))
        fired.append("added_clause")
    if ch.get("minor") or ch["type"] == "moved":
        cap = s["minor_cap"]
        if pts > cap:
            pts = cap
        reasons.append(RS["minor_cap"].format(p=cap))
    return min(pts, 100), reasons, fired


def impact(ch, cats, refs, eff):
    p = imp()["impact_points"]
    RS = L("reasons")
    pts, reasons = 0, []
    mine = [r for r in refs if r["change_id"] == ch["id"]]
    st = len({r["doc_id"] for r in mine if r["match"] == "stale"})
    rel = len({r["doc_id"] for r in mine if r["match"] == "related"})
    if st:
        v = min(st * p["stale_ref"], p["stale_cap"])
        pts += v
        reasons.append(RS["stale"].format(n=st, p=v))
    if rel:
        v = min(rel * p["related_ref"], p["related_cap"])
        pts += v
        reasons.append(RS["related"].format(n=rel, p=v))
    light = ch.get("minor") or ch["type"] == "moved"
    customer = (not light) and any(c.get("customer") for c in cats)
    system = (not light) and any(c.get("system") for c in cats) and \
        bool(ch["signals"]["numbers"] or ch["signals"]["dates"] or ch["signals"].get("obligation"))
    if customer:
        pts += p["customer"]
        reasons.append(RS["customer"].format(p=p["customer"]))
    if system:
        pts += p["system"]
        reasons.append(RS["system"].format(p=p["system"]))
    if eff and not light:
        days = (eff - today()).days
        for limit, add in sorted(p["urgent_days"]):
            if days <= limit:
                pts += add
                reasons.append(RS["urgent" if days >= 0 else "urgent_past"].format(d=abs(days), p=add))
                break
    return min(pts, 100), reasons, customer, system, st, rel


def apply_floors(level, fired, cats, reasons):
    """返回（初筛级别，触发的最高下限或 None）。下限是先验：模型判断可以低于它，但会列入待人工确认。"""
    keys = {c["key"] for c in cats}
    floor = None
    for f in imp().get("floors", []):
        if f["when"] in fired and keys & set(f["categories"]):
            floor = f["level"] if floor is None else more_severe(floor, f["level"])
            new = more_severe(level, f["level"])
            if new != level:
                reasons.append(L("reasons")["floor"].format(when=L("signal_names").get(f["when"], f["when"]), lv=level_name(f["level"])))
                level = new
    return level, floor


def actions_for(cats, level, eff):
    """处置建议：按类别取 playbook，生效日已知时换算成具体日期。"""
    pb = imp().get("playbook", {})
    out, seen = [], set()
    for c in cats[:R("action_categories_max")]:          # 只取最主要的几个类别，避免处置事项堆砌
        for action, owner, offset in pb.get(c["key"], pb.get(fallback_category()["key"], [])):
            if action in seen:
                continue
            seen.add(action)
            due = fmt_date(eff + dt.timedelta(days=offset)) if eff else ""
            out.append({"action": action, "owner": owner, "offset": offset, "due": due})
    return out


def score_all(data, refs, notes):
    meta = data["meta"]
    eff = parse_date(meta.get("effective_date")) if meta.get("effective_date") else None
    w = R("weights")
    ov = (notes or {}).get("overrides", {})
    for ch in data["changes"]:
        cats = _categories_of(ch)
        o = ov.get(ch["id"], {})
        if o.get("category"):
            c0 = cat_by_key(o["category"])
            cats = [c0] + [c for c in cats if c["key"] != c0["key"]]
        imp_s, r1, fired = importance(ch, cats)
        imp_m, r2, customer, system, st, rel = impact(ch, cats, refs, eff)
        total = round(imp_s * w["importance"] + imp_m * w["impact"], 1)
        level = level_of(total)
        r3 = []
        level, floor = apply_floors(level, fired, cats, r3)
        if ch.get("minor") or ch["type"] == "moved":
            level = level_order()[-1]
            floor = None
        auto_level = level
        if o.get("level"):
            level = o["level"]
        ch.update({"category": cats[0]["key"], "category_name": cats[0]["name"],
                   "categories": [c["key"] for c in cats], "objects": _objects(cats), "floor_level": floor,
                   "importance": imp_s, "impact": imp_m, "score": total,
                   "level": level, "level_auto": auto_level, "level_name": level_name(level),
                   "customer": customer, "system": system, "stale_refs": st, "related_refs": rel,
                   "reasons": {"importance": r1, "impact": r2, "floor": r3},
                   "actions": [dict(zip(("action", "owner", "offset"), a)) for a in o["actions"]] if o.get("actions")
                   else actions_for(cats, level, eff),
                   "comment": o.get("comment", ""), "override_reason": o.get("reason", ""),
                   "ignored": bool(o.get("ignore"))})
        if eff:
            for a in ch["actions"]:
                a["due"] = fmt_date(eff + dt.timedelta(days=a["offset"])) if a.get("offset") is not None else a.get("due", "")
    return summarize(data, refs, eff)


def _objects(cats):
    out = []
    for c in cats[:R("action_categories_max")]:          # 只取最主要的几个类别，避免处置事项堆砌
        for ob in c.get("objects", []):
            if ob not in out:
                out.append(ob)
    return out


def summarize(data, refs, eff):
    order = level_order()
    live = [c for c in data["changes"] if not c.get("ignored")]
    sub = [c for c in live if not c.get("minor")]
    by_level = {lv: sum(1 for c in sub if c["level"] == lv) for lv in order}
    by_cat = {}
    for c in sub:
        by_cat[c["category_name"]] = by_cat.get(c["category_name"], 0) + 1
    plan = {}
    for c in sorted(sub, key=lambda c: order.index(c["level"])):
        if c["level"] == order[-1]:
            continue
        for a in c["actions"]:
            k = (a["action"], a["owner"])
            p = plan.setdefault(k, {"action": a["action"], "owner": a["owner"], "offset": a.get("offset"),
                                    "due": a.get("due", ""), "changes": [], "level": c["level"]})
            p["changes"].append(c["id"])
            if a.get("offset") is not None and (p["offset"] is None or a["offset"] < p["offset"]):
                p["offset"], p["due"] = a["offset"], a.get("due", "")
            p["level"] = more_severe(p["level"], c["level"])
    plan = sorted(plan.values(), key=lambda p: (order.index(p["level"]), p["offset"] if p["offset"] is not None else 0))
    ref_docs = {(r["doc_id"], r["match"]) for r in refs if r["change_id"] in {c["id"] for c in sub}}
    return {"total": len(live), "substantive": len(sub), "minor": len(live) - len(sub),
            "ignored": len(data["changes"]) - len(live),
            "by_level": by_level, "by_category": by_cat,
            "customer": sum(1 for c in sub if c["customer"]), "system": sum(1 for c in sub if c["system"]),
            "stale_docs": len({d for d, m in ref_docs if m == "stale"}),
            "related_docs": len({d for d, m in ref_docs if m == "related"} - {d for d, m in ref_docs if m == "stale"}),
            "plan": plan, "effective_date": fmt_date(eff), "days_to_effective": (eff - today()).days if eff else None}


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：初筛评分，并入分析判断后定级")
    ap.add_argument("changes")
    ap.add_argument("--refs", help="find_refs.py 的输出")
    ap.add_argument("--judgments", help="模型的分析判断（见 reference/methods.md），先经 judgments.py 护栏检查")
    ap.add_argument("--notes", help="报告用的补充信息；其中的 overrides 为旧写法，仍然支持（judgments 优先）")
    ap.add_argument("-o", "--output", required=True)
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    data = load_json(a.changes)
    rf = load_json(a.refs) if a.refs else {"refs": [], "queries": [], "meta": {}}
    notes = load_json(a.notes) if a.notes else {}
    for k, o in (notes.get("overrides") or {}).items():
        if o.get("level") and o["level"] not in level_order():
            sys.exit("overrides.%s.level 只能是：%s" % (k, "、".join(level_order())))
        if (o.get("level") or o.get("ignore")) and not o.get("reason"):
            sys.exit("overrides.%s 调整了级别或忽略该条，必须写 reason（报告会保留人工调整痕迹）" % k)

    # 1. 自动初筛（只作参考，保留在每条变更的 prior 里）
    prior = copy.deepcopy(data)
    score_all(prior, rf["refs"], {})
    for c, p in zip(data["changes"], prior["changes"]):
        c["prior"] = {k: p[k] for k in ("level", "importance", "impact", "score", "category_name")}
        c["floor_level"] = p.get("floor_level")

    # 2. 并入分析判断（经护栏检查）
    J = judgments.load(a.judgments) if a.judgments else None
    overrides = dict(notes.get("overrides") or {})
    refs = rf["refs"]
    if J:
        rep = judgments.check(data, rf["refs"], J)
        if rep.errors:
            print("分析判断未通过护栏检查（%d 项必须修改）：" % len(rep.errors))
            for e in rep.errors:
                print("  - " + e)
            sys.exit(2)
        judgments.pre_apply(data["changes"], J)
        overrides.update(judgments.to_overrides(J))
        refs = judgments.scoring_refs(rf["refs"], J)
    summary = score_all(data, refs, {"overrides": overrides})
    if not J:
        rep = judgments.unjudged(data)
    judgments.attach(data, J, rep)
    eff = parse_date(data["meta"]["effective_date"]) if data["meta"].get("effective_date") else None
    summary = summarize(data, refs, eff)            # 判断改了类别名时重新汇总
    summary["human"] = len(rep.human)
    summary["confirmed"] = len(rep.confirmed)
    summary["judged"] = bool(J)
    data["human"] = rep.human
    data["confirmed"] = rep.confirmed
    data["check_warnings"] = rep.warnings
    data["verify_questions"] = (J or {}).get("verify_questions", [])
    data["refs"] = judgments.annotate_refs(rf["refs"], J, data["meta"])
    data["queries"] = rf.get("queries", [])
    data["meta"]["refs"] = rf.get("meta", {})
    data["meta"]["weights"] = R("weights")
    data["meta"]["levels"] = R("levels")
    if J and J.get("analyst"):
        data["meta"]["analyst"] = J["analyst"]
    data["summary"] = summary
    save_json(data, a.output)
    bl = summary["by_level"]
    print("实质变更 %d 项（措辞调整 %d 项，排除 %d 项）" % (summary["substantive"], summary["minor"], summary["ignored"]))
    print("级别：" + "，".join("%s %d" % (level_name(lv), bl[lv]) for lv in level_order()) +
          ("" if J else "（自动初筛，尚未做分析判断）"))
    print("知识库：过时 %d 篇、需复核 %d 篇；处置事项 %d 项" %
          (summary["stale_docs"], summary["related_docs"], len(summary["plan"])))
    if rep.human:
        print("待人工确认 %d 项：报告会标为初稿，确认后在 judgments.json 对应判断里写 confirmed_by 再重跑" % len(rep.human))
    print("已写入：%s" % a.output)


if __name__ == "__main__":
    main()
