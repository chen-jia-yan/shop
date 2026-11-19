# -*- coding: utf-8 -*-
"""
主题（Word 版）—— 只是共享配置的入口，本文件不存放任何色值、字体或文字。

  颜色、字体、字体方案（modern / formal）：tap-config/brand.json
  风格（soft 淡雅蓝 / blue 商务蓝 / navy 深蓝稳重 / classic / premium / minimal，可自行新增）、
  提示框配色：tap-config/themes.json 的 themes.word
  字号、页面尺寸、行距、按文档类型选字体方案、内容体检词表：tap-config/rules.json 的 rules.word
  提示框标题等文字：tap-config/labels.json

BRAND / FONTS / SIZES / CHART_PALETTE 是共享配置里的同一个字典对象，
命令行或内容 JSON 覆盖配置后会原地更新，其他模块不需要重新 import。
"""
from _tap import CONF

BRAND = CONF.colors
FONTS = CONF.fonts
SIZES = CONF.sizes
CHART_PALETTE = CONF.chart_palette


def L(key, **kw):
    return CONF.label(key, **kw)


def G(name):
    return CONF.glyph(name)


def R(key):
    return CONF.rule(key)


def style_names():
    return CONF.theme_names()


def get_style(name):
    return CONF.theme(name)


def default_style(doc_type):
    return CONF.default_theme("default_by_type", doc_type)


def font_preset_for(meta, st, cli=None):
    """字体方案：命令行 > meta.font_preset > 风格的 font_preset > rules.word.font_preset 按文档类型。"""
    spec = R("font_preset")
    return (cli or meta.get("font_preset") or st.get("font_preset")
            or spec.get("by_type", {}).get(meta.get("doc_type")) or spec.get("default"))


def callout(kind, st):
    """提示框配色：themes.word.callouts 为默认，风格里的 callouts 可逐项覆盖；$accent 表示取当前风格的同名颜色。"""
    specs = CONF.theme_part("callouts")
    spec = dict(specs.get(kind) or specs["info"])
    spec.update((st.get("callouts") or {}).get(kind) or {})
    for k, v in spec.items():
        if isinstance(v, str) and v.startswith("$"):
            spec[k] = st[v[1:]]
    spec["label"] = L("callouts").get(kind) or L("callouts")["info"]
    return spec


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
