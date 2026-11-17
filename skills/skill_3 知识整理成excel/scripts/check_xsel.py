#!/usr/bin/env python3
"""检查生成的 Excel：行列数、空单元格、【待补充】占位。

用法:
    python check_xlsx.py output.xlsx
退出码: 0 = 无空单元格；1 = 有空单元格需要确认

依赖: openpyxl
"""
import json
import sys

try:
    from openpyxl import load_workbook
except ModuleNotFoundError:
    sys.exit("缺少依赖 openpyxl，请先执行: pip install openpyxl")


def find_header(ws):
    """表头行：第一行所有非空单元格都加粗且至少 2 列的行。"""
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 10)):
        cells = [c for c in row if c.value not in (None, "")]
        if len(cells) >= 2 and all(c.font and c.font.bold for c in cells):
            return row[0].row, len(cells)
    return None, 0


def check(path):
    wb = load_workbook(path)
    result, has_empty = [], False
    for ws in wb.worksheets:
        header, ncol = find_header(ws)
        if header is None:
            result.append({"sheet": ws.title, "error": "没有找到表头"})
            continue
        headers = [ws.cell(row=header, column=c).value for c in range(1, ncol + 1)]
        empty, todo, nrow = [], [], 0
        for r in range(header + 1, ws.max_row + 1):
            first = ws.cell(row=r, column=1).value
            if first is None and all(ws.cell(row=r, column=c).value is None for c in range(1, ncol + 1)):
                break  # 表格结束（后面是备注）
            nrow += 1
            label = first if first is not None else f"第{r}行"
            for c in range(1, ncol + 1):
                v = ws.cell(row=r, column=c).value
                if v is None or v == "":
                    empty.append(f"{label} / {headers[c - 1]}")
                elif isinstance(v, str) and "【待补充" in v:
                    todo.append(f"{label} / {headers[c - 1]}")
        has_empty |= bool(empty)
        result.append({"sheet": ws.title, "rows": nrow, "columns": headers,
                       "empty_cells": empty, "placeholders": todo})
    return result, has_empty


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    res, has_empty = check(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if has_empty:
        print("\n提示：有空单元格。确实不适用的请填“—”，漏填的请补充或填【待补充】。")
    sys.exit(1 if has_empty else 0)
