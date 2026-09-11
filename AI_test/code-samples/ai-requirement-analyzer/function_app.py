"""
需求分析函数 — 需求分析器
======================
功能：接收产品需求文档（PRD），调用 Azure OpenAI 解析并提取可测试的需求点，
      输出结构化的测试范围清单供后续用例生成使用。

触发方式：HTTP POST（Power Automate / Copilot Studio 回调）
环境变量：
  - AZURE_OPENAI_ENDPOINT
  - AZURE_OPENAI_KEY
  - AZURE_OPENAI_DEPLOYMENT   (建议: gpt-4o)
"""

import json
import logging
import os
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

SYSTEM_PROMPT = """你是一个资深 QA 需求分析专家。你的任务是从产品需求文档中提取可测试的需求点。

## 输出格式
始终返回合法的 JSON 数组，每个元素包含：
- `id`: 需求编号（自动生成，如 REQ-001）
- `title`: 需求简短标题
- `description`: 需求详细描述
- `priority` : "P0" | "P1" | "P2"  （P0=核心流程，P1=重要功能，P2=体验优化）
- `test_focus`: 测试重点描述
- `category`: "功能" | "性能" | "安全" | "兼容性" | "可靠性" | "易用性"
- `related_modules`: 涉及模块列表

## 规则
1. 只提取可测试的需求点，模糊描述不要强行生成
2. 不要遗漏负面场景（如边界值、异常输入、权限不足）
3. 如果原文缺乏必要信息，在 description 中标注"[信息不足]"
"""


# ---------------------------------------------------------------------------
# 请求/响应 Schema
# ---------------------------------------------------------------------------
REQUEST_SCHEMA = {
    "prd_text": "string, 必填，需求文档全文",
    "project_name": "string, 可选，项目名称",
    "version": "string, 可选，版本号",
}

RESPONSE_SCHEMA = {
    "code": "0 成功 | -1 系统异常",
    "data": {
        "project_name": "str",
        "version": "str",
        "requirements": [  # 上方 SYSTEM_PROMPT 定义的数组
            {
                "id": "REQ-001",
                "title": "string",
                "description": "string",
                "priority": "P0",
                "test_focus": "string",
                "category": "功能",
                "related_modules": ["模块A"],
            }
        ],
        "summary": {
            "total": 0,
            "p0_count": 0,
            "p1_count": 0,
            "p2_count": 0,
            "categories": {},
        },
    },
}


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------
def _call_llm(prd_text: str) -> list[dict[str, Any]]:
    """调用 Azure OpenAI 提取需求点，返回解析后的 JSON 数组。"""
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请分析以下需求文档，提取测试需求点：\n\n{prd_text}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # 低温度保证稳定性
    )
    raw = resp.choices[0].message.content
    parsed = json.loads(raw)

    # LLM 可能返回 {requirements: [...]} 也可能直接返回数组
    items = parsed if isinstance(parsed, list) else parsed.get("requirements", [])
    return items


def _build_summary(items: list[dict]) -> dict:
    """汇总统计。"""
    categories: dict[str, int] = {}
    p0 = p1 = p2 = 0
    for item in items:
        p = item.get("priority", "P2")
        if p == "P0":
            p0 += 1
        elif p == "P1":
            p1 += 1
        else:
            p2 += 1
        cat = item.get("category", "其他")
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total": len(items),
        "p0_count": p0,
        "p1_count": p1,
        "p2_count": p2,
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# HTTP 触发器
# ---------------------------------------------------------------------------
@app.route(route="analyze-requirement", methods=["POST"])
def analyze_requirement(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("analyze-requirement 被触发")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "请求体必须是合法 JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    prd_text = body.get("prd_text", "").strip()
    if not prd_text:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "prd_text 不能为空"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        items = _call_llm(prd_text)
    except Exception as exc:
        logging.exception("LLM 调用失败")
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": f"AI 服务异常: {str(exc)}"}),
            status_code=500,
            mimetype="application/json",
        )

    summary = _build_summary(items)

    return func.HttpResponse(
        json.dumps(
            {
                "code": "0",
                "data": {
                    "project_name": body.get("project_name", ""),
                    "version": body.get("version", ""),
                    "requirements": items,
                    "summary": summary,
                },
            },
            ensure_ascii=False,
        ),
        status_code=200,
        mimetype="application/json",
    )
