# -*- coding: utf-8 -*-
"""
流程与结构类图示（10 种）：
  process 箭头流程 / timeline 时间线 / cycle 循环 / funnel 漏斗 / pyramid 金字塔 /
  matrix 四象限 / hub 中心辐射 / hierarchy 层级结构 / stairs 阶梯 / layers 分层架构
每个函数签名：fn(slide, t, seq, box, d)
  t：主题字典；seq：动画序列（每个“步骤”为一组一起入场的形状）；box：(x, y, w, h) 英寸；d：数据
字段说明见 reference/elements.md。
"""
import math

from icons import icon_badge, match_icon
from ppt_base import BRAND, arc_pts, fit_size, line, poly, ring_segment, shape, shape_text, text
from ppt_theme import FONTS, SIZES, G, L as label, palette


def _icon(item, used=None):
    return item.get("icon") or match_icon(item.get("title", "") + item.get("desc", ""), used=used)


def card(slide, x, y, w, h, t, fill=None, line_color=None, shadow=True, radius=0.06):
    return shape(slide, "round", x, y, w, h, fill=fill or t["card"], line=line_color or t["card_line"],
                 line_w=0.75, radius=radius, shadow=shadow)


# ---------------- 1. 箭头流程 ----------------
def process(slide, t, seq, box, d):
    x, y, w, h = box
    steps = d["steps"]
    n = len(steps)
    hi = set(d.get("highlight", []) if isinstance(d.get("highlight"), list) else [d.get("highlight")])
    ov = 0.18
    cw = (w + ov * (n - 1)) / n
    ch = 0.78
    icon_d = 0.72
    y_icon = y + 0.05
    y_chev = y_icon + icon_d + 0.28
    y_desc = y_chev + ch + 0.22
    desc_h = max(0.6, y + h - y_desc)
    used = set()
    for i, s in enumerate(steps):
        s = {"title": s} if isinstance(s, str) else s
        on = (i + 1) in hi
        cx = x + i * (cw - ov)
        seq.begin()
        ic = _icon(s, used)
        used.add(ic)
        icon_badge(slide, ic, cx + (cw - icon_d) / 2, y_icon, icon_d, t["primary"] if on else t["soft2"],
                   BRAND["white"] if on else t["primary"])
        sp = shape(slide, "pentagon" if i == 0 else "chevron", cx, y_chev, cw, ch,
                   fill=t["primary"] if on else (t["soft"] if i % 2 == 0 else t["soft2"]))
        try:
            sp.adjustments[0] = 0.28
        except IndexError:
            pass
        size = fit_size([s["title"]], cw - 0.55, ch - 0.1, 15, 11)
        shape_text(sp, "%02d  %s" % (i + 1, s["title"]), size, BRAND["white"] if on else t["title"], True)
        if s.get("desc"):
            text(slide, cx + 0.12, y_desc, cw - 0.4, desc_h, s["desc"], 12, BRAND["ink_soft"], align="center",
                 min_size=9.5, where="流程第 %d 步说明" % (i + 1), numbers=True, accent=t["primary"])
        seq.end("float")


# ---------------- 2. 时间线 ----------------
def timeline(slide, t, seq, box, d):
    x, y, w, h = box
    nodes = d["nodes"]
    n = len(nodes)
    cur = d.get("current")
    ay = y + h / 2
    seq.begin()
    line(slide, x, ay, x + w, ay, BRAND["line"], 2.5)
    if cur is not None:
        line(slide, x, ay, x + w * (cur + 0.5) / n, ay, t["primary"], 2.5)
    seq.end("wipe")
    slot = w / n
    for i, nd in enumerate(nodes):
        cx = x + slot * (i + 0.5)
        state = "done" if cur is None or i < cur else ("now" if i == cur else "future")
        col = {"done": t["primary"], "now": t["secondary"], "future": BRAND["grey_bar"]}[state]
        up = i % 2 == 0
        seq.begin()
        r = 0.17 if state != "now" else 0.24
        if state == "now":
            shape(slide, "oval", cx - 0.36, ay - 0.36, 0.72, 0.72, fill=col, alpha=0.18)
        shape(slide, "oval", cx - r, ay - r, 2 * r, 2 * r, fill=col, line=BRAND["white"], line_w=2)
        ly0, ly1 = (ay - 0.3, ay - 0.62) if up else (ay + 0.3, ay + 0.62)
        line(slide, cx, ly0, cx, ly1, col, 1)
        bw = min(slot * 1.6, 2.6)
        bh = h / 2 - 0.75
        by = ay - 0.7 - bh if up else ay + 0.7
        paras = [{"text": nd["time"], "size": 13, "bold": True, "color": col if state != "future" else BRAND["muted"]},
                 {"text": nd["title"], "size": 15, "bold": True,
                  "color": BRAND["ink"] if state != "future" else BRAND["muted"]}]
        if nd.get("desc"):
            paras.append({"text": nd["desc"], "size": 11.5, "color": BRAND["ink_soft"]})
        text(slide, cx - bw / 2, by, bw, bh, paras, 13, align="center", anchor="bottom" if up else "top",
             min_size=9, where="时间线“%s”" % nd["title"])
        if state == "now":
            tag = shape(slide, "round", cx - 0.42, ay + (0.32 if up else -0.62), 0.84, 0.3, fill=t["secondary"], radius=0.5)
            shape_text(tag, label("current"), 10.5, BRAND["white"], True)
        seq.end("float")


# ---------------- 3. 循环 ----------------
def cycle(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    pal = palette(t)
    R = min(w * 0.42, h - 1.6) / 2           # 上下留出标签空间，避免压到标题
    cx, cy = x + w / 2, y + h / 2
    thick = R * 0.30
    seq.begin()
    core = shape(slide, "oval", cx - (R - thick - 0.15), cy - (R - thick - 0.15), 2 * (R - thick - 0.15),
                 2 * (R - thick - 0.15), fill=t["soft"])
    if d.get("center"):
        shape_text(core, d["center"], fit_size([d["center"]], 2 * (R - thick) * 0.7, 1.0, 20, 12), t["title"], True)
    seq.end("zoom")
    gapd = 4
    for i, it in enumerate(items):
        it = {"title": it} if isinstance(it, str) else it
        a0 = 90 - i * 360.0 / n - gapd / 2
        a1 = a0 - 360.0 / n + gapd
        mid = math.radians((a0 + a1) / 2)
        seq.begin()
        col = pal[i % 2] if n % 2 == 0 or i < n - 1 else pal[2]
        ring_segment(slide, cx, cy, R, R - thick, a0, a1, col)
        # 段尾箭头（三角）
        ae = math.radians(a1 + 1)
        rm = R - thick / 2
        tip = (cx + (rm) * math.cos(ae - 0.12), cy - rm * math.sin(ae - 0.12))
        b1 = (cx + (R + 0.06) * math.cos(ae), cy - (R + 0.06) * math.sin(ae))
        b2 = (cx + (R - thick - 0.06) * math.cos(ae), cy - (R - thick - 0.06) * math.sin(ae))
        poly(slide, [b1, tip, b2], col)
        nx, ny = cx + rm * math.cos(mid), cy - rm * math.sin(mid)
        num = shape(slide, "oval", nx - 0.24, ny - 0.24, 0.48, 0.48, fill=BRAND["white"])
        shape_text(num, str(i + 1), 13, col, True)
        lx = cx + (R + 0.35) * math.cos(mid)
        ly = cy - (R + 0.35) * math.sin(mid)
        bw, bh = min(3.2, (w - 2 * R) / 2 - 0.2), 1.1
        right = math.cos(mid) >= -0.05
        vertical = abs(math.cos(mid)) < 0.3
        bx = lx if right else lx - bw
        by = ly - bh / 2
        if vertical:                         # 正上方/正下方的标签居中，贴着圆环向外排
            bx, bh = lx - bw / 2, 0.9
            by = ly - bh if math.sin(mid) > 0 else ly
        paras = [{"text": it["title"], "size": 15, "bold": True, "color": t["title"]}]
        if it.get("desc"):
            paras.append({"text": it["desc"], "size": 11.5, "color": BRAND["ink_soft"]})
        text(slide, bx, by, bw, bh, paras, 14, align="center" if vertical else ("left" if right else "right"),
             anchor="middle", min_size=9, where="循环“%s”" % it["title"])
        seq.end("float")


# ---------------- 4. 漏斗 ----------------
def funnel(slide, t, seq, box, d):
    x, y, w, h = box
    lv = d["levels"]
    n = len(lv)
    pal = palette(t)
    fw = w * 0.5
    gap = 0.08
    lh = (h - gap * (n - 1)) / n
    top_w, bot_w = fw, fw * 0.3
    cx = x + fw / 2
    for i, L in enumerate(lv):
        w0 = top_w - (top_w - bot_w) * i / n
        w1 = top_w - (top_w - bot_w) * (i + 1) / n
        y0 = y + i * (lh + gap)
        seq.begin()
        col = t["funnel"][i % len(t["funnel"])]
        sp = poly(slide, [(cx - w0 / 2, y0), (cx + w0 / 2, y0), (cx + w1 / 2, y0 + lh), (cx - w1 / 2, y0 + lh)], col)
        text(slide, cx - w1 / 2, y0, w1, lh, [{"text": L["label"], "bold": True}], 14, BRAND["white"], align="center",
             anchor="middle", min_size=10)
        lx = cx + (w0 + w1) / 4 + 0.15
        line(slide, lx, y0 + lh / 2, x + fw + 0.55, y0 + lh / 2, BRAND["line"], 1)
        tx = x + fw + 0.65
        paras = []
        if L.get("value") is not None:
            paras.append({"text": str(L["value"]), "size": 22, "bold": True, "color": col, "en": FONTS["num"]})
        if L.get("desc"):
            paras.append({"text": L["desc"], "size": 12, "color": BRAND["ink_soft"]})
        if paras:
            text(slide, tx, y0, x + w - tx, lh, paras, 13, anchor="middle", min_size=9, spacing=1.1)
        seq.end("float")


# ---------------- 5. 金字塔 ----------------
def pyramid(slide, t, seq, box, d):
    x, y, w, h = box
    lv = d["levels"]                     # 从塔尖到塔基
    n = len(lv)
    pw = min(w * 0.46, h * 1.25)
    cx = x + pw / 2
    gap = 0.07
    lh = (h - gap * (n - 1)) / n
    cols = t["pyramid"]
    for i, L in enumerate(lv):
        y0 = y + i * (lh + gap)
        y1 = y0 + lh
        hw0 = pw / 2 * (y0 - y) / h
        hw1 = pw / 2 * (y1 - y) / h
        seq.begin()
        col = cols[i % len(cols)]
        pts = [(cx - hw0, y0), (cx + hw0, y0), (cx + hw1, y1), (cx - hw1, y1)] if i else [(cx, y0), (cx + hw1, y1), (cx - hw1, y1)]
        poly(slide, pts, col)
        tw = max(hw1 * 1.6, 0.9)
        text(slide, cx - tw / 2, y0 + (lh * 0.35 if i == 0 else 0), tw, lh * (0.65 if i == 0 else 1),
             [{"text": L["label"], "bold": True}], 13.5, BRAND["white"] if col not in (BRAND["accent"],) else BRAND["ink"],
             align="center", anchor="middle", min_size=9)
        line(slide, cx + (hw0 + hw1) / 2 + 0.1, y0 + lh / 2, x + pw + 0.5, y0 + lh / 2, BRAND["line"], 1)
        shape(slide, "oval", x + pw + 0.44, y0 + lh / 2 - 0.06, 0.12, 0.12, fill=col)
        paras = []
        if L.get("title"):
            paras.append({"text": L["title"], "bold": True, "size": 14, "color": t["title"]})
        if L.get("desc"):
            paras.append({"text": L["desc"], "size": 12, "color": BRAND["ink_soft"]})
        if paras:
            text(slide, x + pw + 0.7, y0, w - pw - 0.7, lh, paras, 12, anchor="middle", min_size=9, spacing=1.15,
                 where="金字塔“%s”" % L["label"])
        seq.end("float")


# ---------------- 6. 四象限 ----------------
def matrix(slide, t, seq, box, d):
    x, y, w, h = box
    q = d["quadrants"]
    hi = d.get("highlight")              # 0-3
    ax = 0.45
    gx, gy = 0.14, 0.14
    cw = (w - ax - gx) / 2
    chh = (h - ax - gy) / 2
    seq.begin()
    line(slide, x + ax - 0.12, y + h - ax + 0.06, x + ax - 0.12, y, BRAND["muted"], 1.5)
    line(slide, x + ax - 0.12, y + h - ax + 0.06, x + w, y + h - ax + 0.06, BRAND["muted"], 1.5)
    poly(slide, [(x + ax - 0.22, y + 0.12), (x + ax - 0.12, y - 0.04), (x + ax - 0.02, y + 0.12)], BRAND["muted"])
    poly(slide, [(x + w - 0.14, y + h - ax - 0.04), (x + w + 0.02, y + h - ax + 0.06), (x + w - 0.14, y + h - ax + 0.16)], BRAND["muted"])
    # 纵轴标签竖排：每个字一个段落（文字块内不能直接写换行符）
    text(slide, x - 0.25, y, 0.4, h - ax, [{"text": ch, "space_before": 0} for ch in d.get("y_label", label("y_label"))],
         11, BRAND["muted"], align="center", anchor="middle", spacing=1.0)
    text(slide, x + ax, y + h - 0.32, w - ax, 0.3, d.get("x_label", label("x_label")) + "  " + G("arrow"), 11, BRAND["muted"], align="center")
    seq.end("fade")
    pos = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for k, (cxk, cyk) in enumerate(pos):
        if k >= len(q):
            break
        qd = q[k]
        on = k == hi
        qx = x + ax + cxk * (cw + gx)
        qy = y + cyk * (chh + gy)
        seq.begin()
        card(slide, qx, qy, cw, chh, t, fill=t["primary"] if on else (t["soft"] if k in (0, 3) else t["card"]),
             line_color=t["primary"] if on else t["card_line"], shadow=on)
        fg = BRAND["white"] if on else t["title"]
        paras = [{"text": qd["title"], "size": 16, "bold": True, "color": fg}]
        for it in qd.get("items", []):
            paras.append({"text": G("dot") + " " + it, "size": 12.5, "color": BRAND["white"] if on else BRAND["ink_soft"]})
        if qd.get("action"):
            paras.append({"text": G("arrow") + " " + qd["action"], "size": 12, "bold": True,
                          "color": BRAND["accent"] if on else t["primary"], "space_before": 8})
        text(slide, qx + 0.25, qy + 0.18, cw - 0.5, chh - 0.3, paras, 13, min_size=9, spacing=1.2,
             where="四象限“%s”" % qd["title"])
        seq.end("zoom" if on else "float")


# ---------------- 7. 中心辐射 ----------------
def hub(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    cx, cy = x + w / 2, y + h / 2
    R = min(h * 0.24, 1.15)
    seq.begin()
    shape(slide, "oval", cx - R - 0.18, cy - R - 0.18, 2 * R + 0.36, 2 * R + 0.36, fill=t["primary"], alpha=0.14)
    c = shape(slide, "oval", cx - R, cy - R, 2 * R, 2 * R, fill=t["primary"], shadow=True)
    shape_text(c, d.get("center", ""), fit_size([d.get("center", "")], 2 * R * 0.72, R, 20, 12), BRAND["white"], True)
    seq.end("zoom")
    bw, bh = min(3.3, w * 0.27), 1.05
    rx, ry = w / 2 - bw / 2 - 0.05, h / 2 - bh / 2 - 0.02
    used = set()
    for i, it in enumerate(items):
        it = {"title": it} if isinstance(it, str) else it
        a = math.radians(90 - i * 360.0 / n + (180.0 / n if n % 2 == 0 and n != 4 else 0))
        if n == 4:
            a = math.radians(45 - i * 90)
        px, py = cx + rx * math.cos(a), cy - ry * math.sin(a)
        seq.begin()
        line(slide, cx + R * math.cos(a), cy - R * math.sin(a), px, py, t["primary"], 1.25)   # 卡片会盖住线的末端
        card(slide, px - bw / 2, py - bh / 2, bw, bh, t)
        ic = _icon(it, used)
        used.add(ic)
        icon_badge(slide, ic, px - bw / 2 + 0.16, py - 0.3, 0.6, t["soft2"], t["primary"])
        paras = [{"text": it["title"], "size": 14.5, "bold": True, "color": t["title"]}]
        if it.get("desc"):
            paras.append({"text": it["desc"], "size": 11, "color": BRAND["ink_soft"]})
        text(slide, px - bw / 2 + 0.9, py - bh / 2 + 0.08, bw - 1.0, bh - 0.16, paras, 13, anchor="middle",
             min_size=8.5, spacing=1.1, where="中心辐射“%s”" % it["title"])
        seq.end("float")


# ---------------- 8. 层级结构 ----------------
def hierarchy(slide, t, seq, box, d):
    x, y, w, h = box
    kids = d["children"]
    n = len(kids)
    rw, rh = min(4.0, w * 0.4), 0.7
    seq.begin()
    root = shape(slide, "round", x + (w - rw) / 2, y, rw, rh, fill=t["primary"], radius=0.18, shadow=True)
    shape_text(root, d["root"], 17, BRAND["white"], True)
    seq.end("zoom")
    gap = 0.22
    kw = (w - gap * (n - 1)) / n
    ky = y + rh + 0.55
    bus = y + rh + 0.27
    seq.begin()
    line(slide, x + w / 2, y + rh, x + w / 2, bus, BRAND["muted"], 1.25)
    line(slide, x + kw / 2, bus, x + w - kw / 2, bus, BRAND["muted"], 1.25)
    seq.end("fade")
    for i, k in enumerate(kids):
        kx = x + i * (kw + gap)
        seq.begin()
        line(slide, kx + kw / 2, bus, kx + kw / 2, ky, BRAND["muted"], 1.25)
        head = shape(slide, "round", kx, ky, kw, 0.6, fill=t["soft2"], radius=0.2)
        shape_text(head, k["name"], fit_size([k["name"]], kw - 0.2, 0.5, 15, 10), t["title"], True)
        items = k.get("items", [])
        if items:
            ih = y + h - (ky + 0.75)
            card(slide, kx, ky + 0.72, kw, ih, t, shadow=False)
            text(slide, kx + 0.15, ky + 0.82, kw - 0.3, ih - 0.2, [G("dot") + " " + s for s in items], 12, BRAND["ink_soft"],
                 min_size=9, spacing=1.25, where="层级“%s”" % k["name"])
        seq.end("float")


# ---------------- 9. 阶梯 ----------------
def stairs(slide, t, seq, box, d):
    x, y, w, h = box
    items = d["items"]
    n = len(items)
    gap = 0.12
    sw = (w - gap * (n - 1)) / n
    step_h = (h * 0.55) / n
    for i, it in enumerate(items):
        bh = step_h * (i + 1)
        bx = x + i * (sw + gap)
        by = y + h - bh
        last = i == n - 1
        seq.begin()
        shape(slide, "rect", bx, by, sw, bh, fill=t["primary"] if last else (t["soft2"] if i % 2 else t["soft"]))
        text(slide, bx, by + 0.1, sw, 0.6, "%02d" % (i + 1), 26, BRAND["white"] if last else t["primary"], True,
             align="center", en=FONTS["num"])
        paras = [{"text": it["title"], "size": 15.5, "bold": True, "color": t["title"]}]
        if it.get("desc"):
            paras.append({"text": it["desc"], "size": 11.5, "color": BRAND["ink_soft"]})
        th = y + h - bh - y - 0.12
        text(slide, bx, y, sw, max(th, 0.6), paras, 13, anchor="bottom", align="center", min_size=9,
             where="阶梯“%s”" % it["title"])
        seq.end("float")


# ---------------- 10. 分层架构 ----------------
def layers(slide, t, seq, box, d):
    x, y, w, h = box
    lv = d["levels"]                     # 自上而下
    n = len(lv)
    gap = 0.14
    lh = (h - gap * (n - 1)) / n
    tag_w = 2.0
    for i, L in enumerate(lv):
        ly = y + i * (lh + gap)
        on = L.get("highlight", False)
        seq.begin()
        tag = shape(slide, "round", x, ly, tag_w, lh, fill=t["primary"] if on or i == 0 else t["secondary"], radius=0.12)
        shape_text(tag, L["label"], fit_size([L["label"]], tag_w - 0.2, lh - 0.1, 16, 11), BRAND["white"], True)
        card(slide, x + tag_w + 0.12, ly, w - tag_w - 0.12, lh, t, fill=t["soft"] if not on else t["soft2"], shadow=False,
             radius=0.1)
        chips = L.get("items", [])
        if chips:
            m = len(chips)
            cg = 0.12
            cwid = (w - tag_w - 0.12 - 0.3 - cg * (m - 1)) / m
            for j, c in enumerate(chips):
                cx = x + tag_w + 0.27 + j * (cwid + cg)
                chip = shape(slide, "round", cx, ly + 0.14, cwid, lh - 0.28, fill=BRAND["white"], line=t["card_line"], radius=0.18)
                shape_text(chip, c, fit_size([c], cwid - 0.15, lh - 0.35, 13, 9), t["title"], False)
        seq.end("wipe")


REGISTRY = {"process": process, "timeline": timeline, "cycle": cycle, "funnel": funnel, "pyramid": pyramid,
            "matrix": matrix, "hub": hub, "hierarchy": hierarchy, "stairs": stairs, "layers": layers}
