# -*- coding: utf-8 -*-
"""
数据与卡片类元素（8 种）：
  kpis 数据卡片 / bars 进度条 / gauge 环形仪表 / icon_grid 图标卡片 / compare 对比（VS）/
  venn 交集 / table 表格 / chart 原生图表（柱、条、堆叠、折线、面积、饼、环形）
签名同 diagrams_flow：fn(slide, t, seq, box, d)
"""
import math
import re

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.oxml.ns import qn
from pptx.util import Pt

from diagrams_flow import _icon, card
from icons import draw_icon, icon_badge
from ppt_base import BRAND, I, fit_size, fmt_num, line, rgb, ring_segment, shape, shape_text, text
from ppt_theme import CONF, FONTS, G, L as label, palette


def _delta_color(delta, good="up"):
    s = str(delta or "").strip()
    if not s:
        return BRAND["muted"]
    up, down = s[0] in "▲+↑", s[0] in "▼-−↓"
    if not (up or down):
        return BRAND["muted"]
    return BRAND["teal"] if (up if good == "up" else down) else BRAND["red"]


# ---------------- 1. 数据卡片 ----------------
def kpis(slide, t, seq, box, d):
    """每张卡可加一种辅助图：trend 迷你趋势线 / progress 进度环（0-1）/ bench 基准条 {value, mark, label}。"""
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    gap = 0.25
    cw = (w - gap * (n - 1)) / n
    extra = any(k.get("trend") or k.get("progress") is not None or k.get("bench") for k in items)
    ch = min(h, 3.5 if extra else 2.6)
    cy = y + (h - ch) / 2
    used = set()
    for i, k in enumerate(items):
        cx = x + i * (cw + gap)
        hero = k.get("highlight", False)
        alert = k.get("alert", False)
        seq.begin()
        card(slide, cx, cy, cw, ch, t, fill=t["primary"] if hero else t["card"])
        shape(slide, "rect", cx, cy, cw, 0.07, fill=t["accent"] if hero else (BRAND["red"] if alert else t["primary"]))
        ic = k.get("icon") or _icon({"title": k["label"]}, used)
        used.add(ic)
        icon_badge(slide, ic, cx + 0.28, cy + 0.32, 0.62, BRAND["white"] if hero else (BRAND["red_light"] if alert else t["soft2"]),
                   BRAND["red"] if alert and not hero else t["primary"])
        fg = BRAND["white"] if hero else BRAND["ink"]
        vs = fit_size([str(k["value"]) + " " * 2], cw - 0.6, 0.9, 44, 24)
        tb = text(slide, cx + 0.28, cy + 1.02, cw - 0.5, 0.9,
                  [{"text": str(k["value"]), "size": vs, "bold": True, "color": fg, "en": FONTS["num"]}], vs, anchor="bottom")
        if k.get("unit"):
            par = tb.text_frame.paragraphs[0]
            from ppt_base import set_font
            r = par.add_run()
            set_font(r, vs * 0.38, True, fg if hero else BRAND["ink_soft"])
            r.text = " " + k["unit"]
        text(slide, cx + 0.28, cy + 1.95, cw - 0.5, 0.32, k["label"], 13, BRAND["white"] if hero else BRAND["ink_soft"],
             min_size=10)
        if k.get("delta"):
            col = _delta_color(k["delta"], k.get("good", "up"))
            text(slide, cx + 0.28, cy + 2.22, cw - 0.5, 0.3,
                 [{"text": str(k["delta"]) + ("  " + k["delta_label"] if k.get("delta_label") else ""),
                   "bold": True, "color": (BRAND["accent"] if hero else col)}], 12, en=FONTS["num"])
        ex, ey, ew, eh = cx + 0.28, cy + 2.62, cw - 0.56, ch - 2.8
        main = BRAND["white"] if hero else t["primary"]
        if k.get("trend"):
            vals = [float(v) for v in k["trend"]]
            lo, hi = min(vals), max(vals)
            sp = (hi - lo) or 1.0
            pts = [(ex + ew * j / float(max(len(vals) - 1, 1)), ey + eh - 0.06 - (v - lo) / sp * (eh - 0.16))
                   for j, v in enumerate(vals)]
            from ppt_base import polyline
            polyline(slide, pts, main, 2.0)
            shape(slide, "oval", pts[-1][0] - 0.07, pts[-1][1] - 0.07, 0.14, 0.14, fill=main)
        elif k.get("progress") is not None:
            p = max(0.0, min(1.0, float(k["progress"])))
            r = min(0.36, eh / 2)
            rcx, rcy = ex + ew - r, ey + eh / 2
            ring_segment(slide, rcx, rcy, r, r * 0.7, 90, -270, BRAND["white"] if hero else t["soft2"],
                         alpha=0.35 if hero else None)
            if p > 0:
                ring_segment(slide, rcx, rcy, r, r * 0.7, 90, 90 - 360 * min(p, 0.999), main)
            if k.get("progress_label"):
                text(slide, ex, ey, ew - 2 * r - 0.1, eh, k["progress_label"], 10.5, BRAND["white"] if hero else BRAND["ink_soft"],
                     anchor="middle", min_size=8.5)
        elif k.get("bench"):
            b = k["bench"]
            ty = ey + 0.12
            shape(slide, "round", ex, ty, ew, 0.13, fill=t["soft2"], radius=0.5)
            shape(slide, "round", ex, ty, max(0.06, ew * min(1.0, float(b["value"]))), 0.13,
                  fill=BRAND["red"] if alert else t["bar_fill"], radius=0.5)
            if b.get("mark") is not None:
                mx = ex + ew * min(1.0, float(b["mark"]))
                shape(slide, "rect", mx - 0.02, ty - 0.08, 0.04, 0.29, fill=BRAND["red"])
            if b.get("label"):
                text(slide, ex, ty + 0.22, ew, 0.3, b["label"], 10.5, BRAND["white"] if hero else BRAND["ink_soft"], min_size=8.5)
        seq.end("float")


# ---------------- 2. 进度条 ----------------
def bars(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    mx = d.get("max") or max([1.0] + [float(i["value"]) for i in items])
    row = min(0.85, h / n)
    lw = min(3.0, w * 0.28)
    bw = w - lw - 1.2
    for i, it in enumerate(items):
        ry = y + i * row + (h - row * n) / 2
        on = it.get("highlight", False)
        seq.begin()
        text(slide, x, ry, lw, row, it["label"], 14, BRAND["ink"], it.get("bold", on), anchor="middle", min_size=10)
        shape(slide, "round", x + lw, ry + row * 0.32, bw, row * 0.36, fill=BRAND["bg_soft"], radius=0.5)
        frac = max(0.02, min(1.0, float(it["value"]) / mx))
        shape(slide, "round", x + lw, ry + row * 0.32, bw * frac, row * 0.36,
              fill=t["primary"] if on or i == 0 and d.get("highlight_first", True) else t["bar_fill"],
              radius=0.5)
        if it.get("target") is not None:
            tx = x + lw + bw * min(1.0, float(it["target"]) / mx)
            line(slide, tx, ry + row * 0.2, tx, ry + row * 0.8, BRAND["red"], 1.5)
        text(slide, x + lw + bw + 0.15, ry, 1.05, row, [{"text": it.get("display", str(it["value"])), "bold": True,
                                                         "color": t["primary"] if on else BRAND["ink"], "en": FONTS["num"]}],
             15, anchor="middle")
        seq.end("wipe")


# ---------------- 3. 环形仪表 ----------------
def gauge(slide, t, seq, box, d):
    x, y, w, h = box
    r = min(w, h) / 2 * 0.92
    cx, cy = x + w / 2, y + h / 2 + r * 0.08
    v = max(0.0, min(1.0, float(d["value"])))
    seq.begin()
    ring_segment(slide, cx, cy, r, r * 0.78, 225, -45, BRAND["bg_soft"])
    seq.end("fade")
    seq.begin()
    ring_segment(slide, cx, cy, r, r * 0.78, 225, 225 - 270 * v, t["primary"])
    if d.get("target") is not None:
        a = math.radians(225 - 270 * float(d["target"]))
        line(slide, cx + r * 0.72 * math.cos(a), cy - r * 0.72 * math.sin(a), cx + r * 1.05 * math.cos(a),
             cy - r * 1.05 * math.sin(a), BRAND["red"], 2)
    seq.end("wipe")
    seq.begin()
    text(slide, cx - r * 0.7, cy - r * 0.42, r * 1.4, r * 0.6,
         [{"text": d.get("display", "%.0f%%" % (v * 100)), "bold": True, "color": BRAND["ink"], "en": FONTS["num"]}],
         fit_size([d.get("display", "100%")], r * 1.3, r * 0.55, 54, 20), align="center", anchor="middle")
    text(slide, cx - r * 0.75, cy + r * 0.16, r * 1.5, r * 0.5,
         [{"text": d.get("label", ""), "bold": True, "color": t["title"]},
          {"text": d.get("sub", ""), "size": 11, "color": BRAND["muted"]}], 14, align="center", min_size=9)
    seq.end("fade")


# ---------------- 4. 图标卡片 ----------------
def icon_grid(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    cols = {1: 1, 2: 2, 3: 3, 4: 4, 5: 3, 6: 3, 7: 4, 8: 4}.get(n, 4)
    rows = int(math.ceil(n / float(cols)))
    gx, gy = 0.25, 0.25
    cw = (w - gx * (cols - 1)) / cols
    chh = (h - gy * (rows - 1)) / rows
    style = d.get("style", "card")       # card 卡片 / plain 无底
    used = set()
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        if r == rows - 1 and n % cols:   # 最后一行居中
            off = (cols - n % cols) * (cw + gx) / 2
        else:
            off = 0
        cx = x + off + c * (cw + gx)
        cy = y + r * (chh + gy)
        on = it.get("highlight", False)
        seq.begin()
        if style == "card":
            card(slide, cx, cy, cw, chh, t, fill=t["primary"] if on else t["card"])
        ic = _icon(it, used)
        used.add(ic)
        d_icon = min(0.78, chh * 0.32)
        icon_badge(slide, ic, cx + 0.3, cy + 0.3, d_icon, BRAND["white"] if on else t["soft2"], t["primary"],
                   kind="round")
        fg = BRAND["white"] if on else t["title"]
        paras = [{"text": it["title"], "size": 16, "bold": True, "color": fg}]
        if it.get("desc"):
            paras.append({"text": it["desc"], "size": 12, "color": BRAND["white"] if on else BRAND["ink_soft"],
                          "numbers": True, "accent": BRAND["accent"] if on else t["primary"]})
        text(slide, cx + 0.3, cy + 0.3 + d_icon + 0.18, cw - 0.55, chh - d_icon - 0.6, paras, 14, min_size=9,
             spacing=1.2, where="图标卡片“%s”" % it["title"])
        if it.get("tag"):
            tg = shape(slide, "round", cx + cw - 1.15, cy + 0.32, 0.9, 0.3, fill=t["accent"], radius=0.5)
            shape_text(tg, it["tag"], 10, BRAND["ink"], True)
        seq.end("float")


# ---------------- 5. 对比 VS ----------------
def compare(slide, t, seq, box, d):
    x, y, w, h = box
    gap = 0.6
    cw = (w - gap) / 2
    sides = [d["left"], d["right"]]
    for i, sd in enumerate(sides):
        cx = x + i * (cw + gap)
        good = i == 1
        seq.begin()
        card(slide, cx, y, cw, h, t, fill=t["soft"] if good else BRAND["bg_soft"],
             line_color=t["primary"] if good else BRAND["line"], shadow=good)
        hdr = shape(slide, "round_top", cx, y, cw, 0.7, fill=t["primary"] if good else BRAND["grey_mid"], radius=0.18)
        shape_text(hdr, sd["title"], 18, BRAND["white"], True)
        iy = y + 0.95
        rows = sd.get("items", [])
        rh = min(0.75, (h - 1.15) / max(len(rows), 1))
        for it in rows:
            draw_icon(slide, "check" if good else "warning", cx + 0.3, iy + (rh - 0.32) / 2, 0.32,
                      t["primary"] if good else BRAND["grey_mid"], t["soft"] if good else BRAND["bg_soft"])
            text(slide, cx + 0.78, iy, cw - 1.0, rh, it, 13.5, BRAND["ink"] if good else BRAND["ink_soft"],
                 anchor="middle", min_size=9.5, numbers=good, accent=t["primary"])
            iy += rh
        seq.end("float")
    seq.begin()
    vs = shape(slide, "oval", x + cw + gap / 2 - 0.42, y + h / 2 - 0.42, 0.84, 0.84, fill=t["accent"], line=BRAND["white"],
               line_w=3, shadow=True)
    shape_text(vs, d.get("vs", "VS"), 16, BRAND["ink"], True)
    seq.end("zoom")


# ---------------- 6. 交集 ----------------
def venn(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    pal = [t["primary"], t["secondary"], BRAND["primary_mid"]]
    r = min(h * 0.42, w * 0.2)
    cx, cy = x + w / 2, y + h / 2
    if n == 2:
        centers = [(cx - r * 0.62, cy), (cx + r * 0.62, cy)]
    else:
        centers = [(cx - r * 0.6, cy + r * 0.38), (cx + r * 0.6, cy + r * 0.38), (cx, cy - r * 0.62)]
    for i, (it, (ox, oy)) in enumerate(zip(items, centers)):
        seq.begin()
        shape(slide, "oval", ox - r, oy - r, 2 * r, 2 * r, fill=pal[i], alpha=0.55)
        dx = (ox - cx) * 1.25
        dy = (oy - cy) * 1.25
        lx = ox + dx - r * 0.55
        text(slide, lx, oy + dy - 0.5, r * 1.1, 1.0,
             [{"text": it["title"], "bold": True, "size": 15, "color": BRAND["white"]},
              {"text": it.get("desc", ""), "size": 11, "color": BRAND["white"]}], 13, align="center", anchor="middle",
             min_size=9)
        seq.end("zoom")
    if d.get("center"):
        seq.begin()
        c = shape(slide, "round", cx - 0.75, cy - 0.22 + (0 if n == 2 else 0.12), 1.5, 0.44, fill=BRAND["white"], radius=0.5,
                  shadow=True)
        shape_text(c, d["center"], 12, t["title"], True)
        seq.end("fade")


# ---------------- 7. 表格 ----------------
def table(slide, t, seq, box, d):
    x, y, w, h = box
    cols = d["columns"]
    rows = d["rows"]
    nr, nc = len(rows) + 1, len(cols)
    rh = min(0.55, h / nr)
    seq.begin()
    gf = slide.shapes.add_table(nr, nc, I(x), I(y), I(w), I(rh * nr))
    tb = gf.table
    widths = d.get("widths") or [1.0] * nc
    tot = float(sum(widths))
    for j, cw in enumerate(widths):
        tb.columns[j].width = I(w * cw / tot)
    hi = d.get("highlight_col")
    for i in range(nr):
        tb.rows[i].height = I(rh)
        for j in range(nc):
            cell = tb.cell(i, j)
            v = cols[j] if i == 0 else (rows[i - 1][j] if j < len(rows[i - 1]) else "")
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = rgb(t["primary"] if j != hi else t["secondary"])
            elif hi is not None and j == hi:
                cell.fill.fore_color.rgb = rgb(t["soft2"])
            else:
                cell.fill.fore_color.rgb = rgb(t["soft"] if i % 2 == 0 else BRAND["white"])
            cell.margin_left = cell.margin_right = I(0.12)
            cell.margin_top = cell.margin_bottom = I(0.04)
            tf = cell.text_frame
            tf.word_wrap = True
            par = tf.paragraphs[0]
            from ppt_base import _runs
            from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            num = isinstance(v, (int, float)) or (isinstance(v, str) and re.match(r"^[+\-−]?\d", v) is not None and j > 0)
            par.alignment = PP_ALIGN.RIGHT if num and i > 0 else (PP_ALIGN.CENTER if i == 0 else PP_ALIGN.LEFT)
            _runs(par, v, d.get("size", 13 if nr <= 7 else 11.5), BRAND["white"] if i == 0 else BRAND["ink"],
                  i == 0 or j == 0 or j == hi, None, False)
    seq.end("fade")
    if d.get("source"):
        text(slide, x, y + rh * nr + 0.08, w, 0.3, label("source") + d["source"], 9.5, BRAND["muted"])


# ---------------- 8. 原生图表 ----------------
CHART_TYPES = {"col": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
               "stacked": XL_CHART_TYPE.COLUMN_STACKED, "line": XL_CHART_TYPE.LINE_MARKERS,
               "area": XL_CHART_TYPE.AREA, "pie": XL_CHART_TYPE.PIE, "donut": XL_CHART_TYPE.DOUGHNUT}


def chart(slide, t, seq, box, d):
    x, y, w, h = box
    kind = d.get("chart", "col")
    cats = d["categories"]
    series = d["series"]
    pal = palette(t)
    cd = CategoryChartData()
    cd.categories = cats
    for s in series:
        cd.add_series(s["name"], s["values"], d.get("number_format"))
    seq.begin()
    gf = slide.shapes.add_chart(CHART_TYPES[kind], I(x), I(y), I(w), I(h), cd)
    ch = gf.chart
    ch.font.size = Pt(CONF.size(12))
    ch.font.name = FONTS["cn"]
    ch.font.color.rgb = rgb(BRAND["ink_soft"])
    plot = ch.plots[0]
    round_ = kind in ("pie", "donut")
    ch.has_legend = round_ or len(series) > 1
    if ch.has_legend:
        ch.legend.position = XL_LEGEND_POSITION.RIGHT if round_ else XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(CONF.size(12))
    if round_:
        plot.vary_by_categories = True
        for i, pt in enumerate(plot.series[0].points):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(pal[i % len(pal)])
            pt.format.line.color.rgb = rgb(BRAND["white"])
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.show_percentage = True
        dl.show_value = False
        dl.number_format = "0%"
        dl.number_format_is_linked = False
        dl.font.size = Pt(CONF.size(12))
        dl.font.bold = True
        dl.font.color.rgb = rgb(BRAND["white"])
        if kind == "donut":
            hs = plot._element.find(qn("c:holeSize"))
            if hs is not None:
                hs.set("val", "62")
    else:
        try:
            plot.gap_width = 70
            if kind == "stacked":
                plot.overlap = 100
        except AttributeError:
            pass
        hi = d.get("highlight")
        alert_i = _alert_index(d, cats, series)
        if alert_i is not None:
            d["_alert_name"] = cats[alert_i]
        emph = (hi is not None or alert_i is not None) and len(series) == 1
        alert_col = t["highlight"] if t["highlight"] != t["primary"] else BRAND["red"]
        for si, s in enumerate(plot.series):
            col = pal[si % len(pal)]
            if kind in ("line",):
                s.format.line.color.rgb = rgb(col)
                s.format.line.width = Pt(2.75)
                s.smooth = False
                s.marker.style = XL_MARKER_STYLE.CIRCLE
                s.marker.size = 8
                s.marker.format.fill.solid()
                s.marker.format.fill.fore_color.rgb = rgb(BRAND["white"])
                s.marker.format.line.color.rgb = rgb(col)
                if emph and alert_i is not None:
                    p = s.points[alert_i]
                    p.marker.format.fill.solid()
                    p.marker.format.fill.fore_color.rgb = rgb(alert_col)
                    p.marker.format.line.color.rgb = rgb(alert_col)
            else:
                s.format.fill.solid()
                s.format.fill.fore_color.rgb = rgb(BRAND["grey_bar"] if emph else col)
                if emph:
                    idx = cats.index(hi) if hi in cats else (s.values.index(max(s.values)) if hi == "max" else None)
                    if idx is not None:
                        p = s.points[idx]
                        p.format.fill.solid()
                        p.format.fill.fore_color.rgb = rgb(t["primary"])
                    if alert_i is not None:
                        p = s.points[alert_i]
                        p.format.fill.solid()
                        p.format.fill.fore_color.rgb = rgb(alert_col)
        if d.get("labels", True):
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.font.size = Pt(CONF.size(11.5))
            dl.font.color.rgb = rgb(BRAND["ink_soft"])
            if d.get("number_format"):
                dl.number_format = d["number_format"]
                dl.number_format_is_linked = False
            try:
                dl.position = XL_LABEL_POSITION.OUTSIDE_END if kind in ("col", "bar") else \
                    (XL_LABEL_POSITION.CENTER if kind == "stacked" else XL_LABEL_POSITION.ABOVE)
            except Exception:       # noqa: BLE001  部分图表类型不支持指定位置
                pass
        va = ch.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb(BRAND["bg_grey"])
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(CONF.size(11))
        va.tick_labels.font.color.rgb = rgb(BRAND["muted"])
        if d.get("labels", True) and kind in ("col", "bar"):
            va.visible = False
        ca = ch.category_axis
        ca.format.line.color.rgb = rgb(BRAND["line"])
        ca.tick_labels.font.size = Pt(CONF.size(12))
        ca.has_major_gridlines = False
        if kind == "bar":
            ca.reverse_order = True
        if kind in ("col", "bar", "line") and (d.get("target") is not None or d.get("callout")):
            _annotate(slide, t, ch, (x, y, w, h), d, kind, cats, series, alert_i, alert_col)
    seq.end("fade")


# ---------------- 图表智能标注：目标线、异常项、标注框 ----------------
def _alert_index(d, cats, series):
    """alert：分类名，或 "auto"（有目标时取低于目标的最低项，没有目标时取最低项；good: "down" 时反过来取最高项）。"""
    a = d.get("alert")
    if a is None or len(series) != 1:
        return None
    if a != "auto":
        return cats.index(a) if a in cats else None
    vals = [float(v) for v in series[0]["values"]]
    down = d.get("good") == "down"
    tg = d.get("target")
    if tg is not None:
        bad = [i for i, v in enumerate(vals) if (v > tg if down else v < tg)]
        if not bad:
            return None
        return max(bad, key=lambda i: vals[i]) if down else min(bad, key=lambda i: vals[i])
    return vals.index(max(vals) if down else min(vals))


def _manual_layout(ch, lx, ly, lw, lh):
    """把绘图区固定在图表框内的指定比例位置，便于在图表上精确叠加目标线和标注。"""
    from lxml import etree
    pa = ch._chartSpace.chart.plotArea
    old = pa.find(qn("c:layout"))
    if old is not None:
        pa.remove(old)
    lay = etree.SubElement(pa, qn("c:layout"))
    pa.remove(lay)
    pa.insert(0, lay)
    ml = etree.SubElement(lay, qn("c:manualLayout"))
    for tag, val in (("c:layoutTarget", "inner"), ("c:xMode", "edge"), ("c:yMode", "edge"),
                     ("c:x", lx), ("c:y", ly), ("c:w", lw), ("c:h", lh)):
        etree.SubElement(ml, qn(tag)).set("val", str(val))


def _annotate(slide, t, ch, box, d, kind, cats, series, alert_i, alert_col):
    x, y, w, h = box
    nf = d.get("number_format")
    vals = [float(v) for s in series for v in s["values"]]
    tg = d.get("target")
    vmin = float(d.get("axis_min", 0))
    vmax = float(d.get("axis_max") or max(vals + ([tg] if tg is not None else [])) * 1.18)
    va = ch.value_axis
    va.minimum_scale, va.maximum_scale = vmin, vmax
    legend = len(series) > 1
    if kind == "bar":
        lx, ly, lw, lh = 0.16, 0.03, 0.8, 0.86 if legend else 0.94
    else:
        lx, ly, lw, lh = 0.03, 0.08, 0.94, 0.72 if legend else 0.8
    _manual_layout(ch, lx, ly, lw, lh)
    frac = lambda v: (float(v) - vmin) / ((vmax - vmin) or 1.0)
    n = len(cats)
    if tg is not None:
        tl = label("target_line", v=fmt_num(tg, nf))
        if kind == "bar":
            tx = x + w * (lx + lw * frac(tg))
            line(slide, tx, y + h * ly, tx, y + h * (ly + lh), BRAND["red"], 1.5, "dash")
            text(slide, tx + 0.05, y + h * ly - 0.05, 1.6, 0.26, tl, 9.5, BRAND["red"], True)
        else:
            ty = y + h * (ly + lh * (1 - frac(tg)))
            line(slide, x + w * lx, ty, x + w * (lx + lw), ty, BRAND["red"], 1.5, "dash")
            text(slide, x + w * (lx + lw) - 1.6, ty - 0.3, 1.6, 0.26, tl, 9.5, BRAND["red"], True, align="right")
    c = d.get("callout")
    if c and alert_i is not None:
        v = float(series[0]["values"][alert_i])
        if c == "auto":
            if tg is not None:
                gap = abs(tg - v)
                gs = ("%.1fpct" % (gap * 100)) if nf and "%" in nf else fmt_num(gap, nf)
                c = label("gap_callout", name=cats[alert_i], value=fmt_num(v, nf), gap=gs)
            else:
                c = "%s %s" % (cats[alert_i], fmt_num(v, nf))
        bw = min(3.2, 0.3 + 0.14 * len(c))
        if kind == "bar":
            cy = y + h * (ly + lh * (alert_i + 0.5) / n)
            bx = min(x + w - bw, x + w * (lx + lw * frac(v)) + 0.55)
            by = cy - 0.19
        else:
            cxp = x + w * (lx + lw * (alert_i + 0.5) / n)
            top = y + h * (ly + lh * (1 - frac(v)))
            bx = max(x, min(x + w - bw, cxp - bw / 2))
            by = max(y, top - 0.95)
            shape(slide, "triangle", cxp - 0.08, by + 0.38, 0.16, 0.1, fill=BRAND["ink"], rotation=180)
        tag = shape(slide, "round", bx, by, bw, 0.38, fill=BRAND["ink"], radius=0.25)
        shape_text(tag, c, 10.5, BRAND["white"], True)
        tag.name = "tap_callout"


REGISTRY = {"kpis": kpis, "bars": bars, "gauge": gauge, "icon_grid": icon_grid, "compare": compare,
            "venn": venn, "table": table, "chart": chart}
