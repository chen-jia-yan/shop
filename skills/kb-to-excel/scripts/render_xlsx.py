# -*- coding: utf-8 -*-
"""
知识生成 Excel —— 渲染入口

用法：
  python render_xlsx.py <内容.json> <输出.xlsx> [--style blue|soft|orange] [--config 额外配置]
                        [--font-cn 字体] [--font-num 字体] [--font-mode first|installed] [--font-scale 1.1]

内容 JSON 的结构（详见 reference/sheet-types.md）：
  meta        标题、用途、来源、日期、kind、style
  params      参数（阈值等），写在“参数”表，公式里用 {param.键} 引用
  options     下拉选项，写在“参数”表；字段里写 options 也会自动收进来
  data        原始数据表（可多张）：fields 字段定义 + rows 原始记录，原样保留
  rules       提醒规则：条件命中时在数据表的“提醒标记”列和指定字段上标色
  views       视图：list 列表（筛选 + 排序）/ board 看板（按字段分列），只引用数据表
  dashboard   仪表盘：指标卡、智能洞察、趋势、热力、分组进度、分布、异常清单
  sheets      其他工作表（沿用）：matrix 对比矩阵 / gantt 甘特 / calculator 试算 / checklist 清单 / notes 口径说明 / table 简单表

工作表顺序：使用说明 →（仪表盘，meta.dashboard_first 时）→ 数据 → 字段说明 → 视图 → 仪表盘 → 其他 → 提醒规则 → 参数

不丢数据的校验（任何一项不通过都不生成文件）：
  - 行里出现了字段定义之外的键（会被丢掉）→ 报错，列出键名
  - 列表写法的行，值的个数多于非公式字段数 → 报错
  - 主键为空或重复 → 报错
  - 写了 expect_rows（检索到的条数）但与 rows 条数不一致 → 报错

退出码：0 成功；2 内容校验不通过；3 文件已生成，但有公式引用或图表无法解析（会逐条列出）。
"""
import argparse
import json
import os
import re
import sys

from openpyxl import Workbook
from openpyxl.workbook.properties import CalcProperties

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, add_cli_args, configure    # noqa: E402

import sheets_data                       # noqa: E402
import sheets_tools                      # noqa: E402
import xl_dash                           # noqa: E402
import xl_data                           # noqa: E402
import xl_meta                           # noqa: E402
import xl_views                          # noqa: E402
from xl_charts import place_charts       # noqa: E402
from xl_helpers import Registry          # noqa: E402
from xl_theme import L, R, default_style, get_style   # noqa: E402

LEGACY = dict(sheets_data.REGISTRY)
LEGACY.update(sheets_tools.REGISTRY)
RETIRED = {"cover": "已停用：第一张“使用说明”会自动生成（表格样式，不做封面）",
           "dashboard": "已改为顶层 dashboard（公式驱动的仪表盘），见 reference/sheet-types.md"}
REQUIRED = {"table": ["columns"], "matrix": ["objects", "groups"], "notes": ["sections"],
            "gantt": ["tasks"], "calculator": ["inputs", "outputs"], "checklist": ["groups"]}
TYPES = ("text", "longtext", "number", "money", "percent", "date", "select", "multi", "person", "link",
         "formula", "ai", "bool")
BAD_NAME = re.compile(r"[\[\]:*?/\\]")


class Ctx(object):
    def __init__(self, st, meta, data):
        self.st, self.meta, self.data = st, meta, data
        self.sheets = data.get("sheets") or []
        self.reg = Registry()
        self.charts = []
        self.tables, self.options, self.params, self.rules = {}, {}, [], []


# ---------------- 校验 ----------------
def _check_name(name, names, where, errs):
    if not name:
        errs.append("%s：缺少 name" % where)
    elif len(name) > 31 or BAD_NAME.search(name):
        errs.append("%s：工作表名“%s”不能超过 31 个字符，且不能含 [ ] : * ? / \\" % (where, name))
    elif name in names:
        errs.append("%s：工作表名“%s”重复" % (where, name))
    names.add(name)


def validate(data):
    errs, names = [], {L("readme_sheet"), L("fields_sheet"), L("rules_sheet"), L("params_sheet")}
    meta = data.get("meta") or {}
    if not meta.get("title"):
        errs.append("meta.title 缺失")
    tables = data.get("data") or []
    if not tables and not data.get("sheets"):
        errs.append("data 和 sheets 都为空")
    for ti, t in enumerate(tables, 1):
        where = "data 第 %d 张（%s）" % (ti, t.get("name"))
        _check_name(t.get("name"), names, where, errs)
        fields = t.get("fields") or []
        if not fields:
            errs.append("%s：缺少 fields" % where)
            continue
        fnames = [f.get("name") for f in fields]
        dup = {x for x in fnames if fnames.count(x) > 1}
        if dup:
            errs.append("%s：字段重名：%s" % (where, "、".join(dup)))
        for f in fields:
            if f.get("type", "text") not in TYPES:
                errs.append("%s：字段“%s”类型 %r 不支持，可用：%s" % (where, f.get("name"), f.get("type"), "、".join(TYPES)))
            if f.get("type") == "formula" and not f.get("formula"):
                errs.append("%s：公式字段“%s”缺少 formula" % (where, f.get("name")))
            if f.get("options_ref") and f["options_ref"] not in (data.get("options") or {}):
                errs.append("%s：字段“%s”的 options_ref “%s”不在 options 中" % (where, f.get("name"), f["options_ref"]))
        key = t.get("key") or fnames[0]
        if key not in fnames:
            errs.append("%s：主键字段“%s”不存在" % (where, key))
        plain = [f["name"] for f in fields if f.get("type") != "formula"]
        seen, rows = {}, t.get("rows") or []
        for ri, row in enumerate(rows, 1):
            if isinstance(row, dict):
                extra = [k for k in row if k not in fnames]
                if extra:
                    errs.append("%s 第 %d 行：字段定义中没有“%s”，这些值会丢失——请在 fields 中补上" %
                                (where, ri, "、".join(extra)))
                kv = row.get(key)
            else:
                if len(row) > len(plain):
                    errs.append("%s 第 %d 行：有 %d 个值，多于 %d 个非公式字段，多出的值会丢失" % (where, ri, len(row), len(plain)))
                kv = row[plain.index(key)] if key in plain and plain.index(key) < len(row) else None
            if kv in (None, ""):
                errs.append("%s 第 %d 行：主键“%s”为空" % (where, ri, key))
            elif kv in seen:
                errs.append("%s 第 %d 行：主键“%s”与第 %d 行重复" % (where, ri, kv, seen[kv]))
            else:
                seen[kv] = ri
        if t.get("expect_rows") is not None and t["expect_rows"] != len(rows):
            errs.append("%s：检索到 %d 条（expect_rows），实际写入 %d 条，原始数据不完整" % (where, t["expect_rows"], len(rows)))
    tnames = {t.get("name") for t in tables}
    for i, ru in enumerate(data.get("rules") or [], 1):
        if not ru.get("name") or not ru.get("when"):
            errs.append("rules 第 %d 条：缺少 name 或 when" % i)
        if ru.get("level", "warn") not in ("bad", "warn", "info"):
            errs.append("rules 第 %d 条：level 只能是 bad / warn / info" % i)
        if ru.get("table") and ru["table"] not in tnames:
            errs.append("rules 第 %d 条：table “%s”不存在" % (i, ru["table"]))
    marks = [ru.get("mark") or ru.get("name") for ru in data.get("rules") or []]
    for a in marks:
        for b in marks:
            if a and b and a != b and a in b:
                errs.append("提醒规则的标记“%s”包含在“%s”里，统计命中数时会混淆，请改名" % (a, b))
    for i, v in enumerate(data.get("views") or [], 1):
        where = "views 第 %d 个（%s）" % (i, v.get("name"))
        _check_name(v.get("name"), names, where, errs)
        if v.get("from") not in tnames:
            errs.append("%s：from “%s”不是 data 中的表" % (where, v.get("from")))
        if v.get("type", "list") == "list" and not v.get("columns"):
            errs.append("%s：列表视图缺少 columns" % where)
        if v.get("type") == "board" and not v.get("group"):
            errs.append("%s：看板缺少 group" % where)
    d = data.get("dashboard")
    if d:
        _check_name(d.get("name"), names, "dashboard", errs)
        if d.get("from") not in tnames:
            errs.append("dashboard：from “%s”不是 data 中的表" % d.get("from"))
        lo, hi = R("kpi_range")
        if d.get("kpis") and not lo <= len(d["kpis"]) <= hi:
            errs.append("dashboard：指标卡建议 %d-%d 个" % (lo, hi))
    for i, s in enumerate(data.get("sheets") or [], 1):
        t = s.get("type")
        where = "sheets 第 %d 个（%s）" % (i, s.get("name") or t)
        if t in RETIRED:
            errs.append("%s：类型 %s %s" % (where, t, RETIRED[t]))
            continue
        if t not in LEGACY:
            errs.append("%s：未知类型 %r，可用：%s" % (where, t, "、".join(k for k in LEGACY if k not in RETIRED)))
            continue
        _check_name(s.get("name"), names, where, errs)
        for f in REQUIRED.get(t, []):
            if not s.get(f):
                errs.append("%s：缺少 %s" % (where, f))
    return errs


# ---------------- 渲染 ----------------
def render(data, out, style=None):
    meta = data["meta"]
    st = get_style(style or meta.get("style") or default_style(meta.get("kind")))
    ctx = Ctx(st, meta, data)
    views, d = data.get("views") or [], data.get("dashboard")
    xl_data.plan(ctx, data)
    xl_views.plan_views(ctx, views, xl_dash.plan_dash(ctx, d) if d else [])
    xl_data.finish_plan(ctx)

    order = []                                       # (工作表名, 类型键, 用途, 写入函数)
    dash = (d["name"], "dash", d.get("desc"), lambda ws: xl_dash.dashboard(ctx, ws, d)) if d else None
    if dash and meta.get("dashboard_first"):
        order.append(dash)
    for t in data.get("data") or []:
        order.append((t["name"], "data", t.get("desc") or t.get("title"),
                      (lambda name: lambda ws: xl_data.data_sheet(ctx, ws, name))(t["name"])))
    if ctx.tables:
        order.append((L("fields_sheet"), "fields", None, lambda ws: xl_meta.fields_sheet(ctx, ws)))
    for v in views:
        fn = xl_views.board_view if v.get("type") == "board" else xl_views.list_view
        order.append((v["name"], "board" if v.get("type") == "board" else "view", v.get("desc"),
                      (lambda fn, v: lambda ws: fn(ctx, ws, v))(fn, v)))
    if dash and not meta.get("dashboard_first"):
        order.append(dash)
    for s in data.get("sheets") or []:
        order.append((s["name"], "other", s.get("desc") or s.get("title"),
                      (lambda s: lambda ws: LEGACY[s["type"]](ctx, ws, s))(s)))
    if ctx.rules:
        order.append((L("rules_sheet"), "rules", None, lambda ws: xl_data.rules_sheet(ctx, ws)))
    wb = Workbook()
    wb.remove(wb.active)
    if ctx.params or ctx.options:
        order.append((L("params_sheet"), "params", None, lambda ws: xl_data.params_sheet(ctx, ws, wb)))
    with_readme = meta.get("readme", True)
    if with_readme:
        wb.create_sheet(L("readme_sheet"))
    for name, _, _, _ in order:
        wb.create_sheet(name)
    for name, _, _, fn in order:                     # 先写参数和规则无所谓：所有地址在规划阶段已确定
        fn(wb[name])
    if with_readme:
        xl_meta.readme(ctx, wb[L("readme_sheet")], [(n, k, desc) for n, k, desc, _ in order])
    errors = list(ctx.reg.resolve_all())
    errors += place_charts(wb, ctx.reg, ctx.charts)
    wb.active = 0
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    p = wb.properties
    p.title = meta["title"]
    p.subject = meta.get("purpose") or meta.get("subtitle", "")
    p.creator = meta.get("department") or CONF.org.get("author_default") or CONF.org_name(meta)
    p.keywords = ",".join(meta.get("tags", []))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wb.save(out)
    return ctx, st, errors, order


def main():
    ap = argparse.ArgumentParser(description="知识生成 Excel：把内容 JSON 渲染为 .xlsx（数据 · 视图 · 仪表盘 · 提醒规则）")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--style", help="色系，见 tap-config/themes.json 的 themes.excel.styles（默认蓝色系）")
    add_cli_args(ap)
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    configure("excel", a, data.get("meta"))
    if a.style and a.style not in CONF.theme_names():
        sys.exit("未知色系 %s，可选：%s" % (a.style, "、".join(CONF.theme_names())))
    errs = validate(data)
    if errs:
        print("内容校验未通过，共 %d 处（未生成文件）：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    try:
        ctx, st, errors, order = render(data, a.output, a.style)
    except KeyError as e:
        print("内容有误：%s" % (e.args[0] if e.args else e))
        sys.exit(2)
    print("已生成：%s（色系：%s）" % (a.output, st["name"]))
    for name, info in ctx.tables.items():
        n_raw = len([f for f in info["spec"]["fields"] if f.get("type") != "formula"])
        print("  数据表“%s”：%d 条记录 × %d 个原始字段（另有公式 / 提醒 / 辅助列 %d 列）" %
              (name, info["n"], n_raw, len(info["cols"]) - n_raw))
    print("  工作表 %d 个：%s" % (len(order) + 1, "、".join(n for n, _, _, _ in order)))
    print("  跨表公式 %d 处；图表 %d 个" % (len(ctx.reg.pending), len(ctx.charts)))
    s = json.dumps(data, ensure_ascii=False)
    todo, confirm = CONF.count_placeholders(s)
    if todo or confirm:
        print("待处理占位：待补充 %d 处，请确认 %d 处（单元格已高亮）" % (todo, confirm))
    if errors:
        print("以下公式引用或图表无法解析，文件已保存但这些位置需要修正：")
        for e in errors:
            print("  - " + e)
        sys.exit(3)


if __name__ == "__main__":
    main()
