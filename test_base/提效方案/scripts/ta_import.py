"""读取执行结果：网页报告（.html / .mhtml，含内嵌截图）、JSON（平台导出、SDK 接口、Allure）、JUnit XML、CSV / 制表符表格。

只用 Python 自带的库。返回统一的“表格”：{kind, tables: [{path, rows: [{列名: 值}]}], images: {"img#1": (mime, bytes)}}，
再按字段对应（mapping）变成用例（ta_engine.to_cases）。
截图：网页里直接嵌入的截图（data:image）和 MHTML 里的截图取出来单独保存，表格里只留编号 img#k；网络地址、文件路径保留原样。
"""
from __future__ import annotations

import base64
import binascii
import json
import quopri
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

# ---------------------------------------------------------------- 字段

FIELDS = [
    {"key": "id", "name": "用例编号", "req": True, "guess": ["caseid", "case_id", "case id", "标识", "用例编号", "用例id", "案例编号", "案例id", "testcaseid", "编号", "id", "historyid"]},
    {"key": "name", "name": "用例名称", "guess": ["casename", "用例名称", "案例名称", "用例标题", "案例标题", "用例描述", "案例描述", "名称", "testname", "name", "title", "标题", "fullname", "scenario", "场景", "用例", "案例"]},
    {"key": "result", "name": "执行结果", "req": True, "guess": ["result", "结果", "status", "状态", "执行结果", "outcome"]},
    {"key": "error", "name": "报错信息", "guess": ["message", "errormessage", "error", "失败原因", "错误信息", "报错", "异常信息", "reason", "statusdetails.message", "failure"]},
    {"key": "stack", "name": "堆栈/日志", "guess": ["trace", "stacktrace", "stack", "堆栈", "详细日志", "日志", "log", "statusdetails.trace", "system-out", "detail"]},
    {"key": "exceptionRaw", "name": "异常类型", "guess": ["exception", "exceptiontype", "异常类型", "type", "errortype"]},
    {"key": "pageText", "name": "页面/弹窗文字", "guess": ["pagetext", "alerttext", "弹窗", "页面提示", "dialog", "popup", "toast"]},
    {"key": "screenshot", "name": "截图", "guess": ["screenshot", "截图", "attachments", "image", "picture", "img"]},
    {"key": "start", "name": "开始时间", "guess": ["starttime", "start", "开始时间", "执行时间", "time", "date"]},
    {"key": "duration", "name": "耗时", "guess": ["duration", "耗时", "time(s)", "duration(ms)", "elapsed"]},
    {"key": "module", "name": "模块/套件", "guess": ["module", "模块", "suite", "套件", "feature", "classname", "目录", "path"]},
    {"key": "device", "name": "执行设备", "guess": ["device", "设备", "执行设备", "browser", "浏览器", "platform"]},
]
CN_WORD = re.compile(r"^[一-鿿]{2,}$")


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]", "", str(s).lower())


def guess_mapping(cols: list[str], saved: dict | None = None) -> dict:
    """按列名猜字段对应；上次导入时确认过的对应优先。"""
    m = {}
    for f in FIELDS:
        if saved and saved.get(f["key"]) in cols:
            m[f["key"]] = saved[f["key"]]
            continue
        for g in f["guess"]:
            cn, n = bool(CN_WORD.match(g)), len(_norm(g))
            hit = next((c for c in cols if _norm(c) == _norm(g)), None) \
                or next((c for c in cols if _norm(c).endswith(_norm(g)) and (n > 3 or (cn and n >= 2 and len(_norm(c)) <= 6))), None) \
                or next((c for c in cols if _norm(g) in _norm(c) and (n > 4 or (cn and n >= 3))), None)
            if hit and hit not in m.values():
                m[f["key"]] = hit
                break
    return m


def columns_of(rows: list[dict]) -> list[str]:
    out = []
    for r in rows[:200]:
        for k in r:
            if k not in out:
                out.append(k)
    return out


# ---------------------------------------------------------------- 文字编码

def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# ---------------------------------------------------------------- 表格文字（CSV / 制表符）

def parse_delimited(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0].rstrip("\r")
    delim = "\t" if first.count("\t") > first.count(",") else (";" if first.count(";") > first.count(",") else ",")
    rows, row, cell, q, i, n = [], [], [], False, 0, len(text)
    while i < n:
        ch = text[i]
        if q:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    cell.append('"')
                    i += 1
                else:
                    q = False
            else:
                cell.append(ch)
        elif ch == '"' and not cell:
            q = True
        elif ch == delim:
            row.append("".join(cell))
            cell = []
        elif ch in "\r\n":
            if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 1
            row.append("".join(cell))
            rows.append(row)
            row, cell = [], []
        else:
            cell.append(ch)
        i += 1
    if cell or row:
        row.append("".join(cell))
        rows.append(row)
    rows = [r for r in rows if any(x.strip() for x in r)]
    if len(rows) < 2:
        return []
    head = [h.strip() or "列" + str(i + 1) for i, h in enumerate(rows[0])]
    return [{h: (r[i] if i < len(r) else "").strip() for i, h in enumerate(head)} for r in rows[1:]]


# ---------------------------------------------------------------- JSON / Allure

def flatten(obj, pre="", out=None) -> dict:
    out = {} if out is None else out
    if obj is None:
        return out
    if isinstance(obj, list):
        if all(x is None or not isinstance(x, (dict, list)) for x in obj):
            out[pre] = "; ".join("" if x is None else _js_str(x) for x in obj)
        elif re.search(r"attach|screenshot|截图|image", pre, re.I):
            out[pre] = "; ".join(_js_str(x.get("source") or x.get("path") or x.get("url") or x.get("name") or "") for x in obj if isinstance(x, dict) and (x.get("source") or x.get("path") or x.get("url") or x.get("name")))
        elif 0 < len(obj) <= 5:
            for i, x in enumerate(obj):
                flatten(x, pre + "[" + str(i) + "]", out)
        else:
            out[pre] = "[" + str(len(obj)) + " 项]"
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, pre + "." + k if pre else k, out)
        return out
    out[pre] = _js_str(obj)
    return out


def _js_str(x) -> str:
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def find_arrays(obj, path="", acc=None) -> list:
    acc = [] if acc is None else acc
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            acc.append({"path": path or "(根)", "arr": obj})
        for i, x in enumerate(obj[:50]):
            if isinstance(x, (dict, list)):
                find_arrays(x, path + "[" + str(i) + "]", acc)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_arrays(v, path + "." + k if path else k, acc)
    return acc


def is_allure(o) -> bool:
    return isinstance(o, dict) and "status" in o and ("uuid" in o or "historyId" in o) and "name" in o


def allure_row(o) -> dict:
    sd = o.get("statusDetails") or {}
    labels = {}
    for l in o.get("labels") or []:
        labels[l.get("name")] = (labels[l["name"]] + "," if l.get("name") in labels else "") + _js_str(l.get("value", ""))
    atts = []

    def walk(s):
        for a in s.get("attachments") or []:
            atts.append(a.get("source") or a.get("name") or "")
        for st in s.get("steps") or []:
            walk(st)
    walk(o)
    iso = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (ms % 1000) if ms else ""
    return {
        "name": o.get("name") or "", "fullName": o.get("fullName") or "", "testCaseId": o.get("testCaseId") or o.get("historyId") or "",
        "status": o.get("status") or "", "message": sd.get("message") or "", "trace": sd.get("trace") or "",
        "start": iso(o["start"]) if o.get("start") else "", "duration(ms)": str(o["stop"] - o["start"]) if o.get("start") and o.get("stop") else "",
        "suite": labels.get("suite") or labels.get("parentSuite") or "", "feature": labels.get("feature") or "", "attachments": "; ".join(a for a in atts if a),
    }


# ---------------------------------------------------------------- JUnit XML

def parse_junit(text: str) -> list[dict]:
    try:
        root = ET.fromstring(text.lstrip("﻿").encode("utf-8"))
    except ET.ParseError as e:
        raise ValueError("XML 格式不正确（" + str(e) + "）")
    parent = {ch: p for p in root.iter() for ch in p}
    rows = []
    for tc in root.iter("testcase"):
        f = tc.find("failure")
        if f is None:
            f = tc.find("error")
        sk, out = tc.find("skipped"), tc.find("system-out")
        suite = parent.get(tc)
        rows.append({
            "name": tc.get("name") or "", "classname": tc.get("classname") or "", "suite": (suite.get("name") if suite is not None else "") or "",
            "status": ("error" if f.tag == "error" else "failed") if f is not None else ("skipped" if sk is not None else "passed"),
            "message": (f.get("message") or "") if f is not None else "", "type": (f.get("type") or "") if f is not None else "",
            "trace": "".join(f.itertext()).strip() if f is not None else "", "time(s)": tc.get("time") or "",
            "system-out": "".join(out.itertext()).strip()[:4000] if out is not None else "",
        })
    return rows


# ---------------------------------------------------------------- MHTML

def parse_mhtml(text: str):
    bm = re.search(r'boundary="?([^";\r\n]+)"?', text, re.I)
    if not bm:
        raise ValueError("MHTML 文件格式不正确（没有找到分段标记）")
    html, res = "", {}
    for p in text.split("--" + bm.group(1))[1:]:
        sp = re.search(r"\r?\n\r?\n", p)
        if not sp:
            continue
        head, body = p[:sp.start()], p[sp.end():]
        h = lambda k: (re.search(r"^" + k + r":\s*(.+)$", head, re.I | re.M) or [None, ""])[1]
        typ = h("Content-Type").split(";")[0].strip().lower()
        enc = h("Content-Transfer-Encoding").strip().lower()
        loc, cid = h("Content-Location").strip(), h("Content-ID").replace("<", "").replace(">", "").strip()
        if typ == "text/html" and not html:
            if enc == "quoted-printable":
                html = quopri.decodestring(body.encode("latin-1", "replace")).decode("utf-8", "replace")
            elif enc == "base64":
                html = base64.b64decode(re.sub(r"\s+", "", body)).decode("utf-8", "replace")
            else:
                html = body
        elif typ.startswith("image/") and enc == "base64":
            try:
                img = (typ, base64.b64decode(re.sub(r"\s+", "", body)))
            except (binascii.Error, ValueError):
                continue
            if loc:
                res[loc] = img
            if cid:
                res["cid:" + cid] = img
    if not html:
        raise ValueError("MHTML 文件里没有找到网页内容")
    return html, res


# ---------------------------------------------------------------- HTML（简单的文档树，够解析表格用）

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "li", "pre", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
# 遇到这些开始标签时，自动结束同一层还没结束的同类标签（HTML 允许省略结束标签）
AUTO_CLOSE = {"td": ({"td", "th"}, {"tr", "table"}), "th": ({"td", "th"}, {"tr", "table"}),
              "tr": ({"tr", "td", "th"}, {"table", "tbody", "thead", "tfoot"}),
              "tbody": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}), "thead": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}),
              "tfoot": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}), "li": ({"li"}, {"ul", "ol"}), "p": ({"p"}, {"div", "td", "th", "li", "body"})}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None, text=None):
        self.tag, self.attrs, self.children, self.parent, self.text = tag, attrs or {}, [], parent, text

    def iter(self, tag=None):
        for ch in self.children:
            if ch.tag is None:
                continue
            if tag is None or ch.tag == tag:
                yield ch
            yield from ch.iter(tag)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in AUTO_CLOSE:
            same, stop = AUTO_CLOSE[tag]
            for i in range(len(self.stack) - 1, 0, -1):
                t = self.stack[i].tag
                if t in stop:
                    break
                if t in same:
                    del self.stack[i:]
                    break
        n = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        n = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(n)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
            if tag in ("tr", "td", "th") and self.stack[i].tag == "table":
                return  # 不越过所在表格去结束外层的行或单元格

    def handle_data(self, data):
        self.stack[-1].children.append(Node(None, None, self.stack[-1], data))


def cell_text(el: Node) -> str:
    """单元格文字，保留换行（日志、Traceback 需要按行解析）。"""
    parts = []

    def walk(n):
        for ch in n.children:
            if ch.tag is None:
                parts.append(ch.text)
            elif ch.tag in ("script", "style"):
                continue
            elif ch.tag == "br":
                parts.append("\n")
            else:
                walk(ch)
                if ch.tag in BLOCK:
                    parts.append("\n")
    walk(el)
    lines = [re.sub(r"[ \t ]+", " ", l).rstrip() for l in "".join(parts).split("\n")]
    return "\n".join(l for l in lines if l.strip()).strip()


def _rows_of(tb: Node) -> list[Node]:
    out = []

    def walk(n):
        for ch in n.children:
            if ch.tag is None or ch.tag == "table":
                continue
            if ch.tag == "tr":
                out.append(ch)
            walk(ch)
    walk(tb)
    return out


IMG_LINK = re.compile(r"\.(png|jpe?g|bmp|gif)(\?|$)", re.I)
DATA_URI = re.compile(r"^data:(image/[\w.+-]+);base64,(.*)$", re.I | re.S)


def parse_html(text: str, res: dict | None = None) -> dict:
    p = _Tree()
    p.feed(text)
    p.close()
    images, counter = {}, [0]

    def img_refs(el):
        refs = []
        for img in el.iter("img"):
            src = img.attrs.get("src", "")
            if res and src in res:
                counter[0] += 1
                k = "img#" + str(counter[0])
                images[k] = res[src]
                refs.append(k)
                continue
            m = DATA_URI.match(src.strip())
            if m:
                try:
                    data = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
                except (binascii.Error, ValueError):
                    continue
                counter[0] += 1
                k = "img#" + str(counter[0])
                images[k] = (m.group(1).lower(), data)
                refs.append(k)
            elif src:
                refs.append(src)
        for a in el.iter("a"):
            h = a.attrs.get("href", "")
            if h and IMG_LINK.search(h):
                refs.append(h)
        return refs

    tables = []
    for ti, tb in enumerate(p.root.iter("table")):
        trs = _rows_of(tb)
        if len(trs) < 2:
            continue
        cells_of = lambda tr: [ch for ch in tr.children if ch.tag in ("td", "th")]
        hi = next((i for i, r in enumerate(trs) if any(True for _ in r.iter("th"))), -1)
        h0 = hi if 0 <= hi < 3 else 0
        head = [(cell_text(c).split("\n")[0] or "列" + str(i + 1)) for i, c in enumerate(cells_of(trs[h0]))]
        if len(head) < 2:
            continue
        rows = []
        for tr in trs[h0 + 1:]:
            cells = cells_of(tr)
            # 只有一两个单元格的行（通常是展开后的详细日志）并到上一行
            if rows and (len(cells) == 1 or (len(head) >= 4 and len(cells) <= 2)):
                prev = rows[-1]
                t = "\n".join(x for x in (cell_text(c) for c in cells) if x)
                im = [r for c in cells for r in img_refs(c)]
                if t:
                    prev["详细日志"] = (prev["详细日志"] + "\n" if prev.get("详细日志") else "") + t
                if im:
                    prev["截图"] = (prev["截图"] + ";" if prev.get("截图") else "") + ";".join(im)
                continue
            if len(cells) < 2:
                continue
            # 表头在表格中间重复出现（分页、吸顶表头）时跳过
            same = sum(1 for i, c in enumerate(cells) if i < len(head) and head[i] and cell_text(c).split("\n")[0] == head[i])
            if same >= max(2, -(-len(cells) // 2)):
                continue
            o, im = {}, []
            for i, c in enumerate(cells):
                o[head[i] if i < len(head) and head[i] else "列" + str(i + 1)] = cell_text(c)
                im += img_refs(c)
            if im:
                o["截图"] = (o["截图"] + ";" if o.get("截图") else "") + ";".join(im)
            if any(v for v in o.values()):
                rows.append(o)
        if rows:
            tables.append({"path": "表格 " + str(ti + 1) + "（" + "、".join(head[:4]) + ("…" if len(head) > 4 else "") + "）", "rows": rows})
    if not tables:
        raise ValueError("网页里没有找到表格。请确认报告页面已经显示出用例列表后再保存或复制")
    return {"kind": "网页（MHTML）" if res is not None else "网页（HTML）", "tables": tables, "images": images}


# ---------------------------------------------------------------- 入口

def parse_file(name: str, data: bytes | str) -> dict:
    """返回 {kind, tables: [{path, rows}], images}。"""
    text = data if isinstance(data, str) else decode_text(data)
    n = name.lower()
    head = text[:1000]
    if re.search(r"\.(mhtml|mht)$", n) or re.match(r"^\s*(From:|MIME-Version:)[\s\S]{0,800}multipart/related", head, re.I):
        html, res = parse_mhtml(text)
        return parse_html(html, res)
    if re.search(r"\.(html?|xhtml)$", n) or re.match(r"^\s*(<!doctype html|<html|<meta|<table|<div|<body)", head, re.I):
        return parse_html(text, None)
    if n.endswith(".xml") or re.match(r"^\s*<\?xml|^\s*<testsuites?[\s>]", head):
        return {"kind": "JUnit XML", "tables": [{"path": "testcase", "rows": parse_junit(text)}], "images": {}}
    if n.endswith(".json") or re.match(r"^\s*[\[{]", head):
        try:
            obj = json.loads(text.lstrip("﻿"))
        except json.JSONDecodeError as e:
            raise ValueError("JSON 格式不正确（第 " + str(e.lineno) + " 行）")
        if is_allure(obj):
            return {"kind": "Allure 结果", "tables": [{"path": "allure", "rows": [allure_row(obj)]}], "images": {}}
        arrs = find_arrays(obj)
        if not arrs and isinstance(obj, dict):
            return {"kind": "JSON", "tables": [{"path": "(根)", "rows": [flatten(obj)]}], "images": {}}
        return {"kind": "JSON", "tables": [{"path": a["path"], "rows": [allure_row(x) if is_allure(x) else flatten(x) for x in a["arr"]]} for a in arrs], "images": {}}
    kind = "表格（制表符）" if n.endswith(".tsv") or "\t" in text else "CSV"
    return {"kind": kind, "tables": [{"path": "表格", "rows": parse_delimited(text)}], "images": {}}


def parse_many(files: list[tuple[str, bytes | str]]) -> dict:
    """多个文件一起导入：每个文件只有一张表时合并成一张。返回 {kind, files, tables, images, errors}。"""
    tables, kinds, errors, images = [], [], [], {}
    for name, data in files:
        try:
            p = parse_file(name, data)
        except ValueError as e:
            errors.append(name + "：" + str(e))
            continue
        if p["kind"] not in kinds:
            kinds.append(p["kind"])
        # 多个网页一起导入时，图片编号加上文件序号，避免重复
        if p["images"] and len(files) > 1:
            pre = "f" + str(len(tables) + 1) + "-"
            ren = {k: k.replace("img#", "img#" + pre) for k in p["images"]}
            for t in p["tables"]:
                for r in t["rows"]:
                    for col, v in r.items():
                        if "img#" in v:
                            r[col] = re.sub(r"img#(\d+)", lambda m: "img#" + pre + m.group(1), v)
            p["images"] = {ren[k]: v for k, v in p["images"].items()}
        images.update(p["images"])
        for t in p["tables"]:
            tables.append(dict(t, file=name))
    if len(files) > 1 and len(tables) == len(files):
        tables = [{"file": str(len(files)) + " 个文件", "path": "合并", "rows": [r for t in tables for r in t["rows"]]}]
    tables = sorted([t for t in tables if t["rows"]], key=lambda t: -len(t["rows"]))
    return {"kind": "、".join(kinds), "files": [f[0] for f in files], "tables": tables, "images": images, "errors": errors}
