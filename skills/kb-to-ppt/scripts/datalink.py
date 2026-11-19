# -*- coding: utf-8 -*-
"""
与 Excel 数据联动：内容页写 data_from，图表、进度条、方块地图、瀑布图、表格的数据直接从工作簿读取，
口径与 Excel 一致，并自动写入“数据来源”脚注。

  "data_from": {"file": "经营看板.xlsx",        # 相对内容 JSON 所在目录；也可以是 Excel 的内容 JSON（.json）
                "table": "机构明细",            # 工作表名或 Excel 表格对象名
                "categories": "机构", "series": ["达成率"],     # 图表 / 进度条 / 地图 / 瀑布图
                "columns": ["机构", "新单保费", "达成率"],       # 表格
                "where": {"状态": ["关注", "预警"]}, "sort": "达成率", "desc": true, "top": 8,
                "number_format": "0.0%"}

.xlsx 读取的是单元格的计算结果：用脚本刚生成、还没在 Excel 里打开保存过的文件，公式列没有值，会提示先打开保存一次。
"""
import json
import os

from ppt_base import fmt_num


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v or "").replace(",", "").strip()
    pct = s.endswith("%")
    try:
        f = float(s.rstrip("%"))
        return f / 100 if pct else f
    except ValueError:
        return None


def _load_json(path, name):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tables = data.get("data") or []
    t = next((x for x in tables if x.get("name") == name), tables[0] if tables and not name else None)
    if t is None:
        raise ValueError("%s 中没有数据表“%s”" % (os.path.basename(path), name))
    plain = [f["name"] for f in t["fields"] if f.get("type") != "formula"]
    formula = {f["name"] for f in t["fields"] if f.get("type") == "formula"}
    rows = []
    for r in t.get("rows") or []:
        rows.append(r if isinstance(r, dict) else {k: (r[i] if i < len(r) else None) for i, k in enumerate(plain)})
    return rows, plain, formula, t["name"]


def _load_xlsx(path, name, header_row=None):
    from openpyxl import load_workbook
    from openpyxl.utils import range_boundaries
    wb_v = load_workbook(path, data_only=True)
    wb_f = load_workbook(path)
    ws_name, ref = None, None
    if name in wb_v.sheetnames:
        ws_name = name
        tabs = list(wb_f[name].tables.values())
        if tabs:
            ref = tabs[0].ref if hasattr(tabs[0], "ref") else tabs[0]
    else:
        for ws in wb_f.worksheets:
            for tn, tab in ws.tables.items():
                if tn == name or getattr(tab, "displayName", None) == name:
                    ws_name, ref = ws.title, (tab.ref if hasattr(tab, "ref") else tab)
    if ws_name is None:
        ws_name = wb_v.sheetnames[0] if not name else None
    if ws_name is None:
        raise ValueError("%s 中没有工作表或表格“%s”" % (os.path.basename(path), name))
    wv, wf = wb_v[ws_name], wb_f[ws_name]
    if ref:
        c0, r0, c1, r1 = range_boundaries(ref)
    else:
        r0 = header_row or next((r for r in range(1, min(wv.max_row, 30) + 1)
                                 if sum(1 for c in range(1, wv.max_column + 1)
                                        if isinstance(wv.cell(row=r, column=c).value, str)) >= 2), 1)
        c0, c1, r1 = 1, wv.max_column, wv.max_row
    heads = [str(wv.cell(row=r0, column=c).value or "").strip() for c in range(c0, c1 + 1)]
    rows, formula = [], set()
    for r in range(r0 + 1, r1 + 1):
        vals = [wv.cell(row=r, column=c).value for c in range(c0, c1 + 1)]
        if all(v in (None, "") for v in vals):
            continue
        for j, c in enumerate(range(c0, c1 + 1)):
            fv = wf.cell(row=r, column=c).value
            if isinstance(fv, str) and fv.startswith("="):
                formula.add(heads[j])
        rows.append(dict(zip(heads, vals)))
    return rows, heads, formula, ws_name


def _filter(rows, df):
    w = df.get("where") or {}
    for k, v in w.items():
        allow = v if isinstance(v, list) else [v]
        rows = [r for r in rows if r.get(k) in allow]
    if df.get("sort"):                             # 空值始终排在最后
        k = df["sort"]
        has = [r for r in rows if _num(r.get(k)) is not None]
        has.sort(key=lambda r: _num(r.get(k)), reverse=bool(df.get("desc")))
        rows = has + [r for r in rows if _num(r.get(k)) is None]
    if df.get("top"):
        rows = rows[:int(df["top"])]
    return rows


def resolve(slides, base_dir, layout_of):
    """把每个 data_from 换成具体数据；返回错误列表（不抛异常，交给校验统一报告）。"""
    errs = []
    for i, s in enumerate(slides, 1):
        df = s.get("data_from")
        if not df:
            continue
        where = "第 %d 页（%s）" % (i, s.get("title", ""))
        path = df["file"] if os.path.isabs(df["file"]) else os.path.join(base_dir, df["file"])
        try:
            if path.lower().endswith(".json"):
                rows, heads, formula, tname = _load_json(path, df.get("table"))
            else:
                rows, heads, formula, tname = _load_xlsx(path, df.get("table"), df.get("header_row"))
        except (OSError, ValueError, KeyError) as e:
            errs.append("%s：读取 %s 失败：%s" % (where, df["file"], e))
            continue
        need = [df.get("categories")] + list(df.get("series") or []) + list(df.get("columns") or [])
        miss = [c for c in need if c and c not in heads and c not in formula]
        if miss:
            errs.append("%s：%s 的“%s”中没有字段：%s" % (where, df["file"], tname, "、".join(miss)))
            continue
        rows = _filter(rows, df)
        empty = [c for c in need if c and c in formula and rows and all(r.get(c) in (None, "") for r in rows)]
        if empty:
            how = ("内容 JSON 里没有公式列的计算结果，请改用在 Excel 中打开并保存过的 .xlsx" if path.lower().endswith(".json")
                   else "请先在 Excel 中打开并保存 %s 一次（脚本生成的文件还没有计算结果）" % df["file"])
            errs.append("%s：公式列“%s”没有值。%s" % (where, "、".join(empty), how))
            continue
        d = s.setdefault("data", {})
        nf = df.get("number_format") or d.get("number_format")
        lay = layout_of(s) if s.get("layout") not in (None, "auto") else df.get("as", "chart")
        cat, ser = df.get("categories"), list(df.get("series") or [])
        if lay == "table":
            cols = df.get("columns") or heads
            fm = df.get("formats") or {}
            d["columns"] = cols
            d["rows"] = [[_cell(r.get(c), fm.get(c)) for c in cols] for r in rows]
        elif lay in ("bars", "tilemap", "waterfall"):
            items = []
            for r in rows:
                v = _num(r.get(ser[0]))
                if v is None:
                    continue
                it = {"label": str(r.get(cat)), "value": v, "display": fmt_num(v, nf)}
                if lay == "bars" and df.get("target") is not None:
                    it["target"] = df["target"]
                items.append(it)
            d["items"] = items
        else:
            d["categories"] = [str(r.get(cat)) for r in rows]
            d["series"] = [{"name": sname, "values": [(_num(r.get(sname)) or 0.0) for r in rows]} for sname in ser]
            if nf:
                d["number_format"] = nf
            s.setdefault("layout", "chart")
        if not s.get("source") and not d.get("source"):
            d["source"] = "%s · %s" % (os.path.basename(df["file"]), tname)
    return errs


def _cell(v, nf=None):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return fmt_num(v, nf)
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return "" if v is None else str(v)
