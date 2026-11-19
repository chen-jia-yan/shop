# -*- coding: utf-8 -*-
"""
内容体检：提示“空洞”的内容。渲染（看内容 JSON）和质检（看 .docx）共用同一套规则，
词表和阈值在 tap-config/rules.json 的 rules.word.content。只提示、不拦截。

检查项：
  1. 套话：一段里套话词（尽快、进一步、全面……）达到阈值且没有任何数字
  2. 话题式标题：以“情况/分析/概述……”结尾、没有数字和冒号的短标题
  3. 内容单薄：一级章节正文不足阈值字数，且没有任何表格或图示
  4. 缺数字：数据类文档（经营分析、项目方案等）的一级章节一个数字都没有
  5. 结论不先行：要求结论先行的文档类型，一级章节第一个元素不是导语/提示框/数据卡片/执行摘要
  6. 要点只有关键词：一组要点每条都很短
  7. 重复表述：同一句话出现两次以上
"""
import re

from themes import R

_DIGIT = re.compile(r"\d")
_SENT = re.compile(r"[^。！？；\n]+")
VISUAL = {"table", "kpi", "flow", "timeline", "structure", "matrix", "compare", "steps", "chart", "image",
          "facts", "exec_summary", "progress", "checklist", "glossary", "faq", "contact", "signoff", "revisions"}


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return " ".join(_txt(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_txt(x) for k, x in v.items() if k not in ("type", "kind", "chart", "style", "widths"))
    return ""


def flatten_blocks(blocks):
    """内容 JSON → [(kind, text)]；kind：h1/h2/h3、p（段落）、lead、li（要点）、visual:<类型>。"""
    out = []
    for b in blocks:
        t = b.get("type")
        if t == "heading":
            out.append(("h%d" % min(int(b.get("level", 1)), 3), b.get("text", "")))
        elif t in ("paragraph", "quote", "note"):
            out.append(("p", b.get("text", "")))
        elif t == "lead":
            out.append(("lead", b.get("text", "")))
        elif t in ("bullets", "numbered"):
            items = [i if isinstance(i, str) else i.get("text", "") for i in b.get("items", [])]
            out.append(("list", items))
        elif t == "callout":
            out.append(("callout", _txt([b.get("title"), b.get("text")])))
            if b.get("items"):
                out.append(("list", [_txt(i) for i in b["items"]]))
        elif t == "page_break":
            continue
        else:
            out.append(("visual:" + str(t), _txt(b)))
    return out


def _strip_num(t):
    """去掉标题编号（“一、”“1.2　”），.docx 里的标题带编号。"""
    return _NUMPFX.sub("", t.strip())


_NUMPFX = re.compile(r"^(?:[一二三四五六七八九十]+、|\d+(?:\.\d+)*[\s　.、]*)")


def check(seq, doc_type=None, lead=True):
    """seq：[(kind, text)]，返回（提示文字列表，提示总数）。lead=False 时不检查“结论先行”（.docx 里分不出导语）。"""
    cf = R("content")
    vague = cf["vague_words"]
    hints = []
    seq = [(k, _strip_num(t) if k.startswith("h") else t) for k, t in seq]

    def vague_hits(s):
        return [w for w in vague if w in s]

    # 1 / 6：套话、要点只有关键词
    for kind, text in seq:
        if kind in ("p", "lead", "callout"):
            hits = vague_hits(text)
            if len(hits) >= cf["vague_per_para"] and not _DIGIT.search(text):
                hints.append("套话偏多：“%s…”（%s）——换成具体的数字、时限、条件或责任部门"
                             % (text[:22], "、".join(hits[:5])))
        elif kind == "list":
            items = [i for i in text if i]
            if len(items) >= 3 and all(len(re.sub(r"\*\*|\s", "", i)) < cf["bullet_min_chars"] for i in items):
                hints.append("要点只有关键词：“%s”——每条补一句说明（做什么、标准是什么、为什么）"
                             % "、".join(items[:4]))
            for i in items:
                hits = vague_hits(i)
                if len(hits) >= cf["vague_per_para"] and not _DIGIT.search(i):
                    hints.append("套话偏多：“%s…”（%s）" % (i[:22], "、".join(hits[:5])))

    # 2：话题式标题
    for kind, text in seq:
        if kind in ("h1", "h2"):
            t = text.strip()
            if t in cf["title_exempt"] or _DIGIT.search(t) or "：" in t or ":" in t:
                continue
            if len(t) <= cf["topic_max_len"] and any(t.endswith(s) for s in cf["topic_suffixes"]):
                hints.append("标题像话题：“%s”——改成结论，如“××同比增长 x%%，主要来自××”" % t)

    # 3 / 4 / 5：按一级章节检查
    chapters, cur = [], None
    for kind, text in seq:
        if kind == "h1":
            cur = {"title": text, "items": []}
            chapters.append(cur)
        elif cur is not None:
            cur["items"].append((kind, text))
    for ch in chapters:
        if ch["title"].strip() in cf["title_exempt"]:
            continue
        body = [(k, t) for k, t in ch["items"] if not k.startswith("h")]
        text = " ".join(_txt(t) for _, t in ch["items"])
        prose = sum(len(_txt(t)) for k, t in body if not k.startswith("visual"))
        has_visual = any(k.startswith("visual") or (k == "list" and len(t) >= 3) for k, t in body)
        if not has_visual and prose < cf["thin_chapter_chars"]:
            hints.append("内容单薄：“%s”只有约 %d 字、没有表格或图示——补充具体规则、数据或案例，或并入相邻章节"
                         % (ch["title"], prose))
        if doc_type in cf["data_types"] and not _DIGIT.search(text):
            hints.append("缺数字：“%s”整章没有一个数字——经营分析、方案类文档的每章至少给出一个有出处的数据" % ch["title"])
        if lead and doc_type in cf["lead_types"] and body:
            first = body[0][0]
            first = first.split(":", 1)[1] if first.startswith("visual:") else first
            if first not in cf["lead_blocks"]:
                hints.append("结论没有先行：“%s”开头不是结论——先用一句导语（lead）或核心要点说清结论" % ch["title"])

    # 7：重复表述
    seen = {}
    for kind, text in seq:
        for s in _SENT.findall(_txt(text)):
            s = s.strip()
            if len(s) >= cf["repeat_min_chars"]:
                seen[s] = seen.get(s, 0) + 1
    for s, n in seen.items():
        if n >= 2:
            hints.append("重复表述（%d 次）：“%s…”——保留一处，其他地方改为引用或删除" % (n, s[:22]))

    return hints[:cf["max_listed"]], len(hints)


def check_blocks(meta, blocks):
    return check(flatten_blocks(blocks), (meta or {}).get("doc_type"))
