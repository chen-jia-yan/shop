#!/usr/bin/env python3
"""根据 JSON 内容生成格式规范的 Excel 表格。

用法:
    python build_xlsx.py content.json output.xlsx

依赖: openpyxl  (pip install openpyxl)
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ModuleNotFoundError:
    sys.exit("缺少依赖 openpyxl，请先执行: pip install openpyxl")

FONT = "微软雅黑"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
STRIPE_FILL = PatternFill("solid", fgColor="F2F5FA")
TODO_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
PLACEHOLDER = "【待补充"
BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def display_width(text):
    """中文等全角字符按 2 个宽度计算。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def sheet_title(name, used):
    base = BAD_SHEET_CHARS.sub("_", str(name or "Sheet")).strip()[:31] or "Sheet"
    title, n = base, 2
    while title in used:
        suffix = f"_{n}"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(title)
    return title


def convert(value, col_type):
    """按列类型转换单元格值；转换失败时保留原文（如【待补充】）。"""
    if value is None or value == "":
        return None, None
    if isinstance(value, str) and value.startswith(PLACEHOLDER):
        return value, None
    if col_type == "number":
        try:
            num = float(str(value).replace(",", "").replace("，", ""))
            return (int(num), "#,##0") if num.is_integer() else (num, "#,##0.00")
        except ValueError:
            return value, None
    if col_type == "percent":
        try:
            s = str(value).strip()
            num = float(s[:-1]) / 100 if s.endswith("%") else float(s)
            return num, "0.0%"
        except ValueError:
            return value, None
    if col_type == "date":
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(str(value).strip(), fmt), "yyyy-mm-dd"
            except ValueError:
                continue
        return value, None
    return value, None


def build_sheet(ws, spec, title, subtitle):
    columns = spec.get("columns", [])
    rows = spec.get("rows", [])
    ncol = max(len(columns), max((len(r) for r in rows), default=0)) or 1
    while len(columns) < ncol:
        columns.append({"name": f"列{len(columns) + 1}", "type": "text"})

    r = 1
    ws.cell(row=r, column=1, value=title).font = Font(name=FONT, size=14, bold=True, color="1F3864")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    ws.row_dimensions[r].height = 26
    r += 1
    if subtitle:
        ws.cell(row=r, column=1, value=subtitle).font = Font(name=FONT, size=9, color="7F7F7F")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
        r += 1
    r += 1  # 空一行

    header_row = r
    widths = []
    for c, col in enumerate(columns, 1):
        cell = ws.cell(row=r, column=c, value=col.get("name", ""))
        cell.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        widths.append(display_width(col.get("name", "")))
    ws.row_dimensions[r].height = 22

    todo = 0
    for i, row in enumerate(rows):
        r += 1
        for c, col in enumerate(columns, 1):
            raw = row[c - 1] if c - 1 < len(row) else None
            value, fmt = convert(raw, col.get("type", "text"))
            cell = ws.cell(row=r, column=c, value=value)
            cell.font = Font(name=FONT, size=10)
            cell.border = BORDER
            is_num = isinstance(value, (int, float)) and not isinstance(value, bool)
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       horizontal="right" if is_num else "left")
            if fmt:
                cell.number_format = fmt
            if isinstance(value, str) and PLACEHOLDER in value:
                cell.fill = TODO_FILL
                todo += 1
            elif i % 2 == 1:
                cell.fill = STRIPE_FILL
            widths[c - 1] = max(widths[c - 1], display_width(raw if raw is not None else ""))
    last_data_row = r

    for c, col in enumerate(columns, 1):
        w = col.get("width") or min(max(widths[c - 1] + 2, 8), 50)
        ws.column_dimensions[get_column_letter(c)].width = w

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ncol)}{last_data_row}"

    notes = spec.get("notes") or []
    if notes:
        r += 2
        ws.cell(row=r, column=1, value="备注").font = Font(name=FONT, size=10, bold=True)
        for n in notes:
            r += 1
            cell = ws.cell(row=r, column=1, value=f"· {n}")
            cell.font = Font(name=FONT, size=9, color="595959")
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if ncol > 5 else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    return len(rows), ncol, todo


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    sheets = spec.get("sheets") or []
    if not sheets:
        sys.exit("内容中没有 sheets")

    wb = Workbook()
    wb.remove(wb.active)
    used, report = set(), []
    for s in sheets:
        name = sheet_title(s.get("name"), used)
        ws = wb.create_sheet(title=name)
        nrow, ncol, todo = build_sheet(ws, s, s.get("title") or spec.get("title", name), spec.get("subtitle"))
        report.append({"sheet": name, "rows": nrow, "columns": ncol, "placeholders": todo})

    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(json.dumps({"output": str(out), "sheets": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
