# -*- coding: utf-8 -*-
"""
变更影响分析 —— 第 2 步：查找受影响的知识库内容

用法：
  python find_refs.py changes.json --corpus 知识库导出 [--corpus 更多] -o refs.json
                      [--scope-term 产品名或制度名 ...] [--exclude 文档ID或标题 ...]

--corpus 可以是：
  - .jsonl / .json：每条 {"doc_id","title","type","owner","url","updated","text"}；
    TAP 检索或 qa_advance 的结果也可以直接用（字段 snippet / content / answer 视同 text，question 计入标题）
  - .csv：同名列
  - 目录：其中的 .md / .txt / .docx / .json 逐个读取（文件名作标题）

判定规则（每条变更 × 每篇内容，取最强的一种）：
  stale   疑似过时：同一句里同时出现“上下文词 + 旧值”（如“等待期”+“90 天”），且没有出现新值；
          或出现了被删除的原文短语（≥ 6 个字）
  related 相关：同一句里出现该变更涉及的上下文词 / 术语；给了 --scope-term 时还要求同一篇提到它
不论有没有语料，都会为每条实质变更生成检索语句（queries），供在 TAP Retrieval / qa_advance 中补查。

这里的匹配只是“找候选”：命中的每篇内容连同全文（doc_text）交给模型，由模型判断是否真的过时、
对存量客户是否仍然有效、该怎么处置（见 reference/methods.md 第 2 节）。语料记录里的 via 字段
（如 keyword / vector / graph）会原样保留，便于说明候选是从哪条检索路径来的。
"""
import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import add_cli_args, configure     # noqa: E402

import extract                                # noqa: E402
from ci_common import R, bare, clip, load_json, norm, save_json   # noqa: E402

SPLIT = re.compile(r"[。；;！!？?\n]+")
TEXT_KEYS = ("text", "content", "snippet", "answer", "body")


def _doc(rec, i, src):
    text = " ".join(str(rec.get(k, "")) for k in TEXT_KEYS if rec.get(k))
    title = rec.get("title") or rec.get("question") or rec.get("name") or "%s#%d" % (os.path.basename(src), i)
    if rec.get("question") and rec.get("title"):
        text = rec["question"] + " " + text
    return {"doc_id": str(rec.get("doc_id") or rec.get("id") or title), "title": title,
            "type": rec.get("type") or rec.get("doc_type") or "", "owner": rec.get("owner") or "",
            "url": rec.get("url") or "", "updated": rec.get("updated") or rec.get("update_time") or "",
            "via": rec.get("via") or rec.get("source_type") or "",
            "text": norm(text)}


def load_corpus(paths):
    docs = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() in (".md", ".txt", ".docx", ".json", ".markdown"):
                        fp = os.path.join(root, fn)
                        try:
                            d = extract.load(fp)
                        except SystemExit as e:
                            print("跳过 %s：%s" % (fp, e))
                            continue
                        docs.append({"doc_id": fn, "title": os.path.splitext(fn)[0], "type": "", "owner": "",
                                     "url": fp, "updated": "", "via": "", "text": "\n".join(b["text"] for b in d["blocks"])})
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext == ".jsonl":
            with open(p, encoding="utf-8-sig") as f:
                for i, ln in enumerate(f):
                    if ln.strip():
                        docs.append(_doc(json.loads(ln), i, p))
        elif ext == ".json":
            data = load_json(p)
            items = (data.get("results") or data.get("docs") or data.get("items")) if isinstance(data, dict) else data
            for i, rec in enumerate(items or []):
                docs.append(_doc(rec, i, p))
        elif ext == ".csv":
            with open(p, encoding="utf-8-sig") as f:
                for i, rec in enumerate(csv.DictReader(f)):
                    docs.append(_doc(rec, i, p))
        else:
            raise SystemExit("不支持的语料格式：%s" % p)
    return docs


def _variants(raw):
    """“90天”也要能匹配“90 天”“九十天”以外的常见写法：数字与单位之间允许空格。"""
    m = re.match(r"^([\d.,]+)(.*)$", raw or "")
    if not m:
        return [raw] if raw else []
    return [raw, m.group(1) + " " + m.group(2)]


def _has(sentence, value):
    """数值整体匹配：“3次”不会误中“13次”。"""
    return bool(value) and re.search(r"(?<![\d.])" + re.escape(value), sentence) is not None


def probes(ch):
    """为一处变更生成“过时值探针”和“相关词探针”。"""
    sig = ch["signals"]
    stale, terms = [], []
    for n in sig["numbers"]:
        if n.get("old"):
            stale.append({"ctx": n["ctx"], "values": _variants(n["old"]),
                          "new": _variants(n["new"]) if n.get("new") else []})
        if n.get("ctx"):
            terms.append(n["ctx"])
    for d in sig["dates"]:
        if d.get("old"):
            stale.append({"ctx": None, "values": [d["old"]], "new": [d["new"]] if d.get("new") else []})
    phrases = []
    if ch["type"] in ("removed", "modified", "moved_modified"):
        for op, t in ch["segments"]:
            b = bare(t)
            if op == "del" and len(b) >= 6:
                phrases.append(norm(t).strip("，。；、 "))
    for kws in (sig.get("changed_terms") or sig.get("terms") or {}).values():
        terms += kws
    seen, uniq = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return stale, phrases, uniq


def queries_for(ch, stale, phrases, terms, scope_terms):
    q = []
    prefix = (" ".join(scope_terms) + " ") if scope_terms else ""
    for s in stale:
        if s["ctx"]:
            q.append({"change_id": ch["id"], "purpose": "stale", "query": prefix + "%s %s" % (s["ctx"], s["values"][0])})
    for p in phrases[:2]:
        q.append({"change_id": ch["id"], "purpose": "stale", "query": prefix + clip(p, 30)})
    if terms:
        q.append({"change_id": ch["id"], "purpose": "related", "query": prefix + " ".join(terms[:3])})
    return q


def match(ch, docs, scope_terms):
    stale, phrases, terms = probes(ch)
    out = []
    for d in docs:
        if scope_terms and not any(s in d["text"] for s in scope_terms):
            continue
        best = None
        for sent in SPLIT.split(d["text"]):
            s = sent.strip()
            if not s:
                continue
            hit = None
            for p in stale:
                if any(_has(s, v) for v in p["values"]) and (p["ctx"] is None or p["ctx"] in s) \
                        and not any(_has(s, v) for v in p["new"]):
                    hit = ("stale", 1.0, s)
                    break
            if not hit:
                for ph in phrases:
                    if ph and ph in s:
                        hit = ("stale", 0.9, s)
                        break
            if not hit and terms:
                k = sum(1 for t in terms if t in s)
                if k:
                    hit = ("related", min(0.5 + 0.1 * (k - 1), 0.8), s)
            if hit and (best is None or hit[1] > best[1]):
                best = hit
            if best and best[1] >= 1.0:
                break
        if best and best[1] >= R("min_ref_score"):
            out.append({"change_id": ch["id"], "doc_id": d["doc_id"], "title": d["title"], "type": d["type"],
                        "owner": d["owner"], "url": d["url"], "updated": d["updated"],
                        "match": best[0], "score": round(best[1], 2), "evidence": clip(best[2], 90),
                        "sentence": best[2], "via": d.get("via", ""), "doc_text": d["text"]})
    return out, queries_for(ch, stale, phrases, terms, scope_terms)


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：查找受影响的知识库内容")
    ap.add_argument("changes")
    ap.add_argument("--corpus", action="append", default=[], help="知识库导出 / 检索结果 / 文档目录，可写多次")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--scope-term", action="append", default=[], help="限定范围的词（如产品名），可写多次")
    ap.add_argument("--exclude", action="append", default=[], help="排除的文档 ID 或标题（通常是被修订的文档本身）")
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    data = load_json(a.changes)
    docs = load_corpus(a.corpus) if a.corpus else []
    ex = set(a.exclude)
    docs = [d for d in docs if d["doc_id"] not in ex and d["title"] not in ex]
    refs, queries = [], []
    for ch in data["changes"]:
        if ch.get("minor") or ch["type"] == "moved":
            continue
        r, q = match(ch, docs, a.scope_term)
        refs += r
        queries += q
    out = {"meta": {"corpus": a.corpus, "docs_scanned": len(docs), "scope_terms": a.scope_term},
           "refs": refs, "queries": queries}
    save_json(out, a.output)
    n_st = sum(1 for r in refs if r["match"] == "stale")
    print("扫描内容 %d 篇；疑似过时 %d 处、相关 %d 处；生成检索语句 %d 条" %
          (len(docs), n_st, len(refs) - n_st, len(queries)))
    if not docs:
        print("未提供语料：请用 refs.json 中的 queries 在 TAP 检索 / qa_advance 中补查，把结果存成 JSON 后用 --corpus 再跑一次")
    print("已写入：%s" % a.output)


if __name__ == "__main__":
    main()
