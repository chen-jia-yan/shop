"""
报告生成函数 — 报告聚合器
======================
功能：聚合测试执行数据（Dataverse + Azure SQL），调用 Azure OpenAI 生成自然语言
      测试报告摘要，返回结构化的报告数据供 Power Apps / Power Pages 展示。

触发方式：HTTP POST（支持定时触发器 + Power Automate 回调）
数据来源：Dataverse（用例、执行记录）+ Azure SQL（历史趋势）
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

import azure.functions as func
from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version="2024-10-01-preview",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
)

DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]

REPORT_TEMPLATE = """# {project_name} v{version} 测试报告

**报告时间**: {report_time}
**执行环境**: {environment}
**测试范围**: {scope_summary}

---

## 执行概览

| 指标 | 值 |
|------|-----|
| 总用例数 | {total} |
| 通过 | {passed} |
| 失败 | {failed} |
| 跳过 | {skipped} |
| 通过率 | {pass_rate:.1f}% |
| 执行时长 | {duration_min} 分钟 |

## AI 分析摘要

{ai_summary}

## 失败分布

{failure_breakdown}

## 建议

{recommendations}
"""


# ---------------------------------------------------------------------------
# HTTP 触发器
# ---------------------------------------------------------------------------
@app.route(route="generate-report", methods=["POST"])
def generate_report(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("generate-report 被触发")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "请求体必须是合法 JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    # ---------- 参数提取 ----------
    project = body.get("project_name", "未知项目")
    version = body.get("version", "0.0.0")
    env = body.get("environment", "测试环境")

    stats = body.get("stats", {})
    total = stats.get("total", 0)
    passed = stats.get("passed", 0)
    failed = stats.get("failed", 0)
    skipped = stats.get("skipped", 0)
    duration_sec = stats.get("duration_seconds", 0)

    failures = body.get("failures", [])  # [{testcase_id, title, category, error}]

    pass_rate = (passed / total * 100) if total > 0 else 0.0
    duration_min = round(duration_sec / 60, 1)

    # ---------- 失败分布 ----------
    failure_cats: dict[str, int] = {}
    for f in failures:
        cat = f.get("category", "未分类")
        failure_cats[cat] = failure_cats.get(cat, 0) + 1

    failure_breakdown = "\n".join(
        f"- **{k}**: {v}" for k, v in sorted(failure_cats.items(), key=lambda x: -x[1])
    )

    # ---------- AI 摘要 ----------
    try:
        ai_summary, recommendations = _ai_summarize(
            project, version, env, pass_rate, failed, failures
        )
    except Exception as exc:
        logging.warning("AI 摘要生成失败，使用兜底文本: %s", exc)
        ai_summary = "AI 摘要生成失败，请查看原始数据。"
        recommendations = "暂无 AI 建议。"

    # ---------- 组装 ----------
    report_text = REPORT_TEMPLATE.format(
        project_name=project,
        version=version,
        report_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        environment=env,
        scope_summary=f"共 {total} 条用例",
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        pass_rate=pass_rate,
        duration_min=duration_min,
        ai_summary=ai_summary,
        failure_breakdown=failure_breakdown or "无失败",
        recommendations=recommendations,
    )

    # ---------- 结构化数据（给 Power Apps 用） ----------
    structured = {
        "project_name": project,
        "version": version,
        "report_time": datetime.now().isoformat(),
        "environment": env,
        "stats": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": round(pass_rate, 1),
            "duration_seconds": duration_sec,
        },
        "failure_distribution": failure_cats,
        "ai_summary": ai_summary,
        "recommendations": recommendations,
        "markdown_report": report_text,
    }

    return func.HttpResponse(
        json.dumps({"code": "0", "data": structured}, ensure_ascii=False),
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# 定时触发器（每天凌晨生成报告）
# ---------------------------------------------------------------------------
@app.schedule(
    schedule="0 0 2 * * *",  # 每天 UTC 2:00
    arg_name="timer",
    run_on_startup=False,
)
def scheduled_report(timer: func.TimerRequest) -> None:
    """定时触发：聚合前一天数据生成日报。实现取决于具体数据源连接。"""
    logging.info("定时报告触发: %s", timer.past_due)
    # 实际实现：从 Dataverse / Azure SQL 拉取数据 → 组装 → 生成 → 推送 Teams
    # 此处仅做示意
    logging.info("定时报告：从数据源拉取数据并生成...")


# ---------------------------------------------------------------------------
# AI 摘要
# ---------------------------------------------------------------------------
def _ai_summarize(
    project: str,
    version: str,
    env: str,
    pass_rate: float,
    failed_count: int,
    failures: list[dict],
) -> tuple[str, str]:
    """调用 LLM 生成报告摘要和修复建议。"""
    failures_text = "\n".join(
        f"- {f.get('title', 'N/A')}: {f.get('error', '')[:150]}"
        for f in failures[:10]  # 只传前 10 条避免超 token
    )

    prompt = f"""项目 {project} v{version} 在 {env} 环境的测试执行情况：
- 通过率: {pass_rate}%
- 失败数: {failed_count}

失败详情：
{failures_text}

请输出：
1. 一段 100 字以内的执行摘要
2. 3-5 条具体修复建议

格式：JSON {{"summary": "...", "recommendations": ["...", "..."]}}
"""

    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": "你是一个测试报告分析师。输出简洁、可执行的结论。",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    result = json.loads(resp.choices[0].message.content)
    recs = result.get("recommendations", [])
    rec_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(recs))

    return result.get("summary", ""), rec_text
