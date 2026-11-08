【任务】K9b：IndexInventoryPort 的实现（只读 Azure 索引）。先做第一步（只读），贴出结果后停下。
【允许修改的文件】新建 src/tap_ai/plugins/ingest/index_inventory.py、tests/unit/test_library_kb_inventory_plugin.py；
bootstrap.py 中 library_kb 代码块的 inventory=None 一行
【第一步】
1. 贴出 plugins/extensions/knowledge 中创建 SearchClient 的原文
2. 贴出 SDK 索引字段中 document_id、文件名字段的定义，以及是否 facetable / filterable
3. 写出 list_documents 的实现方案（如何按 document_id 统计切片数、如何取得每个文档的文件名、文档很多时的上限），先不写代码
【第二步】
1. list_documents(*, saas_id)：索引名取自 kb_indexes；找不到对应租户时返回空列表并记 warning；包含 jp-poc 时同样返回空列表
2. 只允许调用 search 方法（查询）。文件中不得出现 upload_documents、merge_documents、merge_or_upload_documents、delete_documents、create_index、delete_index
3. SearchClient 写法照抄同事的；同步方法用 asyncio.to_thread 调用，或使用 SDK 的异步客户端（照仓库现有写法）
4. bootstrap：library_kb_ingest_sink == "azure" 时构造 inventory
5. 测试使用假的 SearchClient；架构检查：在 index_inventory.py 中搜索第 2 条列出的方法名，应为 0 处
【完成报告】8 步检查原始输出；bootstrap.py 的 git diff 全文



.env末尾加上
set "TAP_AI_LIBRARY_KB_WORKER_ENABLED=true"
set "TAP_AI_LIBRARY_KB_INGEST_SINK=memory"


dbeaver 查询：
SELECT file_name, status, chunk_count, document_key, last_error
FROM library_kb_document WHERE saas_id = 'kbtest' ORDER BY update_time DESC;

SELECT file_name, status, attempts, error_code, error_message
FROM library_kb_job WHERE saas_id = 'kbtest' ORDER BY create_time DESC;


测试清理：
DELETE FROM library_kb_job WHERE saas_id = 'kbtest';
DELETE FROM library_kb_document WHERE saas_id = 'kbtest';