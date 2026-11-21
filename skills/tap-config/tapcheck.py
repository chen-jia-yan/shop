# -*- coding: utf-8 -*-
"""
共享质检工具：合规用语、必备要素、占位符、质检报告格式。
词表全部来自 compliance.json，报告标题文字来自 labels.json，四个 skill 共用同一套口径。
"""
import re

from tapconf import CONF


def _c():
    return CONF.compliance()


def banned_hits(text):
    """返回 [(类别, 命中词, 上下文, 原因)]；否定式提及（如“不保证收益”“不等同于存款”）不算违规。"""
    c = _c()
    wl = re.compile(c["whitelist"]) if c.get("whitelist") else None
    neg = re.compile(c["negation"]) if c.get("negation") else None
    win = int(c.get("negation_window", 10))
    clean = wl.sub("", text) if wl else text
    out = []
    for rule in c.get("banned", []):
        for m in re.finditer(rule["pattern"], clean):
            if neg and neg.search(clean[max(0, m.start() - win):m.start()]):
                continue
            s = max(0, m.start() - 12)
            out.append((rule["cat"], m.group(0), clean[s:m.end() + 12].replace("\n", " "), rule.get("why", "")))
    return out


def required_missing(doc_type, full_text):
    return [name for name, pat in (_c().get("required") or {}).get(doc_type, [])
            if not re.search(pat, full_text)]


def required_types():
    return sorted((_c().get("required") or {}).keys())


def is_customer_facing(doc_type):
    return doc_type in set(_c().get("customer_facing_types", []))


def calc_disclaimer_ok(sheet_titles, all_text):
    kws = _c().get("calc_sheet_keywords", [])
    has_calc = any(k in t for t in sheet_titles for k in kws)
    pat = _c().get("calc_disclaimer")
    return (not has_calc) or (not pat) or bool(re.search(pat, all_text))


def has_placeholder(text):
    return bool(CONF.placeholder_re().search(text))


def report_md(name, must, should, info, head=None, tail=None):
    L = CONF.label
    lines = ["# " + L("report.title", name=name), ""]
    lines += head or []
    lines += ["**%s**" % L("report.verdict", v=L("report.fail") if must else L("report.pass")), ""]
    for key, items in (("report.must", must), ("report.should", should), ("report.info", info)):
        lines.append("## %s（%d）" % (L(key), len(items)))
        lines += ["- " + x for x in items] or ["- " + L("report.none")]
        lines.append("")
    lines += tail or []
    return "\n".join(lines)
