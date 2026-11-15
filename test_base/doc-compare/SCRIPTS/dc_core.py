"""文档对比核心：两份文档的文字行 → 差异清单。

不读 PDF、不画图，只处理文字行，可以单独测试（evals/test_core.py）。

每一行是一个 dict：
    t 原文  n 统一格式后的文字  no 行号（与 total.html 一致）  page 页码  bbox [x0, top, x1, bottom]
    src "text"（PDF 文字层）或 "ocr"（扫描页识别得到）  sec 所在章节  words 词和坐标（截图打码用）

结果里每一条差异的 status：
    real    真实差异
    unsure  不确定，交给人看
    ignored 只差日期或人名，已忽略（附录，可抽查）
    layout  内容相同、只是位置或换行不同（附录，可抽查）
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter, defaultdict

from filters import DATE_PH, NAME_PH, fmt_shift

CORE_DEFAULTS = {
    "normalize_thousands": True,   # 1,000.00 与 1000.00 视为相同
    "min_move_len": 4,             # 少于这么多字的行不做“移动”配对，避免把常见短行配错
    "heading_patterns": [],        # 章节标题的写法（正则），没有字号信息时靠它分章节
    "heading_ratio": 1.2,          # 字号比正文大这么多倍的短行当作标题
    "heading_max_len": 60,
    "owners": [],                  # [{"name": "负责人", "match": ["章节或文字里的关键字（正则）"]}]
    "default_owner": "未分配",
    "ocr_allow_ignore": False,     # 扫描页（识别得到的文字）上的变化是否也自动忽略；默认不忽略，全部交给人看
}

WS = re.compile(r"\s+")
THOUS = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])")
NUM = re.compile(r"\d+(?:\.\d+)?")
PH = re.compile(r"‹[^›]*›")
STATUS_PREFIX = {"real": "D", "unsure": "U", "ignored": "I", "layout": "L"}


def normalize(s: str, cfg: dict) -> str:
    """统一格式：全角半角、多余空格、千分位。只用于比较，报告里显示原文。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = WS.sub(" ", s).strip()
    if cfg.get("normalize_thousands", True):
        s = THOUS.sub(lambda m: m[0].replace(",", ""), s)
    return s


def numbers(s: str, cfg: dict) -> list[str]:
    return NUM.findall(normalize(s, cfg))


def compact(s: str) -> str:
    return WS.sub("", s)


# ---------------------------------------------------------------- 章节、字段、负责人

def assign_sections(lines: list[dict], cfg: dict) -> None:
    """给每行标上所在章节“大标题 › 小标题”。有字号时按字号判断标题，也可以用 heading_patterns 指定。"""
    cfg = {**CORE_DEFAULTS, **cfg}
    sizes = sorted(l["size"] for l in lines if l.get("size"))
    body = sizes[len(sizes) // 2] if sizes else None
    pats = [re.compile(p) for p in cfg["heading_patterns"]]

    def is_head(l):
        t = l["n"]
        if any(p.search(t) for p in pats):
            return True
        return bool(body and l.get("size") and l["size"] >= body * cfg["heading_ratio"]
                    and len(t) <= cfg["heading_max_len"] and not re.fullmatch(r"[\d\s.,/:%-]+", t))

    heads = [l for l in lines if is_head(l)]
    head_ids = {id(h) for h in heads}
    top = max(((h.get("size") or 0) for h in heads), default=0)
    cur = ["", ""]
    for l in lines:
        if id(l) in head_ids:
            if (l.get("size") or 0) >= top - 0.5:
                cur = [l["n"], ""]
            else:
                cur[1] = l["n"]
        l["sec"] = " › ".join(x for x in cur if x)


def field_of(key: str) -> str:
    """字段名：去掉日期、人名、数字后剩下的文字，例如“被保人姓名 ‹人名›”→“被保人姓名”。"""
    f = WS.sub(" ", NUM.sub(" ", PH.sub(" ", key))).strip(" :：-")
    return f[:40]


def owner_of(text: str, cfg: dict) -> str:
    for o in cfg.get("owners") or []:
        if any(re.search(p, text) for p in o.get("match") or []):
            return o["name"]
    return cfg.get("default_owner", "未分配")


# ---------------------------------------------------------------- 对比

def compare(A: list[dict], B: list[dict], cfg: dict, flt) -> dict:
    """A = baseline 的行，B = 新文件的行（页眉页脚已去掉）。flt：filters.Filter。"""
    cfg = {**CORE_DEFAULTS, **cfg}
    ta = [flt.template(l["n"]) for l in A]
    tb = [flt.template(l["n"]) for l in B]
    ctx = {"A": A, "B": B, "ta": ta, "tb": tb, "flt": flt, "cfg": cfg}
    items, cands, loose = [], [], []

    # 1. 把日期、人名换成占位符后整篇对齐（与现在的 difflib 对比同一种方法）
    sm = difflib.SequenceMatcher(None, [k[0] for k in ta], [k[0] for k in tb], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if A[i]["n"] != B[j]["n"]:
                    cands.append(_cand([i], [j], ctx))
            continue
        ia, jb = list(range(i1, i2)), list(range(j1, j2))
        r = _block_rule(ia, jb, ctx)
        if r is None:
            loose.append([ia, jb])
        elif r.get("_cand"):
            cands.append(r)
        else:
            items.append(r)

    # 2. 对不上的行：在全文里找内容相同、只是挪了位置的行
    _moves(loose, ctx, items, cands)
    for ia, jb in loose:
        items += _leftover(ia, jb)

    # 3. 只差日期或人名的：检查日期是不是整体平移同样的天数
    mode, shifts = _judge(cands, items, ctx)

    # 4. 扫描页、疑似人名、章节、负责人、编号
    res = {
        "items": [_materialize(it, ctx) for it in items], "date_shift": mode,
        "date_shifts": {str(k): v for k, v in shifts.items()}, "names": dict(flt.names),
        "stats": {"baseline_lines": len(A), "new_lines": len(B)},
    }
    renumber(res)
    return res


def renumber(res: dict) -> None:
    """按位置排序、编号（真实差异 D001、不确定 U001、已忽略 I001、位置变化 L001），并重算数量。状态改变后要再调用一次。"""
    out = res["items"]
    out.sort(key=lambda x: ((x["a"] or x["b"])[0]["no"], 0 if x["a"] else 1))
    count = Counter()
    for x in out:
        count[x["status"]] += 1
        x["id"] = f"{STATUS_PREFIX[x['status']]}{count[x['status']]:03d}"
    res["stats"].update({s: count.get(s, 0) for s in STATUS_PREFIX})


def _item(status, kind, ia, jb, reason="", **extra):
    return {"status": status, "kind": kind, "ia": list(ia), "jb": list(jb), "reason": reason, **extra}


def _cand(ia, jb, ctx, moved=False):
    """候选：换成占位符后两边相同，只差日期或人名。"""
    ta, tb, A, B, flt = ctx["ta"], ctx["tb"], ctx["A"], ctx["B"], ctx["flt"]
    da = [d for i in ia for d in ta[i][1]]
    db = [d for j in jb for d in tb[j][1]]
    na = [n for i in ia for n in ta[i][2]]
    nb = [n for j in jb for n in tb[j][2]]
    text = " ".join(A[i]["n"] for i in ia) + " " + " ".join(B[j]["n"] for j in jb)
    return {"_cand": True, "ia": list(ia), "jb": list(jb), "moved": moved,
            "dates": [(x.isoformat(), y.isoformat(), (y - x).days) for x, y in zip(da, db) if x != y],
            "names": [(x, y) for x, y in zip(na, nb) if x != y],
            "free": flt.any_shift_label(text)}


def _block_rule(ia, jb, ctx):
    """一段对不上的内容，先看是不是“内容相同、位置不同”或“只有人名”。返回 None 表示交给后面处理。"""
    A, B, ta, tb, flt = ctx["A"], ctx["B"], ctx["ta"], ctx["tb"], ctx["flt"]
    if ia and jb:
        if compact("".join(A[i]["n"] for i in ia)) == compact("".join(B[j]["n"] for j in jb)):
            return _item("layout", "changed", ia, jb, "换行或断行位置不同，内容相同")
        tok = lambda idx, L: sorted(" ".join(L[k]["n"] for k in idx).split())
        if tok(ia, A) == tok(jb, B):
            return _item("layout", "changed", ia, jb, "文字相同，顺序不同（多为表格各列读取顺序不同）")
        if compact("".join(ta[i][0] for i in ia)) == compact("".join(tb[j][0] for j in jb)):
            return _cand(ia, jb, ctx)
    # 只有人名的一段，且两边人名个数不同（例如 baseline 1 个名字，新文件 3 个）
    keys = [ta[i][0].strip() for i in ia] + [tb[j][0].strip() for j in jb]
    if keys and all(k == NAME_PH for k in keys):
        st = "ignored" if flt.cfg["name_count_change"] == "ignore" else "unsure"
        na = [n for i in ia for n in ta[i][2]]
        nb = [n for j in jb for n in tb[j][2]]
        if ia and jb:
            why = f"只有人名，人名个数不同（baseline {len(ia)} 个，新文件 {len(jb)} 个）"
        else:
            why = f"只有人名，人名个数不同：新文件{'多出' if jb else '少了'} {len(jb or ia)} 个"
        if st == "ignored":
            why += "；按配置 name_count_change = ignore 忽略"
        return _item(st, "changed" if ia and jb else ("removed" if ia else "added"), ia, jb, why,
                     names=[[", ".join(na), ", ".join(nb)]])
    return None


def _moves(loose, ctx, items, cands):
    """对不上的行里，内容相同（或只差日期、人名）的配成“位置变化”。"""
    A, B, ta, tb, cfg = ctx["A"], ctx["B"], ctx["ta"], ctx["tb"], ctx["cfg"]
    by_text, by_key = defaultdict(list), defaultdict(list)
    for _, jb in loose:
        for j in jb:
            by_text[B[j]["n"]].append(j)
            by_key[tb[j][0]].append(j)
    used_a, used_b = set(), set()
    for exact in (True, False):
        for ia, _ in loose:
            for i in ia:
                if i in used_a:
                    continue
                key = A[i]["n"] if exact else ta[i][0]
                if len(compact(PH.sub("", key))) < cfg["min_move_len"]:
                    continue
                js = [j for j in (by_text if exact else by_key).get(key, []) if j not in used_b]
                if not js:
                    continue
                j = min(js, key=lambda j: abs(j - i))
                used_a.add(i)
                used_b.add(j)
                if exact:
                    pa, pb = A[i].get("page"), B[j].get("page")
                    why = f"从第 {pa} 页移到第 {pb} 页，内容相同" if pa and pb and pa != pb else "位置变化，内容相同"
                    items.append(_item("layout", "moved", [i], [j], why))
                else:
                    cands.append(_cand([i], [j], ctx, moved=True))
    for pair in loose:
        pair[0] = [i for i in pair[0] if i not in used_a]
        pair[1] = [j for j in pair[1] if j not in used_b]


def _leftover(ia, jb):
    if ia and jb:
        if len(ia) == len(jb):
            return [_item("real", "changed", [i], [j]) for i, j in zip(ia, jb)]
        return [_item("real", "changed", ia, jb)]
    if ia:
        return [_item("real", "removed", ia, [])]
    if jb:
        return [_item("real", "added", [], jb)]
    return []


def _judge(cands, items, ctx):
    """被忽略的日期必须整体平移同样的天数；平移天数和其他不同的，照常报出来。"""
    flt = ctx["flt"]
    shifts = Counter(s for c in cands if not c["free"] for _, _, s in c["dates"])
    top = shifts.most_common(2)
    mode = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None
    for c in cands:
        parts = [f"日期 {o} → {n}（{fmt_shift(s)}）" for o, n, s in c["dates"]]
        parts += [f"人名 {o} → {n}（来源：{flt.source_of(o) if o in flt.names else flt.source_of(n)}）" for o, n in c["names"]]
        kind = "moved" if c["moved"] else "changed"
        extra = {"dates": c["dates"], "names": [list(x) for x in c["names"]]}
        if not parts:
            # 日期、人名都没变，只是日期的写法变了（例如 2026-11-06 → 2026 11 06）：打印格式可能改了，交给人看
            items.append(_item("unsure", kind, c["ia"], c["jb"], "日期的写法变了，日期本身相同", **extra))
            continue
        if c["free"] and c["dates"]:
            parts.append("此行日期不要求统一平移（配置 date_any_shift_labels）")
        bad = [s for _, _, s in c["dates"] if not c["free"] and s != mode]
        if flt.cfg["date_shift_must_match"] and bad:
            if mode is None:
                why = "日期平移的天数各不相同，无法判断哪个正常：" + "、".join(f"{s:+d} 天 × {n}" for s, n in shifts.most_common())
                items.append(_item("unsure", kind, c["ia"], c["jb"], why, **extra))
            else:
                why = f"这里的日期{fmt_shift(bad[0])}，其他日期都是{fmt_shift(mode)}"
                items.append(_item("real", kind, c["ia"], c["jb"], why, **extra))
        else:
            if c["moved"]:
                parts.append("位置也变了")
            items.append(_item("ignored", kind, c["ia"], c["jb"], "；".join(parts), **extra))
    return mode, shifts


def _ref(l):
    return {"no": l["no"], "page": l.get("page"), "bbox": l.get("bbox"), "src": l.get("src", "text")}


def _materialize(it, ctx):
    A, B, tb, ta, flt, cfg = ctx["A"], ctx["B"], ctx["tb"], ctx["ta"], ctx["flt"], ctx["cfg"]
    la, lb = [A[i] for i in it["ia"]], [B[j] for j in it["jb"]]
    flags = []
    status, reason = it["status"], it["reason"]
    if any(l.get("src") == "ocr" for l in la + lb):
        flags.append("扫描页")
        if status == "real" or (status in ("ignored", "layout") and not cfg["ocr_allow_ignore"]):
            status = "unsure"
            reason = "扫描页，文字由识别得到，请看截图核对" + (f"（{reason}）" if reason else "")
    sus = flt.suspects([l["n"] for l in la + lb]) if status in ("real", "unsure") else []
    if sus:
        flags.append("疑似人名")
        reason = (reason + "；" if reason else "") + "疑似人名：" + "、".join(sus) + "（不在人名清单里，请确认；是人名就加进名单）"
    first = (la or lb)[0]
    key = (ta[it["ia"][0]] if la else tb[it["jb"][0]])[0]
    sec, field = first.get("sec", ""), field_of(key)
    text = " ".join([sec, field] + [l["n"] for l in la + lb])
    out = {"status": status, "kind": it["kind"], "a": [_ref(l) for l in la], "b": [_ref(l) for l in lb],
           "old": [l["t"] for l in la], "new": [l["t"] for l in lb], "section": sec, "field": field,
           "owner": owner_of(text, cfg), "reason": reason, "flags": flags}
    for k in ("dates", "names"):
        if it.get(k):
            out[k] = it[k]
    return out
