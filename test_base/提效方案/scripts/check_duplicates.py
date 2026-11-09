"""第 6 步：在 Jira 中查找可能重复的未关闭单据。

用法：
    python scripts/check_duplicates.py --groups triage_runs/<run_id>/groups.json \
        --config config/config.yaml --out triage_runs/<run_id>/duplicates.json [--offline]

做法：
- 只对 needs_jira 为 true 的组查重。
- 用根因短语做全文搜索（text ~），范围是本项目、最近 N 天创建、状态类别不是 Done 的单。
- 再用标题与根因短语的词语重合度排序，结果只作为候选，最终由审核人决定。
- --offline：不连接 Jira，生成空结果（例如还没有拿到 API Token 时）。
"""
from __future__ import annotations

import argparse
import re

from common import load_config, now_iso, read_json, setup_logging, write_json

log = setup_logging()

STOPWORDS = {"the", "a", "an", "of", "to", "due", "cases", "case", "failed", "regression", "and", "is", "for", "on", "in"}


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9一-鿿]+", (text or "").lower()) if w not in STOPWORDS and len(w) > 1}


def jql_phrase(text: str) -> str:
    """去掉 JQL 文本搜索中的保留字符，只保留字母数字和空格。"""
    cleaned = re.sub(r"[^\w一-鿿 ]+", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()[:100]


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    data = read_json(args.groups)
    cfg = load_config(args.config)
    jcfg = cfg["jira"]
    dcfg = jcfg.get("duplicate_search", {})
    out = {"run_id": data["run_id"], "generated_at": now_iso(), "offline": args.offline, "results": {}}

    targets = [g for g in data["groups"] if g["needs_jira"]]
    if args.offline:
        for g in targets:
            out["results"][g["group_id"]] = {"query": None, "candidates": [], "note": "离线模式，未查重"}
        write_json(args.out, out)
        log.warning("离线模式：没有查重。提交前请人工在 Jira 中确认没有重复单。")
        return

    from jira_client import JiraClient  # 延迟导入，离线模式不需要 requests 和 Token
    client = JiraClient()
    for g in targets:
        phrase = jql_phrase(g["root_cause_hint"])
        if not phrase:
            out["results"][g["group_id"]] = {"query": None, "candidates": [], "note": "根因短语为空，无法查重"}
            continue
        jql = (f'project = "{jcfg["project_key"]}" AND statusCategory != Done '
               f'AND created >= -{int(dcfg.get("lookback_days", 30))}d '
               f'AND text ~ "{phrase}" ORDER BY created DESC')
        try:
            issues = client.search(jql, ["summary", "status", "created", "labels"],
                                   int(dcfg.get("max_results", 5)) * 2)
        except RuntimeError as exc:
            log.error("查重失败 %s：%s", g["group_id"], exc)
            out["results"][g["group_id"]] = {"query": jql, "candidates": [], "error": str(exc)}
            continue
        cands = []
        for it in issues:
            f = it.get("fields", {})
            cands.append({
                "key": it.get("key"),
                "summary": f.get("summary"),
                "status": (f.get("status") or {}).get("name"),
                "created": f.get("created"),
                "similarity": similarity(g["root_cause_hint"], f.get("summary", "")),
                "url": f"{client.base}/browse/{it.get('key')}",
            })
        cands.sort(key=lambda c: c["similarity"], reverse=True)
        out["results"][g["group_id"]] = {"query": jql, "candidates": cands[: int(dcfg.get("max_results", 5))]}
        if cands:
            log.info("%s 找到疑似重复：%s", g["group_id"], ", ".join(c["key"] for c in cands[:3]))

    write_json(args.out, out)
    log.info("查重完成，写入 %s", args.out)


if __name__ == "__main__":
    main()
