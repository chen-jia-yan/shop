目标：定位 /tap/ai/library/chunk-previews/baseline 返回"预览源文件不可用"的具体原因。这次可以加临时调试日志，但不要提交，也不要改业务逻辑，排查完删除。

已知情况：
- /files/list 只按租户列出索引里的文件；baseline 在 library_chunk_preview_common.py:134 附近按 租户 + workspace/project/user + document_key 查 library_kb_document，并检查状态、删除标记、文件名、路径、哈希、大小。这几种失败共用同一条提示。
- MySQL 里 document_key=doc::e26586aaea2b4d36 这条记录：status=indexed，deleted=0，哈希、路径齐全，size 约 3MB。用这个 key 调 baseline 仍然提示"不可用"。
- 用 keyword="产品需求文档_2026Q1_003" 调 /files/list 返回 0 条。

请做以下几件事：
1. 在 library_chunk_preview_common.py 的源文件校验处，每个失败分支前各加一行 logger.warning，输出：失败原因（not_found_in_scope / status / deleted / missing_name / missing_path / missing_hash / size）、file_id、请求上下文里的 saas_id、workspace、project、user。另外再查一次只按 saas_id + document_key、不带身份过滤的记录，输出这条记录的 workspace、project、user。不要输出路径、哈希、正文和密钥。
2. 在 /files/list 的 keyword 处理处加日志，输出 keyword 最终被转换成的 Azure filter 或 search 参数，说明 keyword 匹配的是哪个字段、用的是什么匹配方式。
3. 在 baseline 通过 MySQL 校验、开始读取 Azure 切片的位置加日志，输出 chunk_source 返回的 total。
4. 告诉我怎么重启本地服务（9006 端口），以及我需要调用哪 3 个请求：
   a. /files/list 不带 keyword，取第一页的第一个文件，记下它的 file_id 和 source_file
   b. 用 a 拿到的 file_id 调 baseline
   c. 用 doc::e26586aaea2b4d36 调 baseline
5. 我把日志贴给你之后，根据日志给出根因和最小修复方案（只给方案，先不要应用）。如果根因是身份范围不一致，请分析：文件列表是否也应该按同样的身份范围过滤，还是应该保持租户级可见、预览时给出明确提示？分别说明两种做法对现有前端的影响。


SELECT saas_id, workspace_id, project_id, user_id
FROM library_kb_document
WHERE document_key = 'doc::e26586aaea2b4d36';
