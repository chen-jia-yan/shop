# -*- coding: utf-8 -*-
"""
主题（PPT 版）—— 只是共享配置的入口，本文件不存放任何色值、字体或文字。

  颜色、字体：tap-config/brand.json
  风格（orange / premium / minimal / warm，可自行新增）：tap-config/themes.json 的 themes.ppt
    每套风格除颜色外还有几个开关：
      cover_style  封面装饰：glow 半透明圆 + 大图标 / rings 同心圆线 / line 左侧竖条
      filled       强调块是否用实色填充（false 为浅底 + 主色字的简约做法）
      section_dark 章节页是否为深色底
      palette / funnel / pyramid / bar_fill  多项元素的配色顺序
  页面尺寸、字号、拆页与质检阈值：tap-config/rules.json 的 rules.ppt
  固定文字：tap-config/labels.json
"""
from _tap import CONF

BRAND = CONF.colors
FONTS = CONF.fonts
SIZES = CONF.sizes


def L(key, **kw):
    return CONF.label(key, **kw)


def G(name):
    return CONF.glyph(name)


def R(key):
    return CONF.rule(key)


def theme_names():
    return CONF.theme_names()


def get_theme(name):
    return CONF.theme(name)


def default_theme(deck_type):
    return CONF.default_theme("default_by_deck", deck_type)


def palette(t):
    """图表与多项元素的配色顺序（第一个为主色）。t 为主题字典。"""
    return list(t["palette"])
