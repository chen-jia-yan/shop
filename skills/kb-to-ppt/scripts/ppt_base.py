# -*- coding: utf-8 -*-
"""
python-pptx 底层辅助：坐标、字体（中西文分别设置）、文本框（含自动缩字号）、形状、阴影、透明度、渐变。
坐标统一用英寸（16:9 页面为 13.333 × 7.5）。
"""
import math
import re

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from ppt_theme import BRAND, CONF, FONTS, R

DASH = {"dash": MSO_LINE_DASH_STYLE.DASH, "dot": MSO_LINE_DASH_STYLE.ROUND_DOT, "long": MSO_LINE_DASH_STYLE.LONG_DASH}

_SLIDE = R("slide")
W, H = _SLIDE["width_in"], _SLIDE["height_in"]          # 页面尺寸见 rules.ppt.slide
NUM_RE = re.compile(r"([+\-−▲▼]?\d[\d,，.]*\s*(?:%s)?)" % "|".join(re.escape(u) for u in sorted(R("number_units"), key=len, reverse=True)))


def _mark_re():
    """**加粗** 与占位符（见 compliance.json 的 placeholders）。"""
    return re.compile(r"(\*\*.+?\*\*|%s)" % CONF.placeholder_re().pattern)


FIT_LOG = []      # 自动缩字号仍放不下的记录，供构建报告使用


def I(x):
    return Emu(int(round(x * 914400)))


def rgb(h):
    return RGBColor.from_string(h.lstrip("#").upper())


def set_font(run, size=None, bold=None, color=None, en=None, cn=None, italic=None):
    f = run.font
    if size is not None:
        f.size = Pt(CONF.size(size))
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color:
        f.color.rgb = rgb(color)
    f.name = en or FONTS["en"]
    rpr = run._r.get_or_add_rPr()
    latin = rpr.find(qn("a:latin"))
    for old in rpr.findall(qn("a:ea")):
        rpr.remove(old)
    ea = etree.SubElement(rpr, qn("a:ea"))
    ea.set("typeface", cn or FONTS["cn"])
    if latin is not None:
        latin.addnext(ea)       # a:ea 必须紧跟 a:latin
    return run


# ---------------- 文本 ----------------
def text_width(s, size):
    """估算文字宽度（磅）：中文约 1 个字号宽，英文数字约 0.55。"""
    w = 0.0
    for ch in str(s):
        w += size * (1.0 if ord(ch) > 0x2E80 else 0.56)
    return w


def _plain(s):
    return _mark_re().sub(lambda m: m.group(0).strip("*"), str(s or ""))


def fit_size(paras, w_in, h_in, size, min_size=10, spacing=1.25, where=""):
    """按框的宽高估算能放下的最大字号；到最小字号仍放不下时记录到 FIT_LOG。
    返回的是“未缩放”的字号，实际写入时再乘 fonts.scale；估算时已把缩放考虑进去。"""
    w_pt = w_in * 72 * 0.96
    h_pt = h_in * 72
    k = CONF.font_scale
    s = size
    while True:
        lines = 0
        for p in paras:
            t = _plain(p if isinstance(p, str) else p.get("text", ""))
            ps = s * k * (p.get("scale", 1.0) if isinstance(p, dict) else 1.0)
            lines += max(1, math.ceil(text_width(t, ps) / w_pt)) * ps / (s * k)
        need = lines * s * k * spacing + (len(paras) - 1) * s * k * 0.35
        if need <= h_pt or s <= min_size:
            if need > h_pt and where:
                FIT_LOG.append("%s：文字过多，已缩到 %.0f 号仍可能放不下，建议精简" % (where, s))
            return s
        s -= 1


def _runs(par, text, size, color, bold, accent, highlight_numbers, en=None):
    for part in _mark_re().split(str(text or "")):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            set_font(par.add_run(), size, True, accent or color, en).text = part[2:-2]
            continue
        if CONF.placeholder_re().fullmatch(part):
            r = par.add_run()
            set_font(r, size, True, BRAND["primary_dark"], en)
            r.text = part
            _highlight(r, BRAND["todo_bg"])
            continue
        if highlight_numbers:
            for k, seg in enumerate(NUM_RE.split(part)):
                if not seg:
                    continue
                r = par.add_run()
                is_num = k % 2 == 1
                set_font(r, size, True if is_num else bold, (accent or color) if is_num else color, en)
                r.text = seg
        else:
            r = par.add_run()
            set_font(r, size, bold, color, en)
            r.text = part


def _highlight(run, fill):
    rpr = run._r.get_or_add_rPr()
    hl = etree.SubElement(rpr, qn("a:highlight"))
    clr = etree.SubElement(hl, qn("a:srgbClr"))
    clr.set("val", fill)
    # a:highlight 必须位于 a:latin 之前
    latin = rpr.find(qn("a:latin"))
    if latin is not None:
        latin.addprevious(hl)


def text(slide, x, y, w, h, paras, size=14, color=None, bold=False, align="left", anchor="top",
         spacing=1.2, accent=None, numbers=False, min_size=None, where="", en=None, inset=0.0):
    """
    paras：字符串或列表；列表元素可以是字符串或 {"text","size","bold","color","scale","space_before"}。
    min_size：给出时按框大小自动缩小字号。numbers=True 时数字自动加粗并用 accent 色。
    """
    if isinstance(paras, str):
        paras = [paras]
    if min_size:
        size = fit_size(paras, w - 2 * inset, h - 2 * inset, size, min_size, spacing, where)
    tb = slide.shapes.add_textbox(I(x), I(y), I(w), I(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, "margin_" + side, I(inset))
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
    for i, p in enumerate(paras):
        d = {"text": p} if isinstance(p, str) else p
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT,
                         "justify": PP_ALIGN.JUSTIFY}[d.get("align", align)]
        par.line_spacing = d.get("spacing", spacing)
        if i:
            par.space_before = Pt(d.get("space_before", size * 0.35))
        s = d.get("size", size * d.get("scale", 1.0))
        _runs(par, d.get("text", ""), s, d.get("color", color or BRAND["ink"]), d.get("bold", bold),
              d.get("accent", accent), d.get("numbers", numbers), d.get("en", en))
    return tb


# ---------------- 形状 ----------------
SHAPES = {
    "rect": MSO_SHAPE.RECTANGLE, "round": MSO_SHAPE.ROUNDED_RECTANGLE, "oval": MSO_SHAPE.OVAL,
    "chevron": MSO_SHAPE.CHEVRON, "pentagon": MSO_SHAPE.PENTAGON, "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
    "trapezoid": MSO_SHAPE.TRAPEZOID, "arc": MSO_SHAPE.BLOCK_ARC, "diamond": MSO_SHAPE.DIAMOND,
    "right_arrow": MSO_SHAPE.RIGHT_ARROW, "donut": MSO_SHAPE.DONUT, "hexagon": MSO_SHAPE.HEXAGON,
    "round_top": MSO_SHAPE.ROUND_2_SAME_RECTANGLE, "circ_arrow": MSO_SHAPE.CIRCULAR_ARROW,
}


def shape(slide, kind, x, y, w, h, fill=None, line=None, line_w=0.75, radius=None, shadow=False,
          alpha=None, gradient=None, rotation=0):
    sp = slide.shapes.add_shape(SHAPES.get(kind, kind), I(x), I(y), I(w), I(h))
    if gradient:
        sp.fill.gradient()
        sp.fill.gradient_angle = gradient[2] if len(gradient) > 2 else 0
        stops = sp.fill.gradient_stops
        stops[0].color.rgb = rgb(gradient[0])
        stops[0].position = 0
        stops[1].color.rgb = rgb(gradient[1])
        stops[1].position = 1.0
    elif fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(fill)
        if alpha is not None:
            set_alpha(sp, alpha)
    else:
        sp.fill.background()
    if line:
        sp.line.color.rgb = rgb(line)
        sp.line.width = Pt(line_w)
    else:
        sp.line.fill.background()
    if radius is not None and kind in ("round", "round_top"):
        sp.adjustments[0] = radius
    if rotation:
        sp.rotation = rotation
    sp.shadow.inherit = False          # 去掉主题默认阴影，需要时再加柔和阴影
    if shadow:
        add_shadow(sp)
    sp.text_frame.text = ""
    return sp


def set_alpha(sp, alpha):
    """alpha：0-1，1 为不透明。"""
    clr = sp.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    for old in clr.findall(qn("a:alpha")):
        clr.remove(old)
    a = etree.SubElement(clr, qn("a:alpha"))
    a.set("val", str(int(alpha * 100000)))


def add_shadow(sp, blur=16, dist=3, alpha=0.10):
    spPr = sp._element.spPr
    for old in spPr.findall(qn("a:effectLst")):
        spPr.remove(old)
    eff = etree.SubElement(spPr, qn("a:effectLst"))
    sh = etree.SubElement(eff, qn("a:outerShdw"))
    sh.set("blurRad", str(int(blur * 12700)))
    sh.set("dist", str(int(dist * 12700)))
    sh.set("dir", "5400000")
    sh.set("algn", "t")
    sh.set("rotWithShape", "0")
    c = etree.SubElement(sh, qn("a:srgbClr"))
    c.set("val", BRAND["shadow"])
    a = etree.SubElement(c, qn("a:alpha"))
    a.set("val", str(int(alpha * 100000)))
    # effectLst 必须在 ln 之后、scene3d 之前
    for tag in ("a:scene3d", "a:sp3d", "a:extLst"):
        nxt = spPr.find(qn(tag))
        if nxt is not None:
            nxt.addprevious(eff)
            break


def line(slide, x1, y1, x2, y2, color=None, width=1.0, dash=None):
    """dash：None 实线 / "dash" 虚线 / "dot" 点线。"""
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2))
    ln.line.color.rgb = rgb(color or BRAND["line"])
    ln.line.width = Pt(width)
    if dash:
        ln.line.dash_style = DASH.get(dash, dash)
    return ln


def polyline(slide, pts, color, width=2.0, dash=None):
    """折线：逐段画直线（返回线段列表，便于一起加动画）。"""
    return [line(slide, a[0], a[1], b[0], b[1], color, width, dash) for a, b in zip(pts, pts[1:])]


def smooth(pts, n=8):
    """Catmull-Rom 插值，把几个点连成平滑曲线的采样点。"""
    if len(pts) < 3:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(n):
            s = k / float(n)
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * s + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * s * s
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * s ** 3) for j in (0, 1)))
    out.append(pts[-1])
    return out


def fmt_num(v, nf=None):
    """按 Excel 风格的数字格式把数值写成文字：0 / 0.0 / 0.00 / #,##0 / 0% / 0.0% / +0.0%。字符串原样返回。"""
    if isinstance(v, str) or v is None:
        return "" if v is None else v
    nf = nf or ("0" if float(v) == int(v) else "0.0")
    sign = "+" if nf.startswith("+") and v > 0 else ""
    core = nf.lstrip("+")
    dec = len(core.split(".")[1].rstrip("%")) if "." in core else 0
    if core.endswith("%"):
        return sign + ("%.*f%%" % (dec, v * 100))
    if "," in core:
        return sign + "{:,.{d}f}".format(v, d=dec)
    return sign + ("%.*f" % (dec, v))


def mix(c1, c2, k):
    """两色混合：k=0 为 c1，k=1 为 c2。"""
    a, b = c1.lstrip("#"), c2.lstrip("#")
    k = max(0.0, min(1.0, k))
    return "".join("%02X" % int(round(int(a[i:i + 2], 16) * (1 - k) + int(b[i:i + 2], 16) * k)) for i in (0, 2, 4))


def dashed(sp, dash="dash"):
    sp.line.dash_style = DASH.get(dash, dash)
    return sp


def shape_text(sp, s, size=14, color=None, bold=False, align="center", anchor="middle", numbers=False, accent=None):
    tf = sp.text_frame
    tf.word_wrap = True
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, "margin_" + side, I(0.05))
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
    par = tf.paragraphs[0]
    par.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
    _runs(par, s, size, color or BRAND["white"], bold, accent, numbers)
    return sp


def poly(slide, pts, fill=None, line=None, line_w=0.75, alpha=None, shadow=False):
    """任意多边形（坐标为英寸）。局部单位取 1/1000 英寸，避免路径坐标取整失真。"""
    q = [(int(round(px * 1000)), int(round(py * 1000))) for px, py in pts]
    fb = slide.shapes.build_freeform(q[0][0], q[0][1], scale=914.4)
    fb.add_line_segments(q[1:], close=True)
    sp = fb.convert_to_shape(0, 0)
    if fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(fill)
        if alpha is not None:
            set_alpha(sp, alpha)
    else:
        sp.fill.background()
    if line:
        sp.line.color.rgb = rgb(line)
        sp.line.width = Pt(line_w)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    if shadow:
        add_shadow(sp)
    return sp


def arc_pts(cx, cy, r, a0, a1, n=24):
    """圆弧上的点（角度：0° 指向右，逆时针为正；y 轴向下）。"""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy - r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def ring_segment(slide, cx, cy, r_out, r_in, a0, a1, fill, alpha=None):
    pts = arc_pts(cx, cy, r_out, a0, a1) + arc_pts(cx, cy, r_in, a1, a0)
    return poly(slide, pts, fill, alpha=alpha)


def background(slide, spec):
    """spec：("solid", 色) 或 ("gradient", 起色, 止色)；渐变用整页矩形实现。"""
    if spec[0] == "solid":
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = rgb(spec[1])
    else:
        shape(slide, "rect", 0, 0, W, H, gradient=(spec[1], spec[2], 315))
