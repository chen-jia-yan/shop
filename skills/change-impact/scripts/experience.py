# -*- coding: utf-8 -*-
"""
变更影响分析 —— 经验库：把确认过的判断沉淀成判例，下次遇到相似变更时先拿出来参考。

为什么用判例而不是补规则：规则写不全、会写错、要不停维护；判例记录的是“当时什么情况、判成什么、为什么”，
模型读到后能类比迁移，遇到新情况也不会因为“规则没写”而漏判。判例只作参考，不自动套用。

边界：
  - 只有写了 --confirmed-by（业务或合规负责人）的判例才是 active，才会被 find 拿出来参考；
    没确认的记为 pending，默认不参与（防止模型自己的判断不经确认就变成“经验”）
  - 判例过时或有误时用 retire 停用（保留记录、写原因），不直接删除
  - 文件是纯文本 jsonl（默认 change-impact/experience/cases.jsonl，路径见 rules.json 的 impact.experience），
    可以人工审阅、增删，也可以整体迁到知识库或知识图谱里

用法：
  python experience.py find scored.json -o precedents.json      # 为每条实质变更找相似判例
  python experience.py add  scored.json --judgments judgments.json --confirmed-by 张三
                                                               # 把判断里写了 lesson 的条目沉淀为判例
  python experience.py retire EXP-0003 --reason "2027 年起监管口径调整，不再适用"
  python experience.py list [--all]
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _tap import add_cli_args, configure      # noqa: E402

from ci_common import R, clip, find_terms, load_json, save_json   # noqa: E402


def path():
    p = R("experience")["file"]
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(HERE, "..", p))


def read_all():
    p = path()
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def write_all(cases):
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def _features(ch):
    """一条变更的特征：涉及的术语、类别名、信号类型。"""
    terms = set()
    for kws in (ch["signals"].get("changed_terms") or ch["signals"].get("terms") or {}).values():
        terms.update(kws)
    for n in ch["signals"]["numbers"]:
        if n.get("ctx"):
            terms.add(n["ctx"])
    sig = set()
    s = ch["signals"]
    for k, v in (("number", s["numbers"]), ("date", s["dates"]), ("obligation", s.get("obligation")),
                 ("negation", s.get("negation")), ("scope", s.get("scope")),
                 ("removed", ch["type"] == "removed" or s.get("removed_text")),
                 ("added", ch["type"] == "added" or s.get("added_text"))):
        if v:
            sig.add(k)
    return terms, ch.get("category_name") or "", sig


def _score(case, terms, cat, sig):
    s = 3 * len(terms & set(case.get("terms") or []))
    s += 2 if cat and cat == case.get("category") else 0
    s += len(sig & set(case.get("signals") or []))
    return s


def find(data, include_pending=False):
    cf = R("experience")
    cases = [c for c in read_all() if c.get("status") == "active" or (include_pending and c.get("status") == "pending")]
    general = [c for c in cases if c.get("kind") == "method"][:cf["general_max"]]
    out = {}
    for ch in data["changes"]:
        if ch.get("minor") or ch.get("ignored"):
            continue
        terms, cat, sig = _features(ch)
        ranked = sorted(((_score(c, terms, cat, sig), c) for c in cases if c.get("kind") != "method"),
                        key=lambda x: -x[0])
        hits = [dict(c, match_score=s) for s, c in ranked if s >= cf["min_score"]][:cf["top"]]
        if hits:
            out[ch["id"]] = hits
    return {"general": general, "by_change": out, "file": path(), "total_active": sum(1 for c in cases if c.get("status") == "active")}


def add(data, J, confirmed_by, source=None):
    """把 judgments 里写了 lesson 的条目沉淀为判例。没有 confirmed_by 时记为 pending。"""
    cases = read_all()
    n = max([int(c["id"].split("-")[1]) for c in cases if c.get("id", "").startswith("EXP-")] + [0])
    by_id = {c["id"]: c for c in data["changes"]}
    src = source or "%s %s→%s" % (data["meta"]["doc"], data["meta"]["old"]["label"], data["meta"]["new"]["label"])
    today = dt.date.today().strftime("%Y-%m-%d")
    status = "active" if confirmed_by else "pending"
    new = []
    for cid, j in J.get("changes", {}).items():
        if not j.get("lesson") or cid not in by_id:
            continue
        ch = by_id[cid]
        terms, cat, sig = _features(ch)
        new.append({"kind": "change", "change": ch.get("judged_summary") or ch["desc"], "category": cat,
                    "terms": sorted(terms), "signals": sorted(sig),
                    "judgment": {k: j.get(k) for k in ("level", "verdict", "direction", "applies") if j.get(k)},
                    "lesson": j["lesson"]})
    for did, j in J.get("refs", {}).items():
        if not j.get("lesson"):
            continue
        cids = j.get("changes") or []
        terms = set()
        for cid in cids:
            if cid in by_id:
                terms |= _features(by_id[cid])[0]
        title = next((r["title"] for r in data.get("refs", []) if r["doc_id"] == did), did)
        new.append({"kind": "ref", "change": "；".join(clip(by_id[c]["desc"], 30) for c in cids if c in by_id),
                    "content": title, "category": "", "terms": sorted(terms), "signals": [],
                    "judgment": {k: j.get(k) for k in ("verdict", "disposal", "applies") if j.get(k)},
                    "lesson": j["lesson"]})
    for lesson in J.get("lessons", []):          # 不针对某一条的通用经验（方法层面）
        new.append({"kind": "method", "change": "", "category": "", "terms": find_terms_list(lesson),
                    "signals": [], "judgment": {}, "lesson": lesson})
    for c in new:
        n += 1
        c.update({"id": "EXP-%04d" % n, "date": today, "source": src, "status": status,
                  "confirmed_by": confirmed_by or ""})
    write_all(cases + new)
    return new


def find_terms_list(text):
    return sorted({kw for kws in find_terms(text).values() for kw in kws})


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：经验库（判例）")
    ap.add_argument("cmd", choices=["find", "add", "retire", "list"])
    ap.add_argument("target", nargs="?", help="find / add：scored.json 或 changes.json；retire：判例编号")
    ap.add_argument("-o", "--output")
    ap.add_argument("--judgments")
    ap.add_argument("--confirmed-by", help="确认人（业务或合规负责人）；不写则判例为 pending，不参与参考")
    ap.add_argument("--source", help="来源说明，默认“文档名 旧版→新版”")
    ap.add_argument("--reason")
    ap.add_argument("--include-pending", action="store_true")
    ap.add_argument("--all", action="store_true")
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    if a.cmd == "find":
        res = find(load_json(a.target), a.include_pending)
        if a.output:
            save_json(res, a.output)
        print("经验库：%s（有效判例 %d 条）" % (res["file"], res["total_active"]))
        print("找到相似判例的变更 %d 条；通用经验 %d 条" % (len(res["by_change"]), len(res["general"])))
        for cid, hits in res["by_change"].items():
            print("  %s ← %s" % (cid, "、".join("%s（%s）" % (h["id"], clip(h["lesson"], 20)) for h in hits)))
    elif a.cmd == "add":
        if not a.judgments:
            sys.exit("add 需要 --judgments")
        new = add(load_json(a.target), load_json(a.judgments), a.confirmed_by, a.source)
        print("新增判例 %d 条（%s）" % (len(new), "已确认，参与后续参考" if a.confirmed_by else "未确认，记为 pending"))
        for c in new:
            print("  %s %s" % (c["id"], clip(c["lesson"], 40)))
    elif a.cmd == "retire":
        if not a.reason:
            sys.exit("retire 需要 --reason（写明为什么停用）")
        cases = read_all()
        hit = [c for c in cases if c["id"] == a.target]
        if not hit:
            sys.exit("没有判例 %s" % a.target)
        hit[0].update({"status": "retired", "retired_reason": a.reason,
                       "retired_date": dt.date.today().strftime("%Y-%m-%d")})
        write_all(cases)
        print("已停用 %s：%s" % (a.target, a.reason))
    else:
        for c in read_all():
            if a.all or c.get("status") == "active":
                print("%s [%s] %s｜%s" % (c["id"], c.get("status"), clip(c.get("change") or c.get("content") or "通用", 24),
                                         clip(c["lesson"], 50)))


if __name__ == "__main__":
    main()
