"""截图：拿差异的原文回到 PDF 里找位置，截出那一段并把变化的词框出来（代替手工截图）。

用到的库：pdfplumber（读文字和坐标）、pypdfium2（把页面转成图片）、Pillow（画框、裁剪）。
找位置的顺序：整行完全一样 → 包含在某一行里 → 跨 2–4 行拼起来包含。有页码提示时先在那一页找。
找不到、或者找到多处又分不出是哪一处时，不乱框：前者标“截图待补”，后者按顺序推断并写明“请核对”。
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from common import need, norm


class PdfText:
    """一个 PDF 的所有行（文字、页码、坐标、逐词坐标），读一次缓存起来。"""

    def __init__(self, path, cfg: dict):
        self.path = str(path)
        sc = cfg["screenshot"]
        pdfplumber = need("pdfplumber")
        self.lines, self.size = [], {}
        with pdfplumber.open(self.path) as pdf:
            for no, page in enumerate(pdf.pages, 1):
                self.size[no] = (float(page.width), float(page.height))
                words = page.extract_words(x_tolerance=sc["x_tolerance"], y_tolerance=sc["y_tolerance"], keep_blank_chars=False)
                for ws in _group(words, sc["y_tolerance"]):
                    t = " ".join(w["text"] for w in ws)
                    self.lines.append({
                        "page": no, "t": t, "n": norm(t),
                        "bbox": (min(w["x0"] for w in ws), min(w["top"] for w in ws), max(w["x1"] for w in ws), max(w["bottom"] for w in ws)),
                        "words": [(w["text"], w["x0"], w["top"], w["x1"], w["bottom"]) for w in ws],
                    })
        for k, l in enumerate(self.lines):
            l["k"] = k

    def locate(self, text: str, page_hint=None, ratio=None):
        """返回 (行列表, 说明)。行列表为空表示没找到。"""
        t = norm(text)
        if len(t) < 2:
            return [], "文字太短，无法定位"
        pools = []
        if page_hint and any(l["page"] == page_hint for l in self.lines):
            pools.append([l for l in self.lines if l["page"] == page_hint])
        pools.append(self.lines)
        for pool in pools:
            hits = [[l] for l in pool if l["n"] == t] or [[l] for l in pool if t in l["n"]] or _span_hits(pool, t)
            if hits:
                if len(hits) == 1:
                    return hits[0], ""
                if ratio is not None and len(self.lines) > 1:
                    best = min(hits, key=lambda g: abs(g[0]["k"] / (len(self.lines) - 1) - ratio))
                else:
                    best = hits[0]
                return best, f"文件里有 {len(hits)} 处相同内容，按前后顺序推断是第 {hits.index(best) + 1} 处，请核对"
        return [], "在 PDF 里没找到这一行（可能是两边提取文字的方式不同），截图待补"


def _group(words, ytol):
    out = []
    for w in sorted(words, key=lambda w: (round(float(w["top"])), float(w["x0"]))):
        if out and abs(float(w["top"]) - out[-1][0]) <= ytol:
            out[-1][1].append(w)
        else:
            out.append([float(w["top"]), [w]])
    return [sorted(ws, key=lambda w: float(w["x0"])) for _, ws in out]


def _span_hits(pool, t, most=4):
    """他的一行可能是 PDF 里上下几行拼起来的。"""
    hits = []
    for i in range(len(pool)):
        s = pool[i]["n"]
        for j in range(i + 1, min(i + most, len(pool))):
            if pool[j]["page"] != pool[i]["page"]:
                break
            s += pool[j]["n"]
            if t in s:
                hits.append(pool[i:j + 1])
                break
    return hits


def boxes_for(lines, tokens) -> list[tuple]:
    """只框变化的词；一个都对不上时框整行。"""
    want = [norm(x) for x in tokens if norm(x)]
    out = []
    if want:
        for l in lines:
            for txt, x0, y0, x1, y1 in l["words"]:
                n = norm(txt)
                if n and any(n == w or (len(n) >= 2 and (n in w or w in n)) for w in want):
                    out.append((x0, y0, x1, y1))
    if not out:
        out = [l["bbox"] for l in lines]
    return out


def render(pdf_path, jobs: list[dict], cfg: dict) -> None:
    """jobs：[{page, lines, boxes, out}]。截出这几行所在的一段（整页宽），变化处画红框。"""
    if not jobs:
        return
    pdfium = need("pypdfium2")
    from PIL import ImageDraw
    sc = cfg["screenshot"]
    scale, pad = sc["scale"], sc["pad"]
    by_page = defaultdict(list)
    for j in jobs:
        by_page[j["page"]].append(j)
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for no, js in by_page.items():
            page = pdf[no - 1]
            w, h = page.get_size()
            base = page.render(scale=scale).to_pil().convert("RGB")
            page.close()
            for j in js:
                img = base.copy()
                dr = ImageDraw.Draw(img)
                top = max(0, min(l["bbox"][1] for l in j["lines"]) - pad)
                bottom = min(h, max(l["bbox"][3] for l in j["lines"]) + pad)
                for x0, y0, x1, y1 in j["boxes"]:
                    dr.rectangle([(x0 - 2) * scale, (y0 - 2) * scale, (x1 + 2) * scale, (y1 + 2) * scale], outline=(230, 0, 18), width=3)
                Path(j["out"]).parent.mkdir(parents=True, exist_ok=True)
                img.crop((0, int(top * scale), int(w * scale), int(bottom * scale))).save(j["out"])
    finally:
        pdf.close()


def shoot_case(pair: dict, items: list[dict], case_dir: Path, cfg: dict) -> None:
    """给一个 Case 的每条差异截新旧两张图，结果写回 item 的 shot_old / shot_new / shot_note。"""
    max_old = max([i["line_old"] or 0 for i in items] + [1])
    max_new = max([i["line_new"] or 0 for i in items] + [1])
    for side, pdf_key, text_key, page_key, line_key, tok_key, mx in (
            ("old", "baseline", "old", "page_old", "line_old", "tok_old", max_old),
            ("new", "new", "new", "page_new", "line_new", "tok_new", max_new)):
        pdf_path = pair.get(pdf_key)
        for it in items:
            it.setdefault("shot_note", [])
        if not pdf_path or not Path(pdf_path).is_file():
            for it in items:
                it[f"shot_{side}"] = ""
            continue
        doc = PdfText(pdf_path, cfg)
        jobs = []
        for it in items:
            it[f"shot_{side}"] = ""
            it[f"pageno_{side}"] = None
            if not it[text_key]:
                continue                        # 新增 / 删除：这一边本来就没有
            ratio = (it[line_key] / mx) if it.get(line_key) and mx > 1 else None
            lines, note = doc.locate(it[text_key], it.get(page_key), ratio)
            if note:
                it["shot_note"].append(f"{'旧' if side == 'old' else '新'}：{note}")
            if not lines:
                continue
            out = case_dir / "shots" / f"{it['id']}_{side}.png"
            jobs.append({"page": lines[0]["page"], "lines": lines, "boxes": boxes_for(lines, it[tok_key]), "out": str(out)})
            it[f"shot_{side}"] = str(out)
            it[f"pageno_{side}"] = lines[0]["page"]
        render(pdf_path, jobs, cfg)
