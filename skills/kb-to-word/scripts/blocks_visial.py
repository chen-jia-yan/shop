# -*- coding: utf-8 -*-
"""
图示与数据类元素（9 种）：
  kpi 数据卡片 / flow 流程图 / timeline 时间线 / structure 产品责任结构图 /
  matrix 四象限矩阵 / compare 对比卡片 / steps 纵向步骤 / chart 数据图表（8 种）/ image 图片
流程图、时间线、矩阵、卡片用 Word 原生表格绘制：清晰、可编辑、打印不失真；
数据图表和结构图用 matplotlib 生成 200dpi 图片。
"""
import os

from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

import charts
from blocks_basic import caption, gap, source_line
from docx_helpers import (add_rich, cell_borders, cell_margins, no_borders, row_flags, set_run,
                          shade, spacing, table_layout)
from themes import BRAND, FONTS, SIZES


def _trend_color(delta, good="up"):
    """▲/+ 视为上升，▼/- 视为下降；good 指明“上升是好事”还是“下降是好事”（如赔付率）。"""
    d = str(delta or "").strip()
    if not d:
        return BRAND["muted"]
    up = d[0] in "▲+↑"
    down = d[0] in "▼-↓"
    if not (up or down):
        return BRAND["muted"]
    positive = up if good == "up" else down
    return BRAND["teal"] if positive else BRAND["red"]


def kpi(ctx, b):
    items = b["items"]
    n = len(items)
    st = ctx.style
    t = ctx.doc.add_table(rows=1, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [ctx.text_width_cm / n] * n)
    no_borders(t)
    row_flags(t.rows[0])
    for c, it in zip(t.rows[0].cells, items):
        shade(c, st["kpi_bg"])
        cell_borders(c, top=("single", 24, st["kpi_bar"]), left=("single", 36, BRAND["white"]),
                     right=("single", 36, BRAND["white"]), bottom=None)
        cell_margins(c, 140, 140, 160, 120)
        p = c.paragraphs[0]
        set_run(p.add_run(str(it["value"])), SIZES["kpi"], True, BRAND["ink"], FONTS["num"])
        if it.get("unit"):
            set_run(p.add_run(" " + it["unit"]), SIZES["small"], True, BRAND["ink_soft"])
        spacing(p, 0, 0, line=1.0)
        p2 = c.add_paragraph()
        set_run(p2.add_run(it["label"]), SIZES["kpi_label"], False, BRAND["ink_soft"])
        spacing(p2, 2, 0)
        if it.get("delta"):
            p3 = c.add_paragraph()
            set_run(p3.add_run(str(it["delta"])), SIZES["kpi_label"], True,
                    _trend_color(it["delta"], it.get("good", "up")))
            if it.get("delta_label"):
                set_run(p3.add_run(" " + it["delta_label"]), SIZES["footer"], False, BRAND["muted"])
            spacing(p3, 1, 0)
    source_line(ctx, b.get("source"))
    gap(ctx, 8)


def flow(ctx, b):
    """横向流程：步骤 + 箭头，超过 per_row 个自动换行；highlight 为需要强调的步骤序号（从 1 起）。"""
    steps = b["steps"]
    per = int(b.get("per_row", 4))
    hi = set(b.get("highlight", []) if isinstance(b.get("highlight"), list) else
             [b["highlight"]] if b.get("highlight") else [])
    arrow_w = 0.6
    step_w = (ctx.text_width_cm - arrow_w * (per - 1)) / per
    widths = []
    for i in range(per):
        widths.append(step_w)
        if i < per - 1:
            widths.append(arrow_w)
    chunks = [steps[i:i + per] for i in range(0, len(steps), per)]
    t = ctx.doc.add_table(rows=len(chunks) * 2 - 1, cols=len(widths))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, widths)
    no_borders(t)
    idx = 0
    for ri, chunk in enumerate(chunks):
        row = t.rows[ri * 2]
        row_flags(row)
        for j in range(per):
            c = row.cells[j * 2]
            if j >= len(chunk):
                continue
            idx += 1
            s = chunk[j]
            s = {"title": s} if isinstance(s, str) else s
            on = idx in hi
            shade(c, BRAND["orange"] if on else ctx.style["kpi_bg"])
            cell_borders(c, top=("single", 18, BRAND["orange"] if not on else BRAND["orange_dark"]))
            cell_margins(c, 110, 110, 120, 100)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            p = c.paragraphs[0]
            set_run(p.add_run("%02d" % idx), 13, True,
                    BRAND["white"] if on else BRAND["orange"], FONTS["num"])
            p2 = c.add_paragraph()
            add_rich(p2, s["title"], SIZES["body"], BRAND["white"] if on else BRAND["ink"], True)
            spacing(p2, 2, 0)
            if s.get("desc"):
                p3 = c.add_paragraph()
                add_rich(p3, s["desc"], SIZES["footer"] + 0.5,
                         BRAND["white"] if on else BRAND["ink_soft"])
                spacing(p3, 1, 0, line=1.2)
            if j < len(chunk) - 1:
                a = row.cells[j * 2 + 1]
                a.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                pa = a.paragraphs[0]
                pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
                set_run(pa.add_run("›"), 20, True, BRAND["orange"])
        if ri < len(chunks) - 1:
            sep = t.rows[ri * 2 + 1]
            sep.height = Cm(0.55)
            sep.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            c = sep.cells[len(widths) - 1]
            pa = c.paragraphs[0]
            pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
            spacing(pa, 0, 0, exact=14)
            set_run(pa.add_run("↓"), 11, True, BRAND["orange"])
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))
    gap(ctx, 6)


def timeline(ctx, b):
    """时间线：current 之前为已完成（实色），current 高亮，之后为未来（浅色）。"""
    nodes = b["nodes"]
    n = len(nodes)
    cur = b.get("current")
    t = ctx.doc.add_table(rows=3, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [ctx.text_width_cm / n] * n)
    no_borders(t)
    t.rows[1].height = Cm(0.32)
    t.rows[1].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    for i, nd in enumerate(nodes):
        state = "done" if cur is None or i < cur else ("now" if i == cur else "future")
        color = {"done": BRAND["orange"], "now": BRAND["green"], "future": "E6E8EA"}[state]
        top = t.rows[0].cells[i]
        p = top.paragraphs[0]
        set_run(p.add_run(nd["time"]), SIZES["small"] + 0.5, True,
                BRAND["muted"] if state == "future" else (BRAND["green"] if state == "now"
                                                          else BRAND["orange_dark"]))
        if state == "now":
            set_run(p.add_run("  ● 当前"), SIZES["footer"], True, BRAND["green"])
        bar = t.rows[1].cells[i]
        shade(bar, color)
        cell_borders(bar, left=("single", 12, BRAND["white"]), right=("single", 12, BRAND["white"]))
        sp = bar.paragraphs[0]
        spacing(sp, 0, 0, exact=2)
        low = t.rows[2].cells[i]
        cell_margins(low, 80, 40, 100, 100)
        p2 = low.paragraphs[0]
        add_rich(p2, nd["title"], SIZES["body"],
                 BRAND["muted"] if state == "future" else BRAND["ink"], True)
        if nd.get("desc"):
            p3 = low.add_paragraph()
            add_rich(p3, nd["desc"], SIZES["footer"] + 0.5, BRAND["ink_soft"])
            spacing(p3, 1, 0, line=1.2)
    for r in t.rows:
        row_flags(r)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 6)


def structure(ctx, b):
    path = os.path.join(ctx.tmp, charts.safe_name(b.get("root"), len(os.listdir(ctx.tmp))))
    charts.render_structure(b, path)
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm))
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def matrix(ctx, b):
    """四象限矩阵（如风险评估）。quadrants 顺序：左上、右上、左下、右下。"""
    q = b["quadrants"]
    fills = b.get("fills") or [BRAND["yellow_light"], BRAND["red_light"],
                               BRAND["teal_light"], BRAND["yellow_light"]]
    bars = [ "D69E2E", BRAND["red"], BRAND["teal"], "D69E2E"]
    axis_w = 1.0
    cw = (ctx.text_width_cm - axis_w) / 2
    t = ctx.doc.add_table(rows=3, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [axis_w, cw, cw])
    no_borders(t)
    # 纵轴标签（合并左列两格）
    ycell = t.cell(0, 0).merge(t.cell(1, 0))
    ycell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    yp = ycell.paragraphs[0]
    yp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(yp.add_run("\n".join(b.get("y_label", "影响程度")) + "\n↑"), SIZES["small"], True,
            BRAND["muted"])
    for k, (r, c) in enumerate([(0, 1), (0, 2), (1, 1), (1, 2)]):
        cell = t.cell(r, c)
        shade(cell, fills[k])
        cell_borders(cell, top=("single", 18, bars[k]), left=("single", 24, BRAND["white"]),
                     right=("single", 24, BRAND["white"]), bottom=("single", 24, BRAND["white"]))
        cell_margins(cell, 120, 120, 160, 140)
        qd = q[k] if k < len(q) else {"title": "", "items": []}
        p = cell.paragraphs[0]
        set_run(p.add_run(qd["title"]), SIZES["body"], True, bars[k])
        for it in qd.get("items", []):
            pi = cell.add_paragraph()
            pi.paragraph_format.left_indent = Cm(0.35)
            pi.paragraph_format.first_line_indent = Cm(-0.35)
            set_run(pi.add_run("· "), SIZES["small"], True, bars[k])
            add_rich(pi, it, SIZES["small"] + 0.5, BRAND["ink"])
            spacing(pi, 1, 0)
        if qd.get("action"):
            pa = cell.add_paragraph()
            set_run(pa.add_run("应对：" + qd["action"]), SIZES["footer"] + 0.5, True,
                    BRAND["ink_soft"])
            spacing(pa, 4, 0)
    xcell = t.cell(2, 1).merge(t.cell(2, 2))
    xp = xcell.paragraphs[0]
    xp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(xp.add_run(b.get("x_label", "发生可能性") + "  →"), SIZES["small"], True, BRAND["muted"])
    for r in t.rows:
        row_flags(r)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 6)


def compare(ctx, b):
    """对比卡片：2-4 个方案/产品并排，highlight=true 的卡片作为推荐项。"""
    cards = b["cards"]
    n = len(cards)
    t = ctx.doc.add_table(rows=1, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [ctx.text_width_cm / n] * n)
    no_borders(t)
    row_flags(t.rows[0])
    for c, cd in zip(t.rows[0].cells, cards):
        on = cd.get("highlight")
        shade(c, BRAND["orange_pale"] if on else BRAND["bg_soft"])
        cell_borders(c, top=("single", 30 if on else 12, BRAND["orange"] if on else BRAND["muted"]),
                     left=("single", 36, BRAND["white"]), right=("single", 36, BRAND["white"]))
        cell_margins(c, 140, 140, 160, 140)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        p = c.paragraphs[0]
        if cd.get("tag") or on:
            set_run(p.add_run(cd.get("tag") or "推荐"), SIZES["footer"], True,
                    BRAND["orange_dark"] if on else BRAND["muted"])
            p = c.add_paragraph()
        set_run(p.add_run(cd["title"]), 12, True, BRAND["ink"])
        if cd.get("subtitle"):
            ps = c.add_paragraph()
            add_rich(ps, cd["subtitle"], SIZES["small"], BRAND["ink_soft"])
        for pt in cd.get("points", []):
            pp = c.add_paragraph()
            pp.paragraph_format.left_indent = Cm(0.4)
            pp.paragraph_format.first_line_indent = Cm(-0.4)
            set_run(pp.add_run("✓ "), SIZES["small"], True, BRAND["teal"] if on else BRAND["muted"])
            add_rich(pp, pt, SIZES["small"] + 0.5, BRAND["ink"])
            spacing(pp, 2, 0)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 8)


def steps(ctx, b):
    """纵向步骤：适合办理流程（每步可带负责人、时限、所需材料）。"""
    items = b["items"]
    t = ctx.doc.add_table(rows=len(items), cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [1.3, ctx.text_width_cm - 1.3])
    no_borders(t)
    for i, (r, it) in enumerate(zip(t.rows, items), 1):
        row_flags(r)
        nc = r.cells[0]
        nc.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        cell_margins(nc, 60, 60, 0, 0)
        cell_borders(nc, right=("single", 12, BRAND["orange"]) if i < len(items) else None)
        pn = nc.paragraphs[0]
        pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(pn.add_run(" %d " % i), 11, True, BRAND["white"], FONTS["num"])
        _shade_run(pn.runs[-1], BRAND["orange"])
        bc = r.cells[1]
        cell_margins(bc, 40, 200, 200, 80)
        p = bc.paragraphs[0]
        add_rich(p, it["title"], SIZES["body"] + 0.5, BRAND["ink"], True)
        meta = [x for x in (it.get("owner") and "负责：" + it["owner"],
                            it.get("time") and "时限：" + it["time"]) if x]
        if meta:
            set_run(p.add_run("　" + "　".join(meta)), SIZES["footer"] + 0.5, False,
                    BRAND["orange_dark"])
        if it.get("desc"):
            p2 = bc.add_paragraph()
            add_rich(p2, it["desc"], SIZES["small"] + 0.5, BRAND["ink_soft"])
            spacing(p2, 2, 0, line=1.3)
    gap(ctx, 8)


def _shade_run(run, fill):
    from docx.oxml.ns import qn
    from docx_helpers import el
    rpr = run._element.get_or_add_rPr()
    for old in rpr.findall(qn("w:shd")):
        rpr.remove(old)
    rpr.append(el("w:shd", val="clear", color="auto", fill=fill))


def chart(ctx, b):
    path = os.path.join(ctx.tmp, charts.safe_name(b.get("caption", "chart"), len(os.listdir(ctx.tmp))))
    h = b.get("height_in", 3.0 if b.get("chart") not in ("donut", "pie") else 2.6)
    charts.render_chart(b, path, width_in=6.3, height_in=h)
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm))
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def image(ctx, b):
    path = b["path"]
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    if not os.path.exists(path):
        p = ctx.doc.add_paragraph()
        add_rich(p, "【待补充：图片 %s 未找到】" % b["path"], SIZES["small"])
        return
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm * 0.8))
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def _picture(ctx, path, width_cm):
    p = ctx.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    spacing(p, 4, 0)
    p.add_run().add_picture(path, width=Cm(min(width_cm, ctx.text_width_cm)))


REGISTRY = {
    "kpi": kpi, "flow": flow, "timeline": timeline, "structure": structure, "matrix": matrix,
    "compare": compare, "steps": steps, "chart": chart, "image": image,
}
