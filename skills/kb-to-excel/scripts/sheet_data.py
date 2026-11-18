# -*- coding: utf-8 -*-
"""
数据类工作表：cover 封面说明页 / table 明细表 / matrix 对比矩阵 / notes 口径说明。
每个函数签名：fn(ctx, ws, spec)。字段说明见 reference/sheet-types.md。
"""
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from xl_helpers import (TOKEN, Registry, align, auto_width, border, box, fill, font, is_formula,
                        print_setup, put, side, text_width, title_block)
from xl_theme import BRAND, FORMATS, NUM_FONT, ROLE

NUMERIC = {"int", "money", "money2", "wan", "yi", "pct", "pct0", "ratio", "delta", "delta_pt"}


def _fmt(col):
    f = col.get("format", "text")
    return FORMATS.get(f, f)


def write_value(ctx, ws, r, c, value, fmt=None, **style):
    """写单元格；含 {引用} 的公式先占位，最后统一解析。"""
    cell = put(ws, r, c, value, fmt=fmt, **style)
    if is_formula(value) and TOKEN.search(value):
        ctx.reg.defer(ws, cell.coordinate, value)
    return cell


def _rule_fills():
    return {
        "bad": (fill(BRAND["red_light"]), font(10, True, BRAND["red"])),
        "warn": (fill(BRAND["yellow_light"]), font(10, True, "9C6500")),
        "good": (fill(BRAND["teal_light"]), font(10, True, BRAND["teal"])),
    }


def apply_rule(ws, rng, rule, first_cell):
    """条件格式：sign 正负着色 / lt gt between 阈值 / top 前 N 名 / scale 色阶 / databar 数据条。"""
    t = rule.get("type")
    styles = _rule_fills()
    if t == "sign":
        good_up = rule.get("good", "up") == "up"
        pos = font(10, True, BRAND["teal"] if good_up else BRAND["red"])
        neg = font(10, True, BRAND["red"] if good_up else BRAND["teal"])
        ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], font=pos))
        ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], font=neg))
    elif t in ("lt", "gt", "between", "eq"):
        fl, ft = styles[rule.get("style", "bad")]
        op = {"lt": "lessThan", "gt": "greaterThan", "between": "between", "eq": "equal"}[t]
        vals = rule["value"] if isinstance(rule["value"], list) else [rule["value"]]
        formula = [('"%s"' % v) if isinstance(v, str) else str(v) for v in vals]
        ws.conditional_formatting.add(rng, CellIsRule(operator=op, formula=formula, fill=fl, font=ft))
    elif t == "top":
        n = int(rule.get("n", 3))
        fl, ft = styles[rule.get("style", "good")]
        col_rng = rng.replace("$", "")
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=["RANK(%s,%s)<=%d" % (first_cell, _abs(col_rng), n)], fill=fl, font=ft))
    elif t == "scale":
        ws.conditional_formatting.add(rng, ColorScaleRule(
            start_type="min", start_color="FFFFFFFF", mid_type="percentile", mid_value=50,
            mid_color="FF" + BRAND["orange_light"], end_type="max", end_color="FF" + BRAND["orange"]))
    elif t == "databar":
        ws.conditional_formatting.add(rng, DataBarRule(
            start_type="num", start_value=0, end_type="max", color="FF" + rule.get("color", "F2A65A"),
            showValue=True))
    elif t == "text":
        fl, ft = styles[rule.get("style", "bad")]
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=['%s="%s"' % (first_cell, rule["value"])], fill=fl, font=ft))


def _abs(rng):
    a, b = rng.split(":")
    def ab(x):
        col = "".join(ch for ch in x if ch.isalpha())
        row = "".join(ch for ch in x if ch.isdigit())
        return "$%s$%s" % (col, row)
    return ab(a) + ":" + ab(b)


# ---------------- 封面说明页 ----------------
def cover(ctx, ws, spec):
    st = ctx.st
    meta = ctx.meta
    ws.sheet_view.showGridLines = False
    widths = [4, 8, 22, 54, 14, 4]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    band = fill(st["head_bg"] if st["head_bg"] != BRAND["bg_soft"] else BRAND["white"])
    fg = st["head_fg"] if st["head_bg"] != BRAND["bg_soft"] else BRAND["ink"]
    for r in range(1, 9):
        ws.row_dimensions[r].height = 20
        for c in range(1, 7):
            ws.cell(row=r, column=c).fill = band
    if st["head_bg"] == BRAND["bg_soft"]:
        for c in range(1, 7):
            ws.cell(row=1, column=c).fill = fill(BRAND["orange"])
    put(ws, 2, 2, (meta.get("brand", "富卫人寿") + "　FWD"), font(11, True, st["accent"] if fg == BRAND["white"] else BRAND["orange"]))
    put(ws, 4, 2, spec.get("category", meta.get("category", "")), font(11, True, st["accent"] if fg == BRAND["white"] else BRAND["muted"]))
    ws.row_dimensions[5].height = 36
    put(ws, 5, 2, spec.get("title") or meta["title"], font(22, True, fg))
    put(ws, 6, 2, spec.get("subtitle") or meta.get("subtitle", ""), font(11, False, fg))

    r = 10
    info = [(k, meta.get(v)) for k, v in (("编制部门", "department"), ("适用对象", "audience"),
                                           ("数据口径", "as_of"), ("版本", "version"),
                                           ("更新日期", "date"), ("密级", "confidentiality")) if meta.get(v)]
    for k, v in info:
        put(ws, r, 3, k, font(9.5, False, BRAND["muted"]), bd=border(bottom=side()))
        put(ws, r, 4, v, font(10, True), bd=border(bottom=side()))
        r += 1
    if spec.get("purpose"):
        r += 1
        put(ws, r, 2, "用途", font(11, True, st["title"]))
        r += 1
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        put(ws, r, 3, spec["purpose"], font(10), al=align("left", "top", True))
        ws.row_dimensions[r].height = max(20, 16 * (1 + int(text_width(spec["purpose"]) / 80)))
        r += 1

    r += 1
    put(ws, r, 2, "工作表目录", font(11, True, st["title"]))
    r += 1
    for c, h in zip((2, 3, 4, 5), ("序号", "工作表", "内容", "")):
        put(ws, r, c, h, font(9.5, True, st["head_fg"] if st["head_bg"] != BRAND["bg_soft"] else BRAND["ink"]),
            fill(st["head_bg"]), align("center" if c != 4 else "left"))
    r += 1
    n = 0
    for s in ctx.sheets:
        if s.get("type") == "cover":
            continue
        n += 1
        put(ws, r, 2, n, font(10, True, BRAND["orange"], NUM_FONT), al=align("center"), bd=border(bottom=side()))
        put(ws, r, 3, s["name"], font(10, True), bd=border(bottom=side()))
        put(ws, r, 4, s.get("desc", ""), font(9.5, False, BRAND["ink_soft"]), al=align("left", "center", True),
            bd=border(bottom=side()))
        link = put(ws, r, 5, "前往 →", font(9.5, True, BRAND["orange_dark"], underline="single"),
                   al=align("center"), bd=border(bottom=side()))
        link.hyperlink = "#'%s'!A1" % s["name"].replace("'", "''")
        ws.row_dimensions[r].height = 22
        r += 1

    if spec.get("how_to"):
        r += 1
        put(ws, r, 2, "怎么用", font(11, True, st["title"]))
        r += 1
        for i, tip in enumerate(spec["how_to"], 1):
            put(ws, r, 2, i, font(10, True, BRAND["orange"], NUM_FONT), al=align("center"))
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
            put(ws, r, 3, tip, font(10), al=align("left", "center", True))
            r += 1

    if spec.get("legend", True):
        r += 1
        put(ws, r, 2, "单元格说明", font(11, True, st["title"]))
        r += 1
        for label, f, desc in (("录入格", fill(ROLE["input_bg"]), "黄色底，可以修改，相关结果会自动重算"),
                               ("公式格", None, "深绿色字，由公式自动计算，请勿手工覆盖"),
                               ("待补充", fill(ROLE["todo_bg"]), "知识库中未查到，需要人工补充或确认")):
            c = put(ws, r, 3, label, font(9.5, True, ROLE["formula_fg"] if label == "公式格" else BRAND["ink"]),
                    f, align("center"), box(ROLE["input_border"] if label == "录入格" else BRAND["line"]))
            put(ws, r, 4, desc, font(9.5, False, BRAND["ink_soft"]))
            r += 1
    if meta.get("disclaimer"):
        r += 1
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        put(ws, r, 2, meta["disclaimer"], font(8.5, False, BRAND["muted"], italic=True), al=align("left", "top", True))
        ws.row_dimensions[r].height = 30
    print_setup(ws, landscape=False, brand=meta.get("brand", "富卫人寿"))


# ---------------- 明细表 ----------------
def table(ctx, ws, spec):
    st = ctx.st
    cols = spec["columns"]
    names = [c["name"] for c in cols]
    rows = spec.get("rows", [])
    n = len(cols)
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), n, spec.get("note"))
    hdr = r
    head_bd = border(bottom=side(BRAND["orange"], "medium")) if st["head_bg"] == BRAND["bg_soft"] else box(st["head_bg"])
    ws.row_dimensions[hdr].height = 30
    hi = spec.get("highlight_col")
    for ci, col in enumerate(cols, 1):
        label = col["name"] + (("（%s）" % col["unit"]) if col.get("unit") else "")
        put(ws, hdr, ci, label, font(10, True, st["head_fg"]), fill(st["head_bg"]), align("center", "center", True), head_bd)
    first = hdr + 1
    keys = {}
    for ri, row in enumerate(rows):
        rr = first + ri
        ws.row_dimensions[rr].height = spec.get("row_height", 20)
        stripe = st["stripe"] and ri % 2 == 1
        for ci, col in enumerate(cols, 1):
            v = row[ci - 1] if ci - 1 < len(row) else None
            if col.get("formula") and v in (None, ""):
                v = Registry.row_formula(col["formula"], {nm: i for i, nm in enumerate(names, 1)}, rr)
            numeric = col.get("format", "text") not in ("text", "@") or isinstance(v, (int, float))
            f = font(10, ci == 1 and spec.get("first_col_bold", True),
                     ROLE["formula_fg"] if is_formula(v) else BRAND["ink"],
                     NUM_FONT if numeric and not isinstance(v, str) else None)
            bg = fill(st["hi_col"]) if hi == col["name"] else (fill(st["stripe"]) if stripe else None)
            al = align("right" if numeric else ("center" if col.get("align") == "center" else "left"), "center",
                       col.get("wrap", False))
            if col.get("input"):
                bg = fill(ROLE["input_bg"])
            write_value(ctx, ws, rr, ci, v, _fmt(col) if numeric or col.get("format") else None,
                        f=f, fl=bg, al=al, bd=border(bottom=side()))
        if row and row[0] not in (None, ""):
            keys[str(row[0])] = rr
    last = first + len(rows) - 1
    total_row = None
    if spec.get("total") and rows:
        total_row = last + 1
        ws.row_dimensions[total_row].height = 22
        label = spec["total"] if isinstance(spec["total"], str) else "合计"
        for ci, col in enumerate(cols, 1):
            L = get_column_letter(ci)
            t = col.get("total")
            v = None
            if ci == 1:
                v = label
            elif t == "sum":
                v = "=SUBTOTAL(109,%s%d:%s%d)" % (L, first, L, last)
            elif t == "avg":
                v = "=SUBTOTAL(101,%s%d:%s%d)" % (L, first, L, last)
            elif t == "count":
                v = "=SUBTOTAL(103,%s%d:%s%d)" % (L, first, L, last)
            elif isinstance(t, str) and t.startswith("="):
                v = Registry.row_formula(t, {nm: i for i, nm in enumerate(names, 1)}, total_row)
            write_value(ctx, ws, total_row, ci, v, _fmt(col) if ci > 1 else None,
                        f=font(10, True, BRAND["ink"], NUM_FONT if ci > 1 else None), fl=fill(st["total_bg"]),
                        al=align("right" if ci > 1 else "left"),
                        bd=border(top=side(st["head_bg"] if st["head_bg"] != BRAND["bg_soft"] else BRAND["orange"], "medium")))
    ctx.reg.table(spec["name"], names, first, last, keys, total_row)

    # 列宽、校验、条件格式
    for ci, col in enumerate(cols, 1):
        L = get_column_letter(ci)
        vals = [col["name"] + (col.get("unit") or "")] + [r_[ci - 1] if ci - 1 < len(r_) else "" for r_ in rows]
        vals = ["0000000000" if is_formula(v) else v for v in vals]
        ws.column_dimensions[L].width = col.get("width") or auto_width(vals, lo=9, hi=40)
        if text_width(max(vals, key=text_width) if vals else "") > 40:
            for rr in range(first, last + 1):
                ws.cell(row=rr, column=ci).alignment = align("left", "center", True)
        rng = "%s%d:%s%d" % (L, first, L, last)
        if col.get("options") and rows:
            dv = DataValidation(type="list", formula1='"%s"' % ",".join(col["options"]), allow_blank=True,
                                showErrorMessage=True, errorTitle="请从下拉列表选择",
                                error="可选值：" + "、".join(col["options"]))
            ws.add_data_validation(dv)
            dv.add("%s%d:%s%d" % (L, first, L, last + spec.get("spare_rows", 0)))
        for rule in ([col["rule"]] if isinstance(col.get("rule"), dict) else col.get("rule", [])) or []:
            if rows:
                apply_rule(ws, rng, rule, "%s%d" % (L, first))
        if col.get("databar") and rows:
            apply_rule(ws, rng, {"type": "databar"}, "%s%d" % (L, first))
    if rows:
        ws.freeze_panes = ws.cell(row=first, column=2 if spec.get("freeze_first_col", True) else 1)
        if spec.get("filter", True):
            ws.auto_filter.ref = "A%d:%s%d" % (hdr, get_column_letter(n), last)
    after = (total_row or last) + 2
    for note in spec.get("notes", []):
        put(ws, after, 1, "注：" + note, font(9, False, BRAND["muted"]))
        after += 1
    if spec.get("source"):
        put(ws, after, 1, "资料来源：" + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=n > 5, title_rows="%d:%d" % (hdr, hdr), brand=ctx.meta.get("brand", "富卫人寿"))
    for i, ch in enumerate(spec.get("charts", [])):
        ch = dict(ch)
        ch.setdefault("data", spec["name"])
        ch.setdefault("anchor", "%s%d" % (get_column_letter(n + 2), hdr + i * 18))
        ctx.charts.append((spec["name"], ch))


# ---------------- 对比矩阵 ----------------
MARKS = {"✓": BRAND["teal"], "✔": BRAND["teal"], "✗": BRAND["red"], "✘": BRAND["red"], "—": BRAND["muted"], "-": BRAND["muted"]}


def matrix(ctx, ws, spec):
    st = ctx.st
    objs = spec["objects"]
    hi = spec.get("highlight")
    n = len(objs) + 1
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), n, spec.get("note"))
    ws.column_dimensions["A"].width = spec.get("label_width", 20)
    for i in range(len(objs)):
        ws.column_dimensions[get_column_letter(i + 2)].width = spec.get("col_width", 24)
    # 推荐标签行
    if hi:
        for i, o in enumerate(objs, 2):
            if o == hi:
                put(ws, r, i, spec.get("highlight_label", "★ 推荐"), font(9, True, BRAND["white"]),
                    fill(BRAND["orange"]), align("center"))
        r += 1
    hdr = r
    ws.row_dimensions[hdr].height = 34
    put(ws, hdr, 1, spec.get("corner", "对比项"), font(10, True, st["head_fg"]), fill(st["head_bg"]), align("left", "center", indent=1))
    for i, o in enumerate(objs, 2):
        on = o == hi
        put(ws, hdr, i, o, font(11, True, BRAND["white"] if on or st["head_bg"] != BRAND["bg_soft"] else BRAND["ink"]),
            fill(BRAND["orange_dark"] if on and st["head_bg"] == BRAND["orange"] else (BRAND["orange"] if on else st["head_bg"])),
            align("center", "center", True))
    r = hdr + 1
    keys = {}
    for g in spec["groups"]:
        if g.get("name"):
            ws.row_dimensions[r].height = 22
            for c in range(1, n + 1):
                ws.cell(row=r, column=c).fill = fill(st["group_bg"])
            put(ws, r, 1, g["name"], font(10, True, st["group_fg"]), fill(st["group_bg"]), align("left", "center", indent=1))
            r += 1
        for row in g["rows"]:
            lines = max([1] + [1 + int(text_width(v) / (spec.get("col_width", 24) * 0.95)) for v in row["values"]])
            ws.row_dimensions[r].height = max(22, 16 * lines + 6)
            put(ws, r, 1, row["label"], font(10, True, BRAND["ink"]), al=align("left", "center", True, 1),
                bd=border(bottom=side()))
            for i, v in enumerate(row["values"], 2):
                on = objs[i - 2] == hi
                color = MARKS.get(str(v).strip(), ROLE["formula_fg"] if is_formula(v) else BRAND["ink"])
                big = str(v).strip() in MARKS
                write_value(ctx, ws, r, i, v, FORMATS.get(row.get("format", ""), row.get("format")) if row.get("format") else None,
                            f=font(12 if big else 10, big or (on and row.get("emphasis", False)), color,
                                   NUM_FONT if isinstance(v, (int, float)) else None),
                            fl=fill(st["hi_col"]) if on else None, al=align("center", "center", True),
                            bd=border(bottom=side()))
            keys[row["label"]] = r
            r += 1
    ctx.reg.table(spec["name"], [spec.get("corner", "对比项")] + objs, hdr + 1, r - 1, keys)
    ws.freeze_panes = ws.cell(row=hdr + 1, column=2)
    r += 1
    for note in spec.get("notes", []):
        put(ws, r, 1, "注：" + note, font(9, False, BRAND["muted"]))
        r += 1
    if spec.get("source"):
        put(ws, r, 1, "资料来源：" + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=len(objs) > 3, title_rows="%d:%d" % (hdr, hdr), brand=ctx.meta.get("brand", "富卫人寿"))


# ---------------- 口径说明 ----------------
def notes(ctx, ws, spec):
    st = ctx.st
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), 4)
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 70
    ws.column_dimensions["D"].width = 18
    for sec in spec.get("sections", []):
        put(ws, r, 1, "■", font(9, True, BRAND["orange"]))
        put(ws, r, 2, sec["heading"], font(11.5, True, st["title"]))
        r += 1
        for it in sec.get("items", []):
            if isinstance(it, (list, tuple)):
                put(ws, r, 2, it[0], font(10, True), al=align("left", "top", True), bd=border(bottom=side()))
                put(ws, r, 3, it[1], font(10, False, BRAND["ink_soft"]), al=align("left", "top", True), bd=border(bottom=side()))
                txt = it[1]
            else:
                ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
                put(ws, r, 2, "· " + it, font(10, False, BRAND["ink_soft"]), al=align("left", "top", True))
                txt = it
            ws.row_dimensions[r].height = max(18, 15 * (1 + int(text_width(txt) / 130)))
            r += 1
        r += 1
    ws.sheet_properties.tabColor = BRAND["muted"]
    print_setup(ws, landscape=False, brand=ctx.meta.get("brand", "富卫人寿"))


REGISTRY = {"cover": cover, "table": table, "matrix": matrix, "notes": notes}
