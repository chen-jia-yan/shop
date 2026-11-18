# -*- coding: utf-8 -*-
"""
知识生成 Excel —— 交付前质检

用法：
  python review_xlsx.py <文件.xlsx> [--external] [--final] [--recalc] [--out 质检报告.md]

  --external  对外文件（发给客户）：启用合规用语检查，试算表必须有“仅供参考/以合同为准”提示
  --final     正式交付：【待补充】【请确认】视为必须修改
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

from openpyxl import load_workbook

BANNED = [
    ("收益承诺", r"保本|稳赚|零风险|无风险|保证收益|高收益|稳定收益"),
    ("存款类比", r"存款|比存银行|储蓄替代|理财产品"),
    ("绝对化用语", r"最好|最佳|唯一|顶级|最优|100%\s*理赔|一定(?:能|会)?赔|秒赔"),
    ("诱导表述", r"限时抢购|错过(?:再)?无|最后机会|马上停售"),
]
NEG = re.compile(r"不(?:承诺|保证|属于|是|等同|同于)|并非|而非|区别于|不\s*$")
ERRORS = ("#REF!", "#DIV/0!", "#N/A", "#VALUE!", "#NAME?", "#NUM!", "#NULL!")
SHEET_REF = re.compile(r"'((?:[^']|'')+)'!")


def scan(path, external, final):
    wb = load_workbook(path)        # 保留公式文本
    must, should, info = [], [], []
    names = set(wb.sheetnames)
    n_formula = 0
    todo = []
    for ws in wb.worksheets:
        title = ws.cell(row=2, column=1).value
        if not title and ws.max_row > 1:
            should.append("工作表“%s”第 2 行没有标题" % ws.title)
        if ws.max_row > 15 and ws.freeze_panes is None:
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
                if "【待补充" in v or "【请确认" in v:
                    todo.append(where)
                if external:
                    for cat, pat in BANNED:
                        for m in re.finditer(pat, v):
                            if NEG.search(v[max(0, m.start() - 10):m.start()]):
                                continue
                            must.append("%s【%s】“%s”：%s" % (where, cat, m.group(0), v[:40]))
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
        has_calc = any("试算" in ws.title or "测算" in ws.title for ws in wb.worksheets)
        if has_calc and not re.search(r"仅供参考|以.{0,6}合同.{0,4}为准", all_text):
            must.append("对外试算表缺少“仅供参考 / 以保险合同为准”提示")
    if todo:
        msg = "仍有占位 %d 处：%s" % (len(todo), "、".join(todo[:12]) + ("……" if len(todo) > 12 else ""))
        (must if final else info).append(msg)
    info.append("公式 %d 个" % n_formula)
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


def to_md(path, must, should, info):
    lines = ["# 质检报告：%s" % os.path.basename(path), "",
             "**结论：%s**" % ("不通过，需修改后再交付" if must else "通过"), ""]
    for title, items in (("必须修改", must), ("建议修改", should), ("说明", info)):
        lines.append("## %s（%d）" % (title, len(items)))
        lines += ["- " + x for x in items] or ["- 无"]
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="知识生成 Excel 质检")
    ap.add_argument("xlsx")
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--recalc", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    must, should, info = scan(a.xlsx, a.external, a.final)
    if a.recalc:
        found, msg = recalc(a.xlsx)
        if msg:
            info.append(msg)
        elif found:
            must += ["公式错误：" + x for x in found]
        else:
            info.append("LibreOffice 重算：未发现公式错误值")
    # 同类“建议”只保留前 15 条，避免刷屏
    if len(should) > 15:
        should = should[:15] + ["……另有 %d 条同类建议" % (len(should) - 15)]
    md = to_md(a.xlsx, must, should, info)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.exit(1 if must else 0)


if __name__ == "__main__":
    main()
