# -*- coding: utf-8 -*-
"""
知识生成 PPT —— 交付前质检

用法：
  python review_pptx.py <文件.pptx> [--external] [--final] [--out 质检报告.md]

检查：合规用语（--external，词表见 tap-config/compliance.json）、占位符、每页文字量、讲稿备注、动画与切换、中文字体设置、
版式重复（读取渲染时写入的版式记录）、页数结构（封面/结束页/总结页）。
退出码：0 通过；1 存在“必须修改”项。
"""
import argparse
import json
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, configure                 # noqa: E402
import tapcheck                                   # noqa: E402

from pptx import Presentation                     # noqa: E402

P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
FRAMES = ("cover", "agenda", "section", "end", "disclaimer")


def slide_text(slide):
    out = []
    for sp in slide.shapes:
        out += _shape_text(sp)
    return out


def _shape_text(sp):
    out = []
    if (sp.name or "").startswith("tap_avoid"):      # 问答页“避免说”一栏本身列的就是违规用语，不算命中
        return out
    if sp.shape_type == 6:                      # 组合
        for s in sp.shapes:
            out += _shape_text(s)
        return out
    if sp.has_text_frame:
        for p in sp.text_frame.paragraphs:
            t = "".join(r.text for r in p.runs)
            if t.strip():
                out.append(t)
    if getattr(sp, "has_table", False) and sp.has_table:
        for row in sp.table.rows:
            for c in row.cells:
                if c.text.strip():
                    out.append(c.text)
    return out


def review(path, external=False, final=False):
    prs = Presentation(path)
    must, should, info = [], [], []
    rv = CONF.rule("review")
    rep = CONF.rule("repeat_run")
    try:
        rec = json.loads(prs.core_properties.comments or "{}")
    except ValueError:
        rec = {}
    layouts = rec.get("layouts", [])
    n = len(prs.slides)
    todo_pages, no_notes, no_font = [], [], 0
    anim = trans = 0
    for i, slide in enumerate(prs.slides, 1):
        texts = slide_text(slide)
        body = "".join(texts)
        lay = layouts[i - 1] if i - 1 < len(layouts) else ""
        if tapcheck.has_placeholder(body):
            todo_pages.append(str(i))
        chars = len(re.sub(r"\s", "", body))
        limit = rv["text_limit_dense"] if lay in rv["dense_layouts"] else rv["text_limit"]
        if chars > limit and lay not in FRAMES:
            should.append("第 %d 页文字约 %d 字，偏多（建议 ≤%d），考虑精简或拆页" % (i, chars, limit))
        if external:
            for t in texts:
                for cat, word, _, _ in tapcheck.banned_hits(t):
                    must.append("第 %d 页【%s】“%s”：%s" % (i, cat, word, t[:40]))
        if lay not in FRAMES:
            notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
            if not notes:
                no_notes.append(str(i))
        el = slide._element
        anim += 1 if el.find(P_NS + "timing") is not None else 0
        trans += 1 if el.find(P_NS + "transition") is not None else 0
        for rpr in el.iter(A_NS + "rPr"):
            if rpr.find(A_NS + "ea") is None:
                no_font += 1
    if todo_pages:
        msg = "第 %s 页仍有占位符（待补充 / 请确认）" % "、".join(todo_pages)
        (must if final else should).append(msg)
    if no_notes:
        should.append("第 %s 页没有演讲备注" % "、".join(no_notes))
    if no_font:
        should.append("%d 处文字没有单独设置中文字体，可能在其他电脑上显示为宋体" % no_font)
    run = 1
    for k in range(1, len(layouts)):
        if layouts[k] == layouts[k - 1] and layouts[k] not in ("section",):
            run += 1
            if run == rep:
                should.append("第 %d-%d 页连续使用同一版式（%s）" % (k - rep + 2, k + 1, layouts[k]))
        else:
            run = 1
    if external and layouts and "disclaimer" not in layouts:
        must.append("对外材料缺少“重要提示”页（渲染时 meta.external 设为 true 会自动插入）")
    if rec.get("minutes"):
        info.append("预计讲述约 %d 分钟" % round(sum(rec["minutes"])))
    if layouts:
        if layouts[0] != "cover":
            should.append("第 1 页不是封面")
        if layouts[-1] != "end":
            should.append("最后一页不是结束页")
        frame = ("cover", "agenda", "section", "end", "statement", "big_number", "summary", "exec_summary", "disclaimer")
        n_content = sum(1 for l in layouts if l not in frame)
        if n_content >= CONF.rule("summary_min_content") and "summary" not in layouts:
            should.append("内容页较多（%d 页）但没有“总结与行动”页" % n_content)
        varieties = len(set(l for l in layouts if l not in FRAMES))
        info.append("共使用 %d 种版式：%s" % (varieties, "、".join(sorted(set(layouts)))))
    info.append("共 %d 页；有动画 %d 页，有切换效果 %d 页；风格：%s" % (n, anim, trans, rec.get("theme", "未知")))
    return must, should, info


def main():
    ap = argparse.ArgumentParser(description="知识生成 PPT 质检")
    ap.add_argument("pptx")
    ap.add_argument("--external", action="store_true", help="对外材料：启用合规用语检查")
    ap.add_argument("--final", action="store_true", help="正式交付：占位符视为必须修改")
    ap.add_argument("--out")
    ap.add_argument("--config", action="append", default=[])
    a = ap.parse_args()
    configure("ppt", a)
    must, should, info = review(a.pptx, a.external, a.final)
    md = tapcheck.report_md(a.pptx, must, should, info)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.exit(1 if must else 0)


if __name__ == "__main__":
    main()
