【任务 R4a】只读排查：后端的图谱接口、入库链路、删除链路、并发处理。

【绝对禁止】违反任意一条，立即停止并告诉我：
- 不修改、不新建、不删除任何文件；不读取任何 .env 文件（.env.example 可以读）
- 不连接 Azure、Neo4j、MySQL、Redis、大模型；不运行入库或 ingest 命令；不执行 SQL
- git 只允许 status / log / show / grep / ls-files
- 找不到的写"未找到"，并贴出用过的搜索命令。不允许推测、不允许编造

【范围】
- 后端：C:\Users\234393\Desktop\tap-ai-backend
- SDK：C:\Users\234393\fwd-tap-common\fwd-tap-ingest

【要做的 6 件事】每一件都必须贴出 文件:行号 + 原文代码，只写结论的视为没做

1. 后端现有的图谱接口
   运行：git grep -n -i -E "neo4j|graph|kg_" -- src/tap_ai/api src/tap_ai/application
   贴出全部原始输出；再列出所有和图谱有关的接口：请求方法 | 路径 | 处理函数所在的 文件:行号 | 返回什么数据
   没有图谱接口的，写"没有图谱接口"

2. 删除文件、重新上传同一个文件时，Neo4j 里的数据会怎样
   a. 后端知识库管理里"删除文件"的处理函数原文，以及它调用的下一层，一直追到 Azure 删除和 Neo4j 删除为止
   b. SDK 中 Neo4jGraphSink 有没有按 document_id 删除的方法；有的话贴出方法原文和 Cypher 原文
   c. 结论：删除文件时，Neo4j 中这个文件的 Chunk、MENTIONED_IN、实体之间的关系会不会被删除。只能回答「会」「不会」「部分会」，并说明依据

3. 后端入库时，是怎样调用 SDK 的
   从 KbIngestWorker 开始，一层一层追到 Neo4jGraphSink.upsert()，每一层贴出调用的那几行原文
   重点回答：调用 SDK 时是在主线程直接调用、用 asyncio.to_thread / run_in_executor 放到单独线程，还是用别的方式？贴出依据

4. SDK 里大模型抽取器和规则抽取器的接口
   a. LLMProvider（或同等作用的接口 / Protocol）的完整定义原文：方法名、参数、返回值，是同步还是异步
   b. LLMRelationExtractor 调用这个接口的那几行原文
   c. SDK 里有没有把"规则抽取器 + 大模型抽取器"组合在一起的类或函数；有的话贴出原文和 SDK 命令行里使用它的那几行

5. 实体向量
   a. Neo4jGraphSink 接收的向量模型参数叫什么、要求是什么接口（贴出接口定义原文）
   b. 后端有没有现成的向量生成功能：运行 git grep -n -i "embedding" -- src/tap_ai，贴出全部原始输出

6. 入库任务会不会被多个后端实例重复处理
   KbIngestWorker 取任务的完整代码原文。重点看：有没有 SELECT ... FOR UPDATE、带条件的 UPDATE（如 WHERE status='pending'）、分布式锁（Redis）等机制
   结论只能是「有防重复机制」「没有」「无法确定」，并说明依据

【报告格式】
- 按 1 到 6 的顺序写，每条一个小标题
- 最后必须有这张核对表，6 行都要有，不能合并：
  | 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
- 核对表里写"完成"、但正文没有原文代码的，视为未做
