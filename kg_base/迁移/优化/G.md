P0.6的回复

# 先说结论
目前仓库里只找到一个现成可复用的“读知识库/检索/图谱补充”能力，是 `extensions.knowledge` 这套插件；它能提供：
1. 检索入口：`KnowledgeService.search()`，底层走 `AzureSearchRetriever.search()`。
2. 两种取证方式：
    - 检索命中的 chunk（文档切片）
    - 图谱补充出的实体/关系，以及“按实体反查 chunk”
3. trace_id 能拿到，在 ChatService 里由 `new_trace_id()` 生成；知识库引用会在 done 事件里带 `references`。

但也要直接说明：
1. 没有找到 `QaAnswerPort / ChunkSourcePort / ChunkPublishPort` 的同事实现。现在只有你们自己这边定义的 Protocol，和一个可借用的知识库插件能力。
2. 没有找到“按 file_id 列文件 / 读某文件全部 chunk / 整体替换某文件全部 chunk”的现成实现。当前只有“按 query 检索”“按 chunk_id 取回”“按 chunk_id 展开邻居”。
3. 没有找到任何写入或删除 Azure AI Search 索引的生产代码。当前仓库中的 Azure Search 代码只有读：`get_document_count / search / get_document`。
4. 没有找到 doc_id / chunk_id 的生成逻辑。`tap-ai-backend` 只消费现成索引字段，不负责生成它们。

---

# 一、问答（对应 `QaAnswerPort.answer(question, mode, top_k) -> QaResult(answer, evidence, trace_id)`）
## 1. 问答检索的入口函数在哪：完整签名、参数、返回类型
结论：现成入口不是 `QaAnswerPort.answer()` 的实现，而是知识库插件里的 `KnowledgeService.search()`；如果要接 `QaAnswerPort`，目前最接近的就是把它包一层。
证据1：知识库搜索入口 `src/tap_ai/plugins/extensions/knowledge/service.py:92-99`
```python
async def search(
    self,
    space: KnowledgeSpace,
    query: str,
    *,
    filters: Mapping[str, str] | None = None,
    top_k: int | None = None,
) -> SearchOutcome:
```
`src/tap_ai/plugins/extensions/knowledge/service.py:31-35`
```python
@dataclass(frozen=True)
class SearchOutcome:
    hits: list[KnowledgeHit] = field(default_factory=list)
    entities: list[KgEntity] = field(default_factory=list)
    relations: list[KgRelation] = field(default_factory=list)
```

证据2：更底层真正打 Azure Search 的入口 `src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:137-139`
```python
async def search(
    self, space: KnowledgeSpace, q: KnowledgeQuery
) -> list[KnowledgeHit]:
```

## 2. 有没有两种模式（直接检索+生成 / 智能体），怎么选
结论：Library 契约里确实定义了两种模式 `llm / agent`，但同事代码里没有对应的 `QaAnswerPort` 两分支实现。现有仓库只有一套知识库扩展，它会作为 Agent/ReAct 的能力扩展接入，不是你这个端口的现成实现。
证据1：契约里定义了两种模式 `src/tap_ai/contracts/library.py:17-18`
```python
AnswerMode = Literal["llm", "agent"] # llm: 检索+一次生成; agent: 智能体
EvidenceKind = Literal["chunk", "kg_fact", "derived"] # 原文切片 / 图谱事实 / 推断内容
```

证据2：知识库插件是作为 Agent 扩展接入的 `src/tap_ai/config/plugins.py:17-24`
```python
ENABLED_PLUGINS: tuple[str, ...] = (
    # 实现 ModelGatewayPort 的模型网关 (LiteLLM)。
    "models.llm.build",
    # 实现 StoragePort 的 Azure Blob 存储 (附件权威存储)。
    "storage.blob.build",
    # 业务知识库扩展（RAG + 知识图谱）；未配置 TAP_AI_KB_* 时 build 返回 None，等同未启用。
    "extensions.knowledge.plugin.build",
)
```
`src/tap_ai/plugins/extensions/knowledge/extension.py:67-70`
```python
def decide_hint(self) -> DecideHint:
    return DecideHint(
        key=HINT_KEY, rule=self._settings.decide_rule, query_key=HINT_QUERY_KEY
    )
```

我的判断：现有仓库只有“Agent 侧可用的知识库扩展”，没有给 `QaAnswerPort.answer(mode=llm/agent)` 直接复用的二选一函数。后面真接 `QaAnswerPort` 时，需要你们自己做一层 mode 分发。

## 3. 返回结果里能不能拿到“生成答案时实际用到的切片”：每条切片有哪些字段
结论：能拿到一部分。当前链路里最终能拿到的是 `references`，来源于预取 refs + 工具 `source_refs`。每条文档证据至少有：`index / chunk_id / source_file / page_or_sheet / via / score`。检索命中对象本身还有 `content / document_id / section_title / metadata`。
证据1：`KnowledgeHit` 字段 `src/tap_ai/contracts/knowledge.py:34-45`
```python
@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: str
    content: str
    # RRF 融合分。
    score: float
    # 向量通道原始分（用于门槛判断）。
    vector_score: float = 0.0
    document_id: str = ""
    source_file: str = ""
    page_or_sheet: str = ""
    section_title: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

证据2：done 事件会带 `references` `src/tap_ai/application/chat.py:1198-1210`
```python
yield _done(
    answer=answer,
    message_id=assistant_id,
    model=model_id,
    conversation_id=conv_id,
    status=status,
    result_code=result_code,
    turn_count=ctx.turn,
    tool_call_count=int(state_box.get("tool_calls") or 0),
    elapsed_ms=latency_ms,
    ttft_ms=ttft_ms,
    run_id=run_id,
    references=_collect_knowledge_refs(ctx),
)
```

证据3：审计引用结构 `src/tap_ai/plugins/extensions/knowledge/extension.py:171-186`
```python
def _ref(
    index: str,
    chunk_id: str,
    source_file: str,
    page: str,
    via: str,
    score: float | None,
) -> dict[str, Any]:
    return {
        "index": index,
        "chunk_id": chunk_id,
        "source_file": source_file,
        "page_or_sheet": page,
        "via": via,
        "score": score,
    }
```

证据4：工具返回 `source_refs` 时只保留 `file#page@chunk_id` `src/tap_ai/plugins/extensions/knowledge/tools.py:32-34`
```python
def make_source_ref(source_file: str, page: str, chunk_id: str) -> str:
    """source_refs 形如 ``file#page@chunk_id``；audit_refs 据此回解。"""
    return f"{source_file}#{page}@{chunk_id}"
```

## 4. 有没有图谱事实或推断内容，怎么区分
结论：有图谱事实，但没有找到 Library 契约里 `EvidenceKind="kg_fact" / "derived"` 的落地映射。现有仓库里图谱事实走的是 `relations / query_business_graph`；而“推断内容 derived”没有明确结构化输出。
证据1：Library 契约允许三种证据类型 `src/tap_ai/contracts/library.py:17-18`
```python
AnswerMode = Literal["llm", "agent"] # llm: 检索+一次生成; agent: 智能体
EvidenceKind = Literal["chunk", "kg_fact", "derived"] # 原文切片 / 图谱事实 / 推断内容
```

证据2：搜索结果里区分 `hits / entities / relations` `src/tap_ai/plugins/extensions/knowledge/service.py:31-35`
```python
@dataclass(frozen=True)
class SearchOutcome:
    hits: list[KnowledgeHit] = field(default_factory=list)
    entities: list[KgEntity] = field(default_factory=list)
    relations: list[KgRelation] = field(default_factory=list)
```

证据3：图谱工具明确说“图谱结果不产生 source_refs” `src/tap_ai/plugins/extensions/knowledge/tools.py:245-248`
```python
head = "匹配实体: " + ", ".join(f"{e.label}({e.type})" for e in entities)
body = render_relations(relations) if relations else "(无相关关系)"
# 图谱结果不产生 source_refs: 审计只记录文档证据。
return ToolResult.success(f"{head}\n{body}")
```

## 5. trace_id 或 Langfuse 的 id 能不能拿到
结论：`trace_id` 能拿到；Langfuse 的 observation id 我没看到在对外返回里暴露。
证据1：trace_id 由 `new_trace_id()` 生成
```python
def new_trace_id() -> str:
    """生成一次请求链路的 trace_id。"""
    return uuid.uuid4().hex
```
`src/tap_ai/application/chat.py:733-733`
```python
trace_id = new_trace_id()
```

证据2：ChatEvent 里有 references，但没有 Langfuse id 字段 `src/tap_ai/application/chat.py:112-113`
```python
# 知识库引用（仅终帧携带）。
references: tuple[dict[str, Any], ...] = ()
```

证据3：Langfuse 只是 observability 适配层 `src/tap_ai/plugins/observability/langfuse.py:47-60`
```python
@contextmanager
def observe(
    self,
    *,
    name: str,
    as_type: str = "span",
    input: Any = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
) -> Iterator[ObservationPort]:
```

我的判断：`QaResult.trace_id` 可以直接接 `trace_id`；但如果你想要 Langfuse 的 observation/span id，现有代码里没看到有对外透出。

## 6. 调用它需要哪些依赖（模型网关、检索客户端、配置），这些依赖从 container 里怎么取
结论：现有知识库能力依赖：
1. `KnowledgeSettings`（`TAP_AI_KB_*`）
2. `AzureSearchRetriever`
3. `LiteLLMEmbedding`
4. 可选 `Neo4jKnowledgeGraph`
5. `KnowledgeExtension`
这些不是单独注册到 `container.services` 里，而是通过插件装配进 `container.extension_registry`。


## 证据1：插件 build 时装配依赖 `src/tap_ai/plugins/extensions/knowledge/plugin.py:35-52`
```python
resolver = KnowledgeSpaceResolver(kb.indexes)
retriever = AzureSearchRetriever(
    endpoint=kb.azure_search_endpoint,
    key=key,
    vector_field=kb.vector_field,
    candidate_multiplier=kb.candidate_multiplier,
    rrf_k=kb.rrf_k,
    min_vector_score=kb.min_vector_score,
    allowed_filter_fields=kb.allowed_filter_fields,
    max_clients=kb.max_index_clients,
    exists_ttl_s=float(kb.index_cache_ttl_s),
)
embedding = LiteLLMEmbedding(
    model=kb.embedding_model,
    api_base=settings.litellm_base_url,
    api_key=settings.litellm_api_key,
    dimensions=kb.embedding_dimensions,
)
```

## 证据2：bootstrap 按插件注册进扩展注册表
```python
if instance is None:
    return
# 注册到对应类别的注册表中
_, registry = _resolve_registry(category, container)
key = getattr(instance, "__port_name__", None) or module_path
registry.register(key, instance)
```
`src/tap_ai/bootstrap.py:46-47`
```python
if category == "extensions":
    return "extension_registry", container.extension_registry
```

# 二、读索引里的切片（对应 ChunkSourcePort 的 list_files / get_file / list_chunks）
## 7. 索引用的是什么，客户端在哪个文件构造，索引名从哪个配置项
结论：用的是 Azure AI Search。客户端在 `backends/azure_search.py` 构造；索引名不是写死，而是从 `TAP_AI_KB_INDEXES` 解析出的 `KnowledgeSpace.index_name` 来。

证据1：Azure Search SDK
```python
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
```

证据2：客户端构造位置 `src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:80-89`
```python
async def _client(self, index_name: str) -> SearchClient:
    client = self._clients.get(index_name)
    if client is not None:
        self._clients.move_to_end(index_name)
        return client
    client = SearchClient(
        endpoint=self._endpoint,
        index_name=index_name,
        credential=self._credential,
    )
```

证据3：索引名映射配置 `src/tap_ai/plugins/extensions/knowledge/settings.py:29-34`
```python
enabled: bool = False
# saas_id -> index 名称映射 (JSON)，如 {"hk":"hk-kb-chunk-tap-dit"}; 未列出的租户不启用知识库。
indexes: dict[str, str] = {}
azure_search_endpoint: str = ""
# 查询密钥（query key）。
azure_search_key: SecretStr = SecretStr("")
```

`src/tap_ai/plugins/extensions/knowledge/spaces.py:33-39`
```python
def resolve(self, tenant: TenantScope) -> KnowledgeSpace | None:
    # tenant 来自会话落库值; 缺失或未配置 -> 本请求不启用知识库。
    saas_id = (tenant.saas_id or "").strip().lower()
    index = self._indexes.get(saas_id)
    if index is None:
        return None
    return KnowledgeSpace(index_name=index, graph_scope=index)
```

## 8. 索引中每条切片的字段：完整字段名列表和含义
结论：当前读索引时明确 select 的字段有 9 个；另有可选 `chunk_index`。

| 字段 | 含义 |
| ---- | ---- |
| chunk_id | 切片主键 / chunk 标识 |
| content | 切片正文 |
| document_id | 文档 id |
| source_file | 源文件名/路径 |
| page_or_sheet | 页码、sheet 或 slide |
| section_title | 小节标题 |
| doc_type | 文档类型 |
| product_name | 产品名 |
| language | 语言 |
| chunk_index | 同文档内顺序号（可选，旧索引可能没有） |

证据1：select 字段列表 `src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:37-47`
```python
_SELECT = [
    "chunk_id",
    "content",
    "document_id",
    "source_file",
    "page_or_sheet",
    "section_title",
    "doc_type",
    "product_name",
    "language",
]
```

证据2：`chunk_index` 是可选字段 `src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:257-264`
```python
# chunk_index 为可选字段 (旧 index 没有, select 会 400)，单独探测。
try:
    with_idx = await self._lookup(
        client, [chunk_id], [*_SELECT, "chunk_index"]
    )
    if with_idx:
        idx = _int_or_none(with_idx[0].metadata.get("chunk_index"))
        select = [*_SELECT, "chunk_index"]
```

## 9. doc_id 和 chunk_id 怎么生成：是不是仍然用内容哈希
结论：在这个仓库里没找到生成逻辑。当前 tap-ai-backend 只读取 document_id/chunk_id，不生成它们，所以也无法从这里证明还是不是“doc:: + sha256 前 16 位 / sha1(...) 前 12 位”。证据：当前仓库只消费字段，不生成字段
`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:330-340`
```python
return KnowledgeHit(
    chunk_id=str(doc.get("chunk_id", "")),
    content=str(doc.get("content") or ""),
    score=score,
    # 仅向量通道的分数被 rrf_merge 采用; BM25 通道的 vector_score 不参与。
    vector_score=score,
    document_id=str(doc.get("document_id") or ""),
    source_file=str(doc.get("source_file") or ""),
    page_or_sheet=str(doc.get("page_or_sheet") or ""),
    section_title=str(doc.get("section_title") or ""),
    metadata=meta,
)
```

## 10. 有没有“按文件列出切片”“列出所有文件”的现成函数；没有的话，索引支持按 doc_id 过滤吗
结论：
1. 没有找到“列出所有文件”或“按文件列切片”的现成函数。
2. 支持按 `document_id` 过滤，至少在 `neighbors()` 里已经这么做了。证据 1：现成读接口只有这三个
`src/tap_ai/contracts/knowledge.py:71-84`
```python
class KnowledgeRetrieverPort(Protocol):
    async def exists(self, space: KnowledgeSpace) -> bool: ...

    async def search(
        self, space: KnowledgeSpace, q: KnowledgeQuery
    ) -> list[KnowledgeHit]: ...

    async def get_chunks(
        self, space: KnowledgeSpace, chunk_ids: Sequence[str]
    ) -> list[KnowledgeHit]: ...

    async def neighbors(
        self, space: KnowledgeSpace, chunk_id: str, window: int = 1
    ) -> list[KnowledgeHit]: ...
```

证据 2：`neighbors()` 用 `document_id` 过滤
`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:267-277`
```python
if anchor.document_id and idx is not None:
    flt = (
        f"document_id eq '{escape_odata(anchor.document_id)}'"
        f" and chunk_index ge {idx - window} and chunk_index le {idx + window}"
    )
elif anchor.document_id and anchor.page_or_sheet:
    # 摄取侧尚未写 chunk_index: 退化为同文档同页。
    flt = (
        f"document_id eq '{escape_odata(anchor.document_id)}'"
        f" and page_or_sheet eq '{escape_odata(anchor.page_or_sheet)}'"
    )
```

## 11. 文件的 sheet 名或 slide 列表能从哪里取到
结论：目前只能从单条 hit 的 `page_or_sheet` 字段拿；没有找到“按 file 聚合出 locators 列表”的现成函数。
证据：单条 hit 只有 `page_or_sheet`
`src/tap_ai/contracts/knowledge.py:41-45`
```python
document_id: str = ""
source_file: str = ""
page_or_sheet: str = ""
section_title: str = ""
metadata: Mapping[str, Any] = field(default_factory=dict)
```

# 三、写入（对应 `ChunkPublishPort.publish(file_id, chunks, operator) -> PublishResult`）
## 12. 入库流程的入口函数，有没有“删除某个文件的全部切片”“上传一批切片”的函数
结论：没找到。当前仓库里 Azure Search 这部分只有读，没有写入/删除索引的函数。
证据：AzureSearchRetriever 只实现读接口
`src/tap_ai/contracts/knowledge.py:71-88`
```python
class KnowledgeRetrieverPort(Protocol):
    async def exists(self, space: KnowledgeSpace) -> bool: ...

    async def search(
        self, space: KnowledgeSpace, q: KnowledgeQuery
    ) -> list[KnowledgeHit]: ...

    async def get_chunks(
        self, space: KnowledgeSpace, chunk_ids: Sequence[str]
    ) -> list[KnowledgeHit]: ...

    async def neighbors(
        self, space: KnowledgeSpace, chunk_id: str, window: int = 1
    ) -> list[KnowledgeHit]: ...

    async def probe(self) -> bool: ...
    async def aclose(self) -> None: ...
```

## 13. 上传切片前要做什么：生成向量（用哪个模型）、补哪些字段
结论：只能从“读侧契约”反推出摄取侧至少要补哪些字段；仓库里没找到真正上传代码。可以确认 embedding 模型别名默认是 `text-embedding-3-large`。

证据1：embedding 模型配置
`src/tap_ai/plugins/extensions/knowledge/settings.py:35-38`
```python
vector_field: str = "content_vector"
# LiteLLM 上的 embedding 模型别名; 必须与摄取时一致 (3072 维)。
embedding_model: str = "text-embedding-3-large"
embedding_dimensions: int = 3072
```

证据2：读侧依赖的索引字段
`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:37-47`
```python
_SELECT = [
    "chunk_id",
    "content",
    "document_id",
    "source_file",
    "page_or_sheet",
    "section_title",
    "doc_type",
    "product_name",
    "language",
]
```
## 14. 手动修改切片后，chunk_id 应该怎么算才不和同事的增量逻辑冲突
结论：这个仓库里没有证据能回答。因为没有生成 chunk_id 的逻辑，也没有增量写索引逻辑。

## 15. 入库记录（如果有 state 表或入库记录表）要不要同步更新
结论：这个仓库里只看到了 Library 自己的草稿表/评估表，没有看到“知识库索引入库状态表”与索引写入逻辑联动的实现，所以无法从本仓库证明要不要同步更新。

## 16. 知识图谱和切片的关系：切片变了以后，图谱那边要不要做什么
结论：从读侧逻辑看，图谱和切片是关联的：图谱能按实体反查 chunk_ids。所以如果切片变了，高概率要同步维护图谱里的 chunk 关联；但本仓库没有写侧实现，不能把这条当已确认事实。

证据：图谱可按实体回溯 chunk
`src/tap_ai/plugins/extensions/knowledge/service.py:132-143`
```python
async def _hits_from_entities(
    self, space: KnowledgeSpace, entities: Sequence[KgEntity], limit: int
) -> list[KnowledgeHit]:
    assert self._graph is not None
    try:
        chunk_ids: list[str] = []
        for ent in entities:
            chunk_ids += await self._graph.chunks_by_entity(space, ent.id, limit)
        chunk_ids = list(dict.fromkeys(chunk_ids))[:limit]
        if not chunk_ids:
            return []
        return dedupe_hits(await self._retriever.get_chunks(space, chunk_ids))
```

我的判断：切片一旦变，图谱侧至少要检查 `chunks_by_entity()` 用到的 chunk 引用会不会悬空；但这条在当前仓库里没有写侧代码能坐实。

---
# 四、插件写法
## 17. `config/plugins.py` 中 `ENABLED_PLUGINS` 的写法；找一个同事写的插件，贴出 `build()` 和 `__port_name__`
证据1：`ENABLED_PLUGINS` 写法
`src/tap_ai/config/plugins.py:17-24`
```python
ENABLED_PLUGINS: tuple[str, ...] = (
    # 实现 ModelGatewayPort 的模型网关（LiteLLM）。
    "models.llm.build",
    # 实现 StoragePort 的 Azure Blob 存储（附件权威存储）。
    "storage.blob.build",
    # 业务知识库扩展（RAG + 知识图谱）；未配置 TAP_AI_KB_* 时 build 返回 None，等同未启用。
    "extensions.knowledge.plugin.build",
)
```

证据2：知识库插件 `build()`
`src/tap_ai/plugins/extensions/knowledge/plugin.py:23-79`
```python
def build(settings: Settings) -> KnowledgeExtension | None:
    """未启用或缺少凭据时返回 None；本函数不发起任何网络调用。"""
    kb = KnowledgeSettings()
    if not kb.enabled:
        return None
    key = kb.azure_search_key.get_secret_value()
    if not kb.azure_search_endpoint or not key:
        logger.warning(
            "TAP_AI_KB_ENABLED=true 但缺少 Azure Search endpoint/key, 知识库未启用"
        )
        return None

    resolver = KnowledgeSpaceResolver(kb.indexes)
    retriever = AzureSearchRetriever(
        endpoint=kb.azure_search_endpoint,
        key=key,
        vector_field=kb.vector_field,
        candidate_multiplier=kb.candidate_multiplier,
        rrf_k=kb.rrf_k,
        min_vector_score=kb.min_vector_score,
        allowed_filter_fields=kb.allowed_filter_fields,
        max_clients=kb.max_index_clients,
        exists_ttl_s=float(kb.index_cache_ttl_s),
    )
    embedding = LiteLMEmbedding(
        model=kb.embedding_model,
        api_base=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        dimensions=kb.embedding_dimensions,
    )
    graph = None
    closers: list[object] = [retriever]
    if kb.neo4j_uri:
        from tap_ai.plugins.extensions.knowledge.backends.neo4j_graph import (
            Neo4jKnowledgeGraph,
        )
        graph = Neo4jKnowledgeGraph(
            uri=kb.neo4j_uri,
            user=kb.neo4j_user,
            password=kb.neo4j_password,
            database=kb.neo4j_database,
            timeout_s=kb.neo4j_timeout_s,
            entity_vector=kb.kg_entity_vector,
            entity_min_score=kb.kg_entity_min_score,
            relation_types=kb.kg_relation_types,
        )
        closers.append(graph)
        service = KnowledgeService(
            retriever=retriever,
            embedding=embedding,
            settings=kb,
            graph=graph,
            synonyms=load_synonyms(kb.synonyms_path),
        )
        return KnowledgeExtension(
            service=service, resolver=resolver, settings=kb, closers=closers
        )
```

证据3：知识库插件 `__port_name__`
`src/tap_ai/plugins/extensions/knowledge/extension.py:42-43`
```python
class KnowledgeExtension:
    __port_name__ = "knowledge"
```

## 18. 插件里怎么拿到模型网关、配置
结论：
1. 配置：`build(settings: Settings)` 的参数直接拿主配置；插件自己的 `KnowledgeSettings()` 再读 `TAP_AI_KB_*`。
2. 模型网关：知识库插件没拿聊天模型网关，它只直接构造了 `LiteLMEmbedding`；模型网关那套是另一个插件 `models.llm.build`。

证据1：知识库插件拿主配置 + 自己的知识库配置
`src/tap_ai/plugins/extensions/knowledge/plugin.py:23-25`
```python
def build(settings: Settings) -> KnowledgeExtension | None:
    """未启用或缺少凭据时返回 None；本函数不发起任何网络调用。"""
    kb = KnowledgeSettings()
```

证据2：模型网关插件写法
`src/tap_ai/plugins/models/llm.py:56-64`
```python
class LiteLLMModelGateway(ModelGatewayPort):
    """通过 LiteLLM 网关的 /v1/models 动态获取模型目录。"""
    __port_name__ = "model_gateway"

    def __init__(
        self,
        settings: Settings,
        observability: ObservabilityPort | None = None,
    ):
```

`src/tap_ai/plugins/models/llm.py:571-574`
```python
def build(
    settings: Settings, observability: ObservabilityPort | None = None
) -> LiteLLMModelGateway:
    return LiteLLMModelGateway(settings, observability=observability)
```

# 五、安全
## 19. 开发环境用的是哪个索引名（从配置看，不读 .env）；代码里有没有写死 jp-poc
结论：
1. 无法从代码静态确定开发环境实际索引名，因为索引名来自 `TAP_AI_KB_INDEXES` 的运行时配置，不读 `.env` 就拿不到具体值。
2. 在 `src/tap_ai` 代码里，我没找到写死 `jp-poc` 的命中。

证据：索引名来自配置映射，不是常量
`src/tap_ai/plugins/extensions/knowledge/settings.py:29-31`
```python
enabled: bool = False
# saas_id -> index 名称映射（JSON），如 {"hk":"hk-kb-chunk-tap-dit"}；未列出的租户不启用知识库。
indexes: dict[str, str] = {}
```

`src/tap_ai/plugins/extensions/knowledge/spaces.py:35-39`
saas_id = (tenant.saas_id or "").strip().lower()
index = self.indexes.get(saas_id)


## 20. 列出所有会写入或删除索引的函数，标明“绝对不能在测试里调用”
结论：当前仓库中没有找到会写入或删除 Azure AI Search 索引的函数；所以这里列不出生产写侧函数名。当前能确认的 Azure Search 调用都是只读。

已确认只读函数：
1. AzureSearchRetriever.exists() → client.get_document_count()
2. AzureSearchRetriever.search() → client.search()
3. AzureSearchRetriever._lookup() → client.get_document()

证据：只读调用点
`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:104-106`
```python
try:
    client = await self._client(space.index_name)
    await asyncio.wait_for(client.get_document_count(), self._timeout_s)
```

`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:121-123`
```python
results = await client.search(**kwargs)
async for doc in results:
    hits.append(_to_hit(doc))
```

`src/tap_ai/plugins/extensions/knowledge/backends/azure_search.py:208-212`
```python
async def _one(chunk_id: str) -> KnowledgeHit | None:
    try:
        doc = await asyncio.wait_for(
            client.get_document(key=chunk_id, selected_fields=select),
            self._timeout_s,
        )
```

我的判断：真正“绝对不能在测试里调用”的写索引函数，大概率不在这个仓库里，而在你旧项目或同事的摄取仓库中。

# 最后：三个插座怎么接、缺什么、有什么风险

| 插座 | 当前最接近可接的同事代码 | 还缺什么 | 主要风险 |
| ---- | ---- | ---- | ---- |
| QaAnswerPort.answer(question, mode, top_k) | KnowledgeService.search() + KnowledgeExtension 这套能力；检索入口在 src/tap_ai/plugins/extensions/knowledge/service.py:92 | 缺一个真正返回 QaResult(answer, evidence, trace_id) 的 adapter；还缺 mode=llm/agent 分发 | 现成代码是 Agent 扩展，不是 Library 端口；kg_fact/derived 没有直接映射；Langfuse id 没对外暴露 |
| ChunkSourcePort.list_files / get_file / list_chunks | 只能复用 AzureSearchRetriever.search() / get_chunks() / neighbors() | 缺“列文件”“按 file_id 取 detail”“按 file_id 分页列 chunks”的实现；缺 locators 聚合 | 当前代码按 query / chunk_id 读，不是按 file_id 读；document_id 是否就是你要的 file_id 也还没在本仓库证实 |
| ChunkPublishPort.publish(file_id, chunks, operator) | 没找到可接的现成写侧函数 | 缺整套写入实现：删除旧 chunk、补字段、生成 embedding、批量上传、必要时同步图谱/状态表 | 这是最大风险点；如果直接自己写，最容易和同事的 chunk_id / document_id / 增量规则冲突 |
