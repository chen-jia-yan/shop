# -*- coding: utf-8 -*-
"""
读取已有工作簿 / 按主键回写 —— 让智能体基于真实数据做分析、生成报告，再把结果写回表里。

读取（把工作簿里的数据表还原成内容 JSON 的 data 部分，原样保留每一行每一列）：
  python read_xlsx.py read  <文件.xlsx> -o data.json [--sheet 工作表名 ...] [--header-row 行号]
    - 优先读 Excel 表格对象；没有表格对象时按 --header-row（默认自动找第一行非空表头）读取
    - 读到的是单元格的值；公式列同时记下公式文本（formula 字段），方便判断哪些列是算出来的
    - 字段类型按内容推断（日期 / 数字 / 百分比 / 单选 / 长文本 / 文本），推断结果只是建议，生成前请核对

回写（只改指定列，其余列一个字都不动）：
  python read_xlsx.py write <文件.xlsx> updates.json -o 新文件.xlsx
    updates.json：{"sheet": "数据", "key": "工单号",
                   "columns": ["智能摘要", "建议类别"],            # 允许回写的列（白名单）
                   "rows": [{"工单号": "TS2026-1023", "智能摘要": "…", "建议类别": "销售误导"}, …]}
    - 主键找不到、列不在白名单、目标格是公式 → 跳过并列出，不会新增行、不会覆盖公式
    - 输出另存为新文件，原文件不改；回写清单打印在屏幕上，可附在报告里
"""
import argparse
import datetime as dt
import json
import os
import sys

from openpyxl import load_workbook
from openpyxl.utils import range_boundaries


def _guess(values):
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return "text"
    if all(isinstance(v, (dt.date, dt.datetime)) for v in vals):
        return "date"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "percent" if all(0 <= v <= 1 for v in vals) and any(0 < v < 1 for v in vals) else "number"
    strs = [str(v) for v in vals]
    if max(len(s) for s in strs) > 40:
        return "longtext"
    distinct = set(strs)
    if len(vals) >= 6 and len(distinct) <= max(3, len(vals) // 4) and max(len(s) for s in distinct) <= 12:
        return "select"
    return "text"


def _plain(v):
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%Y-%m-%d")
    return v


def _blocks(ws, header_row=None):
    """返回 [(表名, 表头行, 首列, 末列, 末行)]。"""
    out = []
    for name, tab in ws.tables.items():
        ref = tab.ref if hasattr(tab, "ref") else tab
        c0, r0, c1, r1 = range_boundaries(ref)
        out.append((name, r0, c0, c1, r1))
    if out:
        return out
    hr = header_row
    if not hr:
        for r in range(1, min(ws.max_row, 30) + 1):
            vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            if sum(1 for v in vals if isinstance(v, str) and v.strip()) >= 2:
                hr = r
                break
    if not hr:
        return []
    c1 = max(c for c in range(1, ws.max_column + 1) if ws.cell(row=hr, column=c).value not in (None, ""))
    return [(ws.title, hr, 1, c1, ws.max_row)]


def _hidden_cols(ws):
    """隐藏列的列号集合（openpyxl 读入时相邻同设置的列会合并成一个 min-max 区间）。"""
    out = set()
    for cd in ws.column_dimensions.values():
        if cd.hidden and cd.min and cd.max:
            out.update(range(cd.min, cd.max + 1))
    return out


def _value(v):
    """回写值：YYYY-MM-DD 字符串转成日期，其余原样。"""
    if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
        try:
            return dt.datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            pass
    return v


def read(path, sheets=None, header_row=None):
    wb_v = load_workbook(path, data_only=True)
    wb_f = load_workbook(path)
    data = []
    no_cache = []
    for ws in wb_v.worksheets:
        if sheets and ws.title not in sheets:
            continue
        wf = wb_f[ws.title]
        blocks = _blocks(wf, header_row)
        for tname, hr, c0, c1, r1 in blocks:
            heads = [str(wf.cell(row=hr, column=c).value or "").strip() for c in range(c0, c1 + 1)]
            rows, formulas = [], {}
            for r in range(hr + 1, r1 + 1):
                vals = [ws.cell(row=r, column=c).value for c in range(c0, c1 + 1)]
                if all(v in (None, "") for v in vals):
                    continue
                for i, c in enumerate(range(c0, c1 + 1)):
                    fv = wf.cell(row=r, column=c).value
                    if isinstance(fv, str) and fv.startswith("=") and heads[i] not in formulas:
                        formulas[heads[i]] = fv
                rows.append({h: _plain(v) for h, v in zip(heads, vals) if h})
            fields, hidden = [], _hidden_cols(wf)
            for i, h in enumerate(heads):
                if not h:
                    continue
                f = {"name": h, "type": "formula" if h in formulas else _guess([ws.cell(row=r, column=c0 + i).value
                                                                              for r in range(hr + 1, r1 + 1)])}
                if h in formulas:
                    f["formula_seen"] = formulas[h]
                    if rows and all(x.get(h) in (None, "") for x in rows):
                        no_cache.append("%s·%s" % (ws.title, h))
                if c0 + i in hidden:
                    f["hidden"] = True                 # 视图 / 仪表盘用的辅助列；升级重建时去掉，会自动重新生成
                if f["type"] == "select":
                    f["options"] = sorted({str(x[h]) for x in rows if x.get(h) not in (None, "")})
                fields.append(f)
            data.append({"name": ws.title if len(blocks) == 1 else tname, "table_name": tname, "header_row": hr,
                         "source": os.path.basename(path), "expect_rows": len(rows), "fields": fields, "rows": rows})
    out = {"meta": {"title": os.path.splitext(os.path.basename(path))[0], "source": os.path.basename(path)}, "data": data}
    if no_cache:
        out["_warning"] = ("以下公式列没有计算结果（文件未在 Excel 中打开保存过，openpyxl 不会计算公式）："
                           + "、".join(no_cache) + "。请先在 Excel 中打开并保存，或用 review_xlsx.py --recalc 生成的副本。")
    return out


def write(path, upd, out):
    wb = load_workbook(path)
    ws = wb[upd["sheet"]]
    blocks = _blocks(ws, upd.get("header_row"))
    if not blocks:
        sys.exit("工作表“%s”中找不到表头" % upd["sheet"])
    _, hr, c0, c1, r1 = blocks[0]
    heads = {str(ws.cell(row=hr, column=c).value or "").strip(): c for c in range(c0, c1 + 1)}
    key = upd["key"]
    if key not in heads:
        sys.exit("主键列“%s”不存在" % key)
    allow = set(upd["columns"])
    bad = [c for c in allow if c not in heads]
    if bad:
        sys.exit("回写列不存在：%s" % "、".join(bad))
    index = {str(ws.cell(row=r, column=heads[key]).value): r for r in range(hr + 1, r1 + 1)
             if ws.cell(row=r, column=heads[key]).value not in (None, "")}
    done, skipped = 0, []
    for item in upd["rows"]:
        k = str(item.get(key))
        if k not in index:
            skipped.append("主键 %s 不存在（不会新增行）" % k)
            continue
        for col, v in item.items():
            if col == key:
                continue
            if col not in allow:
                skipped.append("%s：列“%s”不在回写白名单" % (k, col))
                continue
            cell = ws.cell(row=index[k], column=heads[col])
            if isinstance(cell.value, str) and cell.value.startswith("="):
                skipped.append("%s：列“%s”是公式，不覆盖" % (k, col))
                continue
            cell.value = _value(v)
            if isinstance(cell.value, dt.datetime) and not cell.number_format.startswith("yy"):
                cell.number_format = "yyyy-mm-dd"
            done += 1
    wb.save(out)
    print("已回写 %d 个单元格 → %s" % (done, out))
    for s in skipped:
        print("  跳过：" + s)


def main():
    ap = argparse.ArgumentParser(description="读取工作簿数据 / 按主键回写指定列")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read")
    r.add_argument("xlsx")
    r.add_argument("-o", "--output", required=True)
    r.add_argument("--sheet", action="append")
    r.add_argument("--header-row", type=int)
    w = sub.add_parser("write")
    w.add_argument("xlsx")
    w.add_argument("updates")
    w.add_argument("-o", "--output", required=True)
    a = ap.parse_args()
    if a.cmd == "read":
        data = read(a.xlsx, a.sheet, a.header_row)
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        for t in data["data"]:
            print("“%s”：%d 条 × %d 个字段（公式列 %d 个）" % (t["name"], len(t["rows"]), len(t["fields"]),
                                                    sum(1 for f in t["fields"] if f["type"] == "formula")))
        print("已写入：%s（字段类型为推断结果，请核对）" % a.output)
        if data.get("_warning"):
            print("注意：" + data["_warning"])
    else:
        if os.path.abspath(a.output) == os.path.abspath(a.xlsx):
            sys.exit("请另存为新文件，不要覆盖原文件")
        with open(a.updates, encoding="utf-8") as f:
            write(a.xlsx, json.load(f), a.output)


if __name__ == "__main__":
    main()
