# -*- coding: utf-8 -*-
"""
页面版式：cover 封面 / agenda 目录 / section 章节页 / content 内容页 / statement 观点页 /
big_number 大数字页 / summary 总结与行动 / end 结束页。

内容页 = 统一页面框架（章节眉标、标题、副标题、页脚、进度条）+ 一个主体元素（18 种图示之一或要点列表）
+ 可选的右侧“关键发现”栏和底部“结论条”。
品牌名、颜色、字体、固定文字都取自 tap-config；封面装饰由主题的 cover_style 决定。
"""
from diagrams_data import REGISTRY as DATA
from diagrams_flow import REGISTRY as FLOW, _icon, card
from icons import draw_icon, icon_badge
from ppt_base import BRAND, H, W, background, fit_size, line, set_font, shape, shape_text, text
from ppt_theme import CONF, FONTS, SIZES, G, L as label, R

BODY = {**FLOW, **DATA}
MX = R("slide")["margin_in"]               # 左右边距
CW = W - 2 * MX


def _brand(slide, t, color=None, x=None, y=0.32, align="right"):
    """品牌标识：机构名 + 简称（brand.json 的 org.name / org.short）。"""
    tb = text(slide, x if x is not None else W - MX - 2.6, y, 2.6, 0.3,
              [{"text": CONF.org_name() + " ", "bold": True, "color": color or t["primary"]}], 10.5, align=align)
    if CONF.org_short():
        r = tb.text_frame.paragraphs[0].add_run()
        set_font(r, 10.5, True, color or BRAND["muted"], FONTS["num"])
        r.text = CONF.org_short()
    return tb


def chrome(slide, t, ctx, spec):
    """内容页框架。返回主体区域 (x, y, w, h)。"""
    background(slide, ("solid", t["bg"]))
    sec = ctx.section_label(spec)
    if sec:
        shape(slide, "rect", MX, 0.42, 0.06, 0.24, fill=t["primary"])
        text(slide, MX + 0.14, 0.36, 6, 0.34, [{"text": sec, "bold": True}], 11.5, t["primary"])
    _brand(slide, t, BRAND["ink_soft"])
    ts = fit_size([spec["title"]], CW - 0.2, 0.62, SIZES["title"], SIZES["title_min"])
    text(slide, MX, 0.7, CW, 0.66, [{"text": spec["title"], "bold": True}], ts, t["title"], anchor="middle",
         where="第 %d 页标题" % ctx.page)
    y0 = 1.42
    if spec.get("kicker"):
        text(slide, MX, 1.36, CW, 0.4, spec["kicker"], SIZES["kicker"], BRAND["ink_soft"], min_size=11,
             numbers=True, accent=t["primary"], where="第 %d 页副标题" % ctx.page)
        y0 = 1.85
    footer(slide, t, ctx)
    return (MX, y0 + 0.18, CW, 6.85 - (y0 + 0.18))


def footer(slide, t, ctx, dark=False):
    fg = t["on_dark"] if dark else BRAND["muted"]
    line(slide, MX, 7.02, W - MX, 7.02, BRAND["white"] if dark else BRAND["line"], 0.75)
    if ctx.total:
        prog = (ctx.page - 1) / float(max(ctx.total - 1, 1))
        if prog > 0:
            line(slide, MX, 7.02, MX + CW * prog, 7.02, t["accent"] if dark else t["primary"], 2.25)
    foot = ctx.meta.get("footer") or (CONF.org_name() + label("footer_sep") + ctx.meta.get("short_title", ctx.meta["title"]))
    text(slide, MX, 7.08, 7, 0.28, foot, 9, fg)
    text(slide, W - MX - 1.5, 7.08, 1.5, 0.28, [{"text": "%02d" % ctx.page, "bold": True,
                                                 "color": t["accent"] if dark else t["primary"]},
                                                ], 9.5, fg, align="right", en=FONTS["num"])


# ---------------- 封面 ----------------
def _cover_deco(slide, t, icon):
    """封面装饰。cover_style：line 左侧竖条 + 浅色圆 / rings 同心圆线 / glow 半透明圆 + 大图标。"""
    style = t.get("cover_style", "glow")
    if style == "line":
        shape(slide, "rect", 0, 0, 0.32, H, fill=t["primary"])
        shape(slide, "oval", W - 4.6, -1.6, 6.2, 6.2, fill=t.get("cover_deco", t["soft"]))
        draw_icon(slide, icon, W - 3.6, 1.0, 2.6, t["cover_icon"], t["cover_icon_cut"])
    elif style == "rings":
        for r in (5.4, 4.3, 3.2):
            shape(slide, "oval", W - 2.2 - r, H / 2 - r, 2 * r, 2 * r, line=t["cover_accent"], line_w=1.0)
        draw_icon(slide, icon, W - 4.15, H / 2 - 1.0, 2.0, t["cover_icon"], t["cover_icon_cut"])
        if t.get("cover_band"):
            shape(slide, "rect", 0, H - 0.12, W, 0.12, fill=t["cover_band"])
    else:
        shape(slide, "oval", W - 5.2, -2.2, 7.4, 7.4, fill=BRAND["white"], alpha=0.10)
        shape(slide, "oval", W - 3.0, 3.6, 5.0, 5.0, fill=BRAND["white"], alpha=0.08)
        draw_icon(slide, icon, W - 4.3, 1.55, 3.0, t["cover_icon"], t["cover_icon_cut"])


def cover(slide, t, ctx, seq, spec):
    m = ctx.meta
    light = t.get("cover_style") == "line"          # 白底封面：文字用深色
    background(slide, t["cover_bg"])
    fg, ac = t["cover_fg"], t["cover_accent"]
    sub_fg = BRAND["ink_soft"] if light else fg
    x0 = MX + (0.2 if light else 0)
    seq.begin()
    _cover_deco(slide, t, spec.get("icon", m.get("cover_icon", "shield")))
    seq.end("fade")
    seq.begin()
    _brand(slide, t, t["primary"] if light else fg, x=x0, y=0.55, align="left")
    if m.get("category"):
        tag = shape(slide, "round", x0, 2.05, 0.3 + 0.19 * len(m["category"]), 0.38,
                    fill=t["soft2"] if light else ac, radius=0.5)
        shape_text(tag, m["category"], 12, t["primary"] if light else BRAND["ink"], True)
    seq.end("fade")
    seq.begin()
    ts = fit_size([m["title"]], 7.6, 1.9, SIZES["cover_title"], 28)
    text(slide, x0, 2.6, 7.8, 1.9, [{"text": m["title"], "bold": True}], ts, fg, anchor="bottom", spacing=1.1)
    if m.get("subtitle"):
        text(slide, x0, 4.6, 7.6, 0.6, m["subtitle"], SIZES["cover_sub"], sub_fg)
    shape(slide, "rect", x0, 5.35, 0.9, 0.07, fill=ac)
    seq.end("float")
    seq.begin()
    info = label("info_sep").join([v for v in (m.get("presenter"), m.get("department"), m.get("date")) if v])
    text(slide, x0, 5.6, 8, 0.4, info, 13, sub_fg)
    if m.get("confidentiality"):
        text(slide, x0, 6.75, 4, 0.3, label("confidentiality") + m["confidentiality"], 10,
             BRAND["muted"] if light else fg)
    seq.end("fade")


# ---------------- 目录 ----------------
def agenda(slide, t, ctx, seq, spec):
    background(slide, ("solid", t["bg"]))
    secs = ctx.sections
    seq.begin()
    shape(slide, "rect", 0, 0, 4.3, H, fill=t["primary"] if t["filled"] else t["soft"])
    fg = BRAND["white"] if t["filled"] else t["title"]
    text(slide, MX, 2.4, 3.4, 1.0, [{"text": spec.get("title", label("agenda")), "bold": True}], 40, fg)
    text(slide, MX, 3.35, 3.4, 0.5, label("contents"), 16, t["accent"] if t["filled"] else t["primary"], True,
         en=FONTS["num"])
    shape(slide, "rect", MX, 4.0, 0.7, 0.06, fill=t["accent"] if t["filled"] else t["primary"])
    seq.end("fade")
    n = len(secs)
    top, bottom = 1.0, 6.6
    rh = min(1.05, (bottom - top) / max(n, 1))
    y0 = top + ((bottom - top) - rh * n) / 2
    for i, s in enumerate(secs):
        y = y0 + i * rh
        seq.begin()
        text(slide, 5.0, y, 1.1, rh, [{"text": "%02d" % (i + 1), "bold": True}], 30, t["primary"], anchor="middle", en=FONTS["num"])
        text(slide, 6.2, y, 5.6, rh * 0.62, [{"text": s["title"], "bold": True}], 20, t["title"], anchor="bottom", min_size=14)
        if s.get("subtitle"):
            text(slide, 6.2, y + rh * 0.6, 5.6, rh * 0.38, s["subtitle"], 12, BRAND["muted"], min_size=10)
        line(slide, 5.0, y + rh - 0.02, W - MX, y + rh - 0.02, BRAND["line"], 0.75)
        seq.end("float")
    footer(slide, t, ctx)


# ---------------- 章节页 ----------------
def section(slide, t, ctx, seq, spec):
    background(slide, t["section_bg"])
    fg = t["section_fg"]
    dark = t["section_dark"]
    idx = ctx.section_index(spec)
    seq.begin()
    shape(slide, "oval", -2.0, 3.2, 6.5, 6.5, fill=BRAND["white"] if dark else t["soft2"], alpha=0.08 if dark else 0.6)
    seq.end("fade")
    seq.begin()
    text(slide, MX + 0.2, 1.6, 4, 1.6, [{"text": "%02d" % idx, "bold": True}], 110, t["section_num"], en=FONTS["num"])
    seq.end("zoom")
    seq.begin()
    text(slide, MX + 0.25, 3.35, 7.5, 1.1, [{"text": spec["title"], "bold": True}], SIZES["section"], fg,
         min_size=28, where="章节页标题")
    if spec.get("subtitle"):
        text(slide, MX + 0.25, 4.45, 7.0, 0.9, spec["subtitle"], 16, fg if dark else BRAND["ink_soft"], min_size=12)
    seq.end("float")
    # 右侧章节导航：当前章节高亮
    seq.begin()
    secs = ctx.sections
    ny = 1.9
    for i, s in enumerate(secs, 1):
        on = i == idx
        col = (t["section_num"] if on else (BRAND["white"] if dark else BRAND["muted"]))
        text(slide, 9.4, ny, 0.6, 0.42, [{"text": "%02d" % i, "bold": True}], 13, col, en=FONTS["num"], anchor="middle")
        text(slide, 10.0, ny, 2.8, 0.42, [{"text": s["title"], "bold": on}], 13.5 if on else 12.5,
             col if on else (t["on_dark_soft"] if dark else BRAND["muted"]), anchor="middle", min_size=10)
        ny += 0.52
    line(slide, 9.25, 1.9, 9.25, ny - 0.1, BRAND["white"] if dark else BRAND["line"], 0.75)
    seq.end("fade")
    footer(slide, t, ctx, dark=dark)


# ---------------- 内容页 ----------------
def content(slide, t, ctx, seq, spec):
    x, y, w, h = chrome(slide, t, ctx, spec)
    if spec.get("takeaway"):
        h -= 0.78
    side = spec.get("insight")
    if side:
        pw = 3.45
        w_body = w - pw - 0.35
    else:
        w_body = w
    layout = spec["layout"]
    data = spec.get("data", spec)
    if layout == "bullets":
        bullets(slide, t, seq, (x, y, w_body, h), data)
    elif layout == "columns":
        columns(slide, t, seq, (x, y, w_body, h), data)
    else:
        BODY[layout](slide, t, seq, (x, y, w_body, h), data)
    if side:
        insight(slide, t, seq, (x + w_body + 0.35, y, pw, h), side)
    if spec.get("takeaway"):
        seq.begin()
        bar = shape(slide, "round", x, y + h + 0.18, w, 0.6, fill=t["primary"] if t["filled"] else t["soft"],
                    radius=0.18)
        fg = BRAND["white"] if t["filled"] else t["title"]
        draw_icon(slide, "arrow_right", x + 0.25, y + h + 0.33, 0.3, t["accent"] if t["filled"] else t["primary"],
                  t["primary"] if t["filled"] else t["soft"])
        text(slide, x + 0.72, y + h + 0.18, w - 0.9, 0.6, spec["takeaway"], 15, fg, True, anchor="middle", min_size=11,
             numbers=True, accent=t["accent"] if t["filled"] else t["primary"], where="结论条")
        seq.end("wipe")


def insight(slide, t, seq, box, side):
    x, y, w, h = box
    seq.begin()
    card(slide, x, y, w, h, t, fill=t["soft"], line_color=t["soft"], shadow=False)
    shape(slide, "rect", x, y, 0.07, h, fill=t["primary"])
    draw_icon(slide, "bulb", x + 0.3, y + 0.3, 0.34, t["primary"], t["soft"])
    text(slide, x + 0.75, y + 0.26, w - 0.9, 0.42, [{"text": side.get("title", label("key_findings")), "bold": True}], 15, t["title"])
    items = side.get("items", [])
    paras = [{"text": it, "space_before": 10} for it in items]
    text(slide, x + 0.3, y + 0.85, w - 0.5, h - 1.05, paras, 13, BRAND["ink"], min_size=9.5, spacing=1.3,
         numbers=True, accent=t["primary"], where="关键发现栏")
    seq.end("float")


def bullets(slide, t, seq, box, d):
    """要点：每条可带标题和说明，自动配图标；超过 4 条分两列。"""
    x, y, w, h = box
    pts = d.get("points") or d.get("items")
    pts = [{"title": p} if isinstance(p, str) else p for p in pts]
    n = len(pts)
    cols = 2 if n > 4 else 1
    per = (n + cols - 1) // cols
    gx = 0.4
    cw = (w - gx * (cols - 1)) / cols
    rh = min(1.25, h / per)
    used = set()
    for i, p in enumerate(pts):
        c, r = divmod(i, per)
        px, py = x + c * (cw + gx), y + r * rh
        seq.begin()
        ic = _icon(p, used)
        used.add(ic)
        icon_badge(slide, ic, px, py + 0.06, 0.62, t["soft2"], t["primary"])
        paras = [{"text": p["title"], "bold": True, "size": 16.5, "color": t["title"]}]
        if p.get("desc"):
            paras.append({"text": p["desc"], "size": 13, "color": BRAND["ink_soft"], "numbers": True,
                          "accent": t["primary"], "space_before": 3})
        text(slide, px + 0.85, py, cw - 0.9, rh - 0.12, paras, 15, min_size=9.5, spacing=1.2,
             where="要点“%s”" % p["title"])
        seq.end("float")


def columns(slide, t, seq, box, d):
    x, y, w, h = box
    cols = d["columns"]
    n = len(cols)
    gx = 0.3
    cw = (w - gx * (n - 1)) / n
    for i, c in enumerate(cols):
        cx = x + i * (cw + gx)
        seq.begin()
        card(slide, cx, y, cw, h, t)
        hd = shape(slide, "round_top", cx, y, cw, 0.66, fill=t["primary"] if c.get("highlight") or i == 0 and n == 1
                   else (t["secondary"] if i % 2 else t["primary"]), radius=0.16)
        shape_text(hd, c["title"], 16, BRAND["white"], True)
        text(slide, cx + 0.28, y + 0.85, cw - 0.5, h - 1.05, [G("dot") + " " + s for s in c.get("items", [])], 13.5, BRAND["ink"],
             min_size=9.5, spacing=1.3, numbers=True, accent=t["primary"], where="分栏“%s”" % c["title"])
        seq.end("float")


# ---------------- 观点页 ----------------
def statement(slide, t, ctx, seq, spec):
    background(slide, ("solid", t["soft"]))
    seq.begin()
    text(slide, MX + 0.6, 1.1, 2, 1.6, G("quote_open"), 150, t["primary"], True, en=FONTS["quote"])
    seq.end("zoom")
    seq.begin()
    ts = fit_size([spec["text"]], 10.6, 2.6, 34, 22)
    text(slide, MX + 1.0, 2.35, 10.8, 2.7, [{"text": spec["text"], "bold": True}], ts, t["title"], anchor="middle",
         spacing=1.25, numbers=True, accent=t["primary"])
    seq.end("float")
    if spec.get("sub"):
        seq.begin()
        shape(slide, "rect", MX + 1.05, 5.3, 0.8, 0.06, fill=t["primary"])
        text(slide, MX + 1.0, 5.5, 10.5, 0.8, spec["sub"], 15, BRAND["ink_soft"], min_size=11)
        seq.end("fade")
    footer(slide, t, ctx)


# ---------------- 大数字页 ----------------
def big_number(slide, t, ctx, seq, spec):
    x, y, w, h = chrome(slide, t, ctx, spec)
    seq.begin()
    shape(slide, "oval", x - 0.4, y - 0.1, 5.6, 5.6, fill=t["soft"])
    vs = fit_size([str(spec["value"])], 5.0, 1.9, 120, 60)
    tb = text(slide, x + 0.1, y + 1.0, 5.2, 1.9, [{"text": str(spec["value"]), "bold": True, "en": FONTS["num"]}], vs,
              t["primary"], align="center", anchor="bottom")
    if spec.get("unit"):
        text(slide, x + 0.1, y + 2.9, 5.2, 0.5, [{"text": spec["unit"], "bold": True}], 20, t["title"], align="center")
    text(slide, x + 0.3, y + 3.45, 4.8, 0.8, spec.get("label", ""), 15, BRAND["ink_soft"], align="center", min_size=11)
    seq.end("zoom")
    pts = spec.get("points", [])
    for i, p in enumerate(pts):
        p = {"title": p} if isinstance(p, str) else p
        py = y + 0.3 + i * min(1.35, (h - 0.3) / max(len(pts), 1))
        seq.begin()
        shape(slide, "rect", x + 6.0, py, 0.07, 0.95, fill=t["primary"] if i == 0 else t["soft2"])
        paras = [{"text": p["title"], "bold": True, "size": 17, "color": t["title"]}]
        if p.get("desc"):
            paras.append({"text": p["desc"], "size": 13, "color": BRAND["ink_soft"], "numbers": True,
                          "accent": t["primary"]})
        text(slide, x + 6.3, py - 0.05, w - 6.4, 1.1, paras, 15, min_size=10, spacing=1.2)
        seq.end("float")


# ---------------- 总结与行动 ----------------
def summary(slide, t, ctx, seq, spec):
    x, y, w, h = chrome(slide, t, ctx, spec)
    acts = spec["actions"]
    n = len(acts)
    rh = min(1.0, h / n)
    for i, a in enumerate(acts):
        ry = y + i * rh
        seq.begin()
        card(slide, x, ry + 0.06, w, rh - 0.12, t, shadow=False)
        num = shape(slide, "oval", x + 0.22, ry + rh / 2 - 0.28, 0.56, 0.56, fill=t["primary"])
        shape_text(num, str(i + 1), 15, BRAND["white"], True)
        paras = [{"text": a["action"], "bold": True, "size": 15.5, "color": t["title"]}]
        if a.get("desc"):
            paras.append({"text": a["desc"], "size": 12, "color": BRAND["ink_soft"]})
        text(slide, x + 1.0, ry + 0.06, w - 4.7, rh - 0.12, paras, 14, anchor="middle", min_size=9.5, spacing=1.15)
        if a.get("owner"):
            chip = shape(slide, "round", x + w - 3.55, ry + rh / 2 - 0.2, 1.7, 0.4, fill=t["soft2"], radius=0.5)
            shape_text(chip, a["owner"], 11.5, t["title"], True)
        if a.get("due"):
            chip = shape(slide, "round", x + w - 1.75, ry + rh / 2 - 0.2, 1.5, 0.4, fill=t["accent"] if t["filled"] else t["soft"], radius=0.5)
            shape_text(chip, a["due"], 11.5, BRAND["ink"], True)
        seq.end("float")


# ---------------- 结束页 ----------------
def end(slide, t, ctx, seq, spec):
    background(slide, t["cover_bg"])
    fg = t["cover_fg"]
    seq.begin()
    shape(slide, "oval", W / 2 - 3.5, H / 2 - 3.5, 7, 7, fill=BRAND["white"] if t["filled"] else t["soft"],
          alpha=0.08 if t["filled"] else 0.9)
    seq.end("zoom")
    seq.begin()
    text(slide, 0, 2.4, W, 1.4, [{"text": spec.get("text", label("thanks")), "bold": True}], 54, fg, align="center")
    if spec.get("sub"):
        text(slide, 0, 3.8, W, 0.6, spec["sub"], 18, fg if t["filled"] else BRAND["ink_soft"], align="center")
    shape(slide, "rect", W / 2 - 0.45, 4.55, 0.9, 0.07, fill=t["cover_accent"])
    seq.end("float")
    if spec.get("contacts"):
        seq.begin()
        info = label("contact_sep").join(label("contact", label=c["label"], value=c["value"]) for c in spec["contacts"])
        text(slide, 0, 5.0, W, 0.5, info, 13, fg if t["filled"] else BRAND["ink_soft"], align="center")
        seq.end("fade")


SLIDES = {"cover": cover, "agenda": agenda, "section": section, "content": content, "statement": statement,
          "big_number": big_number, "summary": summary, "end": end}
