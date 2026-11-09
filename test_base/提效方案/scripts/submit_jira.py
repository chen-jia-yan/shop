"""第 9 步：把审核通过的行提交到 Jira（新建单或在已有单下追加评论），并上传截图。

用法：
    # 查询项目的问题类型和字段 ID（首次配置时运行一次）
    python scripts/submit_jira.py --discover-fields --config config/config.yaml

    # 演练（默认）：只显示将要执行的操作，不写入 Jira
    python scripts/submit_jira.py --review triage_runs/<run_id>/review.xlsx \
        --groups triage_runs/<run_id>/groups.json --config config/config.yaml

    # 真正提交
    python scripts/submit_jira.py ... --confirm

安全措施：
- 只处理“审核状态”为“通过”或“追加到已有单”的行，其他行一律跳过。
- 填写了“人工分类”却没有填写“修改原因”的行会被拒绝。
- 每张新建的单带有标签 triage-<run_id>-<group_id>。提交前先按此标签搜索，已存在就跳过，
  即使 submitted.json 丢失也不会重复建单。
- 提交结果写入 submitted.json；人工修改分类的记录追加到 corrections.jsonl，用于改进规则。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from pathlib import Path

from openpyxl import load_workbook

from common import (CATEGORIES, fail, load_config, mask_pii, now_iso, read_json, setup_logging,
                    write_json)

log = setup_logging()

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
CN_TO_CODE = {v: k for k, v in CATEGORIES.items()}


def read_review(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    ws = wb["审核"]
    headers = [str(c.value or "").replace("（可编辑）", "").strip() for c in ws[1]]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(r):
            continue
        rows.append({h: ("" if v is None else str(v).strip()) for h, v in zip(headers, r)})
    return rows


def safe_label(text: str) -> str:
    return re.sub(r"[^\w.-]+", "-", text).strip("-")


def build_fields(row: dict, group: dict, cfg: dict, run_id: str, category: str,
                 assignee_id: str | None) -> dict:
    jcfg = cfg["jira"]
    itypes = jcfg.get("issue_type_by_category", {})
    description = row["Description"]
    env_text = row.get("Environment") or group["environment"]
    fields = {
        "project": {"key": jcfg["project_key"]},
        "issuetype": {"name": itypes.get(category, itypes.get("default", "Bug"))},
        "summary": row["Summary"],
        "priority": {"name": row.get("Priority") or group["suggested_priority"]},
    }
    env_field = (jcfg.get("fields") or {}).get("environment")
    if jcfg.get("environment_mode", "field") == "field" and env_field:
        fields[env_field] = env_text
    else:
        description = f"h3. Environment\n{{noformat}}\n{env_text}\n{{noformat}}\n\n{description}"
    fields["description"] = description

    labels = [safe_label(x) for x in (row.get("Labels") or "").split(",") if x.strip()]
    labels += [safe_label(x) for x in jcfg.get("default_labels", [])]
    labels += [safe_label(f"run-{run_id}"), safe_label(f"triage-{run_id}-{group['group_id']}")]
    fields["labels"] = sorted(set(labels))

    comps = [c.strip() for c in (row.get("Components") or "").split(",") if c.strip()] or jcfg.get("default_components", [])
    if comps:
        fields["components"] = [{"name": c} for c in comps]

    sys_field = (jcfg.get("fields") or {}).get("system")
    if sys_field and group.get("system") not in (None, "Unknown", "Multiple"):
        if jcfg["fields"].get("system_value_type", "option") == "option":
            fields[sys_field] = {"value": group["system"]}
        else:
            fields[sys_field] = group["system"]
    if assignee_id:
        fields["assignee"] = {"accountId": assignee_id}
    return fields


def comment_body(row: dict, group: dict, run_id: str) -> str:
    started = sorted(c["started_at"] for c in group["cases"] if c.get("started_at"))
    excerpt = next((e["content"][:300] for e in group["evidence"]
                    if e["kind"] in ("business_error_text", "popup_text", "alert_text", "error_message")), "")
    return "\n".join([
        f"h4. 自动回归 {run_id} 再次出现（{len(group['case_ids'])} 个用例）",
        f"* 执行时间：{started[0] if started else '未知'}",
        f"* 受影响用例：{', '.join(group['case_ids'][:30])}" + (" ……" if len(group['case_ids']) > 30 else ""),
        f"* 报错原文：{{noformat}}{excerpt}{{noformat}}",
        f"* 审核人备注：{row.get('审核备注') or '无'}",
        "",
        "{noformat}", row.get("Environment") or group["environment"], "{noformat}",
    ])


def attachments_for(group: dict, cfg: dict, tmpdir: Path) -> list[Path]:
    limit = int(cfg["jira"].get("max_screenshots_per_issue", 10))
    seen, files = set(), []
    for p in group["screenshots"]:
        path = Path(p)
        if path.exists() and path.name not in seen:
            seen.add(path.name)
            files.append(path)
        if len(files) >= limit:
            break
    if len(group["case_ids"]) > int(cfg["jira"].get("max_cases_in_table", 20)):
        csv_path = tmpdir / "affected_cases.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "case_name", "failed_step", "started_at", "reason"])
            for c in group["cases"]:
                w.writerow([c["case_id"], c.get("case_name"), c.get("failed_step"), c.get("started_at"), c.get("reason")])
        files.append(csv_path)
    return files


def discover(cfg: dict, config_path: str) -> None:
    from jira_client import JiraClient
    client = JiraClient()
    project = cfg["jira"]["project_key"]
    me = client.myself()
    print(f"已连接：{client.base}，当前账号：{me.get('displayName')}（{me.get('emailAddress')}）\n")
    out = {}
    for it in client.issue_types(project):
        print(f"== 问题类型：{it['name']}（id={it['id']}）")
        fields = client.create_fields(project, it["id"])
        out[it["name"]] = fields
        for f in fields:
            allowed = [a.get("value") or a.get("name") for a in f.get("allowedValues", [])][:10]
            print(f"   {'*' if f.get('required') else ' '} {f.get('fieldId') or f.get('key'):<22} {f.get('name')}"
                  + (f"  可选值：{allowed}" if allowed else ""))
    dest = Path(config_path).parent / "jira_fields.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n带 * 的是必填字段。完整结果已保存到 {dest}。请把 System 字段的 fieldId 填入 config.yaml 的 jira.fields.system。")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review")
    ap.add_argument("--groups")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--confirm", action="store_true", help="真正写入 Jira；不加时只演练")
    ap.add_argument("--discover-fields", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.discover_fields:
        discover(cfg, args.config)
        return
    if not (args.review and args.groups):
        fail("需要 --review 和 --groups")

    review_path = Path(args.review)
    run_dir = review_path.parent
    gdata = read_json(args.groups)
    run_id = gdata["run_id"]
    groups = {g["group_id"]: g for g in gdata["groups"]}
    submitted_path = run_dir / "submitted.json"
    submitted = read_json(submitted_path) if submitted_path.exists() else {"run_id": run_id, "submitted": [], "failed": []}
    done = {s["group_id"] for s in submitted["submitted"]}

    plan, problems, corrections = [], [], []
    for row in read_review(review_path):
        gid, status = row.get("group_id"), row.get("审核状态")
        if gid not in groups:
            problems.append(f"审核表中的 {gid!r} 在 groups.json 中不存在")
            continue
        if status not in ("通过", "追加到已有单"):
            continue
        if gid in done:
            log.info("%s 已提交过，跳过", gid)
            continue
        category = groups[gid]["category"]
        manual = row.get("人工分类")
        if manual:
            code = manual if manual in CATEGORIES else CN_TO_CODE.get(manual)
            if not code:
                problems.append(f"{gid} 人工分类 {manual!r} 不是有效类别")
                continue
            if not row.get("修改原因"):
                problems.append(f"{gid} 填写了人工分类但没有填写修改原因")
                continue
            corrections.append({"run_id": run_id, "group_id": gid, "case_ids": groups[gid]["case_ids"],
                                "rule_category": category, "human_category": code,
                                "rule_ids": groups[gid]["rule_ids"], "reason": row["修改原因"], "at": now_iso()})
            category = code
        if status == "追加到已有单":
            key = (row.get("已有单号") or "").upper()
            if not KEY_RE.match(key):
                problems.append(f"{gid} 选择了追加到已有单，但单号 {key!r} 格式不正确")
                continue
            plan.append({"group_id": gid, "action": "comment", "issue_key": key, "row": row, "category": category})
        else:
            if not row.get("Summary") or len(row["Summary"]) > 255:
                problems.append(f"{gid} Summary 为空或超过 255 个字符")
                continue
            for name in ("Summary", "Description"):
                if mask_pii(row.get(name)) != row.get(name):
                    problems.append(f"{gid} {name} 中疑似包含个人信息，请在审核表中修改")
                    break
            else:
                plan.append({"group_id": gid, "action": "create", "row": row, "category": category})

    print(f"\n=== {'提交' if args.confirm else '演练'}计划（run {run_id}）===")
    for p in plan:
        g = groups[p["group_id"]]
        target = p.get("issue_key") or p["row"]["Summary"]
        print(f"  {p['group_id']}  {'新建' if p['action'] == 'create' else '追加评论到'}  {target}"
              f"  （{len(g['case_ids'])} 个用例，截图 {len(g['screenshots'])} 张）")
    for msg in problems:
        print(f"  [跳过] {msg}")
    if not plan:
        print("  没有需要提交的行。")
        return
    if not args.confirm:
        print("\n这是演练，没有写入 Jira。确认无误后加 --confirm 重新运行。")
        return

    from jira_client import JiraClient
    client = JiraClient()
    with tempfile.TemporaryDirectory(prefix="jira_att_") as tmp:
        for p in plan:
            gid, row, g = p["group_id"], p["row"], groups[p["group_id"]]
            try:
                if p["action"] == "create":
                    label = safe_label(f"triage-{run_id}-{gid}")
                    existing = client.search(f'project = "{cfg["jira"]["project_key"]}" AND labels = "{label}"',
                                             ["summary"], 1)
                    if existing:
                        key = existing[0]["key"]
                        log.warning("%s 在 Jira 中已存在（%s），跳过新建", gid, key)
                        submitted["submitted"].append({"group_id": gid, "action": "already_exists", "issue_key": key,
                                                       "attachments": [], "submitted_at": now_iso()})
                        continue
                    assignee = None
                    if row.get("Assignee（邮箱）"):
                        assignee = client.find_account_id(row["Assignee（邮箱）"])
                        if not assignee:
                            log.warning("%s 找不到唯一的指派人 %s，将不指派", gid, row["Assignee（邮箱）"])
                    key = client.create_issue(build_fields(row, g, cfg, run_id, p["category"], assignee))
                else:
                    key = p["issue_key"]
                    client.add_comment(key, comment_body(row, g, run_id))
                uploaded = [client.add_attachment(key, f) for f in attachments_for(g, cfg, Path(tmp))]
                submitted["submitted"].append({"group_id": gid, "action": p["action"], "issue_key": key,
                                               "attachments": uploaded, "submitted_at": now_iso()})
                log.info("%s → %s %s（附件 %d 个）", gid, key, "已新建" if p["action"] == "create" else "已追加评论",
                         len(uploaded))
            except Exception as exc:  # noqa: BLE001  单行失败不影响其他行
                log.error("%s 提交失败：%s", gid, exc)
                submitted["failed"].append({"group_id": gid, "error": str(exc)[:800], "at": now_iso()})
            write_json(submitted_path, submitted)  # 每处理一行就保存，中途中断也能续上

    if corrections:
        with open(run_dir / "corrections.jsonl", "a", encoding="utf-8") as f:
            for c in corrections:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    ok = [s for s in submitted["submitted"] if s["submitted_at"]]
    log.info("完成。成功 %d，失败 %d。记录：%s", len(ok), len(submitted["failed"]), submitted_path)
    for s in ok:
        print(f"  {s['group_id']}: {client.base}/browse/{s['issue_key']}")


if __name__ == "__main__":
    main()
