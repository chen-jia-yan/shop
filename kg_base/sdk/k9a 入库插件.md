【任务】K9a：IngestPort 的 SDK 实现（memory 和 azure 两种模式）。先做第一步（只读），贴出结果后停下，等我回复"继续"。
前提：本机虚拟环境已安装 tap_ingest_sdk（uv run --no-sync python -c "import tap_ingest_sdk" 能成功）。导入失败时停下报告。
本阶段运行测试和检查一律用 uv run --no-sync（防止 uv 移除本机安装的 SDK）。

【允许修改的文件】
- 新建：src/tap_ai/plugins/ingest/__init__.py、src/tap_ai/plugins/ingest/sdk_ingest.py、tests/unit/test_library_kb_ingest_plugin.py
- 只追加：src/tap_ai/config/settings.py、.env.example
- 允许修改的已有行（只有这几处，都是 library_kb 自己的代码）：
  a. settings.py 中 library_kb_storage_prefix 的默认值改为 "ai/kb"
  b. bootstrap.py 中 library_kb 代码块里 KbAdminService 的 ingest=None，改为使用 build_ingest 的结果
  c. tests/unit/test_library_kb_skeleton.py 中对 storage_prefix 默认值的断言，以及新增配置的断言

【第一步：只读】
1. 贴出 plugins/extensions/knowledge/plugin.py 的 build 函数，以及它读取 kb_indexes、kb_azure_search_endpoint、kb_azure_search_key、kb_neo4j_* 的原文
2. 贴出 bootstrap.py 中 library_kb 代码块的完整原文（前后各 5 行）
3. 贴出 SDK 中 TapIngestClient.__init__、ingest、SourceDocument.from_bytes、MemorySink、AzureAISearchSink.__init__、Neo4jGraphSink.__init__ 的签名
4. 确认：SDK 包内有没有 py.typed；uv run --no-sync mypy src 在 import tap_ingest_sdk 后会不会新增错误（先写一个临时的 import 检查，检查完删除，不留在仓库）
   如果会新增错误，停下报告，不要用 type: ignore
5. 写出 sdk_ingest.py 的类、函数清单和每个函数的作用，先不写代码

【第二步：修改】
1. settings.py 追加：
   library_kb_ingest_sink: Literal["none", "memory", "azure"] = Field(default="none")
   中文注释：none=不接入（上传返回"入库服务未配置"）；memory=真实解析、切片，只写内存，不写任何索引（本地验证用）；azure=写 Azure 索引，图谱开关打开时同时写 Neo4j
2. plugins/ingest/__init__.py：只做一件事，os.environ.setdefault("TAP_INGEST_SDK_NO_AUTOLOAD_ENV", "1")，并用中文注释说明原因（防止 SDK 导入时自动读取后端目录下的 .env）
3. plugins/ingest/sdk_ingest.py：
   a. 只有这个文件可以 import tap_ingest_sdk
   b. class SdkIngestAdapter（实现 IngestPort），构造参数：mode、index_resolver（saas_id -> 索引名 | None）、sinks_factory（索引名 -> sink 列表）。这里不读 settings
   c. ingest_file(*, saas_id, document_key, file_name, content) -> IngestOutcome，按顺序：
      - azure 模式：index_resolver 返回 None → 失败，error_code="no_index"，error_message="该租户未配置索引"
      - azure 模式：索引名（转小写后）包含 "jp-poc" → 失败，error_code="forbidden_index"，error_message="禁止写入该索引"
      - SourceDocument.from_bytes(content, filename=file_name, idempotency_key=document_key)
      - 每次调用新建 TapIngestClient（parser_registry=ParserRegistry.default()、chunker=DefaultChunker()、sinks=sinks_factory(索引名)）；
        memory 模式每次使用新的 MemorySink（防止内存累积）
      - 如果 SDK 需要工作目录，每次使用 tempfile.TemporaryDirectory()，用完自动删除
      - 取 report.items[0] 转换为 IngestOutcome：
        · status != "succeeded"（包括 skipped）→ 失败，error_code、error_message 取自结果；skipped 时 error_message="入库被跳过"
        · document_id != document_key → 失败，error_code="document_id_mismatch"，error_message="文档编号不一致"
        · azure 模式：indexed_count != chunk_count → 失败，error_code="partial_index"，error_message="部分切片写入失败"
        · chunk_count == 0 → 失败，error_code="empty_content"，error_message="未解析出文本内容"
        · 其余 → 成功，chunk_count 取 chunk_count
      - 捕获所有异常转为失败（error_code=异常类名，error_message 取前 500 个字符），noqa 写法照抄 chat.py 第 1398 行
      - error_message 一律截断到 500 个字符
      - 日志只记录 saas_id、document_key、file_name、status、chunk_count、耗时；不得记录文件内容和任何密钥
   d. def build_ingest(settings) -> IngestPort | None：
      - "none" → None
      - "memory" → SdkIngestAdapter(mode="memory", index_resolver=lambda _: "memory", sinks_factory=lambda _: [MemorySink()])
      - "azure"：
        · kb_indexes 为空，或 endpoint、key 为空 → raise RuntimeError("入库配置不完整：缺少索引映射或 Azure 配置")，不打印配置的值
        · kb_indexes 中任何一个索引名包含 "jp-poc" → raise RuntimeError("禁止写入 jp-poc 索引")
        · index_resolver 读取 kb_indexes.get(saas_id)
        · sinks_factory：[AzureAISearchSink(endpoint=..., index_name=索引名, credential=key)]；
          library_kb_graph_enabled 为 True 时，再加 Neo4jGraphSink(uri, user, password, scope=索引名, database=...)。
          Neo4j 配置不完整 → raise RuntimeError("图谱配置不完整")
        · Neo4j driver：按第一步第 3 条读到的 SDK 写法，确保不会每次调用都新建一个不关闭的连接。
          如果需要共享 driver，在 build_ingest 中创建，并返回关闭函数，由 bootstrap 登记 lifecycle.callback。
          第一步中先说明你的方案，等我确认
4. bootstrap.py：在 library_kb 代码块中，library_kb_ingest_sink != "none" 时，在代码块内部 import 并调用 build_ingest，结果传给 KbAdminService 和 worker 的 ingest。
   不改动代码块以外的任何代码
5. .env.example 追加（注释形式）：TAP_AI_LIBRARY_KB_INGEST_SINK=none，以及说明"azure 模式复用 TAP_AI_KB_INDEXES / TAP_AI_KB_AZURE_SEARCH_* / TAP_AI_KB_NEO4J_*；嵌入模型由 KB_AOAI_* 环境变量提供"
6. 测试 test_library_kb_ingest_plugin.py：
   - 用假的 sinks_factory 和假的 client，覆盖第 3c 条的每一种失败情况，以及成功的情况
   - build_ingest：none → None；azure 配置缺失 → RuntimeError；索引名包含 jp-poc → RuntimeError；错误信息中不含 key 的值
   - 一个真实的本地用例：mode=memory，用 SDK 真实的 TapIngestClient + MemorySink，入库一段 3 行的中文 txt 字节，
     断言成功、chunk_count > 0、document_id == 传入的 document_key（这个用例不连接任何外部服务）
   - 架构检查：src 下除了 plugins/ingest/sdk_ingest.py，没有文件 import tap_ingest_sdk
7. 每改完一个文件，贴出 git diff --stat <文件> 和 git diff -w --stat <文件>

【完成报告】通用规则第十条的全部原始输出（命令都加 --no-sync），另外贴出：
- bootstrap.py 的 git diff 全文
- 第 6 条真实 memory 用例的输出
- uv run --no-sync python -c "from tap_ai.plugins.ingest.sdk_ingest import build_ingest; print('ok')"