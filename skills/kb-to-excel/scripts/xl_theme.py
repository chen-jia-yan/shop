# -*- coding: utf-8 -*-
"""
主题（Excel 版）—— 只是共享配置的入口，本文件不存放任何色值、字体或文字。

  颜色、字体：tap-config/brand.json（表格专用色以 tb_ 开头）
  色系（蓝色系 blue / 淡色系 soft / 橙色系 orange，可自行新增）、单元格角色色、数字格式：
      tap-config/themes.json 的 themes.excel
  阈值：tap-config/rules.json 的 rules.excel；固定文字：tap-config/labels.json 的 labels.excel

下列字典与共享配置联动：命令行或内容 JSON 覆盖配置后原地刷新，其他模块无需重新 import。
"""
from _tap import CONF

BRAND = CONF.colors
FONTS = CONF.fonts                   # FONTS["cn"] 正文字体，FONTS["num"] 数字字体，FONTS["mono"] 等宽
CHART_PALETTE = CONF.chart_palette
ROLE = {}                            # 单元格角色色：录入格、公式、智能生成、异常、提醒……
FORMATS = {}                         # 数字格式别名 → Excel 格式串


@CONF.on_load
def _refresh(conf):
    if conf.scope != "excel":
        return
    ROLE.clear()
    ROLE.update(conf.theme_part("roles"))
    FORMATS.clear()
    FORMATS.update(conf.theme_part("formats"))


def L(key, **kw):
    return CONF.label(key, **kw)


def G(name):
    return CONF.glyph(name)


def R(key):
    return CONF.rule(key)


def style_names():
    return CONF.theme_names()


def default_style(kind):
    return CONF.default_theme("default_by_kind", kind)


# 旧工作表类型（对比矩阵、甘特、试算、清单、口径说明）沿用的风格键，由新色系推导，保证同一工作簿颜色一致
_LEGACY = {
    "title_bar": "accent", "head_bg": "head_bg", "head_fg": "head_fg", "stripe": "band", "total_bg": "total_bg",
    "hi_col": "accent_pale", "group_bg": "group_bg", "group_fg": "group_fg", "tile_bar": "accent",
    "tab": "tab_other", "cover_bg": "accent", "cover_brand": "accent_light", "cover_category": "accent_light",
}


def get_style(name):
    """取色系；同时把品牌主色临时映射为该色系的强调色（只影响本次 Excel 渲染），
    这样旧工作表类型里引用 primary 的地方也会跟着换色。"""
    st = CONF.theme(name)
    for old, new in _LEGACY.items():
        st.setdefault(old, st.get(new))
    st.setdefault("flat_head", True)
    st.setdefault("dark_tiles", False)
    st.setdefault("tile_bg", BRAND["white"])
    st.setdefault("tile_value", BRAND["ink"])
    st.setdefault("tile_label", BRAND["ink_soft"])
    st.setdefault("cover_fg", BRAND["white"])
    for k, v in (("primary", "accent"), ("primary_dark", "accent_dark"), ("primary_mid", "accent_mid"),
                 ("primary_light", "accent_light"), ("primary_pale", "accent_pale"), ("grid", "grid")):
        if st.get(v):
            BRAND[k] = st[v]
    if st.get("palette"):
        CHART_PALETTE[:] = list(st["palette"])
    return st
