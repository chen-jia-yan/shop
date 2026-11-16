#!/usr/bin/env python3
"""对比新旧两个版本的文件，按句子找出改动，标注所在章节、改动类型和数字变化。

用法:
    python compare_docs.py old.docx new.docx [--show-minor]
    python compare_docs.py old.txt new.txt

支持 .docx（需要 python-docx）、.txt、.md。
输出: JSON（打印到标准输出）
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

SENT_SPLIT = re.compile(r"(?<=[。！？；;])")
PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)
NUM_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:个)?(?:工作日|自然日|天|日|小时|周|个月|月|年|万元|元|%|％|人|次|份|页|家)?")
HEADING_TEXT = re.compile(r"^(第[一二三四五六七八九十百零\d]+[章节条]|[一二三四五六七八九十]+、|\d+(\.\d+)*[、.\s])")
ARTICLE = re.compile(r"^第[一二三四五六七八九十百零\d]+条")


# ---------- 读取 ----------

def read_docx(path):
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ModuleNotFoundError:
        sys.exit("读取 .docx 需要 python-docx：pip install python-docx")
    doc = Document(path)
    out = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            style = p.style.name if p.style is not None else ""
            out.append((p.text, style.startswith("Heading") or style.startswith("标题")))
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                seen, cells = set(), []
                for cell in row.cells:
                    if id(cell._tc) not in seen:
                        seen.add(id(cell._tc))
                        cells.append(cell.text.strip())
                out.append(("｜".join(cells) + "。", False))
    return out


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()
    return [(l, l.lstrip().startswith("#")) for l in lines]


def units(path):
    """返回 [(句子, 所在章节)]。"""
    raw = read_docx(path) if Path(path).suffix.lower() == ".docx" else read_text(path)
    heading, out = "（文档开头）", []
    for text, is_heading in raw:
        text = text.strip()
        if not text:
            continue
        if is_heading or (len(text) <= 30 and HEADING_TEXT.match(text) and not text.endswith("。")):
            heading = text.lstrip("# ").strip()   # 单独的标题行，只用作章节名
            continue
        art = ARTICLE.match(text)
        if art:                                   # "第五条 报销须……"：条款号作章节名，内容照常对比
            heading = art.group(0)
        for s in SENT_SPLIT.split(text):
            if s.strip():
                out.append((s.strip(), heading))
    return out


# ---------- 对比 ----------

def numbers(text):
    return [m.group(0).replace(" ", "") for m in NUM_UNIT.finditer(text) if m.group(0).strip()]


def classify(before, after):
    if before and after:
        if PUNCT.sub("", before) == PUNCT.sub("", after):
            return "格式标点"
        nb, na = numbers(before), numbers(after)
        sim = difflib.SequenceMatcher(None, before, after, autojunk=False).ratio()
        if nb == na and sim >= 0.85:
            return "措辞调整"
    return "实质变更"


def pair_block(old, new):
    """把一个改动块里的旧句和新句逐条配对。返回 [(旧句索引或 None, 新句索引或 None)]。"""
    if len(old) == len(new):
        return list(zip(range(len(old)), range(len(new))))
    pairs, used, j_start = [], set(), 0
    for i, s in enumerate(old):
        best, best_r = None, 0.5
        for j in range(j_start, len(new)):
            if j in used:
                continue
            r = difflib.SequenceMatcher(None, s, new[j], autojunk=False).ratio()
            if r > best_r:
                best, best_r = j, r
        if best is None:
            pairs.append((i, None))
        else:
            for j in range(j_start, best):      # 配对点之前没配上的新句视为新增
                if j not in used:
                    pairs.append((None, j))
                    used.add(j)
            pairs.append((i, best))
            used.add(best)
            j_start = best + 1
    pairs += [(None, j) for j in range(len(new)) if j not in used]
    return pairs


def compare(old_path, new_path, show_minor=False):
    a, b = units(old_path), units(new_path)
    sa, sb = [x[0] for x in a], [x[0] for x in b]
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    changes, hidden = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for pi, pj in pair_block(sa[i1:i2], sb[j1:j2]):
            before = sa[i1 + pi] if pi is not None else ""
            after = sb[j1 + pj] if pj is not None else ""
            section = b[j1 + pj][1] if pj is not None else a[i1 + pi][1]
            if before and after:
                kind = classify(before, after)
            else:
                kind = "删除" if before else "新增"
            if kind == "格式标点" and not show_minor:
                hidden += 1
                continue
            item = {"id": len(changes) + 1, "section": section, "type": kind,
                    "before": before or None, "after": after or None}
            nb, na = numbers(before), numbers(after)
            if before and after and nb != na:
                item["number_changes"] = {"before": nb, "after": na}
            changes.append(item)

    summary = {"old": str(old_path), "new": str(new_path),
               "old_sentences": len(sa), "new_sentences": len(sb),
               "similarity": round(sm.ratio(), 3),
               "counts": {}, "minor_hidden": hidden}
    for c in changes:
        summary["counts"][c["type"]] = summary["counts"].get(c["type"], 0) + 1
    if sm.ratio() < 0.3:
        summary["warning"] = "两个文件相似度很低，请确认是否是同一份文件的新旧版本"
    return {"summary": summary, "changes": changes}


def main():
    ap = argparse.ArgumentParser(description="对比新旧版本文件")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--show-minor", action="store_true", help="同时输出只改了格式和标点的地方")
    args = ap.parse_args()
    for p in (args.old, args.new):
        if Path(p).suffix.lower() not in (".docx", ".txt", ".md"):
            sys.exit(f"不支持的格式：{p}。请提供 .docx / .txt / .md")
    print(json.dumps(compare(args.old, args.new, args.show_minor), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
