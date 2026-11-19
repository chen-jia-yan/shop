# -*- coding: utf-8 -*-
"""
知识生成 Excel —— 交付前质检

用法：
  python review_xlsx.py <文件.xlsx> [--content 内容.json] [--external] [--final] [--recalc] [--out 质检报告.md]

  --content   与内容 JSON 逐表核对：行数、字段、原文是否被改写、智能列是否标注；视图与仪表盘里是否有手填数字

  --external  对外文件（发给客户）：启用合规用语检查（词表见 tap-config/compliance.json），试算表须有免责提示
  --final     正式交付：占位符视为必须修改
  --recalc    用 LibreOffice 重算一遍，检查 #REF! #DIV/0! #N/A 等公式错误（需本机安装 LibreOffice）

检查项：公式引用是否解析完整、是否引用了不存在的工作表、公式错误值、占位符、合规用语、
每个工作表的标题/冻结窗格/筛选，以及图表数量。
退出码：0 通过；1 存在“必须修改”项。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, configure                 # noqa: E402
import tapcheck                                   # noqa: E402

from openpyxl import load_workbook                # noqa: E402


ERRORS = ("#REF!", "#DIV/0!", "#N/A", "#VALUE!", "#NAME?", "#NUM!", "#NULL!")
SHEET_REF = re.compile(r"'((?:[^']|'')+)'!")


def scan(path, external, final):
    wb = load_workbook(path)        # 保留公式文本
    must, should, info = [], [], []
    rv = CONF.rule("review")
    names = set(wb.sheetnames)
    n_formula = 0
    todo = []
    for ws in wb.worksheets:
        title = ws.cell(row=1, column=1).value
        if not title and ws.max_row > 1:
            should.append("工作表“%s”第 1 行没有标题" % ws.title)
        if ws.max_row > rv["freeze_rows"] and ws.freeze_panes is None:
            should.append("工作表“%s”有 %d 行但没有冻结表头" % (ws.title, ws.max_row))
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, str):
                    continue
                where = "%s!%s" % (ws.title, c.coordinate)
                if v.startswith("="):
                    n_formula += 1
                    if re.search(r"\{[^{}]+\}", v):
                        must.append("%s 公式里有未解析的引用：%s" % (where, v[:80]))
                    for ref in SHEET_REF.findall(v):
                        if ref.replace("''", "'") not in names:
                            must.append("%s 引用了不存在的工作表“%s”" % (where, ref))
                    if "/" in v and "IFERROR" not in v.upper() and "SUBTOTAL" not in v.upper():
                        should.append("%s 含除法但没有 IFERROR，分母为 0 时会显示 #DIV/0!" % where)
                    continue
                if tapcheck.has_placeholder(v):
                    todo.append(where)
                if external:
                    for cat, word, _, _ in tapcheck.banned_hits(v):
                        must.append("%s【%s】“%s”：%s" % (where, cat, word, v[:40]))
        info.append("“%s”：%d 行 × %d 列，下拉校验 %d 组，条件格式 %d 组"
                    % (ws.title, ws.max_row, ws.max_column, len(ws.data_validations.dataValidation),
                       len(ws.conditional_formatting)))
    # openpyxl 读取时不会加载图表，直接数压缩包里的图表文件
    with zipfile.ZipFile(path) as z:
        n_charts = sum(1 for n in z.namelist() if re.match(r"xl/charts/chart\d+\.xml$", n))
    info.append("原生图表 %d 个" % n_charts)
    if external:
        all_text = " ".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row
                            if isinstance(c.value, str))
        if not tapcheck.calc_disclaimer_ok([ws.title for ws in wb.worksheets], all_text):
            must.append("对外试算表缺少免责提示（如“仅供参考 / 以保险合同为准”，规则见 compliance.json 的 calc_disclaimer）")
    if todo:
        msg = "仍有占位 %d 处：%s" % (len(todo), "、".join(todo[:12]) + ("……" if len(todo) > 12 else ""))
        (must if final else info).append(msg)
    info.append("公式 %d 个" % n_formula)
    return must, should, info


def source_check(path, content_path):
    """与内容 JSON 逐表核对：行数、原始字段、原文是否被改写、主键唯一、智能列是否标注。"""
    import datetime as dt
    import json
    with open(content_path, encoding="utf-8") as f:
        data = json.load(f)
    wb = load_workbook(path)
    must, should, info = [], [], []
    lab = CONF.label("ai_note", **{"from": "", "date": ""}).split("｜")[0]
    for t in data.get("data") or []:
        name = t["name"]
        if name not in wb.sheetnames:
            must.append("缺少数据表“%s”" % name)
            continue
        ws = wb[name]
        tab = next(iter(ws.tables.values()), None)
        if tab is None:
            must.append("数据表“%s”不是 Excel 表格对象（没有筛选和结构化引用）" % name)
            continue
        ref = tab.ref if hasattr(tab, "ref") else tab
        from openpyxl.utils import range_boundaries
        c0, r0, c1, r1 = range_boundaries(ref)
        heads = [ws.cell(row=r0, column=c).value for c in range(c0, c1 + 1)]
        fields = [f["name"] for f in t["fields"]]
        miss = [x for x in fields if x not in heads]
        if miss:
            must.append("“%s”缺少字段：%s" % (name, "、".join(miss)))
        rows = t.get("rows") or []
        n = r1 - r0
        if rows and n < len(rows):
            must.append("“%s”有 %d 条记录，少于内容 JSON 的 %d 条" % (name, n, len(rows)))
        elif rows and n > len(rows):
            info.append("“%s”比内容 JSON 多 %d 条（渲染后新增的记录）" % (name, n - len(rows)))
        if t.get("expect_rows") is not None and t["expect_rows"] != len(rows):
            must.append("“%s”检索到 %d 条，写入 %d 条" % (name, t["expect_rows"], len(rows)))
        plain = [f for f in t["fields"] if f.get("type") != "formula"]
        key = t.get("key") or fields[0]
        kcol = c0 + heads.index(key) if key in heads else None
        at = {}                                          # 按主键找行：用户排序、筛选后也能核对
        if kcol:
            for r in range(r0 + 1, r1 + 1):
                kv = ws.cell(row=r, column=kcol).value
                if kv not in (None, ""):
                    at.setdefault(str(kv).strip(), r)
        changed, lost = 0, []
        for i, row in enumerate(rows):
            vals = row if isinstance(row, dict) else {f["name"]: (row[j] if j < len(row) else None) for j, f in enumerate(plain)}
            kv = str(vals.get(key, "")).strip()
            if kcol and kv not in at:
                lost.append(kv)
                continue
            rr = at[kv] if kcol else r0 + 1 + i
            for f in plain:
                if f["name"] not in heads or f.get("type") == "link":
                    continue
                cell = ws.cell(row=rr, column=c0 + heads.index(f["name"])).value
                a = vals.get(f["name"])
                if isinstance(cell, (dt.datetime, dt.date)):
                    cell = cell.strftime("%Y-%m-%d")
                if a in (None, "") and cell in (None, ""):
                    continue
                if str(a).strip() != str(cell).strip():
                    changed += 1
                    if changed <= 5:
                        must.append("“%s”%s“%s”与原始数据不一致：%s → %s" % (name, kv, f["name"], str(a)[:30], str(cell)[:30]))
        if lost:
            must.append("“%s”缺少 %d 条原始记录：%s" % (name, len(lost), "、".join(lost[:10]) + ("…" if len(lost) > 10 else "")))
        if changed > 5:
            must.append("“%s”另有 %d 处与原始数据不一致" % (name, changed - 5))
        for f in t["fields"]:
            if f.get("type") == "ai" and f["name"] in heads:
                c = ws.cell(row=r0, column=c0 + heads.index(f["name"]))
                if not c.comment or lab not in c.comment.text:
                    should.append("“%s”智能列“%s”表头没有标注依据和生成时间" % (name, f["name"]))
        info.append("“%s”：%d 条 × %d 个字段，与内容 JSON 一致" % (name, n, len(fields)) if not changed and not miss and not lost
                    else "“%s”：核对完成" % name)
    # 视图和仪表盘只能引用数据，不能有手填数字
    derived = [v["name"] for v in data.get("views") or []] + ([data["dashboard"]["name"]] if data.get("dashboard") else [])
    for nm in derived:
        if nm not in wb.sheetnames:
            must.append("缺少工作表“%s”" % nm)
            continue
        ws = wb[nm]
        hard = [c.coordinate for row in ws.iter_rows(min_row=2) for c in row
                if isinstance(c.value, (int, float)) and not isinstance(c.value, bool) and c.column < 15]
        if hard:
            should.append("“%s”有 %d 个手填数字（应为公式引用数据表）：%s" % (nm, len(hard), "、".join(hard[:8])))
    return must, should, info


def recalc(path):
    """用 LibreOffice 无界面打开并另存，得到带计算结果的副本，再扫描错误值。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None, "未找到 LibreOffice，跳过重算检查（可在 Excel 中打开后用“公式 → 错误检查”代替）"
    out = tempfile.mkdtemp(prefix="xlsx_recalc_")
    try:
        subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", out, path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        conv = os.path.join(out, os.path.basename(path))
        wb = load_workbook(conv, data_only=True)
        found = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.strip() in ERRORS:
                        found.append("%s!%s = %s" % (ws.title, c.coordinate, c.value))
        return found, None
    except Exception as e:      # noqa: BLE001
        return None, "重算检查失败：%s" % e
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="知识生成 Excel 质检")
    ap.add_argument("xlsx")
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--recalc", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--content", help="内容 JSON：逐表核对行数、字段、原文是否被改写（原始数据不丢失）")
    ap.add_argument("--config", action="append", default=[])
    a = ap.parse_args()
    configure("excel", a)
    must, should, info = scan(a.xlsx, a.external, a.final)
    if a.content:
        m2, s2, i2 = source_check(a.xlsx, a.content)
        must, should, info = must + m2, should + s2, info + i2
    elif CONF.rule("review").get("source_check"):
        should.append("未提供 --content，未核对原始数据是否完整（建议加上）")
    if a.recalc:
        found, msg = recalc(a.xlsx)
        if msg:
            info.append(msg)
        elif found:
            must += ["公式错误：" + x for x in found]
        else:
            info.append("LibreOffice 重算：未发现公式错误值")
    # 同类“建议”只保留前 N 条，避免刷屏（N 见 rules.excel.review.max_should）
    cap = CONF.rule("review")["max_should"]
    if len(should) > cap:
        should = should[:cap] + ["……另有 %d 条同类建议" % (len(should) - cap)]
    md = tapcheck.report_md(os.path.basename(a.xlsx), must, should, info)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.exit(1 if must else 0)


if __name__ == "__main__":
    main()
