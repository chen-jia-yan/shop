# -*- coding: utf-8 -*-
"""
富卫品牌主题（Word 版）

所有颜色、字体、字号集中在这里，改一处全局生效。
色值说明：
  - 富卫橙 #E87722、深绿 #183028、亮黄 #FED141 为公开资料中常见的富卫品牌色，
    上线前请品牌部按官方 VI 手册核对。
  - 其余为配合品牌色调出的辅助色，用于图表、提示框、表格底纹。

三套风格：
  classic  经典橙白：产品资料、客户方案、理赔指引、培训
  premium  尊享深色：高端客户、管理层报告、年报
  minimal  简约白：内部制度、操作指引、合规报告
"""

BRAND = {
    "orange": "E87722",       # 富卫橙（主色）
    "orange_dark": "B85A12",  # 橙色压暗，用于小字号强调，保证对比度
    "orange_light": "FCE9D9", # 浅橙底纹
    "orange_pale": "FEF6EF",  # 极浅橙，隔行底色
    "green": "183028",        # 深绿（辅助主色）
    "green_mid": "2F5747",
    "green_light": "E3ECE8",
    "yellow": "FED141",       # 亮黄（点缀）
    "yellow_light": "FFF6D6",
    "ink": "1F2329",          # 正文
    "ink_soft": "4A5058",     # 次要文字
    "muted": "8B8E8F",        # 说明文字、页脚
    "line": "D9DCDF",         # 细线
    "bg_soft": "F5F6F7",      # 浅灰底
    "white": "FFFFFF",
    "red": "C8372D",          # 风险/下降
    "red_light": "FBE7E5",
    "blue": "2B6CB0",         # 说明类提示
    "blue_light": "E6EFF8",
    "teal": "1E8C7E",         # 上升/正向
    "teal_light": "E2F3F0",
}

# 图表配色：第一色为主色，后续为辅助色；高亮图表只用主色 + 灰
CHART_PALETTE = ["E87722", "183028", "FED141", "6B9A8B", "F2A65A", "8B8E8F", "B85A12", "C9D6D1"]

FONTS = {
    "cn": "微软雅黑",          # 中文（Word 中的 eastAsia 字体）
    "en": "Microsoft YaHei",   # 西文；与中文统一，避免中英文混排时字形不一致
    "num": "Arial",            # KPI 大数字
    # matplotlib 图表字体按顺序回退，Windows / macOS / Linux 都能找到一个
    "chart": ["Microsoft YaHei", "PingFang SC", "Source Han Sans SC",
              "Noto Sans CJK SC", "SimHei", "WenQuanYi Micro Hei"],
}

SIZES = {  # 磅
    "title": 26, "subtitle": 14,
    "h1": 18, "h2": 14, "h3": 12,
    "body": 10.5, "small": 9, "caption": 9, "footer": 8,
    "kpi": 22, "kpi_label": 9,
}

STYLES = {
    "classic": {
        "name": "经典橙白",
        "cover": "band",            # 橙色色带封面
        "cover_bg": BRAND["orange"],
        "cover_fg": BRAND["white"],
        "cover_accent": BRAND["yellow"],
        "heading": BRAND["orange"],
        "heading_num": BRAND["orange"],
        "h2": BRAND["green"],
        "rule": BRAND["orange"],
        "table_head_bg": BRAND["orange"],
        "table_head_fg": BRAND["white"],
        "table_stripe": BRAND["orange_pale"],
        "table_total_bg": BRAND["orange_light"],
        "highlight_col_bg": BRAND["yellow_light"],
        "kpi_bg": BRAND["orange_pale"],
        "kpi_bar": BRAND["orange"],
        "header_text": BRAND["muted"],
    },
    "premium": {
        "name": "尊享深色",
        "cover": "full",            # 深绿整版封面
        "cover_bg": BRAND["green"],
        "cover_fg": BRAND["white"],
        "cover_accent": BRAND["yellow"],
        "heading": BRAND["green"],
        "heading_num": BRAND["orange"],
        "h2": BRAND["green_mid"],
        "rule": BRAND["yellow"],
        "table_head_bg": BRAND["green"],
        "table_head_fg": BRAND["white"],
        "table_stripe": BRAND["bg_soft"],
        "table_total_bg": BRAND["yellow_light"],
        "highlight_col_bg": BRAND["orange_pale"],
        "kpi_bg": BRAND["green_light"],
        "kpi_bar": BRAND["yellow"],
        "header_text": BRAND["green_mid"],
    },
    "minimal": {
        "name": "简约白",
        "cover": "line",            # 白底 + 橙色细线
        "cover_bg": BRAND["white"],
        "cover_fg": BRAND["ink"],
        "cover_accent": BRAND["orange"],
        "heading": BRAND["ink"],
        "heading_num": BRAND["orange"],
        "h2": BRAND["ink"],
        "rule": BRAND["orange"],
        "table_head_bg": BRAND["bg_soft"],
        "table_head_fg": BRAND["ink"],
        "table_stripe": BRAND["white"],
        "table_total_bg": BRAND["bg_soft"],
        "highlight_col_bg": BRAND["orange_pale"],
        "kpi_bg": BRAND["white"],
        "kpi_bar": BRAND["orange"],
        "header_text": BRAND["muted"],
    },
}

# 提示框语义：标签、图标、边条色、底色
CALLOUTS = {
    "key":     {"label": "核心要点", "icon": "◆", "bar": BRAND["orange"], "bg": BRAND["orange_pale"]},
    "summary": {"label": "摘要",     "icon": "≡", "bar": BRAND["green"],  "bg": BRAND["green_light"]},
    "info":    {"label": "说明",     "icon": "i", "bar": BRAND["blue"],   "bg": BRAND["blue_light"]},
    "tip":     {"label": "提示",     "icon": "✓", "bar": BRAND["teal"],   "bg": BRAND["teal_light"]},
    "warning": {"label": "注意",     "icon": "!", "bar": "D69E2E",        "bg": BRAND["yellow_light"]},
    "risk":    {"label": "风险提示", "icon": "!", "bar": BRAND["red"],    "bg": BRAND["red_light"]},
}

# 文档类型 → 推荐风格（用户没指定时使用）
DEFAULT_STYLE_BY_TYPE = {
    "product": "classic", "proposal": "classic", "claims": "minimal",
    "underwriting": "minimal", "training": "classic", "policy": "minimal",
    "analysis": "premium", "project": "classic", "notice": "classic",
    "compliance": "minimal",
}


def get_style(name):
    if name not in STYLES:
        raise ValueError("未知风格 %r，可选：%s" % (name, ", ".join(STYLES)))
    return STYLES[name]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
