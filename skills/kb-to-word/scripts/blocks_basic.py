# -*- coding: utf-8 -*-
"""
文字类与表格类元素（16 种）：
  heading 标题 / paragraph 正文 / lead 导语 / bullets 要点列表 / numbered 编号列表 /
  callout 提示框（6 种语义）/ quote 引文 / note 注释 / table 品牌表格 / glossary 术语表 /
  faq 常见问题 / checklist 清单 / signoff 签批栏 / revisions 版本记录 / contact 联系卡片 /
  page_break 分页
每个函数签名都是 fn(ctx, block)。字段说明见 reference/elements.md。
"""
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt

from docx_helpers import (add_rich, cell_borders, cell_margins, para_border, row_flags, set_run,
                          shade, spacing, table_borders, table_cell_margins, table_layout,
                          no_borders)
from themes import BRAND, CALLOUTS, SIZES

CN_NUM = "一二三四五六七八九十"


def cn_number(n):
    if n <= 10:
        return CN_NUM[n - 1]
    if n < 20:
        return "十" + CN_NUM[n - 11]
    return CN_NUM[n // 10 - 1] + "十" + (CN_NUM[n % 10 - 1] if n % 10 else "")


def gap(ctx, pt=4):
    p = ctx.doc.add_paragraph()
    spacing(p, 0, 0, exact=pt)
    return p


# ---------------- 标题与段落 ----------------
def heading(ctx, b):
    level = int(b.get("level", 1))
    text = b["text"]
    st = ctx.style
    p = ctx.doc.add_paragraph(style="Heading %d" % level)
    num = ""
    if ctx.numbering:
        ctx.h[level - 1] += 1
        for i in range(level, 3):
            ctx.h[i] = 0
        if level == 1:
            num = cn_number(ctx.h[0]) + "、"
        elif level == 2:
            num = "%d.%d　" % (ctx.h[0], ctx.h[1])
        else:
            num = "%d.%d.%d　" % (ctx.h[0], ctx.h[1], ctx.h[2])
    if level == 1:
        if num:
            set_run(p.add_run(num), SIZES["h1"], True, st["heading_num"])
        set_run(p.add_run(text), SIZES["h1"], True, st["heading"])
        para_border(p, "bottom", st["rule"], sz=12, space=6)
        if b.get("new_page"):
            p.paragraph_format.page_break_before = True
    elif level == 2:
        if num:
            set_run(p.add_run(num), SIZES["h2"], True, st["heading_num"])
        set_run(p.add_run(text), SIZES["h2"], True, st["h2"])
    else:
        if num:
            set_run(p.add_run(num), SIZES["h3"], True, st["heading_num"])
        set_run(p.add_run(text), SIZES["h3"], True, BRAND["ink"])
    ctx.headings.append((level, num + text))


def paragraph(ctx, b):
    p = ctx.doc.add_paragraph()
    add_rich(p, b["text"], SIZES["body"], BRAND["ink"])
    align = b.get("align", "justify")
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[align]
    if b.get("indent", False):
        p.paragraph_format.first_line_indent = Pt(SIZES["body"] * 2)


def lead(ctx, b):
    """导语：章节开头的 1-2 句结论，较大字号 + 左侧色条。"""
    p = ctx.doc.add_paragraph()
    add_rich(p, b["text"], 11.5, BRAND["ink_soft"])
    p.paragraph_format.left_indent = Cm(0.35)
    para_border(p, "left", ctx.style["rule"], sz=24, space=8)
    spacing(p, 4, 10, line=1.45)


def bullets(ctx, b, _level=0):
    for it in b["items"]:
        text, subs = (it, None) if isinstance(it, str) else (it.get("text", ""), it.get("sub"))
        p = ctx.doc.add_paragraph()
        indent = 0.55 + 0.6 * _level
        p.paragraph_format.left_indent = Cm(indent)
        p.paragraph_format.first_line_indent = Cm(-0.42)
        glyph = "■" if _level == 0 else "–"
        set_run(p.add_run(glyph + "  "), 7 if _level == 0 else SIZES["body"], True,
                ctx.style["heading_num"])
        add_rich(p, text, SIZES["body"], BRAND["ink"])
        spacing(p, 0, 3)
        if subs:
            bullets(ctx, {"items": subs}, _level + 1)


def numbered(ctx, b):
    for i, it in enumerate(b["items"], 1):
        p = ctx.doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.7)
        p.paragraph_format.first_line_indent = Cm(-0.7)
        set_run(p.add_run("%d.　" % i), SIZES["body"], True, ctx.style["heading_num"], "Arial")
        add_rich(p, it if isinstance(it, str) else it.get("text", ""), SIZES["body"], BRAND["ink"])
        spacing(p, 0, 3)


# ---------------- 提示框 / 引文 / 注释 ----------------
def _boxed(ctx, bar, bg, width=None):
    t = ctx.doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [width or ctx.text_width_cm])
    no_borders(t)
    c = t.rows[0].cells[0]
    shade(c, bg)
    cell_borders(c, left=("single", 24, bar), top=None, bottom=None, right=None)
    cell_margins(c, 120, 120, 220, 200)
    row_flags(t.rows[0])
    return c


def callout(ctx, b):
    kind = b.get("kind", "info")
    spec = CALLOUTS.get(kind, CALLOUTS["info"])
    c = _boxed(ctx, spec["bar"], spec["bg"])
    p = c.paragraphs[0]
    spacing(p, 0, 2)
    set_run(p.add_run("%s  %s" % (spec["icon"], b.get("title") or spec["label"])), SIZES["body"],
            True, spec["bar"])
    if b.get("text"):
        p2 = c.add_paragraph()
        add_rich(p2, b["text"], SIZES["body"], BRAND["ink"])
        spacing(p2, 2, 0, line=1.35)
    for it in b.get("items", []):
        p3 = c.add_paragraph()
        p3.paragraph_format.left_indent = Cm(0.4)
        p3.paragraph_format.first_line_indent = Cm(-0.4)
        set_run(p3.add_run("·  "), SIZES["body"], True, spec["bar"])
        add_rich(p3, it, SIZES["body"], BRAND["ink"])
        spacing(p3, 1, 0)
    gap(ctx, 8)


def quote(ctx, b):
    p = ctx.doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.0)
    p.paragraph_format.right_indent = Cm(1.0)
    set_run(p.add_run("“"), 26, True, ctx.style["heading_num"], "Georgia")
    add_rich(p, b["text"], 12, BRAND["ink"])
    spacing(p, 8, 2, line=1.4)
    if b.get("source"):
        s = ctx.doc.add_paragraph()
        s.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        s.paragraph_format.right_indent = Cm(1.0)
        set_run(s.add_run("—— " + b["source"]), SIZES["small"], False, BRAND["muted"])
        spacing(s, 0, 10)


def note(ctx, b):
    p = ctx.doc.add_paragraph()
    set_run(p.add_run(b.get("label", "注") + "："), SIZES["small"], True, BRAND["muted"])
    add_rich(p, b["text"], SIZES["small"], BRAND["muted"])
    spacing(p, 2, 6)


def page_break(ctx, b):
    ctx.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------- 图表题注 ----------------
def caption(ctx, kind, text, above=False):
    if not text:
        return
    ctx.counters[kind] += 1
    p = ctx.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if kind == "fig" else WD_ALIGN_PARAGRAPH.LEFT
    label = ("图 %d" if kind == "fig" else "表 %d") % ctx.counters[kind]
    set_run(p.add_run(label + "　"), SIZES["caption"], True, ctx.style["heading_num"])
    set_run(p.add_run(text), SIZES["caption"], True, BRAND["ink_soft"])
    spacing(p, 6 if above else 2, 3 if above else 2)
    if above:
        p.paragraph_format.keep_with_next = True
    ctx.captions.append(label + " " + text)


def source_line(ctx, src):
    if not src:
        return
    p = ctx.doc.add_paragraph()
    set_run(p.add_run("资料来源：" + src), SIZES["footer"], False, BRAND["muted"])
    spacing(p, 0, 8)


# ---------------- 品牌表格 ----------------
def _auto_widths(columns, rows, total):
    """按内容长度估算列宽（中文按 2 个宽度），每列至少 1.6cm。"""
    def w(s):
        s = str(s)
        return sum(2 if ord(ch) > 127 else 1 for ch in s)
    est = []
    for i, c in enumerate(columns):
        lens = [w(c)] + [w(r[i]) for r in rows if i < len(r)]
        est.append(min(max(lens), 40) + 4)
    s = float(sum(est))
    widths = [max(1.6, total * e / s) for e in est]
    k = total / sum(widths)
    return [x * k for x in widths]


def _is_num(s):
    s = str(s).replace(",", "").replace("%", "").replace("亿元", "").replace("万元", "").strip()
    s = s.lstrip("+-▲▼")
    try:
        float(s)
        return True
    except ValueError:
        return False


def table(ctx, b):
    st = ctx.style
    cols = b["columns"]
    rows = b["rows"]
    caption(ctx, "tab", b.get("caption"), above=True)
    t = ctx.doc.add_table(rows=1 + len(rows), cols=len(cols))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = b.get("widths") or _auto_widths(cols, rows, ctx.text_width_cm)
    table_layout(t, widths)
    table_borders(t, BRAND["line"], sz=4, inside_h=True, inside_v=False, outer=False)
    table_cell_margins(t, 70, 70, 110, 110)
    hi = b.get("highlight_col")
    total_row = b.get("total_row", False)
    first_bold = b.get("first_col_bold", True)

    hdr = t.rows[0]
    row_flags(hdr, header=True)
    for i, name in enumerate(cols):
        c = hdr.cells[i]
        shade(c, st["table_head_bg"])
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = c.paragraphs[0]
        set_run(p.add_run(str(name)), SIZES["small"] + 0.5, True, st["table_head_fg"])
        if st["table_head_bg"] == BRAND["bg_soft"]:
            cell_borders(c, bottom=("single", 12, BRAND["orange"]))
    for ri, r in enumerate(rows):
        row = t.rows[ri + 1]
        row_flags(row)
        is_total = total_row and ri == len(rows) - 1
        for ci in range(len(cols)):
            v = r[ci] if ci < len(r) else ""
            c = row.cells[ci]
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if is_total:
                shade(c, st["table_total_bg"])
                cell_borders(c, top=("single", 8, st["rule"]))
            elif hi is not None and ci == hi:
                shade(c, st["highlight_col_bg"])
            elif ri % 2 == 1 and st["table_stripe"] != BRAND["white"]:
                shade(c, st["table_stripe"])
            p = c.paragraphs[0]
            if _is_num(v) and ci > 0:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            bold = is_total or (first_bold and ci == 0) or (hi is not None and ci == hi)
            add_rich(p, v, SIZES["small"] + 0.5, BRAND["ink"], bold)
    if b.get("note"):
        note(ctx, {"text": b["note"]})
    source_line(ctx, b.get("source"))
    if not b.get("note") and not b.get("source"):
        gap(ctx, 8)


# ---------------- 术语 / FAQ / 清单 / 签批 / 版本 / 联系 ----------------
def glossary(ctx, b):
    items = b["items"]
    t = ctx.doc.add_table(rows=len(items), cols=2)
    table_layout(t, [3.6, ctx.text_width_cm - 3.6])
    table_borders(t, BRAND["line"], 4, inside_h=True, outer=False)
    table_cell_margins(t, 80, 80, 100, 100)
    for r, it in zip(t.rows, items):
        row_flags(r)
        set_run(r.cells[0].paragraphs[0].add_run(it["term"]), SIZES["body"], True,
                BRAND["orange_dark"])
        add_rich(r.cells[1].paragraphs[0], it["definition"], SIZES["body"], BRAND["ink"])
    gap(ctx, 8)


def faq(ctx, b):
    for it in b["items"]:
        q = ctx.doc.add_paragraph()
        q.paragraph_format.keep_with_next = True
        q.paragraph_format.left_indent = Cm(0.9)
        q.paragraph_format.first_line_indent = Cm(-0.9)
        set_run(q.add_run(" 问 "), SIZES["small"], True, BRAND["white"])
        _badge(q, ctx.style["heading_num"])
        set_run(q.add_run("　"), SIZES["body"])
        add_rich(q, it["q"], SIZES["body"], BRAND["ink"], True)
        spacing(q, 6, 2)
        a = ctx.doc.add_paragraph()
        a.paragraph_format.left_indent = Cm(0.9)
        a.paragraph_format.first_line_indent = Cm(-0.9)
        set_run(a.add_run(" 答 "), SIZES["small"], True, BRAND["white"])
        _badge(a, BRAND["green"])
        set_run(a.add_run("　"), SIZES["body"])
        add_rich(a, it["a"], SIZES["body"], BRAND["ink_soft"])
        spacing(a, 0, 6, line=1.35)


def _badge(par, fill):
    """给段落中最近一个“问/答”字块加底色（run 级底纹）。"""
    from docx.oxml.ns import qn
    from docx_helpers import el
    run = None
    for r in par.runs:
        if r.text.strip() in ("问", "答"):
            run = r
    if run is None:
        return
    rpr = run._element.get_or_add_rPr()
    for old in rpr.findall(qn("w:shd")):
        rpr.remove(old)
    shd = el("w:shd", val="clear", color="auto", fill=fill)
    # rPr 中 shd 位于 bdr 之后、fitText 之前；这里直接追加到可能存在的 vertAlign/lang 之前
    anchor = None
    for tag in ("fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout"):
        anchor = rpr.find(qn("w:" + tag))
        if anchor is not None:
            break
    if anchor is not None:
        anchor.addprevious(shd)
    else:
        rpr.append(shd)


def checklist(ctx, b):
    items = b["items"]
    has_note = any(isinstance(i, dict) and i.get("note") for i in items)
    widths = [0.8, ctx.text_width_cm - 0.8 - (5.0 if has_note else 0) - 1.6, 1.6]
    if has_note:
        widths.append(5.0)
    t = ctx.doc.add_table(rows=len(items), cols=len(widths))
    table_layout(t, widths)
    table_borders(t, BRAND["line"], 4, inside_h=True, outer=False)
    table_cell_margins(t, 70, 70, 80, 80)
    for r, it in zip(t.rows, items):
        row_flags(r)
        it = {"text": it} if isinstance(it, str) else it
        set_run(r.cells[0].paragraphs[0].add_run("☐"), 12, False, ctx.style["heading_num"])
        add_rich(r.cells[1].paragraphs[0], it["text"], SIZES["body"], BRAND["ink"])
        tag = "必备" if it.get("required", True) else "如适用"
        pc = r.cells[2].paragraphs[0]
        pc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(pc.add_run(tag), SIZES["footer"], True,
                BRAND["orange_dark"] if tag == "必备" else BRAND["muted"])
        if has_note:
            add_rich(r.cells[3].paragraphs[0], it.get("note", ""), SIZES["small"], BRAND["muted"])
    gap(ctx, 8)


def signoff(ctx, b):
    roles = b.get("roles", ["编制", "审核", "批准"])
    cols = ["角色", "部门", "姓名", "签字", "日期"]
    t = ctx.doc.add_table(rows=1 + len(roles), cols=len(cols))
    table_layout(t, [2.4, 3.6, 2.8, 4.4, ctx.text_width_cm - 13.2])
    table_borders(t, BRAND["ink_soft"], 4, inside_h=True, inside_v=True, outer=True)
    for i, n in enumerate(cols):
        c = t.rows[0].cells[i]
        shade(c, BRAND["bg_soft"])
        set_run(c.paragraphs[0].add_run(n), SIZES["small"], True, BRAND["ink"])
    for r, role in zip(t.rows[1:], roles):
        r.height = Cm(1.2)
        r.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row_flags(r)
        r.cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_run(r.cells[0].paragraphs[0].add_run(role), SIZES["body"], True, BRAND["ink"])
    gap(ctx, 8)


def revisions(ctx, b):
    table(ctx, {"columns": ["版本", "日期", "修订人", "修订内容"],
                "rows": [[i["version"], i["date"], i.get("author", ""), i["change"]]
                         for i in b["items"]],
                "widths": [1.8, 2.8, 2.4, ctx.text_width_cm - 7.0],
                "caption": b.get("caption")})


def contact(ctx, b):
    items = b["items"]
    n = min(len(items), 3)
    rows = (len(items) + n - 1) // n
    t = ctx.doc.add_table(rows=rows, cols=n)
    w = ctx.text_width_cm / n
    table_layout(t, [w] * n)
    no_borders(t)
    for i, it in enumerate(items):
        c = t.rows[i // n].cells[i % n]
        shade(c, BRAND["orange_pale"])
        cell_borders(c, top=("single", 18, ctx.style["rule"]), left=("single", 24, BRAND["white"]),
                     right=("single", 24, BRAND["white"]), bottom=None)
        cell_margins(c, 120, 120, 160, 160)
        p = c.paragraphs[0]
        set_run(p.add_run(it["label"]), SIZES["small"], False, BRAND["muted"])
        p2 = c.add_paragraph()
        add_rich(p2, it["value"], 12, BRAND["ink"], True)
        if it.get("desc"):
            p3 = c.add_paragraph()
            add_rich(p3, it["desc"], SIZES["footer"], BRAND["ink_soft"])
    gap(ctx, 8)


REGISTRY = {
    "heading": heading, "paragraph": paragraph, "lead": lead, "bullets": bullets,
    "numbered": numbered, "callout": callout, "quote": quote, "note": note,
    "page_break": page_break, "table": table, "glossary": glossary, "faq": faq,
    "checklist": checklist, "signoff": signoff, "revisions": revisions, "contact": contact,
}
