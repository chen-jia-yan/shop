# -*- coding: utf-8 -*-
"""
变更影响分析 —— 分析判断（judgments.json）：护栏检查、并入评分结果。

分工：
  脚本  比对、找候选、初筛评分、核对、渲染 —— 确定性的、可复现的工作
  模型  按 reference/methods.md 读原文，对每条变更、每篇候选内容作出判断，写进 judgments.json
  人    确认“待人工确认”清单里的事项（在对应判断里写 confirmed_by）

这里只做**通用护栏**检查（参数在 tap-config/impact.json 的 guardrails），不校验业务规则：
  1. 有依据   每条判断都要写 reasoning；定级、过时结论要有 evidence，引文必须能在原文里找到（防编造）
  2. 不编事实 修订稿里出现的数字、日期，必须在新旧条款或该内容原文里出现过；修订稿不得含合规禁用表述
  3. 不越权   不能出现改生效日期、版本、发布状态、写回知识库之类的字段
  4. 要人确认 P0 / P1、比初筛低 2 级以上、低于先验下限、低置信、新类别、排除实质变更、
              下线 / 新旧并列处置、无法判断的内容 —— 不拦截，列入“待人工确认”，确认前报告标为初稿
  5. 不遗漏   初筛为 P0 / P1 的变更必须逐条判断；其余没判断的沿用初筛并提示
errors 必须修改（score.py 拒绝运行）；warnings 和待人工确认写进报告。

用法（写完 judgments.json 后先自查，再交给 score.py）：
  python judgments.py check changes.json --refs refs.json --judgments judgments.json
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import add_cli_args, configure      # noqa: E402

import signals                                 # noqa: E402
import tapcheck                                # noqa: E402
from ci_common import (L, bare, categories, clip, fallback_category, imp, level_name, level_order,  # noqa: E402
                       load_json)


def G():
    return imp()["guardrails"]


def load(path):
    J = load_json(path)
    for k, v in (("changes", {}), ("refs", {}), ("verify_questions", [])):
        J.setdefault(k, v)
    return J


def find_category(name):
    """类别可写 key 或中文名；找不到返回 None，视为配置之外的新类别（允许，但要人确认）。"""
    for c in categories() + [fallback_category()]:
        if name in (c["key"], c["name"]):
            return c
    return None


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            for x in _keys(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _keys(v):
                yield x


def _quotes(ev):
    for e in ev or []:
        yield e.get("quote", "") if isinstance(e, dict) else str(e)


def _found(q, pool):
    b = bare(q)
    return len(b) >= G()["quote_min_chars"] and any(b in s for s in pool)


def _facts(*texts):
    nums, dates = set(), set()
    for t in texts:
        for n in signals.numbers(t or ""):
            nums.add((n["value"], n["unit"]))
        dates.update(signals.dates(t or ""))
    return nums, dates


def _new_facts(proposed, allowed):
    nums, dates = allowed
    bad = [n["raw"] for n in signals.numbers(proposed) if (n["value"], n["unit"]) not in nums]
    bad += [d for d in signals.dates(proposed) if d not in dates]
    return bad


def _step(a, b):
    """b 比 a 轻几级（正数为更轻）。"""
    o = level_order()
    return o.index(b) - o.index(a)


class Report(object):
    def __init__(self):
        self.errors, self.warnings, self.human, self.confirmed = [], [], [], []

    def err(self, where, msg):
        self.errors.append("%s：%s" % (where, msg))

    def warn(self, where, msg):
        self.warnings.append("%s：%s" % (where, msg))

    def ask(self, target, item, why, j):
        rec = {"target": target, "item": item, "why": why}
        if j and j.get("confirmed_by"):
            rec["by"] = j["confirmed_by"]
            self.confirmed.append(rec)
        else:
            self.human.append(rec)


def _enum(rep, where, j, field, allowed):
    v = j.get(field)
    if v is not None and v not in allowed:
        rep.err(where, "%s 只能是 %s，当前为 %r" % (field, " / ".join(allowed), v))


def check(data, refs, J):
    """data：changes.json（已带初筛结果 prior / floor_level 时检查更完整）；refs：find_refs 的候选。"""
    rep = Report()
    I, H, W = imp(), G()["human_review"], L("human_why")
    by_id = {c["id"]: c for c in data["changes"]}
    texts = data.get("texts") or {}
    full = [bare(texts.get("old", "")), bare(texts.get("new", ""))]
    for k in _keys(J):
        if k in G()["forbidden_keys"]:
            rep.err("judgments.json", "出现了超出分析权限的字段 %r：本 skill 只分析、不改文档元数据、不写回知识库" % k)

    # ---------- 变更 ----------
    for cid, j in J["changes"].items():
        where = "changes.%s" % cid
        ch = by_id.get(cid)
        if ch is None:
            rep.err(where, "changes.json 里没有这条变更")
            continue
        for f, key in (("verdict", "change_verdicts"), ("direction", "directions"), ("applies", "applies"),
                       ("confidence", "confidence")):
            _enum(rep, where, j, f, I[key])
        _enum(rep, where, j, "level", level_order())
        if not j.get("reasoning"):
            rep.err(where, "缺少 reasoning：每条判断都要写清依据（为什么是这个结论）")
        verdict = j.get("verdict", "substantive")
        pool = [bare((ch.get("old") or {}).get("text", "")), bare((ch.get("new") or {}).get("text", ""))] + full
        quotes = list(_quotes(j.get("evidence")))
        if verdict == "substantive" and j.get("level") and not quotes:
            rep.err(where, "定级缺少 evidence：至少引一句修订前或修订后的原文")
        for q in quotes:
            if not _found(q, pool):
                rep.err(where, "引文在原文中找不到：“%s”" % clip(q, 30))
        if verdict == "merged":
            if j.get("merge_into") not in by_id or j.get("merge_into") == cid:
                rep.err(where, "merged 需要 merge_into 指向另一条变更编号")
        name = ch.get("category_name") or ""
        if j.get("category") and not find_category(j["category"]):
            name = j["category"]
            if H.get("new_category"):
                rep.ask(cid, ch.get("desc", ""), W["new_category"].format(name=name), j)
        prior = (ch.get("prior") or {}).get("level")
        lv = j.get("level") or prior
        if verdict == "substantive" and lv:
            if lv in H.get("levels", []):
                rep.ask(cid, ch.get("desc", ""), W["level"].format(lv=level_name(lv)), j)
            if prior and _step(prior, lv) >= H.get("downgrade_steps", 99):
                rep.ask(cid, ch.get("desc", ""), W["downgrade"].format(prior=level_name(prior), n=_step(prior, lv)), j)
            fl = ch.get("floor_level")
            if H.get("below_floor") and fl and _step(fl, lv) > 0:
                rep.ask(cid, ch.get("desc", ""), W["below_floor"].format(floor=level_name(fl)), j)
            if not j.get("applies") and lv != level_order()[-1]:
                rep.warn(where, "没有写 applies（对新投保、存量保单还是都适用），处置方式可能判断不准")
        if H.get("ignore_substantive") and verdict in ("wording", "ignore", "merged") and not ch.get("minor"):
            rep.ask(cid, ch.get("desc", ""), W["ignore_substantive"].format(v=L("change_verdicts")[verdict]), j)
        if H.get("low_confidence") and j.get("confidence") == "low":
            rep.ask(cid, ch.get("desc", ""), W["low_confidence"], j)
        for a in j.get("actions") or []:
            if isinstance(a, dict) and not (a.get("action") and a.get("owner")):
                rep.err(where, "actions 每项需要 action 和 owner")
    for c in data["changes"]:
        if c.get("minor") or c["id"] in J["changes"]:
            continue
        pl = (c.get("prior") or {}).get("level")
        if pl in H.get("levels", []):
            rep.err("changes.%s" % c["id"], "初筛为“%s”的变更必须读原文逐条判断：%s" % (level_name(pl), clip(c.get("desc", ""), 30)))
        else:
            rep.warn("changes.%s" % c["id"], "没有判断，沿用初筛结果")

    # ---------- 受影响内容 ----------
    docs = {}
    for r in refs:
        docs.setdefault(r["doc_id"], {"text": r.get("doc_text") or r.get("evidence", ""), "title": r["title"],
                                      "changes": set()})["changes"].add(r["change_id"])
    old_new = texts.get("old", "") + "\n" + texts.get("new", "")
    for did, j in J["refs"].items():
        where = "refs.%s" % did
        d = docs.get(did)
        if d is None:
            rep.err(where, "不在候选内容里：请把这篇内容的检索结果加入 --corpus 重跑 find_refs.py，再写判断")
            continue
        for f, key in (("verdict", "ref_verdicts"), ("disposal", "disposals"), ("applies", "applies"),
                       ("confidence", "confidence")):
            _enum(rep, where, j, f, I[key])
        if not j.get("reasoning"):
            rep.err(where, "缺少 reasoning")
        for cid in j.get("changes") or []:
            if cid not in d["changes"]:
                rep.warn(where, "关联变更 %s 不在这篇内容的候选匹配里，请确认" % cid)
        pool = [bare(d["text"])]
        for q in _quotes(j.get("evidence")):
            if not _found(q, pool):
                rep.err(where, "引文在该内容中找不到：“%s”" % clip(q, 30))
        disp = j.get("disposal")
        revs = j.get("revisions") or []
        if disp in ("replace", "parallel", "switch_on_date", "annotate") and not revs:
            rep.warn(where, "处置为“%s”但没有修订建议稿" % L("disposals")[disp])
        allowed = _facts(old_new, d["text"])
        for k, rv in enumerate(revs, 1):
            if not _found(rv.get("original", ""), pool):
                rep.err(where, "第 %d 条修订的 original 在该内容中找不到（要逐字摘原句）" % k)
            if disp not in ("retire", "keep") and not rv.get("proposed"):
                rep.err(where, "第 %d 条修订缺少 proposed" % k)
            p = rv.get("proposed", "")
            if G().get("fact_check_revisions"):
                bad = _new_facts(p, allowed)
                if bad:
                    rep.err(where, "第 %d 条修订稿出现了新旧条款和原内容里都没有的数值 / 日期：%s" % (k, "、".join(bad)))
            if G().get("compliance_check_revisions"):
                for cat, word, _, why in tapcheck.banned_hits(p):
                    rep.err(where, "第 %d 条修订稿含合规禁用表述“%s”（%s）" % (k, word, cat))
        if disp in H.get("disposals", []):
            rep.ask(did, d["title"], W["disposal"].format(d=L("disposals")[disp]), j)
        if j.get("verdict") == "needs_review":
            rep.ask(did, d["title"], W["ref_needs_review"], j)
        if H.get("low_confidence") and j.get("confidence") == "low":
            rep.ask(did, d["title"], W["low_confidence"], j)
        if disp == "switch_on_date" and not (j.get("switch_date") or data["meta"].get("effective_date")):
            rep.ask(did, d["title"], W["no_switch_date"], j)
    stale_docs = {r["doc_id"]: r["title"] for r in refs if r["match"] == "stale"}
    for did, title in stale_docs.items():
        if did not in J["refs"]:
            rep.ask(did, title, W["unjudged_ref"], None)

    # ---------- 核验问题 ----------
    for k, q in enumerate(J.get("verify_questions") or [], 1):
        if q.get("change_id") not in by_id or not q.get("question") or not q.get("expect"):
            rep.err("verify_questions[%d]" % k, "需要 change_id（已有编号）、question 和 expect（答案里应出现的新口径）")
    return rep


def unjudged(data):
    """没有分析判断时：初筛 P0 / P1 全部列入待人工确认，报告标为初稿。"""
    rep = Report()
    for c in data["changes"]:
        if not c.get("minor") and c.get("level") in G()["human_review"].get("levels", []):
            rep.ask(c["id"], c.get("desc", ""), L("human_why")["level"].format(lv=level_name(c["level"])), None)
    return rep


# ---------------- 并入评分 ----------------
def pre_apply(changes, J):
    """评分前：按判断修正“是否措辞调整”（模型可以把初筛的措辞调整认定为实质变更，反之亦然）。"""
    for c in changes:
        j = J["changes"].get(c["id"])
        if not j or "verdict" not in j:
            continue
        c["minor"] = j["verdict"] == "wording"


def to_overrides(J):
    ov = {}
    for cid, j in J["changes"].items():
        o = {"reason": j.get("reasoning", ""), "comment": j.get("comment", "")}
        if j.get("level"):
            o["level"] = j["level"]
        c = find_category(j["category"]) if j.get("category") else None
        if c:
            o["category"] = c["key"]
        if j.get("verdict") in ("ignore", "merged"):
            o["ignore"] = True
        if j.get("actions"):
            o["actions"] = [[a["action"], a["owner"], a.get("offset")] if isinstance(a, dict) else list(a)
                            for a in j["actions"]]
        ov[cid] = o
    return ov


_MATCH = {"outdated": "stale", "partly": "stale", "valid_for_existing": "related", "needs_review": "related"}


def scoring_refs(refs, J):
    """评分用的候选：判为“不受影响 / 保持不变”的去掉，其余按判断改写匹配强度。"""
    out = []
    for r in refs:
        j = (J or {}).get("refs", {}).get(r["doc_id"])
        if j and j.get("changes") and r["change_id"] not in j["changes"]:
            j = None
        if not j:
            out.append(r)
            continue
        if j.get("verdict") == "not_affected" or j.get("disposal") == "keep":
            continue
        rr = dict(r)
        rr["match"] = _MATCH.get(j.get("verdict"), r["match"])
        out.append(rr)
    return out


def annotate_refs(refs, J, meta):
    out = []
    for r in refs:
        rr = dict(r)
        j = (J or {}).get("refs", {}).get(r["doc_id"])
        if j and (not j.get("changes") or r["change_id"] in j["changes"]):
            rr.update({"verdict": j.get("verdict"), "disposal": j.get("disposal"), "applies": j.get("applies"),
                       "switch_date": j.get("switch_date") or (meta.get("effective_date") if j.get("disposal") == "switch_on_date" else ""),
                       "revisions": j.get("revisions") or [], "ref_reason": j.get("reasoning", ""),
                       "confidence": j.get("confidence"), "confirmed_by": j.get("confirmed_by", "")})
        rr.pop("doc_text", None)                 # 全文不进报告数据，避免体积过大
        out.append(rr)
    return out


def attach(data, J, rep):
    human = {}
    for h in rep.human:
        human.setdefault(h["target"], []).append(h["why"])
    for c in data["changes"]:
        c["human"] = human.get(c["id"], [])
        j = (J or {}).get("changes", {}).get(c["id"])
        if not j:
            c["judged"] = False
            continue
        c.update({"judged": True, "verdict": j.get("verdict", "substantive"), "direction": j.get("direction"),
                  "applies": j.get("applies"), "judged_summary": j.get("summary", ""),
                  "reasoning": j.get("reasoning", ""), "evidence": list(_quotes(j.get("evidence"))),
                  "confidence": j.get("confidence"), "diff_review": j.get("diff_review", ""),
                  "precedents": j.get("precedents") or [], "merge_into": j.get("merge_into"),
                  "confirmed_by": j.get("confirmed_by", "")})
        if j.get("category") and not find_category(j["category"]):
            c["category_name"], c["new_category"] = j["category"], True
        if j.get("objects"):
            c["objects"] = j["objects"]


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：检查分析判断（judgments.json）是否越界、是否有依据")
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("changes", help="changes.json 或 scored.json（带初筛结果时检查更完整）")
    ap.add_argument("--refs")
    ap.add_argument("--judgments", required=True)
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    data = copy.deepcopy(load_json(a.changes))
    if "summary" in data:                      # scored.json：把初筛结果放回 prior
        for c in data["changes"]:
            c.setdefault("prior", {"level": c.get("level_auto") or c.get("level")})
    refs = load_json(a.refs)["refs"] if a.refs else data.get("refs", [])
    rep = check(data, refs, load(a.judgments))
    for title, items in (("必须修改", rep.errors), ("提示", rep.warnings)):
        if items:
            print("%s %d 项：" % (title, len(items)))
            for x in items:
                print("  - " + x)
    if rep.human:
        print("待人工确认 %d 项（不拦截，会列入报告；确认后在对应判断里写 confirmed_by）：" % len(rep.human))
        for h in rep.human:
            print("  - %s %s：%s" % (h["target"], clip(h["item"], 24), h["why"]))
    if rep.confirmed:
        print("已人工确认 %d 项" % len(rep.confirmed))
    if not rep.errors:
        print("检查通过：可以运行 score.py --judgments")
    sys.exit(2 if rep.errors else 0)


if __name__ == "__main__":
    main()
