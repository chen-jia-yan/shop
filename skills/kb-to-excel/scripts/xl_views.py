# -*- coding: utf-8 -*-
"""
视图层：列表视图（筛选 + 排序）与看板视图（按某个字段分列）。

视图只引用数据表，不复制、不手填：每个视图在数据表最右侧有对应的辅助列（已折叠），
视图表用 INDEX / MATCH 按辅助列取数，Excel 2010 到 Microsoft 365 都能随数据自动刷新（不依赖 FILTER / SORTBY）。

列表视图：
  {"type": "list", "name": "视图·待办", "from": "数据", "columns": ["工单号", "受理日期", …],
   "where": "{@状态}<>\"已结案\"", "sort": "处理时限" 或 {"by": "处理时限", "desc": true}, "rows": 200, "desc": "用途"}
看板视图：
  {"type": "board", "name": "视图·看板", "from": "数据", "group": "状态", "groups": ["待处理", …],
   "card": ["客户", "投诉类别", "承办人"], "where": "（可选）", "rows": 60}
"""
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter

from xl_data import (_grid, _header, _sheet_title, add_aux, field_fmt, level_style, readable)
from xl_helpers import absref, align, border, fill, font, put, qsheet, side, sref
from xl_theme import BRAND, FONTS, ROLE, L, R


def plan_views(ctx, views, extra=()):
    """在数据表上登记视图需要的辅助列。extra：仪表盘异常清单等内部视图。"""
    names = L("aux_names")
    for v in list(views) + list(extra):
        info = ctx.tables.get(v["from"])
        if not info:
            raise KeyError("视图“%s”的数据表不存在：%s" % (v["name"], v["from"]))
        for c in v.get("columns", []) + v.get("card", []) + ([v["group"]] if v.get("group") else []):
            if c not in info["cols"]:
                raise KeyError("视图“%s”引用了不存在的字段：%s" % (v["name"], c))
        match = None
        if v.get("where") or v.get("type", "list") == "list":
            match = add_aux(info, names["match"].format(view=v["name"]), "match",
                            when=v.get("where") or '{@%s}<>""' % info["key"], view=v["name"])
        sort = v.get("sort")
        if isinstance(sort, str):
            sort = {"by": sort}
        if v.get("type", "list") == "list":
            v["_seq"] = add_aux(info, names["seq"].format(view=v["name"]), "seq", match=match,
                                sort=(sort or {}).get("by"), desc=(sort or {}).get("desc"), view=v["name"])
        else:
            v["_seq"] = add_aux(info, names["seq"].format(view=v["name"]), "group", match=match,
                                group=v["group"], view=v["name"], **{"for": "board"})
        v["_match"] = match


def _a1col(info, col, span):
    """数据表某列的 A1 绝对区域（条件格式里不能用结构化引用）。"""
    c = info["colidx"][col]
    return "%s%s:%s" % (qsheet(info["spec"]["name"]), absref(c, info["first"]), absref(c, span))


# ---------------- 列表视图 ----------------
def list_view(ctx, ws, v, start_row=None, title=True, start_col=1):
    """写一个列表视图。start_row / start_col 用于把异常清单嵌进仪表盘。返回 (末行, 末列)。"""
    st, info = ctx.st, ctx.tables[v["from"]]
    T, cols = info["tname"], v["columns"]
    n = v.get("rows") or R("view_rows")
    hdr = start_row or 2
    if title:
        sort = v.get("sort")
        sort_t = (sort if isinstance(sort, str) else (sort or {}).get("by")) or L("view_sort_none")
        if isinstance(sort, dict) and sort.get("desc"):
            sort_t += " ↓"
        _sheet_title(ws, st, v.get("title") or v["name"],
                     L("view_note", src=v["from"], where=readable(v["where"]) if v.get("where") else L("view_all"), sort=sort_t))
    c0 = start_col
    _header(ws, st, hdr, ["#"] + cols, start=c0)
    ws.column_dimensions[get_column_letter(c0)].hidden = title           # 仪表盘里保留可见的序号列
    seq = sref(T, v["_seq"])
    span = info["first"] + R("range_rows")
    A = get_column_letter(c0)
    first = hdr + 1
    for i in range(n):
        r = first + i
        put(ws, r, c0, '=IFERROR(MATCH(ROWS($%s$%d:%s%d),%s,0),"")' % (A, first, A, r, seq),
            font(9, False, ROLE["aux_fg"], FONTS["num"]), al=align("center"))
        for j, c in enumerate(cols, 1):
            f = info["fields"].get(c) or {}
            ref = sref(T, c)
            if c == info["key"]:
                hl = '"#%s"&ADDRESS(%d+$%s%d,%d)' % (qsheet(v["from"]), info["hdr"], A, r, info["colidx"][c])
                val = '=IF($%s%d="","",HYPERLINK(%s,INDEX(%s,$%s%d)))' % (A, r, hl, ref, A, r)
                ft = font(10, True, ROLE["link"], FONTS["num"])
            else:
                val = '=IF($%s%d="","",IF(INDEX(%s,$%s%d)="","",INDEX(%s,$%s%d)))' % (A, r, ref, A, r, ref, A, r)
                ft = font(10, False, ROLE["ai_fg"] if f.get("type") == "ai" else BRAND["ink"],
                          FONTS["num"] if f.get("type") in ("number", "money", "percent", "date") else None)
            h = "right" if f.get("type") in ("number", "money", "percent") else \
                ("center" if f.get("type") in ("date", "select", "bool") or c == info.get("remind") else "left")
            put(ws, r, c0 + j, val, ft, fill(st["band"]) if i % 2 else None,
                align(h, "center", f.get("type") == "longtext"), _grid(st), field_fmt(f))
    last = first + n - 1
    # 条件格式：规则命中（读数据表的提醒标记）、按取值着色
    yes = L("yes_no")[0]
    for j, c in enumerate(cols, 1):
        L_ = get_column_letter(c0 + j)
        rng = "%s%d:%s%d" % (L_, first, L_, last)
        f = info["fields"].get(c) or {}
        for val, lv in (f.get("styles") or {}).items():
            fl, ft = level_style(lv)
            ws.conditional_formatting.add(rng, FormulaRule(formula=['%s%d="%s"' % (L_, first, val)], fill=fl, font=ft))
        if info.get("remind"):
            for ru in ctx.rules:
                if c in (ru.get("fields") or []) or (c == info["remind"]):
                    fl, ft = level_style(ru.get("level", "warn"))
                    ws.conditional_formatting.add(rng, FormulaRule(formula=[
                        'AND(%s="%s",$%s%d<>"",ISNUMBER(SEARCH("%s",INDEX(%s,$%s%d))))' % (
                            ru["_enabled"], yes, A, first, ru["mark"], _a1col(info, info["remind"], span), A, first)],
                        fill=fl, font=ft))
    for j, c in enumerate(cols, 1) if title else ():              # 嵌入仪表盘时不改网格列宽
        f = info["fields"].get(c) or {}
        w = f.get("width") or (R("long_text_width") if f.get("type") == "longtext" else
                               max(R("col_width")[0], min(24, len(c) * 2 + 4)))
        cd = ws.column_dimensions[get_column_letter(c0 + j)]
        cd.width = max(cd.width or 0, w)
    if title:
        ws.freeze_panes = ws.cell(row=first, column=c0 + 2)
        ws.sheet_properties.tabColor = st["tab_view"]
    return last, c0 + len(cols)


# ---------------- 看板视图 ----------------
def board_view(ctx, ws, v):
    st, info = ctx.st, ctx.tables[v["from"]]
    T = info["tname"]
    g = v["group"]
    groups = v.get("groups") or ctx.options.get((info["fields"].get(g) or {}).get("options_ref") or "", [])
    if not groups:
        raise KeyError("看板“%s”需要 groups，或分组字段带 options" % v["name"])
    card = v.get("card") or []
    n = v.get("rows") or R("board_rows")
    _sheet_title(ws, st, v.get("title") or v["name"],
                 L("view_note", src=v["from"], where=readable(v["where"]) if v.get("where") else L("view_all"), sort="—"))
    tpl = L("board_col")
    pre, _, post = tpl.partition("{n}")
    seq = sref(T, v["_seq"])
    span = info["first"] + R("range_rows")
    for j, grp in enumerate(groups, 1):
        cnt = 'COUNTIFS(%s,1,%s,"%s")' % (sref(T, v["_match"]), sref(T, g), grp) if v.get("_match") \
            else 'COUNTIFS(%s,"%s")' % (sref(T, g), grp)
        put(ws, 2, j, '="%s"&%s&"%s"' % (pre.format(status=grp), cnt, post.format(status=grp)),
            font(10.5, True, st["head_fg"]), fill(st["head_bg"]), align("left", "center"),
            border(bottom=side(st["head_line"], "medium"), right=side(BRAND["white"], "thick")))
        ws.column_dimensions[get_column_letter(j)].width = 30
    ws.row_dimensions[2].height = R("head_height")

    def piece(c, m):
        f = info["fields"].get(c) or {}
        x = "INDEX(%s,%s)" % (sref(T, c), m)
        return 'TEXT(%s,"yyyy-mm-dd")' % x if f.get("type") == "date" else x
    for i in range(n):
        r = 3 + i
        ws.row_dimensions[r].height = 44
        for j, grp in enumerate(groups, 1):
            m = 'MATCH("%s-%d",%s,0)' % (grp, i + 1, seq)
            body = "&".join(['INDEX(%s,%s)' % (sref(T, info["key"]), m), "CHAR(10)"] +
                            [x for k, c in enumerate(card) for x in ([piece(c, m)] if k == 0 else ['" · "', piece(c, m)])])
            put(ws, r, j, '=IFERROR(%s,"")' % body, font(10, False, BRAND["ink"]), fill(BRAND["white"]),
                align("left", "center", True),
                border(left=side(st["accent_light"], "thick"), bottom=side(st["grid"]), right=side(BRAND["white"], "thick")))
    last = 2 + n
    rng = "A3:%s%d" % (get_column_letter(len(groups)), last)
    ws.conditional_formatting.add(rng, FormulaRule(formula=['A3=""'], fill=fill(st["band"]), stopIfTrue=True))
    if info.get("remind"):
        yes = L("yes_no")[0]
        keys, rem = _a1col(info, info["key"], span), _a1col(info, info["remind"], span)
        for ru in sorted(ctx.rules, key=lambda x: {"bad": 0, "warn": 1, "info": 2}.get(x.get("level"), 1)):
            if ru.get("level") == "info":
                continue
            fl, ft = level_style(ru.get("level", "warn"))
            ws.conditional_formatting.add(rng, FormulaRule(formula=[
                'AND(%s="%s",COUNTIFS(%s,LEFT(A3,FIND(CHAR(10),A3&CHAR(10))-1),%s,"*%s*")>0)' % (
                    ru["_enabled"], yes, keys, rem, ru["mark"])], fill=fl, font=ft))
    ws.freeze_panes = "A3"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = st["tab_view"]
