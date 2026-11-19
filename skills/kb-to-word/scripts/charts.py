# -*- coding: utf-8 -*-
"""
图表与示意图渲染（matplotlib → PNG），供 render_docx.py 调用。

支持 8 种数据图表：
  bar 柱状 / barh 条形 / line 折线 / combo 柱线组合（双轴）/
  stacked 堆叠柱 / donut 环形 / pie 饼图 / highlight 高亮条形（一项主色，其余灰色）
以及 1 种结构图：
  structure 产品责任构成图（根节点 → 若干责任 → 子项）

设计规则（保证“专业而不花哨”）：
  - 只用当前风格的色板（themes.json 的 palette / chart_hi）；单系列图默认用主色，高亮图只用主色 + 灰；负值用警示色
  - 去掉上、右边框，网格线只保留浅色横线
  - 数值标签直接标在图上，减少读者对照坐标轴
  - 字体按 tap-config/brand.json 的字体候选链选本机已安装的；全部找不到时给出明确警告
"""
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib import font_manager                 # noqa: E402
from matplotlib.patches import FancyBboxPatch       # noqa: E402

from themes import BRAND, CHART_PALETTE, FONTS, L, R  # noqa: E402

_FONT_READY = False
PAL = list(CHART_PALETTE)
TH = {}


def use_style(st):
    """渲染前调用：图表配色跟随当前文档风格。"""
    PAL[:] = st.get("palette") or list(CHART_PALETTE)
    TH.clear()
    TH.update({k: st[k] for k in ("accent", "accent_pale", "deep", "chart_hi", "bad")})


def _setup_font():
    global _FONT_READY
    if _FONT_READY:
        return
    available = {f.name.lower() for f in font_manager.fontManager.ttflist}
    chosen = [f for f in FONTS["chart"] if f.lower() in available]
    if not chosen:
        warnings.warn("本机没有安装字体候选链中的任何一种（%s），图表中文可能显示为方块。" % "、".join(FONTS["chart"][:4]) +
                      "请安装其中任意一种，或在 tap-config/brand.json 的 fonts 中加入本机已有的字体。")
    plt.rcParams["font.sans-serif"] = chosen or FONTS["chart"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    _FONT_READY = True


def _c(h):
    return "#" + h.lstrip("#")


def _fmt(v, unit=""):
    if v is None:
        return ""
    if isinstance(v, float) and not v.is_integer():
        s = ("%.1f" % v) if abs(v) < 1000 else "{:,.0f}".format(v)
    else:
        s = "{:,}".format(int(v))
    return s + (unit if unit in ("%", "pct") else "")


def _style_axes(ax, horizontal=False):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(_c(BRAND["line"]))
    ax.spines["bottom"].set_color(_c(BRAND["line"]))
    ax.tick_params(colors=_c(BRAND["ink_soft"]), labelsize=9, length=0)
    if horizontal:
        ax.xaxis.grid(True, color=_c(BRAND["line"]), linewidth=0.6)
    else:
        ax.yaxis.grid(True, color=_c(BRAND["line"]), linewidth=0.6)
    ax.set_axisbelow(True)


def _highlight_index(spec, categories):
    h = spec.get("highlight")
    if h is None:
        return None
    if isinstance(h, int):
        return h
    return categories.index(h) if h in categories else None


def _add_target(ax, spec, horizontal=False):
    t = spec.get("target")
    if not t:
        return
    kw = dict(color=_c(BRAND["red"]), linestyle=(0, (4, 3)), linewidth=1.2)
    if horizontal:
        ax.axvline(t["value"], **kw)
        ax.text(t["value"], ax.get_ylim()[1], " " + t.get("label", L("target")), color=_c(BRAND["red"]),
                fontsize=8, va="bottom")
    else:
        ax.axhline(t["value"], **kw)
        ax.text(ax.get_xlim()[1], t["value"], " " + t.get("label", L("target")), color=_c(BRAND["red"]),
                fontsize=8, va="center")


def render_chart(spec, out_path, width_in=6.3, height_in=3.2):
    """按 spec 生成 PNG，返回路径。spec 字段见 reference/elements.md 的“数据图表”。"""
    _setup_font()
    kind = spec.get("chart", "bar")
    cats = spec.get("categories", [])
    series = spec.get("series", [])
    unit = spec.get("unit", "")

    if kind in ("donut", "pie"):
        fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=R("chart_dpi"))
        values = series[0]["values"]
        colors = [_c(PAL[i % len(PAL)]) for i in range(len(values))]
        wedge_kw = dict(width=0.38, edgecolor="white", linewidth=2) if kind == "donut" \
            else dict(edgecolor="white", linewidth=2)
        wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                           wedgeprops=wedge_kw)
        total = float(sum(values)) or 1.0
        labels = ["%s  %.0f%%" % (c, v * 100.0 / total) for c, v in zip(cats, values)]
        ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
                  fontsize=9, labelcolor=_c(BRAND["ink"]))
        if kind == "donut" and spec.get("center_text"):
            ax.text(0, 0.08, spec["center_text"], ha="center", va="center", fontsize=16,
                    fontweight="bold", color=_c(BRAND["ink"]))
            if spec.get("center_label"):
                ax.text(0, -0.18, spec["center_label"], ha="center", va="center", fontsize=8.5,
                        color=_c(BRAND["muted"]))
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return out_path

    horizontal = kind in ("barh", "highlight")
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=R("chart_dpi"))
    _style_axes(ax, horizontal)
    n = len(series)
    hi = _highlight_index(spec, cats)
    if kind == "highlight" and hi is None and series:
        vals = [v if v is not None else float("-inf") for v in series[0]["values"]]
        hi = vals.index(max(vals))          # 未指定高亮项时，默认高亮最大值
    idx = list(range(len(cats)))

    if kind in ("bar", "barh", "highlight"):
        total_w = 0.72
        w = total_w / max(n, 1)
        for si, s in enumerate(series):
            offs = [i - total_w / 2 + w * (si + 0.5) for i in idx]
            if kind == "highlight" or (hi is not None and n == 1):
                colors = [_c(TH["chart_hi"]) if i == hi else _c(BRAND["grey_bar"]) for i in idx]
            else:
                colors = _c(PAL[si % len(PAL)])
            if n == 1:
                # 单系列：负值（如同比下降）用警示色
                base = colors if isinstance(colors, list) else [colors] * len(idx)
                colors = [_c(TH["bad"]) if (v is not None and v < 0) else c for v, c in zip(s["values"], base)]
            if horizontal:
                bars = ax.barh(offs, s["values"], height=w * 0.9, color=colors, label=s.get("name"))
            else:
                bars = ax.bar(offs, s["values"], width=w * 0.9, color=colors, label=s.get("name"))
            for b, v in zip(bars, s["values"]):
                if v is None:
                    continue
                neg = v < 0
                if horizontal:
                    ax.text(b.get_x() + b.get_width(), b.get_y() + b.get_height() / 2,
                            (_fmt(v, unit) + " ") if neg else (" " + _fmt(v, unit)),
                            va="center", ha="right" if neg else "left", fontsize=8,
                            color=_c(TH["bad"] if neg else BRAND["ink_soft"]))
                else:
                    ax.text(b.get_x() + b.get_width() / 2, b.get_y() + b.get_height(), _fmt(v, unit),
                            ha="center", va="top" if neg else "bottom", fontsize=8,
                            color=_c(TH["bad"] if neg else BRAND["ink_soft"]))
        if any(v is not None and v < 0 for s in series for v in s["values"]):
            (ax.axvline if horizontal else ax.axhline)(0, color=_c(BRAND["grey_mid"]), linewidth=0.8)
        if horizontal:
            ax.set_yticks(idx)
            ax.set_yticklabels(cats)
            ax.invert_yaxis()
        else:
            ax.set_xticks(idx)
            ax.set_xticklabels(cats)

    elif kind == "stacked":
        bottom = [0] * len(cats)
        for si, s in enumerate(series):
            ax.bar(idx, s["values"], width=0.6, bottom=bottom,
                   color=_c(PAL[si % len(PAL)]), label=s.get("name"),
                   edgecolor="white", linewidth=0.8)
            bottom = [b + (v or 0) for b, v in zip(bottom, s["values"])]
        for i, t in zip(idx, bottom):
            ax.text(i, t, _fmt(t, unit), ha="center", va="bottom", fontsize=8,
                    color=_c(BRAND["ink"]), fontweight="bold")
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)

    elif kind == "line":
        for si, s in enumerate(series):
            color = _c(PAL[si % len(PAL)])
            ax.plot(idx, s["values"], color=color, linewidth=2.2, marker="o", markersize=5,
                    markerfacecolor="white", markeredgewidth=1.8, label=s.get("name"))
            last = len(s["values"]) - 1
            ax.text(last, s["values"][last], "  " + _fmt(s["values"][last], unit), va="center",
                    fontsize=8.5, color=color, fontweight="bold")
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)

    elif kind == "combo":
        s0 = series[0]
        bars = ax.bar(idx, s0["values"], width=0.55, color=_c(TH["chart_hi"]), label=s0.get("name"))
        for b, v in zip(bars, s0["values"]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), _fmt(v), ha="center",
                    va="bottom", fontsize=8, color=_c(BRAND["ink_soft"]))
        sec = spec.get("secondary") or (series[1] if len(series) > 1 else None)
        if sec:
            ax2 = ax.twinx()
            ax2.plot(idx, sec["values"], color=_c(TH["deep"]), linewidth=2, marker="o",
                     markersize=5, markerfacecolor="white", markeredgewidth=1.6, label=sec.get("name"))
            for i, v in zip(idx, sec["values"]):
                ax2.annotate(_fmt(v, sec.get("unit", "")), (i, v), xytext=(0, 7),
                             textcoords="offset points", ha="center", fontsize=8,
                             color=_c(TH["deep"]), fontweight="bold")
            for side in ("top", "left"):
                ax2.spines[side].set_visible(False)
            ax2.spines["right"].set_color(_c(BRAND["line"]))
            ax2.tick_params(colors=_c(BRAND["ink_soft"]), labelsize=9, length=0)
            lo, hi_ = min(sec["values"]), max(sec["values"])
            pad = (hi_ - lo) * 0.6 or abs(hi_) * 0.3 or 1
            ax2.set_ylim(lo - pad * 1.5, hi_ + pad)
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=8.5, ncol=2)
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)
    else:
        raise ValueError("未知图表类型：%s" % kind)

    _add_target(ax, spec, horizontal)
    if unit and unit not in ("%", "pct"):
        (ax.set_xlabel if horizontal else ax.set_ylabel)(unit, fontsize=8.5, color=_c(BRAND["muted"]))
    if n > 1 and kind not in ("combo",):
        ax.legend(loc="upper left", frameon=False, fontsize=8.5, ncol=min(n, 4))
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def render_structure(spec, out_path, width_in=6.3):
    """产品责任构成图：root → children(name, note, items[])。"""
    _setup_font()
    children = spec.get("children", [])
    n = max(len(children), 1)
    max_items = max([len(c.get("items", [])) for c in children] + [0])
    height_in = 1.9 + 0.32 * max_items
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=R("chart_dpi"))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def box(x, y, w, h, fc, ec, text, color, size=9, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.6",
                                    fc=_c(fc), ec=_c(ec), lw=1.2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
                color=_c(color), fontweight="bold" if bold else "normal", wrap=True)

    root_w, root_h = 34, 14
    root_y = 82
    box(50 - root_w / 2, root_y, root_w, root_h, TH["accent"], TH["accent"],
        spec.get("root", L("product_default")), BRAND["white"], 10.5, True)

    gap = 2.5
    cw = (100 - gap * (n - 1)) / n
    cy = 56
    ch = 15
    ax.plot([50, 50], [root_y, cy + ch + 6], color=_c(BRAND["muted"]), lw=1)
    xs = [i * (cw + gap) + cw / 2 for i in range(n)]
    if n > 1:
        ax.plot([xs[0], xs[-1]], [cy + ch + 6, cy + ch + 6], color=_c(BRAND["muted"]), lw=1)
    for i, c in enumerate(children):
        x = i * (cw + gap)
        ax.plot([xs[i], xs[i]], [cy + ch + 6, cy + ch], color=_c(BRAND["muted"]), lw=1)
        label = c.get("name", "")
        if c.get("note"):
            label += "\n" + c["note"]
        box(x, cy, cw, ch, TH["accent_pale"], TH["accent"], label, BRAND["ink"], 8.5, True)
        items = c.get("items", [])
        step = min(10, 50 / max(len(items), 1))
        for j, it in enumerate(items):
            iy = cy - 6 - (j + 1) * step
            ax.text(x + 1.5, iy + step / 2, "• " + it, fontsize=7.8, color=_c(BRAND["ink_soft"]),
                    va="center")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def safe_name(s, i):
    keep = "".join(ch for ch in str(s) if ch.isalnum())[:20]
    return "fig_%02d_%s.png" % (i, keep or "chart")


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p
