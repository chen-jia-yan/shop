【任务 R3b】只读排查：SDK 往 Neo4j 写数据时，节点、关系、索引的具体格式。

【绝对禁止】
- 不修改、不新建、不删除任何文件；不读取任何 .env 文件
- 不连接 Neo4j、Azure、大模型；不运行 ingest 命令
- git 只允许 status / log / show / grep / ls-files
- 找不到的写"未找到"并贴出搜索命令，不允许推测

【范围】SDK：C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks

【要做的 6 件事】每件都要贴 文件:行号 + 原文

1. Neo4jGraphSink 建约束和建索引的 Cypher 原文
   （包括唯一约束、entity_label_ft 全文索引、entity_embedding 向量索引；
    向量索引的维度和相似度算法，如 cosine，也要贴出来）

2. Neo4jGraphSink.upsert() 写入 Entity 节点、Chunk 节点、实体之间的关系、MENTIONED_IN 关系的 Cypher 原文，
   以及每种节点和关系上写了哪些属性（例如 scope、id、type、label、label_norm、embedding、weight、document_id）

3. normalize_label 函数的完整原文

4. Entity 节点的 embedding 是怎么生成的：用的哪个模型、从哪个环境变量或参数读取、维度是多少。
   如果不写 embedding，写"不写"并贴出依据

5. LLM_RELATION_MAP 的完整原文（所有键值对一个都不能省略），以及 ALLOWED_RELATIONS 的原文

6. 仓库里关于 Neo4j 版本要求的说明：
   搜索 docker-compose、README、docs 里的 neo4j 镜像版本或版本说明；
   以及代码中有没有用到 CYPHER 25 或 SEARCH 子句

【报告格式】按 1 到 6 写，最后附核对表：
| 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |



CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition
