# -*- coding: utf-8 -*-
"""
知识生成 Word —— 渲染入口

用法：
  python render_docx.py <内容.json> <输出.docx> [--style 风格名] [--font-preset modern|formal] [--no-toc]
                        [--config 额外配置] [--font-cn 字体] [--font-en 字体] [--font-num 字体]
                        [--font-mode first|installed] [--font-scale 1.1]

品牌、配色、字体、风格、页面尺寸、固定文字都来自 tap-config/（见该目录 README.md），本脚本不写死。
内容 JSON 的结构见 reference/elements.md；完整示例见 examples/。
文档结构：封面（独立一节，无页眉页脚）→ 目录（可选）→ 正文（页码从 1 开始）。
渲染后打印“内容体检”：套话、话题式标题、内容单薄、缺数字、结论不先行、重复表述（规则见 rules.word.content）。

退出码：0 成功；2 内容 JSON 校验不通过（会逐条列出问题）。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, add_cli_args, configure       # noqa: E402

from docx import Document                            # noqa: E402
from docx.enum.section import WD_SECTION             # noqa: E402
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH        # noqa: E402
from docx.shared import Cm, Pt                       # noqa: E402

import blocks_basic                                  # noqa: E402
import blocks_visual                                 # noqa: E402
import charts                                        # noqa: E402
import content_check                                 # noqa: E402
from docx_helpers import (add_field, add_rich, add_tab_stop_right, cell_borders, cell_margins,  # noqa: E402
                          enable_update_fields, field_begin, field_end, mark_size,
                          no_borders, para_border, row_flags, section_page_start, set_run, shade,
                          spacing, strip_theme, table_layout)
from themes import BRAND, FONTS, SIZES, G, L, R, default_style, font_preset_for, get_style  # noqa: E402

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
    "facts": ["items"], "exec_summary": ["conclusion", "findings"], "progress": ["items"],
}
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Page(object):
    """页面尺寸（cm），来自 rules.word.page。"""
    def __init__(self):
        p = R("page")
        self.w, self.h = p["width_cm"], p["height_cm"]
        self.ml, self.mr = p["margin_left_cm"], p["margin_right_cm"]
        self.mt, self.mb = p["margin_top_cm"], p["margin_bottom_cm"]
        self.hd, self.fd = p["header_cm"], p["footer_cm"]
        self.text_w = self.w - self.ml - self.mr


class Ctx(object):
    def __init__(self, doc, style, numbering, tmp, base_dir, page, indent=False, h1_new_page=False):
        self.doc = doc
        self.style = style
        self.numbering = numbering
        self.tmp = tmp
        self.base_dir = base_dir
        self.page = page
        self.text_width_cm = page.text_w
        self.indent = indent
        self.h1_new_page = h1_new_page
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
    lo, hi = R("kpi_range")
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
            if b.get("widths") and len(b["widths"]) != n:
                errs.append("第 %d 个元素（表格）：widths 有 %d 项，表头是 %d 列" % (i + 1, len(b["widths"]), n))
        if t == "chart":
            cats = b.get("categories", [])
            for s in b.get("series", []):
                if b.get("chart") not in ("donut", "pie") and len(s.get("values", [])) != len(cats):
                    errs.append("第 %d 个元素（图表 %s）：系列 %s 的数据个数与分类个数不一致"
                                % (i + 1, b.get("caption", ""), s.get("name", "")))
        if t == "kpi" and not lo <= len(b.get("items", [])) <= hi:
            errs.append("第 %d 个元素（数据卡片）：建议 %d-%d 个，当前 %d 个"
                        % (i + 1, lo, hi, len(b.get("items", []))))
        if t == "facts":
            for j, it in enumerate(b.get("items", [])):
                if not isinstance(it, dict) or not it.get("label") or it.get("value") in (None, ""):
                    errs.append("第 %d 个元素（要素表）第 %d 项：需要 label 和 value" % (i + 1, j + 1))
        if t == "progress":
            if len(b.get("items", [])) > R("progress_max"):
                errs.append("第 %d 个元素（进度条）：最多 %d 项，当前 %d 项；更多项改用表格或图表"
                            % (i + 1, R("progress_max"), len(b["items"])))
            for j, it in enumerate(b.get("items", [])):
                if blocks_visual._num(it.get("value")) is None:
                    errs.append("第 %d 个元素（进度条）第 %d 项：value 必须是数字（可带 %%），当前 %r"
                                % (i + 1, j + 1, it.get("value")))
    return errs


# ---------------- 样式 ----------------
def setup_styles(doc, st):
    normal = doc.styles["Normal"]
    strip_theme(normal)
    normal.font.name = FONTS["en"]
    normal.font.size = Pt(CONF.size(SIZES["body"]))
    normal.font.color.rgb = None
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(W_NS + "eastAsia", FONTS["cn"])
    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(R("para_after"))
    pf.line_spacing = R("line_spacing")
    pf.widow_control = True
    hs = R("heading_spacing")
    for lvl in (1, 2, 3):
        before, after = hs[str(lvl)]
        s = doc.styles["Heading %d" % lvl]
        rf = strip_theme(s)
        rf.set(W_NS + "eastAsia", FONTS["head"])
        s.font.name = FONTS["en"]
        s.font.size = Pt(CONF.size(SIZES["h%d" % lvl]))
        s.font.bold = True
        s.font.italic = False
        s.font.color.rgb = None
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True
        s.paragraph_format.line_spacing = 1.25


def page_setup(section, pg, top=None, bottom=None, left=None, right=None):
    section.page_width = Cm(pg.w)
    section.page_height = Cm(pg.h)
    section.top_margin = Cm(pg.mt if top is None else top)
    section.bottom_margin = Cm(pg.mb if bottom is None else bottom)
    section.left_margin = Cm(pg.ml if left is None else left)
    section.right_margin = Cm(pg.mr if right is None else right)
    section.header_distance = Cm(pg.hd)
    section.footer_distance = Cm(pg.fd)


# ---------------- 封面 ----------------
def _meta_rows(meta):
    return [(label, meta[k]) for k, label in L("meta_rows") if meta.get(k)]


def _brand_line(p, meta, st, size):
    set_run(p.add_run(CONF.org_name(meta)), size, True, st["cover_brand"], cn=FONTS["head"])
    if CONF.org_short():
        set_run(p.add_run("　" + CONF.org_short()), size - 2, True, st["cover_short"], FONTS["num"])


def _title_block(cell_or_doc, meta, st, title_size, cat_before, cat_size=11):
    """类别标签 + 大标题 + 副标题 + 短线，各种封面共用。"""
    p = cell_or_doc.add_paragraph()
    spacing(p, cat_before, 6)
    if meta.get("category"):
        set_run(p.add_run(G("section_mark") + " "), cat_size, True, st["cover_accent"])
        set_run(p.add_run(meta["category"]), cat_size, True, st["cover_category"], cn=FONTS["head"])
    p = cell_or_doc.add_paragraph()
    spacing(p, 0, 8, line=1.2)
    set_run(p.add_run(meta["title"]), title_size, True, st["cover_title"], cn=FONTS["head"])
    if meta.get("subtitle"):
        p = cell_or_doc.add_paragraph()
        spacing(p, 0, 0, line=1.3)
        set_run(p.add_run(meta["subtitle"]), SIZES["subtitle"], False, st["cover_sub"])
    p = cell_or_doc.add_paragraph()
    spacing(p, 14, 0)
    set_run(p.add_run(G("rule")), 14, True, st["cover_accent"])


def _info_table(doc, rows, st, width=10.0, indent=None):
    if not rows:
        return
    t = doc.add_table(rows=len(rows), cols=2)
    table_layout(t, [2.6, width - 2.6], indent_twips=indent)
    no_borders(t)
    for i, (r, (k, v)) in enumerate(zip(t.rows, rows)):
        row_flags(r)
        for c in r.cells:
            cell_borders(c, bottom=("single", 4, st["cover_line"]))
            if i == 0:
                cell_borders(c, top=("single", 4, st["cover_line"]))
            cell_margins(c, 80, 80, 0, 80)
        set_run(r.cells[0].paragraphs[0].add_run(k), SIZES["small"], False, st["cover_label"])
        set_run(r.cells[1].paragraphs[0].add_run(str(v)), SIZES["body"], True, st["cover_value"])


def _full_width_table(doc, pg, rows):
    t = doc.add_table(rows=rows, cols=1)
    table_layout(t, [pg.w], indent_twips=-int(pg.ml * 567), total_twips=int(pg.w * 567))
    no_borders(t)
    return t


def cover_band(doc, meta, st, pg):
    """色块封面：顶部满宽色块（可带一条主色细条），下方信息表。蓝色系用浅色块，橙色系用实色块。"""
    page_setup(doc.sections[0], pg, top=0, bottom=1.5)
    top = st.get("cover_top")
    t = _full_width_table(doc, pg, 2 if top else 1)
    if top:
        r0 = t.rows[0]
        r0.height = Cm(0.32)
        r0.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        shade(r0.cells[0], top)
        mark_size(r0.cells[0].paragraphs[0], 1)
    r = t.rows[-1]
    r.height = Cm(pg.h * st.get("cover_ratio", 0.40))
    r.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    c = r.cells[0]
    shade(c, st["cover_bg"])
    cell_margins(c, 0, 0, int(pg.ml * 567), int(pg.mr * 567))
    c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    p = c.paragraphs[0]
    spacing(p, 46, 0)
    _brand_line(p, meta, st, 12)
    _title_block(c, meta, st, SIZES["title"] + 2, 64)
    p = doc.add_paragraph()
    spacing(p, 44, 0)
    _info_table(doc, _meta_rows(meta), st)
    _cover_footnote(doc, meta, st, 140)


def cover_side(doc, meta, st, pg):
    """侧条封面：白底，左侧一深一浅两条竖色带，大量留白；淡雅风格默认。"""
    page_setup(doc.sections[0], pg, top=0, bottom=0.6, left=0, right=0)
    side, side2 = 0.9, 0.28
    t = doc.add_table(rows=1, cols=3)
    table_layout(t, [side, side2, pg.w - side - side2], total_twips=int(pg.w * 567))
    no_borders(t)
    r = t.rows[0]
    r.height = Cm(pg.h - 1.1)
    r.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    shade(r.cells[0], st.get("cover_side") or st["accent"])
    shade(r.cells[1], st.get("cover_side2") or st["accent_light"])
    for cc in r.cells[:2]:
        mark_size(cc.paragraphs[0], 1)
    c = r.cells[2]
    if st["cover_bg"] != BRAND["white"]:
        shade(c, st["cover_bg"])
    cell_margins(c, 0, 0, int((pg.ml + 0.4) * 567), int(pg.mr * 567))
    p = c.paragraphs[0]
    spacing(p, 64, 0)
    _brand_line(p, meta, st, 12)
    _title_block(c, meta, st, SIZES["title"] + 2, 190)
    p = c.add_paragraph()
    spacing(p, 150, 0)
    rows = _meta_rows(meta)
    for i, (k, v) in enumerate(rows):
        q = c.add_paragraph()
        spacing(q, 0, 0, line=1.0)
        q.paragraph_format.right_indent = Cm(pg.w * 0.35)
        if i == 0:
            para_border(q, "top", st["cover_line"], sz=4, space=5)
        para_border(q, "bottom", st["cover_line"], sz=4, space=5)
        add_tab_stop_right(q, int(2.6 * 567))
        set_run(q.add_run(k), SIZES["small"], False, st["cover_label"])
        set_run(q.add_run("\t"), SIZES["small"])
        set_run(q.add_run("　" + str(v)), SIZES["body"], True, st["cover_value"])
    _cover_footnote(c, meta, st, 24)


def cover_full(doc, meta, st, pg):
    """整版封面：整页底色 + 点缀色。"""
    page_setup(doc.sections[0], pg, top=0, bottom=0.6, left=0, right=0)
    t = doc.add_table(rows=1, cols=1)
    table_layout(t, [pg.w], total_twips=int(pg.w * 567))
    no_borders(t)
    r = t.rows[0]
    r.height = Cm(pg.h - 1.1)
    r.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    c = r.cells[0]
    shade(c, st["cover_bg"])
    cell_margins(c, 0, 0, 1700, 1700)
    p = c.paragraphs[0]
    spacing(p, 70, 0)
    _brand_line(p, meta, st, 12)
    _title_block(c, meta, st, SIZES["title"] + 4, 170, 12)
    p = c.add_paragraph()
    spacing(p, 200, 0)
    for k, v in _meta_rows(meta):
        q = c.add_paragraph()
        spacing(q, 0, 3)
        set_run(q.add_run(k + "　"), SIZES["small"], False, st["cover_label"])
        set_run(q.add_run(str(v)), SIZES["body"], True, st["cover_value"])
    if meta.get("confidentiality"):
        q = c.add_paragraph()
        spacing(q, 18, 0)
        set_run(q.add_run(L("confidentiality") + meta["confidentiality"]), SIZES["footer"], True,
                st["cover_accent"])


def cover_line(doc, meta, st, pg):
    """细线封面：白底 + 顶部粗线，留白克制，适合制度与合规文件。"""
    page_setup(doc.sections[0], pg)
    p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    para_border(p, "top", st["cover_accent"], sz=36, space=10)
    spacing(p, 0, 0)
    _brand_line(p, meta, st, 11)
    _title_block(doc, meta, st, SIZES["title"] + 2, 150)
    p = doc.add_paragraph()
    spacing(p, 150, 0)
    _info_table(doc, _meta_rows(meta), st)
    _cover_footnote(doc, meta, st, 30)


COVERS = {"band": cover_band, "side": cover_side, "full": cover_full, "line": cover_line}


def _cover_footnote(container, meta, st, before):
    if not meta.get("confidentiality") and not meta.get("cover_note"):
        return
    p = container.add_paragraph()
    spacing(p, before, 0, line=1.3)
    if meta.get("confidentiality"):
        set_run(p.add_run(L("confidentiality") + meta["confidentiality"]), SIZES["footer"], True,
                st["accent_dark"])
    if meta.get("cover_note"):
        set_run(p.add_run("　" + meta["cover_note"]), SIZES["footer"], False, BRAND["muted"])


# ---------------- 页眉页脚 ----------------
def header_footer(section, meta, st, pg, numbered=True):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    add_tab_stop_right(hp, int(pg.text_w * 567))
    set_run(hp.add_run(CONF.org_name(meta)), SIZES["footer"], True, st["header_brand"], cn=FONTS["head"])
    set_run(hp.add_run(L("header_sep") + meta.get("short_title", meta["title"])), SIZES["footer"], False,
            st["header_text"])
    if meta.get("confidentiality"):
        set_run(hp.add_run("\t" + L("confidentiality") + meta["confidentiality"]), SIZES["footer"], False,
                st["header_text"])
    para_border(hp, "bottom", st["header_line"], sz=4, space=4)
    fp = section.footer.paragraphs[0]
    fp.text = ""
    if not numbered:
        return
    doc_info = L("footer_doc", doc_no=meta.get("doc_no", ""), version=meta.get("version", "")).strip()
    if doc_info:
        # 左侧文档编号与版本，右侧页码
        add_tab_stop_right(fp, int(pg.text_w * 567))
        set_run(fp.add_run(doc_info), SIZES["footer"], False, BRAND["muted"], FONTS["num"])
        set_run(fp.add_run("\t"), SIZES["footer"])
    else:
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(fp.add_run(L("page_prefix")), SIZES["footer"], False, BRAND["muted"])
    add_field(fp, "PAGE", "1", SIZES["footer"], st["deep"], True)
    set_run(fp.add_run(L("page_mid")), SIZES["footer"], False, BRAND["muted"])
    add_field(fp, "SECTIONPAGES", "1", SIZES["footer"], st["deep"], True)
    set_run(fp.add_run(L("page_suffix")), SIZES["footer"], False, BRAND["muted"])


def new_section(doc, pg):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    # add_section 会把上一节的分节符放进一个新的空段落；把它压到最小，避免封面后多出空白页
    mark_size(doc.paragraphs[-1], 1)
    page_setup(sec, pg)
    return sec


def toc(doc, ctx_headings, st, pg):
    p = doc.add_paragraph()
    spacing(p, 0, 16)
    set_run(p.add_run(L("toc_title")), SIZES["h1"] + 2, True, st["heading"], cn=FONTS["head"])
    para_border(p, "bottom", st["rule"], sz=8, space=6)
    entries = [(lvl, txt) for lvl, txt in ctx_headings if lvl <= 2] or [(1, L("toc_placeholder"))]
    first = doc.add_paragraph()
    field_begin(first, 'TOC \\o "1-2" \\h \\z \\u')
    paras = [first] + [doc.add_paragraph() for _ in entries[1:]]
    for par, (lvl, txt) in zip(paras, entries):
        par.paragraph_format.left_indent = Cm(0 if lvl == 1 else 0.75)
        spacing(par, 6 if lvl == 1 else 0, 2)
        set_run(par.add_run(txt), SIZES["body"] if lvl == 1 else SIZES["small"] + 0.5,
                lvl == 1, st["deep"] if lvl == 1 else BRAND["ink_soft"], cn=FONTS["head"] if lvl == 1 else None)
    field_end(paras[-1])
    tip = doc.add_paragraph()
    spacing(tip, 18, 0)
    set_run(tip.add_run(L("toc_tip")), SIZES["footer"], False, BRAND["muted"])


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
            num = blocks_basic.heading_number(lvl, h)
        out.append((lvl, num + b["text"]))
    return out


def render(data, out_path, style_name=None, want_toc=None, base_dir=".", font_preset=None):
    meta = data["meta"]
    style_name = style_name or meta.get("style") or default_style(meta.get("doc_type"))
    st = get_style(style_name)
    if st["cover"] not in COVERS:
        raise SystemExit("风格 %s 的 cover 只能是：%s" % (style_name, "、".join(COVERS)))
    preset = font_preset_for(meta, st, font_preset)
    CONF.set_font_preset(preset)
    charts.use_style(st)
    pg = Page()
    numbering = meta.get("numbering", True)
    blocks = data["blocks"]
    n_h1 = sum(1 for b in blocks if b.get("type") == "heading" and int(b.get("level", 1)) == 1)
    if want_toc is None:
        want_toc = meta.get("toc", n_h1 >= R("toc_min_h1"))
    indent = meta.get("indent", meta.get("doc_type") in R("indent_types"))

    doc = Document()
    setup_styles(doc, st)
    COVERS[st["cover"]](doc, meta, st, pg)

    if want_toc:
        sec = new_section(doc, pg)
        header_footer(sec, meta, st, pg, numbered=False)
        toc(doc, collect_headings(blocks, numbering), st, pg)

    sec = new_section(doc, pg)
    header_footer(sec, meta, st, pg, numbered=True)
    section_page_start(sec, 1)

    tmp = tempfile.mkdtemp(prefix="kb2word_")
    ctx = Ctx(doc, st, numbering, tmp, base_dir, pg, indent, meta.get("h1_new_page", False))
    try:
        for b in blocks:
            REGISTRY[b["type"]](ctx, b)
        if meta.get("end_note"):
            p = doc.add_paragraph()
            spacing(p, 20, 0, line=1.35)
            para_border(p, "top", st["table_line"], 4, 6)
            add_rich(p, meta["end_note"], SIZES["footer"], BRAND["muted"])
        enable_update_fields(doc)
        core = doc.core_properties
        core.title = meta["title"]
        core.subject = meta.get("subtitle", "")
        core.author = meta.get("department") or CONF.org.get("author_default") or CONF.org_name(meta)
        core.keywords = ",".join(meta.get("tags", []))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        doc.save(out_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ctx, style_name, preset


def main():
    ap = argparse.ArgumentParser(description="知识生成 Word：把内容 JSON 渲染为品牌风格 .docx")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--style", help="风格名，见 tap-config/themes.json 的 themes.word.styles")
    ap.add_argument("--font-preset", help="字体方案，见 tap-config/brand.json 的 font_presets（modern / formal）")
    ap.add_argument("--no-toc", action="store_true")
    add_cli_args(ap)
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    configure("word", a, data.get("meta"))
    if a.style and a.style not in CONF.theme_names():
        sys.exit("未知风格 %s，可选：%s" % (a.style, "、".join(CONF.theme_names())))
    errs = validate(data)
    if errs:
        print("内容校验未通过，共 %d 处：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    ctx, style_name, preset = render(data, a.output, a.style, False if a.no_toc else None,
                                     os.path.dirname(os.path.abspath(a.content)), a.font_preset)
    todo, confirm = CONF.count_placeholders(json.dumps(data, ensure_ascii=False))
    print("已生成：%s" % a.output)
    print("风格：%s（%s）；字体方案：%s（标题 %s / 正文 %s / 西文 %s / 数字 %s）"
          % (style_name, ctx.style.get("name", ""), preset, FONTS["head"], FONTS["cn"], FONTS["en"], FONTS["num"]))
    print("一级标题 %d 个；表 %d 个；图 %d 个"
          % (sum(1 for l, _ in ctx.headings if l == 1), ctx.counters["tab"], ctx.counters["fig"]))
    if todo or confirm:
        print("待处理占位：待补充 %d 处，请确认 %d 处（文中已黄底高亮）" % (todo, confirm))
    hints, total = content_check.check_blocks(data["meta"], data["blocks"])
    if hints:
        print("内容体检：%d 项提示（交付前逐条处理，或在交付说明里解释为什么保留）" % total)
        for h in hints:
            print("  - " + h)
        if total > len(hints):
            print("  - ……另有 %d 项未列出" % (total - len(hints)))
    else:
        print("内容体检：未发现套话、话题式标题、单薄章节等问题")


if __name__ == "__main__":
    main()
