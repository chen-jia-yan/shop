# -*- coding: utf-8 -*-
"""
变更影响分析 —— 第 4 步：生成报告（Word）与跟踪表（Excel）

用法：
  python build_report.py scored.json --out-dir out/ [--notes notes.json] [--name 文件名前缀]
                         [--variant full|brief] [--no-tracker] [--render] [--style 风格名]
                         [--config 额外配置] [--font-cn 字体 ...]

输出：
  <名称>_报告内容.json     kb-to-word 的内容 JSON（可人工微调后再渲染）
  <名称>_跟踪表内容.json   kb-to-excel 的内容 JSON（变更清单 / 处置跟踪甘特 / 受影响内容）
  加 --render 时直接调用 kb-to-word、kb-to-excel 渲染，并对 Word 做质检：
  <名称>.docx、<名称>_跟踪表.xlsx、<名称>_质检报告.md

报告结构（full）：结论摘要 → 变更概览 → 重点变更逐条分析 → 影响范围 → 处置计划 → 合规与对客告知
               → 附录（措辞类修订、全部变更明细、分析方法与口径）→ 签批
brief：结论摘要 → 变更概览 → 重大 / 较大变更 → 处置计划 → 合规与对客告知（适合发管理层）
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _tap import CONF, add_cli_args, configure     # noqa: E402

from ci_common import (L, R, clip, fmt_date, imp, level_name, level_order, load_json, parse_date,  # noqa: E402
                       save_json, today, type_name)


def _todo():
    """占位符文字取自 compliance.json，质检会统计它。"""
    return CONF.compliance().get("placeholders", {}).get("todo", "") + "】"


# ---------------- 文本工具 ----------------
def _safe(t):
    return str(t).replace("**", "＊＊")


def excerpt(segs, side, limit):
    """修订前 / 修订后原文，变化部分加粗；太长时只保留变化附近的上下文。"""
    want = "del" if side == "old" else "ins"
    parts = [(op, _safe(t)) for op, t in segs if op == "eq" or op == want]
    if not parts:
        return L("report.empty")
    total = sum(len(t) for _, t in parts)
    out = []
    for k, (op, t) in enumerate(parts):
        if op == "eq" and total > limit and len(t) > 44:
            if k == 0:
                t = "…" + t[-24:]
            elif k == len(parts) - 1:
                t = t[:24] + "…"
            else:
                t = t[:18] + "…" + t[-18:]
        out.append("**%s**" % t if op != "eq" and t.strip() else t)
    return "".join(out)


def due_text(a, eff):
    off = a.get("offset")
    RP = L("report")
    if off is None:
        return a.get("due") or _todo()
    if eff:
        d = fmt_date(eff + dt.timedelta(days=off))
        return RP["due_before"].format(n=-off, date=d) if off < 0 else RP["due_after"].format(n=off, date=d)
    return RP["due_unknown"].format(n=abs(off))


def extra_notes(ch):
    D = L("describe")
    sig = ch["signals"]
    out = []
    ob = sig.get("obligation")
    if ob:
        out.append(D["obligation_up" if ob["direction"] == "up" else "obligation_down"].format(old=ob["old"], new=ob["new"]))
    if sig.get("negation"):
        out.append(D["negation"])
    if sig.get("scope"):
        out.append(D["scope"].format(words="、".join(sig["scope"])))
    return out


def short(ch, n=26):
    return "%s %s" % (ch["id"], clip(ch["desc"], n))


# ---------------- 报告各部分 ----------------
def H(text, level=1, **kw):
    b = {"type": "heading", "text": text, "level": level}
    b.update(kw)
    return b


def sec_summary(data, notes, sub):
    RP = L("report")
    s = data["summary"]
    bl = s["by_level"]
    order = level_order()
    p0, p1 = bl.get(order[0], 0), bl.get(order[1], 0)
    cats = sorted(s["by_category"].items(), key=lambda kv: -kv[1])
    lead = notes.get("summary") or (RP["auto_lead"].format(
        total=s["total"], sub=s["substantive"], p0=p0, p1=p1,
        cats="、".join(k for k, _ in cats[:3]) or RP["empty"],
        stale=s["stale_docs"], related=s["related_docs"]) if sub else RP["auto_lead_none"].format(total=s["total"]))
    blocks = [H(RP["s_summary"]), {"type": "lead", "text": lead},
              {"type": "kpi", "items": [
                  {"value": s["substantive"], "unit": RP["unit_item"], "label": RP["kpi_total"]},
                  {"value": "%d / %d" % (p0, p1), "label": RP["kpi_major"]},
                  {"value": s["stale_docs"] + s["related_docs"], "unit": RP["unit_place"], "label": RP["kpi_refs"]},
                  {"value": s["customer"], "unit": RP["unit_item"], "label": RP["kpi_customer"]}]}]
    top = sorted(sub, key=lambda c: (order.index(c["level"]), -c["score"]))[:3]
    items = list(notes.get("highlights", [])) + ["%s（%s）" % (short(c, 40), c["level_name"]) for c in top
                                                  if c["level"] != order[-1]]
    if items:
        blocks.append({"type": "callout", "kind": "key", "title": RP["top_title"], "items": items[:5]})
    if p0:
        blocks.append({"type": "callout", "kind": "risk", "title": RP["risk_title"], "text": RP["risk_text"].format(n=p0)})
    if notes.get("conclusions"):
        blocks.append({"type": "bullets", "items": notes["conclusions"]})
    return blocks


def sec_overview(data, sub):
    RP = L("report")
    s = data["summary"]
    order = level_order()
    blocks = [H(RP["s_overview"])]
    if sub:
        blocks.append({"type": "chart", "chart": "bar", "categories": [level_name(lv) for lv in order],
                       "series": [{"name": RP["kpi_total"], "values": [s["by_level"].get(lv, 0) for lv in order]}],
                       "caption": RP["by_level_caption"], "height_in": 2.4})
        if len(s["by_category"]) >= 2:
            cats = sorted(s["by_category"].items(), key=lambda kv: -kv[1])
            blocks.append({"type": "chart", "chart": "donut", "categories": [k for k, _ in cats],
                           "series": [{"name": RP["kpi_total"], "values": [v for _, v in cats]}],
                           "caption": RP["by_cat_caption"], "center_text": str(s["substantive"]),
                           "center_label": RP["kpi_total"]})
        rows = [[c["id"], clip(c["location"], 22) or "—", c["category_name"], clip(c["desc"], 56), c["level_name"]]
                for c in sorted(sub, key=lambda c: (order.index(c["level"]), c["id"]))]
        blocks.append({"type": "table", "caption": RP["s_overview"], "columns": RP["overview_cols"], "rows": rows,
                       "highlight_col": 4})
    else:
        blocks.append({"type": "paragraph", "text": RP["empty"]})
    return blocks


def detail_block(ch, data, refs, eff, limit):
    RP = L("report")
    meta = data["meta"]
    b = [H(RP["detail_title"].format(id=ch["id"], desc=clip(ch["desc"], 40), lv=ch["level_name"]), 2)]
    old_x = excerpt(ch["segments"], "old", limit) if ch.get("old") else RP["empty"]
    new_x = excerpt(ch["segments"], "new", limit) if ch.get("new") else RP["empty"]
    b.append({"type": "compare", "cards": [
        {"title": RP["before"], "subtitle": meta["old"]["label"], "points": [old_x]},
        {"title": RP["after"], "subtitle": meta["new"]["label"], "points": [new_x], "highlight": True,
         "tag": RP["after_tag"]}]})
    what = [ch["desc"]] + extra_notes(ch)
    b.append({"type": "paragraph", "text": "**%s**：%s" % (RP["what_changed"], "；".join(what)), "align": "left"})
    b.append({"type": "paragraph", "align": "left", "text": "**%s**：%s" % (RP["why_level"], RP["score_line"].format(
        i=ch["importance"], m=ch["impact"], s=ch["score"], lv=ch["level_name"]))})
    reasons = ch["reasons"]["importance"] + ch["reasons"]["impact"] + ch["reasons"]["floor"]
    if ch.get("override_reason"):
        reasons.append(RP["override"].format(r=ch["override_reason"], a=level_name(ch["level_auto"])))
    b.append({"type": "bullets", "items": reasons})
    b.append({"type": "paragraph", "align": "left", "text": "**%s**：%s" % (RP["objects"], "、".join(ch["objects"]))})
    mine = [r for r in refs if r["change_id"] == ch["id"]]
    if mine:
        M, A = L("match"), L("match_action")
        b.append({"type": "table", "columns": [RP["refs_cols"][0], RP["refs_cols"][3], RP["refs_cols"][4], RP["refs_cols"][6]],
                  "rows": [[clip(r["title"], 24), M[r["match"]], clip(r["evidence"], 48), A[r["match"]]]
                           for r in sorted(mine, key=lambda r: (r["match"] != "stale", -r["score"]))[:8]]})
    if ch["actions"]:
        b.append({"type": "paragraph", "align": "left", "text": "**%s**：" % RP["actions"]})
        b.append({"type": "bullets", "items": [RP["action_item"].format(action=a["action"], owner=a["owner"], due=due_text(a, eff))
                                               for a in ch["actions"]]})
    if ch.get("comment"):
        b.append({"type": "callout", "kind": "info", "title": RP["comment"], "text": ch["comment"]})
    return b


def sec_detail(data, sub, eff, variant):
    RP = L("report")
    levels = R("detail_levels_brief" if variant == "brief" else "detail_levels")
    order = level_order()
    picked = [c for c in sorted(sub, key=lambda c: (order.index(c["level"]), -c["score"])) if c["level"] in levels]
    picked = sorted(picked[:R("detail_max")], key=lambda c: c["id"])
    if not picked:
        return []
    blocks = [H(RP["s_detail"], new_page=True)]
    for c in picked:
        blocks += detail_block(c, data, data["refs"], eff, R("excerpt_chars"))
    return blocks


def sec_scope(data, sub):
    RP = L("report")
    sp = R("matrix_split")
    cap = R("matrix_items_max")
    quads = [[], [], [], []]           # 左上 右上 左下 右下（纵轴重要度、横轴影响面）
    for c in sorted(sub, key=lambda c: -c["score"]):
        hi_i, hi_m = c["importance"] >= sp["importance"], c["impact"] >= sp["impact"]
        k = (0 if hi_i else 2) + (1 if hi_m else 0)
        quads[k].append(short(c))
    qs = []
    for k, label in enumerate(RP["quadrants"]):
        title, _, action = label.partition("：")
        items = quads[k][:cap] + ([RP["more"].format(n=len(quads[k]))] if len(quads[k]) > cap else [])
        qs.append({"title": title, "items": items or [RP["empty"]], "action": action})
    blocks = [H(RP["s_scope"]),
              {"type": "matrix", "quadrants": qs, "x_label": RP["matrix_x"], "y_label": RP["matrix_y"],
               "caption": RP["matrix_title"]}]
    refs = [r for r in data["refs"] if r["change_id"] in {c["id"] for c in sub}]
    if refs:
        M, A = L("match"), L("match_action")
        merged = {}
        for r in refs:
            k = r["doc_id"]
            m = merged.setdefault(k, dict(r, changes=[]))
            m["changes"].append(r["change_id"])
            if r["match"] == "stale":
                m["match"], m["evidence"] = "stale", r["evidence"]
        rows = [[clip(m["title"], 22), m["type"] or "—", m["owner"] or _todo(), M[m["match"]], clip(m["evidence"], 40),
                 "、".join(sorted(set(m["changes"]))), A[m["match"]]]
                for m in sorted(merged.values(), key=lambda m: (m["match"] != "stale", m["title"]))]
        blocks.append({"type": "table", "caption": RP["s_scope"], "columns": RP["refs_cols"], "rows": rows})
    else:
        blocks.append({"type": "callout", "kind": "warning", "text": RP["refs_none"]})
    if not data["meta"].get("refs", {}).get("docs_scanned") and data.get("queries"):
        P = RP["query_purpose"]
        blocks.append({"type": "table", "caption": RP["queries_title"], "columns": RP["queries_cols"],
                       "rows": [[q["change_id"], P.get(q["purpose"], q["purpose"]), q["query"]] for q in data["queries"][:20]]})
    return blocks


def sec_plan(data, eff):
    RP = L("report")
    s = data["summary"]
    blocks = [H(RP["s_plan"])]
    plan = s["plan"]
    if eff and plan:
        dues = {}
        for p in plan:
            if p.get("offset") is not None:
                d = eff + dt.timedelta(days=p["offset"])
                dues[d] = dues.get(d, 0) + 1
        nodes = [{"time": fmt_date(today()), "title": RP["timeline_today"]}]
        for d in sorted(x for x in dues if x != eff)[:3]:
            nodes.append({"time": fmt_date(d), "title": RP["timeline_due"].format(n=dues[d])})
        nodes.append({"time": fmt_date(eff), "title": RP["timeline_effective"]})
        nodes.sort(key=lambda n: n["time"])
        blocks.append({"type": "timeline", "nodes": nodes, "current": 0})
    if plan:
        blocks.append({"type": "table", "caption": RP["s_plan"], "columns": RP["plan_cols"],
                       "rows": [[p["action"], p["owner"], due_text(p, eff), "、".join(p["changes"]), level_name(p["level"])]
                                for p in plan], "highlight_col": 2})
    sla = imp().get("level_sla", {})
    if sla:
        blocks.append({"type": "table", "caption": RP["sla_title"], "columns": RP["sla_cols"],
                       "rows": [[level_name(lv), sla.get(lv, "")] for lv in level_order()]})
    return blocks


def sec_compliance(notes):
    RP = L("report")
    blocks = [H(RP["s_compliance"]),
              {"type": "checklist", "items": [{"text": t, "note": n, "required": True} for t, n in RP["compliance_items"]]}]
    if notes.get("notice"):
        blocks.append({"type": "callout", "kind": "warning", "title": RP["notice_title"], "text": notes["notice"]})
    return blocks


def sec_appendix(data, sub, live, notes):
    RP = L("report")
    meta = data["meta"]
    blocks = []
    minor = [c for c in live if c.get("minor")]
    if minor:
        blocks += [H(RP["s_appendix_minor"], new_page=True),
                   {"type": "table", "columns": RP["minor_cols"],
                    "rows": [[c["id"], clip(c["location"], 20) or "—",
                              clip(c["old"]["text"] if c.get("old") else RP["empty"], 40),
                              clip(c["new"]["text"] if c.get("new") else RP["empty"], 40)] for c in minor]}]
    blocks += [H(RP["s_appendix_all"], new_page=not minor),
               {"type": "table", "columns": RP["all_cols"],
                "rows": [[c["id"], clip(c["location"], 20) or "—", type_name(c["type"]) + ("（%s）" % L("minor") if c.get("minor") else ""),
                          c["category_name"], c["importance"], c["impact"], c["score"], c["level_name"]] for c in live]}]
    lv = R("levels")
    rule_txt = "、".join(RP["level_rule"].format(th=th, name=level_name(n)) for n, th in lv[:-1]) + \
        "、" + RP["level_rest"].format(name=level_name(lv[-1][0]))
    w = meta["weights"]
    method = [[k, v.format(wi=w["importance"], wm=w["impact"], levels=rule_txt)] for k, v in RP["method_items"]]
    refm = meta.get("refs", {})
    srcs = [RP["source_old"].format(file=meta["old"]["file"], label=meta["old"]["label"]),
            RP["source_new"].format(file=meta["new"]["file"], label=meta["new"]["label"])]
    srcs.append(RP["source_corpus"].format(n=refm.get("docs_scanned"), paths="、".join(map(os.path.basename, refm.get("corpus", []))))
                if refm.get("docs_scanned") else RP["source_none"])
    if meta.get("effective_date"):
        srcs.append(RP["effective"].format(d=meta["effective_date"]))
    srcs += notes.get("sources", [])
    blocks += [H(RP["s_method"]), {"type": "table", "columns": RP["method_head"], "rows": method, "widths": [3.0, 13.4]},
               H(RP["sources_title"], 2), {"type": "bullets", "items": srcs},
               {"type": "signoff", "roles": RP["signoff_roles"]}]
    return blocks


def build_report(data, notes, variant, style):
    meta = data["meta"]
    eff = parse_date(meta.get("effective_date")) if meta.get("effective_date") else None
    live = [c for c in data["changes"] if not c.get("ignored")]
    sub = [c for c in live if not c.get("minor")]
    blocks = sec_summary(data, notes, sub) + sec_overview(data, sub) + sec_detail(data, sub, eff, variant)
    if variant != "brief":
        blocks += sec_scope(data, sub)
    blocks += sec_plan(data, eff) + sec_compliance(notes)
    if variant != "brief":
        blocks += sec_appendix(data, sub, live, notes)
    m = {"title": notes.get("title") or L("title", doc=meta["doc"]),
         "subtitle": L("subtitle", old=meta["old"]["label"], new=meta["new"]["label"]),
         "short_title": L("short_title", doc=meta["doc"]), "category": L("doc_category"), "doc_type": "impact",
         "date": meta.get("analysed"), "toc": variant != "brief"}
    for k in ("department", "audience", "confidentiality", "version", "doc_no"):
        if notes.get(k):
            m[k] = notes[k]
    if style:
        m["style"] = style
    for k in ("brand", "fonts", "config"):
        if notes.get(k):
            m[k] = notes[k]
    return {"meta": m, "blocks": blocks}


def build_tracker(data, notes):
    T = L("tracker")
    RP = L("report")
    meta = data["meta"]
    eff = parse_date(meta.get("effective_date")) if meta.get("effective_date") else None
    win = R("default_window_days")
    base = eff or (today() + dt.timedelta(days=win))
    live = [c for c in data["changes"] if not c.get("ignored") and not c.get("minor")]
    order = level_order()
    st = L("status")
    owners = notes.get("owners", {})
    lv_rules = [{"type": "text", "value": level_name(order[0]), "style": "bad"},
                {"type": "text", "value": level_name(order[1]), "style": "warn"}]
    changes_sheet = {"type": "table", "name": T["sheet_changes"], "title": T["sheet_changes"],
                     "columns": [{"name": T["change_cols"][0], "width": 7}, {"name": T["change_cols"][1], "wrap": True, "width": 22},
                                 {"name": T["change_cols"][2], "width": 12}, {"name": T["change_cols"][3], "wrap": True, "width": 48},
                                 {"name": T["change_cols"][4], "align": "center", "options": [level_name(x) for x in order], "rule": lv_rules},
                                 {"name": T["change_cols"][5], "format": "int", "databar": True},
                                 {"name": T["change_cols"][6], "input": True},
                                 {"name": T["change_cols"][7], "options": list(st.values()), "input": True}],
                     "rows": [[c["id"], clip(c["location"], 30), c["category_name"], clip(c["desc"], 80), c["level_name"],
                               c["score"], owners.get(c["actions"][0]["owner"], "") if c["actions"] else "", st["todo"]]
                              for c in sorted(live, key=lambda c: (order.index(c["level"]), c["id"]))],
                     "freeze_first_col": True}
    tasks = []
    for i, p in enumerate(data["summary"]["plan"], 1):
        end = base + dt.timedelta(days=p["offset"] or 0)
        start = min(today(), end)              # 时限已过的保留真实日期，甘特表会自动标“逾期”
        tasks.append({"id": "A%02d" % i, "task": p["action"], "dept": p["owner"], "owner": owners.get(p["owner"], ""),
                      "start": fmt_date(start), "end": fmt_date(end)})
    sheets = [{"type": "cover", "name": T["sheet_cover"],
               "purpose": T["cover_purpose"], "how_to": T["how_to"]}, changes_sheet]
    if tasks:
        g = {"type": "gantt", "name": T["sheet_tasks"], "title": T["sheet_tasks"], "tasks": tasks,
             "unit": "week" if (max(_d(t["end"]) for t in tasks) - today()).days > 45 else "day"}
        if not eff:
            g["note"] = T["no_date"].format(n=win)
        sheets.append(g)
    refs = [r for r in data["refs"] if r["change_id"] in {c["id"] for c in live}]
    if refs:
        M, A = L("match"), L("match_action")
        sheets.append({"type": "table", "name": T["sheet_refs"], "title": T["sheet_refs"],
                       "columns": [{"name": T["ref_cols"][0], "wrap": True, "width": 30}, {"name": T["ref_cols"][1]},
                                   {"name": T["ref_cols"][2], "input": True}, {"name": T["ref_cols"][3], "width": 18},
                                   {"name": T["ref_cols"][4]}, {"name": T["ref_cols"][5], "align": "center"},
                                   {"name": T["ref_cols"][6], "options": list(st.values()), "input": True}],
                       "rows": [[r["title"], r["type"], r["owner"], M[r["match"]], r["change_id"], A[r["match"]], st["todo"]]
                                for r in sorted(refs, key=lambda r: (r["match"] != "stale", r["title"]))]})
    m = {"title": T["title"].format(doc=meta["doc"]), "kind": "impact", "date": meta.get("analysed"),
         "category": L("doc_category")}
    for k in ("department", "confidentiality", "brand", "fonts", "config"):
        if notes.get(k):
            m[k] = notes[k]
    return {"meta": m, "sheets": sheets}


def _d(s):
    return parse_date(s)


# ---------------- 渲染 ----------------
def _passthrough(a):
    out = []
    for c in a.config:
        out += ["--config", c]
    for k in ("font_cn", "font_en", "font_num", "font_mode", "font_scale"):
        v = getattr(a, k, None)
        if v is not None:
            out += ["--" + k.replace("_", "-"), str(v)]
    return out


def _script(skill, name):
    p = os.path.normpath(os.path.join(HERE, "..", "..", skill, "scripts", name))
    if not os.path.exists(p):
        sys.exit("找不到 %s（请把 %s 与 change-impact 放在同一级目录）" % (p, skill))
    return p


def _run(cmd):
    print("运行：" + " ".join(os.path.basename(c) if i < 2 else c for i, c in enumerate(cmd)))
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：生成 Word 报告与 Excel 跟踪表")
    ap.add_argument("scored")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--notes")
    ap.add_argument("--name", help="输出文件名前缀，默认“<文档名>_变更影响分析”")
    ap.add_argument("--variant", choices=["full", "brief"], default="full")
    ap.add_argument("--style", help="Word 风格名（默认按 themes.word.default_by_type.impact）")
    ap.add_argument("--no-tracker", action="store_true")
    ap.add_argument("--render", action="store_true", help="直接渲染 .docx / .xlsx 并质检")
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    data = load_json(a.scored)
    if "summary" not in data:
        sys.exit("请先运行 score.py（输入应为 scored.json）")
    notes = load_json(a.notes) if a.notes else {}
    name = a.name or "%s_%s" % (data["meta"]["doc"], L("doc_category"))
    os.makedirs(a.out_dir, exist_ok=True)
    FN = L("tracker")["files"]
    rp = os.path.join(a.out_dir, name + FN["report_json"])
    save_json(build_report(data, notes, a.variant, a.style), rp)
    print("报告内容：%s" % rp)
    tp = None
    if not a.no_tracker:
        tp = os.path.join(a.out_dir, name + FN["tracker_json"])
        save_json(build_tracker(data, notes), tp)
        print("跟踪表内容：%s" % tp)
    if not a.render:
        print("加 --render 可直接生成 .docx / .xlsx；也可人工调整内容 JSON 后用 kb-to-word / kb-to-excel 渲染")
        return
    extra = _passthrough(a)
    cfg_only = [x for c in a.config for x in ("--config", c)]       # 质检只认 --config
    docx = os.path.join(a.out_dir, name + ".docx")
    code = _run([sys.executable, _script("kb-to-word", "render_docx.py"), rp, docx] + extra)
    if code == 0:
        _run([sys.executable, _script("kb-to-word", "review_docx.py"), docx, "--doc-type", "impact",
              "--out", os.path.join(a.out_dir, name + FN["review"])] + cfg_only)
    if tp:
        code2 = _run([sys.executable, _script("kb-to-excel", "render_xlsx.py"), tp,
                      os.path.join(a.out_dir, name + FN["tracker"])] + extra)
        code = code or code2
    sys.exit(code)


if __name__ == "__main__":
    main()
