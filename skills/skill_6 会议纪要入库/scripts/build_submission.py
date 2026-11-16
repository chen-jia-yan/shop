#!/usr/bin/env python3
"""检查会议纪要草稿，并生成提交审核用的文件。

用法:
    python build_submission.py draft.json --check          只检查，不生成文件
    python build_submission.py draft.json --out outputs/   检查并生成 .md 和 .json

只用 Python 标准库。
退出码: 0 = 无阻断问题；1 = 有必须先处理的问题（缺必填字段等）
"""
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = ("title", "date", "category", "summary")

# 可能的敏感信息，命中后提示用户确认（不会自动删除）
SENSITIVE = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "手机号"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "身份证号"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "邮箱地址"),
    (re.compile(r"薪资|工资|薪酬|年薪|月薪|奖金|绩效(评价|评分|等级|打分)"), "薪酬/绩效"),
    (re.compile(r"(合同|报价|成交)\S{0,6}?\d+(\.\d+)?\s*(万|亿|元)"), "金额"),
]


def iter_texts(d):
    yield d.get("summary", "")
    for x in d.get("decisions", []):
        yield x.get("content", ""); yield x.get("basis", "")
    for x in d.get("open_items", []):
        yield x.get("content", ""); yield x.get("note", "")
    for x in d.get("action_items", []):
        yield x.get("task", "")


def check(d):
    blocking, warnings = [], []
    for k in REQUIRED:
        if not str(d.get(k, "")).strip():
            blocking.append(f"缺少必填字段：{k}")
    if not any(d.get(k) for k in ("decisions", "open_items", "action_items")):
        blocking.append("决定、待定、待办都为空，没有可入库的内容")

    for i, x in enumerate(d.get("decisions", []), 1):
        if not x.get("content", "").strip():
            blocking.append(f"第 {i} 条决定内容为空")
        if not x.get("basis", "").strip():
            warnings.append(f"决定 {i}「{x.get('content', '')[:20]}」没有写依据（谁提出、谁同意）")

    for i, x in enumerate(d.get("action_items", []), 1):
        miss = [n for k, n in (("owner", "负责人"), ("due", "截止时间")) if not x.get(k, "").strip()]
        if miss:
            warnings.append(f"待办 {i}「{x.get('task', '')[:20]}」缺{'、'.join(miss)}")

    found = {}
    for t in iter_texts(d):
        for pat, label in SENSITIVE:
            for m in pat.finditer(t or ""):
                found.setdefault(label, set()).add(m.group(0))
    for label, hits in found.items():
        warnings.append(f"可能含敏感信息（{label}）：{'、'.join(sorted(hits))[:60]}，请确认是否入库")

    for term in d.get("uncertain_terms", []):
        warnings.append(f"待确认的名称：{term}")
    return blocking, warnings


def to_markdown(d):
    lines = [f"# {d['title']}", "",
             f"- 日期：{d['date']}",
             f"- 分类：{d['category']}"]
    if d.get("attendees"):
        lines.append(f"- 参会人：{'、'.join(d['attendees'])}")
    if d.get("source"):
        lines.append(f"- 来源：{d['source']}")
    lines += ["", "## 概要", "", d["summary"], ""]

    if d.get("decisions"):
        lines += ["## 已决定", ""]
        for i, x in enumerate(d["decisions"], 1):
            lines.append(f"{i}. **{x['content']}**")
            if x.get("basis"):
                lines.append(f"   - 依据：{x['basis']}")
        lines.append("")

    if d.get("open_items"):
        lines += ["## 待定事项", ""]
        for i, x in enumerate(d["open_items"], 1):
            lines.append(f"{i}. {x['content']}" + (f"（{x['note']}）" if x.get("note") else ""))
        lines.append("")

    if d.get("action_items"):
        lines += ["## 待办", "", "| # | 事项 | 负责人 | 截止时间 |", "|---|---|---|---|"]
        for i, x in enumerate(d["action_items"], 1):
            lines.append(f"| {i} | {x.get('task', '')} | {x.get('owner') or '待定'} | {x.get('due') or '待定'} |")
        lines.append("")

    lines += ["---", "", "> 本纪要由会议记录整理，提交后需审核通过才生效。"]
    return "\n".join(lines)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")[:60]


def main():
    ap = argparse.ArgumentParser(description="检查会议纪要草稿并生成提交文件")
    ap.add_argument("draft", help="草稿 JSON")
    ap.add_argument("--check", action="store_true", help="只检查，不生成文件")
    ap.add_argument("--out", help="输出目录")
    args = ap.parse_args()

    with open(args.draft, encoding="utf-8") as f:
        d = json.load(f)

    blocking, warnings = check(d)
    print(json.dumps({"blocking": blocking, "warnings": warnings}, ensure_ascii=False, indent=2))

    if blocking:
        print("\n有必须先处理的问题，未生成文件。", file=sys.stderr)
        sys.exit(1)
    if args.check or not args.out:
        sys.exit(0)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"{safe_name(d['title'])}_{safe_name(d['date'])}"
    payload = dict(d, review_status="pending_review")
    (out / f"{base}.md").write_text(to_markdown(d), encoding="utf-8")
    (out / f"{base}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已生成：{out / (base + '.md')}\n已生成：{out / (base + '.json')}")


if __name__ == "__main__":
    main()
