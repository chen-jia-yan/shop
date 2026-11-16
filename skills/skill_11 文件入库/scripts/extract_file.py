#!/usr/bin/env python3
"""提取文件内容并按章节拆分，标出疑似敏感信息。

用法:
    python extract_file.py <文件> --out /tmp/ingest/ [--max-chunk 1500] [--min-chunk 300]

支持: .docx（python-docx）、.pptx（python-pptx）、.xlsx（openpyxl）、.pdf（pypdf）、.txt/.md/.csv
输出: <out>/content.md、<out>/chunks.json、<out>/meta.json
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

SENSITIVE = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "手机号"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "身份证号"),
    (re.compile(r"(?<!\d)(?:62|4\d|5[1-5])\d{14,17}(?!\d)"), "疑似银行卡号"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "邮箱"),
    (re.compile(r"薪资|工资|薪酬|年薪|月薪|奖金|绩效(评价|评分|等级|打分)"), "薪酬/绩效"),
]
HEADING_TEXT = re.compile(r"^(第[一二三四五六七八九十百零\d]+[章节]|[一二三四五六七八九十]+、|\d+(\.\d+)*[、.\s])")
SENT_SPLIT = re.compile(r"(?<=[。！？；\n])")


def need(mod, pip_name):
    try:
        return __import__(mod)
    except ModuleNotFoundError:
        sys.exit(f"处理该格式需要 {pip_name}：pip install {pip_name}")


# ---------- 各格式提取：返回 [(级别, 文本)]，级别 0 = 正文，1-3 = 标题；表格作为一整块正文 ----------

def table_md(rows):
    rows = [[str(c or "").replace("\n", " ").replace("|", "／").strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def from_docx(path, warnings):
    need("docx", "python-docx")
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(path)
    blocks = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            text = p.text.strip()
            if not text:
                continue
            style = p.style.name if p.style is not None else ""
            m = re.search(r"(\d)", style)
            if style.startswith(("Heading", "标题")) or style == "Title":
                blocks.append((int(m.group(1)) if m else 1, text))
            elif len(text) <= 30 and HEADING_TEXT.match(text) and not text.endswith("。"):
                blocks.append((2, text))
            else:
                blocks.append((0, text))
        elif tag == "tbl":
            t = Table(child, doc)
            rows = []
            for row in t.rows:
                seen, cells = set(), []
                for cell in row.cells:
                    if id(cell._tc) not in seen:
                        seen.add(id(cell._tc))
                        cells.append(cell.text)
                rows.append(cells)
            md = table_md(rows)
            if md:
                blocks.append((0, md))
    return blocks


def from_pptx(path, warnings):
    need("pptx", "python-pptx")
    from pptx import Presentation
    prs = Presentation(path)
    blocks = []
    for i, slide in enumerate(prs.slides, 1):
        title, texts = None, []
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text_frame.text.strip()
        for shp in slide.shapes:
            if shp == slide.shapes.title:
                continue
            if shp.has_text_frame and shp.text_frame.text.strip():
                texts.append(shp.text_frame.text.strip())
            if getattr(shp, "has_table", False) and shp.has_table:
                texts.append(table_md([[c.text for c in r.cells] for r in shp.table.rows]))
        if slide.has_notes_slide:
            note = slide.notes_slide.notes_text_frame.text.strip()
            if note:
                texts.append(f"（备注）{note}")
        blocks.append((2, f"第 {i} 页" + (f"：{title}" if title else "")))
        if texts:
            blocks.append((0, "\n".join(texts)))
        else:
            warnings.append(f"第 {i} 页没有文字，可能全是图片")
    return blocks


def from_xlsx(path, warnings):
    need("openpyxl", "openpyxl")
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    blocks = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        blocks.append((2, f"工作表：{ws.title}"))
        if not rows:
            warnings.append(f"工作表 {ws.title} 为空")
            continue
        if len(rows) > 200:
            warnings.append(f"工作表 {ws.title} 有 {len(rows)} 行，只提取前 200 行；大表建议作为附件入库")
            rows = rows[:200]
        blocks.append((0, table_md(rows)))
    return blocks


def from_pdf(path, warnings):
    need("pypdf", "pypdf")
    from pypdf import PdfReader
    reader = PdfReader(path)
    blocks, empty = [], []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if not text:
            empty.append(i)
            continue
        blocks.append((2, f"第 {i} 页"))
        blocks.append((0, text))
    if empty:
        warnings.append(f"第 {', '.join(map(str, empty[:10]))}{' 等' if len(empty) > 10 else ''} 页没有文字层，可能是扫描件，需要先 OCR")
    return blocks


def from_text(path, warnings):
    p = Path(path)
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        if p.suffix.lower() == ".csv":
            return [(0, table_md(list(csv.reader(f))))]
        lines = f.read().splitlines()
    blocks, para = [], []
    def flush():
        if para:
            blocks.append((0, "\n".join(para)))
            para.clear()
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            blocks.append((len(m.group(1)), m.group(2).strip()))
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()
    return blocks


EXTRACTORS = {".docx": from_docx, ".pptx": from_pptx, ".xlsx": from_xlsx, ".pdf": from_pdf,
              ".txt": from_text, ".md": from_text, ".csv": from_text}


# ---------- 拆分 ----------

def split_long(text, max_len):
    if len(text) <= max_len or text.startswith("|"):  # 表格不拆
        return [text]
    parts, cur = [], ""
    for s in SENT_SPLIT.split(text):
        if cur and len(cur) + len(s) > max_len:
            parts.append(cur.strip())
            cur = ""
        cur += s
    if cur.strip():
        parts.append(cur.strip())
    return parts


def chunk(blocks, min_len, max_len):
    chunks, path, buf = [], [], []

    def flush():
        text = "\n\n".join(buf).strip()
        buf.clear()
        if not text:
            return
        for piece in split_long(text, max_len):
            chunks.append({"section": " > ".join(path) or "（正文）", "text": piece, "chars": len(piece)})

    for level, text in blocks:
        if level:
            flush()                                   # 遇到标题先把上一节收尾，避免内容挂到错误的章节下
            path[:] = path[:level - 1] + [text]
        else:
            buf.append(text)
            if sum(len(x) for x in buf) >= max_len:
                flush()
    flush()

    # 合并过短的片段到前一个同章节片段
    merged = []
    for c in chunks:
        if merged and c["chars"] < min_len // 3 and merged[-1]["section"] == c["section"] \
                and merged[-1]["chars"] + c["chars"] <= max_len:
            merged[-1]["text"] += "\n\n" + c["text"]
            merged[-1]["chars"] = len(merged[-1]["text"])
        else:
            merged.append(c)
    for i, c in enumerate(merged, 1):
        c["id"] = i
    return merged


def to_markdown(blocks):
    out = []
    for level, text in blocks:
        out.append(("#" * level + " " + text) if level else text)
    return "\n\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="提取文件内容并拆分")
    ap.add_argument("file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chunk", type=int, default=1500)
    ap.add_argument("--min-chunk", type=int, default=300)
    args = ap.parse_args()

    path = Path(args.file)
    ext = path.suffix.lower()
    if ext in (".doc", ".ppt", ".xls"):
        sys.exit(f"{ext} 是旧格式，请在 Office 里另存为 {ext}x 后再上传")
    if ext not in EXTRACTORS:
        sys.exit(f"不支持的格式：{ext}")

    warnings = []
    blocks = EXTRACTORS[ext](str(path), warnings)
    content = to_markdown(blocks)
    plain = re.sub(r"[#|\-\s]", "", content)
    chunks = chunk(blocks, args.min_chunk, args.max_chunk)

    sensitive = {}
    for pat, label in SENSITIVE:
        hits = sorted({m.group(0) for m in pat.finditer(content)})
        if hits:
            sensitive[label] = hits[:10]
    if len(plain) < 100:
        warnings.append(f"提取到的文字只有 {len(plain)} 字，入库后很难被检索到")
    if re.search(r"草稿|draft|个人|temp|测试", path.stem, re.I):
        warnings.append("文件名提示这可能是草稿或个人文件，请确认是否定稿")

    title = next((t for lvl, t in blocks if lvl == 1), None) or next((t for lvl, t in blocks if lvl), None)
    meta = {"file": path.name, "format": ext.lstrip("."), "chars": len(plain),
            "headings": sum(1 for lvl, _ in blocks if lvl), "chunks": len(chunks),
            "suggested_title": title, "sensitive": sensitive, "warnings": warnings}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "content.md").write_text(content, encoding="utf-8")
    (out / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
