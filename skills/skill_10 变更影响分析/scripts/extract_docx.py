#!/usr/bin/env python3
"""按段落提取 Word 文档内容（含表格内的段落），输出带编号的 JSON，供检查和批注定位。

用法:
    python extract_docx.py input.docx > paras.json

输出:
    [{"para": 1, "style": "Heading 1", "in_table": false, "text": "..."}, ...]
    空段落不输出，但编号会跳过它们，保证和 annotate_docx.py 的编号一致。

依赖: python-docx  (pip install python-docx)
"""
import json
import sys

try:
    from docx import Document
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-docx，请先执行: pip install python-docx")


def iter_paragraphs(doc):
    """按文档顺序遍历正文段落和表格里的段落。annotate_docx.py 使用同一个函数。"""
    body = doc.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc), False
        elif tag == "tbl":
            table = Table(child, doc)
            seen = set()
            for row in table.rows:
                for cell in row.cells:
                    if id(cell._tc) in seen:  # 合并单元格只算一次
                        continue
                    seen.add(id(cell._tc))
                    for p in cell.paragraphs:
                        yield p, True


def extract(path):
    doc = Document(path)
    out = []
    for idx, (p, in_table) in enumerate(iter_paragraphs(doc), 1):
        text = p.text.strip()
        if not text:
            continue
        out.append({
            "para": idx,
            "style": p.style.name if p.style is not None else "",
            "in_table": in_table,
            "text": text,
        })
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2))
