"""
用例生成函数 — 测试用例生成器
======================
功能：基于需求分析器输出的需求点，调用 Azure OpenAI 生成结构化测试用例，
      包含前置条件、测试步骤、预期结果、优先级等。
      生成的用例写入 Dataverse 或输出 JSON 供 Power Automate 消费。

触发方式：HTTP POST
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

SYSTEM_PROMPT = """你是一个资深测试用例设计专家。根据给定的需求点生成可执行的测试用例。

## 输出格式
合法 JSON 数组，每个元素：
- `id`: TC-{三位序号}
- `requirement_id`: 关联需求编号
- `title`: 用例标题
- `priority`: "P0" | "P1" | "P2"
- `precondition`: 前置条件
- `test_data`: 测试数据描述
- `steps`: ["步骤1", "步骤2", ...]
- `expected`: ["结果1", "结果2", ...]
- `category`: "功能" | "性能" | "安全" | "兼容性" | "可靠性"
- `automation_flag`: true/false  （判断是否适合自动化）
- `tags`: ["冒烟", "回归", "边界值", "异常" ...]

## 规则
1. 每个 P0 需求至少 3 个用例（正向 + 边界 + 异常）
2. P1/P2 需求至少 1 个正向用例
3. 步骤必须在 3-8 步之内，避免过于冗长
4. 预期结果必须可验证（能明确判断 pass/fail）
5. 边界值和异常场景必须单独成用例，不要合并到正向用例的步骤里
"""


# ---------------------------------------------------------------------------
# HTTP 触发器
# ---------------------------------------------------------------------------
@app.route(route="generate-testcases", methods=["POST"])
def generate_testcases(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("generate-testcases 被触发")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "请求体必须是合法 JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    requirements = body.get("requirements", [])
    if not requirements:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "requirements 数组不能为空"}),
            status_code=400,
            mimetype="application/json",
        )

    # 控制一次生成的规模，超过 10 个需求点分批
    generation_mode = body.get("mode", "batch")  # "batch" | "single"

    try:
        if generation_mode == "single" and body.get("requirement_id"):
            # 只生成单个需求点的用例
            target = [r for r in requirements if r["id"] == body["requirement_id"]]
            if not target:
                return func.HttpResponse(
                    json.dumps({"code": "-1", "message": "未找到指定需求"}),
                    status_code=404,
                    mimetype="application/json",
                )
            cases = _generate_for_requirement(target[0])
        else:
            cases = _generate_batch(requirements)
    except Exception as exc:
        logging.exception("用例生成失败")
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": f"生成异常: {str(exc)}"}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(
            {
                "code": "0",
                "data": {
                    "total": len(cases),
                    "p0_count": sum(1 for c in cases if c["priority"] == "P0"),
                    "p1_count": sum(1 for c in cases if c["priority"] == "P1"),
                    "p2_count": sum(1 for c in cases if c["priority"] == "P2"),
                    "automation_ready": sum(1 for c in cases if c["automation_flag"]),
                    "testcases": cases,
                },
            },
            ensure_ascii=False,
        ),
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# 核心
# ---------------------------------------------------------------------------
def _generate_for_requirement(req: dict) -> list[dict]:
    """为单个需求生成用例。"""
    prompt = json.dumps(req, ensure_ascii=False)
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请为以下需求生成测试用例：\n\n{prompt}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = json.loads(resp.choices[0].message.content)
    return raw if isinstance(raw, list) else raw.get("testcases", [])


def _generate_batch(requirements: list[dict]) -> list[dict]:
    """分批生成所有需求的用例。"""
    all_cases: list[dict] = []
    # 每批最多 5 个需求，避免超出 token 限制
    batch_size = 5
    for i in range(0, len(requirements), batch_size):
        batch = requirements[i : i + batch_size]
        prompt = json.dumps(batch, ensure_ascii=False)
        resp = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"请为以下 {len(batch)} 个需求生成测试用例：\n\n{prompt}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = json.loads(resp.choices[0].message.content)
        cases = raw if isinstance(raw, list) else raw.get("testcases", [])
        all_cases.extend(cases)
    return all_cases
