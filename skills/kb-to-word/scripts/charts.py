# -*- coding: utf-8 -*-
"""
图表与示意图渲染（matplotlib → PNG），供 render_docx.py 调用。

支持 8 种数据图表：
  bar 柱状 / barh 条形 / line 折线 / combo 柱线组合（双轴）/
  stacked 堆叠柱 / donut 环形 / pie 饼图 / highlight 高亮条形（一项橙色，其余灰色）
以及 1 种结构图：
  structure 产品责任构成图（根节点 → 若干责任 → 子项）

设计规则（保证“专业而不花哨”）：
  - 只用品牌色板；单系列图默认用主色，高亮图只用主色 + 灰
  - 去掉上、右边框，网格线只保留浅色横线
  - 数值标签直接标在图上，减少读者对照坐标轴
  - 中文字体按 FONTS["chart"] 顺序回退；全部找不到时给出明确警告
"""
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib import font_manager                 # noqa: E402
from matplotlib.patches import FancyBboxPatch       # noqa: E402

from themes import BRAND, CHART_PALETTE, FONTS      # noqa: E402

_FONT_READY = False


def _setup_font():
    global _FONT_READY
    if _FONT_READY:
        return
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = [f for f in FONTS["chart"] if f in available]
    if not chosen:
        warnings.warn("未找到中文字体（微软雅黑/苹方/思源黑体等），图表中文可能显示为方块。"
                      "请安装其中任意一种后删除 matplotlib 字体缓存重试。")
    plt.rcParams["font.sans-serif"] = chosen + ["DejaVu Sans"]
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
        ax.text(t["value"], ax.get_ylim()[1], " " + t.get("label", "目标"), color=_c(BRAND["red"]),
                fontsize=8, va="bottom")
    else:
        ax.axhline(t["value"], **kw)
        ax.text(ax.get_xlim()[1], t["value"], " " + t.get("label", "目标"), color=_c(BRAND["red"]),
                fontsize=8, va="center")


def render_chart(spec, out_path, width_in=6.3, height_in=3.2):
    """按 spec 生成 PNG，返回路径。spec 字段见 reference/elements.md 的“数据图表”。"""
    _setup_font()
    kind = spec.get("chart", "bar")
    cats = spec.get("categories", [])
    series = spec.get("series", [])
    unit = spec.get("unit", "")

    if kind in ("donut", "pie"):
        fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=200)
        values = series[0]["values"]
        colors = [_c(CHART_PALETTE[i % len(CHART_PALETTE)]) for i in range(len(values))]
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
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=200)
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
                colors = [_c(BRAND["orange"]) if i == hi else _c("C9CDD1") for i in idx]
            else:
                colors = _c(CHART_PALETTE[si % len(CHART_PALETTE)])
            if horizontal:
                bars = ax.barh(offs, s["values"], height=w * 0.9, color=colors, label=s.get("name"))
            else:
                bars = ax.bar(offs, s["values"], width=w * 0.9, color=colors, label=s.get("name"))
            for b, v in zip(bars, s["values"]):
                if v is None:
                    continue
                if horizontal:
                    ax.text(b.get_width(), b.get_y() + b.get_height() / 2, " " + _fmt(v, unit),
                            va="center", fontsize=8, color=_c(BRAND["ink_soft"]))
                else:
                    ax.text(b.get_x() + b.get_width() / 2, b.get_height(), _fmt(v, unit),
                            ha="center", va="bottom", fontsize=8, color=_c(BRAND["ink_soft"]))
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
                   color=_c(CHART_PALETTE[si % len(CHART_PALETTE)]), label=s.get("name"),
                   edgecolor="white", linewidth=0.8)
            bottom = [b + (v or 0) for b, v in zip(bottom, s["values"])]
        for i, t in zip(idx, bottom):
            ax.text(i, t, _fmt(t, unit), ha="center", va="bottom", fontsize=8,
                    color=_c(BRAND["ink"]), fontweight="bold")
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)

    elif kind == "line":
        for si, s in enumerate(series):
            color = _c(CHART_PALETTE[si % len(CHART_PALETTE)])
            ax.plot(idx, s["values"], color=color, linewidth=2.2, marker="o", markersize=5,
                    markerfacecolor="white", markeredgewidth=1.8, label=s.get("name"))
            last = len(s["values"]) - 1
            ax.text(last, s["values"][last], "  " + _fmt(s["values"][last], unit), va="center",
                    fontsize=8.5, color=color, fontweight="bold")
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)

    elif kind == "combo":
        s0 = series[0]
        bars = ax.bar(idx, s0["values"], width=0.55, color=_c(BRAND["orange"]), label=s0.get("name"))
        for b, v in zip(bars, s0["values"]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), _fmt(v), ha="center",
                    va="bottom", fontsize=8, color=_c(BRAND["ink_soft"]))
        sec = spec.get("secondary") or (series[1] if len(series) > 1 else None)
        if sec:
            ax2 = ax.twinx()
            ax2.plot(idx, sec["values"], color=_c(BRAND["green"]), linewidth=2, marker="o",
                     markersize=5, markerfacecolor="white", markeredgewidth=1.6, label=sec.get("name"))
            for i, v in zip(idx, sec["values"]):
                ax2.annotate(_fmt(v, sec.get("unit", "")), (i, v), xytext=(0, 7),
                             textcoords="offset points", ha="center", fontsize=8,
                             color=_c(BRAND["green"]), fontweight="bold")
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
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=200)
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
    box(50 - root_w / 2, root_y, root_w, root_h, BRAND["orange"], BRAND["orange"],
        spec.get("root", "产品"), BRAND["white"], 10.5, True)

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
        box(x, cy, cw, ch, BRAND["orange_pale"], BRAND["orange"], label, BRAND["ink"], 8.5, True)
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
