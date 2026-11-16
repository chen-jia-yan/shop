#!/usr/bin/env python3
"""检查入库信息并生成提交审核用的文件。

用法:
    python build_ingest.py submission.json --chunks chunks.json --check
    python build_ingest.py submission.json --chunks chunks.json --out /tmp/outputs/

只用 Python 标准库。退出码: 0 = 无阻断问题；1 = 有必须先处理的问题
"""
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = ("title", "summary", "category", "owner")
BROAD_TAGS = {"制度", "文件", "公司", "文档", "资料", "规定", "通知"}


def check(s, chunks):
    blocking, warnings = [], []
    for k in REQUIRED:
        if not str(s.get(k, "")).strip():
            blocking.append(f"缺少必填字段：{k}")
    if not chunks:
        blocking.append("没有正文片段（chunks 为空）")
    if s.get("confirmed") is not True:
        blocking.append("用户尚未确认（confirmed 不为 true），不能提交")

    title = s.get("title", "")
    if re.search(r"终版|最终版|v\d+|副本|copy|草稿", title, re.I):
        warnings.append(f"标题含版本或草稿字样：{title}，建议使用正式标题")
    n = len(s.get("summary", ""))
    if n and not 40 <= n <= 400:
        warnings.append(f"摘要 {n} 字，建议 3-5 句（约 80-250 字）")
    tags = s.get("tags", [])
    if not 3 <= len(tags) <= 8:
        warnings.append(f"标签 {len(tags)} 个，建议 3-8 个")
    broad = [t for t in tags if t in BROAD_TAGS]
    if broad:
        warnings.append(f"标签过宽：{'、'.join(broad)}")
    if s.get("duplicate_of") and not s.get("replaces_doc_id"):
        warnings.append(f"查重发现相似文档 {s['duplicate_of']}，确认是新增还是更新（填 replaces_doc_id）")
    if s.get("sensitive_kept"):
        warnings.append(f"保留了敏感信息：{'、'.join(s['sensitive_kept'])}（已经用户确认）")
    return blocking, warnings


def to_markdown(s, chunks):
    lines = [f"# {s['title']}", "",
             f"- 分类：{s['category']}",
             f"- 标签：{'、'.join(s.get('tags', []))}",
             f"- 负责人：{s['owner']}"]
    for k, label in (("effective_date", "生效日期"), ("expire_date", "有效期至"), ("source_file", "原文件")):
        if s.get(k):
            lines.append(f"- {label}：{s[k]}")
    if s.get("replaces_doc_id"):
        lines.append(f"- 替换文档：{s['replaces_doc_id']}" + (f"（{s['change_note']}）" if s.get("change_note") else ""))
    lines += ["", "## 摘要", "", s["summary"], "", "## 正文", ""]
    last = None
    for c in chunks:
        if c["section"] != last and c["section"] != "（正文）":
            lines += [f"### {c['section']}", ""]
            last = c["section"]
        lines += [c["text"], ""]
    lines += ["---", "", "> 提交后需审核通过才生效。"]
    return "\n".join(lines)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")[:60]


def main():
    ap = argparse.ArgumentParser(description="生成文件入库提交")
    ap.add_argument("submission")
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.submission, encoding="utf-8") as f:
        s = json.load(f)
    with open(args.chunks, encoding="utf-8") as f:
        chunks = json.load(f)

    blocking, warnings = check(s, chunks)
    print(json.dumps({"blocking": blocking, "warnings": warnings}, ensure_ascii=False, indent=2))
    if blocking:
        print("\n有必须先处理的问题，未生成文件。", file=sys.stderr)
        sys.exit(1)
    if args.check or not args.out:
        sys.exit(0)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"{safe_name(s['title'])}_入库"
    payload = {k: v for k, v in s.items() if k != "confirmed"}
    payload.update({"chunks": chunks, "status": "pending_review"})
    (out / f"{base}.md").write_text(to_markdown(s, chunks), encoding="utf-8")
    (out / f"{base}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已生成：{out / (base + '.md')}\n已生成：{out / (base + '.json')}")


if __name__ == "__main__":
    main()
