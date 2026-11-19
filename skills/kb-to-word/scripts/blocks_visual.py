# -*- coding: utf-8 -*-
"""
图示与数据类元素（10 种）：
  kpi 数据卡片 / flow 流程图 / timeline 时间线 / structure 产品责任结构图 /
  matrix 四象限矩阵 / compare 对比卡片 / steps 纵向步骤 / progress 进度条（目标达成）/
  chart 数据图表（8 种）/ image 图片
流程图、时间线、矩阵、卡片、进度条用 Word 原生表格绘制：清晰、可编辑、打印不失真；
数据图表和结构图用 matplotlib 生成 200dpi 图片。颜色全部取自当前风格（ctx.style）。
"""
import os

from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

import charts
from blocks_basic import _shade_run, caption, gap, source_line
from docx_helpers import (add_rich, cell_borders, cell_margins, mark_size, no_borders, row_flags,
                          set_run, shade, spacing, table_layout)
from themes import BRAND, FONTS, SIZES, G, L, R


def _trend_color(st, delta, good="up"):
    """▲/+ 视为上升，▼/- 视为下降；good 指明“上升是好事”还是“下降是好事”（如赔付率）。"""
    d = str(delta or "").strip()
    if not d:
        return BRAND["muted"]
    up = d[0] in "▲+↑"
    down = d[0] in "▼-−↓"
    if not (up or down):
        return BRAND["muted"]
    positive = up if good == "up" else down
    return st["good"] if positive else st["bad"]


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
        on = it.get("highlight")
        shade(c, st["kpi_bg"])
        cell_borders(c, top=("single", 24 if on else 12, st["kpi_bar"] if on else st["accent_light"]),
                     left=("single", 36, BRAND["white"]), right=("single", 36, BRAND["white"]), bottom=None)
        cell_margins(c, 150, 150, 170, 120)
        p0 = c.paragraphs[0]
        set_run(p0.add_run(it["label"]), SIZES["kpi_label"], False, st["deep_mid"], cn=FONTS["head"])
        spacing(p0, 0, 2)
        p = c.add_paragraph()
        set_run(p.add_run(str(it["value"])), SIZES["kpi"], True, st["kpi_value"], FONTS["num"])
        if it.get("unit"):
            set_run(p.add_run(" " + it["unit"]), SIZES["small"], True, st["deep_mid"])
        spacing(p, 0, 0, line=1.0)
        if it.get("delta"):
            p3 = c.add_paragraph()
            set_run(p3.add_run(str(it["delta"])), SIZES["kpi_label"], True,
                    _trend_color(st, it["delta"], it.get("good", "up")), FONTS["num"])
            if it.get("delta_label"):
                set_run(p3.add_run(" " + it["delta_label"]), SIZES["footer"], False, BRAND["muted"])
            spacing(p3, 3, 0)
        if it.get("note"):
            p4 = c.add_paragraph()
            add_rich(p4, it["note"], SIZES["footer"], BRAND["ink_soft"])
            spacing(p4, 2, 0, line=1.2)
    source_line(ctx, b.get("source"))
    gap(ctx, 10)


def flow(ctx, b):
    """横向流程：步骤 + 箭头，超过 per_row 个自动换行；highlight 为需要强调的步骤序号（从 1 起）。"""
    st = ctx.style
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
            shade(c, st["accent"] if on else st["card_bg"])
            cell_borders(c, top=("single", 18, st["accent_dark"] if on else st["accent"]))
            cell_margins(c, 120, 120, 130, 110)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            p = c.paragraphs[0]
            set_run(p.add_run("%02d" % idx), 13, True, BRAND["white"] if on else st["accent"], FONTS["num"])
            p2 = c.add_paragraph()
            add_rich(p2, s["title"], SIZES["body"], BRAND["white"] if on else st["deep"], True, cn=FONTS["head"])
            spacing(p2, 2, 0)
            if s.get("desc"):
                p3 = c.add_paragraph()
                add_rich(p3, s["desc"], SIZES["footer"] + 0.5, BRAND["white"] if on else BRAND["ink_soft"])
                spacing(p3, 2, 0, line=1.25)
            if j < len(chunk) - 1:
                a = row.cells[j * 2 + 1]
                a.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                pa = a.paragraphs[0]
                pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
                set_run(pa.add_run(G("arrow_right")), 20, True, st["accent_light"])
        if ri < len(chunks) - 1:
            sep = t.rows[ri * 2 + 1]
            sep.height = Cm(0.55)
            sep.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            c = sep.cells[len(widths) - 1]
            pa = c.paragraphs[0]
            pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
            spacing(pa, 0, 0, exact=14)
            set_run(pa.add_run(G("arrow_down")), 11, True, st["accent_light"])
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))
    gap(ctx, 8)


def timeline(ctx, b):
    """时间线：current 之前为已完成（实色），current 高亮，之后为未来（浅色）。"""
    st = ctx.style
    nodes = b["nodes"]
    n = len(nodes)
    cur = b.get("current")
    t = ctx.doc.add_table(rows=3, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [ctx.text_width_cm / n] * n)
    no_borders(t)
    t.rows[1].height = Cm(0.28)
    t.rows[1].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    for i, nd in enumerate(nodes):
        state = "done" if cur is None or i < cur else ("now" if i == cur else "future")
        color = {"done": st["accent"], "now": st["deep"], "future": BRAND["grey_future"]}[state]
        top = t.rows[0].cells[i]
        cell_margins(top, 40, 60, 100, 100)
        p = top.paragraphs[0]
        set_run(p.add_run(nd["time"]), SIZES["small"] + 0.5, True,
                BRAND["muted"] if state == "future" else (st["deep"] if state == "now" else st["accent_dark"]),
                FONTS["num"])
        if state == "now":
            set_run(p.add_run(L("now_tag")), SIZES["footer"], True, st["deep"])
        bar = t.rows[1].cells[i]
        shade(bar, color)
        cell_borders(bar, left=("single", 12, BRAND["white"]), right=("single", 12, BRAND["white"]))
        sp = bar.paragraphs[0]
        spacing(sp, 0, 0, exact=2)
        low = t.rows[2].cells[i]
        cell_margins(low, 90, 40, 100, 100)
        p2 = low.paragraphs[0]
        add_rich(p2, nd["title"], SIZES["body"], BRAND["muted"] if state == "future" else st["deep"], True,
                 cn=FONTS["head"])
        if nd.get("desc"):
            p3 = low.add_paragraph()
            add_rich(p3, nd["desc"], SIZES["footer"] + 0.5, BRAND["ink_soft"])
            spacing(p3, 2, 0, line=1.25)
    for r in t.rows:
        row_flags(r)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 8)


def structure(ctx, b):
    path = os.path.join(ctx.tmp, charts.safe_name(b.get("root"), len(os.listdir(ctx.tmp))))
    charts.render_structure(b, path)
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm))
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def matrix(ctx, b):
    """四象限矩阵（如风险评估）。quadrants 顺序：左上、右上、左下、右下。"""
    q = b["quadrants"]
    fills = b.get("fills") or [BRAND["accent_light"], BRAND["red_light"],
                               BRAND["teal_light"], BRAND["accent_light"]]
    bars = [BRAND["warn"], BRAND["red"], BRAND["teal"], BRAND["warn"]]
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
    set_run(yp.add_run("\n".join(b.get("y_label", L("y_label"))) + "\n" + G("arrow_up")), SIZES["small"], True,
            BRAND["muted"])
    for k, (r, c) in enumerate([(0, 1), (0, 2), (1, 1), (1, 2)]):
        cell = t.cell(r, c)
        shade(cell, fills[k])
        cell_borders(cell, top=("single", 18, bars[k]), left=("single", 24, BRAND["white"]),
                     right=("single", 24, BRAND["white"]), bottom=("single", 24, BRAND["white"]))
        cell_margins(cell, 130, 130, 170, 150)
        qd = q[k] if k < len(q) else {"title": "", "items": []}
        p = cell.paragraphs[0]
        set_run(p.add_run(qd["title"]), SIZES["body"], True, bars[k], cn=FONTS["head"])
        for it in qd.get("items", []):
            pi = cell.add_paragraph()
            pi.paragraph_format.left_indent = Cm(0.35)
            pi.paragraph_format.first_line_indent = Cm(-0.35)
            set_run(pi.add_run(G("dot") + " "), SIZES["small"], True, bars[k])
            add_rich(pi, it, SIZES["small"] + 0.5, BRAND["ink"])
            spacing(pi, 2, 0)
        if qd.get("action"):
            pa = cell.add_paragraph()
            set_run(pa.add_run(L("action_prefix") + qd["action"]), SIZES["footer"] + 0.5, True,
                    BRAND["ink_soft"])
            spacing(pa, 4, 0)
    xcell = t.cell(2, 1).merge(t.cell(2, 2))
    xp = xcell.paragraphs[0]
    xp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(xp.add_run(b.get("x_label", L("x_label")) + "  " + G("arrow")), SIZES["small"], True, BRAND["muted"])
    for r in t.rows:
        row_flags(r)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 8)


def compare(ctx, b):
    """对比卡片：2-4 个方案/产品并排，highlight=true 的卡片作为推荐项。"""
    st = ctx.style
    cards = b["cards"]
    n = len(cards)
    t = ctx.doc.add_table(rows=1, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [ctx.text_width_cm / n] * n)
    no_borders(t)
    row_flags(t.rows[0])
    for c, cd in zip(t.rows[0].cells, cards):
        on = cd.get("highlight")
        shade(c, st["accent_pale"] if on else BRAND["bg_soft"])
        cell_borders(c, top=("single", 24 if on else 12, st["accent"] if on else BRAND["grey_bar"]),
                     left=("single", 36, BRAND["white"]), right=("single", 36, BRAND["white"]))
        cell_margins(c, 150, 150, 170, 150)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        p = c.paragraphs[0]
        if cd.get("tag") or on:
            set_run(p.add_run(cd.get("tag") or L("recommend")), SIZES["footer"], True,
                    st["accent_dark"] if on else BRAND["muted"], cn=FONTS["head"])
            p = c.add_paragraph()
        set_run(p.add_run(cd["title"]), 12, True, st["deep"], cn=FONTS["head"])
        if cd.get("subtitle"):
            ps = c.add_paragraph()
            add_rich(ps, cd["subtitle"], SIZES["small"], BRAND["ink_soft"])
            spacing(ps, 2, 2)
        for pt in cd.get("points", []):
            pp = c.add_paragraph()
            pp.paragraph_format.left_indent = Cm(0.4)
            pp.paragraph_format.first_line_indent = Cm(-0.4)
            set_run(pp.add_run(G("tick") + " "), SIZES["small"], True, st["accent"] if on else BRAND["muted"])
            add_rich(pp, pt, SIZES["small"] + 0.5, BRAND["ink"])
            spacing(pp, 3, 0, line=1.3)
    caption(ctx, "fig", b.get("caption"))
    gap(ctx, 10)


def steps(ctx, b):
    """纵向步骤：适合办理流程（每步可带负责人、时限、所需材料）。"""
    st = ctx.style
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
        cell_borders(nc, right=("single", 8, st["accent_light"]) if i < len(items) else None)
        pn = nc.paragraphs[0]
        pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(pn.add_run(" %d " % i), 11, True, BRAND["white"], FONTS["num"])
        _shade_run(pn.runs[-1], st["accent"])
        bc = r.cells[1]
        cell_margins(bc, 40, 220, 200, 80)
        p = bc.paragraphs[0]
        add_rich(p, it["title"], SIZES["body"] + 0.5, st["deep"], True, cn=FONTS["head"])
        meta = [x for x in (it.get("owner") and L("owner_prefix") + it["owner"],
                            it.get("time") and L("due_prefix") + it["time"]) if x]
        if meta:
            set_run(p.add_run("　" + "　".join(meta)), SIZES["footer"] + 0.5, False, st["accent_dark"])
        if it.get("desc"):
            p2 = bc.add_paragraph()
            add_rich(p2, it["desc"], SIZES["small"] + 0.5, BRAND["ink_soft"])
            spacing(p2, 3, 0, line=1.4)
    gap(ctx, 10)


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _bar(cell, width, ratio, target, fill, empty):
    """在单元格里画一根条形：嵌一个 1 行表格，按“数值 / 目标”切成 2-3 段；目标处画一条深色竖线。"""
    ratio = max(0.0, min(ratio, 1.0))
    cuts = sorted({ratio, 1.0} | ({max(0.0, min(target, 1.0))} if target is not None else set()))
    cuts = [c for c in cuts if c > 0.005]
    segs, prev = [], 0.0
    for c in cuts:
        segs.append((prev, c))
        prev = c
    inner = cell.add_table(rows=1, cols=len(segs))
    table_layout(inner, [max(width * (b - a), 0.05) for a, b in segs])
    no_borders(inner)
    ir = inner.rows[0]
    ir.height = Cm(0.32)
    ir.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    for (a, b), ic in zip(segs, ir.cells):
        shade(ic, fill if b <= ratio + 1e-9 else empty)
        if target is not None and abs(b - target) < 1e-9 and b < 1.0:
            cell_borders(ic, right=("single", 12, BRAND["ink"]))
        mark_size(ic.paragraphs[0], 1)


def progress(ctx, b):
    """进度条：每行“名称 | 条形 | 数值”，低于目标的用警示色。value / target / max 同一单位（如 %）。"""
    st = ctx.style
    items = b["items"]
    unit = b.get("unit", "")
    vals = [_num(it["value"]) or 0 for it in items]
    vmax = float(b.get("max") or max(vals + [_num(b.get("target")) or 0, 1]) * 1.08)
    has_note = any(it.get("note") for it in items)
    lw, vw, nw = 2.6, 2.2, (4.2 if has_note else 0)
    bw = ctx.text_width_cm - lw - vw - nw
    caption(ctx, "fig", b.get("caption"), above=True)
    t = ctx.doc.add_table(rows=len(items), cols=4 if has_note else 3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_layout(t, [lw, bw, vw] + ([nw] if has_note else []))
    no_borders(t)
    for r, it, v in zip(t.rows, items, vals):
        row_flags(r)
        target = _num(it.get("target", b.get("target")))
        below = target is not None and v < target
        for c in r.cells:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell_margins(c, 70, 70, 60, 60)
        set_run(r.cells[0].paragraphs[0].add_run(it["label"]), SIZES["body"], True, st["deep"], cn=FONTS["head"])
        bc = r.cells[1]
        mark_size(bc.paragraphs[0], 1)
        _bar(bc, bw - 0.25, v / vmax, None if target is None else target / vmax,
             st["bad"] if below else st["accent"], st["accent_pale"])
        mark_size(bc.paragraphs[-1], 1)
        pv = r.cells[2].paragraphs[0]
        pv.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        set_run(pv.add_run(str(it.get("display", it["value"])) + ("" if str(it["value"]).endswith(unit) else unit)),
                SIZES["body"], True, st["bad"] if below else st["deep"], FONTS["num"])
        if has_note:
            add_rich(r.cells[3].paragraphs[0], it.get("note", ""), SIZES["footer"] + 0.5, BRAND["ink_soft"])
    tg = b.get("target")
    if tg is not None:
        p = ctx.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        set_run(p.add_run("▏" + L("progress_target", v=str(tg) + unit)), SIZES["footer"], False, BRAND["muted"])
        spacing(p, 2, 0)
    source_line(ctx, b.get("source"))
    gap(ctx, 8)


def chart(ctx, b):
    path = os.path.join(ctx.tmp, charts.safe_name(b.get("caption", "chart"), len(os.listdir(ctx.tmp))))
    h = b.get("height_in", 3.0 if b.get("chart") not in ("donut", "pie") else 2.6)
    charts.render_chart(b, path, width_in=6.3, height_in=h)
    caption_above = b.get("caption_above", False)
    if caption_above:
        caption(ctx, "fig", b.get("caption"), above=True)
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm))
    if not caption_above:
        caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def image(ctx, b):
    path = b["path"]
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    if not os.path.exists(path):
        p = ctx.doc.add_paragraph()
        add_rich(p, L("image_missing", path=b["path"]), SIZES["small"])
        return
    _picture(ctx, path, b.get("width_cm", ctx.text_width_cm * 0.8))
    caption(ctx, "fig", b.get("caption"))
    source_line(ctx, b.get("source"))


def _picture(ctx, path, width_cm):
    p = ctx.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    spacing(p, 6, 0)
    p.add_run().add_picture(path, width=Cm(min(width_cm, ctx.text_width_cm)))


REGISTRY = {
    "kpi": kpi, "flow": flow, "timeline": timeline, "structure": structure, "matrix": matrix,
    "compare": compare, "steps": steps, "progress": progress, "chart": chart, "image": image,
}
