继续排查切片预览"预览源文件不可用"的问题。已确认：/files/list 的 file_id 来自 Azure 索引 document_id 分面；/chunk-previews/baseline 先按租户和 document_key=file_id 查 MySQL 的 library_kb_document，查不到时返回 CCB001。用户已确认，同一个库、同一个租户下，这个 file_id 在 MySQL 里没有记录。本轮只读，不改代码、不写数据。

请完成：
1. 说明 library_kb_document.document_key 是怎么生成的（上传入库链路，给出文件名和行号），Azure 索引的 document_id 又是怎么生成的；在正常上传流程下，两者是否一定相等？有没有前缀、哈希、大小写、路径方面的差异？
2. 列出所有会往目标索引写入切片、但不会写 library_kb_document 的路径（旧流程、JP 旧索引、脚本、外部系统、同步逻辑 library_kb.py:1030 附近）。
3. 写一个只读诊断脚本（先不执行，给我审阅）：对指定租户，用 facet 拿到索引里全部 document_id，再批量查 MySQL，输出四类计数和每类最多 10 个示例 ID：
   a. MySQL 有记录且元数据完整（能预览）
   b. MySQL 有记录但缺 storage_path、hash 或 filename，或者状态不是 indexed
   c. MySQL 按 document_key 查不到，但按 filename 能查到（疑似 ID 映射不一致，同时打印两边的 ID）
   d. MySQL 完全没有记录
   脚本不输出切片正文和密钥。
4. 评估两个改动方案，给出 diff 草案（先不要应用）和影响范围：
   A. /files/list 每一项增加 previewable: bool 和 preview_unavailable_reason，通过批量查询 MySQL 得出，不能按单个文件逐条查（避免 N+1）
   B. library_chunk_preview_common.py:134 附近的四种失败原因拆开，分别给出不同的 message，或者在 data 里返回原因码
   另外说明：baseline 保存的源文件哈希、路径在候选预览和保存草稿时有没有用到？如果把源文件校验从 baseline 挪到候选预览，会不会破坏"草稿就是用户看到的那份预览"这个保证？
5. 为方案 A、B 补充回归测试的设计：用假的数据源和假的 MySQL，覆盖上面四类文件。


SELECT id, document_key, filename, status, deleted, storage_path IS NOT NULL AS has_path
FROM library_kb_document
WHERE saas_id = '<租户>' AND filename LIKE '%<文件列表里的 source_file>%';
