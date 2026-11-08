
1. 插件文件当前未确认： `src/tap_ai/config/plugins.py:17-22` 的 `ENABLED_PLUGINS` 只有 `models.llm.build` 和 `storage.blob.build`，没看到检索插件。`git branch` 里有 `remotes/origin/feature/rag-knowledge-graph`，`git log -- src/tap_ai/plugins` 里也没有明确检索插件已进主线的证据。
2. 当前主线里原样贴出的只有模型插件：`src/tap_ai/plugins/models/llm.py:54-58` 定义了 `class LiteLLMModelGateway(ModelGatewayPort): __port_name__ = "model_gateway"`。它的 `build()` 本次未直接读到，检索插件的 `build()` 未确认。
3. 检索插件实现了哪个 Protocol：未确认，因为主线 `contracts/` 下没有 `QaAnswerPort / ChunkSourcePort / ChunkPublishPort`。目前能确认的工具插座是 `src/tap_ai/contracts/tool.py:277-286` 的 `ToolPort`，以及模型插座 `contracts/model_gateway.py`。
4. 检索插件对外方法、参数、返回类型、结果字段：未确认。主线里没找到这类插件实现，因此也没有证据证明返回结果里含 `chunk_id / source_file / page_or_sheet / content / score`。
5. 有没有按文件取出全部切片或按 `source_file` 过滤的方法：新 backend 主线里未确认。旧项目有，见 `kb_poc/indexing/azure_search_store.py:229-249` 的 `get_chunks_by_source_file(...)`。
6. 有没有写入索引的方法：新 backend 主线里未确认。旧项目有，见 `kb_poc/indexing/azure_search_store.py:170-202` 的 `upload_document_chunks(...)` 和 `delete_document_chunks(...)`。
7. 检索插件配置项在 `settings.py` 里叫什么：主线里未确认，因为 `src/tap_ai/config/settings.py:64-77` 只有 LiteLLM、MySQL、Redis、Langfuse 这些配置。没看到 AI Search 索引地址、索引名、密钥字段。
8. `ENABLED_PLUGINS` 全文见 `src/tap_ai/config/plugins.py:17-22`，只有 `"models.llm.build"` 和 `"storage.blob.build"`。`bootstrap` 取插件键名的逻辑在 `src/tap_ai/bootstrap.py:72-76`，优先用实例的 `__port_name__`，然后注册到对应 registry。
9. 真实问答链路从 `src/tap_ai/api/chat.py:240-300` 的聊天接口开始，进入 `ChatService.send_new/send/retry`，再到 `application/chat.py:642-857` 的 `_stream_reply -> _stream_reply_impl -> _run_react_flow`。最终答案在流程里持久化并通过 SSE `done` 事件返回。
10. 可以不经过 HTTP，直接在 Python 调 `app.state.chat_service.send_new(...)` 或 `send(...)`。参数证据见 `api/chat.py:258-289`，至少会传 `message_content`，其余按场景带 `conv_id / saas_id / workspace_id / project_id / user_id / selected_model / provider / file_ids`。
11. 一次调用会写会话消息审计，也会写 Redis 锁和取消标记，并可能写 Langfuse。证据分别见 `application/chat.py:288-343, 373-433`、`application/persistence.py:60-141`、`application/chat.py:658-695`。
12. 同事的检索目前不能证明是作为 `ToolPort` 接入的，因为主线 `_build_react_deps()` 只注册了 `workspace_files / attachment_tools / shell_http / skill_tools`。证据在 `src/tap_ai/bootstrap.py:394-421`，没有检索工具注册代码。
13. `tool_trace` 写入在 `src/tap_ai/application/persistence.py:107-139`，字段结构定义在 `src/tap_ai/contracts/audit.py:59-67` 和 `persistence/models.py:219-222`。从注释不含敏感参数与原文看，不能证明检索结果的 `chunk_id / source_file / content` 会被完整记进去。
14. 主线里目前未确认存在“不走智能体、只检索一次再生成一次”的问答路径。已读到的正式聊天主链路都走 ReAct，见 `application/chat.py:802-825`。
15. 一次问答的最终答案文本在流程里落在变量 `answer`，并进入 `ChatEvent(kind="done", answer=...)`。证据见 `application/chat.py:759-794`；正常主流程的持久化也是把 `answer` 传给 `ResultPersister.persist(...)`。
16. 旧项目文档 id 生成方式是 `doc::` + 文件内容 sha256 前 16 位。证据见 `kb_poc/indexing/identity.py:14-24`。
17. 旧项目切片 id 生成方式不是 uuid，也不是自增；主链路是 `sha1(f"{source_file}:{locator}:{part}")[:12]`。证据见 `kb_poc/ingestion/ingestor.py:243-277`。
18. 同一个文件内容不变、重复入库两次，文档 id 会保持不变，因为它只看内容 sha256。切片 id 在旧主链路下也会保持不变，因为它只看 `source_file + locator + part`，证据还是 `identity.py:17-24` 和 `ingestor.py:243-244`。
19. 文件内容变了重新入库，旧项目有“先按 `document_id` 删除，再上传新 chunks”的能力。证据见 `kb_poc/indexing/azure_search_store.py:170-202`；但你给的新 backend 主线里这套入库逻辑未确认已迁入。
20. 旧项目判断“已入库过”依赖内容哈希链路，`doc_id = doc:: + file_hash[:16]`，状态记录在 `state.db` 的 `files` 表。证据见 `kb_poc/skills/kg_sync/runtime.py:430-446`。
21. 知识图谱模块在新 backend 主线里未确认存在，因为本次对 `src/tap_ai` 搜索没有找到 kg / graph sync 实现。旧项目有按文档同步的入口，见 `kb_poc/skills/kg_sync/runtime.py`。
22. 新 backend 主线里自动触发知识图谱同步：未确认，不看到代码就不能说有。至少当前已读聊天链路和 bootstrap 装配里，没有看到入库完成后自动调 KG 同步的触发代码。

## A. 写转换头插件需要的信息是否齐全
- `QaAnswerPort`：不齐全，因为新 backend 主线没有这个契约；但现有聊天/模型链路足够让你先定义一个新 Port 再接 `ChatService` 或更下层生成链路。`ModelGatewayPort.acompletion()` 和 `astream_turn()` 的现有证据是齐的。
- `ChunkSourcePort`：不齐全，主线没有检索切片读取插件和契约；只能参考旧项目 `get_chunks_by_source_file(...)` 先设计接口。真正要落地前，得先补 backend 里的检索 Port 和 settings。
- `ChunkPublishPort`：也不齐全，主线没看到写入 Port；旧项目只有 `upload_document_chunks/delete_document_chunks` 可参考。也就是说，转换头插件现在最多先把接口壳和 DTO 定下来，真实发布链路还缺后端契约。

## B. id 与增量的结论
- 旧项目文档 id 是基于内容哈希：`doc::` + 文件内容 sha256 前 16 位；切片 id 在主入库链路里是基于 `source_file / locator / part` 的 sha1 前 12 位，不是 uuid。这个结论有直接代码证据，不是猜的。
- 切片内容被修改后，如果要让知识图谱同步正确，旧链路需要按文档维度重新同步；从已有证据看，至少要先按 `document_id/doc_id` 清旧的图谱来源，再按新 chunks 重建。新 backend 主线里这条自动同步链路目前还没看到。

