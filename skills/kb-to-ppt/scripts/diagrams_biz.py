# -*- coding: utf-8 -*-
"""
保险业务与分析类图示（8 种）：
  waterfall 瀑布图（差异归因）/ tilemap 区域方块地图 / coverage 保障责任一览 / case 客户案例推演 /
  journey 服务旅程与痛点 / radar 雷达对比（原生图表）+ 对比表 / roadmap 泳道路线图 / qa 问答话术
签名同 diagrams_flow：fn(slide, t, seq, box, d)。字段说明见 reference/elements.md。
"""
import math
import re

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.util import Pt

from diagrams_flow import _icon, card
from icons import draw_icon, icon_badge
from ppt_base import (BRAND, I, dashed, fit_size, fmt_num, line, mix, polyline, rgb, set_font, shape, shape_text,
                      smooth, text)
from ppt_theme import CONF, FONTS, L as label, R


def _f(v):
    return float(str(v).replace(",", "").replace("%", "")) if isinstance(v, str) else float(v)


def _nice_floor(v, span):
    if v <= 0:
        return 0.0
    step = 10 ** math.floor(math.log10(max(span, 1e-9)))
    return math.floor(v / step) * step


# ---------------- 1. 瀑布图 ----------------
def waterfall(slide, t, seq, box, d):
    """start（起点，如目标）→ items（逐项增减）→ end（终点，如实际；不写时自动累加）。"""
    x, y, w, h = box
    nf = d.get("number_format", "0.0")
    bars, cur = [], 0.0
    if d.get("start"):
        cur = _f(d["start"]["value"])
        bars.append(["tot", d["start"]["label"], None, cur])
    for it in d["items"]:
        v = _f(it["value"])
        bars.append(["up" if v >= 0 else "dn", it["label"], cur, cur + v])
        cur += v
    end = d.get("end") or {}
    end_v = _f(end["value"]) if end.get("value") is not None else cur
    bars.append(["tot", end.get("label") or label("wf_total"), None, end_v])
    levels = [b[3] for b in bars] + [b[2] for b in bars if b[2] is not None]
    lo, hi = min(levels), max(levels)
    span = (hi - lo) or abs(hi) or 1.0
    amin = d.get("axis_min")
    if amin is None:
        amin = 0.0 if lo - span * 1.5 <= 0 else _nice_floor(lo - span * 0.6, span)
    vmax = hi + span * 0.18
    rng = (vmax - amin) or 1.0
    px, pw = x + 0.1, w - 0.2
    py, ph = y + 0.35, h - 0.95
    base = py + ph

    def Y(v):
        return py + ph * (1 - (v - amin) / rng)

    deltas = [abs(b[3] - b[2]) if b[0] == "up" else 0 for b in bars]
    top_i = deltas.index(max(deltas)) if any(deltas) else -1
    n = len(bars)
    slot = pw / n
    bw = slot * 0.56
    seq.begin()
    line(slide, px, base, px + pw, base, BRAND["line"], 1.0)
    seq.end("fade")
    for i, (kind, lab, a, b) in enumerate(bars):
        a = amin if a is None else a
        bx = px + i * slot + (slot - bw) / 2
        top, bot = Y(max(a, b)), Y(min(a, b))
        col = t["primary"] if kind == "tot" else (t["bar_fill"] if kind == "up" else BRAND["red"])
        seq.begin()
        shape(slide, "rect", bx, top, bw, max(0.02, bot - top), fill=col)
        if kind == "tot":
            s = fmt_num(b, nf)
        else:
            s = ("+" if b >= a else "−") + fmt_num(abs(b - a), nf)
        vc = t["title"] if kind == "tot" else (BRAND["red"] if kind == "dn" else (t["primary"] if i == top_i else BRAND["ink_soft"]))
        text(slide, bx - 0.35, top - 0.38, bw + 0.7, 0.34, [{"text": s, "bold": True}], 13, vc, align="center",
             anchor="bottom", en=FONTS["num"])
        text(slide, bx - 0.4, base + 0.08, bw + 0.8, 0.45, lab, 12, BRAND["ink_soft"], align="center", min_size=9,
             bold=kind == "tot")
        if i < n - 1:
            nx = px + (i + 1) * slot + (slot - bw) / 2
            line(slide, bx + bw, Y(b), nx, Y(b), BRAND["grey_mid"], 0.75, "dash")
        seq.end("float")
    if amin > 0:
        text(slide, x, y + h - 0.28, 4, 0.28, label("wf_axis", v=fmt_num(amin, nf)), 9.5, BRAND["muted"])


# ---------------- 2. 区域方块地图 ----------------
def tilemap(slide, t, seq, box, d):
    """按区域相对位置排布的方块，颜色深浅表示数值，负值用红色；右侧自动排名。
    区域位置默认取 rules.ppt.tilemap_regions，也可在 item 里写 pos: [行, 列, 跨行, 跨列]。"""
    x, y, w, h = box
    items = d["items"]
    regions = R("tilemap_regions")
    rows, cols = d.get("grid") or R("tilemap_grid")
    nf = d.get("number_format", "0.0")
    vals = [_f(it["value"]) for it in items]
    vmax = max(abs(v) for v in vals) or 1.0
    rank = d.get("rank", True)
    mw = w * 0.56 if rank else w
    cell = min(mw / cols, (h - 0.55) / rows)
    gap = 0.07
    custom = any(it.get("pos") for it in items)
    seq.begin()
    if not custom:                                  # 没有数据的区域画成浅色虚线框，保留地图轮廓
        have = {it["label"] for it in items}
        for nm, (r0, c0, rs, cs) in regions.items():
            if nm in have:
                continue
            sp = shape(slide, "round", x + c0 * cell + gap / 2, y + r0 * cell + gap / 2, cs * cell - gap, rs * cell - gap,
                       line=t["card_line"], line_w=0.75, radius=0.08)
            dashed(sp)
            tb = text(slide, x + c0 * cell + 0.12, y + r0 * cell + 0.08, cs * cell - 0.2, 0.3, nm, 10, BRAND["muted"])
    seq.end("fade")
    for it, v in zip(items, vals):
        r0, c0, rs, cs = it.get("pos") or regions[it["label"]]
        tx, ty = x + c0 * cell + gap / 2, y + r0 * cell + gap / 2
        tw, th = cs * cell - gap, rs * cell - gap
        if v < 0:
            fill, fg = BRAND["red_light"], BRAND["red"]
        else:
            k = 0.18 + 0.72 * v / vmax
            fill = mix(t["card"], t["primary"], k)
            fg = BRAND["white"] if k > 0.55 else t["title"]
        seq.begin()
        shape(slide, "round", tx, ty, tw, th, fill=fill, radius=0.08)
        text(slide, tx + 0.12, ty + 0.08, tw - 0.2, 0.34, [{"text": it["label"], "bold": True}], 13, fg, min_size=9)
        text(slide, tx + 0.12, ty + th - 0.5, tw - 0.2, 0.42, [{"text": it.get("display") or fmt_num(v, nf), "bold": True}],
             18, fg, en=FONTS["num"], min_size=11, anchor="bottom")
        seq.end("zoom")
    ly = y + rows * cell + 0.12
    seq.begin()
    lx = x
    for c, lab in ((mix(t["card"], t["primary"], 0.18), label("legend_low")), (t["primary"], label("legend_high")),
                   (BRAND["red_light"], label("legend_negative"))):
        shape(slide, "round", lx, ly + 0.06, 0.32, 0.18, fill=c, radius=0.3)
        text(slide, lx + 0.38, ly, 0.9, 0.3, lab, 10, BRAND["ink_soft"])
        lx += 1.2
    if not custom:
        text(slide, lx + 0.2, ly, mw - (lx - x) - 0.2, 0.3, label("tilemap_note"), 9.5, BRAND["muted"])
    seq.end("fade")
    if rank:
        rx, rw = x + mw + 0.45, w - mw - 0.45
        order = sorted(zip(items, vals), key=lambda p: -p[1])
        rh = min(0.62, h / max(len(order), 1))
        for i, (it, v) in enumerate(order):
            ry = y + i * rh
            seq.begin()
            text(slide, rx, ry, 1.1, rh, it["label"], 13, t["title"], i == 0, anchor="middle", min_size=9)
            shape(slide, "round", rx + 1.15, ry + rh * 0.36, rw - 2.35, rh * 0.28, fill=BRAND["bg_soft"], radius=0.5)
            shape(slide, "round", rx + 1.15, ry + rh * 0.36, max(0.06, (rw - 2.35) * abs(v) / vmax), rh * 0.28,
                  fill=BRAND["red"] if v < 0 else (t["primary"] if i == 0 else t["bar_fill"]), radius=0.5)
            text(slide, rx + rw - 1.1, ry, 1.1, rh, [{"text": it.get("display") or fmt_num(v, nf), "bold": True}], 13,
                 BRAND["red"] if v < 0 else t["title"], align="right", anchor="middle", en=FONTS["num"])
            seq.end("wipe")


# ---------------- 3. 保障责任一览 ----------------
def coverage(slide, t, seq, box, d):
    """一张保单的保障责任：key 为核心责任（实色突出），optional 为可选责任（虚线框）。"""
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    cols = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 3}.get(n, 3)
    rows = int(math.ceil(n / float(cols)))
    gx, gy = 0.25, 0.25
    cw = (w - gx * (cols - 1)) / cols
    chh = (h - gy * (rows - 1)) / rows
    used = set()
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        cx, cy = x + c * (cw + gx), y + r * (chh + gy)
        key = it.get("key")
        seq.begin()
        sp = card(slide, cx, cy, cw, chh, t, fill=t["primary"] if key else t["card"],
                  line_color=t["primary"] if key else (t["primary"] if it.get("optional") else None), shadow=not it.get("optional"))
        if it.get("optional"):
            dashed(sp)
        ic = _icon(it, used)
        used.add(ic)
        icon_badge(slide, ic, cx + 0.28, cy + 0.3, 0.74, BRAND["white"] if key else t["soft2"], t["primary"])
        fg = BRAND["white"] if key else t["title"]
        sub = BRAND["white"] if key else BRAND["ink_soft"]
        tx, tw = cx + 1.25, cw - 1.45
        text(slide, tx, cy + 0.22, tw, 0.4, [{"text": it["title"], "bold": True}], 15, fg, min_size=10)
        if it.get("amount") is not None:
            tb = text(slide, tx, cy + 0.6, tw, 0.62, [{"text": str(it["amount"]), "bold": True, "en": FONTS["num"]}],
                      fit_size([str(it["amount"]) + "  " + it.get("unit", "")], tw, 0.6, 28, 16), BRAND["white"] if key else t["primary"],
                      anchor="middle")
            if it.get("unit"):
                rr = tb.text_frame.paragraphs[0].add_run()
                set_font(rr, 11.5, False, sub)
                rr.text = " " + it["unit"]
        if it.get("desc"):
            text(slide, tx, cy + 1.25, tw, chh - 1.4, it["desc"], 11.5, sub, min_size=9, spacing=1.3,
                 where="保障责任“%s”" % it["title"])
        seq.end("float")


# ---------------- 4. 客户案例推演 ----------------
def case(slide, t, seq, box, d):
    """profile 客户画像 → steps 推演步骤（最后一步为结果）→ structure 可选的保障结构条。"""
    x, y, w, h = box
    prof, steps, st = d.get("profile"), d["steps"], d.get("structure")
    pw = 3.1 if prof else 0.0
    if prof:
        seq.begin()
        shape(slide, "round", x, y, pw, h, fill=t["soft"], radius=0.05)
        icon_badge(slide, prof.get("icon", "user"), x + 0.3, y + 0.3, 0.95, t["primary"], BRAND["white"])
        text(slide, x + 0.3, y + 1.4, pw - 0.5, 0.42, [{"text": prof.get("name", ""), "bold": True}], 17, t["title"], min_size=12)
        tx, ty = x + 0.3, y + 1.9
        for tg in prof.get("tags", []):
            tw = 0.28 + 0.16 * len(tg)
            if tx + tw > x + pw - 0.2:
                tx, ty = x + 0.3, ty + 0.36
            chip = shape(slide, "round", tx, ty, tw, 0.28, fill=t["soft2"], radius=0.5)
            shape_text(chip, tg, 9.5, t["title"], True)
            tx += tw + 0.08
        fy = ty + 0.5
        for k, v in prof.get("facts", []):
            text(slide, x + 0.3, fy, 1.2, 0.34, k, 11, BRAND["ink_soft"], anchor="middle")
            text(slide, x + 1.4, fy, pw - 1.6, 0.34, [{"text": str(v), "bold": True}], 11.5, t["title"], align="right",
                 anchor="middle", en=FONTS["num"], min_size=9)
            fy += 0.38
        seq.end("float")
    rx = x + pw + (0.3 if prof else 0)
    rw = w - (rx - x)
    sh = h - (1.3 if st else 0)
    n = len(steps)
    gx = 0.45
    sw = (rw - gx * (n - 1)) / n
    for i, s in enumerate(steps):
        cx = rx + i * (sw + gx)
        res = s.get("result", i == n - 1)
        fg = BRAND["white"] if res else t["title"]
        sub = BRAND["white"] if res else BRAND["ink_soft"]
        seq.begin()
        card(slide, cx, y, sw, sh, t, fill=t["primary"] if res else t["card"])
        text(slide, cx + 0.25, y + 0.22, sw - 0.5, 0.3, [{"text": s.get("label", "%d" % (i + 1)), "bold": True}], 11,
             BRAND["white"] if res else t["primary"])
        text(slide, cx + 0.25, y + 0.55, sw - 0.5, 0.5, [{"text": s.get("title", ""), "bold": True}], 15, fg, min_size=10)
        if s.get("value") is not None:
            tb = text(slide, cx + 0.25, y + 1.05, sw - 0.5, 0.7, [{"text": str(s["value"]), "bold": True, "en": FONTS["num"]}],
                      30, fg, anchor="middle")
            if s.get("unit"):
                rr = tb.text_frame.paragraphs[0].add_run()
                set_font(rr, 12, False, sub)
                rr.text = " " + s["unit"]
        if s.get("desc"):
            text(slide, cx + 0.25, y + 1.8, sw - 0.5, sh - 1.95, s["desc"], 11.5, sub, min_size=9, spacing=1.35,
                 numbers=not res, accent=t["primary"])
        if i < n - 1:
            ar = shape(slide, "chevron", cx + sw + 0.1, y + sh / 2 - 0.17, 0.25, 0.34, fill=t["primary"])
        seq.end("float")
    if st:
        sy = y + sh + 0.2
        seq.begin()
        card(slide, rx, sy, rw, 1.1, t, shadow=False)
        text(slide, rx + 0.25, sy + 0.08, 3, 0.3, [{"text": st.get("title") or label("structure"), "bold": True}], 11.5, t["title"])
        segs = st["items"]
        tot = sum(_f(v) for _, v in segs) or 1.0
        bx, bw = rx + 0.25, rw - 0.5
        cols = [t["grey"], t["bar_fill"], t["primary"], t["secondary"], t["accent"]]
        for k, (lab, v) in enumerate(segs):
            sw_ = bw * _f(v) / tot
            sp = shape(slide, "rect", bx, sy + 0.42, sw_, 0.34, fill=cols[k % len(cols)])
            shape_text(sp, "%s %s" % (lab, v), 10, BRAND["white"] if k else BRAND["ink"], True, align="left")
            bx += sw_
        text(slide, rx + 0.25, sy + 0.8, rw - 0.5, 0.26, st.get("note") or label("case_sample"), 9, BRAND["muted"])
        seq.end("wipe")


# ---------------- 5. 服务旅程与痛点 ----------------
def journey(slide, t, seq, box, d):
    """steps：每步 title / desc / icon / emotion（1-5，客户感受）/ pain（痛点）/ note_title + note。"""
    x, y, w, h = box
    steps = d["steps"]
    n = len(steps)
    slot = w / n
    cxs = [x + slot * (i + 0.5) for i in range(n)]
    has_notes = any(s.get("note") or s.get("note_title") for s in steps)
    seq.begin()
    line(slide, cxs[0], y + 0.36, cxs[-1], y + 0.36, t["bar_fill"], 1.25, "dash")
    seq.end("wipe")
    used = set()
    for i, s in enumerate(steps):
        pain = s.get("pain")
        seq.begin()
        ic = _icon(s, used)
        used.add(ic)
        icon_badge(slide, ic, cxs[i] - 0.36, y, 0.72, BRAND["red_light"] if pain else t["soft2"],
                   BRAND["red"] if pain else t["primary"])
        text(slide, cxs[i] - slot / 2 + 0.05, y + 0.8, slot - 0.1, 0.36, [{"text": s["title"], "bold": True}], 14,
             BRAND["red"] if pain else t["title"], align="center", min_size=10)
        if s.get("desc"):
            text(slide, cxs[i] - slot / 2 + 0.05, y + 1.14, slot - 0.1, 0.34, s["desc"], 10.5, BRAND["ink_soft"],
                 align="center", min_size=8.5, numbers=True, accent=t["primary"])
        seq.end("float")
    ey, eh = y + 1.75, (1.35 if has_notes else h - 1.9)
    pts = [(cxs[i], ey + eh * (1 - (max(1.0, min(5.0, _f(s.get("emotion", 3)))) - 1) / 4.0)) for i, s in enumerate(steps)]
    seq.begin()
    text(slide, x, ey - 0.32, 2, 0.28, label("journey_emotion"), 9.5, BRAND["muted"])
    line(slide, x, ey + eh / 2, x + w, ey + eh / 2, BRAND["line"], 0.75, "dot")
    polyline(slide, smooth(pts), t["primary"], 2.5)
    for (px, py), s in zip(pts, steps):
        shape(slide, "oval", px - 0.09, py - 0.09, 0.18, 0.18, fill=BRAND["red"] if s.get("pain") else t["primary"],
              line=BRAND["white"], line_w=1.5)
    seq.end("wipe")
    if has_notes:
        ny = ey + eh + 0.25
        nh = y + h - ny
        for i, s in enumerate(steps):
            pain = s.get("pain")
            seq.begin()
            shape(slide, "round", cxs[i] - slot / 2 + 0.06, ny, slot - 0.12, nh, fill=BRAND["red_light"] if pain else t["card"],
                  line=BRAND["red"] if pain else t["card_line"], line_w=0.75, radius=0.08)
            paras = []
            if s.get("note_title"):
                paras.append({"text": s["note_title"], "bold": True, "size": 11.5, "color": BRAND["red"] if pain else t["title"]})
            if s.get("note"):
                paras.append({"text": s["note"], "size": 10.5, "color": BRAND["ink_soft"]})
            text(slide, cxs[i] - slot / 2 + 0.16, ny + 0.06, slot - 0.32, nh - 0.12, paras, 11, min_size=8.5, spacing=1.25,
                 where="旅程第 %d 步说明" % (i + 1))
            seq.end("fade")


# ---------------- 6. 雷达对比 ----------------
def radar(slide, t, seq, box, d):
    """axes 维度 + series 各方案得分（highlight 的方案用主色加粗）；可加 table 对比表放在右侧。"""
    from diagrams_data import table as draw_table
    x, y, w, h = box
    axes, series = d["axes"], d["series"]
    tb = d.get("table")
    size = min(h, w * 0.46) if tb else min(h, w)
    cx0 = x if tb else x + (w - size) / 2
    cd = CategoryChartData()
    cd.categories = axes
    for s in series:
        cd.add_series(s["name"], [_f(v) for v in s["values"]])
    seq.begin()
    gf = slide.shapes.add_chart(XL_CHART_TYPE.RADAR_MARKERS, I(cx0), I(y), I(size), I(size), cd)
    ch = gf.chart
    ch.font.size = Pt(CONF.size(11))
    ch.font.name = FONTS["cn"]
    ch.font.color.rgb = rgb(BRAND["ink_soft"])
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    others = [BRAND["grey_mid"], t["secondary"], t["accent"], BRAND["muted"]]
    k = 0
    for spec, s in zip(series, ch.plots[0].series):
        if spec.get("highlight"):
            col, wd = t["primary"], 3.0
        else:
            col, wd = others[k % len(others)], 1.5
            k += 1
        s.format.line.color.rgb = rgb(col)
        s.format.line.width = Pt(wd)
        try:
            s.marker.style = XL_MARKER_STYLE.CIRCLE
            s.marker.size = 7 if spec.get("highlight") else 5
            s.marker.format.fill.solid()
            s.marker.format.fill.fore_color.rgb = rgb(col)
            s.marker.format.line.color.rgb = rgb(col)
        except AttributeError:   # 个别版本的雷达图系列没有 marker 属性，保留默认标记
            pass
    try:
        va = ch.value_axis
        va.minimum_scale = d.get("min", 0)
        va.maximum_scale = d.get("max", 5)
        va.major_unit = d.get("step", 1)
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb(BRAND["bg_grey"])
        va.tick_labels.font.size = Pt(CONF.size(9))
        va.tick_labels.font.color.rgb = rgb(BRAND["muted"])
    except Exception:            # noqa: BLE001  个别版本的 python-pptx 不支持雷达图坐标轴设置，不影响图表本身
        pass
    seq.end("fade")
    if tb:
        draw_table(slide, t, seq, (x + size + 0.4, y + 0.2, w - size - 0.4, h - 0.2), tb)


# ---------------- 7. 泳道路线图 ----------------
def roadmap(slide, t, seq, box, d):
    """periods 时间段；lanes 每条业务线 {name, items:[{title, start, end, key}], milestones:[{at, title}]}；
    start / end / at / now 以时间段为单位（0 = 第一段开始，1.5 = 第二段中间）。"""
    x, y, w, h = box
    periods, lanes = d["periods"], d["lanes"]
    lw, hh = 1.4, 0.42
    gx, gw = x + lw + 0.1, w - lw - 0.1
    pw = gw / len(periods)
    lane_h = (h - hh) / len(lanes)
    ms_col = t["highlight"] if t["highlight"] != t["primary"] else t["secondary"]
    seq.begin()
    for j, p in enumerate(periods):
        cur = d.get("current_period") == j
        text(slide, gx + j * pw + 0.1, y, pw - 0.1, hh, [{"text": p, "bold": True}], 12.5,
             t["primary"] if cur else BRAND["ink_soft"], anchor="middle", en=FONTS["num"])
        line(slide, gx + j * pw, y, gx + j * pw, y + h, t["card_line"], 0.6)
    line(slide, gx + gw, y, gx + gw, y + h, t["card_line"], 0.6)
    line(slide, x, y + hh, x + w, y + hh, BRAND["line"], 1.0)
    seq.end("fade")
    for i, ln in enumerate(lanes):
        ly = y + hh + i * lane_h
        seq.begin()
        shape(slide, "rect", x, ly + lane_h / 2 - 0.16, 0.07, 0.32, fill=t["primary"])
        text(slide, x + 0.16, ly, lw - 0.2, lane_h, [{"text": ln["name"], "bold": True}], 13, t["title"], anchor="middle",
             min_size=9.5)
        line(slide, x, ly + lane_h, x + w, ly + lane_h, t["card_line"], 0.6)
        items = sorted(ln.get("items", []), key=lambda b: _f(b["start"]))
        rows_end = []
        place = []
        for b in items:                          # 时间重叠的事项自动分成上下两行
            r = next((k for k, e in enumerate(rows_end) if _f(b["start"]) >= e - 1e-6), None)
            if r is None:
                rows_end.append(_f(b["end"]))
                r = len(rows_end) - 1
            else:
                rows_end[r] = _f(b["end"])
            place.append((b, r))
        nr = max(1, len(rows_end))
        bh = min(0.5, (lane_h * 0.78) / nr - 0.06)
        top = ly + (lane_h - (bh + 0.06) * nr + 0.06) / 2
        for b, r in place:
            bx = gx + _f(b["start"]) * pw
            bw = max(0.2, (_f(b["end"]) - _f(b["start"])) * pw)
            by = top + r * (bh + 0.06)
            key = b.get("key")
            shape(slide, "round", bx, by, bw, bh, fill=t["primary"] if key else t["soft2"], radius=0.18)
            if not key:
                shape(slide, "rect", bx, by, 0.06, bh, fill=t["primary"])
            text(slide, bx + 0.12, by, bw - 0.16, bh, b["title"], 11, BRAND["white"] if key else t["title"], key,
                 anchor="middle", min_size=8)
        for m in ln.get("milestones", []):
            mx = gx + _f(m["at"]) * pw
            shape(slide, "diamond", mx - 0.12, ly + 0.06, 0.24, 0.24, fill=ms_col, line=BRAND["white"], line_w=1.25)
            if m.get("title"):
                text(slide, mx + 0.14, ly + 0.02, 2.2, 0.3, m["title"], 9.5, ms_col, True)
        seq.end("float")
    if d.get("now") is not None:
        nx = gx + _f(d["now"]) * pw
        seq.begin()
        line(slide, nx, y + hh, nx, y + h, BRAND["red"], 1.5)
        text(slide, nx - 0.5, y + hh - 0.02, 1.0, 0.26, [{"text": label("now"), "bold": True}], 9.5, BRAND["red"], align="center")
        seq.end("wipe")


# ---------------- 8. 问答话术 ----------------
def _auto_avoid(q):
    """按 compliance.json 的 qa_avoid：问题命中 when 时列出该条的 avoid 说法。"""
    for rule in CONF.compliance().get("qa_avoid") or []:
        if re.search(rule["when"], q):
            return "".join("“%s”" % wd for wd in rule["avoid"])
    return ""


def qa(slide, t, seq, box, d):
    """items：{q 客户问, a 规范回答, avoid 避免说（"auto" 时按合规词表自动匹配）}，每页最多 3 组。
    “避免说”文本框命名为 tap_avoid，质检时不算违规用语。"""
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    gx = 0.3
    cw = (w - gx * (n - 1)) / n
    good = BRAND["teal"]
    for i, it in enumerate(items):
        cx = x + i * (cw + gx)
        avoid = it.get("avoid")
        if avoid == "auto" or (avoid is None and d.get("auto_avoid", True)):
            avoid = _auto_avoid(it["q"])
        ab = 0.85 if avoid else 0
        seq.begin()
        card(slide, cx, y, cw, h, t)
        shape(slide, "round", cx + 0.22, y + 0.22, cw - 0.44, 1.15, fill=t["soft"], radius=0.12)
        text(slide, cx + 0.4, y + 0.28, cw - 0.8, 1.05,
             [{"text": label("qa_q"), "bold": True, "size": 9.5, "color": t["primary"]},
              {"text": it["q"], "bold": True, "size": 14.5, "color": t["title"], "space_before": 3}], 14, min_size=10,
             spacing=1.2)
        text(slide, cx + 0.3, y + 1.52, cw - 0.6, 0.28, [{"text": label("qa_a"), "bold": True}], 9.5, good)
        text(slide, cx + 0.3, y + 1.82, cw - 0.6, h - 1.95 - ab, it.get("a", ""), 12, BRAND["ink"], min_size=9, spacing=1.45,
             where="问答“%s”" % it["q"][:10])
        if avoid:
            bx = shape(slide, "round", cx + 0.22, y + h - ab - 0.15, cw - 0.44, ab, fill=BRAND["red_light"], radius=0.14)
            bx.name = "tap_avoid_box"
            tb = text(slide, cx + 0.36, y + h - ab - 0.13, cw - 0.72, ab - 0.04,
                      [{"text": label("qa_avoid"), "bold": True}, {"text": avoid, "space_before": 2}], 10.5, BRAND["red"],
                      anchor="middle", min_size=8.5)
            tb.name = "tap_avoid"
        seq.end("float")


REGISTRY = {"waterfall": waterfall, "tilemap": tilemap, "coverage": coverage, "case": case, "journey": journey,
            "radar": radar, "roadmap": roadmap, "qa": qa}
