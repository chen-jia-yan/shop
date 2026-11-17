#!/usr/bin/env python3
"""根据 JSON 内容生成完整版式的 PPT（16:9）。

用法:
    python build_pptx.py deck.json output.pptx [--theme business|tech|china]

内容格式见 reference/slide-types.md。
依赖: python-pptx  (pip install python-pptx)
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-pptx，请先执行: pip install python-pptx")

# ---------------------------------------------------------------- 设计参数

FONT = "微软雅黑"
W, H = 13.333, 7.5          # 16:9，英寸
M = 0.6                     # 左右边距
CONTENT_TOP = 1.6
CONTENT_BOTTOM = 6.75

THEMES = {
    "business": {"name": "商务蓝", "primary": "1F3864", "secondary": "2E75B6", "accent": "F4A259",
                 "light": "EEF3FA", "muted": "8497B0", "text": "262626", "sub": "595959",
                 "palette": ["1F3864", "2E75B6", "F4A259", "8FAADC", "70AD47"]},
    "tech":     {"name": "科技青", "primary": "0B3C5D", "secondary": "0FA3B1", "accent": "F7B32B",
                 "light": "E8F6F7", "muted": "7FA7B5", "text": "1E2A32", "sub": "4F5D66",
                 "palette": ["0B3C5D", "0FA3B1", "F7B32B", "7FD1D8", "E15554"]},
    "china":    {"name": "中国红", "primary": "8B1A1A", "secondary": "C0392B", "accent": "D4A017",
                 "light": "FBEFEA", "muted": "B08A84", "text": "2B2B2B", "sub": "5C4B48",
                 "palette": ["8B1A1A", "C0392B", "D4A017", "E59866", "7F8C8D"]},
}
WARN = "E36C09"             # 【待补充】文字颜色
WHITE = "FFFFFF"
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
PLACEHOLDER = "【待补充"

# 内容密度上限：超出时输出警告
LIMITS = {"bullets": 6, "bullet_chars": 40, "sub": 3, "column_items": 5, "table_rows": 6, "table_cols": 5,
          "kpi": (2, 4), "kpi_value_chars": 6, "steps": (3, 6), "agenda": (2, 6), "quote_chars": 40,
          "insight": 4, "series": 3, "points": 4, "next_steps": 5}


# ---------------------------------------------------------------- 基础工具

def rgb(hex_):
    return RGBColor.from_string(hex_)


def is_wide(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F")


def text_width(text, size_pt):
    """估算文字宽度（英寸）：全角字符约 1 个字号宽，半角约 0.55 个字号宽。"""
    plain = BOLD_RE.sub(r"\1", str(text))
    return sum((1.0 if is_wide(c) else 0.55) * size_pt / 72 for c in plain)


def estimate_height(paras, width_in, scale, line_spacing):
    total = 0.0
    for p in paras:
        size = p["size"] * scale
        avail = max(width_in - p.get("indent", 0), 0.3)
        lines = max(1, math.ceil(text_width(p["text"], size) / avail))
        total += lines * size * line_spacing / 72 + p.get("space_after", 0) / 72
    return total


def set_ea_font(run):
    rpr = run._r.get_or_add_rPr()
    if rpr.find(qn("a:ea")) is None:
        ea = OxmlElement("a:ea")
        ea.set("typeface", FONT)
        rpr.append(ea)


def add_runs(paragraph, text, size, color, bold=False):
    """写入一段文字，支持 **加粗**；含【待补充】的片段标为橙色。"""
    text = str(text)
    pos, parts = 0, []
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], bold))
        parts.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], bold))
    for seg, b in parts or [("", bold)]:
        run = paragraph.add_run()
        run.text = seg
        run.font.size = Pt(size)
        run.font.bold = b
        run.font.color.rgb = rgb(WARN if PLACEHOLDER in seg else color)
        run.font.name = FONT
        set_ea_font(run)


def set_bullet(paragraph, char, color, indent_in):
    ppr = paragraph._p.get_or_add_pPr()
    ppr.set("marL", str(int(Inches(indent_in))))
    ppr.set("indent", str(-int(Inches(indent_in * 0.75))))
    bu_clr = OxmlElement("a:buClr")
    clr = OxmlElement("a:srgbClr")
    clr.set("val", color)
    bu_clr.append(clr)
    bu_font = OxmlElement("a:buFont")
    bu_font.set("typeface", "Arial")
    bu_char = OxmlElement("a:buChar")
    bu_char.set("char", char)
    for el in (bu_clr, bu_font, bu_char):
        ppr.append(el)


def no_line(shape):
    shape.line.fill.background()
    try:
        shape.shadow.inherit = False
    except AttributeError:
        pass


def rect(slide, x, y, w, h, color, kind=MSO_SHAPE.RECTANGLE, radius=None):
    shp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(color)
    no_line(shp)
    if radius is not None:
        try:
            shp.adjustments[0] = radius
        except IndexError:
            pass
    return shp


class Ctx:
    def __init__(self, meta, theme):
        self.meta, self.t = meta, theme
        self.page = 0
        self.section = 0
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(f"第 {self.page} 页：{msg}")


def text_box(ctx, slide, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             min_size=10, line_spacing=1.15, shape=None, margin=0.05, label="文字"):
    """放置文字。paras: [{text, size, color, bold, bullet, indent, space_after}]。放不下时等比缩小字号。"""
    if isinstance(paras, str):
        paras = [{"text": paras, "size": 18, "color": ctx.t["text"]}]
    if shape is not None:  # 文字写进已有形状时，以形状的实际尺寸为准
        w, h = shape.width / 914400, shape.height / 914400
    inner_w, inner_h = w - 2 * margin, h - 2 * margin
    scale = 1.0
    min_scale = min_size / max(p["size"] for p in paras)
    while scale > min_scale and estimate_height(paras, inner_w, scale, line_spacing) > inner_h:
        scale -= 0.05
    scale = max(scale, min_scale)
    if estimate_height(paras, inner_w, scale, line_spacing) > inner_h * 1.05:
        ctx.warn(f"{label}可能放不下，请精简内容")

    if shape is None:
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, Inches(margin))
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.line_spacing = line_spacing
        if p.get("space_after"):
            para.space_after = Pt(p["space_after"])
        if p.get("bullet"):
            set_bullet(para, p["bullet"], p.get("bullet_color", ctx.t["secondary"]), p.get("indent", 0.3))
        add_runs(para, p["text"], round(p["size"] * scale, 1), p.get("color", ctx.t["text"]), p.get("bold", False))
    return shape


def chrome(ctx, slide, title):
    """内容页通用元素：标题、标题下分隔线、页脚、页码。"""
    t = ctx.t
    rect(slide, M, 0.52, 0.12, 0.62, t["secondary"])
    text_box(ctx, slide, M + 0.28, 0.4, W - 2 * M - 0.28, 0.86,
             [{"text": title or "", "size": 26, "bold": True, "color": t["primary"]}],
             anchor=MSO_ANCHOR.MIDDLE, min_size=18, line_spacing=1.0, label="标题")
    rect(slide, M, 1.33, W - 2 * M, 0.02, t["light"])
    footer(ctx, slide)


def footer(ctx, slide, light=False):
    t = ctx.t
    color = t["light"] if light else t["muted"]
    left = "　".join(x for x in (ctx.meta.get("org"), ctx.meta.get("date")) if x)
    if left:
        text_box(ctx, slide, M, H - 0.5, 7, 0.32, [{"text": left, "size": 10, "color": color}],
                 anchor=MSO_ANCHOR.MIDDLE, min_size=8)
    text_box(ctx, slide, W - M - 1.2, H - 0.5, 1.2, 0.32,
             [{"text": str(ctx.page), "size": 11, "color": color, "bold": True}],
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, min_size=8)
    if not light:
        rect(slide, 0, H - 0.08, W, 0.08, t["primary"])


def bullet_paras(ctx, items, size=20, sub_size=16, color=None):
    t = ctx.t
    paras = []
    for it in items:
        text = it if isinstance(it, str) else it.get("text", "")
        paras.append({"text": text, "size": size, "color": color or t["text"], "bullet": "●",
                      "indent": 0.38, "space_after": 6 if (isinstance(it, dict) and it.get("sub")) else 12})
        if isinstance(it, dict):
            subs = it.get("sub", [])
            if len(subs) > LIMITS["sub"]:
                ctx.warn(f"二级要点超过 {LIMITS['sub']} 条")
            for j, s in enumerate(subs):
                paras.append({"text": s, "size": sub_size, "color": t["sub"], "bullet": "–",
                              "bullet_color": t["muted"], "indent": 0.75,
                              "space_after": 12 if j == len(subs) - 1 else 4})
        if len(BOLD_RE.sub(r"\1", text)) > LIMITS["bullet_chars"]:
            ctx.warn(f"要点超过 {LIMITS['bullet_chars']} 字：{text[:15]}…")
    return paras


def takeaway_bar(ctx, slide, text, y):
    t = ctx.t
    rect(slide, M, y, W - 2 * M, 0.72, t["light"])
    rect(slide, M, y, 0.1, 0.72, t["accent"])
    text_box(ctx, slide, M + 0.3, y, W - 2 * M - 0.4, 0.72,
             [{"text": text, "size": 17, "bold": True, "color": t["primary"]}],
             anchor=MSO_ANCHOR.MIDDLE, min_size=12, label="结论条")


def style_table(ctx, table, header, rows, highlight_col=None, size=14):
    t = ctx.t
    for c, h in enumerate(header):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(t["primary"])
        _cell_text(cell, h, size + 1, WHITE, True)
    for r, row in enumerate(rows, 1):
        for c in range(len(header)):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(t["light"] if r % 2 == 0 else WHITE)
            hl = highlight_col is not None and c == highlight_col
            _cell_text(cell, row[c] if c < len(row) else "", size,
                       t["secondary"] if hl else t["text"], hl)


def _cell_text(cell, text, size, color, bold):
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = cell.margin_right = Inches(0.12)
    cell.margin_top = cell.margin_bottom = Inches(0.05)
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    add_runs(p, text, size, color, bold)


def check_range(ctx, name, n, rng):
    lo, hi = rng
    if not lo <= n <= hi:
        ctx.warn(f"{name}数量为 {n}，建议 {lo}-{hi} 个")


# ---------------------------------------------------------------- 13 种版式

def s_cover(ctx, slide, s):
    t = ctx.t
    rect(slide, 0, 0, W, H, t["primary"])
    rect(slide, W - 4.6, -1.6, 6.4, 6.4, t["secondary"], MSO_SHAPE.OVAL)
    rect(slide, W - 2.6, H - 2.3, 1.9, 1.9, t["accent"], MSO_SHAPE.OVAL)
    rect(slide, 0, H - 0.18, W, 0.18, t["secondary"])
    if ctx.meta.get("org"):
        text_box(ctx, slide, M, 0.55, 8, 0.45, [{"text": ctx.meta["org"], "size": 13, "color": t["light"]}])
    rect(slide, M, 2.25, 1.3, 0.09, t["accent"])
    text_box(ctx, slide, M, 2.5, 8.4, 1.75,
             [{"text": s.get("title", ""), "size": 40, "bold": True, "color": WHITE}],
             min_size=26, line_spacing=1.1, label="封面标题")
    if s.get("subtitle"):
        text_box(ctx, slide, M, 4.3, 8.4, 0.8, [{"text": s["subtitle"], "size": 20, "color": t["light"]}],
                 min_size=14, label="副标题")
    info = [x for x in (s.get("presenter"), s.get("date") or ctx.meta.get("date")) if x]
    if info:
        text_box(ctx, slide, M, 5.5, 8, 0.9,
                 [{"text": x, "size": 15, "color": WHITE, "space_after": 4} for x in info], min_size=11)


def s_agenda(ctx, slide, s):
    t = ctx.t
    items = s.get("items", [])
    check_range(ctx, "目录项", len(items), LIMITS["agenda"])
    chrome(ctx, slide, s.get("title", "目录"))
    cols = 2 if len(items) > 4 else 1
    per_col = math.ceil(len(items) / cols) or 1
    col_w = (W - 2 * M - (cols - 1) * 0.6) / cols
    row_h = min(1.15, (CONTENT_BOTTOM - CONTENT_TOP - 0.2) / per_col)
    for i, item in enumerate(items):
        col, row = divmod(i, per_col)
        x = M + 0.3 + col * (col_w + 0.6)
        y = CONTENT_TOP + 0.35 + row * row_h
        num = rect(slide, x, y, 0.8, 0.8, t["secondary"] if i % 2 == 0 else t["primary"],
                   MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18)
        text_box(ctx, slide, 0, 0, 0.8, 0.8, [{"text": f"{i + 1:02d}", "size": 22, "bold": True, "color": WHITE}],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, shape=num, margin=0)
        text_box(ctx, slide, x + 1.05, y, col_w - 1.4, 0.8,
                 [{"text": item, "size": 22, "color": t["text"], "bold": True}],
                 anchor=MSO_ANCHOR.MIDDLE, min_size=14, label="目录项")
        rect(slide, x + 1.05, y + 0.92, col_w - 1.4, 0.015, t["light"])


def s_section(ctx, slide, s):
    t = ctx.t
    ctx.section += 1
    number = s.get("number") or f"{ctx.section:02d}"
    rect(slide, 0, 0, W * 0.4, H, t["primary"])
    rect(slide, W * 0.4 - 1.2, H - 1.6, 1.6, 1.6, t["secondary"], MSO_SHAPE.OVAL)
    text_box(ctx, slide, M, 1.9, W * 0.4 - M - 0.3, 2.4,
             [{"text": number, "size": 110, "bold": True, "color": t["accent"]}],
             anchor=MSO_ANCHOR.MIDDLE, min_size=60, line_spacing=1.0, label="章节号")
    text_box(ctx, slide, M, 4.3, 3, 0.4, [{"text": "PART", "size": 14, "bold": True, "color": t["light"]}])
    x = W * 0.4 + 0.9
    rect(slide, x, 2.55, 1.0, 0.08, t["accent"])
    text_box(ctx, slide, x, 2.8, W - x - M, 1.3,
             [{"text": s.get("title", ""), "size": 38, "bold": True, "color": t["primary"]}],
             min_size=24, line_spacing=1.1, label="章节标题")
    if s.get("subtitle"):
        text_box(ctx, slide, x, 4.15, W - x - M, 0.9, [{"text": s["subtitle"], "size": 18, "color": t["sub"]}],
                 min_size=12, label="章节副标题")
    text_box(ctx, slide, W - M - 1.2, H - 0.5, 1.2, 0.32,
             [{"text": str(ctx.page), "size": 11, "bold": True, "color": t["muted"]}],
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def s_bullets(ctx, slide, s):
    items = s.get("items", [])
    if len(items) > LIMITS["bullets"]:
        ctx.warn(f"要点超过 {LIMITS['bullets']} 条（{len(items)} 条），建议拆成两页")
    chrome(ctx, slide, s.get("title"))
    bottom = 5.85 if s.get("takeaway") else CONTENT_BOTTOM
    text_box(ctx, slide, M + 0.25, CONTENT_TOP + 0.15, W - 2 * M - 0.5, bottom - CONTENT_TOP - 0.25,
             bullet_paras(ctx, items), min_size=13, label="要点")
    if s.get("takeaway"):
        takeaway_bar(ctx, slide, s["takeaway"], 5.95)


def s_two_column(ctx, slide, s):
    t = ctx.t
    chrome(ctx, slide, s.get("title"))
    gap = 0.4
    col_w = (W - 2 * M - gap) / 2
    y, h = CONTENT_TOP + 0.15, CONTENT_BOTTOM - CONTENT_TOP - 0.2
    for i, key in enumerate(("left", "right")):
        col = s.get(key) or {}
        items = col.get("items", [])
        if len(items) > LIMITS["column_items"]:
            ctx.warn(f"{'左' if i == 0 else '右'}栏超过 {LIMITS['column_items']} 条")
        x = M + i * (col_w + gap)
        rect(slide, x, y, col_w, h, t["light"])
        band = rect(slide, x, y, col_w, 0.7, t["primary"] if i == 0 else t["secondary"])
        text_box(ctx, slide, 0, 0, 0, 0, [{"text": col.get("heading", ""), "size": 19, "bold": True, "color": WHITE}],
                 anchor=MSO_ANCHOR.MIDDLE, shape=band, margin=0.25, min_size=13)
        text_box(ctx, slide, x + 0.3, y + 0.9, col_w - 0.6, h - 1.1,
                 bullet_paras(ctx, items, size=17, sub_size=14), min_size=12, label="栏内要点")


def s_table(ctx, slide, s):
    header, rows = s.get("header", []), s.get("rows", [])
    if len(rows) > LIMITS["table_rows"]:
        ctx.warn(f"表格超过 {LIMITS['table_rows']} 行，建议放进 Excel 附件")
    if len(header) > LIMITS["table_cols"]:
        ctx.warn(f"表格超过 {LIMITS['table_cols']} 列")
    chrome(ctx, slide, s.get("title"))
    ncol = max(len(header), max((len(r) for r in rows), default=0)) or 1
    header = header + [""] * (ncol - len(header))
    row_h = 0.62
    total_h = min(row_h * (len(rows) + 1), CONTENT_BOTTOM - CONTENT_TOP - 0.6)
    gf = slide.shapes.add_table(len(rows) + 1, ncol, Inches(M), Inches(CONTENT_TOP + 0.2),
                                Inches(W - 2 * M), Inches(total_h))
    table = gf.table
    for c in range(ncol):
        table.columns[c].width = Inches((W - 2 * M) / ncol)
    size = 14 if len(rows) <= 5 else 12
    style_table(ctx, table, header, rows, s.get("highlight_col"), size=size)
    if s.get("note"):
        text_box(ctx, slide, M, CONTENT_BOTTOM - 0.35, W - 2 * M, 0.35,
                 [{"text": s["note"], "size": 11, "color": ctx.t["muted"]}], min_size=9)


def s_kpi(ctx, slide, s):
    t = ctx.t
    metrics = s.get("metrics", [])
    check_range(ctx, "数据卡片", len(metrics), LIMITS["kpi"])
    chrome(ctx, slide, s.get("title"))
    n = max(len(metrics), 1)
    gap = 0.35
    w = (W - 2 * M - (n - 1) * gap) / n
    y, h = CONTENT_TOP + 0.35, 3.5
    for i, m in enumerate(metrics):
        x = M + i * (w + gap)
        rect(slide, x, y, w, h, t["light"])
        rect(slide, x, y, w, 0.1, t["accent"] if i == 0 else t["secondary"])
        value = str(m.get("value", ""))
        if len(value) > LIMITS["kpi_value_chars"]:
            ctx.warn(f"数字“{value}”过长，建议不超过 {LIMITS['kpi_value_chars']} 个字符")
        text_box(ctx, slide, x + 0.15, y + 0.4, w - 0.3, 1.45,
                 [{"text": value, "size": 58, "bold": True, "color": t["primary"]}],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=30, line_spacing=1.0, label="指标数字")
        text_box(ctx, slide, x + 0.15, y + 1.95, w - 0.3, 0.55,
                 [{"text": m.get("label", ""), "size": 18, "bold": True, "color": t["text"]}],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=12, label="指标名称")
        if m.get("note"):
            text_box(ctx, slide, x + 0.25, y + 2.55, w - 0.5, 0.8,
                     [{"text": m["note"], "size": 13, "color": t["sub"]}],
                     align=PP_ALIGN.CENTER, min_size=10, label="指标说明")
    if s.get("takeaway"):
        takeaway_bar(ctx, slide, s["takeaway"], 5.85)


def s_timeline(ctx, slide, s):
    t = ctx.t
    events = s.get("events", [])
    check_range(ctx, "时间线节点", len(events), LIMITS["steps"])
    chrome(ctx, slide, s.get("title"))
    n = max(len(events), 1)
    current = s.get("current")
    step = (W - 2 * M) / n
    line_y = 3.75
    rect(slide, M + step / 2, line_y, step * (n - 1) if n > 1 else 0.01, 0.06, t["muted"])
    if current is not None and n > 1:
        rect(slide, M + step / 2, line_y, step * min(current, n - 1), 0.06, t["secondary"])
    for i, e in enumerate(events):
        cx = M + step * i + step / 2
        future = current is not None and i > current
        is_cur = current is not None and i == current
        d = 0.56 if is_cur else 0.4
        color = t["accent"] if is_cur else (t["light"] if future else t["secondary"])
        dot = rect(slide, cx - d / 2, line_y + 0.03 - d / 2, d, d, color, MSO_SHAPE.OVAL)
        if future:
            dot.line.color.rgb = rgb(t["muted"])
            dot.line.width = Pt(1.5)
        txt = t["muted"] if future else t["text"]
        text_box(ctx, slide, cx - step / 2 + 0.08, 2.55, step - 0.16, 0.75,
                 [{"text": e.get("date", ""), "size": 20, "bold": True,
                   "color": t["muted"] if future else t["primary"]}],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM, min_size=12, label="时间")
        text_box(ctx, slide, cx - step / 2 + 0.08, 4.35, step - 0.16, 0.6,
                 [{"text": e.get("title", ""), "size": 17, "bold": True, "color": txt}],
                 align=PP_ALIGN.CENTER, min_size=11, label="节点标题")
        if e.get("desc"):
            text_box(ctx, slide, cx - step / 2 + 0.12, 4.95, step - 0.24, 1.6,
                     [{"text": e["desc"], "size": 13, "color": t["muted"] if future else t["sub"]}],
                     align=PP_ALIGN.CENTER, min_size=10, label="节点说明")


def s_process(ctx, slide, s):
    t = ctx.t
    steps = s.get("steps", [])
    check_range(ctx, "流程步骤", len(steps), LIMITS["steps"])
    chrome(ctx, slide, s.get("title"))
    n = max(len(steps), 1)
    overlap = 0.15
    w = (W - 2 * M + overlap * (n - 1)) / n
    y, h = 2.2, 1.35
    for i, st in enumerate(steps):
        x = M + i * (w - overlap)
        kind = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
        shp = rect(slide, x, y, w, h, t["primary"] if i % 2 == 0 else t["secondary"], kind)
        text_box(ctx, slide, 0, 0, w, h,
                 [{"text": f"{i + 1:02d}", "size": 14, "bold": True, "color": t["accent"]},
                  {"text": st.get("title", ""), "size": 18, "bold": True, "color": WHITE}],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, shape=shp,
                 margin=0.45 if i else 0.25, min_size=11, line_spacing=1.05, label="步骤标题")
        if st.get("desc"):
            text_box(ctx, slide, x + 0.2, y + h + 0.3, w - 0.5, 2.2,
                     [{"text": st["desc"], "size": 15, "color": t["sub"]}],
                     align=PP_ALIGN.CENTER, min_size=11, label="步骤说明")


CHART_TYPES = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
               "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE}


def s_chart(ctx, slide, s):
    t = ctx.t
    chrome(ctx, slide, s.get("title"))
    ctype = s.get("chart_type", "column")
    cats = [str(c) for c in s.get("categories", [])]
    series = s.get("series", [])[:LIMITS["series"]]
    if len(s.get("series", [])) > LIMITS["series"]:
        ctx.warn(f"图表系列超过 {LIMITS['series']} 个，只画前 {LIMITS['series']} 个")
    if ctype == "pie":
        series = series[:1]

    data = CategoryChartData()
    data.categories = cats
    ok = bool(cats and series)
    all_int = True
    for se in series:
        vals = []
        for v in se.get("values", []):
            try:
                num = float(str(v).replace(",", ""))
                all_int &= num.is_integer()
                vals.append(num)
            except ValueError:
                ok = False
        if len(vals) != len(cats):
            ok = False
        data.add_series(se.get("name", ""), vals)

    insight = s.get("insight") or []
    chart_w = (W - 2 * M) * (0.6 if insight else 1.0)
    top = CONTENT_TOP + 0.1
    if s.get("unit"):
        text_box(ctx, slide, M, top, 3, 0.32, [{"text": f"单位：{s['unit']}", "size": 11, "color": t["muted"]}])
        top += 0.32
    if not ok:
        ctx.warn("图表数据不完整（分类与数值数量不一致或有非数字），未生成图表")
        text_box(ctx, slide, M, top + 1.5, chart_w, 1.0,
                 [{"text": "【待补充：图表数据不完整】", "size": 20, "color": WARN}], align=PP_ALIGN.CENTER)
    else:
        gf = slide.shapes.add_chart(CHART_TYPES.get(ctype, XL_CHART_TYPE.COLUMN_CLUSTERED),
                                    Inches(M), Inches(top), Inches(chart_w), Inches(CONTENT_BOTTOM - top - 0.1), data)
        ch = gf.chart
        ch.font.size = Pt(12)
        ch.font.name = FONT
        ch.font.color.rgb = rgb(t["sub"])
        plot = ch.plots[0]
        pal = t["palette"]
        if ctype == "pie":
            for j, pt in enumerate(plot.series[0].points):
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(pal[j % len(pal)])
        else:
            for j, se in enumerate(plot.series):
                color = rgb(pal[j % len(pal)])
                if ctype == "line":
                    se.format.line.color.rgb = color
                    se.format.line.width = Pt(2.75)
                    se.smooth = False
                    se.marker.format.fill.solid()
                    se.marker.format.fill.fore_color.rgb = color
                else:
                    se.format.fill.solid()
                    se.format.fill.fore_color.rgb = color
            if ctype in ("column", "bar"):
                plot.gap_width = 80
            va = ch.value_axis
            va.has_major_gridlines = True
            va.major_gridlines.format.line.color.rgb = rgb(t["light"])
            va.format.line.fill.background()
            va.tick_labels.font.size = Pt(11)
            ch.category_axis.tick_labels.font.size = Pt(12)
            ch.category_axis.format.line.color.rgb = rgb(t["muted"])
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size = Pt(11)
        dl.number_format_is_linked = False
        if ctype == "pie":
            dl.show_percentage = True
            dl.show_value = False
            dl.number_format = "0%"
        else:
            dl.show_value = True
            dl.number_format = "#,##0" if all_int else "#,##0.0"
        ch.has_legend = ctype == "pie" or len(series) > 1
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
            ch.legend.font.size = Pt(12)

    if insight:
        if len(insight) > LIMITS["insight"]:
            ctx.warn(f"图表解读超过 {LIMITS['insight']} 条")
        x = M + chart_w + 0.35
        w = W - M - x
        rect(slide, x, CONTENT_TOP + 0.1, w, CONTENT_BOTTOM - CONTENT_TOP - 0.2, t["light"])
        rect(slide, x, CONTENT_TOP + 0.1, w, 0.08, t["accent"])
        text_box(ctx, slide, x + 0.3, CONTENT_TOP + 0.35, w - 0.6, 0.5,
                 [{"text": "关键发现", "size": 18, "bold": True, "color": t["primary"]}])
        text_box(ctx, slide, x + 0.3, CONTENT_TOP + 1.0, w - 0.6, CONTENT_BOTTOM - CONTENT_TOP - 1.3,
                 bullet_paras(ctx, insight, size=16), min_size=11, label="图表解读")


def s_quote(ctx, slide, s):
    t = ctx.t
    rect(slide, 0, 0, W, H, t["light"])
    rect(slide, 0, 0, 0.25, H, t["primary"])
    text_box(ctx, slide, 1.2, 0.5, 2.5, 2.4, [{"text": "“", "size": 180, "bold": True, "color": t["secondary"]}],
             line_spacing=1.0, min_size=100)
    text = s.get("text", "")
    if len(text) > LIMITS["quote_chars"]:
        ctx.warn(f"金句超过 {LIMITS['quote_chars']} 字")
    text_box(ctx, slide, 1.8, 2.3, W - 3.6, 2.3,
             [{"text": text, "size": 38, "bold": True, "color": t["primary"]}],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=24, line_spacing=1.2, label="金句")
    rect(slide, W / 2 - 0.65, 4.85, 1.3, 0.08, t["accent"])
    if s.get("source"):
        text_box(ctx, slide, 1.8, 5.1, W - 3.6, 0.55, [{"text": s["source"], "size": 17, "color": t["sub"]}],
                 align=PP_ALIGN.CENTER, min_size=12)
    footer(ctx, slide)


def s_summary(ctx, slide, s):
    t = ctx.t
    chrome(ctx, slide, s.get("title", "总结与下一步"))
    points, steps = s.get("points", []), s.get("next_steps", [])
    if len(points) > LIMITS["points"]:
        ctx.warn(f"总结要点超过 {LIMITS['points']} 条")
    if len(steps) > LIMITS["next_steps"]:
        ctx.warn(f"下一步超过 {LIMITS['next_steps']} 条")
    both = bool(points and steps)
    left_w = 5.5 if both else W - 2 * M
    if points:
        text_box(ctx, slide, M, CONTENT_TOP + 0.1, left_w, 0.5,
                 [{"text": "核心结论", "size": 18, "bold": True, "color": t["primary"]}])
        row_h = min(1.1, (CONTENT_BOTTOM - CONTENT_TOP - 0.8) / max(len(points), 1))
        for i, p in enumerate(points):
            y = CONTENT_TOP + 0.8 + i * row_h
            dot = rect(slide, M, y + 0.05, 0.6, 0.6, t["secondary"], MSO_SHAPE.OVAL)
            text_box(ctx, slide, 0, 0, 0, 0, [{"text": str(i + 1), "size": 18, "bold": True, "color": WHITE}],
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, shape=dot, margin=0)
            text_box(ctx, slide, M + 0.85, y, left_w - 0.9, row_h - 0.1,
                     [{"text": p, "size": 18, "color": t["text"]}], anchor=MSO_ANCHOR.MIDDLE,
                     min_size=12, label="总结要点")
    if steps:
        x = M + left_w + 0.5 if both else M
        w = W - M - x
        text_box(ctx, slide, x, CONTENT_TOP + 0.1, w, 0.5,
                 [{"text": "下一步", "size": 18, "bold": True, "color": t["primary"]}])
        rows = [[st.get("action", ""), st.get("owner", ""), st.get("due", "")] for st in steps]
        gf = slide.shapes.add_table(len(rows) + 1, 3, Inches(x), Inches(CONTENT_TOP + 0.75),
                                    Inches(w), Inches(min(0.58 * (len(rows) + 1), 4.3)))
        tb = gf.table
        for c, ratio in enumerate((0.56, 0.22, 0.22)):
            tb.columns[c].width = Inches(w * ratio)
        style_table(ctx, tb, ["事项", "负责人", "时间"], rows, size=13)


def s_end(ctx, slide, s):
    t = ctx.t
    rect(slide, 0, 0, W, H, t["primary"])
    rect(slide, -1.8, H - 3.6, 5.2, 5.2, t["secondary"], MSO_SHAPE.OVAL)
    rect(slide, W - 2.4, 0.7, 1.4, 1.4, t["accent"], MSO_SHAPE.OVAL)
    text_box(ctx, slide, 1, 2.35, W - 2, 1.5, [{"text": s.get("title", "谢谢"), "size": 60, "bold": True, "color": WHITE}],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=36)
    rect(slide, W / 2 - 0.65, 3.95, 1.3, 0.08, t["accent"])
    if s.get("subtitle"):
        text_box(ctx, slide, 1, 4.2, W - 2, 0.7, [{"text": s["subtitle"], "size": 22, "color": t["light"]}],
                 align=PP_ALIGN.CENTER, min_size=14)
    if s.get("contact"):
        text_box(ctx, slide, 1, 5.1, W - 2, 0.5, [{"text": s["contact"], "size": 14, "color": t["light"]}],
                 align=PP_ALIGN.CENTER, min_size=10)


BUILDERS = {"cover": s_cover, "agenda": s_agenda, "section": s_section, "bullets": s_bullets,
            "two_column": s_two_column, "table": s_table, "kpi": s_kpi, "timeline": s_timeline,
            "process": s_process, "chart": s_chart, "quote": s_quote, "summary": s_summary, "end": s_end}


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="生成完整版式的 PPT")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--theme", choices=list(THEMES), help="覆盖 meta.theme")
    args = ap.parse_args()

    with open(args.content, encoding="utf-8") as f:
        deck = json.load(f)
    meta = deck.get("meta", {})
    theme_key = args.theme or meta.get("theme", "business")
    if theme_key not in THEMES:
        print(f"未知主题 {theme_key}，改用 business", file=sys.stderr)
        theme_key = "business"
    ctx = Ctx(meta, THEMES[theme_key])

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    prs.core_properties.title = meta.get("title", "")

    types = []
    for i, s in enumerate(deck.get("slides", []), 1):
        ctx.page = i
        kind = s.get("type")
        builder = BUILDERS.get(kind)
        if builder is None:
            ctx.warn(f"未知版式 {kind}，已跳过")
            continue
        slide = prs.slides.add_slide(blank)
        builder(ctx, slide, s)
        types.append(kind)
        if s.get("notes"):
            slide.notes_slide.notes_text_frame.text = s["notes"]
        elif kind not in ("cover", "end"):
            ctx.warn("没有演讲备注")

    for a, b, c in zip(types, types[1:], types[2:]):
        if a == b == c and a not in ("section",):
            ctx.warnings.append(f"连续 3 页以上使用 {a} 版式，建议换用其他版式")
            break

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(json.dumps({"output": str(out), "theme": THEMES[theme_key]["name"], "slides": len(types),
                      "layouts": types, "warnings": ctx.warnings}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
