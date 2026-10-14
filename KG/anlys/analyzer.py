from __future__ import annotations
from typing import Any

CAT_LABEL = {"empty_retrieval":"检索为空","retrieval_miss":"漏召回","context_fragment":"上下文碎片",
             "noise_wrong_level":"噪声·层级不符","generation_issue":"生成问题","other":"其它"}
CAT_FIX = {
  "empty_retrieval":"检索没召回任何内容：查扩展、放宽门禁、确认该文档已入库。",
  "retrieval_miss":"正确文档没进 top-k：查询扩展(Phase2→フェーズ2)、提升向量权重、扩大候选池。",
  "context_fragment":"正确文档命中但关键行不在召回 chunk：答案时表格重组/父文档召回/改 Excel chunk 策略。",
  "noise_wrong_level":"召回被无关来源淹没：rerank 调权、来源一致性门槛、doc-type 加权。",
  "generation_issue":"素材里有但答错/没答到：检查判官 prompt、completeness 口径、温度。",
  "other":"需人工复核。",
}
DIMS = ["faithfulness","answer_relevance","completeness","correctness"]

# ⚠️对齐点A：按真实结果字段名取值（下面做了多候选兼容）
def _score(r, k):
    s = r.get("scores") or r
    return float(s.get(k, 0) or 0)

def _retr(r):   # 统一取检索诊断
    rt = r.get("retrieval") or {}
    srcs = rt.get("sources") or r.get("retrieval_context") or r.get("sources") or []
    return {
        "sources": srcs,
        "toehold": rt.get("toehold_recall", r.get("toehold_recall")),
        "context_relevance": rt.get("context_relevance", r.get("context_relevance", 0)) or 0,
    }

def _hit_expected(r, srcs):
    ef = r.get("expected_file") or r.get("expected_source") or ""
    return any(ef and s.get("source_file") and (ef in s["source_file"] or s["source_file"] in ef) for s in srcs)

def classify(r) -> str:
    srcs = _retr(r)["sources"]
    if not srcs:
        return "empty_retrieval"
    rt = _retr(r)
    toe = rt["toehold"] if rt["toehold"] is not None else (1 if _hit_expected(r, srcs) else 0)
    if not toe:
        return "retrieval_miss"
    if _score(r, "faithfulness") >= 4 and _score(r, "correctness") <= 2:
        ef = r.get("expected_file") or r.get("expected_source") or ""
        other = sum(1 for s in srcs if not (ef and s.get("source_file") and (ef in s["source_file"] or s["source_file"] in ef))) / len(srcs)
        return "noise_wrong_level" if other > 0.6 else "context_fragment"
    if rt["context_relevance"] >= 0.6 and _score(r, "correctness") <= 2:
        return "generation_issue"
    return "other"

def is_bad(r) -> bool:
    return _score(r, "correctness") < 3

def analyze_results(results: list[dict[str, Any]]) -> dict:
    """把一份评估结果分析成：聚合指标 + 分类计数 + 逐 badcase 详情（含修复建议）。纯规则、离线、确定性。"""
    total = len(results)
    for r in results:
        r["_category"] = classify(r)
    bad = [r for r in results if is_bad(r)]
    means = {k: (sum(_score(r, k) for r in results) / total if total else 0) for k in DIMS}
    counts: dict[str, int] = {}
    for r in bad:
        counts[r["_category"]] = counts.get(r["_category"], 0) + 1
    weakest = min(means, key=means.get) if means else None
    ret_not_gen = sum(1 for r in bad if _score(r, "faithfulness") >= 4)  # 检索问题而非生成

    badcases = [{
        "id": r.get("id") or r.get("question_id"),
        "question": r.get("question") or r.get("query"),
        "category": r["_category"],
        "category_label": CAT_LABEL[r["_category"]],
        "suggested_fix": CAT_FIX[r["_category"]],
        "scores": {k: _score(r, k) for k in DIMS},
        "expected_file": r.get("expected_file") or r.get("expected_source"),
        "toehold_recall": _retr(r)["toehold"],
        "context_relevance": _retr(r)["context_relevance"],
    } for r in bad]

    return {
        "total": total,
        "passed": total - len(bad),
        "pass_rate": round((total - len(bad)) / total, 3) if total else 0,
        "bad_count": len(bad),
        "weakest_dim": weakest,
        "dim_means": {k: round(v, 2) for k, v in means.items()},
        "retrieval_not_generation": ret_not_gen,  # 忠实度≥4 的差题数：问题多半在检索/内容，不在生成
        "category_counts": {CAT_LABEL[c]: n for c, n in counts.items()},
        "category_fix": {CAT_LABEL[c]: CAT_FIX[c] for c in counts},
        "badcases": badcases,
    }
