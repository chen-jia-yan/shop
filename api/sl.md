前端上传文件
  ↓
KbAdminService.upload           判重 → 原文件存进 blob → MySQL 写一条文档记录和一个任务（待处理）
  ↓（后台轮询）
KbIngestWorker                  抢到任务 → 读出原文件 → 在后台线程里调用入库插件
  ↓
SdkIngestAdapter.ingest_file    把 saas_id 换成索引名（如 hk → hk 的索引），组装 SDK 客户端
  ↓
TapIngestClient.process(source)   ← 全部在内存里完成
  ├─ ParserRegistry  按扩展名选解析器（pptx / docx / xlsx / pdf）→ 段落、表格、幻灯片
  ├─ DefaultChunker  按长度切成切片，每个切片算出固定的 chunk_id
  └─ embedding_provider.embed(全部切片的正文) → 每个切片得到一个向量
  ↓  得到一个 document 对象：document.chunks = [切片1, 切片2, ...]，每个切片有正文、编号、页码、向量
for sink in sinks: sink.upsert(document)
  ├─ AzureAISearchSink  → Azure 索引：每个切片一条（正文 + content_vector + 元数据）
  └─ Neo4jGraphSink     → Neo4j（scope = 索引名）：
        Document -HAS_CHUNK-> Chunk
        （有抽取器时）Entity -MENTIONED_IN-> Chunk、Entity -关系-> Entity
  ↓
回到 Worker → MySQL 里把任务和文档标记为成功，记下切片数






|项目                        |结果                                                                            |影响                               |
|--------------------------|------------------------------------------------------------------------------|---------------------------------|
|`GatewayEmbeddingProvider`|在 `plugins/ingest/embedding.py`，直接调用模型网关的**同步**方法 `gateway.embed(...)`，没有做异步转换|我之前写的「照抄它的异步转换方式」不成立，第 1 件事要改（见下）|
|它被传给了谁                    |只传给了 `SdkIngestAdapter`，用来算切片向量；**没有传给 Neo4j 写入端**                            |和之前的判断一致，K3a 要补的就是这里             |
|实体向量失败时                   |`_embed_entities` 只打警告并跳过，下次入库再重试，**不会让整个文档失败**                               |好事，第 3 件事不用停，可以继续                |
|`LLMProvider.complete`    |参数是消息列表 `messages`（每条有 role 和 content），**不是一段文字**                             |`GatewayChatProvider` 要按这个签名写    |
|大模型抽取失败时                  |打警告并返回空列表                                                                     |不会中断入库                           |
|任务超时                      |`library_kb_job_timeout_sec`，默认 600 秒                                         |够不够，要看大模型调用次数（下面要它报告）            |


纠正我上一条说的一处： 实体向量算的不只是实体名称，而是「名称 + 类型 + 相邻实体」拼成的一段文字（‎`embedding_text`）。另外，这段文字会先算一个指纹，没变就不重算，所以重新上传文档时，不会把所有实体的向量都重算一遍。

要调整的地方：大模型抽取怎么调用模型网关 ￼

向量这边有同步方法，可以直接调。聊天补全目前只看到异步流式的 ‎`acompletion`。SDK 是在后台线程里同步调用的，所以要先确认模型网关有没有同步的聊天方法：

- 有同步方法：直接用，写法和 ‎`GatewayEmbeddingProvider` 保持一致，最简单。

- 没有：在后台线程里，把异步调用投递回主事件循环去执行，然后等结果，也就是 ‎`run_coroutine_threadsafe`。

 - 不要在后台线程里用 ‎`asyncio.run` 新开事件循环。 模型网关内部可能缓存了绑定在主循环上的连接，换一个循环去用，容易报「attached to a different loop」这类错误。



 【K3a 补充说明】开工前确认已看过，按以下调整继续完成 K3a。其余要求不变。

一、第 1 件事改为：
1. 先确认模型网关有没有同步的聊天补全方法（只读，贴原始输出）：
   git grep -n -E "def (embed|completion|complete|acompletion|chat)" -- src/tap_ai/contracts/model_gateway.py src/tap_ai/plugins
   并贴出 ModelGatewayPort 的全文
2. 如果有同步的聊天补全方法：
   - GatewayChatProvider.complete(messages) 直接调用它，写法与 GatewayEmbeddingProvider 一致（构造参数 gateway、model；同步调用）
   - 返回完整文本（如果返回的是流，就逐段拼接，结束时关闭）
3. 如果只有异步的 acompletion：
   - GatewayChatProvider 构造参数：gateway、model、timeout_s（默认 120）
   - 新增方法 bind_loop(loop)：保存主事件循环
   - complete(messages)：
     · 没有绑定循环：抛 RuntimeError("大模型抽取未绑定事件循环")
     · 当前线程就是该循环所在的线程：抛 RuntimeError（否则会互相等待卡死），中文注释说明原因
     · 否则：用 asyncio.run_coroutine_threadsafe 把一个协程投递到主循环，协程内照抄 core/library_eval/llm_call.py 的写法（acompletion → async for 拼接 → finally aclose）；用 future.result(timeout=timeout_s) 等结果，超时时 future.cancel() 并抛出超时异常
     · 不得 import tap_ai.core.library_eval（不同模块之间不互相依赖），照抄那十几行即可
     · 不得使用 asyncio.run 或新建事件循环，中文注释说明原因（模型网关的连接可能绑定在主循环上）
   - SdkIngestAdapter 新增 bind_loop(loop)，转交给 GatewayChatProvider（没有图谱写入端时什么也不做）
   - application/library_kb_worker.py：KbIngestWorker 启动时（在主循环里运行的那个方法开头），取 asyncio.get_running_loop()，如果 ingest 有 bind_loop 方法就调用。只加这几行，本文件加入允许修改名单
   - 测试 4a 改为：在主循环里绑定，再从 asyncio.to_thread 的线程里调用 complete，能拿到完整文本并调用了 aclose；追加：未绑定时报错；在主循环线程里直接调用时报错（不卡死）
4. 模型名：用 library_eval 调用 complete_text 时传入的同一个配置（贴出该配置名和默认值），不新增配置项

二、第 3 件事：已确认 _embed_entities 失败时只告警跳过，不用停，继续第 4、5 件事。

三、单独报告追加一项（只读）：
- sinks/_kg_llm_extract.py 中 LLMRelationExtractor.__call__ 全文，以及 MAX_PROMPT_CHARS 的值
- 回答：一个文档是调用一次大模型、按切片逐个调用，还是分批调用？文档正文超过 MAX_PROMPT_CHARS 时，超出部分是被截掉，还是会分多次抽取？
- 按一个 10 页、约 30 个切片的文档估算总耗时，600 秒的任务超时够不够
