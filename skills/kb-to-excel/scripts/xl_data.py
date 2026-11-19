# -*- coding: utf-8 -*-
"""
数据层：参数表、提醒规则表、原始数据表（Excel“表格”对象）。

原则（见 SKILL.md）：
  - 原始数据一行一条、一列一个字段，检索到的内容原样写入，不合并单元格、不汇总、不改写。
  - 数据表是 Excel 表格对象：自带筛选、结构化引用；用户在表格下方新增行时，公式列自动延伸。
  - 公式列（type=formula）、提醒标记列、视图用的辅助列都追加在原始字段之后，原始字段一列不少。
  - 数据表内的公式统一写结构化引用（tbl[[#This Row],[字段]]），条件格式用 A1 引用（Excel 不支持在条件格式里用结构化引用）。

字段写法（fields 中每一项）：
  {"name": "受理日期", "type": "date", "required": true, "desc": "…", "src": "TAP 工单系统"}
  type：text 文本 / longtext 长文本 / number 数字 / money 金额 / percent 百分比 / date 日期 / select 单选 /
        multi 多选 / person 人员 / link 链接 / formula 公式 / ai 智能生成 / bool 是否
  其他可选键：options（可选值列表，自动写进“参数”表并做下拉）、options_ref（引用 options 中已有的一组）、
        formula（type=formula 时必填，用 {@字段} 引用本行、{param.键} 引用参数）、format、width、input（录入格）、
        freeze（冻结到该列）、styles（{取值: good|bad|warn|info|grey}，按取值着色）、databar、
        ai（{"from": "依据字段", "date": "生成日期", "check": "对照字段"}）、display（链接显示文字模板）
"""
import datetime as dt
import re

from openpyxl.comments import Comment
from openpyxl.formatting.rule import DataBarRule, FormulaRule
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableFormula, TableStyleInfo

from xl_helpers import TOKEN, absref, align, border, fill, font, is_formula, put, qsheet, side, sref, text_width
from xl_theme import BRAND, CONF, FONTS, FORMATS, ROLE, L, R

ROWTOK = re.compile(r"\{@([^{}]+)\}")
TYPE_FMT = {"number": "int", "money": "money", "percent": "pct", "date": "date"}
NUMERIC_TYPES = ("number", "money", "percent")
LEVEL_ROLE = {"bad": ("bad_bg", "bad_fg"), "warn": ("warn_bg", "warn_fg"), "info": ("info_bg", "info_fg"),
              "good": ("good_bg", "good_fg"), "grey": ("status_grey_bg", "status_grey_fg")}


# ---------------- 小工具 ----------------
def level_style(level):
    bg, fg = LEVEL_ROLE.get(level, LEVEL_ROLE["warn"])
    return fill(ROLE[bg]), font(10, True, ROLE[fg])


def field_fmt(f):
    k = f.get("format") or TYPE_FMT.get(f.get("type"))
    return FORMATS.get(k, k) if k else None


def to_date(v):
    if isinstance(v, str) and re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", v.strip()):
        y, m, d = (int(x) for x in v.strip().split("-"))
        return dt.date(y, m, d)
    return v


def struct_expr(expr, tname, cols, reg):
    """{@字段} → 结构化“本行”引用；{param.x}/{options.x}/{表.列} → 立即解析（规划阶段已登记全部数据表），
    这样表格的计算列模板里也不会残留花括号。"""
    def rep(m):
        name = m.group(1)
        if name not in cols:
            raise KeyError("引用了不存在的字段：%s" % name)
        return sref(tname, name, this_row=True)
    s = ROWTOK.sub(rep, expr)
    return TOKEN.sub(lambda m: reg.cells[m.group(1)] if m.group(1) in reg.cells else reg.resolve_token(m.group(1)), s)


def a1_expr(expr, colidx, row, reg):
    """条件格式用：{@字段} → $列行号（列绝对、行相对）。条件格式里不能有跨表 {表.列} 引用。"""
    def rep(m):
        name = m.group(1)
        if name not in colidx:
            raise KeyError("引用了不存在的字段：%s" % name)
        return "$%s%d" % (get_column_letter(colidx[name]), row)
    s = ROWTOK.sub(rep, expr)
    s = TOKEN.sub(lambda m: reg.cells.get(m.group(1), m.group(0)), s)
    if TOKEN.search(s):
        raise KeyError("条件里只能引用本行字段 {@…} 和参数 {param.…}：%s" % expr)
    return s


def readable(expr):
    """把条件公式写成给人看的样子：{@状态} → [状态]，{param.x} → 参数名。"""
    return TOKEN.sub(lambda m: "[%s]" % m.group(1).lstrip("@").split(".")[-1], ROWTOK.sub(r"[\1]", expr)).lstrip("=")


def define_name(wb, name, ref):
    """兼容 openpyxl 3.0 / 3.1 的命名区域写法。"""
    try:
        from openpyxl.workbook.defined_name import DefinedName
        dn = DefinedName(name, attr_text=ref)
        try:
            wb.defined_names[name] = dn          # 3.1
        except TypeError:
            wb.defined_names.append(dn)          # 3.0
    except Exception as e:                        # 命名区域只是方便查看，失败不影响公式
        print("命名区域 %s 未写入：%s" % (name, e))


# ---------------- 规划：先算好所有位置，后面的表才能互相引用 ----------------
def plan(ctx, data):
    """确定参数、选项、规则启用格、数据表列布局。返回后 ctx.reg.cells 已含 param./options.。"""
    reg, P = ctx.reg, L("params_sheet")
    params = data.get("params") or []
    r = 3
    for p in params:
        reg.cell("param", p["key"], P, 2, r)
        p["_row"] = r
        r += 1
    # 下拉选项：显式 options + 各 select 字段自带的 options
    opts = dict(data.get("options") or {})
    for t in data.get("data") or []:
        for f in t["fields"]:
            if f.get("options") and not f.get("options_ref"):
                key = f.get("options_name") or f["name"]
                if key in opts and opts[key] != f["options"]:
                    key = "%s·%s" % (t["name"], f["name"])
                opts[key] = f["options"]
                f["options_ref"] = key
            if f.get("type") == "bool" and not f.get("options_ref"):
                opts.setdefault("_yes_no", L("yes_no"))
                f["options_ref"] = "_yes_no"
    ctx.options = opts
    top = r + 2                                   # 选项表头所在行
    for i, (k, vals) in enumerate(opts.items()):
        c = i + 1
        reg.cells["options." + k] = "%s%s:%s" % (qsheet(P), absref(c, top + 1), absref(c, top + len(vals)))
    ctx.params, ctx.options_top = params, top
    # 提醒规则启用格
    ctx.rules = data.get("rules") or []
    for i, ru in enumerate(ctx.rules):
        ru.setdefault("id", "A%02d" % (i + 1))
        ru.setdefault("mark", ru.get("name"))
        ru["_enabled"] = qsheet(L("rules_sheet")) + absref(6, 3 + i)
    # 数据表
    ctx.tables = {}
    for i, t in enumerate(data.get("data") or []):
        cols = [f["name"] for f in t["fields"]]
        info = {"spec": t, "tname": t.get("table_name") or "tbl%d" % (i + 1), "hdr": 2, "first": 3,
                "n": len(t.get("rows") or []), "key": t.get("key") or cols[0],
                "fields": {f["name"]: f for f in t["fields"]}, "cols": cols, "aux": []}
        info["last"] = info["first"] + max(info["n"], 1) - 1
        if any((ru.get("table") or data["data"][0]["name"]) == t["name"] for ru in ctx.rules):
            info["remind"] = L("remind_field")
            info["cols"].append(info["remind"])
        ctx.tables[t["name"]] = info


def add_aux(info, name, kind, **kw):
    """视图、看板、异常清单需要的辅助列（追加在最右侧，分组折叠）。"""
    if name in info["cols"]:
        raise KeyError("辅助列重名：%s" % name)
    info["cols"].append(name)
    info["aux"].append(dict(kw, name=name, kind=kind))
    return name


def finish_plan(ctx):
    for name, info in ctx.tables.items():
        info["colidx"] = {c: i for i, c in enumerate(info["cols"], 1)}
        ctx.reg.table(name, info["cols"], info["first"], info["last"],
                      {}, tname=info["tname"])


# ---------------- 参数表 ----------------
def params_sheet(ctx, ws, wb):
    st = ctx.st
    _sheet_title(ws, st, L("params_sheet"))
    _header(ws, st, 2, L("params_cols"))
    for p in ctx.params:
        r = p["_row"]
        put(ws, r, 1, p.get("name", p["key"]), font(10, True), bd=_grid(st))
        v = p.get("value")
        c = put(ws, r, 2, v, font(10, False, ROLE["fx_fg"] if is_formula(v) else BRAND["ink"], FONTS["num"]),
                fill(ROLE["input_bg"]), align("right" if isinstance(v, (int, float)) else "left"), _grid(st),
                FORMATS.get(p.get("format"), p.get("format")))
        put(ws, r, 3, p.get("desc", ""), font(10, False, BRAND["ink_soft"]), bd=_grid(st))
        if re.match(r"^[A-Za-z_]\w*$", p["key"]):
            define_name(wb, "p_" + p["key"], "%s%s" % (qsheet(ws.title), absref(2, r)))
    top = ctx.options_top
    if ctx.options:
        put(ws, top - 1, 1, L("options_title"), font(11, True, st["title"]))
        for i, (k, vals) in enumerate(ctx.options.items()):
            c = i + 1
            label = L("type_names")["bool"] if k == "_yes_no" else k
            put(ws, top, c, label, font(10, True, st["head_fg"]), fill(st["head_bg"]),
                bd=border(bottom=side(st["head_line"], "medium")))
            for j, v in enumerate(vals, 1):
                put(ws, top + j, c, v, font(10), fill(ROLE["input_bg"]), bd=_grid(st))
            ws.column_dimensions[get_column_letter(c)].width = max(ws.column_dimensions[get_column_letter(c)].width or 0,
                                                                  min(30, max(text_width(x) for x in [label] + vals) + 3))
            define_name(wb, "opt%d" % c, ctx.reg.cells["options." + k])
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 0, 22)
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 18)
    ws.column_dimensions["C"].width = max(ws.column_dimensions["C"].width or 0, 48)
    ws.sheet_properties.tabColor = st["tab_other"]


# ---------------- 提醒规则表 ----------------
def rules_sheet(ctx, ws):
    st = ctx.st
    _sheet_title(ws, st, L("rules_sheet"))
    _header(ws, st, 2, L("rules_cols"))
    marks = L("rule_marks")
    yes, no = L("yes_no")[:2]
    dv = DataValidation(type="list", formula1='"%s,%s"' % (yes, no), allow_blank=False)
    ws.add_data_validation(dv)
    first_t = next(iter(ctx.tables)) if ctx.tables else None
    for i, ru in enumerate(ctx.rules):
        r = 3 + i
        info = ctx.tables.get(ru.get("table") or first_t)
        lv = ru.get("level", "warn")
        fl, ft = level_style(lv)
        fields = "、".join(ru.get("fields") or [])
        how = ru.get("how") or L("rule_how", fields=(fields + " ") if fields else "", how=marks.get(lv, ""),
                                 remind=L("remind_field"), name=ru["mark"])
        hit = '=COUNTIF(%s,"*%s*")' % (sref(info["tname"], info["remind"]), ru["mark"].replace('"', '""')) if info else ""
        vals = [ru["id"], ru["name"], ru.get("when_text") or readable(ru["when"]), hit, how,
                yes if ru.get("enabled", True) else no]
        for c, v in enumerate(vals, 1):
            cell = put(ws, r, c, v, font(10, c == 2, ROLE["fx_fg"] if c == 4 else BRAND["ink"],
                                         FONTS["mono"] if c == 3 else (FONTS["num"] if c in (1, 4) else None)),
                       al=align("center" if c in (1, 4, 6) else "left", "center", c in (3, 5)), bd=_grid(st))
        ws.cell(row=r, column=6).fill = fill(ROLE["input_bg"])
        dv.add(ws.cell(row=r, column=6).coordinate)
        ws.conditional_formatting.add("D%d" % r, FormulaRule(formula=["D%d>0" % r], fill=fl, font=ft))
    for c, w in zip("ABCDEF", (8, 16, 44, 10, 44, 8)):
        ws.column_dimensions[c].width = w
    ws.freeze_panes = "A3"
    ws.sheet_properties.tabColor = st["tab_rule"]


# ---------------- 原始数据表 ----------------
def data_sheet(ctx, ws, name):
    info = ctx.tables[name]
    t, st, reg = info["spec"], ctx.st, ctx.reg
    tname, cols, colidx, hdr, first = info["tname"], info["cols"], info["colidx"], info["hdr"], info["first"]
    fields = info["fields"]
    rows = [_row_values(t, r) for r in (t.get("rows") or [])]
    last = first + max(len(rows), 1) - 1
    span = first + R("range_rows")                  # 校验、条件格式覆盖到的行（表格向下扩展后仍有效）
    ws.sheet_view.showGridLines = True

    # 第 1 行：标题 + 来源（一行，不做封面）
    src = L("data_source", source=t.get("source") or "—", date=t.get("date") or ctx.meta.get("date") or "—", n=len(rows))
    put(ws, 1, 1, t.get("title") or name, font(13, True, st["title"]), al=align("left", "center"))
    put(ws, 1, 3 if len(cols) > 3 else 2, src, font(9, False, st["subtitle"]), al=align("left", "center"))
    ws.row_dimensions[1].height = 26

    # 第 2 行：表头（按字段类型区分底色），批注写类型、必填、口径、来源
    tn = L("type_names")
    ws.row_dimensions[hdr].height = R("head_height")
    for name_, ci in colidx.items():
        f = fields.get(name_)
        aux = _aux(info, name_)
        kind = "aux" if aux else ("remind" if name_ == info.get("remind") else (f or {}).get("type", "text"))
        bg, line = st["head_bg"], st["head_line"]
        if kind in ("formula", "remind"):
            bg, line = ROLE["fx_head_bg"], st["deep_mid"]
        elif kind == "ai":
            bg, line = ROLE["ai_head_bg"], ROLE["ai_line"]
        elif kind == "link":
            bg = ROLE["src_head_bg"]
        elif kind == "aux":
            bg, line = ROLE["aux_bg"], BRAND["grey_bar"]
        c = put(ws, hdr, ci, name_, font(10, True, st["head_fg"] if kind != "aux" else ROLE["aux_fg"]), fill(bg),
                align("left", "center", True), border(bottom=side(line, "medium"), right=side(st["grid"])))
        note = _header_note(ctx, info, name_, f, kind, tn)
        if note:
            c.comment = Comment(note, CONF.org_name())
            c.comment.width, c.comment.height = 260, 110

    # 数据行：原样写入；公式列写结构化引用
    templates = {}
    for name_ in cols:
        f = fields.get(name_)
        if f and f.get("type") == "formula":
            templates[name_] = "=" + struct_expr(f["formula"].lstrip("="), tname, colidx, reg)
        elif name_ == info.get("remind"):
            templates[name_] = _remind_formula(ctx, info)
        elif _aux(info, name_):
            templates[name_] = _aux_formula(info, _aux(info, name_), reg)
    for ri, row in enumerate(rows):
        r = first + ri
        ws.row_dimensions[r].height = R("row_height") if not _has_long(row, fields) else None
        for name_, ci in colidx.items():
            f = fields.get(name_) or {}
            v = templates.get(name_, row.get(name_))
            _write_cell(ctx, ws, r, ci, v, f, ri, info, row)
    if not rows:                                    # 没有数据时保留一行空行，表格才能建立
        for name_, ci in colidx.items():
            if name_ in templates:
                ws.cell(row=first, column=ci, value=templates[name_])

    # 建立 Excel 表格对象（筛选、结构化引用、计算列自动延伸）
    ref = "A%d:%s%d" % (hdr, get_column_letter(len(cols)), last)
    tab = Table(displayName=tname, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showFirstColumn=False, showLastColumn=False,
                                        showRowStripes=False, showColumnStripes=False)
    tab._initialise_columns()
    for tc, cname in zip(tab.tableColumns, cols):     # 列名必须与表头单元格一致，否则 Excel 会提示修复
        tc.name = cname
        if cname in templates:
            tc.calculatedColumnFormula = TableFormula(attr_text=templates[cname].lstrip("="))
    ws.add_table(tab)

    # 列宽、校验、条件格式
    _columns(ctx, ws, info, rows, span)
    _field_rules(ctx, ws, info, span)
    _rule_marks(ctx, ws, info, span)
    # 辅助列分组折叠
    for a in info["aux"]:
        cd = ws.column_dimensions[get_column_letter(colidx[a["name"]])]
        cd.outlineLevel, cd.hidden, cd.width = 1, True, 10
    try:
        ws.sheet_properties.outlinePr.summaryRight = False
    except AttributeError:
        pass
    # 冻结：表头 + 主键（或 freeze 指定的列）
    fz = max([colidx[f["name"]] for f in t["fields"] if f.get("freeze")] + [colidx[info["key"]]])
    ws.freeze_panes = ws.cell(row=first, column=fz + 1)
    ws.sheet_properties.tabColor = st["tab_data"]
    from xl_helpers import print_setup
    print_setup(ws, landscape=True, title_rows="%d:%d" % (hdr, hdr))
    info["last"] = last
    for i, ch in enumerate(t.get("charts") or []):                 # 可选：在数据表右侧放原生图表
        ch = dict(ch)
        ch.setdefault("data", name)
        ch.setdefault("anchor", "%s%d" % (get_column_letter(len(cols) + 2), hdr + i * 18))
        ctx.charts.append((name, ch))
    reg.tables[name]["last"] = last


def _row_values(t, r):
    """行可以写成 {字段: 值}，也可以写成列表（按非公式字段的顺序）。"""
    if isinstance(r, dict):
        return dict(r)
    names = [f["name"] for f in t["fields"] if f.get("type") != "formula"]
    return {n: (r[i] if i < len(r) else None) for i, n in enumerate(names)}


def _has_long(row, fields):
    lim = R("long_text_chars")
    return any(f.get("type") == "longtext" and text_width(row.get(n) or "") > lim * 2 for n, f in fields.items())


def _aux(info, name):
    return next((a for a in info["aux"] if a["name"] == name), None)


def _header_note(ctx, info, name, f, kind, tn):
    if kind == "aux":
        a = _aux(info, name)
        return L("aux_desc")[a.get("for", "view")].format(view=a.get("view", ""))
    if kind == "remind":
        return "%s｜%s" % (tn["formula"], L("rules_sheet"))
    if not f:
        return ""
    parts = [tn.get(f.get("type", "text"), f.get("type", ""))]
    if f.get("required"):
        parts.append(L("required"))
    if f.get("desc"):
        parts.append(f["desc"])
    if f.get("src"):
        parts.append(L("source") + f["src"])
    if kind == "ai":
        a = f.get("ai") or {}
        parts.append(L("ai_note", **{"from": a.get("from", "—"), "date": a.get("date") or ctx.meta.get("date") or "—"}))
    return "｜".join(parts)


def _remind_formula(ctx, info):
    """提醒标记：逐条判断提醒规则，命中的规则名用空格连起来；规则在“提醒规则”表停用后不再显示。"""
    tname, colidx, reg = info["tname"], info["colidx"], ctx.reg
    key = sref(tname, info["key"], this_row=True)
    yes = L("yes_no")[0]
    parts = []
    for ru in ctx.rules:
        if (ru.get("table") or next(iter(ctx.tables))) != info["spec"]["name"]:
            continue
        cond = struct_expr(ru["when"].lstrip("="), tname, colidx, reg)
        parts.append('IF(AND(%s="%s",%s),"%s ","")' % (ru["_enabled"], yes, cond, ru["mark"].replace('"', '""')))
    return '=IF(%s="","",TRIM(%s))' % (key, "&".join(parts) or '""')


def _aux_formula(info, a, reg):
    """辅助列公式（新旧版本 Excel 通用，不用 FILTER / SORTBY）。"""
    T = info["tname"]
    me = lambda c: sref(T, c, this_row=True)
    col = lambda c: sref(T, c)
    upto = lambda c: "INDEX(%s,1):%s" % (col(c), me(c))
    key = me(info["key"])
    if a["kind"] == "match":
        return '=IF(AND(%s<>"",%s),1,0)' % (key, struct_expr(a["when"].lstrip("="), T, info["colidx"], reg))
    if a["kind"] == "seq":
        m = a["match"]
        if not a.get("sort"):
            return '=IF(%s=1,COUNTIF(%s,1),"")' % (me(m), upto(m))
        s, op = a["sort"], (">" if a.get("desc") else "<")
        return '=IF(%s=1,COUNTIFS(%s,1,%s,"%s"&%s)+COUNTIFS(%s,1,%s,%s),"")' % (
            me(m), col(m), col(s), op, me(s), upto(m), upto(s), me(s))
    if a["kind"] == "group":
        g = a["group"]
        if a.get("match"):
            m = a["match"]
            return '=IF(%s=1,%s&"-"&COUNTIFS(%s,1,%s,%s),"")' % (me(m), me(g), upto(m), upto(g), me(g))
        return '=IF(%s="","",%s&"-"&COUNTIF(%s,%s))' % (key, me(g), upto(g), me(g))
    raise KeyError(a["kind"])


def _write_cell(ctx, ws, r, ci, v, f, ri, info, row):
    st = ctx.st
    typ = f.get("type", "text")
    name = ws.cell(row=info["hdr"], column=ci).value
    aux = _aux(info, name)
    v = None if v == "" else (to_date(v) if typ == "date" else v)          # 空字符串写成真正的空格，COUNTA 和填写率才准确
    fmt = field_fmt(f)
    color = BRAND["ink"]
    if typ == "formula" or name == info.get("remind"):
        color = ROLE["fx_fg"]
    elif typ == "ai":
        color = ROLE["ai_fg"]
    elif aux:
        color = ROLE["aux_fg"]
    numeric = typ in NUMERIC_TYPES or isinstance(v, (int, float)) and not isinstance(v, bool)
    h = "right" if numeric else ("center" if typ in ("date", "select", "bool") else "left")
    if typ == "formula" and f.get("format") in ("date",):
        h = "center"
    bg = fill(st["band"]) if st.get("band") and ri % 2 == 1 else None
    if f.get("input"):
        bg = fill(ROLE["input_bg"])
    if aux:
        bg = fill(ROLE["aux_bg"])
    c = put(ws, r, ci, v, font(10, False, color, FONTS["num"] if numeric or typ == "date" else None), bg,
            align(h, "center", typ == "longtext"), border(bottom=side(st["grid"]), right=side(st["grid"])), fmt)
    if typ == "link" and v:
        disp = f.get("display")
        if disp:
            c.value = ROWTOK.sub(lambda m: str(row.get(m.group(1), "")), disp)
        c.hyperlink = str(v)
        c.font = font(10, False, ROLE["link"], underline="single")
    if is_formula(c.value) and TOKEN.search(c.value):
        ctx.reg.defer(ws, c.coordinate, c.value)


def _columns(ctx, ws, info, rows, span):
    lo, hi = R("col_width")
    for name, ci in info["colidx"].items():
        f = info["fields"].get(name) or {}
        L_ = get_column_letter(ci)
        if f.get("width"):
            w = f["width"]
        elif f.get("type") == "longtext":
            w = R("long_text_width")
        elif f.get("type") in ("formula",) or name == info.get("remind"):
            w = max(lo, min(hi, text_width(name) + 4, 22))
        else:
            vals = [name] + [r.get(name) for r in rows[:300]]
            w = max(lo, min(hi, max(text_width(x if not isinstance(x, (dt.date,)) else "2026-01-01") for x in vals) + 3))
        ws.column_dimensions[L_].width = w
        rng = "%s%d:%s%d" % (L_, info["first"], L_, span)
        if f.get("options_ref"):
            dv = DataValidation(type="list", formula1=ctx.reg.cells["options." + f["options_ref"]], allow_blank=True,
                                showErrorMessage=f.get("type") != "person", errorTitle=L("pick_title"),
                                error=L("pick_msg", opts="、".join(ctx.options[f["options_ref"]])))
            ws.add_data_validation(dv)
            dv.add(rng)
        if f.get("type") == "date" and not f.get("formula"):
            dv = DataValidation(type="date", operator="greaterThan", formula1="DATE(1900,1,1)", allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(rng)


def _field_rules(ctx, ws, info, span):
    """字段级条件格式：必填为空、按取值着色、智能列与对照字段不一致、数据条。"""
    st, colidx, first = ctx.st, info["colidx"], info["first"]
    keycol = get_column_letter(colidx[info["key"]])
    for name, f in info["fields"].items():
        ci = colidx[name]
        L_ = get_column_letter(ci)
        rng = "%s%d:%s%d" % (L_, first, L_, span)
        cell = "%s%d" % (L_, first)
        if f.get("required"):
            ws.conditional_formatting.add(rng, FormulaRule(
                formula=['AND($%s%d<>"",LEN(%s)=0)' % (keycol, first, cell)], fill=fill(ROLE["todo_bg"]), stopIfTrue=True))
        for val, lv in (f.get("styles") or {}).items():
            fl, ft = level_style(lv)
            ws.conditional_formatting.add(rng, FormulaRule(formula=['%s="%s"' % (cell, str(val).replace('"', '""'))],
                                                           fill=fl, font=ft))
        chk = (f.get("ai") or {}).get("check")
        if chk and chk in colidx:
            other = "$%s%d" % (get_column_letter(colidx[chk]), first)
            fl, ft = level_style("info")
            ws.conditional_formatting.add(rng, FormulaRule(
                formula=['AND(%s<>"",%s<>%s)' % (cell, cell, other)], fill=fl, font=ft))
        if f.get("databar"):
            ws.conditional_formatting.add(rng, DataBarRule(start_type="num", start_value=0, end_type="max",
                                                           color="FF" + st["accent_light"], showValue=True))


def _rule_marks(ctx, ws, info, span):
    """提醒规则命中时，把规则指定的字段标色（条件格式，随数据自动变化）。"""
    yes = L("yes_no")[0]
    keycol = get_column_letter(info["colidx"][info["key"]])
    for ru in ctx.rules:
        if (ru.get("table") or next(iter(ctx.tables))) != info["spec"]["name"]:
            continue
        cond = a1_expr(ru["when"].lstrip("="), info["colidx"], info["first"], ctx.reg)
        fl, ft = level_style(ru.get("level", "warn"))
        targets = list(ru.get("fields") or [])
        for name in targets:
            if name not in info["colidx"]:
                raise KeyError("提醒规则 %s 标记的字段不存在：%s" % (ru["id"], name))
            L_ = get_column_letter(info["colidx"][name])
            ws.conditional_formatting.add("%s%d:%s%d" % (L_, info["first"], L_, span), FormulaRule(
                formula=['AND(%s="%s",$%s%d<>"",%s)' % (ru["_enabled"], yes, keycol, info["first"], cond)],
                fill=fl, font=ft))
    if info.get("remind"):
        L_ = get_column_letter(info["colidx"][info["remind"]])
        rng = "%s%d:%s%d" % (L_, info["first"], L_, span)
        for ru in sorted(ctx.rules, key=lambda x: {"bad": 0, "warn": 1, "info": 2}.get(x.get("level"), 1)):
            fl, ft = level_style(ru.get("level", "warn"))
            ws.conditional_formatting.add(rng, FormulaRule(
                formula=['ISNUMBER(SEARCH("%s",%s%d))' % (ru["mark"], L_, info["first"])], fill=fl, font=ft, stopIfTrue=True))


# ---------------- 共用样式 ----------------
def _grid(st):
    return border(bottom=side(st["grid"]), right=side(st["grid"]))


def _sheet_title(ws, st, text, note=None):
    put(ws, 1, 1, text, font(13, True, st["title"]), al=align("left", "center"))
    if note:
        put(ws, 1, 3, note, font(9, False, st["subtitle"]))
    ws.row_dimensions[1].height = 26


def _header(ws, st, row, names, start=1):
    ws.row_dimensions[row].height = R("head_height")
    for i, n in enumerate(names):
        put(ws, row, start + i, n, font(10, True, st["head_fg"]), fill(st["head_bg"]), align("left", "center", True),
            border(bottom=side(st["head_line"], "medium"), right=side(st["grid"])))
