# 1. saas_id 是从哪里来的
## 1.1 接收聊天请求的接口原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\chat.py:41-52`
```python
class SendMessageRequest(BaseModel):
    """发送消息请求体。"""

    message_content: str = Field(..., min_length=1)
    selected_model: str | None = None
    provider: str | None = None
    saas_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    file_ids: list[str] | None = None
    title: str | None = None
```

已确认事实：聊天接口把 `saas_id` 定义在请求体 `SendMessageRequest` 里，不是请求头字段，也没看到这里从登录令牌里取值。

## 1.2 路由把 saas_id 直接传给 ChatService
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\chat.py:241-271`
```python
@router.post("", include_in_schema=True)
async def send_message_new(
    body: SendMessageRequest, request: Request
) -> EventSourceResponse:
    """新建会话并发送消息（不传 conv_id）。"""
    if (
        not body.saas_id
        and not body.workspace_id
        and not body.project_id
        and not body.user_id
    ):
        return _sse_stream(
            _identity_error_events(
                "新建会话至少需要提供 saas_id、workspace_id、project_id、user_id 之一"
            ),
            emit_queued=False,
        )

    return _sse_stream(
        _service(request).send_new(
            message_content=body.message_content,
            selected_model=body.selected_model,
            provider=body.provider,
            saas_id=body.saas_id,
            workspace_id=body.workspace_id,
            project_id=body.project_id,
            user_id=body.user_id,
            file_ids=body.file_ids,
            title=body.title,
        )
    )
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\chat.py:274-291`
```python
@router.post("/{conv_id}")
async def send_message(
    conv_id: str, body: SendMessageRequest, request: Request
) -> EventSourceResponse:
    """发送消息并逐 token 实时流式返回模型回复。"""
    return _sse_stream(
        _service(request).send(
            conv_id=conv_id,
            message_content=body.message_content,
            selected_model=body.selected_model,
            provider=body.provider,
            saas_id=body.saas_id,
            workspace_id=body.workspace_id,
            project_id=body.project_id,
            user_id=body.user_id,
            file_ids=body.file_ids,
        )
    )
```

## 1.3 新建会话时 saas_id 如何落库
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:267-292`
```python
async def send_new(
    self,
    *,
    message_content: str,
    selected_model: str | None,
    provider: str | None,
    saas_id: str | None,
    workspace_id: str | None,
    project_id: str | None,
    user_id: str | None,
    file_ids: list[str] | None,
    title: str | None,
) -> AsyncIterator[ChatEvent]:
    title = title or message_content[:_DEFAULT_TITLE_LENGTH]
    async with self._session_factory() as session:
        conv = await self._conv_factory(session).add(
            saas_id=saas_id,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
            title=title,
            model=selected_model,
            provider=provider,
        )
        conv_id = conv.id
        kb_tenant = _tenant_of(conv)
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\repo.py:45-69`
```python
async def add(
    self,
    *,
    saas_id: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    title: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> Conversation:
    """创建一条新会话并返回完整对象。"""
    conv = Conversation(
        saas_id=saas_id,
        workspace_id=workspace_id,
        project_id=project_id,
        user_id=user_id,
        title=title,
        model=model,
        provider=provider,
    )
    self._session.add(conv)
    await self._session.commit()
    await self._session.refresh(conv)
    return conv
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\models.py:74-89`
```python
class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    saas_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
```

## 1.4 既有会话 / retry 时 saas_id 来源
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:365-377`
```python
async with self._session_factory() as session:
    conv = await self._conv_factory(session).get(conv_id)
    if conv is None:
        yield _error("会话不存在")
        return
# 知识隔离只认会话落库的租户，须在合并请求值之前捕获
```
```python
kb_tenant = _tenant_of(conv)
saas_id = saas_id or conv.saas_id
workspace_id = workspace_id or conv.workspace_id
project_id = project_id or conv.project_id
user_id = user_id or conv.user_id
selected_model = selected_model or conv.model
provider = provider or conv.provider
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:445-463`
```python
async def retry(self, conv_id: str) -> AsyncIterator[ChatEvent]:
    async with self._session_factory() as session:
        conv = await self._conv_factory(session).get(conv_id)
        if conv is None:
            yield _error("会话不存在")
            return
        msg_repo = self._msg_factory(session)
        last_user = await msg_repo.get_last_user_message(conv_id)
        if last_user is None:
            yield _error("没有可重试的消息")
            return
        kb_tenant = _tenant_of(conv)
        saas_id = conv.saas_id
        workspace_id = conv.workspace_id
        project_id = conv.project_id
        user_id = conv.user_id
        selected_model = conv.model
        provider = conv.provider
```

## 1.5 会话里存的 saas_id 最终怎么进租户作用域
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:970-972`
```python
tenant = kb_tenant or TenantScope()
active = await self._activate_extensions(deps.extensions, tenant)
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\extension.py:11-16`
```python
@dataclass(frozen=True)
class TenantScope:
    saas_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
```

## 1.6 结论
结论：saas_id 来自请求体。

已确认事实：
- 新建聊天时，`saas_id` 由 `SendMessageRequest` 请求体字段传入。
- `send_new()` 直接把这个值写进 `conversation.saas_id`。
- 已有会话的 `send()` 若请求体没传，就回退到 `conv.saas_id`。
- `retry()` 不读请求体，直接用会话里已存的 `conv.saas_id`。
- 在本次只读范围内，未找到从请求头、Authorization、Bearer token、登录令牌里解析 `saas_id` 的证据。

本地测试如果要让一次提问使用 `saas_id='jp'`，需要在聊天请求 JSON 请求体里传：
```json
{
  "message_content": "...",
  "saas_id": "jp"
}
```

对新会话端点是 `POST /tap/ai/conversations/chat`；如果是已有会话端点，也可以在请求体传 `saas_id`，但代码会优先沿用会话已落库的 `conv.saas_id`。

# 2. 实体名字的归一化规则，后端和 SDK 是否一致
## 2.1 后端问答按名字查实体时的 norm 函数
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:32-36`
```python
_Q_EXACT = (
    "CYPHER 25 MATCH (e:Entity {scope: $scope}) "
    "WHERE e.label_norm = $norm "
    "RETURN e.id AS id, e.type AS type, e.label AS label, 1.0 AS score LIMIT $limit"
)
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:71-72`
```python
def normalize_label(text: str) -> str:
    return _WS.sub("", unicodedata.normalize("NFKC", text or "")).lower()
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:179-201`
```python
async def match_entities(
    self,
    space: KnowledgeSpace,
    text: str,
    limit: int = 3,
    vector: Sequence[float] | None = None,
) -> list[KgEntity]:
    if not await self._ensure():
        raise KnowledgeBackendError("图谱不可用")
    norm = normalize_label(text)
    scope = space.graph_scope
    logger.info(
        "[Neo4j] 实体匹配调用 scope=%s text=%r limit=%d vector=%s",
        scope,
        text[:200],
        limit,
        bool(vector),
    )
    groups: list[list[KgEntity]] = []
    if norm:
        rows = await self._query(
            _Q_EXACT, {"scope": scope, "norm": norm, "limit": limit}
        )
```

## 2.2 SDK normalize_label 原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\lexicon\_model.py:36-38`
```python
def normalize_label(label: str) -> str:
    """实体名归一化（NFKC + 小写 + 去空白），与查询端 `label_norm` 一致。"""
    return _WS.sub("", unicodedata.normalize("NFKC", label or "")).lower()
```

## 2.3 SDK 写入 label_norm 的位置
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:452-454`
```python
"label_norm": normalize_label(ref.label),
"display_terms": [ref.label, *aliases],
"alias_norms": list(dict.fromkeys(normalize_label(a) for a in aliases)),
```

## 2.4 结论
结论：一致。
- 后端查询端 `normalize_label(text)` 是 NFKC -> 去空白 -> lower()。
- SDK `normalize_label(label)` 也是 NFKC -> 去空白 -> lower()。
- 两边原文返回式完全相同：`_WS.sub("", unicodedata.normalize("NFKC", ...)).lower()`。

# 3. 有没有“对已有文件重新入库”的功能
## 3.1 指定关键词原始输出
命令：
```bash
git --no-pager grep -n -i -E "reindex|reingest|retry|rebuild" -- .
```
原始输出（与本题相关的后端命中）：
```
src/tap_ai/api/library_kb.py:7:- POST  /tap/ai/library/kb/documents/retry      - 重试失败文档
src/tap_ai/api/library_kb.py:120:@router.post("/documents/retry", response_model=KbRetryData)
src/tap_ai/api/library_kb.py:121:async def library_kb_documents_retry(
src/tap_ai/api/library_kb.py:122:    body: KbDocumentRetryRequest, request: Request
src/tap_ai/api/library_kb.py:123:) -> KbRetryData:
src/tap_ai/api/library_kb.py:125:    result = await _service(request).retry(body)
src/tap_ai/application/library_kb.py:75:    async def mark_document_retry(
src/tap_ai/application/library_kb.py:433:    async def retry(self, req: KbDocumentRetryRequest) -> dict[str, Any]:
src/tap_ai/application/library_kb.py:470:        updated = await document_repo.mark_document_retry(
src/tap_ai/application/library_kb_worker.py:287:        job_updated = await job_repo.mark_job_retry(
src/tap_ai/contracts/library_kb.py:101:class KbDocumentRetryRequest(BaseModel):
src/tap_ai/persistence/library_kb_repo.py:193:    async def mark_document_retry(
src/tap_ai/persistence/library_kb_repo.py:529:    async def mark_job_retry(
```

## 3.2 已找到的“重新入库/重试”接口原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\library_kb.py:120-128`
```python
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
```

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_kb.py:433-506`
```python
async def retry(self, req: KbDocumentRetryRequest) -> dict[str, Any]:
    """重新排队失败文档。"""
    saas_id = self._require_saas_id(req.saas_id)
    retried: list[str] = []
    ignored: list[dict[str, str]] = []
    unique_document_ids = list(dict.fromkeys(req.document_ids))
    async with self._session_factory() as session:
        document_repo = self._document_repo_factory(session)
        job_repo = self._job_repo_factory(session)
        try:
            for document_id in unique_document_ids:
                document = await document_repo.get_document(document_id=document_id)
                if document is None or document.saas_id != saas_id:
                    ignored.append(
                        {"document_id": document_id, "reason": "文档不存在"}
                    )
                    continue
                if document.status != "failed":
                    ignored.append(
                        {
                            "document_id": document_id,
                            "reason": "只有失败的文档可以重试",
                        }
                    )
                    continue
                recent_jobs = await job_repo.get_recent_jobs(
                    document_id=document_id,
                    limit=1,
                )
                if not recent_jobs or not recent_jobs[0].storage_path:
                    ignored.append(
                        {
                            "document_id": document_id,
                            "reason": "该文档没有可重新处理的文件",
                        }
                    )
                    continue
                updated = await document_repo.mark_document_retry(
                    document_id=document_id,
                    now=self._clock(),
                    commit=False,
                )
                if not updated:
                    ignored.append(
                        {
                            "document_id": document_id,
                            "reason": "文档状态已变化，请刷新后重试",
                        }
                    )
                    continue
                last_job = recent_jobs[0]
                await job_repo.add_job(
                    saas_id=document.saas_id,
                    workspace_id=document.workspace_id,
                    project_id=document.project_id,
                    user_id=document.user_id,
                    document_id=document.id,
                    batch_id=uuid4().hex,
                    file_name=last_job.file_name,
                    content_sha256=last_job.content_sha256,
                    size_bytes=last_job.size_bytes,
                    storage_path=last_job.storage_path,
                    status="pending",
                    attempts=0,
                    max_attempts=self._settings.library_kb_max_attempts,
                    commit=False,
                )
                retried.append(document_id)
            await session.commit()
```

## 3.3 结论
结论：有。

已确认事实：
- 后端存在 `POST /tap/ai/library/kb/documents/retry`。
- 但它只针对失败文档，不是任意已成功文件的 reindex / rebuild。
- 在本次只读范围内，未找到名为 `reindex`、`reingest`、`rebuild` 的知识库重新入库接口。

# 4. SDK 配置和大模型调用的使用方
## 4.1 git grep -n "env_config" 全部原始输出
命令：
```bash
git --no-pager grep -n "env_config"
```
原始输出：
```
fwd-tap-ingest/src/tap_ingest_sdk/__init__.py:10:from .env_config import load_env_file
fwd-tap-ingest/tests/test_env_config.py:10:from tap_ingest_sdk.env_config import find_env_file, load_env_file
```

## 4.2 git grep -n "OpenAILLMProvider" 全部原始输出
命令：
```bash
git --no-pager grep -n "OpenAILLMProvider"
```
原始输出：
```
fwd-tap-ingest/docs/计划-KG增量与向量迁移.md:69:> 实现: `sinks/_kg_llm_extract.py` (`LLMRelationExtractor`、`OpenAILLMProvider.from_env`、`llm_en
fwd-tap-ingest/docs/设计-Neo4j业务关系扩展.md:513:- SPI: `protocols.LLMProvider.complete(messages) -> str`; 内置 `OpenAILLMProvider` (复用 `KB_CO
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:27:    OpenAILLMProvider,
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:192:        relation_extractor, LLMRelationExtractor(OpenAILLMProvider.from_env())
fwd-tap-ingest/src/tap_ingest_sdk/sinks/__init__.py:7:from ._kg_llm_extract import LLMRelationExtractor, OpenAILLMProvider, llm_enabled
fwd-tap-ingest/src/tap_ingest_sdk/sinks/__init__.py:22:    "OpenAILLMProvider",
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:183:class OpenAILLMProvider:
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:202:    def from_env(cls, env: dict[str, str] | None = None) -> OpenAILLMProvider:
fwd-tap-ingest/tests/test_kg_llm_extract.py:6:from tap_ingest_sdk.sinks import LLMRelationExtractor, Neo4jGraphSink, OpenAILLMProvider, llm_enab
fwd-tap-ingest/tests/test_kg_llm_extract.py:84:        OpenAILLMProvider.from_env({"KB_COPILOT_PROVIDER_BASE_URL": "u", "KB_COPILOT_PROVIDER_API
```

## 4.3 git grep -n -E "KB_AOAI_|KB_COPILOT_PROVIDER|KB_EMBEDDING_|KB_KG_LLM" 全部原始输出
命令：
```bash
git --no-pager grep -n -E "KB_AOAI_|KB_COPILOT_PROVIDER|KB_EMBEDDING_|KB_KG_LLM"
```
原始输出：
```
fwd-tap-ingest/README.md:90:    - `--kg-extractor llm` / `KB_KG_LLM_ENABLED=1`：追加 LLM 关系抽取（默认关）；需 `KB_COPILOT_PROVIDER_BASE_URL`
fwd-tap-ingest/README.md:91:    - `--kg-embed-entities`：生成实体向量并建 Neo4j 向量索引 `entity_embedding`（需 `KB_EMBEDDING_*`，Neo4j ≥ 5.11）
fwd-tap-ingest/README.md:94: 向量维度默认 3072 (`KB_EMBEDDING_DIMENSIONS`)，Azure 与 Neo4j 共用；改维度需新建索引。
fwd-tap-ingest/README.md:101: chunk 向量：`--sink azure` 默认要求 `KB_EMBEDDING_BASE_URL`、`KB_EMBEDDING_API_KEY`、`KB_EMBEDDING_MODEL`，缺一则报错；
fwd-tap-ingest/README.md:102: Integrated vectorization（仅 Azure OpenAI）：设置 `KB_AOAI_ENDPOINT` / `KB_AOAI_EMBEDDING_DEPLOYMENT` 后索引绑定 vector
fwd-tap-ingest/README.md:116:| `KB_EMBEDDING_DIMENSIONS` | 向量维度，默认 3072 |
fwd-tap-ingest/README.md:118:| `KB_AOAI_ENDPOINT` / `KB_AOAI_EMBEDDING_DEPLOYMENT` / `KB_AOAI_EMBEDDING_MODEL` / `KB_AOAI_API_KEY` | 可选，配置索引
fwd-tap-ingest/docs/计划-KG增量与向量迁移.md:58:- [x] **引入 LLM 抽取，做成开关**：默认关闭，未开启时完全不实例化 LLM 客户端、不产生任何调用与成本，行为与现
fwd-tap-ingest/docs/计划-KG增量与向量迁移.md:69:> 实现: `sinks/_kg_llm_extract.py` (`LLMRelationExtractor`、`OpenAILLMProvider.from_env`、`llm_enable
fwd-tap-ingest/docs/计划-KG增量与向量迁移.md:89:> 实现: `Neo4jGraphSink(embedding_provider=...)`；写入 `Entity.embedding` / `embedding_hash`，并建 `e
fwd-tap-ingest/docs/计划-KG增量与向量迁移.md:108:> 实现: `build_index_definition()` (`uri`/`title` 字段、维度取自 `KB_EMBEDDING_DIMENSIONS`（默认 3072
fwd-tap-ingest/docs/设计-Neo4j业务关系扩展.md:511:- `LLMRelationExtractor` (`source="llm"`, `SOURCE_PRIORITY` 中最低)；默认关闭，`--kg-extractor llm`
fwd-tap-ingest/docs/设计-Neo4j业务关系扩展.md:513:- SPI: `protocols.LLMProvider.complete(messages) -> str`；内置 `OpenAILLMProvider`（复用 `KB_COPILC
fwd-tap-ingest/docs/设计-Neo4j业务关系扩展.md:526:- 索引新增 `title`、`url`（完整 URL，缺失时不写）、semantic configuration；向量维度取 `KB_EMBE
fwd-tap-ingest/docs/设计-Neo4j业务关系扩展.md:527:- 配置 `KB_AOAI_*` 后绑定 Azure OpenAI vectorizer（须与入库模型一致）。已有索引改维度或补绑 vectorizer
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:123:    "(default: rule, or llm when KB_KG_LLM_ENABLED=1)",
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:137:    help="Azure: write chunks without vectors (also: KB_EMBEDDING_ENABLED=0). "
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:138:    "By default Azure sinks require KB_EMBEDDING_BASE_URL / KB_EMBEDDING_API_KEY / KB_EMBEDDING_
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:314:    names = ("KB_EMBEDDING_BASE_URL", "KB_EMBEDDING_API_KEY", "KB_EMBEDDING_MODEL")
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:326:    if os.getenv("KB_EMBEDDING_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:331:        raise click.UsageError(f"{exc.message} Or pass --no-embedding / KB_EMBEDDING_ENABLED=0 t
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:333:        base_url=cfg["KB_EMBEDDING_BASE_URL"],
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:334:        api_key=cfg["KB_EMBEDDING_API_KEY"],
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:335:        model=cfg["KB_EMBEDDING_MODEL"],
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:336:        dimension=int(os.getenv("KB_EMBEDDING_DIMENSIONS")) or 3072,
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:342:    dimension = int(os.getenv("KB_EMBEDDING_DIMENSIONS")) or 3072
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:344:        base_url=cfg["KB_EMBEDDING_BASE_URL"],
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:345:        api_key=cfg["KB_EMBEDDING_API_KEY"],
fwd-tap-ingest/src/tap_ingest_sdk/cli/main.py:346:        model=cfg["KB_EMBEDDING_MODEL"],
fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py:32:    embedding_enabled=os.getenv("KB_EMBEDDING_ENABLED", "1").strip()
fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py:34:    embedding_model=os.getenv("KB_EMBEDDING_MODEL"),
fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py:35:    copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py:36:    copilot_provider_base_url=os.getenv("KB_EMBEDDING_BASE_URL"),
fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py:37:    copilot_provider_api_key=os.getenv("KB_EMBEDDING_API_KEY"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:92:    embedding_model=os.getenv("KB_EMBEDDING_MODEL"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:93:    embedding_dimensions=int(os.getenv("KB_EMBEDDING_DIMENSIONS") or 3072)
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:94:    aoai_endpoint=os.getenv("KB_AOAI_ENDPOINT"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:95:    aoai_embedding_deployment=os.getenv("KB_AOAI_EMBEDDING_DEPLOYMENT"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:96:    aoai_embedding_model=os.getenv("KB_AOAI_EMBEDDING_MODEL") or os.getenv("
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:97:    aoai_api_key=os.getenv("KB_AOAI_API_KEY"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:98:    copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:99:    copilot_provider_base_url=os.getenv("KB_EMBEDDING_BASE_URL"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py:100:    copilot_provider_api_key=os.getenv("KB_EMBEDDING_API_KEY"),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:35:LLM_ENABLED_ENV = "KB_KG_LLM_ENABLED"
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:59:    """`KB_KG_LLM_ENABLED` 是否为开启状态（默认关闭）。"""
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:184:    """基于 OpenAI 兼容端点的 `LLMProvider`；复用 `KB_COPILOT_PROVIDER_*`
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:204:        base_url = env.get("KB_COPILOT_PROVIDER_BASE_URL")
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:205:        api_key = env.get("KB_COPILOT_PROVIDER_API_KEY")
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:206:        model = env.get("KB_KG_LLM_MODEL")
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:210:        ("KB_COPILOT_PROVIDER_BASE_URL", base_url),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:211:        ("KB_COPILOT_PROVIDER_API_KEY", api_key),
fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_llm_extract.py:212:        ("KB_KG_LLM_MODEL", model),
fwd-tap-ingest/tests/test_cli.py:63:    for name in ("KB_EMBEDDING_BASE_URL", "KB_EMBEDDING_API_KEY", "KB_EMBEDDING_MODEL", "KB_EMBEDDING_ENAB
fwd-tap-ingest/tests/test_cli.py:73:    assert "KB_EMBEDDING_MODEL" in result.output
fwd-tap-ingest/tests/test_kg_llm_extract.py:78:    assert llm_enabled({"KB_KG_LLM_ENABLED": "0"}) is False
fwd-tap-ingest/tests/test_kg_llm_extract.py:79:    assert llm_enabled({"KB_KG_LLM_ENABLED": "1"}) is True
fwd-tap-ingest/tests/test_kg_llm_extract.py:83:    with pytest.raises(ConfigurationError, match="KB_KG_LLM_MODEL"):
fwd-tap-ingest/tests/test_kg_llm_extract.py:84:        OpenAILLMProvider.from_env({"KB_COPILOT_PROVIDER_BASE_URL": "u", "KB_COPILOT_PROVIDER_AP
```

## 4.4 除 fwd-tap-ingest 自己外，还有谁在用这些配置
结论：只有 `fwd-tap-ingest` 自己使用。

依据：
- `env_config` 的代码命中只出现在 `fwd-tap-ingest/src/tap_ingest_sdk/__init__.py` 和它自己的测试。
- `OpenAILLMProvider` 的代码命中只出现在 `fwd-tap-ingest` 的 CLI、sink、测试和文档。
- `KB_AOAI_* / KB_COPILOT_PROVIDER_* / KB_EMBEDDING_* / KB_KG_LLM_*` 的代码命中也都在 `fwd-tap-ingest` 自己的源码、测试、README、设计文档里。
- 在本次搜索结果中，未找到 `fwd-tap-common` 仓库中其他项目代码文件对这些配置的使用证据。

# 5. 后端的配置是怎么读取的
## 5.1 src/tap_ai/config/settings.py 中 Settings.model_config 原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:40-54`
```python
class Settings(BaseSettings):
    """由 `.env` / 环境变量驱动的应用设置。

安全开关（debug / echo_sql）与运行期不变的应用元数据（app_name /
app_version）默认从代码/包元数据读取；产线无需为它们配置环境变量。
其余连接参数仍由 `TAP_AI_` 前缀环境变量驱动，无默认值。
"""

model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
    env_prefix="TAP_AI_",
)
```
结论：有 `env_file`，指向当前工作目录下的 `.env`。

## 5.2 knowledge/settings.py 中 KnowledgeSettings.model_config 原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:21-27`
```python
class KnowledgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAP_AI_KB_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

## 5.3 tests/conftest.py 完整原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\tests\conftest.py:1-58`
```python
"""共享的 pytest fixtures。

应用通过 `bootstrap.build_app()` 组装。模型与工具插件是假实现，
不触达真实 LLM / Copilot CLI; 但 **数据库与 Redis 仍是进程级单例**:
`build_app()` 缺省使用 `persistence.db.async_session_factory`，
会话工厂绑定真实 MySQL engine。

因此 `app` / `client` 为 session 级: 进程内只应存在一个事件循环持有
该连接池。需要独立事件循环或真实 DB 交互的用例，应自行
`build_app(session_factory=...)` 注入隔离实现，而不要复用本 fixture。
"""
from __future__ import annotations

import asyncio
import pytest
from fastapi.testclient import TestClient

from tap_ai.bootstrap import build_app
from tap_ai.contracts.prompt_library import PromptLibraryProvider
from tap_ai.prompts.library import default_prompt_library

# 注册全局默认提示词实现: 让不显式注入 prompts 的 core 用例 (run_task / decide /
# IntentExtractor / Summarizer) 也能经契约提供者解析到默认实现。
PromptLibraryProvider.set_default(default_prompt_library)


@pytest.fixture(scope="session")
def app():
    """已完整组装的 FastAPI 应用（每个测试会话只构建一次）。"""
    return build_app()


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    """针对已组装应用的同步 HTTP 测试客户端。"""
    return TestClient(app)


@pytest.fixture
def isolated_session_factory():
    """按用例新建的会话工厂，不触碰进程级连接池。

`NullPool` 使每条连接在事务结束后关闭，不带跨循环残留。需要独立
事件循环或真实 DB 交互的用例，应注入本工厂而非复用 `client`。
"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from tap_ai.config.settings import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        # NullPool 不缓存连接，但引擎自身仍持有资源，必须显式释放。
        asyncio.run(engine.dispose())
```

## 5.4 后端导入 SDK 的所有位置原始输出
命令：
```bash
git --no-pager grep -n "tap_ingest_sdk" -- src
```
原始输出：
```
src/tap_ai/plugins/ingest/sdk_ingest.py:46:    """通过 tap_ingest_sdk 实现单文件入库。"""
src/tap_ai/plugins/ingest/sdk_ingest.py:89:        from tap_ingest_sdk import ( # type: ignore[import-untyped]
src/tap_ai/plugins/ingest/sdk_ingest.py:93:        from tap_ingest_sdk.chunkers import ( # type: ignore[import-untyped]
src/tap_ai/plugins/ingest/sdk_ingest.py:96:        from tap_ingest_sdk.parsers import ( # type: ignore[import-untyped]
src/tap_ai/plugins/ingest/sdk_ingest.py:99:        from tap_ingest_sdk.sinks.memory import ( # type: ignore[import-untyped]
src/tap_ai/plugins/ingest/sdk_ingest.py:276:        from tap_ingest_sdk.sinks._azure import ( # type: ignore[import-untyped]
src/tap_ai/plugins/ingest/sdk_ingest.py:279:        from tap_ingest_sdk.sinks._neo4j import ( # type: ignore[import-untyped]
```
结论：在 `src` 范围内，后端导入 `tap_ingest_sdk` 的位置只找到 `src/tap_ai/plugins/ingest/sdk_ingest.py` 这一处文件。

# 6. 入库任务表里，有没有记录“图谱写入状态”的字段
## 6.1 知识库入库任务对应 ORM 类完整原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\models.py:566-620`
```python
class LibraryKbJob(Base):
    """知识库入库任务。"""
    __tablename__ = "library_kb_job"
    __table_args__ = (
        Index("idx_kbjob_status_ctime", "status", "create_time"),
        Index("idx_kbjob_status_hb", "status", "heartbeat_time"),
        Index("idx_kbjob_docid", "document_id"),
        Index("idx_kbjob_saas", "saas_id"),
        Index("idx_kbjob_workspace", "workspace_id"),
        Index("idx_kbjob_project", "project_id"),
        Index("idx_kbjob_user", "user_id"),
    ),
    {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    saas_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        OptionalString(64), nullable=True, index=True
    )
    document_id: Mapped[str] = mapped_column(String(32), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(OptionalString(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heartbeat_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=_now_ts
    )
    update_time: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=_now_ts, onupdate=_now_ts
    )
    deleted: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    delete_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ```

## 6.2 对应建表 SQL 原文
文件：`C:\Users\234393\Desktop\tap-ai-backend\sql\003_create_library_kb_tables.sql:39-72`
```sql
-- ---- library_kb_job (知识库处理任务) ----
CREATE TABLE library_kb_job (
    id             VARCHAR(32)  NOT NULL PRIMARY KEY COMMENT '任务 ID (UUID hex)',
    saas_id        VARCHAR(64)  NULL     COMMENT '租户标识',
    workspace_id   VARCHAR(64)  NULL     COMMENT '工作空间标识',
    project_id     VARCHAR(64)  NULL     COMMENT '项目标识',
    user_id        VARCHAR(64)  NULL     COMMENT '用户标识',
    document_id    VARCHAR(32)  NOT NULL COMMENT '关联文档 ID',
    batch_id       VARCHAR(32)  NOT NULL COMMENT '同一次上传的批次 ID',
    file_name      VARCHAR(512) NOT NULL COMMENT '任务处理时对应的文件名',
    content_sha256 VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '文件内容 SHA-256',
    size_bytes     BIGINT       NOT NULL DEFAULT 0 COMMENT '文件大小 (字节)',
    storage_path   VARCHAR(1024)NOT NULL COMMENT '待处理文件在存储中的路径',
    status         VARCHAR(16)  NOT NULL COMMENT '任务状态 (pending/processing/succeeded/failed)',
    attempts       INT          NOT NULL DEFAULT 0 COMMENT '已尝试次数',
    max_attempts   INT          NOT NULL DEFAULT 0 COMMENT '最大尝试次数',
    error_code     VARCHAR(64)  NULL     COMMENT '失败错误码',
    error_message  TEXT         NULL     COMMENT '失败错误信息',
    chunk_count    INT          NULL     COMMENT '本次处理得到的切片数量',
    heartbeat_time BIGINT       NULL     COMMENT '最近一次心跳时间 (Unix 时间戳，毫秒)',
    started_time   BIGINT       NULL     COMMENT '开始处理时间 (Unix 时间戳，毫秒)',
    finished_time  BIGINT       NULL     COMMENT '处理完成时间 (Unix 时间戳，毫秒)',
    create_time    BIGINT       NOT NULL COMMENT '创建时间 (Unix 时间戳，毫秒)',
    update_time    BIGINT       NOT NULL COMMENT '更新时间 (Unix 时间戳，毫秒)',
    deleted        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '软删除标记 (1=已删除)',
    delete_time    BIGINT       NULL     COMMENT '软删除时间 (Unix 时间戳，毫秒; 未删除为 NULL)',
    INDEX idx_kbjob_status_ctime (status, create_time),
    INDEX idx_kbjob_status_hb (status, heartbeat_time),
    INDEX idx_kbjob_docid (document_id),
    INDEX idx_kbjob_saas (saas_id),
    INDEX idx_kbjob_workspace (workspace_id),
    INDEX idx_kbjob_project (project_id),
    INDEX idx_kbjob_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库处理任务表';
```

## 6.3 结论
结论：不能。

依据：
- LibraryKbJob 里只有一个总的 `status`，以及通用的 `error_code / error_message / chunk_count`。
- ORM 和建表 SQL 里都没有 `azure_status`、`neo4j_status`、`graph_status`、`sink_status`、`kg_status` 之类的独立字段。
- 所以现在这张任务表不能单独表达“Azure 写入成功、Neo4j 写入失败”这种拆分状态；最多只能记录整个任务总体成功/失败，以及失败码/失败信息。

# 核对表
| 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
| ---- | ---------------------------- | ------------------- |
| 1 | 完成 | src\tap_ai\api\chat.py:41-52,241-291 ; src\tap_ai\application\chat.py:267-292,365-377,445-463,970-972 ; src\tap_ai\persistence\repo.py:45-69 ; src\tap_ai\persistence\models.py:74-89 ; src\tap_ai\contracts\extension.py:11-16 |
| 2 | 完成 | src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:32-36,71-72,179-201 ; fwd-tap-ingest\src\tap_ingest_sdk\lexicon\_model.py:36-38 ; fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:452-454 |
| 3 | 完成 | `git grep -n -E "reindex"` |
| 4 | 完成 | `git grep -n "env_config"` ; `git grep -n "OpenAILLMProvider"` ; `git grep -n -E "KB_AOAI"` |
| 5 | 完成 | src\tap_ai\config\settings.py:40-54 ; src\tap_ai\plugins\extensions\knowledge\settings.py:21-27 ; tests\conftest.py:1-58 ; `git grep -n "tap_ingest_sdk" -- src` |
| 6 | 完成 | src\tap_ai\persistence\models.py:566-620 ; sql\003_create_library_kb_tables.sql:39-72 |
```
