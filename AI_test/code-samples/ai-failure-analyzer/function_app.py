"""
失败分析函数 — 测试失败分析器
======================
功能：接收 Playwright 执行失败的测试报告，调用 Azure OpenAI 分析失败根因，
      输出原因分类和修复建议。

触发方式：HTTP POST（Azure DevOps Pipeline 回调 / Power Automate 触发）
"""

import json
import logging
import os
import re
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

FAILURE_CATEGORIES = [
    "元素定位失败 — 选择器过期或 DOM 结构变化",
    "超时 — 页面加载或元素等待超时",
    "断言失败 — 实际结果与预期不符",
    "环境问题 — 测试数据、权限、网络、依赖服务不可用",
    "脚本错误 — 测试代码本身有 bug",
    "浏览器异常 — 崩溃、OOM、版本不兼容",
    "AI 判定 — 无法归入以上类别时由 LLM 判断",
]

SYSTEM_PROMPT = f"""你是一个测试失败分析专家。分析测试失败日志，判断根因并给出修复建议。

## 失败类别
{chr(10).join(f'- {{i+1}}. {{cat}}' for i, cat in enumerate(FAILURE_CATEGORIES))}

## 输出格式
```json
{{
  "root_cause_category": "类别名称",
  "root_cause": "根因简述",
  "confidence": 0.95,
  "suggestion": "修复建议",
  "is_flaky": false,
  "flaky_reason": "如果 is_flaky 为 true，填可能原因",
  "related_screenshots": ["screenshot_urls如果有的话"]
}}
```

## 规则
1. 优先根据错误信息关键字判断类别，LLM 判定只在无匹配时使用
2. 同一场景连续失败 3 次以上 → 不是 flaky
3. 给出具体修复建议，不要说"检查代码"这种废话
"""


# ---------------------------------------------------------------------------
# 关键字快速分类（不依赖 LLM）
# ---------------------------------------------------------------------------
_KEYWORD_RULES = [
    (r"Timeout|timed? ?out|等待超时", "超时"),
    (r"strict mode violation|element is not attached|locator\.(click|fill|press)",
     "元素定位失败"),
    (r"expect\(|AssertionError|Expected|assert\..*failed", "断言失败"),
    (r"ECONNREFUSED|ENOTFOUND|5\d{2}|401|403|50[0123]|Service Unavailable",
     "环境问题"),
    (r"Session|crash|OOM|out of memory|Browser.*closed|Target closed",
     "浏览器异常"),
]


def _keyword_classify(error_text: str) -> str | None:
    """用关键字预分类，命中直接返回，不调 LLM。"""
    for pattern, category in _KEYWORD_RULES:
        if re.search(pattern, error_text, re.IGNORECASE):
            return category
    return None  # 未命中，走 LLM


# ---------------------------------------------------------------------------
# Flaky 检测（基于历史模式，简单版）
# ---------------------------------------------------------------------------
def _check_flaky(error_text: str, history: list[dict]) -> bool:
    """检查是否是 flaky 测试。
    history: 同用例最近 N 次执行记录 [{status: "pass"|"fail", error: "..."}]
    """
    if not history:
        return False
    recent = history[-5:]  # 最近 5 次
    fails = [h for h in recent if h["status"] == "fail"]
    # 连续 3 次以上失败 → 不是 flaky，是稳定失败
    if len(fails) >= 3:
        return False
    # 多次失败但间歇性通过 → flaky
    if len(fails) >= 2 and any(h["status"] == "pass" for h in recent):
        return True
    return False


# ---------------------------------------------------------------------------
# HTTP 触发器
# ---------------------------------------------------------------------------
@app.route(route="analyze-failure", methods=["POST"])
def analyze_failure(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("analyze-failure 被触发")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "请求体必须是合法 JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    error_text = body.get("error", "").strip()
    if not error_text:
        return func.HttpResponse(
            json.dumps({"code": "-1", "message": "error 不能为空"}),
            status_code=400,
            mimetype="application/json",
        )

    history = body.get("history", [])
    screenshots = body.get("screenshots", [])

    # 1. 关键字预分类
    category = _keyword_classify(error_text)
    is_flaky = _check_flaky(error_text, history)

    # 2. 如果需要 LLM 分析
    if category is None:
        try:
            analysis = _llm_analyze(error_text)
        except Exception as exc:
            logging.exception("LLM 分析失败")
            return func.HttpResponse(
                json.dumps({"code": "-1", "message": f"AI 分析异常: {str(exc)}"}),
                status_code=500,
                mimetype="application/json",
            )
    else:
        analysis = {
            "root_cause_category": category,
            "root_cause": f"关键字匹配: {error_text[:200]}",
            "confidence": 0.8,
            "suggestion": _default_suggestion(category),
        }

    analysis["is_flaky"] = is_flaky
    if screenshots:
        analysis["related_screenshots"] = screenshots

    return func.HttpResponse(
        json.dumps({"code": "0", "data": analysis}, ensure_ascii=False),
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# LLM 分析
# ---------------------------------------------------------------------------
def _llm_analyze(error_text: str) -> dict[str, Any]:
    """调用 LLM 分析无法通过关键字分类的失败。"""
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"分析以下测试失败原因：\n\n{error_text}"},
        ],
        temperature=0.1,
    )
    raw = json.loads(resp.choices[0].message.content)
    return raw


def _default_suggestion(category: str) -> str:
    """关键字匹配时的默认建议。"""
    suggestions = {
        "超时": "检查页面加载性能或增加等待时间/调整 timeout 配置",
        "元素定位失败": "检查选择器是否随 UI 变更，考虑使用 data-testid 属性",
        "断言失败": "检查预期值是否随数据变化，区分环境差异导致的断言差异",
        "环境问题": "检查被依赖服务是否正常，测试账号权限是否到位",
        "浏览器异常": "检查浏览器版本和资源使用情况，考虑重启浏览器实例",
    }
    return suggestions.get(category, "请人工排查")
