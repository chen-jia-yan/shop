# -*- coding: utf-8 -*-
"""
工具类工作表：dashboard 看板 / gantt 甘特跟踪 / calculator 试算 / checklist 清单。
字段说明见 reference/sheet-types.md。
"""
import datetime as dt

from openpyxl.formatting.rule import CellIsRule, DataBarRule, FormulaRule
from openpyxl.styles import Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from sheets_data import apply_rule, write_value
from xl_helpers import (Registry, align, border, box, fill, font, is_formula, print_setup, put, side,
                        text_width, title_block)
from xl_theme import BRAND, FORMATS, NUM_FONT, ROLE


def _date(v):
    if isinstance(v, (dt.date, dt.datetime)) or v is None:
        return v
    return dt.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _fmt(name):
    return FORMATS.get(name, name) if name else None


# ---------------- 看板 ----------------
def dashboard(ctx, ws, spec):
    st = ctx.st
    grid = 12                                   # B..M 共 12 列
    ws.column_dimensions["A"].width = 2
    for c in range(2, 2 + grid):
        ws.column_dimensions[get_column_letter(c)].width = 11
    ws.column_dimensions[get_column_letter(2 + grid)].width = 2
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), grid + 2, spec.get("note"))

    kpis = spec.get("kpis", [])
    if kpis:
        span = max(2, grid // len(kpis))
        for i, k in enumerate(kpis):
            c0 = 2 + i * span
            c1 = c0 + span - 1
            for rr in range(r, r + 4):
                for cc in range(c0, c1 + 1):
                    ws.cell(row=rr, column=cc).fill = fill(st["tile_bg"])
                    left = side(BRAND["white"], "thick") if cc == c0 and i > 0 else None
                    ws.cell(row=rr, column=cc).border = border(left=left)
            for cc in range(c0, c1 + 1):
                ws.cell(row=r, column=cc).fill = fill(st["tile_bar"])
            ws.row_dimensions[r].height = 5
            label_c = st["tile_value"] if st["tile_bg"] == BRAND["green"] else BRAND["ink_soft"]
            ws.merge_cells(start_row=r + 1, start_column=c0, end_row=r + 1, end_column=c1)
            put(ws, r + 1, c0, k["label"] + (("（%s）" % k["unit"]) if k.get("unit") else ""),
                font(9.5, False, "C9D6D1" if st["tile_bg"] == BRAND["green"] else label_c),
                al=align("left", "bottom", indent=1))
            ws.merge_cells(start_row=r + 2, start_column=c0, end_row=r + 2, end_column=c1)
            write_value(ctx, ws, r + 2, c0, k["value"], _fmt(k.get("format", "int")),
                        f=font(24, True, st["tile_value"], NUM_FONT), al=align("left", "center", indent=1))
            ws.merge_cells(start_row=r + 3, start_column=c0, end_row=r + 3, end_column=c1)
            if k.get("delta") is not None:
                dc = write_value(ctx, ws, r + 3, c0, k["delta"], _fmt(k.get("delta_format", "delta")),
                                 f=font(9.5, True, BRAND["muted"], NUM_FONT), al=align("left", "top", indent=1))
                good_up = k.get("good", "up") == "up"
                ok = BRAND["teal"] if st["tile_bg"] != BRAND["green"] else "7FD1C2"
                bad = BRAND["red"] if st["tile_bg"] != BRAND["green"] else "FF9B8F"
                ws.conditional_formatting.add(dc.coordinate, CellIsRule(
                    operator="greaterThan", formula=["0"], font=font(9.5, True, ok if good_up else bad)))
                ws.conditional_formatting.add(dc.coordinate, CellIsRule(
                    operator="lessThan", formula=["0"], font=font(9.5, True, bad if good_up else ok)))
            elif k.get("note"):
                put(ws, r + 3, c0, k["note"], font(9, False, BRAND["muted"]), al=align("left", "top", indent=1))
        ws.row_dimensions[r + 1].height = 20
        ws.row_dimensions[r + 2].height = 38
        ws.row_dimensions[r + 3].height = 20
        r += 5

    if spec.get("insights"):
        put(ws, r, 2, "关键结论", font(11, True, st["title"]))
        r += 1
        for i, t in enumerate(spec["insights"], 1):
            put(ws, r, 2, i, font(10, True, BRAND["orange"], NUM_FONT), al=align("center", "top"))
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=1 + grid)
            write_value(ctx, ws, r, 3, t, f=font(10), al=align("left", "top", True))
            ws.row_dimensions[r].height = max(18, 15 * (1 + int(text_width(t) / 120)))
            r += 1
        r += 1

    if spec.get("rank"):
        r = _rank(ctx, ws, spec["rank"], r)

    charts = spec.get("charts", [])
    for i, ch in enumerate(charts):
        ch = dict(ch)
        ch.setdefault("anchor", "%s%d" % (get_column_letter(2 + (i % 2) * 6), r + (i // 2) * 17))
        ch.setdefault("width", 13.6)
        ch.setdefault("height", 7.8)
        ctx.charts.append((spec["name"], ch))
    ws.sheet_properties.tabColor = st["accent"]
    ws.sheet_view.zoomScale = 90
    print_setup(ws, landscape=True, brand=ctx.meta.get("brand", "富卫人寿"))


def _rank(ctx, ws, rk, r):
    """动态排名：按指定列取前 N，数据变了排名自动跟着变。"""
    st = ctx.st
    n = int(rk.get("top", 5))
    by = rk["by"]
    put(ws, r, 2, rk.get("title", "按%s排名前 %d" % (by, n)), font(11, True, st["title"]))
    r += 1
    show = rk.get("columns", [rk.get("key", "")])
    key_col = rk["key"]
    heads = ["名次"] + show
    spans = [1] + [max(2, (12 - 1) // len(show))] * len(show)
    c = 2
    pos = []
    for h, sp in zip(heads, spans):
        ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + sp - 1)
        put(ws, r, c, h, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center"))
        pos.append(c)
        c += sp
    data = rk["data"]
    order = "SMALL" if rk.get("ascending") else "LARGE"
    for k in range(1, n + 1):
        rr = r + k
        put(ws, rr, 2, k, font(10, True, BRAND["orange"] if k <= 3 else BRAND["ink_soft"], NUM_FONT),
            al=align("center"), bd=border(bottom=side()))
        val = "%s({%s.%s},%d)" % (order, data, by, k)
        match = "MATCH(%s,{%s.%s},0)" % (val, data, by)
        for h, c0, sp in zip(show, pos[1:], spans[1:]):
            ws.merge_cells(start_row=rr, start_column=c0, end_row=rr, end_column=c0 + sp - 1)
            f = "=IFERROR(INDEX({%s.%s},%s),\"\")" % (data, h, match)
            fmt = _fmt(rk.get("formats", {}).get(h))
            write_value(ctx, ws, rr, c0, f, fmt, f=font(10, h == key_col, ROLE["formula_fg"] if h != key_col else BRAND["ink"]),
                        al=align("left" if h == key_col else "right", "center", indent=1), bd=border(bottom=side()))
    return r + n + 2


# ---------------- 甘特跟踪 ----------------
GANTT_COLS = [("编号", "id", 7), ("事项", "task", 30), ("责任部门", "dept", 12), ("责任人", "owner", 9),
              ("开始", "start", 11), ("完成", "end", 11), ("状态", "status", 9), ("进度", "progress", 8),
              ("预警", None, 13)]


def gantt(ctx, ws, spec):
    st = ctx.st
    tasks = spec["tasks"]
    unit = spec.get("unit", "week")
    step = 7 if unit == "week" else 1
    start = _date(spec.get("start") or min(_date(t["start"]) for t in tasks))
    end = _date(spec.get("end") or max(_date(t["end"]) for t in tasks))
    if unit == "week":
        start = start - dt.timedelta(days=start.weekday())     # 对齐到周一
    slots = []
    d = start
    while d <= end:
        slots.append(d)
        d += dt.timedelta(days=step)
    ncols = len(GANTT_COLS) + len(slots)
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), min(ncols, 20), spec.get("note"))

    # 汇总条
    statuses = spec.get("statuses", ["未开始", "进行中", "已完成"])
    sum_row = r
    hdr = r + 3
    first = hdr + 1
    last = first + len(tasks) - 1
    S = "$G$%d:$G$%d" % (first, last)
    E = "$F$%d:$F$%d" % (first, last)
    stats = [("事项总数", "=COUNTA($B$%d:$B$%d)" % (first, last), "int"),
             ("已完成", '=COUNTIF(%s,"已完成")' % S, "int"),
             ("进行中", '=COUNTIF(%s,"进行中")' % S, "int"),
             ("已逾期", '=COUNTIFS(%s,"<>已完成",%s,"<"&TODAY())' % (S, E), "int"),
             ("完成率", '=IFERROR(COUNTIF(%s,"已完成")/COUNTA($B$%d:$B$%d),0)' % (S, first, last), "pct0")]
    for i, (label, f, fm) in enumerate(stats):
        c = 1 + i * 2                       # 每个指标占两列：A-B、C-D、E-F……
        put(ws, sum_row, c, label, font(9, False, BRAND["muted"]), fill(st["tile_bg"]), align("left", "center", indent=1))
        ws.merge_cells(start_row=sum_row, start_column=c, end_row=sum_row, end_column=c + 1)
        cell = put(ws, sum_row + 1, c, f, font(18, True, BRAND["red"] if label == "已逾期" else st["tile_value"], NUM_FONT),
                   fill(st["tile_bg"]), align("left", "center", indent=1), fmt=FORMATS[fm])
        ws.merge_cells(start_row=sum_row + 1, start_column=c, end_row=sum_row + 1, end_column=c + 1)
        for rr in (sum_row, sum_row + 1):
            for cc in (c, c + 1):
                ws.cell(row=rr, column=cc).fill = fill(st["tile_bg"])
        ws.cell(row=sum_row, column=c).border = border(top=side(st["tile_bar"], "thick"))
        ws.cell(row=sum_row, column=c + 1).border = border(top=side(st["tile_bar"], "thick"))
    ws.row_dimensions[sum_row + 1].height = 30

    # 表头：左侧字段 + 右侧时间刻度（上一行月份）
    month_row = hdr - 1
    for ci, (label, _, w) in enumerate(GANTT_COLS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
        put(ws, hdr, ci, label, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center", "center", True))
    g0 = len(GANTT_COLS) + 1
    month_start = None
    for i, d in enumerate(slots):
        c = g0 + i
        ws.column_dimensions[get_column_letter(c)].width = 5.2 if unit == "week" else 3.2
        cell = put(ws, hdr, c, d, font(8, True, st["head_fg"]), fill(st["head_bg"]), align("center", "center"),
                   fmt="m/d" if unit == "week" else "d")
        key = (d.year, d.month)
        if month_start is None or key != month_start[0]:
            if month_start:
                _month(ws, month_row, month_start, c - 1, st)
            month_start = (key, c)
    if month_start:
        _month(ws, month_row, month_start, g0 + len(slots) - 1, st)
    ws.row_dimensions[hdr].height = 26

    keys = {}
    for i, t in enumerate(tasks):
        rr = first + i
        ws.row_dimensions[rr].height = 22
        vals = [t.get("id", i + 1), t["task"], t.get("dept", ""), t.get("owner", ""), _date(t["start"]),
                _date(t["end"]), t.get("status", "未开始"), t.get("progress", 0)]
        for ci, v in enumerate(vals, 1):
            fm = {5: "yyyy-mm-dd", 6: "yyyy-mm-dd", 8: "0%"}.get(ci)
            put(ws, rr, ci, v, font(9.5, ci == 2, BRAND["ink"], NUM_FONT if ci in (1, 5, 6, 8) else None),
                fill(ROLE["input_bg"]) if ci in (7, 8) else None,
                align("center" if ci in (1, 4, 5, 6, 7, 8) else "left", "center", ci == 2),
                border(bottom=side()), fm)
        warn = ('=IF($G{r}="已完成","✓ 已完成",IF($F{r}<TODAY(),"逾期 "&(TODAY()-$F{r})&" 天",'
                'IF($F{r}-TODAY()<=7,"7 天内到期","")))').format(r=rr)
        put(ws, rr, 9, warn, font(9, True, ROLE["formula_fg"]), al=align("center"), bd=border(bottom=side()))
        for c in range(g0, g0 + len(slots)):
            ws.cell(row=rr, column=c).border = border(bottom=side("EEEEEE"), left=side("F3F3F3"))
        keys[str(vals[0])] = rr
    ctx.reg.table(spec["name"], [c[0] for c in GANTT_COLS], first, last, keys)

    # 条件格式：逾期红、完成绿、计划橙；今天所在列浅黄
    G1 = get_column_letter(g0)
    GN = get_column_letter(g0 + len(slots) - 1)
    grid = "%s%d:%s%d" % (G1, first, GN, last)
    span = step - 1
    inbar = "%s$%d<=$F%d,%s$%d+%d>=$E%d" % (G1, hdr, first, G1, hdr, span, first)
    ws.conditional_formatting.add(grid, FormulaRule(
        formula=['AND($G%d<>"已完成",$F%d<TODAY(),%s)' % (first, first, inbar)], fill=fill(BRAND["red"])))
    ws.conditional_formatting.add(grid, FormulaRule(
        formula=['AND($G%d="已完成",%s)' % (first, inbar)], fill=fill(BRAND["teal"])))
    ws.conditional_formatting.add(grid, FormulaRule(formula=["AND(%s)" % inbar], fill=fill(BRAND["orange"])))
    ws.conditional_formatting.add("%s%d:%s%d" % (G1, hdr, GN, last), FormulaRule(
        formula=["AND(%s$%d<=TODAY(),%s$%d+%d>=TODAY())" % (G1, hdr, G1, hdr, span)], fill=fill(BRAND["yellow_light"])))
    # 状态列着色、进度数据条、预警着色
    ws.conditional_formatting.add("G%d:G%d" % (first, last), FormulaRule(
        formula=['G%d="已完成"' % first], font=font(9.5, True, BRAND["teal"])))
    ws.conditional_formatting.add("G%d:G%d" % (first, last), FormulaRule(
        formula=['G%d="进行中"' % first], font=font(9.5, True, BRAND["orange_dark"])))
    ws.conditional_formatting.add("H%d:H%d" % (first, last), DataBarRule(
        start_type="num", start_value=0, end_type="num", end_value=1, color="FFF2A65A", showValue=True))
    ws.conditional_formatting.add("I%d:I%d" % (first, last), FormulaRule(
        formula=['LEFT(I%d,2)="逾期"' % first], font=font(9, True, BRAND["red"]), fill=fill(BRAND["red_light"])))
    ws.conditional_formatting.add("I%d:I%d" % (first, last), FormulaRule(
        formula=['I%d="7 天内到期"' % first], font=font(9, True, "9C6500"), fill=fill(BRAND["yellow_light"])))
    dv = DataValidation(type="list", formula1='"%s"' % ",".join(statuses), allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("G%d:G%d" % (first, last + 20))
    dv2 = DataValidation(type="decimal", operator="between", formula1="0", formula2="1",
                         showErrorMessage=True, error="进度请填 0-100%")
    ws.add_data_validation(dv2)
    dv2.add("H%d:H%d" % (first, last + 20))
    ws.freeze_panes = ws.cell(row=first, column=3)
    ws.auto_filter.ref = "A%d:I%d" % (hdr, last)
    r = last + 2
    put(ws, r, 2, "图例：", font(9, True, BRAND["muted"]))
    for i, (lab, col) in enumerate((("计划", BRAND["orange"]), ("已完成", BRAND["teal"]),
                                    ("逾期", BRAND["red"]), ("本周", BRAND["yellow_light"]))):
        put(ws, r, 3 + i * 2, "", fl=fill(col), bd=box("DDDDDD"))
        put(ws, r, 4 + i * 2, lab, font(9, False, BRAND["ink_soft"]))
    if spec.get("source"):
        put(ws, r + 1, 2, "资料来源：" + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=True, title_rows="%d:%d" % (hdr - 1, hdr), brand=ctx.meta.get("brand", "富卫人寿"))


def _month(ws, row, month_start, c_end, st):
    (y, m), c0 = month_start
    if c_end > c0:
        ws.merge_cells(start_row=row, start_column=c0, end_row=row, end_column=c_end)
    put(ws, row, c0, "%d年%d月" % (y, m), font(8.5, True, st["title"]), al=align("center"),
        bd=border(bottom=side(st["accent"], "medium")))


# ---------------- 试算 ----------------
def calculator(ctx, ws, spec):
    st = ctx.st
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), 9, spec.get("note"))
    for col, w in zip("ABCDEFGHI", (2, 20, 16, 8, 4, 24, 18, 22, 2)):
        ws.column_dimensions[col].width = w
    top = r
    put(ws, r, 2, "① 录入参数", font(11, True, st["title"]), bd=border(bottom=side(st["accent"], "medium")))
    for c in (3, 4):
        ws.cell(row=r, column=c).border = border(bottom=side(st["accent"], "medium"))
    put(ws, r, 6, "② 试算结果", font(11, True, st["title"]), bd=border(bottom=side(st["accent"], "medium")))
    for c in (7, 8):
        ws.cell(row=r, column=c).border = border(bottom=side(st["accent"], "medium"))
    r += 1
    protect = spec.get("protect", True)
    for i, inp in enumerate(spec["inputs"]):
        rr = r + i
        ws.row_dimensions[rr].height = 26
        put(ws, rr, 2, inp["label"], font(10, True), al=align("left", "center"), bd=border(bottom=side()))
        cell = put(ws, rr, 3, inp.get("value"), font(11, True, BRAND["ink"], NUM_FONT if isinstance(inp.get("value"), (int, float)) else None),
                   fill(ROLE["input_bg"]), align("center"), box(ROLE["input_border"]), _fmt(inp.get("format")))
        cell.protection = Protection(locked=False)
        put(ws, rr, 4, inp.get("unit", ""), font(9, False, BRAND["muted"]), bd=border(bottom=side()))
        ctx.reg.cell("input", inp["key"], spec["name"], 3, rr)
        v = inp.get("validation") or {}
        dv = None
        if inp.get("options"):
            dv = DataValidation(type="list", formula1='"%s"' % ",".join(inp["options"]), allow_blank=False)
        elif v.get("type") in ("whole", "decimal"):
            dv = DataValidation(type=v["type"], operator="between", formula1=str(v["min"]), formula2=str(v["max"]),
                                showErrorMessage=True, errorTitle="超出范围",
                                error="请输入 %s 到 %s 之间的数值" % (v["min"], v["max"]))
        if dv:
            dv.showInputMessage = True
            dv.promptTitle = inp["label"]
            dv.prompt = inp.get("hint", "")
            ws.add_data_validation(dv)
            dv.add(cell.coordinate)
    for i, out in enumerate(spec["outputs"]):
        rr = r + i
        emph = out.get("emphasis", False)
        ws.row_dimensions[rr].height = max(ws.row_dimensions[rr].height or 26, 34 if emph else 26)
        put(ws, rr, 6, out["label"], font(10, True, st["title"] if emph else BRAND["ink"]),
            fill(st["tile_bg"]) if emph and st["tile_bg"] != BRAND["green"] else None, align("left", "center", indent=1),
            border(bottom=side()))
        f = out["formula"]
        if spec.get("iferror", True) and f.startswith("="):
            f = '=IFERROR(%s,"请检查录入")' % f[1:]
        write_value(ctx, ws, rr, 7, f, _fmt(out.get("format")),
                    f=font(16 if emph else 11, True, BRAND["orange_dark"] if emph else ROLE["formula_fg"], NUM_FONT),
                    fl=fill(st["tile_bg"]) if emph and st["tile_bg"] != BRAND["green"] else None,
                    al=align("right", "center"), bd=border(bottom=side()))
        put(ws, rr, 8, out.get("comment", ""), font(9, False, BRAND["muted"]), al=align("left", "center", True),
            bd=border(bottom=side()))
        ctx.reg.cell("output", out["key"], spec["name"], 7, rr)
    r = r + max(len(spec["inputs"]), len(spec["outputs"])) + 2

    for lk in spec.get("lookups", []):
        put(ws, r, 2, lk["title"], font(11, True, st["title"]))
        r += 1
        r0 = r
        for ci, h in enumerate(lk["columns"], 2):
            put(ws, r, ci, h, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center"))
        for ri, row in enumerate(lk["rows"], 1):
            for ci, v in enumerate(row, 2):
                put(ws, r + ri, ci, v, font(9.5, ci == 2, BRAND["ink"], NUM_FONT), al=align("center"),
                    bd=border(bottom=side()), fmt=_fmt(lk.get("format")) if ci > 2 else None)
        r1 = r + len(lk["rows"])
        ctx.reg.lookups[lk["name"]] = {"sheet": spec["name"], "r0": r0, "r1": r1, "c0": 2,
                                       "c1": 1 + len(lk["columns"])}
        r = r1 + 1
        if lk.get("note"):
            put(ws, r, 2, "注：" + lk["note"], font(9, False, BRAND["muted"]))
            r += 1
        r += 1
    for note in spec.get("notes", []):
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        put(ws, r, 2, note, font(9, False, BRAND["muted"]), al=align("left", "top", True))
        ws.row_dimensions[r].height = max(16, 14 * (1 + int(text_width(note) / 110)))
        r += 1
    if protect:
        ws.protection.sheet = True          # 只锁公式格，录入格已解锁；无密码，审阅 → 撤销保护即可修改
        ws.protection.formatCells = False
    ws.sheet_properties.tabColor = BRAND["orange"]
    print_setup(ws, landscape=False, brand=ctx.meta.get("brand", "富卫人寿"))


# ---------------- 清单 ----------------
def checklist(ctx, ws, spec):
    st = ctx.st
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), 6, spec.get("note"))
    for col, w in zip("ABCDEF", (6, 34, 9, 40, 14, 2)):
        ws.column_dimensions[col].width = w
    prog = r
    r += 2
    hdr = r
    for ci, h in enumerate(["完成", "材料 / 事项", "要求", "说明", "提供方"], 1):
        put(ws, hdr, ci, h, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center"))
    r += 1
    first = r
    for g in spec["groups"]:
        if g.get("name"):
            for c in range(1, 6):
                ws.cell(row=r, column=c).fill = fill(st["group_bg"])
            put(ws, r, 1, "▍" + g["name"], font(10, True, st["group_fg"]), fill(st["group_bg"]))
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
            r += 1
        for it in g["items"]:
            it = {"text": it} if isinstance(it, str) else it
            ws.row_dimensions[r].height = max(22, 15 * (1 + int(text_width(it.get("note", "")) / 76)))
            put(ws, r, 1, "☑" if it.get("done") else "☐", font(13, False, BRAND["orange"]), fill(ROLE["input_bg"]),
                align("center"), border(bottom=side()))
            put(ws, r, 2, it["text"], font(10, True), al=align("left", "center", True), bd=border(bottom=side()))
            req = "必备" if it.get("required", True) else "如适用"
            put(ws, r, 3, req, font(9, True, BRAND["orange_dark"] if req == "必备" else BRAND["muted"]),
                al=align("center"), bd=border(bottom=side()))
            put(ws, r, 4, it.get("note", ""), font(9.5, False, BRAND["ink_soft"]), al=align("left", "center", True),
                bd=border(bottom=side()))
            put(ws, r, 5, it.get("who", ""), font(9.5, False, BRAND["ink_soft"]), al=align("center"),
                bd=border(bottom=side()))
            r += 1
    last = r - 1
    rng = "A%d:A%d" % (first, last)
    dv = DataValidation(type="list", formula1='"☐,☑"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(rng)
    ws.conditional_formatting.add("B%d:E%d" % (first, last), FormulaRule(
        formula=['$A%d="☑"' % first], font=font(10, False, BRAND["muted"]), fill=fill(BRAND["teal_light"])))
    ws.conditional_formatting.add("B%d:E%d" % (first, last), FormulaRule(
        formula=['AND($A%d="☐",$C%d="必备")' % (first, first)], font=font(10, True, BRAND["ink"])))
    # 进度
    put(ws, prog, 1, "准备进度", font(10, True, st["title"]))
    ws.merge_cells(start_row=prog, start_column=1, end_row=prog, end_column=2)
    total = 'COUNTIF(A%d:A%d,"☐")+COUNTIF(A%d:A%d,"☑")' % (first, last, first, last)
    c = put(ws, prog, 3, '=IFERROR(COUNTIF(A%d:A%d,"☑")/(%s),0)' % (first, last, total),
            font(12, True, BRAND["orange_dark"], NUM_FONT), al=align("center"), fmt="0%")
    put(ws, prog, 4, '="已完成 "&COUNTIF(A%d:A%d,"☑")&" / "&(%s)&" 项；必备项还差 "&COUNTIFS(A%d:A%d,"☐",C%d:C%d,"必备")&" 项"'
        % (first, last, total, first, last, first, last), font(9.5, False, BRAND["ink_soft"]))
    ws.conditional_formatting.add(c.coordinate, DataBarRule(start_type="num", start_value=0, end_type="num",
                                                            end_value=1, color="FFF2A65A", showValue=True))
    ws.freeze_panes = ws.cell(row=first, column=1)
    r += 1
    for note in spec.get("notes", []):
        put(ws, r, 2, "注：" + note, font(9, False, BRAND["muted"]))
        r += 1
    if spec.get("source"):
        put(ws, r, 2, "资料来源：" + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=False, title_rows="%d:%d" % (hdr, hdr), brand=ctx.meta.get("brand", "富卫人寿"))


REGISTRY = {"dashboard": dashboard, "gantt": gantt, "calculator": calculator, "checklist": checklist}
