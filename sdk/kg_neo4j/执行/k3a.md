【任务 K3a】后端入库时默认用"规则 + 大模型"抽取关系并写入实体向量。抽关系走后端模型网关（这样会被 Langfuse 记录），向量直接调用 litellm 同步接口。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【本次允许修改的文件】
- 新建 src/tap_ai/plugins/ingest/kg_providers.py
- src/tap_ai/plugins/ingest/sdk_ingest.py
- src/tap_ai/application/library_kb_worker.py（只追加：worker 启动时把事件循环交给入库插件，几行）
- src/tap_ai/bootstrap.py（只改创建入库插件那一处，把模型网关传进去）
- src/tap_ai/plugins/extensions/knowledge/settings.py（只追加 kg_llm_model 一个字段）
- .env.example（只追加）
- 新建 tests/unit/test_kg_providers.py；tests/unit/test_library_kb_ingest_plugin.py 只追加用例

【背景】
- 入库时 SDK 是在单独的线程里运行的（library_kb_worker.py 用 asyncio.to_thread）。这时主线程的事件循环是空闲的
- 后端的模型网关是异步的，并且只支持流式调用（async for 读取，最后在 finally 中 aclose）
- 做法：在线程里用 asyncio.run_coroutine_threadsafe(协程, 主事件循环).result(timeout=...) 调用模型网关。主事件循环在 worker 启动时交给入库插件

【开工前确认（只读，贴原始输出）】
1. 模型网关的接口定义（contracts 中的 ModelGatewayPort）原文；仓库中任意一处"用 async for 读取流式结果并 aclose"的现有写法原文（评估服务里就有）
2. 模型网关调用会被 Langfuse 记录的依据：网关实现中调用 observability 的那几行原文
3. bootstrap.py 中创建入库插件（build_ingest）那一处的原文，以及 container.model_registry.get("model_gateway") 的现有用法
4. library_kb_worker.py 中 worker 启动的方法原文（start / run 之类，是否是 async、是否在事件循环中被调用）
5. SDK 中 DefaultRelationExtractor、LLMRelationExtractor、combine_extractors 的 __init__ / 函数签名原文；
   LLMRelationExtractor 调用失败时的处理原文；Neo4jGraphSink._embed_entities 调用失败时的处理原文
6. SDK 中 AzureAISearchSink 生成切片向量时，地址、密钥、模型从哪里来（K1b 之后的代码），贴原文
7. 后端 config/settings.py 中 LiteLLM 地址、密钥、默认模型的字段名和默认值原文；knowledge/backends/litellm_embedding.py 全文

【要做的 7 件事】

1. 新建 kg_providers.py，文件开头中文注释说明：这两个类给 SDK 入库使用；为什么抽关系要回到主事件循环调用模型网关
   a. GatewayChatProvider（实现 SDK 的 LLMProvider 接口）
      - __init__(self, *, gateway, model: str, timeout_s: float = 180.0)
      - bind_loop(self, loop: asyncio.AbstractEventLoop) -> None：保存主事件循环
      - complete(self, messages) -> str：
        · 没有绑定事件循环 → 抛出 RuntimeError("模型网关未就绪")
        · 用 asyncio.run_coroutine_threadsafe 把一个协程交给主事件循环执行，result(timeout=timeout_s) 等待结果
        · 协程内部：调用网关，temperature=0.0，流式读取并拼接全部文字，finally 中 aclose。写法照抄开工前确认第 1 条中的现有写法
        · 超时 → 取消这个 future，抛出 TimeoutError
   b. LiteLLMEmbeddingProvider（实现 SDK 的 EmbeddingProvider 接口）
      - __init__(self, *, model: str, dimension: int, api_base: str, api_key: str, timeout_s: float = 60.0)
      - dimension 属性
      - embed(self, texts) -> list[list[float]]：调用 litellm.embedding（同步），参数写法照抄 litellm_embedding.py
      - 返回的向量长度与 dimension 不一致时抛出 ValueError，提示中写明期望维度和实际维度
   - 两个类都不读取环境变量，所有配置从参数传入

2. KnowledgeSettings 追加：kg_llm_model: str = ""，注释"入库时抽取关系使用的模型；为空时使用后端默认模型"
   .env.example 追加：# TAP_AI_KB_KG_LLM_MODEL=

3. build_ingest 增加一个参数 model_gateway（默认 None）；bootstrap.py 创建入库插件时把模型网关传进去
   入库插件对象增加方法 bind_loop(loop)，内部转交给 GatewayChatProvider

4. library_kb_worker.py：worker 在事件循环中启动时，调用一次 ingest.bind_loop(asyncio.get_running_loop())（ingest 没有这个方法时跳过）

5. sdk_ingest.py 的 _sinks_factory 中构造 Neo4jGraphSink 时追加：
   - relation_extractor=combine_extractors(DefaultRelationExtractor(), LLMRelationExtractor(chat_provider))
     （DefaultRelationExtractor 的参数与 SDK 命令行默认值一致，以开工前确认第 5 条为准）
     model_gateway 为 None 时只用 DefaultRelationExtractor()，并打印一条 warning
   - embedding_provider=LiteLLMEmbeddingProvider(...)：模型和维度用 KnowledgeSettings 的 embedding_model、embedding_dimensions；地址和密钥用后端 LiteLLM 配置
   - chat_provider 和 embedding_provider 在 _sinks_factory 外面创建一次，所有索引共用
   - 模型名：kg_llm_model 不为空就用它，否则用后端默认模型
   如果开工前确认第 6 条显示 AzureAISearchSink 的切片向量配置与后端不一致（模型或维度不同），停下来告诉我

6. 失败时的处理（只核对，不改 SDK）：在报告中写明，并贴出依据
   - 大模型抽关系失败（包括"模型网关未就绪"和超时）时，这个文件是不是只用规则抽取的结果，入库继续
   - 实体向量生成失败时，图谱是否照常写入
   任何一项会导致整个文件入库失败的，停下来告诉我

7. 测试（不调用真实服务）
   a. GatewayChatProvider：用假网关（异步生成器分几段返回文字）+ 在测试里启动的事件循环线程，complete 返回拼接后的完整文字；传给网关的 temperature 是 0.0
   b. GatewayChatProvider：未绑定事件循环时抛出 RuntimeError；假网关一直不返回时，超过 timeout_s 抛出 TimeoutError
   c. LiteLLMEmbeddingProvider：用 monkeypatch 替换 litellm.embedding；维度正确时返回向量，维度不对时抛出 ValueError
   d. _sinks_factory：图谱写入开启时，Neo4jGraphSink 收到的 relation_extractor 和 embedding_provider 都不是 None（用假的 Neo4jGraphSink 记录参数）
   e. model_gateway 为 None 时 relation_extractor 只有规则抽取
   f. kg_llm_model 为空时用后端默认模型，不为空时用配置值

【完成报告】按【通用规则】第五条；另外写明第 6 条的两个结论和依据


## 验收方法 ￼
1. 全部测试（新窗口，不设环境变量），失败数不比 K2b 之后多。
2. 抽关系的调用走了模型网关：

```powershell
uv run pytest -q tests/unit/test_kg_providers.py -v 2>&1 | Select-Object -Last 15

```

每个用例都是 PASSED。

3. 真实入库这一步，今晚和明天都先不做。原因：你本地的 hk 连的是同事共用的 Azure 索引，真实入库会改到他的数据；Neo4j 写入在你本地也是关着的。等有了专门测试用的索引，再做一次真实上传验证。这一项记在第十二节的待办里。

通过以后提交：

```powershell
git add -A
git commit -m "feat(kb): 入库默认使用规则加大模型抽取关系并写入实体向量，抽取调用走模型网关"

```

