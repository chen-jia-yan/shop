【任务 R3c】只读排查：后端的索引映射配置、关系白名单配置。

【绝对禁止】
- 不修改、不新建、不删除任何文件；不读取任何 .env 文件
- 不连接任何外部服务
- git 只允许 status / log / show / grep / ls-files
- 找不到的写"未找到"并贴出搜索命令，不允许推测

【范围】C:\Users\234393\Desktop\tap-ai-backend

【要做的 5 件事】每件都要贴 文件:行号 + 原文

1. 列出读取"租户 → 索引名映射"配置（形如 {"hk": ..., "jp": ...}）的所有代码位置。
   对每个位置说明：它是只读（查询、图谱读取），还是会写入（新增、更新、删除索引或 Neo4j 里的数据）

2. 如果第 1 条中有会写入的位置，单独列出来，并说明：当 key 为 "jp" 时，会对哪个索引、哪个 Neo4j scope 执行什么写操作

3. TAP_AI_KB_KG_RELATION_TYPES 这个环境变量应该怎么写，才能被 KnowledgeSettings.kg_relation_types 正确读成 6 个值
   （贴出 KnowledgeSettings 的完整类定义；如果有 field_validator 或其他解析逻辑，也要贴出来；
    最后给出一行可以直接写进 .env 的示例：
    TAP_AI_KB_KG_RELATION_TYPES=... ，包含 NEXT、HANDLED_BY、PART_OF、CONTAINS、USES、REQUIRES）

4. library_kb_graph_enabled 在哪里定义、默认值是什么、在哪里被读取

5. 后端入库链路（sdk_ingest.py）构造 Neo4jGraphSink 时传了哪些参数；
   如果要打开大模型关系抽取，是只需要设环境变量 KB_KG_LLM_ENABLED=1，还是必须改代码。
   贴出 SDK 中 llm_enabled() 函数的原文作为依据

【报告格式】按 1 到 5 写，最后附核对表：
| 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
