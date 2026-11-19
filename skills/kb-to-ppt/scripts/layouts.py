# -*- coding: utf-8 -*-
"""
页面版式：cover 封面 / agenda 目录 / exec_summary 执行摘要 / section 章节页 / content 内容页 / statement 观点页 /
big_number 大数字页 / summary 总结与行动 / disclaimer 重要提示 / end 结束页。

内容页 = 统一页面框架（章节眉标、标题、副标题、页脚、进度条，可选数据来源脚注与“示例样本”标记）
+ 一个主体元素（26 种图示之一或要点列表）+ 可选的右侧“关键发现”栏和底部“结论条”。
封面、章节页、结束页以留白为主，主色只做强调；装饰由主题的 cover_style 决定：
  light 白底 + 柔和圆形 / line 左侧竖条 / panel 右侧色块（grid 网格 / wave 波浪）/ rings 深色同心圆。
品牌名、颜色、字体、固定文字都取自 tap-config。
"""
import math

from diagrams_biz import REGISTRY as BIZ
from diagrams_data import REGISTRY as DATA
from diagrams_flow import REGISTRY as FLOW, _icon, card
from icons import draw_icon, icon_badge
from ppt_base import BRAND, H, W, background, fit_size, line, poly, set_font, shape, shape_text, text
from ppt_theme import CONF, FONTS, SIZES, G, L as label, R

BODY = {**FLOW, **DATA, **BIZ}
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
         where="第 %d 页标题" % ctx.page, accent=t["highlight"])
    y0 = 1.42
    if spec.get("kicker"):
        text(slide, MX, 1.36, CW, 0.4, spec["kicker"], SIZES["kicker"], BRAND["ink_soft"], min_size=11,
             numbers=True, accent=t["highlight"], where="第 %d 页副标题" % ctx.page)
        y0 = 1.85
    footer(slide, t, ctx)
    bottom = 6.85
    src = spec.get("source") or (spec.get("data") or {}).get("source") if spec.get("type") == "content" else spec.get("source")
    sample = spec.get("sample", ctx.meta.get("sample") and spec.get("layout") in ("case", "coverage", "radar"))
    if src or sample:
        bottom -= 0.24
        if src and not (spec.get("layout") == "table"):            # 表格自带来源行
            text(slide, MX, 6.66, 8.5, 0.26, label("source") + str(src), 9, BRAND["muted"])
        if sample:
            tg = shape(slide, "round", W - MX - 1.1, 6.67, 1.1, 0.24, line=BRAND["red"], line_w=0.75, radius=0.3)
            shape_text(tg, label("sample"), 9, BRAND["red"], True)
    return (MX, y0 + 0.18, CW, bottom - (y0 + 0.18))


def footer(slide, t, ctx, dark=False):
    fg = t["on_dark"] if dark else BRAND["muted"]
    line(slide, MX, 7.02, W - MX, 7.02, t["section_deco"] if dark else BRAND["line"], 0.75)
    if ctx.total:
        prog = (ctx.page - 1) / float(max(ctx.total - 1, 1))
        if prog > 0:
            line(slide, MX, 7.02, MX + CW * prog, 7.02, t["accent"] if dark else t["primary"], 2.25)
    foot = ctx.meta.get("footer") or (CONF.org_name() + label("footer_sep") + ctx.meta.get("short_title", ctx.meta["title"]))
    text(slide, MX, 7.08, 7, 0.28, foot, 9, fg)
    text(slide, W - MX - 1.5, 7.08, 1.5, 0.28, [{"text": "%02d" % ctx.page, "bold": True,
                                                 "color": t["accent"] if dark else t["primary"]},
                                                ], 9.5, fg, align="right", en=FONTS["num"])


# ---------------- 封面装饰 ----------------
def _blob(slide, t, x, y, d, key="cover_deco"):
    if t.get(key + "_grad"):
        g = t[key + "_grad"]
        return shape(slide, "oval", x, y, d, d, gradient=(g[0], g[1], 315))
    return shape(slide, "oval", x, y, d, d, fill=t.get(key) or t["soft"])


def _band(slide, t, x=0, w=None, h=0.1):
    w = W if w is None else w
    if t.get("cover_band_grad"):
        g = t["cover_band_grad"]
        shape(slide, "rect", x, H - h, w, h, gradient=(g[0], g[1], 0))
    elif t.get("cover_band"):
        shape(slide, "rect", x, H - h, w, h, fill=t["cover_band"])


def _panel(slide, t, icon, x0):
    """右侧色块：渐变底 + 网格或波浪 + 白色图标。"""
    pw = W - x0
    g = t["cover_panel"]
    shape(slide, "rect", x0, 0, pw, H, gradient=(g[0], g[1], 300))
    lc = t.get("panel_line", BRAND["white"])
    if t.get("panel_deco") == "grid":
        step = 0.5
        k = 1
        while x0 + k * step < W:
            shape(slide, "rect", x0 + k * step, 0, 0.012, H, fill=lc, alpha=0.16)
            k += 1
        k = 1
        while k * step < H:
            shape(slide, "rect", x0, k * step, pw, 0.012, fill=lc, alpha=0.16)
            k += 1
        shape(slide, "oval", x0 + pw * 0.15, H * 0.12, pw * 0.8, pw * 0.8, fill=lc, alpha=0.14)
    elif t.get("panel_deco") == "wave":
        for i, (amp, base, a) in enumerate(((0.32, H - 1.5, 0.14), (0.26, H - 0.9, 0.18))):
            pts = [(x0 + pw * k / 40.0, base + amp * math.sin(k / 40.0 * math.pi * 2.2 + i * 1.3)) for k in range(41)]
            poly(slide, pts + [(W, H), (x0, H)], fill=lc, alpha=a)
        shape(slide, "oval", x0 + pw * 0.2, H * 0.1, pw * 0.7, pw * 0.7, fill=lc, alpha=0.12)
    s = min(2.6, pw * 0.48)
    draw_icon(slide, icon, x0 + (pw - s) / 2, H * 0.5 - s * 0.62, s, t["cover_icon"], t["cover_icon_cut"])


def _cover_deco(slide, t, icon):
    style = t.get("cover_style", "light")
    if style == "line":
        shape(slide, "rect", 0, 0, 0.32, H, fill=t["primary"])
        shape(slide, "oval", W - 4.6, -1.6, 6.2, 6.2, fill=t.get("cover_deco", t["soft"]))
        draw_icon(slide, icon, W - 3.6, 1.0, 2.6, t["cover_icon"], t["cover_icon_cut"])
    elif style == "rings":
        for r in (5.4, 4.3, 3.2):
            shape(slide, "oval", W - 2.2 - r, H / 2 - r, 2 * r, 2 * r, line=t["cover_accent"], line_w=1.0)
        draw_icon(slide, icon, W - 4.15, H / 2 - 1.0, 2.0, t["cover_icon"], t["cover_icon_cut"])
        _band(slide, t, h=0.12)
    elif style == "panel":
        _panel(slide, t, icon, W * 0.62)
        _band(slide, t, x=MX, w=1.4, h=0.08)
    else:                                       # light：白底，右上大圆 + 右下小圆 + 图标，底部细色带
        _blob(slide, t, W - 5.6, -1.9, 7.6)
        _blob(slide, t, W - 2.5, 4.9, 3.4, "cover_deco2")
        draw_icon(slide, icon, W - 4.35, 1.45, 2.7, t["cover_icon"],
                  t["cover_deco_grad"][0] if t.get("cover_deco_grad") else t["cover_icon_cut"])
        _band(slide, t, h=0.09)


def cover(slide, t, ctx, seq, spec):
    m = ctx.meta
    light = t.get("cover_light", False)
    background(slide, t["cover_bg"])
    fg, ac = t["cover_fg"], t["cover_accent"]
    sub_fg = BRAND["ink_soft"] if light else fg
    x0 = MX + (0.2 if t.get("cover_style") == "line" else 0.1)
    tw = 7.0 if t.get("cover_style") == "panel" else 7.8
    seq.begin()
    _cover_deco(slide, t, spec.get("icon", m.get("cover_icon", "shield")))
    seq.end("fade")
    seq.begin()
    _brand(slide, t, t["primary"] if light else fg, x=x0, y=0.55, align="left")
    if m.get("category"):
        tag = shape(slide, "round", x0, 2.05, 0.3 + 0.19 * len(m["category"]), 0.38, fill=t["cover_tag_bg"], radius=0.5)
        shape_text(tag, m["category"], 12, t["cover_tag_fg"], True)
    seq.end("fade")
    seq.begin()
    ts = fit_size([m["title"]], tw - 0.2, 1.9, SIZES["cover_title"], 28)
    text(slide, x0, 2.6, tw, 1.9, [{"text": m["title"], "bold": True}], ts, fg, anchor="bottom", spacing=1.1)
    if m.get("subtitle"):
        text(slide, x0, 4.6, tw - 0.2, 0.6, m["subtitle"], SIZES["cover_sub"], sub_fg, numbers=True, accent=ac)
    shape(slide, "rect", x0, 5.35, 0.9, 0.07, fill=ac)
    seq.end("float")
    seq.begin()
    info = label("info_sep").join([v for v in (m.get("presenter"), m.get("department"), m.get("date")) if v])
    text(slide, x0, 5.6, tw, 0.4, info, 13, sub_fg)
    if m.get("confidentiality"):
        text(slide, x0, 6.75, 4, 0.3, label("confidentiality") + m["confidentiality"], 10,
             BRAND["muted"] if light else fg)
    seq.end("fade")


# ---------------- 目录：每章一张卡片，显示页数和讲述时长 ----------------
def agenda(slide, t, ctx, seq, spec):
    secs = ctx.sections
    n_sec, total = len(secs), ctx.total_minutes()
    sp = dict(spec, title=spec.get("title") or label("agenda"),
              kicker=spec.get("kicker") or label("agenda_kicker", n=n_sec, m=_m(total)))
    x, y, w, h = chrome(slide, t, ctx, sp)
    cols = n_sec if n_sec <= 4 else 3
    rows = int(math.ceil(n_sec / float(cols)))
    gx, gy = 0.3, 0.3
    cw = (w - gx * (cols - 1)) / cols
    chh = min(3.6, (h - gy * (rows - 1)) / rows)
    for i, s in enumerate(secs):
        r, c = divmod(i, cols)
        cx, cy = x + c * (cw + gx), y + r * (chh + gy)
        pages, mins = ctx.section_stats(s)
        seq.begin()
        card(slide, cx, cy, cw, chh, t, shadow=False)
        shape(slide, "rect", cx, cy, cw, 0.07, fill=t["primary"])
        text(slide, cx + 0.3, cy + 0.3, 2, 0.8, [{"text": "%02d" % (i + 1), "bold": True}], 40, t["primary"], en=FONTS["num"])
        text(slide, cx + 0.3, cy + 1.15, cw - 0.6, 0.5, [{"text": s["title"], "bold": True}], 18, t["title"], min_size=13)
        if s.get("subtitle"):
            text(slide, cx + 0.3, cy + 1.65, cw - 0.6, chh - 2.35, s["subtitle"], 12, BRAND["ink_soft"], min_size=9.5,
                 spacing=1.35)
        line(slide, cx + 0.3, cy + chh - 0.6, cx + cw - 0.3, cy + chh - 0.6, t["card_line"], 0.75, "dash")
        text(slide, cx + 0.3, cy + chh - 0.52, cw - 0.6, 0.36,
             [{"text": label("pages", n=pages) + "　·　" + label("minutes", m=_m(mins)), "bold": True}], 11, BRAND["muted"],
             numbers=True, accent=t["primary"])
        seq.end("float")


def _m(x):
    return max(1, int(math.ceil(x - 0.05)))


# ---------------- 执行摘要：把各页结论串成一页 ----------------
def exec_summary(slide, t, ctx, seq, spec):
    items = spec.get("items") or []
    decisions = spec.get("decisions") or []
    sp = dict(spec, title=spec.get("title") or label("exec_title"),
              kicker=spec.get("kicker") or label("exec_kicker", n=len(items)))
    x, y, w, h = chrome(slide, t, ctx, sp)
    rw = 3.5 if decisions else 0
    lw = w - (rw + 0.35 if rw else 0)
    n = max(len(items), 1)
    rh = min(0.92, h / n)
    for i, it in enumerate(items):
        ry = y + i * rh
        alert = it.get("alert")
        seq.begin()
        card(slide, x, ry + 0.05, lw, rh - 0.1, t, shadow=False)
        num = shape(slide, "oval", x + 0.2, ry + rh / 2 - 0.26, 0.52, 0.52, fill=t["highlight"] if alert and t["highlight"] != t["primary"]
                    else (BRAND["red"] if alert else t["primary"]))
        shape_text(num, str(i + 1), 14, BRAND["white"], True)
        paras = [{"text": it["title"], "bold": True, "size": 15, "color": t["title"]}]
        if it.get("sub"):
            paras.append({"text": it["sub"], "size": 11.5, "color": BRAND["ink_soft"], "numbers": True, "accent": t["primary"]})
        text(slide, x + 0.95, ry + 0.05, lw - 2.1, rh - 0.1, paras, 14, anchor="middle", min_size=9.5, spacing=1.15)
        if it.get("page"):
            text(slide, x + lw - 1.1, ry, 0.9, rh, [{"text": label("go_page", n=it["page"]), "bold": True}], 11,
                 t["primary"], align="right", anchor="middle", en=FONTS["num"])
        seq.end("float")
    if decisions:
        px = x + lw + 0.35
        seq.begin()
        shape(slide, "round", px, y, rw, h, fill=t["soft"], radius=0.05)
        text(slide, px + 0.3, y + 0.25, rw - 0.6, 0.4, [{"text": label("decisions"), "bold": True}], 13, BRAND["ink_soft"])
        tb = text(slide, px + 0.3, y + 0.7, rw - 0.6, 1.0, [{"text": str(len(decisions)), "bold": True, "en": FONTS["num"]}],
                  54, t["primary"])
        r = tb.text_frame.paragraphs[0].add_run()
        set_font(r, 16, True, t["primary"])
        r.text = " " + label("decision_unit")
        paras = [{"text": "%s %s" % (G("circled")[k] if k < len(G("circled")) else "%d." % (k + 1), d if isinstance(d, str) else d.get("text", "")),
                  "space_before": 8} for k, d in enumerate(decisions)]
        text(slide, px + 0.3, y + 1.85, rw - 0.6, h - 2.5, paras, 12.5, BRAND["ink"], min_size=9.5, spacing=1.35)
        if spec.get("decisions_page"):
            text(slide, px + 0.3, y + h - 0.55, rw - 0.6, 0.3, label("see_page", n=spec["decisions_page"]), 10.5, BRAND["muted"])
        seq.end("fade")


# ---------------- 章节页 ----------------
def section(slide, t, ctx, seq, spec):
    background(slide, t["section_bg"])
    fg = t["section_fg"]
    dark = t["section_dark"]
    idx = ctx.section_index(spec)
    seq.begin()
    if dark:
        shape(slide, "oval", -2.0, 3.2, 6.5, 6.5, fill=BRAND["white"], alpha=0.08)
    else:
        shape(slide, "oval", -2.2, 3.6, 6.4, 6.4, fill=t["section_deco"])
        shape(slide, "rect", 0, 0, W, 0.09, fill=t["primary"])
    seq.end("fade")
    seq.begin()
    text(slide, MX + 0.2, 1.6, 4, 1.6, [{"text": "%02d" % idx, "bold": True}], 110, t["section_num"], en=FONTS["num"])
    seq.end("zoom")
    seq.begin()
    text(slide, MX + 0.25, 3.35, 7.5, 1.1, [{"text": spec["title"], "bold": True}], SIZES["section"], fg,
         min_size=28, where="章节页标题")
    if spec.get("subtitle"):
        text(slide, MX + 0.25, 4.45, 7.0, 0.9, spec["subtitle"], 16, t["on_dark_soft"] if dark else BRAND["ink_soft"],
             min_size=12, numbers=True, accent=t["section_num"])
    pages, mins = ctx.section_stats(spec)
    if pages:
        text(slide, MX + 0.25, 5.55, 6, 0.36, label("section_time", n=pages, m=_m(mins)), 11.5,
             t["on_dark"] if dark else BRAND["muted"])
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
             (col if dark else t["title"]) if on else (t["on_dark_soft"] if dark else BRAND["muted"]), anchor="middle", min_size=10)
        if on:
            shape(slide, "rect", 9.22, ny + 0.06, 0.06, 0.3, fill=t["section_num"])
        ny += 0.52
    line(slide, 9.25, 1.9, 9.25, ny - 0.1, t["section_deco"] if dark else BRAND["line"], 0.75)
    seq.end("fade")
    footer(slide, t, ctx, dark=dark)


# ---------------- 内容页 ----------------
def content(slide, t, ctx, seq, spec):
    x, y, w, h = chrome(slide, t, ctx, spec)
    if spec.get("takeaway"):
        h -= 0.74
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
        takeaway(slide, t, seq, (x, y + h + 0.16, w, 0.56), spec["takeaway"])


def takeaway(slide, t, seq, box, s):
    """结论条：浅底 + 左侧主色竖条，数字与加粗部分用强调色。"""
    x, y, w, h = box
    seq.begin()
    shape(slide, "round", x, y, w, h, fill=t["soft"], radius=0.12)
    shape(slide, "rect", x, y, 0.08, h, fill=t["primary"])
    draw_icon(slide, "arrow_right", x + 0.28, y + (h - 0.28) / 2, 0.28, t["primary"], t["soft"])
    text(slide, x + 0.72, y, w - 0.9, h, s, 15, t["title"], True, anchor="middle", min_size=11,
         numbers=True, accent=t["highlight"], where="结论条")
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
         numbers=True, accent=t["highlight"], where="关键发现栏")
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
    text(slide, x + 0.1, y + 1.0, 5.2, 1.9, [{"text": str(spec["value"]), "bold": True, "en": FONTS["num"]}], vs,
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
    """行动卡片（前 3 项，第一项强调）+ 其余行动与“需要决策”列成明细。"""
    x, y, w, h = chrome(slide, t, ctx, spec)
    acts = spec["actions"]
    top = acts[:3] if len(acts) <= 3 or spec.get("cards", True) else []
    rest = acts[len(top):]
    if top:
        n = len(top)
        gx = 0.3
        cw = (w - gx * (n - 1)) / n
        chh = min(2.55, h if not (rest or spec.get("decisions")) else h * 0.56)
        for i, a in enumerate(top):
            cx = x + i * (cw + gx)
            hero = i == 0
            seq.begin()
            card(slide, cx, y, cw, chh, t, fill=t["primary"] if hero else t["card"], shadow=not hero)
            fg, sub = (BRAND["white"], BRAND["white"]) if hero else (t["title"], BRAND["ink_soft"])
            text(slide, cx + 0.3, y + 0.22, 1.5, 0.7, [{"text": "%02d" % (i + 1), "bold": True}], 30,
                 BRAND["white"] if hero else t["primary"], en=FONTS["num"])
            paras = [{"text": a["action"], "bold": True, "size": 16, "color": fg}]
            if a.get("desc"):
                paras.append({"text": a["desc"], "size": 12, "color": sub, "space_before": 4})
            text(slide, cx + 0.3, y + 0.92, cw - 0.6, chh - 1.55, paras, 14, min_size=9.5, spacing=1.25,
                 where="行动“%s”" % a["action"])
            line(slide, cx + 0.3, y + chh - 0.55, cx + cw - 0.3, y + chh - 0.55,
                 BRAND["white"] if hero else t["card_line"], 0.75, "dash")
            who = " ".join(v for v in (a.get("owner"), a.get("due")) if v)
            text(slide, cx + 0.3, y + chh - 0.48, cw - 0.6, 0.34, who, 11, sub, True)
            seq.end("float")
        y += chh + 0.3
        h -= chh + 0.3
    rows = [(a["action"], a.get("owner", ""), a.get("due", ""), a.get("status", "")) for a in rest]
    rows += [(d if isinstance(d, str) else d.get("text", ""), "" if isinstance(d, str) else d.get("owner", ""), "",
              label("decisions")) for d in spec.get("decisions") or []]
    if rows:
        rh = min(0.5, h / (len(rows) + 1))
        seq.begin()
        for i, r in enumerate(rows):
            ry = y + i * rh
            line(slide, x, ry + rh, x + w, ry + rh, t["card_line"], 0.75)
            text(slide, x + 0.1, ry, w * 0.55, rh, r[0], 12.5, BRAND["ink"], anchor="middle", min_size=9.5)
            text(slide, x + w * 0.58, ry, w * 0.18, rh, r[1], 12, BRAND["ink_soft"], anchor="middle", min_size=9.5)
            text(slide, x + w * 0.76, ry, w * 0.12, rh, r[2], 12, BRAND["ink_soft"], anchor="middle", en=FONTS["num"])
            if r[3]:
                chip = shape(slide, "round", x + w - 1.25, ry + rh / 2 - 0.15, 1.2, 0.3,
                             fill=BRAND["red_light"] if r[3] == label("decisions") else t["soft2"], radius=0.5)
                shape_text(chip, r[3], 10, BRAND["red"] if r[3] == label("decisions") else t["title"], True)
        seq.end("fade")


# ---------------- 重要提示（对外版本自动插入） ----------------
def disclaimer(slide, t, ctx, seq, spec):
    background(slide, ("solid", t["bg"]))
    _brand(slide, t, BRAND["ink_soft"])
    items = spec.get("items") or []
    bx, by, bw, bh = 1.1, 0.95, W - 2.2, 5.75
    seq.begin()
    card(slide, bx, by, bw, bh, t, shadow=True)
    shape(slide, "rect", bx, by, bw, 0.07, fill=t["primary"])
    draw_icon(slide, "shield", bx + 0.55, by + 0.5, 0.5, t["primary"], t["card"])
    text(slide, bx + 1.2, by + 0.45, bw - 1.6, 0.6, [{"text": spec.get("title") or label("disclaimer_title"), "bold": True}],
         24, t["title"], anchor="middle")
    paras = [{"text": "%d. %s" % (i + 1, s), "space_before": 9} for i, s in enumerate(items)]
    text(slide, bx + 0.6, by + 1.35, bw - 1.2, bh - 2.0, paras, 15, BRAND["ink"], min_size=11, spacing=1.45,
         accent=t["primary"], where="重要提示")
    text(slide, bx + 0.6, by + bh - 0.55, bw - 1.2, 0.32, label("disclaimer_sig", org=CONF.org_name()), 10.5,
         BRAND["muted"], align="right")
    seq.end("fade")
    footer(slide, t, ctx)


# ---------------- 结束页 ----------------
def end(slide, t, ctx, seq, spec):
    background(slide, t["cover_bg"])
    fg = t["cover_fg"]
    light = t.get("cover_light", False)
    seq.begin()
    if t.get("cover_style") == "panel":
        g = t["cover_panel"]
        shape(slide, "rect", 0, H - 1.1, W, 1.1, gradient=(g[0], g[1], 0))
        shape(slide, "oval", W / 2 - 3.2, H / 2 - 3.6, 6.4, 6.4, fill=t["soft"])
    elif light:
        _blob(slide, t, W / 2 - 3.4, H / 2 - 3.7, 6.8)
        _band(slide, t, h=0.09)
    else:
        shape(slide, "oval", W / 2 - 3.5, H / 2 - 3.5, 7, 7, fill=BRAND["white"], alpha=0.08)
        _band(slide, t, h=0.12)
    seq.end("zoom")
    seq.begin()
    text(slide, 0, 2.2, W, 1.4, [{"text": spec.get("text", label("thanks")), "bold": True}], 54, fg, align="center")
    if spec.get("sub"):
        text(slide, 0, 3.6, W, 0.6, spec["sub"], 18, BRAND["ink_soft"] if light else fg, align="center")
    shape(slide, "rect", W / 2 - 0.45, 4.35, 0.9, 0.07, fill=t["cover_accent"])
    seq.end("float")
    if spec.get("contacts"):
        seq.begin()
        info = label("contact_sep").join(label("contact", label=c["label"], value=c["value"]) for c in spec["contacts"])
        text(slide, 0, 4.75, W, 0.5, info, 13, BRAND["ink_soft"] if light else fg, align="center")
        seq.end("fade")
    _brand(slide, t, t["primary"] if light else fg, x=MX, y=0.55, align="left")


SLIDES = {"cover": cover, "agenda": agenda, "exec_summary": exec_summary, "section": section, "content": content,
          "statement": statement, "big_number": big_number, "summary": summary, "disclaimer": disclaimer, "end": end}
