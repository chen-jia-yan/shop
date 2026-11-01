## 1. POC 写入 jp-poc 索引时，切片的主键字段叫什么、值是怎么算出来的
**结论：**主键字段叫 `chunk_id`；POC 写入 Azure Search 时把 `chunk.metadata.chunk_id` 写到文档主键字段 `chunk_id`。在全量入库链路里，这个值由 `sha1(f"{document.source_file}:{segment.locator}:{part}")[:12]` 算出来。

证据 1: Azure 索引主键字段定义
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\indexing\azure_search_store.py:93-106`
```python
def _ensure_index(self) -> None:
    fields = [
        SimpleField(name="chunk_id", type="Edm.String", key=True),
        SearchableField(name="content", type="Edm.String", analyzer_name="standard.lucene"),
        SearchField(
            name=self._settings.azure_search_vector_field,
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="vector-profile",
        ),
    ]
    for name in _METADATA_FIELDS:
        fields.append(SimpleField(name=name, type="Edm.String", filterable=True, facetable=True))
```

证据 2: 上传文档时写入的主键字段
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\indexing\azure_search_store.py:170-183`
```python
def upload_document_chunks(self, document_id: str, version_id: str, chunks: Iterable[DocumentChunk]) -> None:
    """增量上传: 单个文档的 chunk 写入, 复用已有 embedding 或现场生成"""
    self._ensure_index()
    documents = []
    for chunk in chunks:
        payload = chunk.metadata.to_dict()
        payload["document_id"] = document_id
        payload["document_version_id"] = version_id
        doc = {"chunk_id": chunk.metadata.chunk_id, "content": chunk.content}
        doc[self._settings.azure_search_vector_field] = chunk.embedding or []
        for name in _METADATA_FIELDS:
            value = payload.get(name)
            doc[name] = "" if value is None else str(value)
        documents.append(doc)
```

证据 3: `chunk_id` 字段在元数据 schema 中定义
```python
class ChunkMetadata(BaseModel):
    """可追溯元数据。每个 chunk 入库即绑定该 schema。"""
    source_file: str
    doc_type: str
    page_or_sheet: str | None = None
    cell_range: str | None = None
    product_name: str | None = None
    language: str | None = None
    cycle_stage: str | None = None
    title_path: str | None = None
    section_title: str | None = None
    content_type: str | None = None
    block_type: str | None = None
    source_kind: str | None = None
    evidence_level: str | None = None
    source_consistency: float | None = None
    semantic_tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    artifact_path: str | None = None
    document_id: str | None = None
    document_version_id: str | None = None
    chunk_id: str
    ingested_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
```

证据 4: `chunk_id` 的计算原文
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\ingestion\ingestor.py:243-278`
```python
for part in parts:
    chunk_id = hashlib.sha1(f"{document.source_file}:{segment.locator}:{part}".encode()).hexdigest()[:12]
    # flowchart 元数据注入（仅当 segment 包含流程图时）
    fc_nodes: list[str] = []
    fc_edges: list[str] = []
    fc_data: dict[str, Any] | None = None
    if segment.flowchart:
        fc_nodes = [n.text for n in segment.flowchart.nodes]
        fc_edges = [f"{e.source_text} -> {e.target_text}" for e in segment.flowchart.edges]
        fc_data = segment.flowchart.to_dict()

    metadata = ChunkMetadata(
        source_file=document.source_file,
        doc_type=document.doc_type,
        page_or_sheet=segment.locator,
        cell_range=segment.cell_range,
        product_name=document.product_name,
        language=document.language,
        cycle_stage=document.cycle_stage,
        title_path=segment.title_path,
        section_title=segment.section_title,
        content_type=content_type,
        block_type=segment.block_type,
        source_kind=segment.source_kind or "native",
        evidence_level=segment.evidence_level or "primary",
        semantic_tags=list(segment.semantic_tags),
        entities=list(segment.entities),
        table_headers=list(segment.table_headers),
        artifact_path=segment.artifact_path,
        chunk_id=chunk_id,
        ocr_blocks=list(segment.ocr_blocks),
        flowchart_nodes=fc_nodes,
        flowchart_edges=fc_edges,
        flowchart_data=fc_data,
    )
```

## 2. POC 建图谱时，Chunk 节点的编号是怎么来的
**结论：**POC 建图谱时，Chunk 节点的 `node_id` 来自 chunk 内容本身的 SHA256 前 12 位，不是 Azure 索引里的 `chunk_id` 算法。`mentioned_in` 边的 `target` 也是这个值。

证据 1: Chunk 节点 ID 生成函数
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\kg_extractor.py:68-70`
```python
def _content_hash(text: str) -> str:
    """对 chunk 内容计算 SHA256 前 12 位，作为 Chunk 节点 ID。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
```

证据 2: 写入 `type='Chunk'` 节点时 `id` 的赋值原文
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\kg_extractor.py:194-219`
```python
# 1. Chunk 节点（直接从 chunks 构建，不依赖 LLM）
chunk_id_by_index: dict[int, str] = {}
for i, ch in enumerate(chunks, start=1):
    content = str(ch.get("content", ""))
    chunk_hash = _content_hash(content)
    meta = ch.get("metadata", {}) if isinstance(ch.get("metadata"), dict) else {}
    page = str(meta.get("page_or_sheet", ""))
    cell = str(meta.get("cell_range", ""))
    label_parts = [source_file]
    if page:
        label_parts.append(page)
    if cell:
        label_parts.append(cell)
    node = {
        "id": chunk_hash,
        "type": "Chunk",
        "label": " / ".join(label_parts),
        "metadata": {
            "source_file": source_file,
            "page_or_sheet": page,
            "cell_range": cell,
        },
    }
    nodes.append(node)
    chunk_id_by_index[i] = chunk_hash
```

证据 3: `mentioned_in` 边的 `target` 用值原文
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\extractors\rule_extractor.py:91-121`
```python
for ch in chunks:
    text = ch.content or ""
    if not text:
        continue
    cid = _chunk_id(text)
    present: list[str] = []

    # 1) 词典匹配已有实体
    for label, eid in label_to_id.items():
        if len(label) >= self.MIN_LABEL_LEN and label in text:
            present.append(eid)
            nodes_by_id.setdefault(
                eid,
                {
                    "id": eid,
                    "type": _type_of(eid),
                    "label": _label_of(eid, label),
                    "source_docs": [source_doc_id],
                    "_reason": "matched_existing",
                },
            )
    _ensure_chunk_node(ch, cid)
    edges.append(
        {
            "source": eid,
            "target": cid,
            "type": "mentioned_in",
            "source_docs": [source_doc_id],
            "provenance_inferred": True,
        }
    )
```

证据 4: 规则抽取器里 `cid` 的算法
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\extractors\rule_extractor.py:9-10`
```python
def _chunk_id(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:12]
```

## 3. 对比第 1 条和第 2 条：是不是同一个值、同一种算法
回答：不一致
依据：
- 第 1 条的 Azure /jp-poc 切片主键：`sha1(f"{document.source_file}:{segment.locator}:{part}")[:12]`
- 第 2 条的图谱 Chunk 节点编号：`sha256(content)[:12]`
- 两边输入不同（前者含 `source_file + locator + part`，后者只看 `content`），哈希算法也不同（SHA1 vs SHA256）

证据 1: Azure /jp-poc 的算法
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\ingestion\ingestor.py:243-245`
```python
for part in parts:
    chunk_id = hashlib.sha1(f"{document.source_file}:{segment.locator}:{part}".encode()).hexdigest()[:12]
```

证据 2: 图谱 Chunk 的算法
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\kg_extractor.py:68-70`
```python
def _content_hash(text: str) -> str:
    """对 chunk 内容计算 SHA256 前 12 位，作为 Chunk 节点 ID。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
```

## 4. kg.db（kg_api 使用的 SQLite 文件）的完整路径，以及建表语句
结论：`kg_api` 默认把 `kg.db` 读为 `C:\Users\234393\Desktop\kg_api\data\kg.db`。

证据 1: kg.db 默认路径
文件：`C:\Users\234393\Desktop\kg_api\settings.py:24-31`
```python
def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    return Settings(
        data_dir=data_dir,
        db_path=Path(os.getenv("KG_DEMO_DB_PATH", data_dir / "kg.db")),
        chunk_content_path=Path(
            os.getenv("KG_DEMO_CHUNK_CONTENT_PATH", data_dir / "chunk_content.csv")
        ),
    )
```

证据 2: kg_api 只读连接就是用这个路径
文件：`C:\Users\234393\Desktop\kg_api\db.py:27-39`
```python
class GraphRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._doc_to_source_files: dict[str, list[str]] = {}
        self._chunk_to_source_file: dict[str, str] = {}
        self._entity_source_files: dict[str, list[str]] = {}
        self._file_summaries: list[FileSummary] = []
        self._build_caches()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
```

证据 3: `CREATE TABLE kg_nodes` 原文
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\stores\sqlite_schema.sql:5-12`
```sql
CREATE TABLE IF NOT EXISTS kg_nodes (
  node_id        TEXT PRIMARY KEY, -- 'System:SFDC' 或 chunk 的哈希 id
  type           TEXT NOT NULL,    -- System/Concept/Product/Process/Data/Document/Role/Channel/Chunk
  label          TEXT NOT NULL,    -- 显示名
  metadata_json  TEXT,             -- Chunk 节点的 source_file/page_or_sheet/cell_range, 其它可为空
  created_seq    INTEGER,          -- 第几次变更时加入（对应 kg_changelog.seq）
  updated_seq    INTEGER
);
```

证据 4: `CREATE TABLE kg_edges` 原文
文件：`C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\kg\stores\sqlite_schema.sql:15-26`
```sql
CREATE TABLE IF NOT EXISTS kg_edges (
  edge_id          TEXT PRIMARY KEY, -- sha256('源|类型|目标') 前 32 位
  source_id        TEXT NOT NULL,
  target_id        TEXT NOT NULL,
  type             TEXT NOT NULL,
  provenance_inferred INTEGER NOT NULL DEFAULT 0, -- 1=推断来源（规则共现等）
  bridge_reason    TEXT,
  metadata_json    TEXT,
  created_seq      INTEGER,
  updated_seq      INTEGER,
  UNIQUE (source_id, type, target_id)
);
```

## 5. 后端问答顺着 MENTIONED_IN 拿到 chunk_id 以后，用它去 Azure 索引查原文时，按哪个字段查
结论：后端拿到 Neo4j 返回的 `chunk_id` 后，下一步不是按 filter 条件查 Azure，而是直接把这个值当成 Azure Search 文档主键 key 去 `get_document`，也就是按主键字段查，字段对应 `chunk_id`。

证据 1: Neo4j 的 `_Q_CHUNKS` 返回 `c.chunk_id AS chunk_id`
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:65-68`
```python
_Q_CHUNKS = (
    "CYPHER 25 MATCH (:Entity {scope: $scope, id: $id})-[:MENTIONED_IN]->"
    "(c:Chunk {scope: $scope}) RETURN c.chunk_id AS chunk_id LIMIT $limit"
)
```

证据 2: 调用 `_Q_CHUNKS` 后把结果收成 `chunk_ids`
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:295-313`
```python
async def chunks_by_entity(
    self, space: KnowledgeSpace, entity_id: str, limit: int = 8
) -> list[str]:
    if not await self._ensure():
        raise KnowledgeBackendError("图谱不可用")
    logger.info(
        "[Neo4j] 实体关联 chunk 调用 scope=%s entity=%s limit=%s",
        space.graph_scope,
        entity_id,
        limit,
    )
    rows = await self._query(
        _Q_CHUNKS, {"scope": space.graph_scope, "id": entity_id, "limit": limit}
    )
    chunk_ids = [str(r["chunk_id"]) for r in rows]
    logger.info(
        "[Neo4j] 实体关联 chunk 返回 count=%d ids=%s", len(chunk_ids), chunk_ids
    )
    return chunk_ids
```

证据 3: Service 层拿到 `chunk_ids` 后调用 `_retriever.get_chunks(space, chunk_ids)`
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:132-143`
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

证据 4: Azure 检索层 `get_chunks()` 直接走 `_lookup(client, ids, _SELECT)`
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\azure_search.py:228-243`
```python
async def get_chunks(
    self, space: KnowledgeSpace, chunk_ids: Sequence[str]
) -> list[KnowledgeHit]:
    ids = [c for c in dict.fromkeys(chunk_ids) if c]
    if not ids:
        return []
    client = await self._client(space.index_name)
    logger.info("[AISearch] 按 chunk 取回 index=%s ids=%s", space.index_name, ids)
    hits = await self._lookup(client, ids, _SELECT)
    logger.info(
        "[AISearch] 取回结果 index=%s requested=%d found=%d",
        space.index_name,
        len(ids),
        len(hits),
    )
    return hits
```

## 证据5
`_lookup()` 明确写的是“按主键直取文档”，调用 `client.get_document(key=chunk_id)`
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\azure_search.py:203-223`

```python
async def _lookup(
    self, client: SearchClient, ids: Sequence[str], select: list[str]
) -> list[KnowledgeHit]:
    """按主键直取文档: 不依赖 chunk_id 的 filterable 属性。"""

    async def _one(chunk_id: str) -> KnowledgeHit | None:
        try:
            doc = await asyncio.wait_for(
                client.get_document(key=chunk_id, selected_fields=select),
                self._timeout_s,
            )
        except ResourceNotFoundError:
            return None
        except Exception as exc:
            logger.warning(
                "[AISearch] 按主键取回失败 chunk_id=%s err=%s",
                chunk_id,
                getattr(exc, "message", None) or repr(exc),
            )
            raise KnowledgeBackendError("Azure AI Search 查询失败") from exc
        return _to_hit(doc)
```

## 6. 两条只读SQL（由你执行）
依据建表字段，kg_nodes 可直接全字段查；kg_edges 也可直接全字段查。

### 6.a 取5条Chunk节点
```sql
SELECT node_id, type, label, metadata_json, created_seq, updated_seq
FROM kg_nodes
WHERE type = 'Chunk'
LIMIT 5;
```

### 6.b 取5条mentioned_in边
```sql
SELECT edge_id, source_id, target_id, type, provenance_inferred, bridge_reason, metadata_json, created_seq, updated_seq
FROM kg_edges
WHERE type = 'mentioned_in'
LIMIT 5;
```

---
## 搜索命令记录（按 R3a 要求保留）
```
rg -n "kg_nodes|kg_edges|mentioned_in|Chunk|jp-poc|Azure|azure|upload.*doc|search_client|merge_or_upload|upload_documents|index_documen
rg -n "kg_nodes|kg_edges|mentioned_in|Chunk" C:\Users\234393\Desktop\jap-cycle-poc\kb_poc -g "*.py"
rg -n "upload_documents|merge_or_upload|index_documents|search_client|jp-poc|chunk_id|id\s*=\s*\"id\"\s*:\s*key=\[primary key" C
rg -n "_Q_CHUNKS|match_entities|subgraph|chunk_id|SearchClient|search\(|filter=|knowledge_search|azure" C:\Users\234393\Desktop\tap-ai-b
rg -n "kg_nodes|kg_edges|CREATE TABLE|sqlite3.connect|kg.db" C:\Users\234393\Desktop\kg_api -g "*.py"
rg -n "SearchClient|upload_documents|merge_or_upload|index_documents|chunk_id.*=.*hash|sha256|hexdigest\(\)\[\:|ChunkMetadata\(|metadata=ChunkMetadata|chunk_id=|document_version_id=" C:\Users\234393\De
rg -n "chunk_id.*=.*hash|sha256|hexdigest\(\)\[\:|ChunkMetadata\(|metadata=ChunkMetadata|chunk_id=|document_version_id=" C:\Users\234393\De
rg -n "CREATE TABLE\s+kg_nodes|CREATE TABLE\s+kg_edges|CREATE TABLE\s+kg_node_sources|CREATE TABLE\s+kg_edge_sources" C:\Users\234393\Desktop\jap-cycle-poc -g "*.sql"
```

---
## 核对表
| 编号 | 状态（完成/未找到/未做） | 证据所在的文件:行号 |
| ---- | ---- | ---- |
| 1 | 完成 | kb_poc\indexing\azure_search_store.py:93-106,170-183 ; kb_poc\models.py:22-46 ; kb_poc\ingestion\ingestor.py:243-278 |
| 2 | 完成 | kb_poc\kg\kg_extractor.py:68-70,194-219 ; kb_poc\kg\extractors\rule_extractor.py:9-10,91-121 |
| 3 | 完成 | kb_poc\ingestion\ingestor.py:243-245 ; kb_poc\kg\kg_extractor.py:68-70 |
| 4 | 完成 | kg_api\settings.py:24-31 ; kg_api\db.py:27-39 ; kb_poc\kg\stores\sqlite_schema.sql:5-26 |
| 5 | 完成 | tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\backends\neo4j_graph.py:65-68,295-313 ; ...\service.py:132-143 ; ...\azure_search.py:203-243 |
| 6 | 完成 | kb_poc\kg\stores\sqlite_schema.sql:5-26 |


---
## SQL执行记录（PowerShell sqlite3 只读查询）
```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc>
>> import sqlite3
>> conn = sqlite3.connect(r"file:C:\Users\234393\Desktop\kg_api\data\kg.db?mode=ro", uri=True)
>> cur = conn.cursor()
>> print("kg_nodes ---")
>> for r in cur.execute("SELECT node_id, type, label, metadata_json, created_seq, updated_seq FROM kg_nodes WHERE type = 'Chunk' LIMIT 5"):
>>     print(tuple(r))
>> print("kg_edges ---")
>> for r in cur.execute("SELECT edge_id, source_id, target_id, type, provenance_inferred, bridge_reason, metadata_json, created_seq, updated_seq FROM kg_edges WHERE type = 'mentioned_in' LIMIT 5"):
>>     print(tuple(r))
```

### 执行输出结果
```
kg_nodes ---
('74baf908182e', 'Chunk', '#15_SFDC.pptx / slide-6', '{"source_file": "#15_SFDC.pptx", "page_or_sheet": "slide-6", "cell_range": ""}', None, None)
('ff38653c715e', 'Chunk', '#15_SFDC.pptx / slide-10', '{"source_file": "#15_SFDC.pptx", "page_or_sheet": "slide-10", "cell_range": ""}', None, None)
('dc934914dbe7', 'Chunk', '#15_SFDC.pptx / slide-18', '{"source_file": "#15_SFDC.pptx", "page_or_sheet": "slide-18", "cell_range": ""}', None, None)
('e4ddb59a8ff5', 'Chunk', '#06_新契約システム概要.pptx / slide-4', '{"source_file": "#06_新契約システム概要.pptx", "page_or_sheet": "slide-4", "cell_range": ""}', None, None)
('baf401320588', 'Chunk', '#06_新契約システム概要.pptx / slide-28', '{"source_file": "#06_新契約システム概要.pptx", "page_or_sheet": "slide-28", "cell_range": ""}', None, None)
kg_edges ---
('e1b342d4aa03d634725e62cbca2e4308', 'System:Openframe', '74baf908182e', 'mentioned_in', 0, None, None, None, None)
('6f95126ba7f4bc392e409d8f8ec2604e', 'Product:被保険者情報', '74baf908182e', 'mentioned_in', 0, None, None, None, None)
('12922e4a1cdbdecf86ae963b208f81d4', 'Product:Life/J', '74baf908182e', 'mentioned_in', 0, None, None, None, None)
('f620982559095f99271ee559a21b472d', 'Process:無解約返戻金型医療保険', 'ff38653c715e', 'mentioned_in', 0, None, None, None, None)
('e7b2cd6ffd36feedf3eabf7a3cbdd9e0', 'Product:被保険者', 'ff38653c715e', 'mentioned_in', 0, None, None, None, None)


