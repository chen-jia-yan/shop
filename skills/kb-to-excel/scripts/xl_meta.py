# -*- coding: utf-8 -*-
"""
说明类工作表：使用说明（第一张，表格样式，不做封面）、字段说明（每个字段的类型、必填、口径、来源、填写率）。
"""
from openpyxl.formatting.rule import DataBarRule
from openpyxl.utils import get_column_letter

from xl_data import _grid, _header, _sheet_title, level_style, readable
from xl_helpers import align, border, fill, font, put, side, sref
from xl_theme import BRAND, FONTS, FORMATS, ROLE, L


def readme(ctx, ws, sheets):
    """sheets: [(工作表名, 类型键, 用途)]"""
    st, meta = ctx.st, ctx.meta
    ws.sheet_view.showGridLines = False
    put(ws, 1, 1, L("readme_title", title=meta["title"]), font(15, True, st["title"]), al=align("left", "center"))
    ws.row_dimensions[1].height = 30
    r = 2
    for line in [meta.get("purpose") or meta.get("subtitle"),
                 "　·　".join(x for x in [meta.get("source") and L("source") + meta["source"], meta.get("date"),
                                          meta.get("department"), meta.get("confidentiality")] if x),
                 meta.get("disclaimer")]:
        if line:
            put(ws, r, 1, line, font(9.5, False, st["subtitle"]))
            r += 1
    r += 1
    # 分层说明
    _header(ws, st, r, [L("readme_cols")[0], L("readme_cols")[2]])
    for name, desc in L("readme_layers"):
        r += 1
        put(ws, r, 1, name, font(10, True), bd=_grid(st))
        put(ws, r, 2, desc, font(10, False, BRAND["ink_soft"]), al=align("left", "center", True), bd=_grid(st))
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    r += 2
    # 工作表目录（可点击跳转）
    _header(ws, st, r, L("readme_cols"))
    kinds = L("readme_kinds")
    for name, kind, desc in sheets:
        r += 1
        c = put(ws, r, 1, name, font(10, True, ROLE["link"], underline="single"), bd=_grid(st))
        c.hyperlink = "#'%s'!A1" % name.replace("'", "''")
        put(ws, r, 2, kinds.get(kind, kinds["other"]), font(10, False, BRAND["ink_soft"]), bd=_grid(st))
        put(ws, r, 3, desc or "", font(10, False, BRAND["ink_soft"]), al=align("left", "center", True), bd=_grid(st))
    r += 2
    # 单元格说明：每种颜色给一个样例格
    put(ws, r, 1, L("legend_title"), font(11, True, st["title"]))
    sample = {"input": (fill(ROLE["input_bg"]), font(10)), "formula": (None, font(10, False, ROLE["fx_fg"])),
              "ai": (None, font(10, False, ROLE["ai_fg"])), "todo": (fill(ROLE["todo_bg"]), font(10, True, ROLE["todo_fg"])),
              "bad": level_style("bad"), "warn": level_style("warn")}
    for kind, label, desc in L("legend_items"):
        r += 1
        fl, ft = sample.get(kind, (None, font(10)))
        put(ws, r, 1, label, ft, fl, align("center"), border(bottom=side(st["grid"]), top=side(st["grid"]),
                                                            left=side(st["grid"]), right=side(st["grid"])))
        put(ws, r, 2, desc, font(10, False, BRAND["ink_soft"]))
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 72
    ws.sheet_properties.tabColor = st["tab_other"]


def fields_sheet(ctx, ws):
    st = ctx.st
    _sheet_title(ws, st, L("fields_sheet"))
    tn = L("type_names")
    r = 2
    for tname, info in ctx.tables.items():
        if len(ctx.tables) > 1:
            put(ws, r, 1, tname, font(10.5, True, st["group_fg"]), fill(st["group_bg"]))
            for c in range(2, 8):
                ws.cell(row=r, column=c).fill = fill(st["group_bg"])
            r += 1
        _header(ws, st, r, L("fields_cols"))
        first = r + 1
        keyref = sref(info["tname"], info["key"])
        for name in info["cols"]:
            r += 1
            f = info["fields"].get(name)
            aux = next((a for a in info["aux"] if a["name"] == name), None)
            if aux:
                kind, req, opt = L("aux_kind"), "", ""
                desc = L("aux_desc")[aux.get("for", "view")].format(view=aux.get("view", ""))
                src = tn["formula"]
            elif f is None:                                  # 提醒标记
                kind, req, opt, desc, src = tn["formula"], "", L("rules_sheet"), L("rules_sheet"), tn["formula"]
            else:
                kind = tn.get(f.get("type", "text"), f.get("type"))
                req = L("yes_no")[0] if f.get("required") else ""
                opt = " / ".join(ctx.options.get(f.get("options_ref"), [])) if f.get("options_ref") else \
                    (readable(f["formula"]) if f.get("formula") else "")
                desc, src = f.get("desc", ""), f.get("src", "")
                if f.get("type") == "ai":
                    a = f.get("ai") or {}
                    desc = (desc + "｜" if desc else "") + L("ai_note", **{"from": a.get("from", "—"),
                                                                         "date": a.get("date") or ctx.meta.get("date") or "—"})
            data_field = f is not None and f.get("type") != "formula" and not aux
            rate = '=IFERROR(COUNTA(%s)/ROWS(%s),0)' % (sref(info["tname"], name), keyref) if data_field else "—"
            vals = [name, kind, req, opt, src, desc, rate]
            for c, v in enumerate(vals, 1):
                put(ws, r, c, v, font(10, c == 1, ROLE["aux_fg"] if aux else (ROLE["fx_fg"] if c == 7 else BRAND["ink"]),
                                      FONTS["mono"] if c == 4 and f is not None and f.get("formula") else
                                      (FONTS["num"] if c == 7 else None)),
                    fill(ROLE["aux_bg"]) if aux else None,
                    align("right" if c == 7 else ("center" if c == 3 else "left"), "center", c in (4, 6)),
                    _grid(st), FORMATS["pct0"] if c == 7 and data_field else None)
        ws.conditional_formatting.add("G%d:G%d" % (first, r), DataBarRule(
            start_type="num", start_value=0, end_type="num", end_value=1, color="FF" + st["accent_light"], showValue=True))
        lv_fill, lv_font = level_style("warn")
        from openpyxl.formatting.rule import FormulaRule
        ws.conditional_formatting.add("G%d:G%d" % (first, r), FormulaRule(       # 只提示必填字段的缺失
            formula=['AND($C%d="%s",ISNUMBER(G%d),G%d<1)' % (first, L("yes_no")[0], first, first)], fill=lv_fill, font=lv_font))
        r += 2
    for c, w in zip("ABCDEFG", (22, 10, 6, 44, 18, 44, 10)):
        ws.column_dimensions[c].width = w
    ws.freeze_panes = "B3"
    ws.sheet_properties.tabColor = st["tab_data"]
