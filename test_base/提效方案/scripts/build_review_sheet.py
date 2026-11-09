"""第 8 步：生成审核表 review.xlsx（编辑用）和 review.html（带截图的只读预览）。

用法：
    python scripts/build_review_sheet.py --drafts triage_runs/<run_id>/drafts.json \
        --groups triage_runs/<run_id>/groups.json --duplicates triage_runs/<run_id>/duplicates.json \
        --out-dir triage_runs/<run_id>/ [--force]

说明：
- 已存在 review.xlsx 时默认不覆盖，避免冲掉审核人已经做的修改；确需重建时加 --force（旧文件会备份）。
- “审核状态”列有下拉选项：待审核 / 通过 / 驳回 / 追加到已有单，初始全部为“待审核”。
- 第二个工作表“全部分组”列出所有分组（包括不需要建单的），便于整体查看。
"""
from __future__ import annotations

import argparse
import html
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from common import CATEGORIES, REVIEW_STATUSES, read_json, setup_logging

log = setup_logging()

COLUMNS = [
    ("group_id", 9, False), ("审核状态", 12, True), ("已有单号", 12, True), ("疑似重复", 28, False),
    ("分类", 12, False), ("规则状态", 10, False), ("处理方", 10, False),
    ("人工分类", 14, True), ("修改原因", 20, True),
    ("Summary", 50, True), ("Description", 80, True), ("Environment", 36, True),
    ("Priority", 10, True), ("Labels", 26, True), ("Components", 14, True), ("Assignee（邮箱）", 22, True),
    ("受影响用例", 22, False), ("截图", 30, False), ("证据摘要", 50, False), ("推测与待确认", 40, False),
    ("审核备注", 30, True),
]
EDITABLE_FILL = PatternFill("solid", fgColor="FFF8E1")
HEADER_FILL = PatternFill("solid", fgColor="E0E0E0")


def dup_text(dups: dict, gid: str) -> str:
    r = (dups.get("results") or {}).get(gid) or {}
    if r.get("error"):
        return f"查重失败：{r['error'][:80]}"
    if r.get("note"):
        return r["note"]
    return "\n".join(f"{c['key']}（{c['status']}，相似度 {c['similarity']}）{c['summary']}"
                     for c in r.get("candidates", [])) or "未发现"


def inference_text(draft: dict) -> str:
    return "\n".join(f"- {c['text']}" for c in draft.get("claims", []) if c.get("type") == "inference")


def evidence_text(group: dict, limit: int = 12) -> str:
    lines = [f"{e['id']} [{e['kind']}] {e['case_id']}: {e['content'][:160]}" for e in group["evidence"][:limit]]
    if len(group["evidence"]) > limit:
        lines.append(f"……共 {len(group['evidence'])} 条证据，完整内容见 groups.json")
    return "\n".join(lines)


def build_xlsx(path: Path, drafts: list, groups: dict, dups: dict, cfg_components: list) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "审核"
    for col, (name, width, editable) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col, value=name + ("（可编辑）" if editable else ""))
        cell.font = Font(bold=False)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "C2"

    dv = DataValidation(type="list", formula1='"' + ",".join(REVIEW_STATUSES) + '"', allow_blank=False)
    dv_cat = DataValidation(type="list", formula1='"' + ",".join(CATEGORIES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    ws.add_data_validation(dv_cat)

    for r, d in enumerate(drafts, 2):
        g = groups[d["group_id"]]
        values = [
            g["group_id"], "待审核", "", dup_text(dups, g["group_id"]),
            g["category_cn"], g["status"], g["owner"], "", "",
            d["summary"], d["description"], d.get("environment") or g["environment"],
            d.get("priority") or g["suggested_priority"],
            ",".join(d.get("labels") or []), ",".join(d.get("components") or cfg_components), "",
            "\n".join(g["case_ids"]), "\n".join(Path(p).name for p in g["screenshots"]),
            evidence_text(g), inference_text(d), "",
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if COLUMNS[c - 1][2]:
                cell.fill = EDITABLE_FILL
        dv.add(ws.cell(row=r, column=2))
        dv_cat.add(ws.cell(row=r, column=8))
        ws.row_dimensions[r].height = 180

    ws2 = wb.create_sheet("全部分组")
    headers = ["group_id", "分类", "规则状态", "处理方", "用例数", "是否建单", "根因提示", "用例", "AI 调整的用例"]
    ws2.append(headers)
    for g in groups.values():
        ws2.append([g["group_id"], g["category_cn"], g["status"], g["owner"], len(g["case_ids"]),
                    "是" if g["needs_jira"] else "否", g["root_cause_hint"], ", ".join(g["case_ids"]),
                    ", ".join(g["ai_adjusted_cases"])])
    for col, w in zip("ABCDEFGHI", [9, 12, 10, 10, 8, 8, 50, 60, 20]):
        ws2.column_dimensions[col].width = w

    ws3 = wb.create_sheet("填写说明")
    for line in [
        "1. 在“审核”表逐行检查，黄色底色的列可以修改。",
        "2. 审核状态：通过 = 按本行内容新建 Jira；追加到已有单 = 在“已有单号”填写的单下追加评论；驳回 = 不提交；待审核 = 不提交。",
        "3. 如果不同意分类，在“人工分类”选择正确类别，并在“修改原因”说明理由。这些记录会用于改进分类规则。",
        "4. Assignee 填写对方的 Atlassian 账号邮箱，留空则不指派。",
        "5. 不要修改 group_id 列，也不要删除或调整行的顺序以外的结构。",
        "6. 审核完成后保存文件，告诉 AI“审核完了，提交”，会先演练，确认后才真正提交。",
    ]:
        ws3.append([line])
    ws3.column_dimensions["A"].width = 120
    wb.save(path)


def build_html(path: Path, drafts: list, groups: dict, dups: dict, run_id: str) -> None:
    esc = html.escape
    rows = []
    for d in drafts:
        g = groups[d["group_id"]]
        shots = "".join(
            f'<a href="{Path(p).resolve().as_uri()}" target="_blank"><img src="{Path(p).resolve().as_uri()}" '
            f'alt="{esc(Path(p).name)}"></a>' for p in g["screenshots"][:6])
        rows.append(f"""
<section>
  <h2>{esc(g['group_id'])} · {esc(g['category_cn'])}（{esc(g['status'])}）· {len(g['case_ids'])} 个用例 · 处理方：{esc(g['owner'])}</h2>
  <p class="summary">{esc(d['summary'])}</p>
  <p class="meta">建议优先级：{esc(d.get('priority') or g['suggested_priority'])} ｜ 疑似重复：{esc(dup_text(dups, g['group_id']))}</p>
  <div class="shots">{shots or '<em>无截图</em>'}</div>
  <details open><summary>Description</summary><pre>{esc(d['description'])}</pre></details>
  <details><summary>证据</summary><pre>{esc(evidence_text(g, 50))}</pre></details>
  <details><summary>Environment</summary><pre>{esc(g['environment'])}</pre></details>
</section>""")
    others = [g for g in groups.values() if not g["needs_jira"]]
    other_rows = "".join(
        f"<tr><td>{esc(g['group_id'])}</td><td>{esc(g['category_cn'])}</td><td>{len(g['case_ids'])}</td>"
        f"<td>{esc(g['root_cause_hint'][:120])}</td><td>{esc(', '.join(g['case_ids'][:15]))}</td></tr>" for g in others)
    page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>回归失败审核预览 {esc(run_id)}</title>
<style>
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:24px;color:#222;max-width:1200px}}
section{{border:1px solid #ddd;padding:12px 16px;margin:16px 0}}
h2{{font-size:16px;margin:0 0 8px}} .summary{{font-size:15px;background:#f5f5f5;padding:6px}}
.meta{{color:#666;font-size:13px}} pre{{white-space:pre-wrap;font-size:13px;background:#fafafa;padding:8px}}
.shots img{{height:140px;margin:4px;border:1px solid #ccc}} table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ddd;padding:4px 6px;font-size:13px;text-align:left}}
</style></head><body>
<h1>回归失败审核预览 · {esc(run_id)}</h1>
<p>本页只读。修改和审核请在 review.xlsx 中进行。生成时间：{datetime.now():%Y-%m-%d %H:%M}</p>
{''.join(rows)}
<h2>不需要建单的分组（{len(others)}）</h2>
<table><tr><th>组</th><th>分类</th><th>用例数</th><th>根因提示</th><th>用例</th></tr>{other_rows}</table>
</body></html>"""
    path.write_text(page, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--duplicates")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--components", default="SYSTEM-QA", help="草稿未指定 Components 时的默认值，逗号分隔")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    drafts = read_json(args.drafts).get("drafts", [])
    gdata = read_json(args.groups)
    groups = {g["group_id"]: g for g in gdata["groups"]}
    dups = read_json(args.duplicates) if args.duplicates and Path(args.duplicates).exists() else {}
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    xlsx = out_dir / "review.xlsx"
    if xlsx.exists():
        if not args.force:
            log.error("review.xlsx 已存在，可能包含审核人的修改。确需重建请加 --force")
            raise SystemExit(1)
        backup = out_dir / f"review.backup-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        shutil.copy2(xlsx, backup)
        log.info("已备份旧审核表：%s", backup)

    unknown = [d.get("group_id") for d in drafts if d.get("group_id") not in groups]
    if unknown:
        log.error("草稿中有不存在的组：%s。请先运行 validate_drafts.py", unknown)
        raise SystemExit(1)

    build_xlsx(xlsx, drafts, groups, dups, [c.strip() for c in args.components.split(",") if c.strip()])
    build_html(out_dir / "review.html", drafts, groups, dups, gdata["run_id"])
    log.info("审核表：%s", xlsx)
    log.info("预览页：%s", out_dir / "review.html")


if __name__ == "__main__":
    main()
