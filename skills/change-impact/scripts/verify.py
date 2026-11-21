# -*- coding: utf-8 -*-
"""
变更影响分析 —— 处置后核验：知识库改完了没有、改对了没有。

用法：
  python verify.py scored.json --corpus 修订后的知识库导出.jsonl [--corpus 更多] [--qa 问答结果.json]
                   [--date YYYY-MM-DD] -o verify.json

三类核验（都是机械比对，判断不了的标“待核验”交给人或模型看）：
  1. 逐条销项   每篇判为过时的内容：建议稿是否已上线、原句是否已撤下；下线的是否已不在库里；
                生效日切换的，未到切换日记为“待核验”而不是失败
  2. 回归扫描   用同样的旧值探针重扫修订后的全库：有没有新冒出来的、含旧口径的内容
                （判为“对存量仍有效 / 新旧并列 / 加注说明”的内容含旧值是正常的，不算）
  3. 问答回测   judgments 里的 verify_questions 交给 qa_advance 再问一遍（结果存 JSON 后 --qa），
                答案里要出现 expect 中的新口径、不能出现 reject 中的旧口径
输出 verify.json，并可用 build_report.py --verify 把核验结果写进跟踪表。
"""
import argparse
import os
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import add_cli_args, configure       # noqa: E402

import find_refs                                # noqa: E402
from ci_common import L, R, bare, clip, load_json, parse_date, save_json, today   # noqa: E402

EXPECTED_OLD = ("valid_for_existing", "not_affected")
EXPECTED_OLD_DISP = ("parallel", "annotate", "keep")


def _present(text, sentence, th):
    """建议稿是否出现在内容里：去标点后整句包含，或与某一句高度相似。"""
    b = bare(sentence)
    if not b:
        return False
    t = bare(text)
    if b in t:
        return True
    for s in find_refs.SPLIT.split(text):
        if SequenceMatcher(None, bare(s), b, autojunk=False).ratio() >= th:
            return True
    return False


def check_refs(data, docs, on):
    th = R("verify")["proposed_sim"]
    by_doc = {}
    for r in data["refs"]:
        if r.get("disposal") or r.get("verdict"):
            by_doc.setdefault(r["doc_id"], r)
    out = []
    for did, r in by_doc.items():
        disp, verdict = r.get("disposal"), r.get("verdict")
        item = {"doc_id": did, "title": r["title"], "disposal": disp, "changes": sorted({x["change_id"] for x in data["refs"] if x["doc_id"] == did})}
        d = docs.get(did)
        if verdict == "not_affected" or disp == "keep":
            item.update(status="skip", note="判为不受影响 / 保持不变")
        elif disp == "retire":
            item.update(status="pass" if d is None else "fail", note="已下线" if d is None else "仍在库中")
        elif d is None:
            item.update(status="fail", note="修订后的语料里找不到这篇内容（被删了还是没导出？）")
        elif disp == "switch_on_date" and r.get("switch_date") and on < parse_date(r["switch_date"]):
            item.update(status="pending", note="未到切换日 %s" % r["switch_date"])
        else:
            revs = r.get("revisions") or []
            if not revs:
                item.update(status="pending", note="没有修订建议稿，需人工看是否已处理")
            else:
                done, changed, left = 0, 0, []
                for rv in revs:
                    has_new = _present(d["text"], rv.get("proposed", ""), th)
                    has_old = _present(d["text"], rv.get("original", ""), 0.98)
                    if has_new and (not has_old or disp in EXPECTED_OLD_DISP):
                        done += 1
                    elif not has_old:
                        changed += 1                # 原句已改，但不是按建议稿改的
                    else:
                        left.append(clip(rv.get("original", ""), 24))
                if left:
                    item.update(status="fail", note="原句仍在：" + "；".join(left))
                elif changed:
                    item.update(status="changed", note="%d 处已改但与建议稿不同" % changed)
                else:
                    item.update(status="pass", note="%d 处均已按建议稿更新" % done)
        out.append(item)
    return out


def regress(data, corpus_docs):
    """用比对时的旧值探针重扫全库，找新冒出来的含旧口径内容。"""
    known = {}
    for r in data["refs"]:
        known.setdefault(r["doc_id"], set()).add(r.get("verdict") or "")
        if r.get("disposal") in EXPECTED_OLD_DISP:
            known[r["doc_id"]].add("expected")
    found = []
    scope = data["meta"].get("refs", {}).get("scope_terms") or []
    for ch in data["changes"]:
        if ch.get("minor") or ch.get("ignored") or ch["type"] == "moved":
            continue
        hits, _ = find_refs.match(ch, corpus_docs, scope)
        for h in hits:
            if h["match"] != "stale":
                continue
            k = known.get(h["doc_id"], set())
            if "expected" in k or k & set(EXPECTED_OLD):
                continue
            status = "new" if h["doc_id"] not in known else "still"
            found.append({"doc_id": h["doc_id"], "title": h["title"], "change_id": ch["id"],
                          "evidence": h["evidence"], "kind": status})
    return found


def check_qa(data, qa):
    qs = data.get("verify_questions") or []
    answers = {}
    for rec in qa:
        q = bare(rec.get("question", ""))
        if q:
            answers[q] = " ".join(str(rec.get(k, "")) for k in ("answer", "content", "text") if rec.get(k))
    out = []
    for q in qs:
        a = answers.get(bare(q["question"]))
        item = {"change_id": q["change_id"], "question": q["question"]}
        if a is None:
            item.update(status="pending", note="没有这个问题的回测结果")
        else:
            ok = any(bare(x) in bare(a) for x in q.get("expect", []))
            bad = [x for x in q.get("reject", []) if bare(x) in bare(a)]
            item.update(answer=clip(a, 80), status="pass" if ok and not bad else "fail",
                        note=("仍含旧口径：" + "、".join(bad)) if bad else ("" if ok else "答案里没有新口径"))
        out.append(item)
    return out


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：处置后核验")
    ap.add_argument("scored")
    ap.add_argument("--corpus", action="append", default=[], help="修订后的知识库导出，可写多次")
    ap.add_argument("--qa", help="qa_advance 回测结果 JSON（数组或 {results: [...]}，每条含 question、answer）")
    ap.add_argument("--date", help="核验日期，默认今天（用于判断是否已到切换日）")
    ap.add_argument("-o", "--output", required=True)
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    data = load_json(a.scored)
    if "summary" not in data:
        sys.exit("请输入 score.py 的输出（scored.json）")
    on = parse_date(a.date) if a.date else today()
    corpus = find_refs.load_corpus(a.corpus) if a.corpus else []
    docs = {d["doc_id"]: d for d in corpus}
    refs = check_refs(data, docs, on) if corpus else []
    reg = regress(data, corpus) if corpus else []
    qa_items = []
    if a.qa:
        raw = load_json(a.qa)
        qa_items = check_qa(data, raw.get("results", []) if isinstance(raw, dict) else raw)
    items = refs + qa_items
    S = {k: sum(1 for x in items if x["status"] == k) for k in ("pass", "fail", "pending", "changed", "skip")}
    out = {"meta": {"date": on.strftime("%Y-%m-%d"), "corpus": a.corpus, "qa": a.qa, "docs": len(corpus)},
           "summary": dict(S, regressions=len(reg)), "refs": refs, "regressions": reg, "qa": qa_items}
    save_json(out, a.output)
    VS = L("verify_status")
    print(L("report.verify_line", n=len(items), p=S["pass"], f=S["fail"], w=S["pending"] + S["changed"], r=len(reg)))
    for x in items:
        if x["status"] in ("fail", "changed", "pending"):
            print("  - [%s] %s %s" % (VS[x["status"]], x.get("title") or x.get("question"), x.get("note", "")))
    for g in reg:
        print("  - [%s] %s（%s）：%s" % ("新发现" if g["kind"] == "new" else "仍含旧值", g["title"], g["change_id"], g["evidence"]))
    if not corpus and not a.qa:
        print("没有提供修订后的语料或问答结果：用 --corpus 和 / 或 --qa 再跑")
    print("已写入：%s" % a.output)
    sys.exit(1 if S["fail"] or reg else 0)


if __name__ == "__main__":
    main()
