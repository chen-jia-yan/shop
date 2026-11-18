# -*- coding: utf-8 -*-
"""
富卫品牌主题（Excel 版）—— 色值与 kb-to-word/scripts/themes.py 保持一致，改色时两边同步。

三套风格：
  classic  经典橙白：产品对比、客户清单、理赔材料、培训台账
  premium  尊享深色：经营看板、管理层报表
  minimal  简约白：整改跟踪、制度台账、合规检查表
"""

BRAND = {
    "orange": "E87722", "orange_dark": "B85A12", "orange_light": "FCE9D9", "orange_pale": "FEF6EF",
    "green": "183028", "green_mid": "2F5747", "green_light": "E3ECE8",
    "yellow": "FED141", "yellow_light": "FFF6D6",
    "ink": "1F2329", "ink_soft": "4A5058", "muted": "8B8E8F", "line": "D9DCDF",
    "bg_soft": "F5F6F7", "white": "FFFFFF",
    "red": "C8372D", "red_light": "FBE7E5", "teal": "1E8C7E", "teal_light": "E2F3F0",
    "blue": "2B6CB0", "blue_light": "E6EFF8",
}

CHART_PALETTE = ["E87722", "183028", "FED141", "6B9A8B", "F2A65A", "8B8E8F", "B85A12", "C9D6D1"]
GREY_BAR = "C9CDD1"

FONT = "微软雅黑"
NUM_FONT = "Arial"

STYLES = {
    "classic": {
        "name": "经典橙白",
        "title": BRAND["orange"], "title_bar": BRAND["orange"], "subtitle": BRAND["ink_soft"],
        "head_bg": BRAND["orange"], "head_fg": BRAND["white"],
        "stripe": BRAND["orange_pale"], "total_bg": BRAND["orange_light"],
        "hi_col": BRAND["yellow_light"], "group_bg": BRAND["green_light"], "group_fg": BRAND["green"],
        "tile_bg": BRAND["orange_pale"], "tile_bar": BRAND["orange"], "tile_value": BRAND["ink"],
        "tab": BRAND["orange"], "accent": BRAND["orange"],
    },
    "premium": {
        "name": "尊享深色",
        "title": BRAND["green"], "title_bar": BRAND["green"], "subtitle": BRAND["green_mid"],
        "head_bg": BRAND["green"], "head_fg": BRAND["white"],
        "stripe": BRAND["bg_soft"], "total_bg": BRAND["yellow_light"],
        "hi_col": BRAND["orange_pale"], "group_bg": BRAND["orange_light"], "group_fg": BRAND["orange_dark"],
        "tile_bg": BRAND["green"], "tile_bar": BRAND["yellow"], "tile_value": BRAND["white"],
        "tab": BRAND["green"], "accent": BRAND["yellow"],
    },
    "minimal": {
        "name": "简约白",
        "title": BRAND["ink"], "title_bar": BRAND["orange"], "subtitle": BRAND["muted"],
        "head_bg": BRAND["bg_soft"], "head_fg": BRAND["ink"],
        "stripe": None, "total_bg": BRAND["bg_soft"],
        "hi_col": BRAND["orange_pale"], "group_bg": BRAND["bg_soft"], "group_fg": BRAND["ink"],
        "tile_bg": BRAND["white"], "tile_bar": BRAND["orange"], "tile_value": BRAND["ink"],
        "tab": BRAND["muted"], "accent": BRAND["orange"],
    },
}

# 单元格角色：录入格（可改）、公式格（自动算）、占位格（待补充）
ROLE = {
    "input_bg": BRAND["yellow_light"], "input_border": "D69E2E",
    "formula_fg": BRAND["green_mid"],
    "todo_bg": "FFE699",
}

# 数字格式
FORMATS = {
    "text": "@",
    "int": "#,##0",
    "money": "#,##0",            # 元，整数
    "money2": "#,##0.00",        # 元，两位小数
    "wan": "#,##0.00",           # 万元
    "yi": "0.00",                # 亿元
    "pct": "0.0%",
    "pct0": "0%",
    "ratio": "0.00",
    "date": "yyyy-mm-dd",
    "month": "yyyy-mm",
    "delta": '"▲"0.0%;"▼"0.0%;0.0%',
    "delta_pt": '"▲"0.0"pct";"▼"0.0"pct";0.0"pct"',
}

DEFAULT_STYLE_BY_KIND = {
    "compare": "classic", "dashboard": "premium", "tracker": "minimal", "checklist": "classic",
    "calculator": "classic", "ledger": "minimal", "roster": "classic",
}


def get_style(name):
    if name not in STYLES:
        raise ValueError("未知风格 %r，可选：%s" % (name, ", ".join(STYLES)))
    return STYLES[name]
