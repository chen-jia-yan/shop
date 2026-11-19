# -*- coding: utf-8 -*-
"""
文字类与表格类元素（18 种）：
  heading 标题 / paragraph 正文 / lead 导语 / bullets 要点列表 / numbered 编号列表 /
  callout 提示框（6 种语义）/ quote 引文 / note 注释 / table 品牌表格 / glossary 术语表 /
  faq 常见问题 / checklist 清单 / signoff 签批栏 / revisions 版本记录 / contact 联系卡片 /
  facts 要素表 / exec_summary 执行摘要 / page_break 分页
每个函数签名都是 fn(ctx, block)。字段说明见 reference/elements.md。
颜色全部取自当前风格（ctx.style，见 themes.json 的 themes.word.styles），字号、固定文字、符号取自 tap-config。
"""
import re

from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt

from docx_helpers import (add_rich, cell_borders, cell_margins, para_border, para_shade, row_flags,
                          set_run, shade, spacing, table_borders, table_cell_margins, table_layout,
                          no_borders)
from themes import BRAND, CONF, FONTS, SIZES, G, L, R, callout as callout_spec


def cn_number(n):
    d = L("cn_digits")                      # 一二三四五六七八九十
    ten = d[9]
    if n <= 10:
        return d[n - 1]
    if n < 20:
        return ten + d[n - 11]
    return d[n // 10 - 1] + ten + (d[n % 10 - 1] if n % 10 else "")


def heading_number(level, h):
    fmt = L("heading_num")
    if level == 1:
        return fmt["l1"].format(cn=cn_number(h[0]), a=h[0])
    if level == 2:
        return fmt["l2"].format(a=h[0], b=h[1])
    return fmt["l3"].format(a=h[0], b=h[1], c=h[2])


def gap(ctx, pt=4):
    p = ctx.doc.add_paragraph()
    spacing(p, 0, 0, exact=pt)
    return p


# ---------------- 标题与段落 ----------------
def heading(ctx, b):
    level = int(b.get("level", 1))
    text = b["text"]
    st = ctx.style
    p = ctx.doc.add_paragraph(style="Heading %d" % min(level, 3))
    num = ""
    if ctx.numbering:
        ctx.h[level - 1] += 1
        for i in range(level, 3):
            ctx.h[i] = 0
        num = heading_number(level, ctx.h)
    size = SIZES["h%d" % min(level, 3)]
    color = {1: st["heading"], 2: st["h2"]}.get(level, st["h3"])
    if num:
        set_run(p.add_run(num), size, True, st["heading_num"], FONTS["num"], cn=FONTS["head"])
    set_run(p.add_run(text), size, True, color, cn=FONTS["head"])
    if level == 1:
        if st["h1_style"] == "bar":
            # 左侧主色竖条 + 浅底纹；上下用与底纹同色的边框撑出内边距
            para_shade(p, st["h1_bg"])
            para_border(p, "left", st["rule"], sz=36, space=8)
            para_border(p, "top", st["h1_bg"], sz=4, space=5)
            para_border(p, "bottom", st["h1_bg"], sz=4, space=5)
            p.paragraph_format.left_indent = Cm(0.25)
        elif st["h1_style"] == "rule":
            para_border(p, "bottom", st["rule"], sz=8, space=5)
        first_h1 = not any(lv == 1 for lv, _ in ctx.headings)
        if b.get("new_page") or (ctx.h1_new_page and not first_h1):
            p.paragraph_format.page_break_before = True
    ctx.headings.append((level, num + text))


def paragraph(ctx, b):
    p = ctx.doc.add_paragraph()
    add_rich(p, b["text"], SIZES["body"], BRAND["ink"])
    align = b.get("align", "justify")
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[align]
    if b.get("indent", ctx.indent):
        p.paragraph_format.first_line_indent = Pt(CONF.size(SIZES["body"]) * 2)


def lead(ctx, b):
    """导语：章节开头的 1-2 句结论，较大字号 + 左侧色条。"""
    p = ctx.doc.add_paragraph()
    add_rich(p, b["text"], SIZES["lead"], ctx.style["lead_fg"])
    p.paragraph_format.left_indent = Cm(0.35)
    para_border(p, "left", ctx.style["lead_bar"], sz=18, space=8)
    spacing(p, 2, 10, line=1.5)


def bullets(ctx, b, _level=0):
    st = ctx.style
    for it in b["items"]:
        text, subs = (it, None) if isinstance(it, str) else (it.get("text", ""), it.get("sub"))
        p = ctx.doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.55 + 0.6 * _level)
        p.paragraph_format.first_line_indent = Cm(-0.42)
        glyph = G("bullet") if _level == 0 else G("sub_bullet")
        set_run(p.add_run(glyph + "  "), 6.5 if _level == 0 else SIZES["body"], True,
                st["accent"] if _level == 0 else st["deep_mid"])
        add_rich(p, text, SIZES["body"], BRAND["ink"])
        spacing(p, 0, 3)
        if subs:
            bullets(ctx, {"items": subs}, _level + 1)


def numbered(ctx, b):
    for i, it in enumerate(b["items"], 1):
        p = ctx.doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.7)
        p.paragraph_format.first_line_indent = Cm(-0.7)
        set_run(p.add_run(L("numbered", n=i)), SIZES["body"], True, ctx.style["accent"], FONTS["num"])
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
    cell_borders(c, left=("single", 18, bar), top=None, bottom=None, right=None)
    cell_margins(c, 130, 130, 240, 220)
    row_flags(t.rows[0])
    return c


def callout(ctx, b):
    spec = callout_spec(b.get("kind", "info"), ctx.style)
    c = _boxed(ctx, spec["bar"], spec["bg"])
    p = c.paragraphs[0]
    spacing(p, 0, 3)
    set_run(p.add_run("%s  %s" % (spec["icon"], b.get("title") or spec["label"])), SIZES["body"],
            True, spec["bar"], cn=FONTS["head"])
    if b.get("text"):
        p2 = c.add_paragraph()
        add_rich(p2, b["text"], SIZES["body"], BRAND["ink"])
        spacing(p2, 2, 0, line=1.45)
    for it in b.get("items", []):
        p3 = c.add_paragraph()
        p3.paragraph_format.left_indent = Cm(0.4)
        p3.paragraph_format.first_line_indent = Cm(-0.4)
        set_run(p3.add_run(G("dot") + "  "), SIZES["body"], True, spec["bar"])
        add_rich(p3, it, SIZES["body"], BRAND["ink"])
        spacing(p3, 2, 0, line=1.4)
    gap(ctx, 10)


def quote(ctx, b):
    p = ctx.doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.0)
    p.paragraph_format.right_indent = Cm(1.0)
    set_run(p.add_run(G("quote_open")), 26, True, ctx.style["accent_light"], FONTS["quote"])
    add_rich(p, b["text"], SIZES["quote"], ctx.style["deep"])
    spacing(p, 8, 2, line=1.45)
    if b.get("source"):
        s = ctx.doc.add_paragraph()
        s.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        s.paragraph_format.right_indent = Cm(1.0)
        set_run(s.add_run(L("quote_by", s=b["source"])), SIZES["small"], False, BRAND["muted"])
        spacing(s, 0, 10)


def note(ctx, b):
    p = ctx.doc.add_paragraph()
    set_run(p.add_run(b.get("label", L("note")) + "："), SIZES["small"], True, BRAND["muted"])
    add_rich(p, b["text"], SIZES["small"], BRAND["muted"])
    spacing(p, 3, 8, line=1.35)


def page_break(ctx, b):
    ctx.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------- 图表题注 ----------------
def caption(ctx, kind, text, above=False):
    if not text:
        return
    ctx.counters[kind] += 1
    p = ctx.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if kind == "fig" else WD_ALIGN_PARAGRAPH.LEFT
    label = L("figure" if kind == "fig" else "table", n=ctx.counters[kind])
    set_run(p.add_run(label + "　"), SIZES["caption"], True, ctx.style["accent_dark"], cn=FONTS["head"])
    set_run(p.add_run(text), SIZES["caption"], True, ctx.style["deep"], cn=FONTS["head"])
    spacing(p, 8 if above else 3, 4 if above else 2)
    if above:
        p.paragraph_format.keep_with_next = True
    ctx.captions.append(label + " " + text)


def source_line(ctx, src):
    if not src:
        return
    p = ctx.doc.add_paragraph()
    set_run(p.add_run(L("source") + src), SIZES["footer"], False, BRAND["muted"])
    spacing(p, 2, 10)


# ---------------- 品牌表格 ----------------
def _auto_widths(columns, rows, total):
    """按内容长度估算列宽（中日韩字符按 2 个宽度），每列至少 1.6cm。"""
    def w(s):
        return sum(2 if ord(ch) > 127 else 1 for ch in str(s))
    est = []
    for i, c in enumerate(columns):
        lens = [w(c)] + [w(r[i]) for r in rows if i < len(r)]
        est.append(min(max(lens), 40) + 4)
    s = float(sum(est))
    widths = [max(1.6, total * e / s) for e in est]
    k = total / sum(widths)
    return [x * k for x in widths]


def fit_widths(widths, total):
    """内容 JSON 里写的列宽按比例贴合版心：超出版心或与版心相差不到 1cm 时等比缩放到版心宽度。"""
    s = float(sum(widths))
    if s > total or total - s < 1.0:
        return [w * total / s for w in widths]
    return widths


# 数字判断：可带正负/涨跌符号、千分位、小数、百分号，以及不超过 4 个字的单位后缀
_NUM = re.compile(r"^[+\-−▲▼]?\s*\d[\d,，]*(?:\.\d+)?\s*%?\s*\D{0,4}$")


def _is_num(s):
    return bool(_NUM.match(str(s).strip()))


def _sign(s):
    s = str(s).strip()
    if not s:
        return 0
    if s[0] in "+▲↑":
        return 1
    if s[0] in "-−▼↓":
        return -1
    return 0


def _head_cells(ctx, row, cols, aligns):
    st = ctx.style
    kind = st["table_style"]
    row_flags(row, header=True)
    for i, name in enumerate(cols):
        c = row.cells[i]
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        if st["table_head_bg"] != BRAND["white"]:
            shade(c, st["table_head_bg"])
        if kind == "three_line":
            cell_borders(c, top=("single", 12, st["table_head_line"]), bottom=("single", 6, st["table_head_line"]))
        elif kind == "tint":
            cell_borders(c, bottom=("single", 12, st["table_head_line"]))
        p = c.paragraphs[0]
        p.alignment = aligns[i]
        set_run(p.add_run(str(name)), SIZES["table"], True, st["table_head_fg"], cn=FONTS["head"])
        spacing(p, 0, 0, line=1.2)


def table(ctx, b):
    st = ctx.style
    cols = b["columns"]
    rows = b["rows"]
    kind = st["table_style"]
    caption(ctx, "tab", b.get("caption"), above=True)
    t = ctx.doc.add_table(rows=1 + len(rows), cols=len(cols))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = fit_widths(b["widths"], ctx.text_width_cm) if b.get("widths") else \
        _auto_widths(cols, rows, ctx.text_width_cm)
    table_layout(t, widths)
    if kind == "three_line":
        no_borders(t)
    else:
        table_borders(t, st["table_line"], sz=4, inside_h=True, inside_v=False, outer=False)
    table_cell_margins(t, 75, 75, 120, 120)
    hi = b.get("highlight_col")
    total_row = b.get("total_row", False)
    first_bold = b.get("first_col_bold", True)
    delta_cols = {i for i, c in enumerate(cols) if any(k in str(c) for k in R("delta_headers"))}
    # 列对齐：除首列外，整列都是数字的右对齐（表头随列对齐）
    aligns = []
    for ci in range(len(cols)):
        vals = [r[ci] for r in rows if ci < len(r) and str(r[ci]).strip() not in ("", "—", "-")]
        numeric = ci > 0 and vals and all(_is_num(v) for v in vals)
        aligns.append(WD_ALIGN_PARAGRAPH.RIGHT if numeric else WD_ALIGN_PARAGRAPH.LEFT)
    _head_cells(ctx, t.rows[0], cols, aligns)

    for ri, r in enumerate(rows):
        row = t.rows[ri + 1]
        row_flags(row)
        is_total = total_row and ri == len(rows) - 1
        is_last = ri == len(rows) - 1
        for ci in range(len(cols)):
            v = r[ci] if ci < len(r) else ""
            c = row.cells[ci]
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if is_total:
                shade(c, st["table_total_bg"])
                cell_borders(c, top=("single", 8, st["table_head_line"]))
            elif hi is not None and ci == hi:
                shade(c, st["highlight_col_bg"])
            elif ri % 2 == 1 and st["table_stripe"] != BRAND["white"]:
                shade(c, st["table_stripe"])
            if is_last and kind == "three_line":
                cell_borders(c, bottom=("single", 12, st["table_head_line"]))
            elif is_last and kind == "tint":
                cell_borders(c, bottom=("single", 6, st["table_head_line"]))
            p = c.paragraphs[0]
            spacing(p, 0, 0, line=1.3)
            numeric = _is_num(v) and ci > 0
            if numeric:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            bold = is_total or (first_bold and ci == 0) or (hi is not None and ci == hi)
            color = BRAND["ink"]
            if ci in delta_cols and not is_total:
                sign = _sign(v) * (-1 if b.get("delta_good") == "down" else 1)
                color = {1: st["good"], -1: st["bad"]}.get(sign, BRAND["ink"])
            add_rich(p, v, SIZES["table"], color, bold, FONTS["num"] if numeric else None)
    if b.get("note"):
        note(ctx, {"text": b["note"]})
    source_line(ctx, b.get("source"))
    if not b.get("note") and not b.get("source"):
        gap(ctx, 10)


# ---------------- 要素表 / 执行摘要 ----------------
def facts(ctx, b):
    """要素表：投保年龄、保障期间等“名称—取值”成对排列，每行 cols 组（默认 2 组）。"""
    st = ctx.style
    items = b["items"]
    lo, hi = R("facts_cols")
    n = max(lo, min(hi, int(b.get("cols", 2))))
    rows = (len(items) + n - 1) // n
    caption(ctx, "tab", b.get("caption"), above=True)
    t = ctx.doc.add_table(rows=rows, cols=n * 2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    lw = 2.6 if n <= 2 else 2.0
    vw = ctx.text_width_cm / n - lw
    table_layout(t, [lw, vw] * n)
    table_borders(t, st["table_line"], sz=4, inside_h=True, inside_v=False, outer=False)
    table_cell_margins(t, 85, 85, 120, 120)
    for i in range(rows * n):
        r, k = divmod(i, n)
        row = t.rows[r]
        row_flags(row)
        lc, vc = row.cells[k * 2], row.cells[k * 2 + 1]
        shade(lc, st["card_bg"])
        for c in (lc, vc):
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if r == 0:
                cell_borders(c, top=("single", 12, st["table_head_line"]))
            if r == rows - 1:
                cell_borders(c, bottom=("single", 6, st["table_head_line"]))
        if i >= len(items):
            continue
        it = items[i]
        set_run(lc.paragraphs[0].add_run(it["label"]), SIZES["small"], False, st["deep_mid"])
        p = vc.paragraphs[0]
        spacing(p, 0, 0, line=1.3)
        add_rich(p, it["value"], SIZES["table"] + 0.5, BRAND["ink"], True)
        if it.get("note"):
            q = vc.add_paragraph()
            spacing(q, 1, 0)
            add_rich(q, it["note"], SIZES["footer"], BRAND["muted"])
    if b.get("note"):
        note(ctx, {"text": b["note"]})
    source_line(ctx, b.get("source"))
    if not b.get("note") and not b.get("source"):
        gap(ctx, 10)


def exec_summary(ctx, b):
    """执行摘要：核心结论 + 带数字的主要发现 + 需要决策事项，放在正文最前面。"""
    st = ctx.style
    w = ctx.text_width_cm
    fw = 3.4
    findings = b.get("findings", [])
    decisions = b.get("decisions", [])
    n_rows = 2 + len(findings) + (1 + len(decisions) if decisions else 0)
    t = ctx.doc.add_table(rows=n_rows, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [fw, w - fw])
    no_borders(t)

    head = t.cell(0, 0).merge(t.cell(0, 1))
    shade(head, st["deep"])
    cell_margins(head, 110, 110, 240, 220)
    p = head.paragraphs[0]
    set_run(p.add_run(b.get("title") or L("exec_title")), SIZES["h2"], True, BRAND["white"], cn=FONTS["head"])
    if b.get("subtitle"):
        set_run(p.add_run("　" + b["subtitle"]), SIZES["small"], False, st["accent_light"])

    con = t.cell(1, 0).merge(t.cell(1, 1))
    shade(con, st["accent_pale"])
    cell_margins(con, 160, 160, 240, 220)
    p = con.paragraphs[0]
    set_run(p.add_run(L("exec_conclusion")), SIZES["small"], True, st["accent_dark"], cn=FONTS["head"])
    p2 = con.add_paragraph()
    spacing(p2, 3, 0, line=1.45)
    add_rich(p2, b.get("conclusion", ""), SIZES["lead"], st["deep"], True, cn=FONTS["head"])

    for i, f in enumerate(findings):
        f = {"text": f} if isinstance(f, str) else f
        row = t.rows[2 + i]
        row_flags(row)
        fc, tc = row.cells
        for c in (fc, tc):
            cell_borders(c, bottom=("single", 4, st["table_line"]))
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cell_margins(fc, 110, 110, 240, 80)
        cell_margins(tc, 110, 110, 120, 220)
        pf = fc.paragraphs[0]
        if f.get("figure"):
            color = {1: st["good"], -1: st["bad"]}.get(_sign(f.get("trend", "")), st["accent_dark"])
            set_run(pf.add_run(str(f["figure"])), SIZES["h1"], True, color, FONTS["num"])
            if f.get("label"):
                q = fc.add_paragraph()
                set_run(q.add_run(f["label"]), SIZES["footer"], False, BRAND["muted"])
        else:
            set_run(pf.add_run(G("circled")[i % len(G("circled"))]), SIZES["h2"], True, st["accent"])
        pt = tc.paragraphs[0]
        spacing(pt, 0, 0, line=1.45)
        add_rich(pt, f["text"], SIZES["body"], BRAND["ink"])
        if f.get("ref"):
            set_run(pt.add_run("　" + f["ref"]), SIZES["footer"], False, BRAND["muted"])

    if decisions:
        base = 2 + len(findings)
        dh = t.cell(base, 0).merge(t.cell(base, 1))
        cell_margins(dh, 140, 40, 240, 220)
        set_run(dh.paragraphs[0].add_run(L("exec_decisions")), SIZES["small"], True, st["bad"], cn=FONTS["head"])
        for j, d in enumerate(decisions):
            c = t.cell(base + 1 + j, 0).merge(t.cell(base + 1 + j, 1))
            cell_margins(c, 30, 30 if j < len(decisions) - 1 else 140, 240, 220)
            p = c.paragraphs[0]
            p.paragraph_format.left_indent = Cm(0.55)
            p.paragraph_format.first_line_indent = Cm(-0.55)
            set_run(p.add_run(G("box") + "  "), SIZES["body"], False, st["bad"])
            add_rich(p, d, SIZES["body"], BRAND["ink"])
        for r in t.rows[base:]:
            for c in r.cells:
                shade(c, st["card_bg"])
    for r in t.rows:
        row_flags(r)
    gap(ctx, 12)


# ---------------- 术语 / FAQ / 清单 / 签批 / 版本 / 联系 ----------------
def glossary(ctx, b):
    st = ctx.style
    items = b["items"]
    t = ctx.doc.add_table(rows=len(items), cols=2)
    table_layout(t, [3.6, ctx.text_width_cm - 3.6])
    table_borders(t, st["table_line"], 4, inside_h=True, outer=False)
    table_cell_margins(t, 85, 85, 110, 110)
    for i, (r, it) in enumerate(zip(t.rows, items)):
        row_flags(r)
        if i == 0:
            for c in r.cells:
                cell_borders(c, top=("single", 8, st["table_head_line"]))
        set_run(r.cells[0].paragraphs[0].add_run(it["term"]), SIZES["body"], True, st["accent_dark"],
                cn=FONTS["head"])
        p = r.cells[1].paragraphs[0]
        spacing(p, 0, 0, line=1.4)
        add_rich(p, it["definition"], SIZES["body"], BRAND["ink"])
    gap(ctx, 10)


def faq(ctx, b):
    st = ctx.style
    for it in b["items"]:
        for key, fill, text, color, bold in (("faq_q", st["accent"], it["q"], st["deep"], True),
                                             ("faq_a", st["deep_mid"], it["a"], BRAND["ink"], False)):
            p = ctx.doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.9)
            badge = set_run(p.add_run(" %s " % L(key)), SIZES["small"], True, BRAND["white"], cn=FONTS["head"])
            _shade_run(badge, fill)
            set_run(p.add_run("　"), SIZES["body"])
            add_rich(p, text, SIZES["body"], color, bold, cn=FONTS["head"] if bold else None)
            if key == "faq_q":
                p.paragraph_format.keep_with_next = True
                spacing(p, 8, 3)
            else:
                spacing(p, 0, 6, line=1.45)


def _shade_run(run, fill):
    """给一个 run 加底色（问/答徽标、步骤编号）。shd 须放在 rPr 中 vertAlign/lang 等之前。"""
    from docx.oxml.ns import qn
    from docx_helpers import el
    rpr = run._element.get_or_add_rPr()
    for old in rpr.findall(qn("w:shd")):
        rpr.remove(old)
    shd = el("w:shd", val="clear", color="auto", fill=fill)
    for tag in ("fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout"):
        anchor = rpr.find(qn("w:" + tag))
        if anchor is not None:
            anchor.addprevious(shd)
            return
    rpr.append(shd)


def checklist(ctx, b):
    st = ctx.style
    items = b["items"]
    has_note = any(isinstance(i, dict) and i.get("note") for i in items)
    widths = [0.8, ctx.text_width_cm - 0.8 - (5.0 if has_note else 0) - 1.6, 1.6]
    if has_note:
        widths.append(5.0)
    t = ctx.doc.add_table(rows=len(items), cols=len(widths))
    table_layout(t, widths)
    table_borders(t, st["table_line"], 4, inside_h=True, outer=False)
    table_cell_margins(t, 75, 75, 90, 90)
    for i, (r, it) in enumerate(zip(t.rows, items)):
        row_flags(r)
        if i == 0:
            for c in r.cells:
                cell_borders(c, top=("single", 8, st["table_head_line"]))
        it = {"text": it} if isinstance(it, str) else it
        for c in r.cells:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_run(r.cells[0].paragraphs[0].add_run(G("box")), 12, False, st["accent"])
        add_rich(r.cells[1].paragraphs[0], it["text"], SIZES["body"], BRAND["ink"])
        required = it.get("required", True)
        pc = r.cells[2].paragraphs[0]
        pc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(pc.add_run(L("required") if required else L("optional")), SIZES["footer"], True,
                st["accent_dark"] if required else BRAND["muted"])
        if has_note:
            add_rich(r.cells[3].paragraphs[0], it.get("note", ""), SIZES["small"], BRAND["ink_soft"])
    gap(ctx, 10)


def signoff(ctx, b):
    st = ctx.style
    roles = b.get("roles") or L("signoff_roles")
    cols = L("signoff_cols")
    t = ctx.doc.add_table(rows=1 + len(roles), cols=len(cols))
    table_layout(t, fit_widths([2.4, 3.6, 2.8, 4.4, 3.2], ctx.text_width_cm))
    table_borders(t, st["table_line"], 4, inside_h=True, inside_v=True, outer=True)
    for i, n in enumerate(cols):
        c = t.rows[0].cells[i]
        shade(c, st["table_head_bg"] if st["table_head_bg"] != BRAND["white"] else BRAND["bg_soft"])
        set_run(c.paragraphs[0].add_run(n), SIZES["small"], True,
                st["table_head_fg"] if st["table_style"] != "filled" else BRAND["white"], cn=FONTS["head"])
    for r, role in zip(t.rows[1:], roles):
        r.height = Cm(1.2)
        r.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row_flags(r)
        r.cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_run(r.cells[0].paragraphs[0].add_run(role), SIZES["body"], True, BRAND["ink"])
    gap(ctx, 10)


def revisions(ctx, b):
    table(ctx, {"columns": L("revision_cols"),
                "rows": [[i["version"], i["date"], i.get("author", ""), i["change"]]
                         for i in b["items"]],
                "widths": [1.8, 2.8, 2.4, ctx.text_width_cm - 7.0],
                "first_col_bold": False,
                "caption": b.get("caption")})


def contact(ctx, b):
    st = ctx.style
    items = b["items"]
    n = min(len(items), 3)
    rows = (len(items) + n - 1) // n
    t = ctx.doc.add_table(rows=rows, cols=n)
    w = ctx.text_width_cm / n
    table_layout(t, [w] * n)
    no_borders(t)
    for i, it in enumerate(items):
        c = t.rows[i // n].cells[i % n]
        shade(c, st["card_bg"])
        cell_borders(c, top=("single", 12, st["accent"]), left=("single", 24, BRAND["white"]),
                     right=("single", 24, BRAND["white"]), bottom=None)
        cell_margins(c, 130, 130, 170, 160)
        p = c.paragraphs[0]
        set_run(p.add_run(it["label"]), SIZES["small"], False, st["deep_mid"])
        p2 = c.add_paragraph()
        spacing(p2, 2, 0)
        add_rich(p2, it["value"], 12, st["deep"], True)
        if it.get("desc"):
            p3 = c.add_paragraph()
            add_rich(p3, it["desc"], SIZES["footer"], BRAND["ink_soft"])
    gap(ctx, 10)


REGISTRY = {
    "heading": heading, "paragraph": paragraph, "lead": lead, "bullets": bullets,
    "numbered": numbered, "callout": callout, "quote": quote, "note": note,
    "page_break": page_break, "table": table, "glossary": glossary, "faq": faq,
    "checklist": checklist, "signoff": signoff, "revisions": revisions, "contact": contact,
    "facts": facts, "exec_summary": exec_summary,
}
