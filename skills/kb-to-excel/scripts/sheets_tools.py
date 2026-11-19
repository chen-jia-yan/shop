# -*- coding: utf-8 -*-
"""
工具类工作表：dashboard 看板 / gantt 甘特跟踪 / calculator 试算 / checklist 清单。
字段说明见 reference/sheet-types.md。
颜色、字体、状态名称、预警天数、表头与提示文字均取自 tap-config，公式里的状态值也随配置变化。
"""
import datetime as dt

from openpyxl.formatting.rule import CellIsRule, DataBarRule, FormulaRule
from openpyxl.styles import Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from sheets_data import write_value
from xl_helpers import align, border, box, fill, font, print_setup, put, side, text_width, title_block
from xl_theme import BRAND, FONTS, FORMATS, ROLE, G, L, R


def _date(v):
    if isinstance(v, (dt.date, dt.datetime)) or v is None:
        return v
    return dt.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _fmt(name):
    return FORMATS.get(name, name) if name else None


def _q(s):
    """放进公式的字符串常量：双引号转义。"""
    return '"%s"' % str(s).replace('"', '""')


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
        ok_c = BRAND["on_dark_good"] if st["dark_tiles"] else BRAND["teal"]
        bad_c = BRAND["on_dark_bad"] if st["dark_tiles"] else BRAND["red"]
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
            ws.merge_cells(start_row=r + 1, start_column=c0, end_row=r + 1, end_column=c1)
            put(ws, r + 1, c0, k["label"] + (("（%s）" % k["unit"]) if k.get("unit") else ""),
                font(9.5, False, st["tile_label"]), al=align("left", "bottom", indent=1))
            ws.merge_cells(start_row=r + 2, start_column=c0, end_row=r + 2, end_column=c1)
            write_value(ctx, ws, r + 2, c0, k["value"], _fmt(k.get("format", "int")),
                        f=font(24, True, st["tile_value"], FONTS["num"]), al=align("left", "center", indent=1))
            ws.merge_cells(start_row=r + 3, start_column=c0, end_row=r + 3, end_column=c1)
            if k.get("delta") is not None:
                dc = write_value(ctx, ws, r + 3, c0, k["delta"], _fmt(k.get("delta_format", "delta")),
                                 f=font(9.5, True, BRAND["muted"], FONTS["num"]), al=align("left", "top", indent=1))
                good_up = k.get("good", "up") == "up"
                ws.conditional_formatting.add(dc.coordinate, CellIsRule(
                    operator="greaterThan", formula=["0"], font=font(9.5, True, ok_c if good_up else bad_c)))
                ws.conditional_formatting.add(dc.coordinate, CellIsRule(
                    operator="lessThan", formula=["0"], font=font(9.5, True, bad_c if good_up else ok_c)))
            elif k.get("note"):
                put(ws, r + 3, c0, k["note"], font(9, False, st["tile_label"]), al=align("left", "top", indent=1))
        ws.row_dimensions[r + 1].height = 20
        ws.row_dimensions[r + 2].height = 38
        ws.row_dimensions[r + 3].height = 20
        r += 5

    if spec.get("insights"):
        put(ws, r, 2, spec.get("insights_title", L("conclusions")), font(11, True, st["title"]))
        r += 1
        for i, t in enumerate(spec["insights"], 1):
            put(ws, r, 2, i, font(10, True, BRAND["primary"], FONTS["num"]), al=align("center", "top"))
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=1 + grid)
            write_value(ctx, ws, r, 3, t, f=font(10), al=align("left", "top", True))
            ws.row_dimensions[r].height = max(18, 15 * (1 + int(text_width(t) / 120)))
            r += 1
        r += 1

    if spec.get("rank"):
        r = _rank(ctx, ws, spec["rank"], r)

    for i, ch in enumerate(spec.get("charts", [])):
        ch = dict(ch)
        ch.setdefault("anchor", "%s%d" % (get_column_letter(2 + (i % 2) * 6), r + (i // 2) * 17))
        ch.setdefault("width", 13.6)
        ch.setdefault("height", 7.8)
        ctx.charts.append((spec["name"], ch))
    ws.sheet_properties.tabColor = st["accent"]
    ws.sheet_view.zoomScale = 90
    print_setup(ws, landscape=True)


def _rank(ctx, ws, rk, r):
    """动态排名：按指定列取前 N，数据变了排名自动跟着变。"""
    st = ctx.st
    n = int(rk.get("top", 5))
    by = rk["by"]
    put(ws, r, 2, rk.get("title") or L("rank_title", by=by, n=n), font(11, True, st["title"]))
    r += 1
    show = rk.get("columns", [rk.get("key", "")])
    key_col = rk["key"]
    heads = [L("rank_no")] + show
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
        put(ws, rr, 2, k, font(10, True, BRAND["primary"] if k <= 3 else BRAND["ink_soft"], FONTS["num"]),
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
GANTT_WIDTHS = {"id": 7, "task": 30, "dept": 12, "owner": 9, "start": 11, "end": 11, "status": 9,
                "progress": 8, None: 13}


def gantt(ctx, ws, spec):
    st = ctx.st
    tasks = spec["tasks"]
    cols = L("gantt_cols")                          # [[表头, 字段], ...]，最后一列为预警
    status = dict(L("gantt_status"))
    status.update(spec.get("status_names") or {})   # 可按项目改状态叫法，如 {"done": "已关闭"}
    statuses = spec.get("statuses") or [status["todo"], status["doing"], status["done"]]
    done, doing = status["done"], status["doing"]
    soon = int(spec.get("soon_days", R("soon_days")))
    spare = R("spare_rows")
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
    ncols = len(cols) + len(slots)
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), min(ncols, 20), spec.get("note"))

    # 汇总条
    lab = L("gantt_stats")
    sum_row = r
    hdr = r + 3
    first = hdr + 1
    last = first + len(tasks) - 1
    S = "$G$%d:$G$%d" % (first, last)
    E = "$F$%d:$F$%d" % (first, last)
    stats = [(lab["total"], "=COUNTA($B$%d:$B$%d)" % (first, last), "int", False),
             (lab["done"], "=COUNTIF(%s,%s)" % (S, _q(done)), "int", False),
             (lab["doing"], "=COUNTIF(%s,%s)" % (S, _q(doing)), "int", False),
             (lab["overdue"], '=COUNTIFS(%s,"<>%s",%s,"<"&TODAY())' % (S, done.replace('"', '""'), E), "int", True),
             (lab["rate"], "=IFERROR(COUNTIF(%s,%s)/COUNTA($B$%d:$B$%d),0)" % (S, _q(done), first, last), "pct0", False)]
    for i, (label, f, fm, alarm) in enumerate(stats):
        c = 1 + i * 2                       # 每个指标占两列：A-B、C-D、E-F……
        put(ws, sum_row, c, label, font(9, False, st["tile_label"]), fill(st["tile_bg"]), align("left", "center", indent=1))
        ws.merge_cells(start_row=sum_row, start_column=c, end_row=sum_row, end_column=c + 1)
        put(ws, sum_row + 1, c, f, font(18, True, BRAND["red"] if alarm and not st["dark_tiles"] else
                                        (BRAND["on_dark_bad"] if alarm else st["tile_value"]), FONTS["num"]),
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
    for ci, (label, key) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(ci)].width = GANTT_WIDTHS.get(key, 10)
        put(ws, hdr, ci, label, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center", "center", True))
    g0 = len(cols) + 1
    month_start = None
    for i, d in enumerate(slots):
        c = g0 + i
        ws.column_dimensions[get_column_letter(c)].width = 5.2 if unit == "week" else 3.2
        put(ws, hdr, c, d, font(8, True, st["head_fg"]), fill(st["head_bg"]), align("center", "center"),
            fmt="m/d" if unit == "week" else "d")
        key = (d.year, d.month)
        if month_start is None or key != month_start[0]:
            if month_start:
                _month(ws, month_row, month_start, c - 1, st)
            month_start = (key, c)
    if month_start:
        _month(ws, month_row, month_start, g0 + len(slots) - 1, st)
    ws.row_dimensions[hdr].height = 26

    pre, suf = L("warn_overdue_prefix"), L("warn_overdue_suffix")
    soon_txt = L("warn_soon", n=soon)
    keys = {}
    for i, t in enumerate(tasks):
        rr = first + i
        ws.row_dimensions[rr].height = 22
        vals = [t.get("id", i + 1), t["task"], t.get("dept", ""), t.get("owner", ""), _date(t["start"]),
                _date(t["end"]), t.get("status", status["todo"]), t.get("progress", 0)]
        for ci, v in enumerate(vals, 1):
            fm = {5: FORMATS["date"], 6: FORMATS["date"], 8: FORMATS["pct0"]}.get(ci)
            put(ws, rr, ci, v, font(9.5, ci == 2, BRAND["ink"], FONTS["num"] if ci in (1, 5, 6, 8) else None),
                fill(ROLE["input_bg"]) if ci in (7, 8) else None,
                align("center" if ci in (1, 4, 5, 6, 7, 8) else "left", "center", ci == 2),
                border(bottom=side()), fm)
        warn = ('=IF($G{r}={done},{done_txt},IF($F{r}<TODAY(),{pre}&(TODAY()-$F{r})&{suf},'
                'IF($F{r}-TODAY()<={soon},{soon_txt},"")))').format(
            r=rr, done=_q(done), done_txt=_q(L("warn_done")), pre=_q(pre), suf=_q(suf), soon=soon,
            soon_txt=_q(soon_txt))
        put(ws, rr, 9, warn, font(9, True, ROLE["formula_fg"]), al=align("center"), bd=border(bottom=side()))
        for c in range(g0, g0 + len(slots)):
            ws.cell(row=rr, column=c).border = border(bottom=side(BRAND["grid_light"]), left=side(BRAND["grid_faint"]))
        keys[str(vals[0])] = rr
    ctx.reg.table(spec["name"], [c[0] for c in cols], first, last, keys)

    # 条件格式：逾期、完成、计划三种条形；今天所在列浅色
    G1 = get_column_letter(g0)
    GN = get_column_letter(g0 + len(slots) - 1)
    grid = "%s%d:%s%d" % (G1, first, GN, last)
    span = step - 1
    inbar = "%s$%d<=$F%d,%s$%d+%d>=$E%d" % (G1, hdr, first, G1, hdr, span, first)
    ws.conditional_formatting.add(grid, FormulaRule(
        formula=['AND($G%d<>%s,$F%d<TODAY(),%s)' % (first, _q(done), first, inbar)], fill=fill(BRAND["red"])))
    ws.conditional_formatting.add(grid, FormulaRule(
        formula=['AND($G%d=%s,%s)' % (first, _q(done), inbar)], fill=fill(BRAND["teal"])))
    ws.conditional_formatting.add(grid, FormulaRule(formula=["AND(%s)" % inbar], fill=fill(BRAND["primary"])))
    ws.conditional_formatting.add("%s%d:%s%d" % (G1, hdr, GN, last), FormulaRule(
        formula=["AND(%s$%d<=TODAY(),%s$%d+%d>=TODAY())" % (G1, hdr, G1, hdr, span)], fill=fill(BRAND["accent_light"])))
    # 状态列着色、进度数据条、预警着色
    ws.conditional_formatting.add("G%d:G%d" % (first, last), FormulaRule(
        formula=['G%d=%s' % (first, _q(done))], font=font(9.5, True, BRAND["teal"])))
    ws.conditional_formatting.add("G%d:G%d" % (first, last), FormulaRule(
        formula=['G%d=%s' % (first, _q(doing))], font=font(9.5, True, BRAND["primary_dark"])))
    ws.conditional_formatting.add("H%d:H%d" % (first, last), DataBarRule(
        start_type="num", start_value=0, end_type="num", end_value=1, color="FF" + ROLE["databar"], showValue=True))
    head = pre.strip()
    ws.conditional_formatting.add("I%d:I%d" % (first, last), FormulaRule(
        formula=['LEFT(I%d,%d)=%s' % (first, len(head), _q(head))], font=font(9, True, BRAND["red"]),
        fill=fill(BRAND["red_light"])))
    ws.conditional_formatting.add("I%d:I%d" % (first, last), FormulaRule(
        formula=['I%d=%s' % (first, _q(soon_txt))], font=font(9, True, BRAND["warn_text"]),
        fill=fill(BRAND["accent_light"])))
    dv = DataValidation(type="list", formula1='"%s"' % ",".join(statuses), allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("G%d:G%d" % (first, last + spare))
    dv2 = DataValidation(type="decimal", operator="between", formula1="0", formula2="1",
                         showErrorMessage=True, error=L("progress_err"))
    ws.add_data_validation(dv2)
    dv2.add("H%d:H%d" % (first, last + spare))
    ws.freeze_panes = ws.cell(row=first, column=3)
    ws.auto_filter.ref = "A%d:%s%d" % (hdr, get_column_letter(len(cols)), last)
    r = last + 2
    put(ws, r, 2, L("legend"), font(9, True, BRAND["muted"]))
    li = L("gantt_legend")
    for i, (k, col) in enumerate((("plan", BRAND["primary"]), ("done", BRAND["teal"]),
                                  ("overdue", BRAND["red"]), ("now", BRAND["accent_light"]))):
        put(ws, r, 3 + i * 2, "", fl=fill(col), bd=box(BRAND["legend_border"]))
        put(ws, r, 4 + i * 2, li[k], font(9, False, BRAND["ink_soft"]))
    if spec.get("source"):
        put(ws, r + 1, 2, L("source") + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=True, title_rows="%d:%d" % (hdr - 1, hdr))


def _month(ws, row, month_start, c_end, st):
    (y, m), c0 = month_start
    if c_end > c0:
        ws.merge_cells(start_row=row, start_column=c0, end_row=row, end_column=c_end)
    put(ws, row, c0, L("month", y=y, m=m), font(8.5, True, st["title"]), al=align("center"),
        bd=border(bottom=side(st["accent"], "medium")))


# ---------------- 试算 ----------------
def calculator(ctx, ws, spec):
    st = ctx.st
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), 9, spec.get("note"))
    for col, w in zip("ABCDEFGHI", (2, 20, 16, 8, 4, 24, 18, 22, 2)):
        ws.column_dimensions[col].width = w
    put(ws, r, 2, spec.get("inputs_title", L("calc_inputs")), font(11, True, st["title"]),
        bd=border(bottom=side(st["accent"], "medium")))
    for c in (3, 4):
        ws.cell(row=r, column=c).border = border(bottom=side(st["accent"], "medium"))
    put(ws, r, 6, spec.get("outputs_title", L("calc_outputs")), font(11, True, st["title"]),
        bd=border(bottom=side(st["accent"], "medium")))
    for c in (7, 8):
        ws.cell(row=r, column=c).border = border(bottom=side(st["accent"], "medium"))
    r += 1
    protect = spec.get("protect", True)
    soft_tile = fill(st["tile_bg"]) if not st["dark_tiles"] else None
    for i, inp in enumerate(spec["inputs"]):
        rr = r + i
        ws.row_dimensions[rr].height = 26
        put(ws, rr, 2, inp["label"], font(10, True), al=align("left", "center"), bd=border(bottom=side()))
        cell = put(ws, rr, 3, inp.get("value"), font(11, True, BRAND["ink"], FONTS["num"] if isinstance(inp.get("value"), (int, float)) else None),
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
                                showErrorMessage=True, errorTitle=L("range_title"),
                                error=L("range_msg", min=v["min"], max=v["max"]))
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
            soft_tile if emph else None, align("left", "center", indent=1), border(bottom=side()))
        f = out["formula"]
        if spec.get("iferror", True) and f.startswith("="):
            f = "=IFERROR(%s,%s)" % (f[1:], _q(spec.get("error_text", L("calc_err"))))
        write_value(ctx, ws, rr, 7, f, _fmt(out.get("format")),
                    f=font(16 if emph else 11, True, BRAND["primary_dark"] if emph else ROLE["formula_fg"], FONTS["num"]),
                    fl=soft_tile if emph else None, al=align("right", "center"), bd=border(bottom=side()))
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
                put(ws, r + ri, ci, v, font(9.5, ci == 2, BRAND["ink"], FONTS["num"]), al=align("center"),
                    bd=border(bottom=side()), fmt=_fmt(lk.get("format")) if ci > 2 else None)
        r1 = r + len(lk["rows"])
        ctx.reg.lookups[lk["name"]] = {"sheet": spec["name"], "r0": r0, "r1": r1, "c0": 2,
                                       "c1": 1 + len(lk["columns"])}
        r = r1 + 1
        if lk.get("note"):
            put(ws, r, 2, L("note_prefix") + lk["note"], font(9, False, BRAND["muted"]))
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
    ws.sheet_properties.tabColor = st["accent"]
    print_setup(ws, landscape=False)


# ---------------- 清单 ----------------
def checklist(ctx, ws, spec):
    st = ctx.st
    box_off, box_on = G("box"), G("box_done")
    req_txt, opt_txt = L("required"), L("optional")
    r = title_block(ws, st, spec.get("title", spec["name"]), spec.get("subtitle"), 6, spec.get("note"))
    for col, w in zip("ABCDEF", (6, 34, 9, 40, 14, 2)):
        ws.column_dimensions[col].width = w
    prog = r
    r += 2
    hdr = r
    for ci, h in enumerate(spec.get("columns") or L("check_cols"), 1):
        put(ws, hdr, ci, h, font(9.5, True, st["head_fg"]), fill(st["head_bg"]), align("center"))
    r += 1
    first = r
    for g in spec["groups"]:
        if g.get("name"):
            for c in range(1, 6):
                ws.cell(row=r, column=c).fill = fill(st["group_bg"])
            put(ws, r, 1, G("section_mark") + g["name"], font(10, True, st["group_fg"]), fill(st["group_bg"]))
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
            r += 1
        for it in g["items"]:
            it = {"text": it} if isinstance(it, str) else it
            ws.row_dimensions[r].height = max(22, 15 * (1 + int(text_width(it.get("note", "")) / 76)))
            put(ws, r, 1, box_on if it.get("done") else box_off, font(13, False, BRAND["primary"]), fill(ROLE["input_bg"]),
                align("center"), border(bottom=side()))
            put(ws, r, 2, it["text"], font(10, True), al=align("left", "center", True), bd=border(bottom=side()))
            req = req_txt if it.get("required", True) else opt_txt
            put(ws, r, 3, req, font(9, True, BRAND["primary_dark"] if req == req_txt else BRAND["muted"]),
                al=align("center"), bd=border(bottom=side()))
            put(ws, r, 4, it.get("note", ""), font(9.5, False, BRAND["ink_soft"]), al=align("left", "center", True),
                bd=border(bottom=side()))
            put(ws, r, 5, it.get("who", ""), font(9.5, False, BRAND["ink_soft"]), al=align("center"),
                bd=border(bottom=side()))
            r += 1
    last = r - 1
    rng = "A%d:A%d" % (first, last)
    dv = DataValidation(type="list", formula1='"%s,%s"' % (box_off, box_on), allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(rng)
    ws.conditional_formatting.add("B%d:E%d" % (first, last), FormulaRule(
        formula=['$A%d=%s' % (first, _q(box_on))], font=font(10, False, BRAND["muted"]), fill=fill(BRAND["teal_light"])))
    ws.conditional_formatting.add("B%d:E%d" % (first, last), FormulaRule(
        formula=['AND($A%d=%s,$C%d=%s)' % (first, _q(box_off), first, _q(req_txt))], font=font(10, True, BRAND["ink"])))
    # 进度
    put(ws, prog, 1, L("progress"), font(10, True, st["title"]))
    ws.merge_cells(start_row=prog, start_column=1, end_row=prog, end_column=2)
    total = "COUNTIF(A%d:A%d,%s)+COUNTIF(A%d:A%d,%s)" % (first, last, _q(box_off), first, last, _q(box_on))
    c = put(ws, prog, 3, "=IFERROR(COUNTIF(A%d:A%d,%s)/(%s),0)" % (first, last, _q(box_on), total),
            font(12, True, BRAND["primary_dark"], FONTS["num"]), al=align("center"), fmt=FORMATS["pct0"])
    p1, p2, p3, p4 = L("progress_parts")
    put(ws, prog, 4, "=%s&COUNTIF(A%d:A%d,%s)&%s&(%s)&%s&COUNTIFS(A%d:A%d,%s,C%d:C%d,%s)&%s"
        % (_q(p1), first, last, _q(box_on), _q(p2), total, _q(p3), first, last, _q(box_off), first, last,
           _q(req_txt), _q(p4)), font(9.5, False, BRAND["ink_soft"]))
    ws.conditional_formatting.add(c.coordinate, DataBarRule(start_type="num", start_value=0, end_type="num",
                                                            end_value=1, color="FF" + ROLE["databar"], showValue=True))
    ws.freeze_panes = ws.cell(row=first, column=1)
    r += 1
    for note in spec.get("notes", []):
        put(ws, r, 2, L("note_prefix") + note, font(9, False, BRAND["muted"]))
        r += 1
    if spec.get("source"):
        put(ws, r, 2, L("source") + spec["source"], font(9, False, BRAND["muted"], italic=True))
    ws.sheet_properties.tabColor = st["tab"]
    print_setup(ws, landscape=False, title_rows="%d:%d" % (hdr, hdr))


REGISTRY = {"dashboard": dashboard, "gantt": gantt, "calculator": calculator, "checklist": checklist}
