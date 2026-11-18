# -*- coding: utf-8 -*-
"""
知识生成 Word —— 交付前质检

用法：
  python review_docx.py <文档.docx> --doc-type product [--final] [--out 质检报告.md]

检查四类问题（分“必须修改 / 建议修改”两级）：
  1. 合规用语：收益承诺、与存款类比、绝对化用语、诱导性表述
  2. 监管/业务必备要素：按文档类型检查（如产品资料必须有犹豫期、等待期、责任免除、风险提示）
  3. 结构：标题层级跳级、空章节、超长段落、缺少图表
  4. 占位符：【待补充】【请确认】的数量（--final 时视为必须修改）

退出码：0 通过；1 存在“必须修改”项。
词表为行业常见口径，上线前请合规部审定后改 BANNED / REQUIRED 两处。
"""
import argparse
import re
import sys

from docx import Document

CUSTOMER_FACING = {"product", "proposal", "claims", "notice", "underwriting"}

# (类别, 正则, 说明)
BANNED = [
    ("收益承诺", r"保本|稳赚|稳赚不赔|零风险|无风险|保证收益|收益(?:有)?保证|确保收益|高收益|稳定收益",
     "不得承诺或暗示收益；分红、万能账户收益须写明“不保证”"),
    ("存款类比", r"存款|储蓄(?:替代|产品)|比存银行|利息更高|理财产品",
     "不得将保险产品与存款、理财产品类比或混同"),
    ("绝对化用语", r"最好|最佳|第一|唯一|顶级|最优|全网最低|100%\s*理赔|百分百|一定(?:能|会)?赔|秒赔",
     "避免绝对化、无法证实的表述"),
    ("诱导表述", r"限时抢购|错过(?:再)?无|最后机会|马上停售|即将涨价|免费送保险",
     "避免制造紧迫感或诱导购买"),
    ("误导表述", r"什么都(?:能)?赔|全都赔|无条件(?:赔付|给付)|不用体检就能保|带病(?:也)?能(?:保|投)",
     "保障范围须以合同条款为准，不得夸大"),
]

# 文档类型 → [(要素名, 正则)]
REQUIRED = {
    "product": [("犹豫期", r"犹豫期"), ("等待期", r"等待期"), ("责任免除", r"责任免除|免责"),
                ("条款为准声明", r"以.{0,6}(?:保险)?合同.{0,4}条款为准"), ("风险提示", r"风险提示")],
    "proposal": [("条款为准声明", r"以.{0,6}(?:保险)?合同.{0,4}条款为准"), ("风险提示", r"风险提示"),
                 ("犹豫期", r"犹豫期")],
    "claims": [("理赔材料", r"(?:理赔|申请)材料"), ("办理时效", r"时效|时限|工作日"),
               ("联系方式", r"客服|热线|联系")],
    "underwriting": [("如实告知", r"如实告知"), ("健康告知", r"健康告知")],
    "training": [("学习目标", r"学习目标"), ("自测/练习", r"自测|练习|测验")],
    "policy": [("适用范围", r"适用范围"), ("职责", r"职责"), ("生效/施行", r"生效|施行")],
    "analysis": [("数据口径/来源", r"口径|资料来源|数据来源")],
    "project": [("目标", r"目标"), ("计划/里程碑", r"里程碑|计划"), ("风险", r"风险")],
    "notice": [("联系方式", r"客服|热线|联系"), ("生效日期", r"生效|起")],
    "compliance": [("问题清单", r"问题|发现"), ("整改责任", r"责任人|负责")],
}

# 这些语境里出现“存款/第一”等不算违规（如“第一条”“第一年度”“第一受益人”）
WHITELIST = re.compile(r"第一(?:条|章|节|年|个|次|步|季度|受益人|期|项|部分|阶段|顺位)|唯一(?:编号|标识)")


def iter_text(doc):
    for p in doc.paragraphs:
        yield p.style.name if p.style is not None else "", p.text
    for t in doc.tables:
        for row in t.rows:
            seen = set()
            for c in row.cells:
                if id(c._tc) in seen:
                    continue
                seen.add(id(c._tc))
                for p in c.paragraphs:
                    yield "Table", p.text


def review(path, doc_type, final=False):
    doc = Document(path)
    must, should, info = [], [], []
    texts = list(iter_text(doc))
    full = "\n".join(t for _, t in texts)

    # 1. 合规用语
    for cat, pat, why in BANNED:
        for _, t in texts:
            clean = WHITELIST.sub("", t)
            for m in re.finditer(pat, clean):
                s = max(0, m.start() - 12)
                snippet = clean[s:m.end() + 12].replace("\n", " ")
                item = "【%s】“%s”：…%s…（%s）" % (cat, m.group(0), snippet, why)
                # 否定式提及（如“本产品不保本”“不等同于银行存款”）不算违规
                neg = re.search(r"不(?:承诺|保证|属于|是|等同|同于|可视为|应理解为)|并非|而非|区别于|不\s*$",
                                clean[max(0, m.start() - 10):m.start()])
                if neg:
                    continue
                (must if doc_type in CUSTOMER_FACING else should).append(item)

    # 2. 必备要素
    for name, pat in REQUIRED.get(doc_type, []):
        if not re.search(pat, full):
            must.append("缺少必备要素：%s" % name)

    # 3. 结构
    levels = []
    for p in doc.paragraphs:
        n = p.style.name if p.style is not None else ""
        if n.startswith("Heading "):
            try:
                levels.append((int(n.split()[-1]), p.text.strip()))
            except ValueError:
                pass
    if not levels:
        must.append("没有任何标题：读者无法快速定位内容")
    prev = 0
    for lvl, txt in levels:
        if lvl > prev + 1:
            should.append("标题跳级：“%s”是 %d 级标题，但前面没有 %d 级标题" % (txt, lvl, lvl - 1))
        prev = lvl
    # 空章节：标题后紧跟同级或更高级标题
    body = [(p.style.name if p.style is not None else "", p.text.strip()) for p in doc.paragraphs]
    for i, (s, t) in enumerate(body):
        if not s.startswith("Heading "):
            continue
        lvl = int(s.split()[-1]) if s.split()[-1].isdigit() else 9
        j = i + 1
        while j < len(body) and not body[j][1] and not body[j][0].startswith("Heading "):
            j += 1
        if j < len(body) and body[j][0].startswith("Heading "):
            nxt = int(body[j][0].split()[-1]) if body[j][0].split()[-1].isdigit() else 9
            if nxt <= lvl and not _has_table_between(doc, i, j):
                should.append("可能是空章节：“%s”下面没有内容" % t)
    for s, t in body:
        if not s.startswith("Heading ") and len(t) > 320:
            should.append("段落过长（%d 字）：“%s…”，建议拆分或改为要点/表格" % (len(t), t[:24]))
    n_img = len(doc.inline_shapes)
    n_tab = len(doc.tables)
    n_h1 = sum(1 for l, _ in levels if l == 1)
    if doc_type not in ("policy", "notice") and n_h1 >= 3 and n_img + max(n_tab - 2, 0) < max(1, n_h1 // 2):
        should.append("图表偏少：%d 个一级章节只有 %d 张图、%d 个表格（含封面信息表），"
                      "数字和流程建议用图表呈现" % (n_h1, n_img, n_tab))

    # 4. 占位符
    todo = len(re.findall(r"【待补充", full))
    confirm = len(re.findall(r"【请确认", full))
    if todo or confirm:
        msg = "仍有占位：【待补充】%d 处、【请确认】%d 处" % (todo, confirm)
        (must if final else info).append(msg)

    info.append("统计：一级标题 %d，标题总数 %d，图片 %d，表格 %d，正文约 %d 字"
                % (n_h1, len(levels), n_img, n_tab, len(re.sub(r"\s", "", full))))
    return must, should, info


def _has_table_between(doc, i, j):
    """判断两个段落之间是否夹着表格（表格不在 doc.paragraphs 中）。"""
    body = doc.element.body
    paras = [p._p for p in doc.paragraphs]
    a, b = paras[i], paras[j]
    node = a.getnext()
    while node is not None and node is not b:
        if node.tag.endswith("}tbl"):
            return True
        node = node.getnext()
    return False


def to_markdown(path, doc_type, must, should, info):
    lines = ["# 质检报告：%s" % path, "", "文档类型：`%s`" % doc_type, ""]
    lines.append("**结论：%s**" % ("不通过，需修改后再交付" if must else "通过"))
    lines.append("")
    for title, items in (("必须修改", must), ("建议修改", should), ("说明", info)):
        lines.append("## %s（%d）" % (title, len(items)))
        lines += ["- " + x for x in items] or ["- 无"]
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="知识生成 Word 质检")
    ap.add_argument("docx")
    ap.add_argument("--doc-type", required=True, choices=sorted(REQUIRED))
    ap.add_argument("--final", action="store_true", help="正式交付：占位符也视为必须修改")
    ap.add_argument("--out")
    a = ap.parse_args()
    must, should, info = review(a.docx, a.doc_type, a.final)
    md = to_markdown(a.docx, a.doc_type, must, should, info)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.exit(1 if must else 0)


if __name__ == "__main__":
    main()
