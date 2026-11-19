"""读差异：从他的 difference / total 页面里取出“哪一行、原来是什么、现在是什么”。值原样照抄，不做加工。

支持三种格式（config 里 difference.format）：
- htmldiff：Python difflib.HtmlDiff 生成的左右对照表（auto 时检测到 diff_header 就用它）；
- lines：一行旧值、一行新值的文字（例如 “- 旧” “+ 新”），用 old_line / new_line 两个正则识别；
- custom：自己写一个 .py，里面有 parse(path) -> list[dict]，dict 至少有 old、new 两个键。
"""
from __future__ import annotations

import difflib
import importlib.util
import re
from html.parser import HTMLParser
from pathlib import Path

from common import clean, norm, read_text_any

MARKS = ("diff_add", "diff_chg", "diff_sub")
LABEL = re.compile(r"^\s*(.{1,60}?)\s*[:：]\s*\S")


class _HtmlDiff(HTMLParser):
    """把 difflib.HtmlDiff 的表格读成行：每行 [左行号, 左文字, 左有没有标记, 右行号, 右文字, 右有没有标记]。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self.skip = 0
        self.depth = 0
        self.row = None
        self.cell = None
        self.span = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self.skip or self.cell is not None or (a.get("summary") or "").lower() == "legends":
                self.skip += 1          # 图例表、嵌套表不读
                return
            self.tables.append({"desc": [], "rows": []})
            return
        if self.skip or not self.tables:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"tag": tag, "cls": a.get("class") or "", "text": "", "mark": False, "marked": ""}
        elif tag == "span" and self.cell is not None:
            if any(m in (a.get("class") or "") for m in MARKS):
                self.cell["mark"] = True
                self.span += 1
            elif self.span:
                self.span += 1
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += " "

    def handle_endtag(self, tag):
        if tag == "table" and self.skip:
            self.skip -= 1
            return
        if self.skip or not self.tables:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(self.cell)
            self.cell = None
            self.span = 0
        elif tag == "span" and self.span:
            self.span -= 1
        elif tag == "tr" and self.row is not None:
            row, self.row = self.row, None
            if row and all(c["tag"] == "th" for c in row):
                self.tables[-1]["desc"] += [clean(c["text"]) for c in row if clean(c["text"])]
                return
            tds = [c for c in row if c["tag"] == "td"]
            if len(tds) >= 6 and "diff_header" in tds[1]["cls"] and "diff_header" in tds[4]["cls"]:
                self.tables[-1]["rows"].append([
                    clean(tds[1]["text"]), tds[2]["text"].replace("\u00a0", " "), tds[2]["mark"],
                    clean(tds[4]["text"]), tds[5]["text"].replace("\u00a0", " "), tds[5]["mark"],
                ])

    def handle_data(self, data):
        if self.skip or self.cell is None:
            return
        self.cell["text"] += data
        if self.span:
            self.cell["marked"] += data


def _page_hint(desc: list[str], side: int) -> int | None:
    """表头是 page0、第 3 页 这类写法时，拿来当页码提示（page0 → 第 1 页）。"""
    if len(desc) <= side:
        return None
    t = desc[side]
    m = re.search(r"page\s*_?(\d+)", t, re.I)
    if m:
        return int(m.group(1)) + 1
    m = re.search(r"第\s*(\d+)\s*页", t)
    return int(m.group(1)) if m else None


def parse_htmldiff(text: str) -> list[dict]:
    p = _HtmlDiff()
    p.feed(text)
    items = []
    for ti, t in enumerate(p.tables):
        # 先把折行拼回去（行号是 “>” 的是上一行的续行；变化可能只在续行里），再挑出有变化的行
        rows = []
        for ln_a, ta, ma, ln_b, tb, mb in t["rows"]:
            if rows and (ln_a == ">" or ln_b == ">"):
                r = rows[-1]
                if ln_a == ">":
                    r[1] += ta
                    r[2] = r[2] or ma
                if ln_b == ">":
                    r[4] += tb
                    r[5] = r[5] or mb
                continue
            rows.append([ln_a, ta, ma, ln_b, tb, mb])
        for ln_a, ta, ma, ln_b, tb, mb in rows:
            if not (ma or mb):
                continue
            items.append({"old": ta.strip(), "new": tb.strip(),
                          "line_old": _int(ln_a), "line_new": _int(ln_b),
                          "page_old": _page_hint(t["desc"], 0), "page_new": _page_hint(t["desc"], 1),
                          "table": ti + 1})
    return items


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


class _Text(HTMLParser):
    """html → 按行的纯文字（br、p、div、tr、li 换行）。"""
    BREAK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "pre", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in self.BREAK:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag in self.BREAK or tag in ("td", "th"):
            self.buf.append("\n" if tag not in ("td", "th") else "\t")

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def text_lines(text: str, is_html: bool) -> list[str]:
    if is_html:
        p = _Text()
        p.feed(text)
        text = "".join(p.buf)
    return [l.replace("\u00a0", " ").rstrip() for l in text.splitlines() if l.strip()]


def parse_lines(lines: list[str], old_re: str, new_re: str) -> list[dict]:
    ro, rn = re.compile(old_re), re.compile(new_re)
    items, pend = [], None
    for k, l in enumerate(lines, 1):
        mo, mn = ro.match(l), rn.match(l)
        if mo and not mn:
            if pend is not None:
                items.append({"old": pend[1], "new": "", "line_old": pend[0], "line_new": None})
            pend = (k, mo.group(1).strip())
        elif mn:
            old = pend[1] if pend else ""
            items.append({"old": old, "new": mn.group(1).strip(), "line_old": pend[0] if pend else None, "line_new": k})
            pend = None
    if pend is not None:
        items.append({"old": pend[1], "new": "", "line_old": pend[0], "line_new": None})
    for it in items:
        it.update(page_old=None, page_new=None)
    return items


def detect(text: str) -> str:
    return "htmldiff" if "diff_header" in text else "lines"


def parse(path, cfg: dict) -> tuple[list[dict], str]:
    dc = cfg["difference"]
    fmt = dc["format"]
    if fmt == "custom":
        f = Path(dc["custom_parser"])
        spec = importlib.util.spec_from_file_location("custom_parser", str(f))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        items = [dict({"line_old": None, "line_new": None, "page_old": None, "page_new": None}, **x) for x in mod.parse(str(path))]
        return finish(items, cfg), "custom"
    text = read_text_any(path)
    if fmt == "auto":
        fmt = detect(text)
    if fmt == "htmldiff":
        items = parse_htmldiff(text)
    else:
        is_html = bool(re.search(r"<(html|body|table|div|p|br)\b", text[:5000], re.I))
        items = parse_lines(text_lines(text, is_html), dc["old_line"], dc["new_line"])
    return finish(items, cfg), fmt


# ---------------------------------------------------------------- 字段名、变化的部分

def field_of(old: str, new: str) -> str:
    """字段名取冒号前面的标签（两边一致时）；没有标签就留空，交付物里显示行号。"""
    la, lb = LABEL.match(old or ""), LABEL.match(new or "")
    # 标签里要有字母或汉字，避免把 10:30 这种时间当成字段名
    la = la if la and re.search(r"[A-Za-z㐀-鿿]", la.group(1)) else None
    lb = lb if lb and re.search(r"[A-Za-z㐀-鿿]", lb.group(1)) else None
    if la and lb and norm(la.group(1)) == norm(lb.group(1)):
        return la.group(1).strip()
    return (la or lb).group(1).strip() if (la or lb) else ""


def segments(old: str, new: str) -> tuple[list[tuple[str, bool]], list[tuple[str, bool]], list[str], list[str]]:
    """按词对比：返回 旧值分段、新值分段（(文字, 是否变化)），以及两边变化的词，用于截图时只框变化的词。"""
    ta, tb = re.findall(r"\S+|\s+", old or ""), re.findall(r"\S+|\s+", new or "")
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    sa, sb, ca, cb = [], [], [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        a, b = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        ch = op != "equal"
        if a:
            sa.append((a, ch and bool(a.strip())))
            if ch:
                ca += [x for x in ta[i1:i2] if x.strip()]
        if b:
            sb.append((b, ch and bool(b.strip())))
            if ch:
                cb += [x for x in tb[j1:j2] if x.strip()]
    return sa, sb, ca, cb


def change_text(sa, sb) -> str:
    """一句话说明变化：587.85 → 600.00；多处变化用 ； 隔开。"""
    a = [t.strip() for t, ch in sa if ch]
    b = [t.strip() for t, ch in sb if ch]
    if not a and not b:
        return ""
    if len(a) == len(b):
        return "；".join(f"{x} → {y}" for x, y in zip(a, b))
    return f"{' '.join(a) or '（无）'} → {' '.join(b) or '（无）'}"


def finish(items: list[dict], cfg: dict) -> list[dict]:
    out = []
    for it in items:
        it["old"], it["new"] = (it.get("old") or "").strip(), (it.get("new") or "").strip()
        if not it["old"] and not it["new"]:
            continue
        it["space_only"] = bool(it["old"] and it["new"] and norm(it["old"]) == norm(it["new"]))
        sa, sb, ca, cb = segments(it["old"], it["new"])
        it.update(seg_old=sa, seg_new=sb, tok_old=ca, tok_new=cb,
                  field=it.get("field") or field_of(it["old"], it["new"]),
                  change=change_text(sa, sb),
                  kind="新增" if not it["old"] else "删除" if not it["new"] else "修改")
        out.append(it)
    for k, it in enumerate(out, 1):
        it["id"] = f"D{k:03d}"
    return out


def inspect_file(path, cfg: dict) -> str:
    """诊断：看看他的文件是什么格式、能读出多少条。输出贴给我就能对着调整。"""
    text = read_text_any(path)
    fmt = detect(text) if cfg["difference"]["format"] == "auto" else cfg["difference"]["format"]
    rep = [f"文件：{path}", f"大小：{len(text)} 字符", f"识别为：{fmt}"]
    rep.append("含有 difflib 表格标记（diff_header）：" + ("是" if "diff_header" in text else "否"))
    rep.append(f"<table> 个数：{len(re.findall(r'<table', text, re.I))}，<tr> 个数：{len(re.findall(r'<tr', text, re.I))}")
    classes = sorted(set(re.findall(r'class="([^"]+)"', text)))[:30]
    rep.append("出现的 class：" + ", ".join(classes))
    if fmt in ("htmldiff", "lines", "custom"):
        try:
            items, used = parse(path, cfg)
            rep.append(f"按 {used} 读出差异：{len(items)} 条（其中只差空格 {sum(1 for i in items if i['space_only'])} 条）")
            for it in items[:8]:
                rep.append(f"  {it['id']} 行 {it['line_old']}/{it['line_new']} 页 {it['page_old']}/{it['page_new']} "
                           f"字段「{it['field']}」 {it['old'][:60]!r} → {it['new'][:60]!r}")
        except Exception as e:
            rep.append(f"读取出错：{type(e).__name__}: {e}")
    if fmt != "htmldiff":
        is_html = bool(re.search(r"<(html|body|table|div|p|br)\b", text[:5000], re.I))
        lines = text_lines(text, is_html)
        rep.append(f"纯文字共 {len(lines)} 行，前 40 行：")
        rep += ["  | " + l[:140] for l in lines[:40]]
    return "\n".join(rep)
