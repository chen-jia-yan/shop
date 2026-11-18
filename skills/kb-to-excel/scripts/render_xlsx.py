# -*- coding: utf-8 -*-
"""
知识生成 Excel —— 渲染入口

用法：
  python render_xlsx.py <内容.json> <输出.xlsx> [--style classic|premium|minimal]

渲染顺序：校验 → 逐个写工作表 → 统一解析跨表公式引用 → 生成原生图表 → 保存。
打开文件时 Excel 会自动重算全部公式（已设置 fullCalcOnLoad）。

退出码：0 成功；2 内容校验不通过；3 公式引用或图表无法解析（会逐条列出）。
"""
import argparse
import json
import os
import re
import sys

from openpyxl import Workbook
from openpyxl.workbook.properties import CalcProperties

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sheets_data                       # noqa: E402
import sheets_tools                      # noqa: E402
from xl_charts import place_charts       # noqa: E402
from xl_helpers import Registry          # noqa: E402
from xl_theme import DEFAULT_STYLE_BY_KIND, get_style   # noqa: E402

REGISTRY = dict(sheets_data.REGISTRY)
REGISTRY.update(sheets_tools.REGISTRY)

REQUIRED = {
    "cover": [], "table": ["columns"], "matrix": ["objects", "groups"], "notes": ["sections"],
    "dashboard": [], "gantt": ["tasks"], "calculator": ["inputs", "outputs"], "checklist": ["groups"],
}
BAD_NAME = re.compile(r"[\[\]:*?/\\]")


class Ctx(object):
    def __init__(self, st, meta, sheets):
        self.st = st
        self.meta = meta
        self.sheets = sheets
        self.reg = Registry()
        self.charts = []


def validate(data):
    errs = []
    meta = data.get("meta") or {}
    if not meta.get("title"):
        errs.append("meta.title 缺失")
    sheets = data.get("sheets") or []
    if not sheets:
        errs.append("sheets 为空")
    names = set()
    for i, s in enumerate(sheets, 1):
        t = s.get("type")
        name = s.get("name", "")
        where = "第 %d 个工作表（%s）" % (i, name or t)
        if t not in REGISTRY:
            errs.append("%s：未知类型 %r，可用：%s" % (where, t, "、".join(REGISTRY)))
            continue
        if not name:
            errs.append("%s：缺少 name" % where)
        elif len(name) > 31 or BAD_NAME.search(name):
            errs.append("%s：工作表名不能超过 31 个字符，且不能含 [ ] : * ? / \\" % where)
        elif name in names:
            errs.append("%s：工作表名重复" % where)
        names.add(name)
        for f in REQUIRED[t]:
            if not s.get(f):
                errs.append("%s：缺少 %s" % (where, f))
        if t == "table":
            n = len(s.get("columns", []))
            for ri, row in enumerate(s.get("rows", []), 1):
                if len(row) > n:
                    errs.append("%s：第 %d 行有 %d 个值，多于 %d 列" % (where, ri, len(row), n))
        if t == "matrix":
            n = len(s.get("objects", []))
            for g in s.get("groups", []):
                for row in g.get("rows", []):
                    if len(row.get("values", [])) != n:
                        errs.append("%s：“%s”有 %d 个值，对比对象有 %d 个" % (where, row.get("label"), len(row.get("values", [])), n))
        if t == "dashboard" and not 2 <= len(s.get("kpis", [])) <= 6 and s.get("kpis"):
            errs.append("%s：指标卡建议 2-6 个" % where)
        if t == "calculator":
            keys = [x.get("key") for x in s.get("inputs", []) + s.get("outputs", [])]
            if len(keys) != len(set(keys)):
                errs.append("%s：inputs/outputs 的 key 有重复" % where)
    return errs


def render(data, out, style=None):
    meta = data["meta"]
    st = get_style(style or meta.get("style") or DEFAULT_STYLE_BY_KIND.get(meta.get("kind"), "classic"))
    sheets = data["sheets"]
    wb = Workbook()
    wb.remove(wb.active)
    ctx = Ctx(st, meta, sheets)
    for s in sheets:
        wb.create_sheet(s["name"])
    for s in sheets:
        REGISTRY[s["type"]](ctx, wb[s["name"]], s)
    errors = list(ctx.reg.resolve_all())
    errors += place_charts(wb, ctx.reg, ctx.charts)
    wb.active = 0
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    p = wb.properties
    p.title = meta["title"]
    p.subject = meta.get("subtitle", "")
    p.creator = meta.get("department", meta.get("brand", "富卫人寿"))
    p.keywords = ",".join(meta.get("tags", []))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wb.save(out)
    return ctx, st, errors


def main():
    ap = argparse.ArgumentParser(description="知识生成 Excel：把内容 JSON 渲染为富卫风格 .xlsx")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--style", choices=["classic", "premium", "minimal"])
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    errs = validate(data)
    if errs:
        print("内容校验未通过，共 %d 处：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    ctx, st, errors = render(data, a.output, a.style)
    s = json.dumps(data, ensure_ascii=False)
    print("已生成：%s（风格：%s）" % (a.output, st["name"]))
    print("工作表 %d 个；跨表公式 %d 处；图表 %d 个" % (len(data["sheets"]), len(ctx.reg.pending), len(ctx.charts)))
    todo, confirm = s.count("【待补充"), s.count("【请确认")
    if todo or confirm:
        print("待处理占位：【待补充】%d 处，【请确认】%d 处（单元格已标为橙黄色）" % (todo, confirm))
    if errors:
        print("以下公式引用或图表无法解析，文件已保存但这些位置需要修正：")
        for e in errors:
            print("  - " + e)
        sys.exit(3)


if __name__ == "__main__":
    main()
