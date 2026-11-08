【任务】K9a 修订。先做第一步（只读），贴出结果后停下，等我回复"继续"。运行命令一律加 --no-sync。
允许修改的文件：src/tap_ai/plugins/ingest/sdk_ingest.py、tests/unit/test_library_kb_ingest_plugin.py、bootstrap.py 中 library_kb 代码块内部的代码、.env.example（只追加）

【第一步：只读，贴出原文（文件:行号）】
1. sdk_ingest.py 全文
2. bootstrap.py 中 library_kb 代码块全文（前后各 5 行），并说明：入库插件的 close 和 worker.stop 分别在第几行登记到 lifecycle
3. build_ingest 现在从哪里读取 kb_indexes、Azure endpoint/key、Neo4j 配置（贴代码）；
   以及 src/tap_ai/plugins/extensions/knowledge/settings.py 中这些字段的定义和配置类名
4. SDK 中：TapIngestClient 是否有 close()，它或 ingest() 是否会调用各个 sink 的 close()；
   AzureAISearchSink（及其内部的 repository/store）在什么时候调用 create_or_update_index，有没有参数可以关闭；
   Neo4jGraphSink 构造时传入 driver 的参数名
5. 写出修订方案（每一条怎么改），先不写代码

【第二步：修改】
1. bootstrap：getattr(app_settings, "library_kb_ingest_sink", "none") 改为 app_settings.library_kb_ingest_sink
2. 配置来源：kb_indexes、Azure、Neo4j 配置，一律通过 knowledge 插件的 settings 配置类读取（与知识库问答链路使用同一个类），不另外新增同义配置
3. Neo4j driver：
   - build_ingest 中只创建一个 neo4j driver（同步版 GraphDatabase.driver），每次构造 Neo4jGraphSink 都传入这个 driver
   - 任何地方都不调用 Neo4jGraphSink.close()；如果 TapIngestClient 会自动关闭 sink，就不调用 client 的关闭方法（第一步第 4 条的结论写在注释里）
   - 适配器提供 close()，只关闭这个共享 driver；bootstrap 用 lifecycle.callback 登记
   - 登记顺序：入库插件的 close 必须在 worker.stop 之前登记（lifecycle 倒序关闭，先停 worker 再关 driver）。在登记处用中文注释写明原因
4. 防止误建索引：azure 模式下，第一次写某个索引前，用 SearchIndexClient.get_index 检查索引是否存在（只读），结果缓存在内存中；
   不存在 → 失败，error_code="index_not_found"，error_message="索引不存在：{索引名}"，不调用 SDK 入库。
   如果第一步查到 SDK 有关闭自动建索引的参数，同时把它关掉
5. 每次调用：tempfile.TemporaryDirectory() 作为 work_dir 显式传入；用完自动删除
6. 结果映射：
   - len(report.items) != 1 → 失败，error_code="unexpected_result"，error_message="入库结果数量异常"
   - status == "skipped" → 失败，error_code="skipped"，error_message="入库被跳过"
   - 其余规则保持不变（document_id 一致性、partial_index、empty_content、异常转失败、截断 500 个字符）
7. .env.example 追加中文注释：OCR 依赖 paddleocr（必装）；首次运行可能需要下载 OCR 模型，离线环境需要提前准备模型文件；OCR 占用 CPU 和内存较多，建议 library_kb_worker_concurrency=1
8. 测试补充：
   - 共享 driver：多次调用 ingest_file 后，假 driver 的 close 没有被调用；调用适配器 close() 后才被调用 1 次
   - 索引不存在 → index_not_found，且没有调用 SDK
   - items 数量为 0 或 2 → unexpected_result
   - skipped → 失败
   - 架构检查：src 下只有 sdk_ingest.py import tap_ingest_sdk；sdk_ingest.py 中不出现 create_index、delete_index、delete_documents
9. 每改完一个文件，贴出 git diff --stat 和 git diff -w --stat

【完成报告】通用规则第十条的全部原始输出，另外贴出：bootstrap.py library_kb 代码块的 git diff 全文；真实 memory 用例的输出




K9a 验收（你自己看）：

8 步检查都通过（命令加 --no-sync），ruff 4 个、mypy 6 个
bootstrap 的 diff 里，入库插件 close 的登记行，行号比 worker.stop 的登记行小
在 sdk_ingest.py 里搜：
get_index：有，就是防误建索引的检查
.close()：只出现在关闭共享 driver 的那一处
getattr(：bootstrap 里那一处已经改掉
测试结果里有"真实 memory 用例 passed"
全部通过后提交：feat(library-kb): K9a SDK 入库插件