git grep -n -i "enabled" -- src/tap_ai/config/settings.py src/tap_ai/plugins
Select-String -Path .env.example -Pattern "ENABLED"


【任务 R3d】只读排查：列出后端和 SDK 两个仓库里所有的开关和配置项。

【绝对禁止】
- 不修改、不新建、不删除任何文件；不读取任何 .env 文件（.env.example 可以读）
- 不连接任何外部服务；不运行入库或 ingest 命令
- git 只允许 status / log / show / grep / ls-files
- 找不到的写"未找到"并贴出搜索命令，不允许推测

【范围】
- 后端：C:\Users\234393\Desktop\tap-ai-backend
- SDK：C:\Users\234393\fwd-tap-common\fwd-tap-ingest

【要做的 6 件事】每件都要贴 文件:行号 + 原文

1. 后端 src/tap_ai/config/settings.py 中，所有类型为 bool 的字段：字段名、默认值、上一行的注释

2. 后端 src/tap_ai/plugins 下所有 settings.py 中，所有 bool 字段（同上格式）；
   以及 kg_relation_types、所有和 neo4j 有关的字段（地址、用户名、密码、database 名等）

3. 对第 1、2 条中的每个 bool 字段，用 git grep 找出读取它的所有位置，并用一句话说明：为 False 时会跳过什么

4. SDK 中所有读取环境变量的地方：
   运行 git grep -n -E "os\.environ|getenv|BaseSettings|env_prefix" -- src
   贴出全部原始输出，再整理成表格：环境变量名 | 默认值 | 作用

5. SDK 中 OpenAILLMProvider 的完整类定义原文：它从哪些环境变量或参数读取模型地址、密钥、模型名

6. 后端 src/tap_ai/plugins/ingest/sdk_ingest.py 中构造 Neo4jGraphSink 的完整原文（上下各 20 行）；
   以及 library_kb_graph_enabled 为 False 时，这段代码走哪一条分支

【报告格式】按 1 到 6 写，最后附核对表，6 行都要有：
| 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
