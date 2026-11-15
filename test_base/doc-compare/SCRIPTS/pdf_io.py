"""读 PDF：文字和坐标、扫描页、截图识别结果、第二种方式复读数字、差异处截图（打码）。

用到的库（pip install -r requirements.txt）：
- pdfplumber（MIT）：逐字读取文字和坐标；
- pypdfium2（Apache-2.0 / BSD，随 pdfplumber 安装）：把页面转成图片，以及第二种方式读文字（复读核对）；
- Pillow：画框、打码、裁剪。
不用 PyMuPDF（AGPL 许可，公司内使用要法务确认）。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from dc_core import normalize, numbers

IO_DEFAULTS = {
    "min_chars_per_page": 20,      # 少于这么多字的页当作“没有文字层”（扫描页）
    "big_image_ratio": 0.5,        # 图片占页面一半以上、文字又少的页，提醒“图里的文字没有比较”
    "x_tolerance": 1.5,
    "y_tolerance": 3,
    "header_band": 0.08,           # 页面上下各 8% 的范围内找页眉页脚
    "header_min_ratio": 0.5,       # 一半以上的页都出现，才当作页眉页脚去掉
    "header_patterns": [],         # 另外指定要去掉的行（正则），读 txt 时只能靠它
    "render_dpi": 200,             # 扫描页转图片的清晰度（交给「识别截图.bat」）
    "snapshot_scale": 2,           # 差异截图的放大倍数
    "snapshot_pad": 36,            # 差异上下各留多少空白（单位：pt，约 1.3 cm）
    "mask_snapshots": True,        # 差异截图打码（人名清单、证件号、电话、邮箱、卡号）
    "mask_patterns": [
        r"[A-Z]{1,2}\d{6}\(?[0-9A]\)?",                   # 香港身份证
        r"[\w.+-]+@[\w-]+\.[\w.]+",                        # 邮箱
        r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)",            # 卡号
        r"(?<![\d.])(?:\+?852[ -]?)?[2-9]\d{3}[ -]?\d{4}(?![\d.])",  # 电话
    ],
}

CJK = re.compile(r"[㐀-鿿豈-﫿]")


def need(mod: str):
    try:
        return __import__(mod)
    except ImportError:
        raise SystemExit(f"缺少 {mod}，请先运行：pip install -r requirements.txt")


def page_image_name(pdf_path, page_no: int) -> str:
    """扫描页图片的文件名。带上所在文件夹名：baseline 和新文件同名时也不会互相覆盖。"""
    p = Path(pdf_path).resolve()
    return f"{p.parent.name}_{p.stem}_p{page_no:03d}.png"


# ---------------------------------------------------------------- 读取

def read_doc(path, cfg: dict, ocr_index: dict | None = None) -> dict:
    """返回 {file, name, pages: [{page, w, h, text, ocr, big_image}], lines: [...]}。"""
    cfg = {**IO_DEFAULTS, **cfg}
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return _read_txt(p, cfg)
    pdfplumber = need("pdfplumber")
    pages, lines = [], []
    with pdfplumber.open(str(p)) as pdf:
        for no, page in enumerate(pdf.pages, 1):
            w, h = float(page.width), float(page.height)
            info = {"page": no, "w": w, "h": h, "text": True, "ocr": False, "big_image": False}
            pages.append(info)
            nchars = len(page.chars)
            img_area = sum(max(0.0, float(i["x1"]) - float(i["x0"])) * max(0.0, float(i["bottom"]) - float(i["top"])) for i in page.images)
            if nchars < cfg["min_chars_per_page"]:
                info["text"] = False
                rec = (ocr_index or {}).get(page_image_name(p, no).lower())
                if rec:
                    info["ocr"] = True
                    lines += _ocr_lines(rec, no, w)
                continue
            if img_area > w * h * cfg["big_image_ratio"] and nchars < 200:
                info["big_image"] = True
            words = page.extract_words(x_tolerance=cfg["x_tolerance"], y_tolerance=cfg["y_tolerance"],
                                       keep_blank_chars=False, extra_attrs=["size"])
            for ws in _group(words, cfg["y_tolerance"]):
                lines.append({
                    "t": " ".join(x["text"] for x in ws), "page": no, "src": "text",
                    "bbox": [round(min(x["x0"] for x in ws), 1), round(min(x["top"] for x in ws), 1),
                             round(max(x["x1"] for x in ws), 1), round(max(x["bottom"] for x in ws), 1)],
                    "size": round(max(float(x.get("size") or 0) for x in ws), 1),
                    "words": [[x["text"], round(x["x0"], 1), round(x["top"], 1), round(x["x1"], 1), round(x["bottom"], 1)] for x in ws],
                })
    for k, l in enumerate(lines, 1):
        l["no"] = k
        l["n"] = normalize(l["t"], cfg)
    mark_header_footer(lines, pages, cfg)
    return {"file": str(p), "name": p.name, "pages": pages, "lines": lines}


def _read_txt(p: Path, cfg: dict) -> dict:
    """已经提取好的文字（一行一条）。行号保持原文件的行号，空行不参与比较。"""
    lines = []
    for k, t in enumerate(p.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        if t.strip():
            lines.append({"t": t, "no": k, "page": None, "bbox": None, "src": "text", "words": [], "n": normalize(t, cfg)})
    mark_header_footer(lines, [], cfg)
    return {"file": str(p), "name": p.name, "pages": [], "lines": lines}


def _group(words, ytol):
    """词按位置排成行：上下位置相差不超过 ytol 的算同一行，行内从左到右。"""
    out = []
    for w in sorted(words, key=lambda w: (round(float(w["top"])), float(w["x0"]))):
        if out and abs(float(w["top"]) - out[-1][0]) <= ytol:
            out[-1][1].append(w)
        else:
            out.append([float(w["top"]), [w]])
    return [sorted(ws, key=lambda w: float(w["x0"])) for _, ws in out]


def mark_header_footer(lines, pages, cfg) -> None:
    """每页重复出现的页眉、页脚、页码标为 hf，不参与比较（数字不同也算同一个页眉，例如页码）。"""
    pats = [re.compile(x) for x in cfg.get("header_patterns") or []]
    for l in lines:
        if any(x.search(l["n"]) for x in pats):
            l["hf"] = True
    text_pages = [p for p in pages if p["text"]]
    if len(text_pages) < 3:
        return
    hgt = {p["page"]: p["h"] for p in pages}
    band = cfg["header_band"]
    seen = defaultdict(set)
    keyed = []
    for l in lines:
        if l.get("src") != "text" or not l.get("bbox"):
            continue
        h = hgt[l["page"]]
        if l["bbox"][1] < h * band or l["bbox"][3] > h * (1 - band):
            k = re.sub(r"\d+", "#", l["n"])
            seen[k].add(l["page"])
            keyed.append((l, k))
    need_pages = max(3, cfg["header_min_ratio"] * len(text_pages))
    for l, k in keyed:
        if len(seen[k]) >= need_pages:
            l["hf"] = True


# ---------------------------------------------------------------- 扫描页：用「识别截图.bat」识别

def render_pages(pdf_path, page_nos: list[int], out_dir, dpi: int) -> list[Path]:
    """把指定页转成图片，交给「识别截图.bat」识别（Windows 自带识别，不安装软件、不出本机）。"""
    pdfium = need("pypdfium2")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    files = []
    try:
        for no in page_nos:
            page = pdf[no - 1]
            img = page.render(scale=dpi / 72).to_pil()
            page.close()
            f = out / page_image_name(pdf_path, no)
            img.save(f)
            files.append(f)
    finally:
        pdf.close()
    return files


def load_ocr(paths) -> dict:
    """读「识别截图.bat」生成的 截图识别结果.ocr.json，按图片文件名（小写）索引。"""
    idx = {}
    for p in paths or []:
        data = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        if data.get("tool") != "ta-ocr":
            raise SystemExit(f"{p} 不是「识别截图.bat」生成的识别结果文件")
        for im in data.get("images") or []:
            if im.get("langs"):
                idx[re.split(r"[\\/]", im.get("name") or "")[-1].lower()] = im
    return idx


def _ocr_lines(rec, page_no, page_w):
    """识别结果 → 行。英文结果为主；含中文的行用中文结果替换同一位置的英文结果。坐标换算成 pt。"""
    langs = rec.get("langs") or []
    en = next((l for l in langs if (l.get("lang") or "").lower().startswith("en")), None)
    zh = next((l for l in langs if (l.get("lang") or "").lower().startswith("zh")), None)
    base = list((en or (langs[0] if langs else {})).get("lines") or [])
    if zh and zh is not en:
        for z in zh.get("lines") or []:
            if not CJK.search(z.get("t") or ""):
                continue
            zy, zh_ = z["b"][1], z["b"][3]
            base = [e for e in base if not (min(zy + zh_, e["b"][1] + e["b"][3]) - max(zy, e["b"][1]) > 0.5 * min(zh_, e["b"][3]))]
            base.append(z)
    s = page_w / float(rec.get("w") or page_w)
    out = []
    for l in sorted(base, key=lambda l: (l["b"][1], l["b"][0])):
        t = re.sub(r"(?<=[㐀-鿿]) (?=[㐀-鿿])", "", l.get("t") or "")
        x, y, w, h = l["b"]
        out.append({"t": t, "page": page_no, "src": "ocr", "size": 0,
                    "bbox": [round(x * s, 1), round(y * s, 1), round((x + w) * s, 1), round((y + h) * s, 1)],
                    "words": [[wt, round(wx * s, 1), round(wy * s, 1), round((wx + ww) * s, 1), round((wy + wh) * s, 1)]
                              for wt, wx, wy, ww, wh in l.get("w") or []]})
    return out


# ---------------------------------------------------------------- 第二种方式复读数字

def second_read(pdf_path, refs: list[tuple[int, list]], cfg: dict) -> list[str | None]:
    """用 PDFium（与 pdfplumber 不同的读取引擎）重新读出每个位置的文字。refs：[(页码, bbox)]。"""
    pdfium = need("pypdfium2")
    pdf = pdfium.PdfDocument(str(pdf_path))
    cache, out = {}, []
    try:
        for no, bbox in refs:
            if no not in cache:
                page = pdf[no - 1]
                cache[no] = (page, page.get_textpage(), page.get_size()[1])
            _, tp, h = cache[no]
            x0, top, x1, bottom = bbox
            out.append(tp.get_text_bounded(left=x0 - 0.5, bottom=h - bottom - 0.5, right=x1 + 0.5, top=h - top + 0.5))
    finally:
        for page, tp, _ in cache.values():
            tp.close()
            page.close()
        pdf.close()
    return out


def verify(doc_a: dict, doc_b: dict, items: list[dict], cfg: dict) -> dict:
    """真实差异、不确定、已忽略里含数字的行，用第二种方式复读。数字读出来不一样的，标出来交给人看。

    复读不一致超过一半时，多半是两种引擎的坐标不一致（PDF 页面框特殊），这时不采用复读结果，只给出提示。
    """
    jobs = {"a": [], "b": []}
    for it in items:
        if it["status"] == "layout":
            continue
        for side, refs, texts in (("a", it["a"], it["old"]), ("b", it["b"], it["new"])):
            for r, t in zip(refs, texts):
                if r["src"] == "text" and r.get("page") and r.get("bbox") and numbers(t, cfg):
                    jobs[side].append((it, r, t))
    checked = bad = 0
    found = []
    for side, doc in (("a", doc_a), ("b", doc_b)):
        if not jobs[side] or not str(doc["file"]).lower().endswith(".pdf"):
            continue
        again = second_read(doc["file"], [(r["page"], r["bbox"]) for _, r, _ in jobs[side]], cfg)
        for (it, r, t), t2 in zip(jobs[side], again):
            checked += 1
            n1 = numbers(t, cfg)
            # 复读的范围可能多带进相邻的字，只要求第一次读到的数字按顺序都在复读结果里
            n2 = numbers(t2 or "", cfg)
            if not _subseq(n1, n2):
                bad += 1
                found.append((it, side, r, t, t2))
    if checked and bad > checked / 2:
        return {"checked": checked, "mismatch": bad, "used": False,
                "note": "两种方式读出的位置对不上（多为 PDF 页面框特殊），本次没有采用复读结果，请抽查截图"}
    for it, side, r, t, t2 in found:
        it.setdefault("verify", []).append({"side": side, "no": r["no"], "first": t, "second": (t2 or "").strip()})
        if "复读不一致" not in it["flags"]:
            it["flags"].append("复读不一致")
        note = "两种方式读出的数字不一样，请看截图核对"
        it["reason"] = (it["reason"] + "；" if it["reason"] else "") + note
        if it["status"] == "ignored":
            it["status"] = "unsure"
    return {"checked": checked, "mismatch": bad, "used": True}


def _subseq(small, big):
    it = iter(big)
    return all(x in it for x in small)


# ---------------------------------------------------------------- 差异截图

def snapshots(doc: dict, jobs: list[dict], cfg: dict, mask_text) -> None:
    """jobs：[{page, boxes: [bbox...], color: (r,g,b), out: 路径}]。每张图是这一页上差异所在的一段，差异处画框。

    打码：这一段里命中人名清单或证件号、电话、邮箱、卡号的词涂黑（mask_text(词) 返回 True 表示要打码）。
    """
    if not jobs or not str(doc["file"]).lower().endswith(".pdf"):
        return
    pdfium = need("pypdfium2")
    from PIL import ImageDraw
    cfg = {**IO_DEFAULTS, **cfg}
    scale, pad = cfg["snapshot_scale"], cfg["snapshot_pad"]
    words_on = defaultdict(list)
    for l in doc["lines"]:
        if l.get("page"):
            words_on[l["page"]] += l.get("words") or []
    by_page = defaultdict(list)
    for j in jobs:
        by_page[j["page"]].append(j)
    pdf = pdfium.PdfDocument(str(doc["file"]))
    try:
        for no, js in by_page.items():
            page = pdf[no - 1]
            w, h = page.get_size()
            base = page.render(scale=scale).to_pil().convert("RGB")
            page.close()
            for j in js:
                img = base.copy()
                dr = ImageDraw.Draw(img)
                top = max(0, min(b[1] for b in j["boxes"]) - pad)
                bottom = min(h, max(b[3] for b in j["boxes"]) + pad)
                if cfg["mask_snapshots"]:
                    for t, x0, y0, x1, y1 in words_on[no]:
                        if y1 >= top and y0 <= bottom and mask_text(t):
                            dr.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], fill=(0, 0, 0))
                for x0, y0, x1, y1 in j["boxes"]:
                    dr.rectangle([(x0 - 2) * scale, (y0 - 2) * scale, (x1 + 2) * scale, (y1 + 2) * scale], outline=j["color"], width=3)
                Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
                img.crop((0, int(top * scale), int(w * scale), int(bottom * scale))).save(j["out"])
    finally:
        pdf.close()
