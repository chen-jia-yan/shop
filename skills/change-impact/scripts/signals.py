# -*- coding: utf-8 -*-
"""
变更信号识别：在“修订前 / 修订后”两段文字中找出实质性变化的证据。

  numbers     关键数值变化（天数、比例、金额、年龄、次数……），带上下文词（如“等待期”）
  dates       日期变化（生效日、截止日）
  obligation  义务/授权表述变化（“可以”→“应当”为加强，反之为放宽）
  negation    否定词在被删或新增的文字里出现，含义可能反转（“承担”↔“不承担”）
  scope       适用范围措辞变化（仅、除外、不包括、以上、以内……）
  terms       涉及的业务术语（按 impact.json 的类别）

所有词表来自 tap-config/impact.json，可按业务增删。
"""
import re
from difflib import SequenceMatcher

from ci_common import all_keywords, bare, find_terms, imp, norm

CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}
DATE_RX = re.compile(r"(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(?:(\d{1,2})\s*日?)?")


def cn_to_num(s):
    """中文数字转数值：九十 → 90，一百八十 → 180，十五 → 15，两万 → 20000。"""
    total, sec, num = 0, 0, 0
    for ch in s:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            u = CN_UNIT[ch]
            if u == 10000:
                total += (sec + num) * u
                sec = 0
            else:
                sec += (num or 1) * u
            num = 0
    return total + sec + num


def _units():
    return sorted(imp().get("number_units", []), key=len, reverse=True)


def _num_rx():
    u = "|".join(re.escape(x) for x in _units())
    return re.compile(r"(?<![第\d.])(?P<num>\d+(?:,\d{3})*(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)\s*(?P<unit>%s)" % u)


def _mask_dates(text):
    return DATE_RX.sub(lambda m: " " * len(m.group(0)), text)


def _context(text, pos):
    """数值前面最近的业务关键词（12 个字以内）；找不到时取前 6 个字。"""
    left = text[max(0, pos - 14):pos]
    best, best_at = None, -1
    for kw in all_keywords():
        at = left.rfind(kw)
        if at > best_at:
            best, best_at = kw, at
    if best:
        return best
    return re.sub(r"[\s，。；：、]", "", left)[-6:]


def numbers(text):
    t = _mask_dates(norm(text))
    out = []
    for m in _num_rx().finditer(t):
        raw_n = m.group("num")
        if re.match(r"^[零〇一二两三四五六七八九十百千万]+$", raw_n):
            v = float(cn_to_num(raw_n))
        else:
            v = float(raw_n.replace(",", ""))
        out.append({"value": v, "unit": m.group("unit"), "raw": m.group(0).replace(" ", ""),
                    "ctx": _context(t, m.start()), "pos": m.start()})
    return out


def dates(text):
    out = []
    for m in DATE_RX.finditer(norm(text)):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if not 1 <= int(mo) <= 12:
            continue
        out.append("%s-%02d" % (y, int(mo)) + ("-%02d" % int(d) if d else ""))
    return out


def _fmt(v):
    return ("%d" % v) if float(v).is_integer() else ("%g" % v)


def compare_numbers(old_text, new_text):
    """同一上下文词 + 同一单位的数值发生变化，记为一处数值变更。"""
    a, b = numbers(old_text), numbers(new_text)
    key = lambda x: (x["ctx"], x["unit"], x["value"])          # noqa: E731
    ca = {}
    for x in a:
        ca.setdefault(key(x), []).append(x)
    rest_b = []
    for y in b:
        if ca.get(key(y)):
            ca[key(y)].pop()                               # 新旧都有、没变
        else:
            rest_b.append(y)
    rest_a = [x for v in ca.values() for x in v]
    changes = []
    for pairing in (lambda x, y: x["ctx"] == y["ctx"] and x["unit"] == y["unit"],
                    lambda x, y: x["unit"] == y["unit"]):
        for x in list(rest_a):
            for y in rest_b:
                if pairing(x, y):
                    ratio = abs(y["value"] - x["value"]) / abs(x["value"]) if x["value"] else 1.0
                    changes.append({"ctx": x["ctx"] if x["ctx"] == y["ctx"] else y["ctx"] or x["ctx"],
                                    "unit": x["unit"], "old": x["raw"], "new": y["raw"],
                                    "old_v": x["value"], "new_v": y["value"],
                                    "direction": "up" if y["value"] > x["value"] else "down",
                                    "ratio": round(ratio, 4)})
                    rest_a.remove(x)
                    rest_b.remove(y)
                    break
    for x in rest_a:
        changes.append({"ctx": x["ctx"], "unit": x["unit"], "old": x["raw"], "new": None,
                        "old_v": x["value"], "new_v": None, "direction": "removed", "ratio": 1.0})
    for y in rest_b:
        changes.append({"ctx": y["ctx"], "unit": y["unit"], "old": None, "new": y["raw"],
                        "old_v": None, "new_v": y["value"], "direction": "added", "ratio": 1.0})
    return changes


def compare_dates(old_text, new_text):
    a, b = dates(old_text), dates(new_text)
    ra = [x for x in a if x not in b]
    rb = [y for y in b if y not in a]
    out = []
    for i in range(max(len(ra), len(rb))):
        out.append({"old": ra[i] if i < len(ra) else None, "new": rb[i] if i < len(rb) else None})
    return out


# ---------------- 字词级差异 ----------------
TOKEN = re.compile(r"\d+(?:[.,]\d+)*%?|[A-Za-z]+|\s+|.", re.S)


def tokens(s):
    return TOKEN.findall(norm(s))


def segments(old_text, new_text):
    """[["eq"|"del"|"ins", 文本], ...]，相邻同类合并；替换拆成先删后增。"""
    a, b = tokens(old_text), tokens(new_text)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    out = []

    def add(op, t):
        if not t:
            return
        if out and out[-1][0] == op:
            out[-1][1] += t
        else:
            out.append([op, t])
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            add("eq", "".join(a[i1:i2]))
        else:
            add("del", "".join(a[i1:i2]))
            add("ins", "".join(b[j1:j2]))
    return out


def similarity(a, b):
    return SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


def _count_words(text, words):
    if not words or not text:
        return {}
    rx = re.compile("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)))
    out = {}
    for m in rx.finditer(text):
        out[m.group(0)] = out.get(m.group(0), 0) + 1
    return out


def obligation(old_text, new_text):
    ow = imp().get("obligation_words", {})
    strong, weak = ow.get("strong", []), ow.get("weak", [])
    a_s, b_s = _count_words(norm(old_text), strong), _count_words(norm(new_text), strong)
    a_w, b_w = _count_words(norm(old_text), weak), _count_words(norm(new_text), weak)
    ds = sum(b_s.values()) - sum(a_s.values())
    dw = sum(b_w.values()) - sum(a_w.values())
    if ds == 0 and dw == 0 and a_s == b_s and a_w == b_w:
        return None
    gone = [w for w in list(a_s) + list(a_w) if (b_s.get(w, 0) + b_w.get(w, 0)) < (a_s.get(w, 0) + a_w.get(w, 0))]
    came = [w for w in list(b_s) + list(b_w) if (b_s.get(w, 0) + b_w.get(w, 0)) > (a_s.get(w, 0) + a_w.get(w, 0))]
    if not gone and not came:
        return None
    direction = "up" if (ds > 0 or dw < 0) else "down"
    return {"direction": direction, "old": "、".join(gone) or "—", "new": "、".join(came) or "—"}


def negation(segs):
    """否定词出现在被删除或新增的文字里，且两边数量不同 → 可能含义反转。"""
    words = imp().get("negation_words", [])
    strong = imp().get("obligation_words", {}).get("strong", [])
    dele = "".join(t for op, t in segs if op == "del")
    ins = "".join(t for op, t in segs if op == "ins")
    # “不得”等已按义务表述统计，这里剔除，避免重复计分
    for w in strong:
        dele, ins = dele.replace(w, ""), ins.replace(w, "")
    a = sum(_count_words(dele, words).values())
    b = sum(_count_words(ins, words).values())
    return a != b


def scope(segs):
    words = imp().get("scope_words", [])
    dele = "".join(t for op, t in segs if op == "del")
    ins = "".join(t for op, t in segs if op == "ins")
    a, b = _count_words(dele, words), _count_words(ins, words)
    return sorted(set(w for w in list(a) + list(b) if a.get(w, 0) != b.get(w, 0)))


def clauses(segs, op):
    """修改类变更里整句 / 整项被删除或新增的文字（去标点后不少于 clause_chars 个字）。
    例如责任免除里删掉“（六）遗传性疾病……”一项：整段相似度仍很高，但这是实质变更。"""
    n = imp().get("clause_chars", 6)
    return [norm(t).strip() for o, t in segs if o == op and len(bare(t)) >= n]


def analyse(old_text, new_text, segs=None):
    """返回一处变更的全部信号。old_text / new_text 可为空（新增 / 删除）。"""
    old_text, new_text = old_text or "", new_text or ""
    segs = segs if segs is not None else segments(old_text, new_text)
    changed = "".join(t for op, t in segs if op != "eq")
    sig = {
        "numbers": compare_numbers(old_text, new_text),
        "dates": compare_dates(old_text, new_text),
        "obligation": obligation(old_text, new_text),
        "negation": negation(segs) if old_text and new_text else False,
        "scope": scope(segs) if old_text and new_text else [],
        "terms": find_terms(old_text + "\n" + new_text),
        "changed_terms": find_terms(changed) if changed else {},
        "removed_text": clauses(segs, "del") if old_text and new_text else [],
        "added_text": clauses(segs, "ins") if old_text and new_text else [],
    }
    return sig


def has_substance(sig):
    return bool(sig["numbers"] or sig["dates"] or sig["obligation"] or sig["negation"] or sig["scope"]
                or sig.get("removed_text") or sig.get("added_text"))
