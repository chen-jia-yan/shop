# -*- coding: utf-8 -*-
"""
知识生成 Word —— 渲染入口

用法：
  python render_docx.py <内容.json> <输出.docx> [--style classic|premium|minimal] [--no-toc]

内容 JSON 的结构见 reference/elements.md；完整示例见 examples/。
文档结构：封面（独立一节，无页眉页脚）→ 目录（可选）→ 正文（页码从 1 开始，“第 X 页 / 共 Y 页”）。

退出码：0 成功；2 内容 JSON 校验不通过（会逐条列出问题）。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import blocks_basic                                  # noqa: E402
import blocks_visual                                 # noqa: E402
from docx_helpers import (add_field, add_rich, add_tab_stop_right, cell_borders, cell_margins,  # noqa: E402
                          enable_update_fields, field_begin, field_end, mark_size, no_borders,
                          para_border, row_flags, section_page_start, set_run, shade, spacing,
                          strip_theme, table_layout)
from themes import BRAND, DEFAULT_STYLE_BY_TYPE, FONTS, SIZES, get_style  # noqa: E402

REGISTRY = dict(blocks_basic.REGISTRY)
REGISTRY.update(blocks_visual.REGISTRY)

REQUIRED = {
    "heading": ["text"], "paragraph": ["text"], "lead": ["text"], "bullets": ["items"],
    "numbered": ["items"], "callout": [], "quote": ["text"], "note": ["text"], "page_break": [],
    "table": ["columns", "rows"], "glossary": ["items"], "faq": ["items"], "checklist": ["items"],
    "signoff": [], "revisions": ["items"], "contact": ["items"], "kpi": ["items"],
    "flow": ["steps"], "timeline": ["nodes"], "structure": ["root", "children"],
    "matrix": ["quadrants"], "compare": ["cards"], "steps": ["items"],
    "chart": ["chart", "series"], "image": ["path"],
}

PAGE_W, PAGE_H = 21.0, 29.7
MARGIN_L = MARGIN_R = 2.3
TEXT_W = PAGE_W - MARGIN_L - MARGIN_R


class Ctx(object):
    def __init__(self, doc, style, numbering, tmp, base_dir):
        self.doc = doc
        self.style = style
        self.numbering = numbering
        self.tmp = tmp
        self.base_dir = base_dir
        self.text_width_cm = TEXT_W
        self.h = [0, 0, 0]
        self.headings = []
        self.captions = []
        self.counters = Counter()


# ---------------- 校验 ----------------
def validate(data):
    errs = []
    meta = data.get("meta")
    if not isinstance(meta, dict) or not meta.get("title"):
        errs.append("meta.title 缺失：封面和页眉都需要文档标题")
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errs.append("blocks 为空：没有正文内容")
        return errs
    for i, b in enumerate(blocks):
        t = b.get("type")
        if t not in REGISTRY:
            errs.append("第 %d 个元素：未知类型 %r（可用类型见 reference/elements.md）" % (i + 1, t))
            continue
        for f in REQUIRED[t]:
            if f not in b or b[f] in (None, "", []):
                errs.append("第 %d 个元素（%s）：缺少字段 %s" % (i + 1, t, f))
        if t == "table":
            n = len(b.get("columns", []))
            for ri, r in enumerate(b.get("rows", [])):
                if len(r) != n:
                    errs.append("第 %d 个元素（表格）第 %d 行有 %d 列，表头是 %d 列"
                                % (i + 1, ri + 1, len(r), n))
        if t == "chart":
            cats = b.get("categories", [])
            for s in b.get("series", []):
                if b.get("chart") not in ("donut", "pie") and len(s.get("values", [])) != len(cats):
                    errs.append("第 %d 个元素（图表 %s）：系列 %s 的数据个数与分类个数不一致"
                                % (i + 1, b.get("caption", ""), s.get("name", "")))
        if t == "kpi" and not 2 <= len(b.get("items", [])) <= 4:
            errs.append("第 %d 个元素（数据卡片）：建议 2-4 个，当前 %d 个"
                        % (i + 1, len(b.get("items", []))))
    return errs


# ---------------- 样式 ----------------
def setup_styles(doc, st):
    normal = doc.styles["Normal"]
    strip_theme(normal)
    normal.font.name = FONTS["en"]
    normal.font.size = Pt(SIZES["body"])
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", FONTS["cn"])
    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(6)
    pf.line_spacing = 1.4
    pf.widow_control = True
    spec = {1: (SIZES["h1"], 20, 10), 2: (SIZES["h2"], 14, 6), 3: (SIZES["h3"], 10, 4)}
    for lvl, (size, before, after) in spec.items():
        s = doc.styles["Heading %d" % lvl]
        rf = strip_theme(s)
        rf.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", FONTS["cn"])
        s.font.name = FONTS["en"]
        s.font.size = Pt(size)
        s.font.bold = True
        s.font.italic = False
        s.font.color.rgb = None
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True
        s.paragraph_format.line_spacing = 1.2


def page_setup(section, top=2.6, bottom=2.3, left=MARGIN_L, right=MARGIN_R):
    section.page_width = Cm(PAGE_W)
    section.page_height = Cm(PAGE_H)
    section.top_margin = Cm(top)
    section.bottom_margin = Cm(bottom)
    section.left_margin = Cm(left)
    section.right_margin = Cm(right)
    section.header_distance = Cm(1.2)
    section.footer_distance = Cm(1.1)


# ---------------- 封面 ----------------
def _meta_rows(meta):
    rows = []
    for k, label in (("department", "编制部门"), ("audience", "适用对象"), ("version", "版本"),
                     ("doc_no", "文档编号"), ("date", "发布日期")):
        if meta.get(k):
            rows.append((label, meta[k]))
    return rows


def _info_table(doc, rows, label_color, value_color, line_color, width=9.5, indent=None):
    if not rows:
        return
    t = doc.add_table(rows=len(rows), cols=2)
    table_layout(t, [2.6, width - 2.6], indent_twips=indent)
    no_borders(t)
    for r, (k, v) in zip(t.rows, rows):
        row_flags(r)
        for c in r.cells:
            cell_borders(c, bottom=("single", 4, line_color))
            cell_margins(c, 70, 70, 0, 80)
        set_run(r.cells[0].paragraphs[0].add_run(k), SIZES["small"], False, label_color)
        set_run(r.cells[1].paragraphs[0].add_run(str(v)), SIZES["body"], True, value_color)


def cover_band(doc, meta, st):
    """经典橙白：顶部满宽橙色色带 + 下方信息表。"""
    sec = doc.sections[0]
    page_setup(sec, top=0, bottom=1.5)
    t = doc.add_table(rows=1, cols=1)
    table_layout(t, [PAGE_W], indent_twips=-int(MARGIN_L * 567), total_twips=int(PAGE_W * 567))
    no_borders(t)
    r = t.rows[0]
    r.height = Cm(11.5)
    r.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    c = r.cells[0]
    shade(c, st["cover_bg"])
    cell_margins(c, 0, 0, int(MARGIN_L * 567), int(MARGIN_R * 567))
    c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    p = c.paragraphs[0]
    spacing(p, 52, 0)
    set_run(p.add_run(meta.get("brand", "富卫人寿")), 12, True, st["cover_fg"])
    set_run(p.add_run("　FWD"), 10, True, st["cover_accent"], "Arial")
    p = c.add_paragraph()
    spacing(p, 60, 4)
    set_run(p.add_run(meta.get("category", "")), 12, True, st["cover_accent"])
    p = c.add_paragraph()
    spacing(p, 0, 6, line=1.15)
    set_run(p.add_run(meta["title"]), SIZES["title"] + 2, True, st["cover_fg"])
    if meta.get("subtitle"):
        p = c.add_paragraph()
        set_run(p.add_run(meta["subtitle"]), SIZES["subtitle"], False, st["cover_fg"])
    p = c.add_paragraph()
    spacing(p, 10, 0)
    set_run(p.add_run("———"), 16, True, st["cover_accent"])
    p = doc.add_paragraph()
    spacing(p, 40, 0)
    _info_table(doc, _meta_rows(meta), BRAND["muted"], BRAND["ink"], BRAND["line"])
    _cover_footnote(doc, meta, 150)


def cover_full(doc, meta, st):
    """尊享深色：整版深绿 + 暖黄点缀。"""
    sec = doc.sections[0]
    page_setup(sec, top=0, bottom=0.6, left=0, right=0)
    t = doc.add_table(rows=1, cols=1)
    table_layout(t, [PAGE_W], total_twips=int(PAGE_W * 567))
    no_borders(t)
    r = t.rows[0]
    r.height = Cm(28.6)
    r.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    c = r.cells[0]
    shade(c, st["cover_bg"])
    cell_margins(c, 0, 0, 1700, 1700)
    p = c.paragraphs[0]
    spacing(p, 70, 0)
    set_run(p.add_run(meta.get("brand", "富卫人寿")), 12, True, st["cover_accent"])
    set_run(p.add_run("　FWD"), 10, True, BRAND["white"], "Arial")
    p = c.add_paragraph()
    spacing(p, 170, 6)
    set_run(p.add_run(meta.get("category", "")), 12, True, st["cover_accent"])
    p = c.add_paragraph()
    spacing(p, 0, 8, line=1.15)
    set_run(p.add_run(meta["title"]), SIZES["title"] + 4, True, BRAND["white"])
    if meta.get("subtitle"):
        p = c.add_paragraph()
        set_run(p.add_run(meta["subtitle"]), SIZES["subtitle"], False, "C9D6D1")
    p = c.add_paragraph()
    spacing(p, 14, 0)
    set_run(p.add_run("———"), 18, True, st["cover_accent"])
    p = c.add_paragraph()
    spacing(p, 210, 0)
    for k, v in _meta_rows(meta):
        q = c.add_paragraph()
        spacing(q, 0, 3)
        set_run(q.add_run(k + "　"), SIZES["small"], False, "9DB3AA")
        set_run(q.add_run(str(v)), SIZES["body"], True, BRAND["white"])
    if meta.get("confidentiality"):
        q = c.add_paragraph()
        spacing(q, 18, 0)
        set_run(q.add_run("密级：" + meta["confidentiality"]), SIZES["footer"], True,
                st["cover_accent"])


def cover_line(doc, meta, st):
    """简约白：白底 + 顶部橙色粗线，留白克制，适合制度与合规文件。"""
    page_setup(doc.sections[0])
    p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    para_border(p, "top", st["cover_accent"], sz=36, space=10)
    spacing(p, 0, 0)
    set_run(p.add_run(meta.get("brand", "富卫人寿")), 11, True, st["cover_accent"])
    set_run(p.add_run("　FWD"), 9, True, BRAND["muted"], "Arial")
    p = doc.add_paragraph()
    spacing(p, 150, 6)
    set_run(p.add_run(meta.get("category", "")), 11, True, BRAND["muted"])
    p = doc.add_paragraph()
    spacing(p, 0, 8, line=1.15)
    set_run(p.add_run(meta["title"]), SIZES["title"] + 2, True, BRAND["ink"])
    if meta.get("subtitle"):
        p = doc.add_paragraph()
        set_run(p.add_run(meta["subtitle"]), SIZES["subtitle"], False, BRAND["ink_soft"])
    p = doc.add_paragraph()
    spacing(p, 8, 0)
    set_run(p.add_run("———"), 16, True, st["cover_accent"])
    p = doc.add_paragraph()
    spacing(p, 150, 0)
    _info_table(doc, _meta_rows(meta), BRAND["muted"], BRAND["ink"], BRAND["line"])
    _cover_footnote(doc, meta, 30)


def _cover_footnote(doc, meta, before):
    if not meta.get("confidentiality") and not meta.get("cover_note"):
        return
    p = doc.add_paragraph()
    spacing(p, before, 0)
    if meta.get("confidentiality"):
        set_run(p.add_run("密级：%s" % meta["confidentiality"]), SIZES["footer"], True,
                BRAND["orange_dark"])
    if meta.get("cover_note"):
        set_run(p.add_run("　" + meta["cover_note"]), SIZES["footer"], False, BRAND["muted"])


# ---------------- 页眉页脚 ----------------
def header_footer(section, meta, st, numbered=True):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    add_tab_stop_right(hp, int(TEXT_W * 567))
    set_run(hp.add_run(meta.get("brand", "富卫人寿")), SIZES["footer"], True, BRAND["orange"])
    set_run(hp.add_run("　|　" + meta.get("short_title", meta["title"])), SIZES["footer"], False,
            st["header_text"])
    if meta.get("confidentiality"):
        set_run(hp.add_run("\t" + meta["confidentiality"]), SIZES["footer"], True, st["header_text"])
    para_border(hp, "bottom", BRAND["line"], sz=4, space=4)
    fp = section.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if numbered:
        set_run(fp.add_run("第 "), SIZES["footer"], False, BRAND["muted"])
        add_field(fp, "PAGE", "1", SIZES["footer"], BRAND["ink_soft"], True)
        set_run(fp.add_run(" 页 / 共 "), SIZES["footer"], False, BRAND["muted"])
        add_field(fp, "SECTIONPAGES", "1", SIZES["footer"], BRAND["ink_soft"], True)
        set_run(fp.add_run(" 页"), SIZES["footer"], False, BRAND["muted"])


def new_section(doc):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    # add_section 会把上一节的分节符放进一个新的空段落；把它压到最小，避免封面后多出空白页
    prev_break = doc.paragraphs[-1]
    mark_size(prev_break, 1)
    page_setup(sec)
    return sec


def toc(doc, ctx_headings, st):
    p = doc.add_paragraph()
    spacing(p, 0, 14)
    set_run(p.add_run("目　录"), SIZES["h1"], True, st["heading"])
    para_border(p, "bottom", st["rule"], sz=12, space=6)
    entries = [(lvl, txt) for lvl, txt in ctx_headings if lvl <= 2] or [(1, "（打开文档后右键 → 更新域）")]
    first = doc.add_paragraph()
    field_begin(first, 'TOC \\o "1-2" \\h \\z \\u')
    paras = [first] + [doc.add_paragraph() for _ in entries[1:]]
    for par, (lvl, txt) in zip(paras, entries):
        par.paragraph_format.left_indent = Cm(0 if lvl == 1 else 0.75)
        spacing(par, 4 if lvl == 1 else 0, 2)
        set_run(par.add_run(txt), SIZES["body"] if lvl == 1 else SIZES["small"] + 0.5,
                lvl == 1, BRAND["ink"] if lvl == 1 else BRAND["ink_soft"])
    field_end(paras[-1])
    tip = doc.add_paragraph()
    spacing(tip, 18, 0)
    set_run(tip.add_run("提示：如页码未显示，在目录上右键选择“更新域 → 更新整个目录”。"),
            SIZES["footer"], False, BRAND["muted"])


# ---------------- 主流程 ----------------
def collect_headings(blocks, numbering):
    """预先算出标题编号，供目录占位使用（与正文编号规则一致）。"""
    h = [0, 0, 0]
    out = []
    for b in blocks:
        if b.get("type") != "heading":
            continue
        lvl = int(b.get("level", 1))
        num = ""
        if numbering:
            h[lvl - 1] += 1
            for i in range(lvl, 3):
                h[i] = 0
            num = (blocks_basic.cn_number(h[0]) + "、") if lvl == 1 else \
                ("%d.%d　" % (h[0], h[1]) if lvl == 2 else "%d.%d.%d　" % tuple(h))
        out.append((lvl, num + b["text"]))
    return out


def render(data, out_path, style_name=None, want_toc=None, base_dir="."):
    meta = data["meta"]
    style_name = style_name or meta.get("style") or DEFAULT_STYLE_BY_TYPE.get(
        meta.get("doc_type"), "classic")
    st = get_style(style_name)
    numbering = meta.get("numbering", True)
    blocks = data["blocks"]
    n_h1 = sum(1 for b in blocks if b.get("type") == "heading" and int(b.get("level", 1)) == 1)
    if want_toc is None:
        want_toc = meta.get("toc", n_h1 >= 4)

    doc = Document()
    setup_styles(doc, st)
    {"band": cover_band, "full": cover_full, "line": cover_line}[st["cover"]](doc, meta, st)

    if want_toc:
        sec = new_section(doc)
        header_footer(sec, meta, st, numbered=False)
        toc(doc, collect_headings(blocks, numbering), st)

    sec = new_section(doc)
    header_footer(sec, meta, st, numbered=True)
    section_page_start(sec, 1)

    tmp = tempfile.mkdtemp(prefix="kb2word_")
    ctx = Ctx(doc, st, numbering, tmp, base_dir)
    try:
        for b in blocks:
            REGISTRY[b["type"]](ctx, b)
        if meta.get("end_note"):
            p = doc.add_paragraph()
            spacing(p, 18, 0)
            para_border(p, "top", BRAND["line"], 4, 6)
            add_rich(p, meta["end_note"], SIZES["footer"], BRAND["muted"])
        enable_update_fields(doc)
        core = doc.core_properties
        core.title = meta["title"]
        core.subject = meta.get("subtitle", "")
        core.author = meta.get("department", meta.get("brand", "富卫人寿"))
        core.keywords = ",".join(meta.get("tags", []))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        doc.save(out_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ctx, style_name


def count_placeholders(data):
    s = json.dumps(data, ensure_ascii=False)
    return s.count("【待补充"), s.count("【请确认")


def main():
    ap = argparse.ArgumentParser(description="知识生成 Word：把内容 JSON 渲染为富卫风格 .docx")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--style", choices=["classic", "premium", "minimal"])
    ap.add_argument("--no-toc", action="store_true")
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    errs = validate(data)
    if errs:
        print("内容校验未通过，共 %d 处：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    ctx, style_name = render(data, a.output, a.style, False if a.no_toc else None,
                             os.path.dirname(os.path.abspath(a.content)))
    todo, confirm = count_placeholders(data)
    print("已生成：%s" % a.output)
    print("风格：%s；一级标题 %d 个；表 %d 个；图 %d 个"
          % (style_name, sum(1 for l, _ in ctx.headings if l == 1), ctx.counters["tab"],
             ctx.counters["fig"]))
    if todo or confirm:
        print("待处理占位：【待补充】%d 处，【请确认】%d 处（文中已黄底高亮）" % (todo, confirm))


if __name__ == "__main__":
    main()
