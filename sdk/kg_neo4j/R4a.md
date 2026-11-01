# 后端图谱接口调研文档
## 1. 后端现有的图谱接口
### 1.1 指定命令原始输出
命令：
```bash
git grep -n -i -E "neo4j|graph|kg_" -- src/tap_ai/api src/tap_ai/application
```
原始输出：
```
src/tap_ai/api/chat.py:8:图（graph）只负责模型选择与上下文组装；流式模型调用由本模块直接消费网关实现，
src/tap_ai/api/chat.py:21:from tap_ai.core.graph import RESULT_CANCELLED, RESULT_ERROR
src/tap_ai/application/chat.py:35:from tap_ai.core.graph import (
src/tap_ai/application/chat.py:122:        graph,
src/tap_ai/application/chat.py:148:        self._graph = graph
src/tap_ai/application/chat.py:728:        if self._graph is None:
src/tap_ai/application/chat.py:1052:                self._graph,
```

### 1.2 图谱相关接口结论
结论：**没有图谱接口。**
依据1：`git grep` 在 `src/tap_ai/api` / `src/tap_ai/application` 范围内只命中了聊天里的 `graph` 编排，不是知识图谱 CRUD / 查询接口。

依据2：后端现有知识库API全文如下，只有统计、列表、详情、上传、重试、同步，没有任何 Neo4j / graph 专用路由。

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\library_kb.py:1-8`
```python
"""Library KB 管理 API 路由。

- POST /tap/ai/library/kb/stats            - 查询知识库统计
- POST /tap/ai/library/kb/documents/list   - 分页列出知识库文档
- GET  /tap/ai/library/kb/documents/{document_id} - 查询文档详情
- POST /tap/ai/library/kb/documents/upload - 上传文档并入队
- POST /tap/ai/library/kb/documents/retry  - 重试失败文档
- POST /tap/ai/library/kb/documents/sync   - 从索引同步已有文档
"""
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\library_kb.py:54-138`
```python
@router.post("/stats", response_model=KbStatsData)
async def library_kb_stats(body: KbStatsRequest, request: Request) -> KbStatsData:
    """查询知识库统计。"""
    return KbStatsData.model_validate(await _service(request).stats(body))

@router.post("/documents/list", response_model=KbDocumentListData)
async def library_kb_documents_list(
    body: KbDocumentListRequest, request: Request
) -> KbDocumentListData:
    """分页列出知识库文档。"""
    result = await _service(request).list_documents(body)
    return KbDocumentListData(
        items=[KbDocumentData.model_validate(item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )

@router.get("/documents/{document_id:path}", response_model=KbDocumentDetailData)
async def library_kb_document_detail(
    document_id: str, request: Request
) -> KbDocumentDetailData:
    """查询单个知识库文档详情。"""
    return KbDocumentDetailData.model_validate(
        await _service(request).get_document(document_id)
    )

@router.post("/documents/upload", response_model=KbUploadData)
async def library_kb_documents_upload(
    request: Request,
    saas_id: Annotated[str | None, Form()] = None,
    workspace_id: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
    user_id: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> KbUploadData:
    """接收 multipart 文件并交给知识库服务入队。"""
    max_files = request.app.state.settings.library_kb_max_files_per_upload
    upload_inputs = files or []
    if not upload_inputs:
        raise BusinessError(code="CCB001", message="未选择文件")
    if len(upload_inputs) > max_files:
        raise BusinessError(code="CCB001", message="上传文件数量超过上限")
    tenant = _TenantForm(
        saas_id=saas_id,
        workspace_id=workspace_id,
        project_id=project_id,
        user_id=user_id,
    )
    upload_files: list[tuple[str, str | None, Callable[[int], Awaitable[bytes]]]] = [
        (upload.filename or "", upload.content_type, upload.read)
        for upload in upload_inputs
    ]
    result = await _service(request).upload(tenant=tenant, files=upload_files)
    return KbUploadData(
        batch_id=result["batch_id"],
        queued=result["queued"],
        skipped=result["skipped"],
        rejected=result["rejected"],
        items=[KbUploadItemData.model_validate(item) for item in result["items"]],
    )

@router.post("/documents/retry", response_model=KbRetryData)
async def library_kb_documents_retry(
    body: KbDocumentRetryRequest, request: Request
) -> KbRetryData:
    """把失败文档重新放回待处理队列。"""
    result = await _service(request).retry(body)
    return KbRetryData(
        retried=result["retried"],
        ignored=[KbRetryIgnoredData.model_validate(item) for item in result["ignored"]],
    )

@router.post("/documents/sync", response_model=KbSyncData)
async def library_kb_documents_sync(
    body: KbDocumentSyncRequest, request: Request
) -> KbSyncData:
    """从索引同步已有文档。"""
    result = await _service(request).sync(body)
    return KbSyncData.model_validate(result)
```

### 1.3 和图谱有关的接口清单
| 请求方法 | 路径 | 处理函数所在 文件:行号 | 返回什么数据 |
| ---- | ---- | ---- | ---- |
| 无 | 无 | 无 | 没有图谱接口 |

## 2. 删除文件、重新上传同一个文件时，Neo4j里的数据会怎样
### 2.1 后端“删除文件”处理函数追踪
我在后端范围内没有找到知识库“删除文件”接口或服务方法。

搜索命令：
```bash
rg -n "delete|deleted|soft delete|mark_deleted|remove|purge" C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai -g "*.py"
```
与知识库相关的命中里，只看到：

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:250-250`
```python
await self._delete_storage_file(path=path)
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:319-319`
```python
await self._delete_storage_file(path=stored["path"])
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:342-342`
```python
await self._delete_storage_file(path=stored["path"])
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:372-372`
```python
await self._delete_storage_file(path=stored["path"])
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:646-649`
```python
async def _delete_storage_file(self, *, path: str) -> None:
    try:
        await self._storage.delete(path=path)
```
这些都是上传失败/冲突时删除存储文件，不是“删除已入库知识库文件”。

所以 2.a 这部分对“后端删除文件一路追到 Azure 删除和 Neo4j 删除”为：未找到。

## 2.2 SDK 中 Neo4jGraphSink 是否有按 document_id 删除的方法
文件: `C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\protocols.py:70-75`
```python
class DocumentSink(Protocol):
    def upsert(self, document: ProcessedDocument) -> SinkResult:
        ...

    def delete(self, document_id: str) -> None:
        ...
```

文件: `C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:280-284`
```python
def delete(self, document_id: str) -> None:
    self._run(_RETRACT_RELATIONS, document_id=document_id)
    self._run(_RETRACT_ENTITIES, document_id=document_id)
    self._run(_DELETE_CHUNKS, document_id=document_id)
    self._run(_DELETE_DOCUMENT, document_id=document_id)
```

相关 Cypher 原文：
文件: `C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:68-84`
```python
_RETRACT_RELATIONS = (
    "OPTIONAL MATCH (c:Chunk {scope: $scope, document_id: $document_id}) "
    "WITH collect(c.chunk_id) AS old "
    "MATCH (:Entity {scope: $scope})-[e]->(:Entity {scope: $scope}) "
    "WHERE $document_id IN e.doc_ids "
    "SET e.doc_ids = [x IN e.doc_ids WHERE x <> $document_id], "
    "e.chunk_ids = [x IN coalesce(e.chunk_ids, []) WHERE NOT x IN old] "
    "SET e.weight = size(e.doc_ids) "
    "WITH e WHERE e.weight = 0 "
    "DELETE e"
)
_RETRACT_ENTITIES = (
    "MATCH (e:Entity {scope: $scope}) WHERE $document_id IN e.doc_ids "
    "SET e.doc_ids = [x IN e.doc_ids WHERE x <> $document_id]"
)
_DELETE_CHUNKS = "MATCH (c:Chunk {scope: $scope, document_id: $document_id}) DETACH DELETE c"
_DELETE_DOCUMENT = "MATCH (d:Document {scope: $scope, document_id: $document_id}) DETACH DELETE d"
```

## 2.3 重新上传同一个文件时的 Neo4j 行为
文件: `C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:231-257`
```python
def upsert(self, document: ProcessedDocument) -> SinkResult:
    doc_id = document.document_id
    if self.is_excluded(document):
        self.delete(doc_id)
        return SinkResult(indexed_count=0)
    self._run(_RETRACT_RELATIONS, document_id=doc_id)
    self._run(_RETRACT_ENTITIES, document_id=doc_id)
    self._run(_DELETE_CHUNKS, document_id=doc_id)
    self._run(
        _WRITE_DOCUMENT,
        document_id=doc_id,
        source_file=document.filename,
        doc_type=document.content_type,
        chunk_ids=[c.metadata.chunk_id for c in document.chunks],
    )
    relations = self._collect_relations(document)
    rows = self._mention_rows(document, relations)
    if rows:
        self._run(
            _WRITE_MENTIONS,
            rows=rows,
            document_id=doc_id,
            source_file=document.filename,
        )
    self._write_relations(doc_id, relations)
    self._embed_entities({row["id"] for row in rows})
    return SinkResult(indexed_count=len(rows))
```

后端重新上传同名文件时，服务侧会把已有 document 重新入队，而不是新建第二个 document 记录：

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:330-351`
```python
if decision.existing_document_id is not None:
    expected = by_name[decision.name_key]
    updated = await document_repo.requeue_document_for_upload(
        document_id=decision.existing_document_id,
        expected_status=expected.status,
        file_name=decision.file_name,
        content_sha256=stored["content_sha256"],
        size_bytes=stored["size_bytes"],
        now=self._clock(),
        commit=False,
    )
    if not updated:
        await self._delete_storage_file(path=stored["path"])
        results.append(
            KbUploadItemResult(
                file_name=decision.file_name,
                result="rejected",
                reason="该文件正在被其他请求上传",
            )
        )
        continue
    document_id = decision.existing_document_id
```

后端把这个 document 的 `document_key` 继续传给 SDK：

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:158-168`
```python
outcome = await self._run_ingest_with_timeout(
    saas_id=document.saas_id,
    document_key=document.document_key,
    file_name=job.file_name,
    content=content,
    timeout_s=self._job_timeout_s,
    stop_event=stop_event,
)
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:106-110`
```python
source = SourceDocument.from_bytes(
    content,
    filename=file_name,
    idempotency_key=document_key,
)
```
## 2.4 结论
结论：部分会。

依据：
1. 如果调用到 SDK 的 `Neo4jGraphSink.delete(document_id)` 或 `upsert(document)` 覆盖同一个 `document_id`，则：
   - Chunk 会被删：`_DELETE_CHUNKS = "MATCH (c:Chunk {scope: $scope, document_id: $document_id}) DETACH DELETE c"`
   - Document 会被删：`_DELETE_DOCUMENT = "MATCH (d:Document {scope: $scope, document_id: $document_id}) DETACH DELETE d"`
   - MENTIONED_IN 会随着 DETACH DELETE c 一起删除
   - 实体之间的业务关系会先执行 `_RETRACT_RELATIONS`，只去掉这个文档贡献的 doc_ids/chunk_ids；当 e.weight = 0 时才 DELETE e
2. 后端当前未找到“删除知识库文件”接口/服务链路，所以不能证明用户在后端点“删除文件”时一定会调到 Azure 删除和 Neo4j 删除。
3. 重新上传同名文件这条链路，后端会复用原 document 记录，并把同一个 document_key 传给 SDK；而 `Neo4jGraphSink.upsert()` 会先撤销旧关系、删除 Chunk，再写新内容。所以在“重新上传同一个文件并成功重新入库”的前提下，Neo4j 中该文件对应的 Chunk 与 MENTIONED_IN 会被重建，实体关系会按是否仍有其他文档支撑而保留或删除。

# 3. 后端入库时，是怎样调用 SDK 的
## 3.1 从 KbIngestWorker 到 SDK 的调用链
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:147-168`
```python
async def _process_job(self, *, job) -> None:
    if self._ingest is None or job.storage_path is None:
        return
    document = await self._load_document(document_id=job.document_id)
    if document is None:
        return
    expected_attempts = int(job.attempts)
    heartbeat_task = asyncio.create_task(
        self._heartbeat_loop(job_id=job.id, expected_attempts=expected_attempts)
    )
    try:
        content = await self._storage.read(path=job.storage_path)
        stop_event = asyncio.Event()
        try:
            outcome = await self._run_ingest_with_timeout(
                saas_id=document.saas_id,
                document_key=document.document_key,
                file_name=job.file_name,
                content=content,
                timeout_s=self._job_timeout_s,
                stop_event=stop_event,
            )
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:343-380`
```python
async def _run_ingest_with_timeout(
    self,
    *,
    saas_id: str,
    document_key: str,
    file_name: str,
    content: bytes,
    timeout_s: float,
    stop_event: asyncio.Event,
):
    loop = asyncio.get_running_loop()
    result_fut = loop.create_future()

    def _run() -> None:
        try:
            outcome = self._ingest.ingest_file(
                saas_id=saas_id,
                document_key=document_key,
                file_name=file_name,
                content=content,
                stop_event=stop_event,
            )
        except TypeError:
            outcome = self._ingest.ingest_file(
                saas_id=saas_id,
                document_key=document_key,
                file_name=file_name,
                content=content,
            )
        except Exception as exc:  # noqa: BLE001 - 线程内异常要透传回主协程统一处理
            loop.call_soon_threadsafe(result_fut.set_exception, exc)
            return
        if not result_fut.done():
            loop.call_soon_threadsafe(result_fut.set_result, outcome)
    worker_task = asyncio.create_task(asyncio.to_thread(_run))
    try:
        return await asyncio.wait_for(result_fut, timeout=timeout_s)
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\library_kb.py:23-28`
```python
class IngestPort(Protocol):
    """入库插座，由后台处理通过 asyncio.to_thread 调用。"""
    def ingest_file(
        self, *, saas_id: str, document_key: str, file_name: str, content: bytes
    ) -> IngestOutcome: ...
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:61-64`
```python
def ingest_file(
    self, *, saas_id: str, document_key: str, file_name: str, content: bytes
) -> IngestOutcome:
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:116-123`
```python
client = TapIngestClient(
    parser_registry=ParserRegistry.default(),
    chunker=DefaultChunker(),
    sinks=sinks,
    work_dir=temp_dir,
)
report = client.ingest([source])
```

文件: `C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\client.py:190-201`
```python
def _ingest_one(self, source: SourceDocument) -> FileIngestResult:
    started_at = time.perf_counter()
    try:
        document = self.process(source)
        indexed_count = 0
        for sink in self._sinks:
            try:
                result = sink.upsert(document)
                indexed_count = max(indexed_count, result.indexed_count)
            except Exception as exc:
                logger.exception("sink upsert failed filename=%s", source.filename)
                raise SinkError(f"Sink failed for {source.filename}: {exc}") from exc
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:275-301`
```python
def _sinks_factory(index_name: str) -> Sequence[object]:
    from tap_ingest_sdk.sinks._azure import (  # type: ignore[import-untyped]
        AzureAISearchSink,
    )
    from tap_ingest_sdk.sinks._neo4j import (  # type: ignore[import-untyped]
        Neo4jGraphSink,
    )

    sinks: list[object] = [
        AzureAISearchSink(
            endpoint=kb.azure_search_endpoint,
            index_name=index_name,
            credential=key,
        )
    ]
```

## 3.2 线程模型结论
结论：调用SDK时不是主线程直接跑，而是通过 `asyncio.to_thread` 放到单独线程。

最直接依据就是：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:378-380`
```python
worker_task = asyncio.create_task(asyncio.to_thread(_run))
try:
    return await asyncio.wait_for(result_fut, timeout=timeout_s)
```

## 4. SDK里大模型抽取器和规则抽取器的接口
### 4.1 LLMProvider 完整定义原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\protocols.py:62-66`
```python
@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, messages: Sequence[dict[str, str]]) -> str:
        """Send chat messages (`role`/`content`) and return the reply text."""
        ...
```

结论：
- 方法名：`complete`
- 参数：`messages: Sequence[dict[str, str]]`
- 返回值：`str`
- 同步 / 异步：同步（定义里没有 `async`）

### 4.2 LLMRelationExtractor 调用这个接口的原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\kg_llm_extract.py:105-113`
```python
def __call__(self, document: ProcessedDocument) -> list[RelationSpec]:
    if not document.chunks:
        return []
    try:
        reply = self._provider.complete(build_messages(document, self._max_chars))
    except Exception as exc:
        logger.warning("[KG][llm] 文档 %s 抽取失败，已跳过: %s", document.filename, exc)
        return []
    return self._to_specs(document, parse_response(reply))
```

### 4.3 是否有“规则抽取器 + 大模型抽取器”组合器
有。
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\kg_extract.py:85-94`
```python
def combine_extractors(*extractors: Any) -> Any:
    """依次运行多个 `relation_extractor`，合并结果。"""
    def combined(document: ProcessedDocument) -> list[Any]:
        out: list[Any] = []
        for extractor in extractors:
            out.extend(extractor(document))
        return out
    return combined
```

SDK命令行里使用它的原文：
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\cli\main.py:186-193`
```python
relation_extractor: Any | None = DefaultRelationExtractor(cooccurrence_roles=kg_cooccurrence_roles)
if no_kg_relations:
    relation_extractor = None
elif sink in ("neo4j", "azure-neo4j") and (kg_extractor == "llm" or (kg_extractor is None and llm_enabled())):
    # 仅在开关打开时才创建 LLM 客户端；缺配置会抛 ConfigurationError。
    relation_extractor = combine_extractors(
        relation_extractor, LLMRelationExtractor(OpenAILLMProvider.from_env())
    )
```

## 5. 实体向量
### 5.1 Neo4jGraphSink 接收的向量模型参数名与接口要求
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:186-199`
```python
def __init__(
    self,
    uri: str,
    user: str,
    password: str,
    scope: str,
    database: str | None = None,
    relation_extractor: RelationExtractor | None = None,
    ensure_schema: bool = True,
    driver: Any | None = None,
    allowed_relations: Mapping[str, Iterable[tuple[str, str]]] | None = None,
    exclude: Iterable[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> None:
```

所以参数名叫：`embedding_provider`

它要求的接口定义：
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\protocols.py:52-59`
```python
@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int:
        ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        ...
```

Neo4jGraphSink 对它的直接使用原文：
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:217-221`
```python
if ensure_schema:
    for stmt in _SCHEMA:
        self._run(stmt)
    if self._embedder is not None:
        self._run(_VECTOR_INDEX, dimensions=self._embedder.dimension)
```

文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:270-276`
```python
for i in range(0, len(todo), _EMBED_BATCH):
    batch = todo[i : i + _EMBED_BATCH]
    vectors = self._embedder.embed([t["text"] for t in batch])
    rows = [
        {"id": t["id"], "hash": t["hash"], "vector": list(v)} for t, v in zip(batch, vectors)
    ]
    self._run(_WRITE_EMBEDDINGS, rows=rows)
```

### 5.2 后端有没有现成的向量生成功能
命令：`git grep -n -i "embedding" -- src/tap_ai`

原始输出：
```
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\knowledge.py:1:"""业务知识库端口契约（检索 / 图谱 / embedding）。
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\knowledge.py:67:class EmbeddingPort(Protocol):
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\knowledge.py:121:    """知识库后端（检索 / embedding）不可用或返回异常。
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\__init__.py:1:"""知识库插件的检索 / 图谱 / embedding 后端实现
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:1:"""经 LiteLLM 网关调用 embedding（与
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:12:class LiteLLMEmbedding:
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:31:        resp = await litellm.a
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:39:        vectors = [list(item["
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:41:        raise KnowledgeBackend
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:43:        raise KnowledgeBackend
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:47:        f"embedding 维
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:46:        "SEARCH e IN (VECTOR INDEX entity_em
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:167:        self._has_vector = stat
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:171:        logger.warning("ent
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:11:from tap_ai.plugins.extensions.knowledge.backends.lite
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:12:from tap_ai.plugins.extensions.knowledge.backends.litellm_embedding import LiteLLMEmbedding
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:47:        embedding = LiteLLMEmbedding(
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:48:            model=kb.embedding_model,
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:51:            dimensions=kb.embedding_dimensions,
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:73:        embedding=embedding,
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:1:"""知识库检索服务: 改写 → embedding || 实体匹配 → Azure 混
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:11:        EmbeddingPort,
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:47:        self._embedding = embedding
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:53:        return (await self._embedding.embed([rw
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:36:    # LiteLLM 上的 embedding 模型别名; 必须与摄取时一致
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:37:    embedding_model: str = "text-embedding-3-large"
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:38:    embedding_dimensions: int = 3072
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:46:    # 实体向量匹配（需要 SDK 写入实体 embedding）。
C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:6:并按 `GET /model/info` 的 `mode` 仅保留 `chat` 类型（排除 embedding
```

结论：有现成的向量生成功能，但它在知识检索插件里，不在 Library KB 入库 worker 里直接生成实体向量。

最直接代码：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\litellm_embedding.py:12-39`
```python
class LiteLLMEmbedding:
    def __init__(self, *, model: str, dimensions: int, api_base: str, api_key: str) -> None:
        self._model = model
        self._dimensions = dimensions
        self._api_base = api_base
        self._api_key = api_key

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            resp = await litellm.aembedding(
                model=self._model,
                input=list(texts),
                api_base=self._api_base,
                api_key=self._api_key,
                dimensions=self._dimensions,
            )
            vectors = [list(item["embedding"]) for item in resp["data"]]
```

## 6. 入库任务会不会被多个后端实例重复处理
### 6.1 KbIngestWorker 取任务完整代码原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:63-84`
```python
async def run_once(self) -> int:
    """执行一轮: 恢复中断任务 → 抢任务 → 处理。"""
    await self._recover_stale_jobs()
    now = self._clock()
    async with self._session_factory() as session:
        job_repo = self._job_repo_factory(session)
        pending_job_ids = await job_repo.list_pending_job_ids(
            limit=self._settings.library_kb_worker_concurrency
        )
    loaded_jobs: list[Any] = []
    for job_id in pending_job_ids:
        job = await self._claim_and_load_job(job_id=job_id, now=now)
        if job is not None:
            loaded_jobs.append(job)
    if not loaded_jobs:
        return 0
    tasks = [
        asyncio.create_task(self._process_job_with_semaphore(job=job))
    for job in loaded_jobs
]
results = await asyncio.gather(*tasks)
return sum(1 for item in results if item)
```
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:123-145`

```python
async def _claim_and_load_job(self, *, job_id: str, now: int):
    async with self._session_factory() as session:
        job_repo = self._job_repo_factory(session)
        document_repo = self._document_repo_factory(session)
        claimed = await job_repo.claim_job(job_id=job_id, now=now, commit=False)
        if not claimed:
            await session.rollback()
            return None
        job = await job_repo.get_job(job_id=job_id)
        if job is None:
            await session.rollback()
            return None
        document_updated = await document_repo.mark_document_processing(
            document_id=job.document_id,
            now=now,
            commit=False,
        )
        if not document_updated:
            await session.rollback()
            logger.info("任务已被其他实例接手")
            return None
        await session.commit()
        return job
```
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\library_kb_repo.py:434-469`

### 片段2 library_kb_repo.py
```python
async def list_pending_job_ids(self, limit: int) -> list[str]:
    """列出待领取任务 ID, 按 create_time 升序。"""
    stmt = (
        select(LibraryKbJob.id)
        .where(
            LibraryKbJob.status == "pending",
            LibraryKbJob.deleted.is_(False),
        )
        .order_by(LibraryKbJob.create_time, LibraryKbJob.id)
        .limit(limit)
    )
    rows = (await self._session.execute(stmt)).scalars().all()
    return list(rows)
```

```python
async def claim_job(self, job_id: str, now: int, *, commit: bool = True) -> bool:
    """搶佔一條 pending 任務並轉為 processing。"""
    stmt = (
        update(LibraryKbJob)
        .where(
            LibraryKbJob.id == job_id,
            LibraryKbJob.status == "pending",
            LibraryKbJob.deleted.is_(False),
        )
        .values(
            status="processing",
            attempts=LibraryKbJob.attempts + 1,
            started_time=now,
            heartbeat_time=now,
            update_time=now,
        )
    )
    result = await self._session.execute(stmt)
    cursor = cast(CursorResult[Any], result)
    if commit:
        await self._session.commit()
    return cursor.rowcount > 0
```
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\library_kb_repo.py:246-263`

```python
async def mark_document_processing(
    self, document_id: str, now: int, *, commit: bool = True
) -> bool:
    """將文檔標記為 processing。"""
    stmt = (
        update(LibraryKbDocument)
        .where(
            LibraryKbDocument.id == document_id,
            LibraryKbDocument.status.in_(["pending", "processing"]),
            LibraryKbDocument.deleted.is_(False),
        )
        .values(status="processing", update_time=now)
    )
    result = await self._session.execute(stmt)
    cursor = cast(CursorResult[Any], result)
    if commit:
        await self._session.commit()
    return cursor.rowcount > 0
```
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\library_kb_repo.py:471-494`

```python
async def heartbeat(
    self,
    job_id: str,
    now: int,
    expected_attempts: int,
    *,
    commit: bool = True,
) -> bool:
    """更新 processing 任務心跳。"""
    stmt = (
        update(LibraryKbJob)
        .where(
            LibraryKbJob.id == job_id,
            LibraryKbJob.status == "processing",
            LibraryKbJob.attempts == expected_attempts,
            LibraryKbJob.deleted.is_(False),
        )
        .values(heartbeat_time=now, update_time=now)
    )
    result = await self._session.execute(stmt)
    cursor = cast(CursorResult[Any], result)
    if commit:
        await self._session.commit()
    return cursor.rowcount > 0
```
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\library_kb_repo.py:529-564`

```python
async def mark_job_retry(
    self,
    job_id: str,
    error_code: str | None,
    error_message: str | None,
    now: int,
    expected_attempts: int,
    stale_before: int | None = None,
    *,
    commit: bool = True,
) -> bool:
    """將任務重置回 pending。"""
    filters: list[Any] = [
        LibraryKbJob.id == job_id,
        LibraryKbJob.status == "processing",
        LibraryKbJob.attempts == expected_attempts,
        LibraryKbJob.deleted.is_(False),
    ]
```

## 6.2 结论
结论：有防重复机制。

依据：
1. 没有看到 `SELECT ... FOR UPDATE`。
2. 没有看到 Redis 分布式锁用于 KB 入库抢任务；虽然仓里有 `utils\redis.py`，但本条链路未见调用。
3. 看到了带条件的 `UPDATE ... WHERE status='pending'` 抢占机制：
    - `claim_job()` 用 `update(LibraryKbJob).where(LibraryKbJob.id == job_id, LibraryKbJob.status == "pending", ...)`
    - 更新成功必须 `rowcount == 1` 才算抢到任务
4. 后续还有 `attempts/heartbeat` 的并发保护：
    - `heartbeat()` / `mark_job_succeeded()` / `mark_job_retry()` / `mark_job_failed()` 都要求 `LibraryKbJob.attempts == expected_attempts`
5. worker 侧明确把抢占失败视为“被其他实例接手”：

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb_worker.py:140-143`
```python
if not document_updated:
    await session.rollback()
    logger.info("任务已被其他实例接手")
    return None
```

所以按当前已读代码，入库任务不是裸跑，存在基于数据库条件更新和心跳/attempts 的防重复领取机制。

---
## 核对表
| 编号 | 状态（完成/未找到/未做） | 证据所在的文件:行号 |
| ---- | ---- | ---- |
| 1 | 完成 | `src\tap_ai\api\library_kb.py:1-8,54-138` ; `git grep` 原始输出见本文1.1 |
| 2 | 完成 | `src\tap_ingest_sdk\protocols.py:70-75` ; `src\tap_ingest_sdk\sinks\_neo4j.py:68-84,231-257,280-284` ; 后端未找到删除链路的搜索证据见本文2.1 |
| 3 | 完成 | `src\tap_ai\application\library_kb_worker.py:147-168,343-380` ; `src\tap_ai\plugins\ingest\sdk_ingest.py:61-64,106-123,275-301` ; `src\tap_ingest_sdk\client.py:190-201` |
| 4 | 完成 | `src\tap_ingest_sdk\protocols.py:62-66` ; `src\tap_ingest_sdk\sinks\_kg_llm_extract.py:105-113` ; `src\tap_ingest_sdk\sinks\_kg_extract.py:85-94` ; `src\tap_ingest_sdk\cli\main.py:186-193` |
| 5 | 完成 | `src\tap_ingest_sdk\sinks\_neo4j.py:186-199,217-221,270-276` ; `src\tap_ingest_sdk\protocols.py:52-59` ; `git grep -n -i "embedding" -- src/tap_ai` 原始输出见本文5.2 |
| 6 | 完成 | `src\tap_ai\application\library_kb_worker.py:63-84,123-145` ; `src\tap_ai\persistence\library_kb_repo.py:246-263,434-469,471-494,529-564` |


    
