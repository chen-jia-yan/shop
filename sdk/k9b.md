可以进入第二步，按下面的方案执行（与原提示词冲突时以这里为准）。运行命令一律加 --no-sync：
1. 配置：kb_indexes、Azure endpoint/key，通过 src/tap_ai/plugins/extensions/knowledge/settings.py 中的配置类读取（与 K9a 修订后相同），不在 SDK 中查找
2. settings.py 追加：library_kb_sync_max_documents: int = Field(default=5000, ge=100, le=50000)，中文注释"同步时最多列出的文档数"
3. list_documents(*, saas_id) 实现：
   a. 索引名 = kb_indexes.get(saas_id)；None → 返回 []，记 warning；索引名（转小写后）包含 jp-poc → 返回 []，记 warning
   b. 切片数：一次查询 search(search_text="*", facets=[f"document_id,count:{max}"], top=0)，从 get_facets() 中取每个 document_id 的 count
   c. 文件名：对每个 document_id 查询 search(search_text="*", filter=f"document_id eq '{escape_odata(id)}'", select=["source_file"], top=1)；
      escape_odata 复用 knowledge 插件中已有的函数；用 asyncio.Semaphore(8) 限制并发
   d. 文档数达到 max 时，记 warning "索引文档数达到上限，可能未完整列出"
   e. 使用异步 SearchClient，创建写法照抄 azure_search.py:80-89；客户端在 close() 中关闭，由 bootstrap 用 lifecycle.callback 登记（在 worker.stop 之前登记）
4. 只读约束：index_inventory.py 中只允许出现 search、get_facets 两种调用；不得出现 upload_documents、merge_documents、merge_or_upload_documents、delete_documents、create_index、create_or_update_index、delete_index
5. 测试：假的 SearchClient 返回 facets 和 source_file，覆盖：正常、租户未配置、jp-poc、达到上限、某个文档查不到文件名（source_file 为空字符串）；
   架构检查：在 index_inventory.py 中搜索第 4 条列出的方法名，应为 0 处
6. bootstrap：library_kb_ingest_sink == "azure" 时构造 inventory，替换 inventory=None；其他模式保持 None
完成后出完整的《完成报告》，中途不用停


K9b 验收：

在 index_inventory.py 里搜 upload、delete、create：0 处
搜 facets：有
在 bootstrap 里，inventory= 只在 azure 模式下才不是 None



// 1. 有哪几个 scope，每个 scope 下各有多少文档
MATCH (d:Document) RETURN d.scope AS scope, count(d) AS documents;

// 2. 每种节点各有多少个
MATCH (n) RETURN labels(n)[0] AS label, n.scope AS scope, count(*) AS cnt ORDER BY scope, label;

// 3. 节点有哪些属性（写 G1 要用）
CALL db.schema.nodeTypeProperties();

// 4. 关系有哪些属性（写 G1 要用）
CALL db.schema.relTypeProperties();

MATCH p=(a:Entity {scope:'scope名'})-[r]->(b:Entity) RETURN p LIMIT 50;