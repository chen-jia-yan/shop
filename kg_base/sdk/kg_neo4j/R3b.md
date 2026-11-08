# R3b_reply.md
## 1. Neo4jGraphSink 建约束和建索引的 Cypher 原文
结论：Neo4jGraphSink 在初始化时通过 `_SCHEMA` 建 3 个唯一约束、1 个普通索引、1 个全文索引；如果提供了 `embedding_provider`，还会额外执行向量索引 `entity_embedding`。向量索引维度取 `provider.dimension`，相似度函数写死为 `cosine`。

### 证据1：schema Cypher 原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:58-66`
```python
_PREFIX = "CYPHER 25 "
_SCHEMA = (
    "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE (e.scope, e.id) IS UNIQUE",
    "CREATE CONSTRAINT chunk_key IF NOT EXISTS FOR (c:Chunk) REQUIRE (c.scope, c.chunk_id) IS UNIQUE",
    "CREATE CONSTRAINT document_key IF NOT EXISTS FOR (d:Document) REQUIRE (d.scope, d.document_id) IS UNIQUE",
    "CREATE INDEX entity_norm IF NOT EXISTS FOR (e:Entity) ON (e.scope, e.label_norm)",
    "CREATE FULLTEXT INDEX entity_label_ft IF NOT EXISTS FOR (e:Entity) "
    "ON EACH [e.label, e.aliases_text] OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk'}}",
)
```

### 证据2：向量索引 Cypher 原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:144-150`
```python
ENTITY_VECTOR_INDEX = "entity_embedding"
_MAX_NEIGHBORS = 8
_EMBED_BATCH = 64
_VECTOR_INDEX = (
    "CREATE VECTOR INDEX " + ENTITY_VECTOR_INDEX + " IF NOT EXISTS FOR (e:Entity) ON (e.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine'}}"
)
```

### 证据3：初始化何时建 schema / vector index
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:217-221`
```python
if ensure_schema:
    for stmt in _SCHEMA:
        self._run(stmt)
    if self._embedder is not None:
        self._run(_VECTOR_INDEX, dimensions=self._embedder.dimension)
```

---
## 2. Neo4jGraphSink.upsert() 写入 Entity / Chunk / 关系 / MENTIONED_IN 的 Cypher 原文，以及属性
结论：
- Document 节点写属性：`scope, document_id, source_file, doc_type`
- Chunk 节点写属性：`scope, chunk_id, document_id, source_file`
- Entity 节点写属性：`scope, id, type, label, label_norm, aliases, alias_norms, aliases_text`；若启用实体向量，还会额外写 `embedding, embedding_hash`
- 实体之间业务关系写属性：`doc_ids, chunk_ids, source, weight`
- `MENTIONED_IN` 关系本身没有额外属性，只是 `MERGE (e)-[:MENTIONED_IN]->(c)`
- `HAS_CHUNK` 关系也没有额外属性

### 证据1：写 Document / Chunk / HAS_CHUNK 的 Cypher
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:85-93`
```python
_WRITE_DOCUMENT = (
    "MERGE (d:Document {scope: $scope, document_id: $document_id}) "
    "SET d.source_file = $source_file, d.doc_type = $doc_type "
    "WITH d "
    "UNWIND $chunk_ids AS cid "
    "MERGE (c:Chunk {scope: $scope, chunk_id: cid}) "
    "SET c.document_id = $document_id, c.source_file = $source_file "
    "MERGE (d)-[:HAS_CHUNK]->(c)"
)
```

### 证据2：写 Entity / Chunk / MENTIONED_IN 的 Cypher
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:94-104`
```python
_WRITE_MENTIONS = (
    "UNWIND $rows AS row "
    "MERGE (e:Entity {scope: $scope, id: row.id}) "
    "SET e.type = row.type, e.label = row.label, e.label_norm = row.label_norm, "
    "e.aliases = row.aliases, e.alias_norms = row.alias_norms, e.aliases_text = row.aliases_text, "
    "e.doc_ids = CASE WHEN $document_id IN coalesce(e.doc_ids, []) THEN e.doc_ids "
    "ELSE coalesce(e.doc_ids, []) + $document_id END "
    "MERGE (c:Chunk {scope: $scope, chunk_id: row.chunk_id}) "
    "SET c.document_id = $document_id, c.source_file = $source_file "
    "MERGE (e)-[:MENTIONED_IN]->(c)"
)
```

### 证据3：写实体关系端点 Entity 节点属性的 Cypher
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:115-123`
```python
_REL_ENDPOINTS_MERGE = (
    "UNWIND $rels AS r "
    "MERGE (a:Entity {scope: $scope, id: r.src_id}) "
    "SET a.type = r.src_type, a.label = r.src_label, a.label_norm = r.src_norm, "
    "a.aliases = r.src_aliases, a.alias_norms = r.src_alias_norms, a.aliases_text = r.src_aliases_text "
    "MERGE (b:Entity {scope: $scope, id: r.dst_id}) "
    "SET b.type = r.dst_type, b.label = r.dst_label, b.label_norm = r.dst_norm, "
    "b.aliases = r.dst_aliases, b.alias_norms = r.dst_alias_norms, b.aliases_text = r.dst_aliases_text "
)
```

### 证据4：写实体之间业务关系的 Cypher
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:129-139`
```python
_REL_MERGE = (
    "MERGE (a)-[e:{rel}]->(b) "
    "ON CREATE SET e.doc_ids = [$document_id], e.chunk_ids = r.chunk_ids, e.source = r.source "
    "ON MATCH SET "
    "e.doc_ids = CASE WHEN $document_id IN coalesce(e.doc_ids, []) THEN e.doc_ids "
    "ELSE coalesce(e.doc_ids, []) + $document_id END, "
    "e.chunk_ids = (coalesce(e.chunk_ids, []) "
    "+ [x IN r.chunk_ids WHERE NOT x IN coalesce(e.chunk_ids, [])])[0..$max_chunk_ids], "
    "e.source = CASE WHEN r.rank < coalesce($ranks[e.source], 99) THEN r.source ELSE e.source END "
    "SET e.weight = size(e.doc_ids)"
)
```
### 证据5：写实体向量的 Cypher
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:159-162`
```python
_WRITE_EMBEDDINGS = (
    "UNWIND $rows AS r MATCH (e:Entity {scope: $scope, id: r.id}) "
    "SET e.embedding = r.vector, e.embedding_hash = r.hash"
)
```

### 证据6：upsert() 调用顺序原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:231-257`
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

### 证据7：Entity 属性来源 `_entity_props()` 原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:448-456`
```python
def _entity_props(ref: EntityRef) -> dict[str, Any]:
    aliases = [a for a in ref.aliases if a != ref.label]
    return {
        "label": ref.label,
        "label_norm": normalize_label(ref.label),
        "aliases": aliases,
        "alias_norms": list(dict.fromkeys(normalize_label(a) for a in aliases)),
        "aliases_text": " ".join(aliases),
    }
```

---
## 3. normalize_label 函数的完整原文
结论：`normalize_label` 不在 `_neo4j.py` 里定义，而是从 `tap_ingest_sdk.lexicon` 导入，完整原文如下。

证据：
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\lexicon\_model.py:27-38`
```python
_WS = re.compile(r"\s+")
_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")

def normalize_text(text: str) -> str:
    """匹配用归一化: NFKC + casefold + 空白折叠。"""
    return _WS.sub(" ", unicodedata.normalize("NFKC", text or "")).casefold().strip()

def normalize_label(label: str) -> str:
    """实体名归一化 (NFKC + 小写 + 去空白)，与查询端 `label_norm` 一致。"""
    return _WS.sub(" ", unicodedata.normalize("NFKC", label or "")).lower()
```

---
## 4. Entity 节点的 embedding 是怎么生成的：模型、环境变量 / 参数、维度
结论：
- Entity embedding 不是默认必写；只有 `Neo4jGraphSink` 传入 `embedding_provider` 时才写
- CLI 对应开关是 `--kg-embed-entities`
- 读取的配置是：`KB_EMBEDDING_BASE_URL`、`KB_EMBEDDING_API_KEY`、`KB_EMBEDDING_MODEL`、`KB_EMBEDDING_DIMENSIONS`
- 维度默认 `3072`
- README / 设计文档里明确举例模型是 `text-embedding-3-large`，3072 维

### 证据1：没有 embedder 就不写
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:259-263`
```python
def _embed_entities(self, ids: set[str]) -> None:
    """只为本次涉及的实体重算向量: 文本(含邻居)哈希未变的跳过; 失败只告警, 下次入库会重试。"""
    if self._embedder is None or not ids:
        return
```

### 证据2：Entity embedding 文本和写入逻辑
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:265-276`
```python
for rec in self._read(_READ_FOR_EMBEDDING, ids=sorted(ids)):
    text = embedding_text(rec["label"], rec["type"], rec["neighbors"])
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    if rec["hash"] != digest:
        todo.append({"id": rec["id"], "text": text, "hash": digest})
for i in range(0, len(todo), _EMBED_BATCH):
    batch = todo[i : i + _EMBED_BATCH]
    vectors = self._embedder.embed([t["text"] for t in batch])
    rows = [
        {"id": t["id"], "hash": t["hash"], "vector": list(v)} for t, v in zip(batch, vectors)
    ]
    self._run(_WRITE_EMBEDDINGS, rows=rows)
```

### 证据3：构建 embedder、读取环境变量
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\cli\main.py:340-348`
```python
def _build_entity_embedder() -> CopilotEmbeddingProvider:
    cfg = _require_embedding_env("--kg-embed-entities")
    dimension = int(os.getenv("KB_EMBEDDING_DIMENSIONS")) or 3072
    return CopilotEmbeddingProvider(
        base_url=cfg["KB_EMBEDDING_BASE_URL"],
        api_key=cfg["KB_EMBEDDING_API_KEY"],
        model=cfg["KB_EMBEDDING_MODEL"],
        dimension=dimension,
    )
```

### 证据4：CLI 校验这些环境变量必须存在
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\cli\main.py:313-319`
```python
def _require_embedding_env(purpose: str) -> dict[str, str]:
    names = ("KB_EMBEDDING_BASE_URL", "KB_EMBEDDING_API_KEY", "KB_EMBEDDING_MODEL")
    cfg = {name: os.getenv(name) for name in names}
    missing = [name for name, value in cfg.items() if not value]
    if missing:
       raise click.UsageError(f"{purpose} requires {', '.join(missing)} to be set.")
    return cfg
```

#### 证据5：默认维度配置
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_internal\config.py:39-42`
```python
# Embedding
embedding_enabled: bool = True
embedding_model: str | None = None
embedding_dimensions: int = 3072
```

#### 证据6：README 的 Neo4j 说明
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\README.md:91-94`
```
- `--kg-embed-entities`: 生成实体向量并建 Neo4j 向量索引 `entity_embedding`（需 `KB_EMBEDDING_*`，Neo4j ≥ 5.11）
- 多语言词典覆盖简/繁中文、日文、英文、泰文、马来文，同一概念合并为一个实体；泰/马/英词条待业务审核。
- 重新摄取与删除会撤销该文档贡献的关系并清理其 Chunk / Document；升级后需按 scope 清空 Neo4j 重新摄取。设计见 `docs/设计-Neo4j业务关系扩展.md`。
- 向量维度默认 3072（`KB_EMBEDDING_DIMENSIONS`，Azure 与 Neo4j 共用）；改维度需新建索引。
```

#### 证据7：设计文档对模型和维度的说明
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\docs\计划-KG增量与向量迁移.md:87-89`
```markdown
### P4 实体向量（约 1.5 天）- ✅ 已完成
> 实现: `Neo4jGraphSink(embedding_provider=...)`; 写入 `Entity.embedding` / `embedding_hash`, 并建 `entity_embedding` 向量索引 (cosine, 维度取自 prov.
```

---
## 5. LLM_RELATION_MAP 的完整原文，以及 ALLOWED_RELATIONS 的原文
### 证据1：ALLOWED_RELATIONS 完整原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_kg_schema.py:86-94`
```python
# 关系类型 -> 允许的 (源实体类型, 目标实体类型)
ALLOWED_RELATIONS: dict[str, frozenset[tuple[str, str]]] = {
    "NEXT": _pairs(_FLOW_OR_PROCESS, _FLOW_OR_PROCESS),
    "HANDLED_BY": _pairs(_FLOW_OR_PROCESS, (ROLE,)),
    "PART_OF": _pairs((_FLOW_OR_PROCESS, DOCUMENT, DATA, SYSTEM, PRODUCT, CONCEPT, CHANNEL), (STAGE, PROCESS, SYSTEM, PRODUCT)),
    "CONTAINS": _pairs((STAGE, PROCESS, SYSTEM, PRODUCT, DOCUMENT, DATA, CONCEPT), _ENTITIES),
    "USES": _pairs((ROLE, PROCESS, STEP, ACTION, SYSTEM, PRODUCT, CHANNEL), (SYSTEM, DATA, DOCUMENT, CHANNEL, PRODUCT)),
    "REQUIRES": _pairs((PROCESS, STEP, ACTION, PRODUCT, SYSTEM, DOCUMENT), (DATA, DOCUMENT, SYSTEM, PROCESS, CONCEPT)),
}
```

### 证据2：LLM_RELATION_MAP 完整原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_kg_schema.py:101-110`
```python
# LLM 输出的自由关系名 -> (规范关系名, 是否需要交换端点)。未列出的关系不入图。
LLM_RELATION_MAP: dict[str, tuple[str, bool]] = {
    "包含": ("CONTAINS", False),
    "属于": ("PART_OF", False),
    "使用": ("USES", False),
    "依赖": ("REQUIRES", False),
    "前置步骤": ("NEXT", False),
    "执行": ("HANDLED_BY", True),
    **{name: (name, False) for name in ALLOWED_RELATIONS},
}
```

---
## 6. 仓库里关于 Neo4j 版本要求的说明；以及代码里有没有用到 CYPHER 25 或 SEARCH 子句
### 结论
- README 里明确写了: 实体向量索引需要 Neo4j ≥ 5.11
- 代码里明确使用了 `CYPHER 25` 前缀
- 在本次限定范围与 README / docs 搜索结果中，未找到 `SEARCH` 子句的使用
- 本次在仓库里未找到 `docker-compose` 中的 Neo4j 镜像版本说明

### 证据1：README 的版本要求
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\README.md:91-94`
```
- `--kg-embed-entities`: 生成实体向量并建 Neo4j 向量索引 `entity_embedding`（需 `KB_EMBEDDING_*`，Neo4j ≥ 5.11）
- 多语言词典覆盖简/繁中文、日文、英文、泰文、马来文，同一概念合并为一个实体；泰/马/英词条待业务审核。
- 重新摄取与删除会撤销该文档贡献的关系并清理其 Chunk / Document；升级后需按 scope 清空 Neo4j 重新摄取。设计见 `docs/设计-Neo4j业务关系扩展.md`。
- 向量维度默认 3072（`KB_EMBEDDING_DIMENSIONS`，Azure 与 Neo4j 共用）；改维度需新建索引。
```

### 证据2：代码里使用 CYPHER 25
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\_neo4j.py:58`
```python
_PREFIX = "CYPHER 25 "
```

### 证据3：README 范围内没找到 docker-compose / neo4j 镜像版本说明；代码没找到 SEARCH 子句
搜索命令：
```
rg -n "neo4j|Neo4j|CYPHER 25|SEARCH " C:\Users\234393\fwd-tap-common\fwd-tap-ingest -g "*.{md,yml,yaml,py}"
rg -n "SEARCH " C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks -g "*.py"
```
搜索结果结论：
- `docker-compose`：未找到
- `SEARCH` 子句：未找到

### 搜索命令记录
```
rg -n "Neo4jGraphSink|entity_label_ft|entity_embedding|CREATE CONSTRAINT|CREATE FULLTEXT INDEX|CREATE VECTOR INDEX|CYPHER 25|SEA
rg -n "neo4j|Neo4j|CYPHER 25|SEARCH " C:\Users\234393\fwd-tap-common\fwd-tap-ingest -g "*.{md,yml,yaml,py}"
rg -n "def normalize_label" C:\Users\234393\fwd-tap-common\fwd-tap-ingest -g "*.py"
rg -n "embedding_provider|--kg-embed-entities|KB_EMBEDDING_|Neo4j >= 5.11|5.11|vector.dimensions|vector.similarity_function" C:\
rg -n "SEARCH " C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks -g "*.py"
```

---
## 核对表
| 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
| ---- | ---- | ---- |
| 1 | 完成 | `_neo4j.py:58-66,144-150,217-221` |
| 2 | 完成 | `_neo4j.py:85-104,115-139,159-162,231-257,448-456` |
| 3 | 完成 | `lexicon\_model.py:27-38` |
| 4 | 完成 | `_neo4j.py:259-276` ; `cli\main.py:313-348` ; `_internal\config.py:39-42` ; `README.md:91-94` ; `docs\计划-KG增量与向量迁移.md:87-89` |
| 5 | 完成 | `_kg_schema.py:86-110` |
| 6 | 完成 | `README.md:91-94` ; `_neo4j.py:58` ; 搜索命令见正文（docker-compose / SEARCH 未找到） |

---
## 附：Neo4j 组件查询语句与结果
Cypher语句：
```cypher
CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition
```
查询结果：
| name | versions | edition |
| ---- | ---- | ---- |
| "Neo4j Kernel" | ["2026.10.1"] | "community" |
| "Cypher" | ["5", "25"] | "" |

