# knowledge/settings.py 全文
```python
"""知识库插件配置（环境变量前缀 ``TAP_AI_KB_``）。

配置类由插件自己持有，``config/settings.py`` 不感知；读取同一个 ``.env``
(主 Settings 设置了 ``extra="ignore"``，不会冲突)。
"""
from __future__ import annotations
from typing import Literal
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from tap_ai.config.settings import env_file_path

DEFAULT_DECIDE_RULE = (
    "回答需要依据公司内部业务资料时为 true，例如保险产品、条款、理赔/核保/保全流程、"
    "业务规则、内部规范、测试周期业务文档；编程/代码、通用常识、闲聊、纯附件分析、"
    "实时外部信息为 false。"
)

class KnowledgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAP_AI_KB_",
        env_file=env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    # saas_id -> index 名称映射 (JSON)，如 {"hk":"hk-kb-chunk-tap-dit"}; 未列出的租户不启用知识库。
    indexes: dict[str, str] = {}
    azure_search_endpoint: str = ""
    # 查询密钥（query key）。
    azure_search_key: SecretStr = SecretStr("")
    vector_field: str = "content_vector"
    # LiteLLM 上的 embedding 模型别名；必须与摄取时一致（3072 维）。
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    # 为空时不启用图谱；本地联调如 bolt://localhost:7687。
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    # Community 只有一个用户库。
    neo4j_database: str = "neo4j"
    neo4j_timeout_s: float = 3.0
    # 实体向量匹配（需要 SDK 写入实体 embedding）。
    kg_entity_vector: bool = False
    kg_entity_min_score: float = 0.75
    decide_rule: str = DEFAULT_DECIDE_RULE
    tools_policy: Literal["decided", "always"] = "decided"
    # 超时即转为通用回答；必须小于 core 的 TAP_AI_REACT_EXTENSION_TIMEOUT_S。
    prefetch_timeout_s: float = 10.0
    prefetch_max_chars: int = 3000
    top_k: int = 5
    max_alternates: int = 3
    candidate_multiplier: int = 4
    rrf_k: int = 60
    # 0 表示不过滤（待 Golden Set 标定）。
    min_vector_score: float = 0.0
    snippet_chars: int = 400
    expand_chars: int = 1500
    kg_max_edges: int = 10
    # 子图允许遍历的业务关系类型（白名单）。
    kg_relation_types: tuple[str, ...] = ("NEXT", "HANDLED_BY", "PART_OF", "REQUIRES")
    synonyms_path: str = ""
    allowed_filter_fields: tuple[str, ...] = (
        "source_file",
        "doc_type",
        "product_name",
        "language",
        "cycle_stage",
        "content_type",
    )
    max_index_clients: int = 64
    index_cache_ttl_s: int = 300
```

# plugin.py 中判断“知识库是否启用”、读取 kg_entity_vector、构造 Azure 检索对象的原文
```python
def build(settings: Settings) -> KnowledgeExtension | None:
    """未启用或缺少凭据时返回 None；本函数不发起任何网络调用。"""
    kb = KnowledgeSettings()
    if not kb.enabled:
        return None
    key = kb.azure_search_key.get_secret_value()
    if not kb.azure_search_endpoint or not key:
        logger.warning(
            "TAP_AI_KB_ENABLED=true 但缺少 Azure Search endpoint/key，知识库未启用"
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
    embedding = LiteLLMEmbedding(
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
            password=kb.neo4j_password.get_secret_value(),
            database=kb.neo4j_database,
            timeout_s=kb.neo4j_timeout_s,
            entity_vector=kb.kg_entity_vector,
            entity_min_score=kb.kg_entity_min_score,
            relation_types=kb.kg_relation_types,
        )
        closers.append(graph)
```

> 已确认事实：
> - 当前通过 `kb.enabled` 控制知识库是否启用。
> - 当前构造 `AzureSearchRetriever` 时直接传 `kb.azure_search_endpoint` 和 `kb.azure_search_key`。
> - 当前 Neo4j 图谱对象读取 `kb.kg_entity_vector`。

# backends/azure_search.py 中 endpoint / key 来源、_client 原文
```python
def __init__(
    self,
    *,
    endpoint: str,
    key: str,
    vector_field: str = "content_vector",
    candidate_multiplier: int = 4,
    rrf_k: int = 60,
    min_vector_score: float = 0.0,
    allowed_filter_fields: Sequence[str] = (),
    max_clients: int = 64,
    exists_ttl_s: float = 300.0,
    timeout_s: float = 8.0,
) -> None:
    self._endpoint = endpoint
    self._credential = AzureKeyCredential(key)
    self._vector_field = vector_field
    self._multiplier = max(1, candidate_multiplier)
    self._rrf_k = rrf_k
    self._min_vector_score = min_vector_score
    self._allowed = tuple(allowed_filter_fields)
    self._max_clients = max(1, max_clients)
    self._exists_ttl = exists_ttl_s
    self._timeout_s = timeout_s
    self._clients: OrderedDict[str, SearchClient] = OrderedDict()
    self._exists_cache: dict[str, tuple[bool, float]] = {}

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
   self._clients[index_name] = client
   while len(self._clients) > self._max_clients:
      _, evicted = self._clients.popitem(last=False)
      try:
         await evicted.close()
      except Exception:
         logger.debug("关闭被淘汰的 SearchClient 失败", exc_info=True)
   ```

> 已确认事实：
> - 当前 endpoint / key 是在 `AzureSearchRetriever(...)` 初始化时传入的。
> - 当前 `_client` 只按 `index_name` 缓存 `SearchClient`。
> - 当前 `SearchClient` 用的是单一的 `self._endpoint` 与 `self._credential`。

---
## 4. tools.py 关系枚举、prompts.py 中 RELATION_LEGEND、neo4j_graph.py 中 DEFAULT_RELATION_TYPES 原文
### 4.1 tools.py
```json
"items": {
    "type": "string",
    "enum": ["NEXT", "HANDLED_BY", "PART_OF", "REQUIRES"],
},
"description": (
    "只返回这些关系: NEXT=流程下一步，HANDLED_BY=步骤由哪个角色负责，"
    "PART_OF=步骤所属阶段，REQUIRES=需要的材料/条件; 不填返回全部"
),
```

### 4.2 prompts.py
```python
RELATION_LEGEND = """(关系说明: NEXT=流程下一步，HANDLED_BY=由该角色负责，PART_OF=所属阶段，REQUIRES=需要的材料/条件)"""
```

### 4.3 neo4j_graph.py
```python
# 子图只遍历业务关系; MENTIONED_IN / HAS_CHUNK 等结构性关系不进入子图。
DEFAULT_RELATION_TYPES = ("NEXT", "HANDLED_BY", "PART_OF", "REQUIRES")
```

> 已确认事实：
> - 这三处目前都还在手写关系名字符串。
> - K2b 要求后续统一改为从 SDK 的 `TRAVERSABLE_RELATIONS` / `RELATION_ZH` 读取。

---
## 5. sdk_ingest.py 中两处 jp-poc 检查、_contains_forbidden_index 定义、Neo4j 配置不全时报错原文
### 5.1 _contains_forbidden_index 定义
```python
def _contains_forbidden_index(value: str) -> bool:
    return "jp-poc" in _normalize_index_name(value)
```

### 5.2 写入时检查 jp-poc
```python
if _contains_forbidden_index(index_name):
    return IngestOutcome(
        succeeded=False,
        error_code="forbidden_index",
        error_message="禁止写入该索引",
    )
```

### 5.3 启动时检查映射里是否含 jp-poc
```python
if any(_contains_forbidden_index(index_name) for index_name in kb.indexes.values()):
    raise RuntimeError("禁止写入 jp-poc 索引")
```

### 5.4 Neo4j 配置不全时报错原文
```python
password = kb.neo4j_password.get_secret_value()
if getattr(settings, "library_kb_graph_enabled", False):
    if not kb.neo4j_uri or not kb.neo4j_user or not password:
        raise RuntimeError("图谱配置不完整")
try:
    from neo4j import GraphDatabase
except ImportError as exc:
    raise RuntimeError("图谱配置不完整") from exc
shared_driver = GraphDatabase.driver(
    kb.neo4j_uri,
```

> 已确认事实：
> - 当前 `_contains_forbidden_index()` 不是“完全相等”，而是只要归一化字符串里包含 `jp-poc` 就算命中。
> - 当前有两处 jp-poc 检查：
>   i. 单次写入前检查
>   ii. 启动时扫描整个映射并直接报错
> - 当前图谱开关读取方式是 `getattr(settings, "library_kb_graph_enabled", False)`。
> - 当前只要开关为真，但 `neo4j_uri` / `neo4j_user` / `password` 任一缺失，就直接报 `RuntimeError("图谱配置不完整")`。

---
## 6. config/settings.py 中 library_kb_graph_enabled 原文
```python
# 入库时是否同时写知识图谱（K9 使用）。
library_kb_graph_enabled: bool = Field(default=False)
```

> 已确认事实：
> - 当前默认值是 `False`。
> - K2b 要求把默认值改为 `True`，并同步修改注释。

---
## 7. spaces.py 中 KnowledgeSpace 的定义原文
> 这里 spaces.py 里直接出现的是 `KnowledgeSpaceResolver.resolve()` 返回 `KnowledgeSpace(...)` 的代码；当前文件内没有 `KnowledgeSpace` 类定义，它是从 `tap_ai.contracts.knowledge` 引入的。

### 7.1 spaces.py 当前相关原文
```python
class KnowledgeSpaceResolver:
    def __init__(self, indexes: Mapping[str, str]) -> None:
        resolved: dict[str, str] = {}
        for saas_id, index in indexes.items():
            key = saas_id.strip().lower()
            name = index.strip().lower()
            if not _SAFE_SAAS.fullmatch(key):
                raise ValueError(f"知识库 saas_id 非法: {saas_id!r}")
            if not _SAFE_INDEX.fullmatch(name):
                raise ValueError(f"知识库 index 名称非法: {index!r}")
            resolved[key] = name
        self._indexes = resolved

    def resolve(self, tenant: TenantScope) -> KnowledgeSpace | None:
        # tenant 来自会话落库值; 缺失或未配置 -> 本请求不启用知识库。
        saas_id = (tenant.saas_id or "").strip().lower()
        index = self._indexes.get(saas_id)
        if index is None:
            return None
        return KnowledgeSpace(index_name=index, graph_scope=index)
```

### 7.2 当前可确认的返回形态
```python
return KnowledgeSpace(index_name=index, graph_scope=index)
```

> 已确认事实：
> - 当前 `KnowledgeSpaceResolver` 只处理 `saas_id -> index_name`。
> - 当前返回的 `KnowledgeSpace` 只传了 `index_name` 和 `graph_scope`。
> - K2b 要求后续在 `KnowledgeSpace` 上追加 `search_endpoint`、`search_key` 两个字段，并让 resolver 根据租户覆盖值来填充。

---
## 当前理解与边界
### 已确认事实
1. 当前知识库问答启用条件仍依赖 `KnowledgeSettings.enabled`。
2. 当前 Azure Search endpoint / key 是全局单值，没有租户级覆盖。
3. 当前关系名单在 `settings.py`、`tools.py`、`prompts.py`、`neo4j_graph.py` 中都存在手写字符串。
4. 当前 `sdk_ingest.py` 对 jp-poc 既有“启动时全局禁止”，又有“写入时禁止”。
5. 当前 `library_kb_graph_enabled` 默认值还是 `False`。
6. 当前 `KnowledgeSpaceResolver` 只返回 `index_name` / `graph_scope`，还不携带 Azure endpoint / key。

### 我的判断
1. K2b 的核心不是单点修补，而是把“知识库是否启用”“关系名单来源”“Azure 多租户配置”“禁止写入索引名单”“图谱写入默认行为”这几块同时重构到新规则下。
2. 这次最敏感的点会在：
    - `KnowledgeSpace` / `KnowledgeSpaceResolver` 的契约变动
    - `AzureSearchRetriever` 的客户端缓存逻辑变动
    - `sdk_ingest.py` 中禁止写入名单和图谱初始化逻辑变动
3. 后续动手时必须严格只改 `k2b.md` 允许的文件，并且每改一个文件都要看 `git diff --stat` 和 `git diff -w --stat`，不能顺手扩改。