#!/usr/bin/env python3
"""根据 JSON 内容生成 Word 文档。

用法:
    python build_docx.py content.json output.docx [--template template.docx] [--keep-template-body]

依赖: python-docx  (pip install python-docx)
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Cm
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-docx，请先执行: pip install python-docx")

CN_FONT = "微软雅黑"
CN_BODY_FONT = "宋体"
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def set_run_font(run, name, east_asia=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), east_asia or name)


def set_style_font(style, name, size=None, bold=None, color=None):
    style.font.name = name
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color:
        style.font.color.rgb = RGBColor.from_string(color)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)


def apply_default_styles(doc):
    """没有模板时使用的内置样式。"""
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(section, side, Cm(2.5))
    section.top_margin = section.bottom_margin = Cm(2.5)

    normal = doc.styles["Normal"]
    set_style_font(normal, CN_BODY_FONT, size=11)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    for level, size in ((1, 16), (2, 14), (3, 12)):
        style = doc.styles[f"Heading {level}"]
        set_style_font(style, CN_FONT, size=size, bold=True, color="1F3864")
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True


def clear_body(doc):
    """保留模板的样式、页眉页脚，清空正文内容。"""
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def add_rich_text(paragraph, text):
    """支持 **加粗** 的行内文本。"""
    pos = 0
    for m in BOLD_PATTERN.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def safe_style(doc, name, fallback="Normal"):
    try:
        doc.styles[name]
        return name
    except KeyError:
        return fallback


def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    for tag, attr in (("w:fldChar", "begin"), ("w:instrText", None), ("w:fldChar", "separate")):
        el = OxmlElement(tag)
        if attr:
            el.set(qn("w:fldCharType"), attr)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = 'TOC \\o "1-3" \\h \\z \\u'
        run._r.append(el)
    run.add_text("（目录：在 Word 中右键此处选择“更新域”或按 F9 显示）")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)
    p.add_run().add_break(WD_BREAK.PAGE)


def set_cell_shading(cell, hex_color):
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def add_table(doc, header, rows):
    cols = len(header) if header else max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=cols)
    table.style = safe_style(doc, "Table Grid", fallback=None) or table.style
    if header:
        cells = table.add_row().cells
        for i, h in enumerate(header):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(h))
            run.bold = True
            set_cell_shading(cells[i], "D9E2F3")
    for r in rows:
        cells = table.add_row().cells
        for i in range(cols):
            cells[i].text = ""
            add_rich_text(cells[i].paragraphs[0], str(r[i]) if i < len(r) else "")
    doc.add_paragraph()


def add_note(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    label = p.add_run("注：")
    label.bold = True
    label.font.color.rgb = RGBColor(0xC0, 0x50, 0x00)
    add_rich_text(p, text)


def build(spec, output, template=None, keep_template_body=False):
    if template:
        doc = Document(template)
        if not keep_template_body:
            clear_body(doc)
    else:
        doc = Document()
        apply_default_styles(doc)

    title = doc.add_paragraph(style=safe_style(doc, "Title"))
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run(spec.get("title", "未命名文档"))
    if not template:
        title_run.font.size = Pt(22)
        title_run.bold = True
        set_run_font(title_run, CN_FONT)

    if spec.get("subtitle"):
        sub = doc.add_paragraph(style=safe_style(doc, "Subtitle"))
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.add_run(spec["subtitle"])

    meta = spec.get("meta") or {}
    if meta:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("　|　".join(f"{k}：{v}" for k, v in meta.items())).font.size = Pt(9)

    if spec.get("toc"):
        add_toc(doc)

    for i, block in enumerate(spec.get("blocks", [])):
        kind = block.get("type")
        if kind == "heading":
            level = min(max(int(block.get("level", 1)), 1), 3)
            doc.add_heading(block["text"], level=level)
        elif kind == "paragraph":
            add_rich_text(doc.add_paragraph(), block["text"])
        elif kind in ("bullets", "numbered"):
            style = safe_style(doc, "List Bullet" if kind == "bullets" else "List Number")
            for item in block.get("items", []):
                add_rich_text(doc.add_paragraph(style=style), item)
        elif kind == "table":
            add_table(doc, block.get("header", []), block.get("rows", []))
        elif kind == "note":
            add_note(doc, block["text"])
        elif kind == "page_break":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        else:
            print(f"警告：第 {i + 1} 个 block 类型未知（{kind}），已跳过", file=sys.stderr)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    print(f"已生成：{output}")


def main():
    parser = argparse.ArgumentParser(description="根据 JSON 内容生成 Word 文档")
    parser.add_argument("content", help="内容 JSON 文件")
    parser.add_argument("output", help="输出 .docx 路径")
    parser.add_argument("--template", help="公司 Word 模板（.docx）")
    parser.add_argument("--keep-template-body", action="store_true",
                        help="保留模板原有正文（默认会清空，只保留样式和页眉页脚）")
    args = parser.parse_args()

    with open(args.content, encoding="utf-8") as f:
        spec = json.load(f)
    build(spec, args.output, args.template, args.keep_template_body)


if __name__ == "__main__":
    main()
