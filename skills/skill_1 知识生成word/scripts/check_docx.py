#!/usr/bin/env python3
"""检查生成的 Word 文档：结构、占位符、空章节。

用法:
    python check_docx.py output.docx
退出码: 0 = 通过；1 = 有需要处理的问题
"""
import json
import re
import sys

try:
    from docx import Document
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-docx，请先执行: pip install python-docx")

PLACEHOLDER = re.compile(r"【待补充[^】]*】")
SUSPICIOUS = re.compile(r"TODO|XXX|lorem ipsum|\{\{.*?\}\}", re.IGNORECASE)


def check(path):
    doc = Document(path)
    headings, placeholders, suspicious, empty_sections = [], [], [], []
    chars = 0
    last_heading, content_since_heading = None, 0

    for p in doc.paragraphs:
        text = p.text.strip()
        style = p.style.name if p.style is not None else ""
        if style.startswith("Heading") or style.startswith("标题"):
            if last_heading is not None and content_since_heading == 0:
                empty_sections.append(last_heading)
            last_heading, content_since_heading = text, 0
            headings.append({"level": style, "text": text})
            continue
        if text:
            content_since_heading += 1
            chars += len(text)
            placeholders += PLACEHOLDER.findall(text)
            suspicious += SUSPICIOUS.findall(text)

    # 表格里的内容也算作章节内容
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                chars += len(cell.text)
                placeholders += PLACEHOLDER.findall(cell.text)

    # 表格紧跟标题时，段落计数为 0，但章节并不空，这里只做提示
    report = {
        "file": path,
        "headings": headings,
        "chars": chars,
        "tables": len(doc.tables),
        "placeholders": placeholders,
        "suspicious_text": suspicious,
        "possibly_empty_sections": empty_sections + (
            [last_heading] if last_heading and content_since_heading == 0 else []),
    }
    report["passed"] = not (suspicious or report["possibly_empty_sections"]) and bool(headings)
    return report


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result = check(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["placeholders"]:
        print(f"\n提示：有 {len(result['placeholders'])} 处【待补充】，交付时需告知用户。")
    if not result["headings"]:
        print("问题：文档没有任何标题，结构可能有误。")
    if result["possibly_empty_sections"]:
        print("提示：以下章节没有正文段落（如果下面是表格可忽略）："
              + "、".join(result["possibly_empty_sections"]))
    sys.exit(0 if result["passed"] else 1)
