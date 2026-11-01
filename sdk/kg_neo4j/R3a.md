【任务 R3a】只读排查：POC 图谱中的切片编号，和 jp-poc 索引中的切片编号是否一致。

【绝对禁止】违反任意一条，立即停止并告诉我：
- 不修改、不新建、不删除任何文件
- 不读取任何 .env 文件
- 不连接 Azure、Neo4j、MySQL、Redis、大模型；不运行任何入库命令或 ingest 命令
- 不执行任何 SQL（SQL 写出来给我，由我执行）
- git 只允许 status / log / show / grep / ls-files
- 找不到的内容写"未找到"，并贴出你用过的搜索命令。不允许推测、不允许编造

【涉及的目录】
- POC 项目：C:\Users\234393\Desktop\jap-cycle-poc（包含 kb_poc、kg_api 等目录；如果 kg_api 不在这里，先找到它的位置）
- 后端：C:\Users\234393\Desktop\tap-ai-backend
- SDK：C:\Users\234393\fwd-tap-common\fwd-tap-ingest

【要做的 6 件事】每一件都必须贴出 文件:行号 + 原文代码，只写结论的视为没做

1. POC 写入 jp-poc 索引时，切片的主键字段叫什么、值是怎么算出来的
   （找到构造上传文档 / 字段的代码，贴出主键字段的定义和计算函数的完整原文）

2. POC 建图谱时，Chunk 节点的编号是怎么来的
   （kb_poc\kg 下写入 kg_nodes 表中 type='Chunk' 记录的代码，贴出 node_id 的赋值原文；
    同时贴出 mentioned_in 边的 target 用的是什么值）

3. 对比第 1 条和第 2 条：是不是同一个值、同一种算法。
   回答只能是三种之一：「一致」「不一致」「无法从代码确定」，并说明依据

4. kg.db（kg_api 使用的 SQLite 文件）的完整路径，以及建表语句
   （找到 CREATE TABLE kg_nodes、CREATE TABLE kg_edges 的原文，贴出全部字段）

5. 后端问答顺着 MENTIONED_IN 拿到 chunk_id 以后，用它去 Azure 索引查原文时，按哪个字段查
   （从 tap-ai-backend 的 src\tap_ai\plugins\extensions\knowledge 里找：
    调用 _Q_CHUNKS 的地方 → 拿到 chunk_id 以后的下一步 → 查询 Azure 时用的过滤条件或字段名，逐层贴原文）

6. 写出两条只读 SQL，由我在 kg.db 上执行：
   a. 取 5 条 Chunk 节点：SELECT node_id 以及其他所有字段 FROM kg_nodes WHERE type='Chunk' LIMIT 5
   b. 取 5 条 mentioned_in 边：SELECT * FROM kg_edges WHERE type='mentioned_in' LIMIT 5
   （字段名以第 4 条查到的建表语句为准）

【报告格式】
- 按 1 到 6 的顺序写，每条一个小标题
- 最后必须有这张核对表，6 行都要有，不能合并：
  | 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
- 核对表里写"完成"、但正文没有原文代码的，视为未做




python -c "import sqlite3; c=sqlite3.connect(r'file:<kg.db路径>?mode=ro', uri=True); [print(r) for r in c.execute(\"SELECT * FROM kg_nodes WHERE type='Chunk' LIMIT 5\")]; print('---'); [print(r) for r in c.execute(\"SELECT * FROM kg_edges WHERE type='mentioned_in' LIMIT 5\")]"
