目标：新增一道"来源可追溯检查（attribution）"，把答案拆成一条条原子结论，逐条判断它的支撑来自原始文档原文、仅来自图谱/复原推断，还是没有支撑。用来发现"在残缺碎片上扩充补齐"的内容。
约束：开关 KB_EVAL_ATTRIBUTION（默认开）；temperature=0.0；不碰 Azure；判断依据只能是传入的证据，不得使用模型自身知识。
前置：阶段 A3 已确认 work_logs 能区分原始 chunk 和推断内容；如果不能，先在 Agent 的工具调用处补记录（search_kb/expand_evidence 记 chunk_id+正文；query_business_graph/复原/流程图校验记返回内容），这部分改动单独给我看 diff。

D1. 新建 kb_poc/skills/rag_eval/attribution.py，函数 attribute(question, actual_output, original_evidence, derived_evidence, client) -> dict。prompt 如下：

---
你是严格的事实溯源审查员。只根据下面的证据判断，不要使用你自己的知识。

【原始证据】（知识库原文，每段带 chunk_id）
{original_evidence}
【推断证据】（知识图谱/空间复原/流程图重建的结果，不是原文）
{derived_evidence}
【答案】{actual_output}

第一步：把答案拆成原子结论。每条只包含一个可核对的事实（一个实体、一个关系、一个数值、一个步骤）。客套话、过渡句不算结论。
第二步：给每条结论标注一个类别：
- SOURCE：能在【原始证据】中找到直接支撑（写出 chunk_id）
- DERIVED：【原始证据】里没有，只能在【推断证据】中找到支撑
- UNSUPPORTED：两类证据里都找不到支撑
- CONTRADICTED：与【原始证据】的内容矛盾

只输出 JSON：
{
  "claims": [
    {"text": "结论原文", "label": "SOURCE|DERIVED|UNSUPPORTED|CONTRADICTED", "chunk_ids": ["..."], "note": "简短说明"}
  ]
}
---

D2. 代码里根据 claims 计算（不让模型算）：
- source_rate = SOURCE数 / 总数
- derived_rate = DERIVED数 / 总数
- unsupported_count、contradicted_count
- risk_level：
  · contradicted_count ≥ 1 → "high"
  · unsupported_count ≥ 1 → "high"
  · derived_rate > 0.3 → "review"
  · 其它 → "ok"
  阈值 0.3 做成配置项 KB_EVAL_DERIVED_THRESHOLD。

D3. 写入 result["attribution"] = {claims, source_rate, derived_rate, unsupported_count, contradicted_count, risk_level}。

D4. 纯检索链路（LLM-RAG）同样跑这道检查，derived_evidence 为空：这时任何 DERIVED 都不该出现，UNSUPPORTED 就是编造。

D5. 报告汇总新增：risk_level 各档的题数、平均 source_rate、平均 derived_rate、全部 high 风险题清单。

D6. 单元测试（不调真实模型，用 mock 返回固定 JSON）：验证四种 label 的计数、risk_level 判定、derived_evidence 为空时的行为、模型返回非 JSON 时降级为 risk_level="unknown" 而不是崩溃。

停，给我 diff 和测试结果。