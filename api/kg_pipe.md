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
