Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git grep -n -E "key=True|SimpleField\(|SearchableField\(" -- src/tap_ingest_sdk/sinks

【任务 K3a】入库时让 Neo4j 写入端抽取实体和关系、生成实体向量。大模型抽取和向量都走后端模型网关。实体向量复用已有的 GatewayEmbeddingProvider，不新建向量提供者。不新增任何开关。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend
Python 统一用 C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe（下文 <py>），开工先运行
& <py> -c "import sys, tap_ingest_sdk; print(sys.executable)"
不得使用系统 python 或 uv run。

【绝对禁止】
- 不改 src/tap_ai/plugins/extensions/knowledge/ 下任何文件（问答是同事的业务）
- 不改 SDK 仓库的任何文件
- 不直接调用 litellm 或任何模型 SDK；大模型和向量调用一律经过后端模型网关
- 不新增 bool 开关；不改 library_kb_graph_enabled 的默认值
- 不读 .env；不连接外部服务；不安装包；git 只允许只读命令；不对已有文件运行 ruff format

【本次允许修改的文件】
- src/tap_ai/plugins/ingest/sdk_ingest.py（只改 _sinks_factory，以及它需要的构造参数）
- 新建 src/tap_ai/plugins/ingest/kg_providers.py（只放大模型抽取用的 GatewayChatProvider）
- src/tap_ai/bootstrap.py（只改创建入库插件时传入模型网关的那几行，如有需要）
- tests/unit/test_library_kb_ingest_plugin.py（只追加用例）
- 新建 tests/unit/test_kg_providers.py

【开工前确认（只读，贴原始输出）】
1. GatewayEmbeddingProvider 的位置和全文：git grep -n "class GatewayEmbeddingProvider" -- src
   重点说明：它从 SDK 的工作线程里被同步调用时，是怎么去调用异步的模型网关的（run_coroutine_threadsafe、事件循环来自哪里）
2. sdk_ingest.py 中 _sinks_factory 全文，以及 GatewayEmbeddingProvider 在哪里被创建、传给了谁
3. SDK 中以下内容的签名和全文（只读）：
   - tap_ingest_sdk.protocols 的 LLMProvider（complete 的参数和返回类型）
   - sinks/_kg_llm_extract.py 的 LLMRelationExtractor.__init__
   - sinks/_kg_extract.py 的 DefaultRelationExtractor.__init__ 和 combine_extractors
   - sinks/_neo4j.py 的 Neo4jGraphSink.__init__、_embed_entities；_embed_entities 里向量计算失败时是抛异常还是记日志
4. 后端其他地方（例如 application/library_eval.py）调用模型网关做一次非流式补全时的写法：取哪个模型、怎么拼消息、怎么收集流式结果（async for + aclose）
5. library_kb_worker 中单个任务的超时时间（配置名和默认值）

【要做的 5 件事】

1. 新建 plugins/ingest/kg_providers.py，类 GatewayChatProvider，实现 SDK 的 LLMProvider：
   - 构造参数：模型网关、事件循环的获取方式、模型名、单次超时秒数。写法照抄 GatewayEmbeddingProvider（开工确认第 1 条），两个类桥接同步和异步的方式必须一致，不能自创第二种
   - complete(...)：把提示词按开工确认第 4 条的写法交给模型网关，用 async for 收集全部文本，结束时 aclose，返回完整字符串
   - 模型名：与开工确认第 4 条中后端默认使用的模型一致，不新增配置项
   - 超时或网关报错：向上抛出异常（LLMRelationExtractor 会接住并返回 []，不会中断入库）。文件开头中文注释写明这一点
   - 中文注释说明：为什么不直接调 litellm（统一走网关，额度、日志、Langfuse 记录才完整）

2. _sinks_factory 中创建 Neo4jGraphSink 时新增两个参数：
   - relation_extractor = combine_extractors(DefaultRelationExtractor(...), LLMRelationExtractor(GatewayChatProvider(...)))
     构造参数按开工确认第 3 条的签名填写，未列出的参数用 SDK 的默认值
   - embedding_provider = 写 Azure 时用的同一个 GatewayEmbeddingProvider 实例（不新建第二个）
   - 其他参数（uri、user、password、scope、database、driver）不变
   - 中文注释说明：切片向量（写 Azure）和实体向量（写 Neo4j）用同一个提供者、同一个模型，维度一致

3. 如果开工确认第 3 条显示 _embed_entities 在向量计算失败时会抛异常并导致整个文档失败：停下来告诉我，不要自己改 SDK，也不要在后端吞掉异常

4. 测试（全部用假的模型网关和假的 Neo4j，不连外部服务）：
   tests/unit/test_kg_providers.py
   a. GatewayChatProvider 在另一个线程里调用 complete，能拿到假网关流式返回的完整文本，并且调用了 aclose
   b. 假网关抛异常时，complete 向上抛出异常
   c. 超时时向上抛出超时异常
   d. 源码中不出现 "litellm"
   tests/unit/test_library_kb_ingest_plugin.py（追加）
   e. 图谱开关打开且 Neo4j 配置完整时：Neo4jGraphSink 收到的 relation_extractor 不为空；embedding_provider 与 Azure 写入端用的是同一个对象（用 is 判断）
   f. 图谱开关关闭时：不创建 Neo4jGraphSink，也不创建 GatewayChatProvider
   g. 用真实 SDK 和内存版写入端处理一个测试文件，假网关返回一段固定的抽取结果：写入端收到了实体和关系（如果已有 test_sdk_ingest_success_with_memory_mode_real_sdk 可以扩展，就在它旁边追加一个新用例，不改原用例）
   h. 假网关在抽取时抛异常：文档仍然处理成功，只是没有大模型抽出的关系

5. 验证（贴原始输出）：
   a. & <py> -m pytest -q tests/unit/test_kg_providers.py tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 15
   b. & <py> -m pytest -q 2>&1 | Select-Object -Last 15（失败数不得比修改前多；修改前先跑一次记下数字）
   c. & <py> -m ruff check src/tap_ai/plugins/ingest tests/unit/test_kg_providers.py tests/unit/test_library_kb_ingest_plugin.py
   d. & <py> -m mypy src/tap_ai/plugins/ingest
   e. & <py> -m ruff format --check src/tap_ai/plugins/ingest/kg_providers.py tests/unit/test_kg_providers.py
   f. git diff --stat 和 git status：只能出现允许的文件
   g. & <py> C:/Users/234393/Desktop/check_chars.py src tests

【需要单独报告的内容（只报告，不修改）】
- 一个 10 页的文档大约有多少个切片，按 LLMRelationExtractor 的实现，会调用几次大模型（每个切片一次，还是按批）
- 第 5 条开工确认中的任务超时，按每次大模型调用约 5 秒估算，够不够；不够的话建议改成多少

【完成报告】按【通用规则】第五条

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–5 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4a–4h | | |
| 5a–5g | | |
| 单独报告 2 项 | | |



