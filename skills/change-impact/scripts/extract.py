# -*- coding: utf-8 -*-
"""
文档抽取：把 docx / md / txt / json（kb-to-word 内容格式或通用章节格式）/ pdf 统一转成“块”列表。

块（block）：
  {"seq": 序号, "kind": "heading|para|table", "level": 标题级别（仅 heading）,
   "path": ["第二章 保险责任", ...]  所在章节路径,
   "anchor": "第五条" 或 null        条款号（用于对齐时加分，条款重新编号也能对上）,
   "text": 原文, "norm": 规范化文本}

标题识别：docx 的标题样式 / md 的 # / 配置中的章节编号格式（impact.json 的 heading_patterns，
如“第一章”“一、”“（一）”“1.1”），只对较短且不以句号结尾的段落生效，避免把正文误判为标题。
表格：每个数据行转成“表头：值；表头：值”的一块，便于逐行比对。
"""
import os
import re

from ci_common import imp, norm

SENT_END = "。；;!！?？"
NON_TEXT = ("drawing", "pict", "object", "oMath", "oMathPara")


def _heading_rules():
    return [(re.compile(p), int(lv)) for p, lv in imp().get("heading_patterns", [])]


def _anchor_re():
    p = imp().get("anchor_pattern")
    return re.compile(p) if p else None


def _guess_heading(text):
    t = norm(text)
    if not t or len(t) > 40 or t[-1] in SENT_END:
        return None
    for rx, lv in _heading_rules():
        if rx.match(t):
            return lv
    return None


class Builder(object):
    def __init__(self):
        self.blocks = []
        self.path = []
        self.anchor_rx = _anchor_re()
        self.non_text = 0          # 图片、公式、嵌入对象：不参与比对，只计数提示
        self.empty_pages = 0       # PDF 中没有抽到文字的页（疑似扫描件）

    def heading(self, text, level):
        t = norm(text)
        if not t:
            return
        level = max(1, int(level))
        self.path = self.path[:level - 1] + [t]
        self._add("heading", t, level=level)

    def para(self, text):
        t = norm(text)
        if not t:
            return
        lv = _guess_heading(t)
        if lv:
            self.heading(t, lv)
            return
        self._add("para", t)

    def table(self, header, rows, caption=None):
        header = [norm(h) for h in header]
        for r in rows:
            cells = [norm(c) for c in r]
            if not any(cells):
                continue
            if header and len(header) == len(cells):
                text = "；".join("%s：%s" % (h, c) for h, c in zip(header, cells) if c)
            else:
                text = "；".join(c for c in cells if c)
            self._add("table", text, caption=caption)

    def _add(self, kind, text, level=None, caption=None):
        anchor = None
        if self.anchor_rx and kind != "heading":
            m = self.anchor_rx.match(text)
            if m:
                anchor = m.group(1)
        b = {"seq": len(self.blocks), "kind": kind, "path": list(self.path if kind != "heading" else self.path[:-1]),
             "anchor": anchor, "text": text, "norm": norm(text)}
        if level:
            b["level"] = level
        if caption:
            b["caption"] = caption
        self.blocks.append(b)


# ---------------- 各格式 ----------------
def _from_docx(path, bd):
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        raise SystemExit("读取 .docx 需要 python-docx：pip install -U python-docx")
    doc = Document(path)
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in ("p", "tbl"):
            bd.non_text += sum(1 for el in child.iter() if el.tag.rsplit("}", 1)[-1] in NON_TEXT)
        if tag == "p":
            p = Paragraph(child, doc)
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"^(?:Heading|标题)\s*(\d)", style)
            if m and p.text.strip():
                bd.heading(p.text, int(m.group(1)))
            else:
                bd.para(p.text)
        elif tag == "tbl":
            t = Table(child, doc)
            grid = []
            for row in t.rows:
                seen, cells = set(), []
                for c in row.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(c.text)
                grid.append(cells)
            if grid:
                bd.table(grid[0], grid[1:]) if len(grid) > 1 else bd.para(" ".join(grid[0]))


def _from_md(text, bd):
    table = []

    def flush():
        if table:
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table]
            rows = [r for r in rows if not all(re.match(r"^:?-{2,}:?$", c) for c in r if c)]
            if rows:
                bd.table(rows[0], rows[1:])
            del table[:]

    buf = []

    def flush_para():
        if buf:
            bd.para(" ".join(buf))
            del buf[:]

    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|"):
            flush_para()
            table.append(s)
            continue
        flush()
        if not s:
            flush_para()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para()
            bd.heading(m.group(2), len(m.group(1)))
            continue
        m = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", s)
        if m:
            flush_para()
            bd.para(m.group(1))
            continue
        if _guess_heading(s) or (bd.anchor_rx and bd.anchor_rx.match(norm(s))):
            flush_para()
            bd.para(s)
            continue
        buf.append(s)
    flush_para()
    flush()


def _from_txt(text, bd):
    for ln in text.splitlines():
        bd.para(ln)


def _from_json(data, bd):
    """支持 kb-to-word 的内容 JSON（blocks），以及通用的 [{"title","text"}] / {"sections": [...]}。"""
    if isinstance(data, dict) and isinstance(data.get("blocks"), list):
        for b in data["blocks"]:
            t = b.get("type")
            if t == "heading":
                bd.heading(b.get("text", ""), b.get("level", 1))
            elif t in ("paragraph", "lead", "quote", "note"):
                bd.para(b.get("text", ""))
            elif t in ("bullets", "numbered", "checklist"):
                for it in b.get("items", []):
                    bd.para(it if isinstance(it, str) else it.get("text", ""))
            elif t == "table":
                bd.table(b.get("columns", []), b.get("rows", []), b.get("caption"))
            elif t == "callout":
                bd.para(" ".join(x for x in [b.get("title", ""), b.get("text", "")] + list(b.get("items", [])) if x))
            elif t == "faq":
                for it in b.get("items", []):
                    bd.para("%s %s" % (it.get("q", ""), it.get("a", "")))
            elif t == "glossary":
                for it in b.get("items", []):
                    bd.para("%s：%s" % (it.get("term", ""), it.get("definition", "")))
            elif t in ("steps", "flow", "timeline"):
                for it in b.get("items") or b.get("steps") or b.get("nodes") or []:
                    if isinstance(it, str):
                        bd.para(it)
                    else:
                        bd.para(" ".join(str(it.get(k, "")) for k in ("time", "title", "desc", "owner") if it.get(k)))
        return
    secs = data.get("sections") if isinstance(data, dict) else data
    if not isinstance(secs, list):
        raise SystemExit("无法识别的 JSON 结构：需要 kb-to-word 的 blocks，或 [{\"title\",\"text\"}] 列表")

    def walk(items, level):
        for s in items:
            if s.get("title"):
                bd.heading(s["title"], level)
            for para in re.split(r"\n+", s.get("text") or s.get("content") or ""):
                bd.para(para)
            walk(s.get("children", []), level + 1)
    walk(secs, 1)


def _from_pdf(path, bd):
    try:
        import pdfplumber
    except ImportError:
        raise SystemExit("读取 .pdf 需要 pdfplumber：pip install pdfplumber（扫描件需先 OCR）")
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if not txt.strip():
                bd.empty_pages += 1
            for ln in txt.splitlines():
                bd.para(ln)


def load(path):
    """返回 {"name": 文件名, "path": 路径, "blocks": [...]}。"""
    if not os.path.exists(path):
        raise SystemExit("文件不存在：%s" % path)
    bd = Builder()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        _from_docx(path, bd)
    elif ext == ".pdf":
        _from_pdf(path, bd)
    else:
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
        if ext == ".json":
            import json
            _from_json(json.loads(raw), bd)
        elif ext in (".md", ".markdown"):
            bd.non_text += len(re.findall(r"!\[[^\]]*\]\(", raw))
            _from_md(raw, bd)
        else:
            _from_txt(raw, bd)
    if not bd.blocks:
        raise SystemExit("没有从 %s 读到任何内容（扫描版 PDF 需先 OCR）" % path)
    return {"name": os.path.basename(path), "path": os.path.abspath(path), "blocks": bd.blocks,
            "non_text": bd.non_text, "empty_pages": bd.empty_pages}
