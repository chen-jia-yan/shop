# -*- coding: utf-8 -*-
"""
变更影响分析 —— 一键流程（手动或由 TAP 事件自动触发）

  python run.py prepare --event event.json --work work/
      比对 → 查候选受影响内容 → 自动初筛 → 找相似判例，生成“工作包”：
        work/workpack.md               给模型看的待判断清单（变更、复核提示、候选内容、参考判例、补查语句）
        work/judgments.template.json   判断文件骨架（每条实质变更、每篇候选内容各一项）
      然后由模型按 reference/methods.md 写 work/judgments.json。
  python run.py finish --work work/ --out-dir out/ [--notes notes.json] [--render] [--variant brief]
      护栏检查 → 并入判断定级 → 生成报告、跟踪表、修订建议稿。

event.json（TAP 在新版本进入“待审核”时推送；也可以手写，格式见 reference/auto-trigger.md）：
  {"trigger": "review_submitted", "doc": {"id": "...", "name": "..."},
   "old": {"file": "...", "label": "v2.3"}, "new": {"file": "...", "label": "v3.0", "effective_date": "2026-01-01"},
   "source": "产品条款修订", "scope_terms": ["..."], "exclude": ["..."], "corpus": ["知识库导出.jsonl"]}
文件路径相对 event.json 所在目录。trigger 不为 manual 时，报告按“审核前预分析”出具。

边界：本流程只读文档和知识库、只产出分析材料；不改审核状态、不改知识库、不发通知。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _tap import add_cli_args, configure      # noqa: E402

from ci_common import L, clip, level_name, load_json, save_json   # noqa: E402


def _py(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script)] + [str(x) for x in args]
    print("运行：%s %s" % (script, " ".join(str(x) for x in args)))
    code = subprocess.call(cmd)
    if code not in (0,):
        sys.exit("%s 失败（退出码 %d），流程停止" % (script, code))


def _cfg(a):
    out = []
    for c in a.config:
        out += ["--config", c]
    return out


def prepare(a):
    ev_path = os.path.abspath(a.event)
    ev = load_json(ev_path)
    base = os.path.dirname(ev_path)
    P = lambda p: p if os.path.isabs(p) else os.path.join(base, p)          # noqa: E731
    for k in ("old", "new"):
        if not (ev.get(k) or {}).get("file"):
            sys.exit("event.json 缺少 %s.file：拿不到%s就不能做变更分析（不要凭记忆补）" % (k, "旧版" if k == "old" else "新版"))
    w = os.path.abspath(a.work)
    os.makedirs(w, exist_ok=True)
    shutil.copyfile(ev_path, os.path.join(w, "event.json"))
    doc = (ev.get("doc") or {}).get("name") or os.path.splitext(os.path.basename(ev["new"]["file"]))[0]
    args = [P(ev["old"]["file"]), P(ev["new"]["file"]), "-o", os.path.join(w, "changes.json"), "--doc-name", doc,
            "--old-label", ev["old"].get("label", ""), "--new-label", ev["new"].get("label", "")]
    if ev["new"].get("effective_date"):
        args += ["--effective-date", ev["new"]["effective_date"]]
    if ev.get("source"):
        args += ["--source", ev["source"]]
    _py("diff_docs.py", *(args + _cfg(a)))
    fr = [os.path.join(w, "changes.json"), "-o", os.path.join(w, "refs.json")]
    for c in ev.get("corpus") or []:
        fr += ["--corpus", P(c)]
    for s in ev.get("scope_terms") or []:
        fr += ["--scope-term", s]
    for x in (ev.get("exclude") or []) + [doc]:
        fr += ["--exclude", x]
    _py("find_refs.py", *(fr + _cfg(a)))
    _py("score.py", os.path.join(w, "changes.json"), "--refs", os.path.join(w, "refs.json"),
        "-o", os.path.join(w, "prior.json"), *_cfg(a))
    _py("experience.py", "find", os.path.join(w, "prior.json"), "-o", os.path.join(w, "precedents.json"), *_cfg(a))
    configure("impact", a)
    prior = load_json(os.path.join(w, "prior.json"))
    refs = load_json(os.path.join(w, "refs.json"))
    prec = load_json(os.path.join(w, "precedents.json"))
    save_json(template(prior, refs), os.path.join(w, "judgments.template.json"))
    with open(os.path.join(w, "workpack.md"), "w", encoding="utf-8") as f:
        f.write(workpack(ev, prior, refs, prec))
    print("工作包：%s" % os.path.join(w, "workpack.md"))
    print("下一步：按 reference/methods.md 读原文，把 judgments.template.json 填好另存为 judgments.json，再运行 run.py finish")


def template(prior, refs):
    ch = {}
    for c in prior["changes"]:
        if c.get("minor"):
            continue
        ch[c["id"]] = {"verdict": "substantive", "level": None, "category": None, "direction": None, "applies": None,
                       "summary": c["desc"], "reasoning": "", "evidence": [], "confidence": None,
                       "actions": [], "comment": "", "lesson": ""}
        if c.get("review_flags"):
            ch[c["id"]]["diff_review"] = ""
    docs = {}
    for r in refs["refs"]:
        d = docs.setdefault(r["doc_id"], {"changes": [], "verdict": None, "applies": None, "disposal": None,
                                          "switch_date": None, "revisions": [], "reasoning": "", "evidence": [],
                                          "confidence": None, "lesson": ""})
        if r["change_id"] not in d["changes"]:
            d["changes"].append(r["change_id"])
        sent = r.get("sentence") or r["evidence"]
        if r["match"] == "stale" and not any(x["original"] == sent for x in d["revisions"]):
            d["revisions"].append({"original": sent, "proposed": ""})
    return {"analyst": "", "changes": ch, "refs": docs, "verify_questions": [], "lessons": []}


def workpack(ev, prior, refs, prec):
    m = prior["meta"]
    s = prior["summary"]
    F = L("flags")
    out = ["# 变更影响分析工作包：《%s》%s → %s" % (m["doc"], m["old"]["label"], m["new"]["label"]), "",
           "- 触发：%s%s" % (ev.get("trigger", "manual"), "（审核前预分析）" if ev.get("trigger", "manual") != "manual" else ""),
           "- 生效日期：%s" % (m.get("effective_date") or "【待补充】"),
           "- 变更来源：%s" % (m.get("source") or "—"),
           "- 识别变更 %d 处：实质 %d、措辞调整 %d；候选受影响内容 %d 篇（扫描 %d 篇）" % (
               s["total"], s["substantive"], s["minor"], len({r["doc_id"] for r in refs["refs"]}),
               refs["meta"].get("docs_scanned", 0)), ""]
    for wmsg in m.get("warnings") or []:
        out.append("> 注意：" + wmsg)
    out += ["", "## 你要做的", "",
            "1. 读 `reference/methods.md`（怎么判断）和 `reference/boundaries.md`（不能做什么）。",
            "2. 逐条读下面每条变更的修订前后原文（changes.json 的 old.text / new.text），判断性质、级别、对谁生效。初筛只是起点。",
            "3. 逐篇读候选内容全文（refs.json 的 doc_text），判断是否真的过时、对存量是否仍有效、怎么处置，写修订建议稿。",
            "4. 有“复核提示”的，按方法第 4 节读原文确认，把结论写进 diff_review。",
            "5. 看“参考判例”：情况相似就借鉴，不相似就说明为什么不同；不要机械套用。",
            "6. 为每条重大 / 较大变更写 1-2 个回测问题（verify_questions）。",
            "7. 存为 judgments.json，运行 `python scripts/judgments.py check ...` 自查，再运行 `run.py finish`。", "",
            "## 变更清单（按初筛级别）", "",
            "| 编号 | 位置 | 初筛 | 内容 | 复核提示 | 参考判例 |", "|---|---|---|---|---|---|"]
    order = [lv for lv, _ in prior["meta"]["levels"]]
    for c in sorted([c for c in prior["changes"] if not c.get("minor")], key=lambda c: (order.index(c["level"]), c["id"])):
        flags = "；".join(F.get(f["flag"], f["flag"]) + ("（%s）" % f["with"] if f.get("with") else "") for f in c.get("review_flags", []))
        hits = "、".join(h["id"] for h in prec["by_change"].get(c["id"], []))
        out.append("| %s | %s | %s | %s | %s | %s |" % (c["id"], clip(c["location"], 18) or "—", level_name(c["level"]),
                                                     clip(c["desc"], 40).replace("|", "/"), flags or "", hits or ""))
    minor = [c for c in prior["changes"] if c.get("minor")]
    if minor:
        out += ["", "措辞调整 %d 处（%s）：抽查是否有被误判的实质变更，例如“或”改“且”。" % (
            len(minor), "、".join(c["id"] for c in minor[:20]))]
    out += ["", "## 候选受影响内容", "", "| 内容 | 关联变更 | 匹配 | 命中句 |", "|---|---|---|---|"]
    seen = {}
    for r in refs["refs"]:
        seen.setdefault(r["doc_id"], []).append(r)
    for did, rs in seen.items():
        r0 = sorted(rs, key=lambda r: r["match"] != "stale")[0]
        out.append("| %s（%s） | %s | %s | %s |" % (clip(r0["title"], 24), did, "、".join(sorted({r["change_id"] for r in rs})),
                                                L("match")[r0["match"]], clip(r0["evidence"], 50).replace("|", "/")))
    if not seen:
        out.append("| （没有候选：未提供语料，或关键词没有匹配上。用下方检索语句和语义 / 图谱检索补查） | | | |")
    if refs.get("queries"):
        out += ["", "## 建议补查（TAP Retrieval / qa_advance）", ""]
        out += ["- %s：%s" % (q["change_id"], q["query"]) for q in refs["queries"][:30]]
    if prec.get("general"):
        out += ["", "## 通用经验", ""] + ["- %s：%s" % (g["id"], g["lesson"]) for g in prec["general"]]
    if prec.get("by_change"):
        out += ["", "## 参考判例", ""]
        shown = set()
        for hits in prec["by_change"].values():
            for h in hits:
                if h["id"] in shown:
                    continue
                shown.add(h["id"])
                out.append("- **%s**（%s）%s → %s。%s" % (h["id"], h.get("source", ""), clip(h.get("change") or h.get("content"), 40),
                                                       json.dumps(h.get("judgment", {}), ensure_ascii=False), h["lesson"]))
    return "\n".join(out) + "\n"


def finish(a):
    w = os.path.abspath(a.work)
    j = a.judgments or os.path.join(w, "judgments.json")
    if not os.path.exists(j):
        sys.exit("找不到 %s：先按工作包写好分析判断" % j)
    ev = load_json(os.path.join(w, "event.json")) if os.path.exists(os.path.join(w, "event.json")) else {}
    sc = [os.path.join(w, "changes.json"), "--refs", os.path.join(w, "refs.json"), "--judgments", j,
          "-o", os.path.join(w, "scored.json")]
    if a.notes:
        sc += ["--notes", a.notes]
    _py("score.py", *(sc + _cfg(a)))
    br = [os.path.join(w, "scored.json"), "--out-dir", a.out_dir, "--variant", a.variant]
    if a.notes:
        br += ["--notes", a.notes]
    if a.render:
        br.append("--render")
    if ev.get("trigger", "manual") != "manual":
        br.append("--precheck")
    _py("build_report.py", *(br + _cfg(a)))


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：一键流程")
    ap.add_argument("cmd", choices=["prepare", "finish"])
    ap.add_argument("--event", help="prepare：事件 / 任务描述 JSON")
    ap.add_argument("--work", required=True, help="工作目录")
    ap.add_argument("--judgments", help="finish：分析判断，默认 <work>/judgments.json")
    ap.add_argument("--notes")
    ap.add_argument("--out-dir", help="finish：输出目录")
    ap.add_argument("--variant", choices=["full", "brief"], default="full")
    ap.add_argument("--render", action="store_true")
    add_cli_args(ap)
    a = ap.parse_args()
    if a.cmd == "prepare":
        if not a.event:
            sys.exit("prepare 需要 --event")
        prepare(a)
    else:
        if not a.out_dir:
            sys.exit("finish 需要 --out-dir")
        finish(a)


if __name__ == "__main__":
    main()
