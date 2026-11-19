# -*- coding: utf-8 -*-
"""
知识生成 Word —— 交付前质检

用法：
  python review_docx.py <文档.docx> --doc-type product [--final] [--out 质检报告.md] [--config 额外配置]

检查五类问题（分“必须修改 / 建议修改”两级）：
  1. 合规用语：词表见 tap-config/compliance.json 的 banned（对客文档类型见 customer_facing_types）
  2. 必备要素：按文档类型检查，见 compliance.json 的 required
  3. 结构：标题层级跳级、空章节、超长段落、缺少图表（阈值见 rules.json 的 rules.word.review）
  4. 占位符：数量（--final 时视为必须修改）
  5. 内容体检：套话、话题式标题、内容单薄、缺数字、重复表述（规则见 rules.word.content，列为建议修改）

退出码：0 通过；1 存在“必须修改”项。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, configure                    # noqa: E402
import tapcheck                                      # noqa: E402

from docx import Document                            # noqa: E402
from docx.text.paragraph import Paragraph            # noqa: E402

import content_check                                 # noqa: E402


def iter_text(doc):
    for p in doc.paragraphs:
        yield p.style.name if p.style is not None else "", p.text
    for t in doc.tables:
        for row in t.rows:
            seen = set()
            for c in row.cells:
                if id(c._tc) in seen:
                    continue
                seen.add(id(c._tc))
                for p in c.paragraphs:
                    yield "Table", p.text


def review(path, doc_type, final=False):
    doc = Document(path)
    rv = CONF.rule("review")
    must, should, info = [], [], []
    texts = list(iter_text(doc))
    full = "\n".join(t for _, t in texts)

    # 1. 合规用语
    strict = tapcheck.is_customer_facing(doc_type)
    for _, t in texts:
        for cat, word, snippet, why in tapcheck.banned_hits(t):
            (must if strict else should).append("【%s】“%s”：…%s…（%s）" % (cat, word, snippet, why))

    # 2. 必备要素
    for name in tapcheck.required_missing(doc_type, full):
        must.append("缺少必备要素：%s" % name)

    # 3. 结构
    levels = []
    for p in doc.paragraphs:
        n = p.style.name if p.style is not None else ""
        if n.startswith("Heading "):
            try:
                levels.append((int(n.split()[-1]), p.text.strip()))
            except ValueError:
                pass
    if not levels:
        must.append("没有任何标题：读者无法快速定位内容")
    prev = 0
    for lvl, txt in levels:
        if lvl > prev + 1:
            should.append("标题跳级：“%s”是 %d 级标题，但前面没有 %d 级标题" % (txt, lvl, lvl - 1))
        prev = lvl
    body = [(p.style.name if p.style is not None else "", p.text.strip()) for p in doc.paragraphs]
    for i, (s, t) in enumerate(body):
        if not s.startswith("Heading "):
            continue
        lvl = int(s.split()[-1]) if s.split()[-1].isdigit() else 9
        j = i + 1
        while j < len(body) and not body[j][1] and not body[j][0].startswith("Heading "):
            j += 1
        if j < len(body) and body[j][0].startswith("Heading "):
            nxt = int(body[j][0].split()[-1]) if body[j][0].split()[-1].isdigit() else 9
            if nxt <= lvl and not _has_table_between(doc, i, j):
                should.append("可能是空章节：“%s”下面没有内容" % t)
    for s, t in body:
        if not s.startswith("Heading ") and len(t) > rv["long_paragraph"]:
            should.append("段落过长（%d 字）：“%s…”，建议拆分或改为要点/表格" % (len(t), t[:24]))
    n_img = len(doc.inline_shapes)
    n_tab = len(doc.tables)
    n_h1 = sum(1 for l, _ in levels if l == 1)
    if doc_type not in rv["no_chart_types"] and n_h1 >= 3 and n_img + max(n_tab - 2, 0) < max(1, n_h1 // 2):
        should.append("图表偏少：%d 个一级章节只有 %d 张图、%d 个表格（含封面信息表），"
                      "数字和流程建议用图表呈现" % (n_h1, n_img, n_tab))

    # 4. 占位符
    todo, confirm = CONF.count_placeholders(full)
    if todo or confirm:
        msg = "仍有占位：待补充 %d 处、请确认 %d 处" % (todo, confirm)
        (must if final else info).append(msg)

    # 5. 内容体检（套话、话题式标题、内容单薄、缺数字、重复表述）
    hints, total = content_check.check(body_sequence(doc), doc_type, lead=False)
    should.extend("内容体检：" + h for h in hints)
    if total > len(hints):
        should.append("内容体检：另有 %d 项未列出，见渲染时的构建输出" % (total - len(hints)))

    info.append("统计：一级标题 %d，标题总数 %d，图片 %d，表格 %d，正文约 %d 字"
                % (n_h1, len(levels), n_img, n_tab, len(re.sub(r"\s", "", full))))
    return must, should, info


def body_sequence(doc):
    """按正文顺序给出 [(kind, text)]，从第一个一级标题开始（跳过封面和目录）；表格、图片记为 visual。"""
    seq, started = [], False
    body = doc.element.body
    for node in body.iterchildren():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "p":
            par = Paragraph(node, doc)
            name = par.style.name if par.style is not None else ""
            text = par.text.strip()
            if name.startswith("Heading "):
                lvl = name.split()[-1]
                lvl = int(lvl) if lvl.isdigit() else 3
                started = started or lvl == 1
                if started:
                    seq.append(("h%d" % min(lvl, 3), text))
            elif started:
                if node.findall(".//" + _DRAWING):
                    seq.append(("visual:image", text))
                elif text:
                    seq.append(("p", text))
        elif tag == "tbl" and started:
            seq.append(("visual:table", " ".join(t.text for t in node.iter(_T) if t.text)))
    return seq


_DRAWING = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"


def _has_table_between(doc, i, j):
    """判断两个段落之间是否夹着表格（表格不在 doc.paragraphs 中）。"""
    paras = [p._p for p in doc.paragraphs]
    node = paras[i].getnext()
    while node is not None and node is not paras[j]:
        if node.tag.endswith("}tbl"):
            return True
        node = node.getnext()
    return False


def main():
    ap = argparse.ArgumentParser(description="知识生成 Word 质检")
    ap.add_argument("docx")
    ap.add_argument("--doc-type", required=True, help="文档类型，可选值见 compliance.json 的 required")
    ap.add_argument("--final", action="store_true", help="正式交付：占位符也视为必须修改")
    ap.add_argument("--out")
    ap.add_argument("--config", action="append", default=[])
    a = ap.parse_args()
    configure("word", a)
    if a.doc_type not in tapcheck.required_types():
        sys.exit("未知文档类型 %s，可选：%s" % (a.doc_type, "、".join(tapcheck.required_types())))
    must, should, info = review(a.docx, a.doc_type, a.final)
    md = tapcheck.report_md(a.docx, must, should, info, head=[CONF.label("report.doc_type", t=a.doc_type), ""])
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.exit(1 if must else 0)


if __name__ == "__main__":
    main()
