只读确认，不写任何文件、不改代码、不碰 Azure 索引、不重新入库。每条给出 文件:行号 证据和真实输出。

A1. 生产的「纯检索回答」链路：
- 入口函数是哪个？它在返回答案前有没有调用大模型生成？
- 贴出判断"模型没配置就只返回检索结果拼接"的那段代码，以及当前环境下这个判断的实际取值（model_provider_configured 是 True 还是 False）。
- 如果有调用模型，贴出它用的 system prompt 原文。
- 结论用一句话回答：生产检索链路的输出是「模型组织后的句子」还是「chunk 原文拼接」。

A2. 评估的 _judge()：
- 贴出当前判官 prompt 的完整原文、输出格式要求、分数解析代码。
- 当前判官用的模型名、temperature。

A3. Agent 链路（AgentOrchestrator.run_user_query）的证据记录：
- FinalGroundedAnswer.work_logs 里每一项有哪些字段？
- 能否从 work_logs 里区分出：(a) search_kb / expand_evidence 返回的「原始 chunk」（带 chunk_id、正文）；(b) query_business_graph、空间复原、流程图校验等返回的「图谱/复原推断内容」？
- 实跑一道题（如「QlikSenseとは何ですか？」），把 work_logs 按 (a)(b) 两类整理贴给我，每类给出条数和示例。
- 如果 work_logs 里没有保存 chunk 正文或图谱返回内容，明确说"没有"，并指出要在哪个函数里加记录。

A4. gold 集（evals/rag_gold_set.jsonl 或日文版）：
- 贴出一条完整记录的真实字段结构。
- 统计总题数。

输出一份「评估改造_调研.md」，停下等我确认。