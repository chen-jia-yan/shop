## 删除文档、重新处理文档接口
【任务 K3b】知识库管理新增两个接口：删除文档（同时删除 Azure 和 Neo4j 中的数据）、重新处理文档（已成功的文档也可以重新入库）。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【本次允许修改的文件】
- src/tap_ai/contracts/library_kb.py（只追加）
- src/tap_ai/plugins/ingest/sdk_ingest.py
- src/tap_ai/application/library_kb.py（只追加方法，已有方法不改）
- src/tap_ai/persistence/library_kb_repo.py（只追加方法）
- src/tap_ai/api/library_kb.py（只追加路由，文件开头的接口说明同步追加）
- src/tap_ai/api/dto.py（只追加）
- docs/API-文档.md（只追加两个接口的说明）
- tests/ 下新建 test_library_kb_delete.py、test_library_kb_reprocess.py

【开工前确认（只读）】贴出原始输出
1. contracts/library_kb.py 中 IngestPort、IngestOutcome、KbDocumentRetryRequest 的原文
2. application/library_kb.py 中 retry 方法全文（作为新方法的参照）
3. library_kb_repo.py 中文档表、任务表的软删除写法（如果没有，写"没有"）；get_recent_jobs、mark_document_retry 的原文
4. 文档表 LibraryKbDocument 的 ORM 原文：status 有哪些取值、document_key 的含义
5. sdk_ingest.py 中 SdkIngestAdapter 的 ingest_file 全文
6. SDK 中 AzureAISearchSink.delete、Neo4jGraphSink.delete 的原文（参数是不是 document_id，和后端 document_key 是不是同一个值，贴依据）

【要做的 6 件事】

1. 入库插座增加删除方法
   - IngestPort 追加：def delete_document(self, *, saas_id: str, document_key: str) -> IngestOutcome: ...
   - SdkIngestAdapter 实现 delete_document：
     · 按 saas_id 找到索引名；找不到 → error_code="no_index"
     · 索引在禁止写入名单中 → error_code="forbidden_index"，不调用任何 sink
     · 依次调用 Azure sink 和 Neo4j sink（如果有）的 delete(document_key)
     · 任何一个 sink 失败 → 返回失败，error_code="delete_failed"，error_message 写明是哪个 sink
   - 测试中已有的假 IngestPort 如果因为新增方法而报类型错误，只给假实现追加这个方法

2. 删除文档接口：POST /tap/ai/library/kb/documents/delete
   - 请求：KbDocumentDeleteRequest（saas_id、workspace_id、project_id、user_id 照 KbDocumentRetryRequest 的写法；document_ids: list[str]，1 到 50 个）
   - 返回：KbDeleteData（deleted: list[str]、ignored: list[KbRetryIgnoredData]）
   - 处理每个文档的顺序：
     a. 文档不存在、或不属于这个 saas_id → ignored，原因"文档不存在"
     b. 状态是 processing → ignored，原因"文档正在处理，请稍后再删除"
     c. 先删外部数据：用 asyncio.to_thread 调用 delete_document；失败 → ignored，原因写失败信息，数据库不改
     d. 外部数据删成功以后，在一个事务里：文档和它的所有任务软删除（deleted=1、delete_time=当前时间）
     e. 最后删除存储中的文件；删除失败只打印 warning，不影响结果
   - 已经软删除的文档再删一次 → ignored，原因"文档不存在"

3. 重新处理文档接口：POST /tap/ai/library/kb/documents/reprocess
   - 请求：KbDocumentReprocessRequest（字段同删除接口）
   - 返回：KbRetryData（和 retry 接口一样）
   - 规则：状态为 succeeded 或 failed 的文档可以重新处理；pending、processing → ignored，原因"文档已在处理队列中"
   - 处理方式照抄 retry 方法：找到最近一次任务的存储文件，新增一条 pending 任务，文档状态改为 pending
   - 新写一个方法 reprocess，不要修改 retry；两个方法共用的部分可以抽成私有方法，但 retry 的行为必须保持不变

4. 数据库操作
   - library_kb_repo.py 追加需要的方法（软删除文档、软删除文档的所有任务、文档改回 pending）
   - 每个更新语句都要带条件（例如 status 不是 processing、deleted=0），用 rowcount 判断是否成功，写法照抄 claim_job

5. 接口规范
   - 按 docs/API-文档.md 的规范：只用 POST；业务错误返回 HTTP 200 + {code, message}
   - docs/API-文档.md 追加两个接口的请求示例和返回示例

6. 测试（假的 IngestPort 和假的仓储，不连数据库）
   a. 删除：正常删除；文档不存在；正在处理；外部删除失败时数据库不变；禁止写入的索引不调用 sink；重复删除
   b. 重新处理：succeeded 能重新处理；failed 能重新处理；pending / processing 被忽略；没有存储文件时被忽略
   c. retry 原有的测试全部通过（证明 retry 行为没变）

【完成报告】按【通用规则】第五条；另外列出新增的每个测试函数名



## 要特别注意：删除接口会真的删掉 Azure 里的数据。你本地 hk 连的是同事共用的索引，所以：

**本地不要对 hk 的文档调用删除接口。**只用测试验收。

验收方法：

1. 新增的测试：

```powershell
uv run pytest -q tests/unit/test_library_kb_delete.py tests/unit/test_library_kb_reprocess.py -v 2>&1 | Select-Object -Last 25

```

每个用例都是 PASSED。

2. 原来的重试功能没受影响：

```powershell
uv run pytest -q tests/unit/test_library_kb_service.py tests/api/test_library_kb_api.py 2>&1 | Select-Object -Last 10

```

没有失败。

3. 删除时会检查禁止写入的名单：

```powershell
git grep -n "forbidden" -- src/tap_ai/plugins/ingest/sdk_ingest.py

```

在 ‎`delete_document` 函数里，能看到对禁止写入名单的检查。

**4. 接口文档里能看到两个新接口：**启动后端，打开 ‎`/docs`，能看到 ‎`documents/delete` 和 ‎`documents/reprocess`。只看，不要点执行。

通过以后提交：

```powershell
git add -A
git commit -m "feat(kb): 新增删除文档与重新处理文档接口"

```

