# -*- coding: utf-8 -*-
"""
变更影响分析 —— 公共工具：读写 JSON、文本规范化、类别识别、级别换算。
所有规则（类别关键词、权重、阈值、文字）来自 tap-config/impact.json、rules.json、labels.json。
"""
import datetime as dt
import json
import os
import re
import unicodedata

from _tap import CONF

PUNCT = re.compile(r"[\s　，。；：、！？“”‘’（）()《》〈〉【】\[\]{}<>,;:!?\"'·…—\-_/|]+")


def imp():
    """impact.json 的内容（tapconf 已合并进 CONF.raw）。"""
    v = CONF.raw.get("impact")
    if not v:
        raise SystemExit("缺少 tap-config/impact.json（变更影响分析的类别与评分规则）")
    return v


def L(key, **kw):
    return CONF.label("impact." + key, **kw)


def R(key):
    return CONF.rule(key)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def norm(s):
    """比对用的规范化：全角转半角、去首尾空白、合并空白。"""
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def bare(s):
    """去掉标点和空白，用于判断“只改了标点/空格”。"""
    return PUNCT.sub("", norm(s))


def clip(s, n=60):
    s = norm(s)
    return s if len(s) <= n else s[:n - 1] + "…"


# ---------------- 类别 ----------------
def categories():
    return imp()["categories"]


def fallback_category():
    return imp()["fallback_category"]


def cat_by_key(key):
    for c in categories():
        if c["key"] == key:
            return c
    fb = fallback_category()
    if key == fb["key"]:
        return fb
    raise KeyError(key)


def find_terms(text):
    """返回 {类别 key: [命中的关键词]}，按出现顺序去重。"""
    t = norm(text)
    out = {}
    for c in categories():
        hits = []
        for kw in c["keywords"]:
            if kw in t and kw not in hits:
                hits.append(kw)
        if hits:
            out[c["key"]] = hits
    return out


def all_keywords():
    """全部关键词，长的在前（用于就近找“数值的上下文词”）。"""
    kws = {kw for c in categories() for kw in c["keywords"]}
    return sorted(kws, key=len, reverse=True)


# ---------------- 级别 ----------------
def level_order():
    return [lv for lv, _ in R("levels")]


def level_of(score):
    for lv, th in R("levels"):
        if score >= th:
            return lv
    return level_order()[-1]


def more_severe(a, b):
    order = level_order()
    return a if order.index(a) <= order.index(b) else b


def level_name(lv):
    return L("levels").get(lv, lv)


def type_name(t):
    return L("change_types").get(t, t)


# ---------------- 日期 ----------------
def parse_date(s):
    if not s:
        return None
    if isinstance(s, dt.date):
        return s
    s = norm(s)
    m = re.match(r"^(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if not m:
        raise SystemExit("无法识别的日期：%s（请用 YYYY-MM-DD）" % s)
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def today():
    return dt.date.today()


def fmt_date(d):
    return d.strftime("%Y-%m-%d") if d else ""
