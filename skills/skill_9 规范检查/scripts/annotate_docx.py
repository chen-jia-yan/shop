#!/usr/bin/env python3
"""根据检查结果给 Word 文档加批注，另存为新文件（不修改原文件）。

用法:
    python annotate_docx.py input.docx issues.json output.docx [--author 规范检查]

issues.json 格式见 examples/issues.json。每个问题用 para（段落编号，来自 extract_docx.py）定位；
para 找不到或文字对不上时，用 quote 在全文中查找；都找不到则挂到文档第一段。

批注方式:
    - python-docx >= 1.2：使用 Word 原生批注（右侧批注栏）
    - 更早的版本：在对应段落后插入红色【检查意见】段落，并提示升级

依赖: python-docx  (pip install -U python-docx)
"""
import argparse
import copy
import json
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.shared import RGBColor, Pt
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-docx，请先执行: pip install python-docx")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_docx import iter_paragraphs  # noqa: E402

LEVEL_ORDER = {"必须修改": 0, "建议修改": 1, "提示": 2}


def comment_text(issue):
    parts = [f"【{issue.get('level', '提示')}】{issue.get('issue', '')}"]
    if issue.get("rule"):
        parts.append(f"依据：{issue['rule']}")
    if issue.get("suggestion"):
        parts.append(f"建议：{issue['suggestion']}")
    return "\n".join(parts)


def locate(paras, issue):
    """返回 (段落, 定位方式)。"""
    idx = issue.get("para")
    quote = (issue.get("quote") or "").strip()
    if idx == 0 and not quote:
        # 缺失类问题：整篇都没有，挂在文档第一段
        for p in paras:
            if p.text.strip():
                return p, "doc_start"
    if isinstance(idx, int) and 1 <= idx <= len(paras):
        p = paras[idx - 1]
        if not quote or quote[:15] in p.text:
            return p, "para"
    if quote:
        key = quote[:15]
        for p in paras:
            if key and key in p.text:
                return p, "quote"
    for p in paras:
        if p.text.strip():
            return p, "fallback"
    return (paras[0] if paras else None), "fallback"


def ensure_run(p):
    if not p.runs:
        p.add_run("")
    return p.runs


def add_native_comment(doc, p, text, author):
    runs = ensure_run(p)
    doc.add_comment(runs, text=text, author=author, initials=author[:2])


def add_inline_note(p, text):
    """旧版 python-docx：在段落后插入一段红色检查意见。"""
    new_p = copy.deepcopy(p._p)
    for child in list(new_p):
        if child.tag.split("}")[-1] != "pPr":
            new_p.remove(child)
    p._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    note = Paragraph(new_p, p._parent)
    run = note.add_run("【检查意见】" + text.replace("\n", "；"))
    run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    run.font.size = Pt(9)


def main():
    ap = argparse.ArgumentParser(description="给 Word 文档加检查批注")
    ap.add_argument("input")
    ap.add_argument("issues")
    ap.add_argument("output")
    ap.add_argument("--author", default="规范检查")
    args = ap.parse_args()

    if Path(args.input).resolve() == Path(args.output).resolve():
        sys.exit("输出路径不能和原文件相同")

    with open(args.issues, encoding="utf-8") as f:
        issues = json.load(f)
    issues.sort(key=lambda x: LEVEL_ORDER.get(x.get("level"), 3))

    doc = Document(args.input)
    paras = [p for p, _ in iter_paragraphs(doc)]
    native = hasattr(doc, "add_comment")

    stats = {"para": 0, "quote": 0, "doc_start": 0, "fallback": 0}
    unplaced = []
    for issue in issues:
        p, how = locate(paras, issue)
        if p is None:
            unplaced.append(issue)
            continue
        stats[how] += 1
        if how == "fallback":
            issue = dict(issue, issue=f"（未能定位到原文「{(issue.get('quote') or '')[:20]}」）" + issue.get("issue", ""))
        text = comment_text(issue)
        if native:
            add_native_comment(doc, p, text, args.author)
        else:
            add_inline_note(p, text)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.output)

    counts = {}
    for x in issues:
        counts[x.get("level", "提示")] = counts.get(x.get("level", "提示"), 0) + 1
    print(json.dumps({
        "output": args.output,
        "mode": "Word 原生批注" if native else "段落内红字（python-docx 版本较旧，建议 pip install -U python-docx）",
        "counts": counts,
        "located_by": stats,
        "unplaced": len(unplaced),
    }, ensure_ascii=False, indent=2))
    if stats["fallback"]:
        print(f"注意：有 {stats['fallback']} 条意见未能定位到原文，已挂在文档开头，请在交付时说明。", file=sys.stderr)


if __name__ == "__main__":
    main()
