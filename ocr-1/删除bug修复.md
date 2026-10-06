任务目标:统一 document_id,修好删除匹配,让"删文档"能真正删掉索引里它的全部 chunk,止住孤儿 chunk 再生。本任务改的是核心索引写入/删除,风险较高,务必按两步走。

== 第一步:只读确认 + 出方案(先做这步,做完停下等我批准,不要改代码)==

只读阅读 azure_search_store.py 及相关管理层代码,确认并原样贴出:
1. 全量重建(replace_all)写入路径里,document_id 从哪来——确认是不是取了 ChunkMetadata 里并不存在的 document_id,导致 None → 存成字符串 "None"。
2. 增量上传(worker,upload_document_chunks)写入路径里,document_id 怎么生成(是不是 "worker::物理路径")。
3. delete_document / delete_document_chunks 用什么 filter 删(是不是 document_id eq '...')。
4. 管理层(documents.json)的 document_id 是什么格式、在哪生成、删除时传给索引的是哪一个。
5. 确认 ChunkMetadata 到底有没有 document_id 字段。

然后提出一个"统一 document_id"方案:
- 让两条写入路径写入同一个、稳定可推导的 document_id;
- 这个值管理层也要知道,删除时能对得上;
- 说明"一个 source_file 对应多个 document_id(多路径/多版本入库)"时,删除怎么做到全删不漏。

把以上确认结果 + 方案发我,停在这里,不要实现。

== 第二步:我批准方案后再实现(先写明要求和护栏)==

- 两条写入路径的 document_id 用同一套规则,绝不再出现字符串 "None"(修掉 str(None) 那个坑)。
- 删除按统一规则匹配,能删掉同一文档的全部 chunk(含多路径/多版本),且不误删别的文档。
- 删除前必须先"干跑":打印/返回将被删的 chunk 数量和 document_id,确认无误才真删。
- 存量兼容:对已有的 "None" / "worker::路径" 旧 id,给一个一次性迁移或兜底匹配(例如删除时同时按 source_file 兜底),别让旧数据变成永远删不掉的孤儿。
- 只动 document_id 的写入与删除簿记;不改 embedding、切分、检索排序。

明确不做(红线):
- 不改 embedding、切分、检索排序逻辑;
- 不改 worker 调度/锁/续跑/幂等;
- 不碰其它文件。

必须保持不变:检索结果排序、embedding 结果、切分结果、worker 行为。

验收标准:
- 新入库(全量、增量各来一个)后,查索引里该文档的 document_id 是统一格式、没有 "None";
- 对一个测试文档调删除 → 索引里它的 chunk 全部消失(含多版本),其它文档不受影响;
- 干跑模式能先列出"将删除 N 条、哪些 document_id"。

验证方式:
- py_compile / import 静态检查 + 干跑 + 单文档小测;
- 针对真实索引的批量删除,由我(用户)在自己环境执行;你(Copilot)只做静态检查和干跑,不要自动对真实索引批量删除。

风险与回退:删除是高危操作,务必先干跑再真删;写入规则若需回退,保留按旧 id / source_file 的兼容匹配。