# R3c 只读排查报告
说明: 本报告仅基于静态代码阅读；未修改任何文件、未读取 `.env`、未连接任何外部服务。找不到的项明确写“未找到”，并附搜索依据。

## 1. 读取“租户 → 索引名映射”配置的所有代码位置
### 1.1 配置定义位置
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:21-31`
```python
class KnowledgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAP_AI_KB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    # saas_id → index 名称映射 (JSON), 如 {"hk":"hk-kb-chunk-tap-dit"}; 未列出的租户不启用知识库。
    indexes: dict[str, str] = {}
```

结论：
- 这里定义了“租户 → 索引名映射”配置，字段名是 `KnowledgeSettings.indexes`
- 这是配置定义，本身不做读写业务数据

### 1.2 知识检索/图谱读取链路：构造 resolver
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:23-35`
```python
def build(settings: Settings) -> KnowledgeExtension | None:
    """未启用或缺少凭据时返回 None; 本函数不发起任何网络调用。"""
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
```

结论：
- 这里读取 `kb.indexes` 并交给 `KnowledgeSpaceResolver`
- 这是只读位置，用于后续查询时把租户解析成 index / graph_scope
- 这一段本身不写入 Azure index，也不写入 Neo4j

### 1.3 映射解析逻辑：租户 → index / graph_scope
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\spaces.py:20-39`
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
        # tenant 来自会话落库值; 缺失或未配置 → 本请求不启用知识库。
        saas_id = (tenant.saas_id or "").strip().lower()
        index = self._indexes.get(saas_id)
        if index is None:
            return None
        return KnowledgeSpace(index_name=index, graph_scope=index)
```

结论：
- 这里真正把租户映射成 `KnowledgeSpace(index_name=index, graph_scope=index)`
- 这是只读解析逻辑
- 重要事实：Neo4j scope 与 Azure index 名称相同，都是 `index`
- 这一段本身不写数据，只负责解析和返回空间对象

### 1.4 检索扩展运行时读取映射结果
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\extension.py:72-83`
```python
async def enabled_for(self, tenant: TenantScope) -> bool:
    space = self._resolver.resolve(tenant)
    if space is None:
        return False
    now = time.monotonic()
    cached = self._enabled_cache.get(space.index_name)
    if cached is not None and cached[1] > now:
        return cached[0]
    # exists 内部已按 index 缓存并区分 404 / 故障 TTL; 这里只做短缓存防抖。
    ok = await self._service.exists(space)
    self._enabled_cache[space.index_name] = (ok, now + _TIMEOUT_TTL_S)
    return ok
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\extension.py:97-106`
```python
space = self._resolver.resolve(req.tenant)
query = req.decision.query.strip() or req.user_content
if space is None:
    return ContextContribution(
        system_text=GENERAL_ANSWER, hide_tools=tools_hidden
    )
try:
    outcome = await asyncio.wait_for(
        self._service.search(space, query),
        self._settings.prefetch_timeout_s,
    )
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\extension.py:144-157`
```python
space = self._resolver.resolve(tenant)
if space is None:
    return []
out: list[dict[str, Any]] = []
for entry in tool_trace:
    if entry.get("tool") != SEARCH_KB and entry.get("tool") not in TOOL_NAMES:
        continue
    via = "tool" if entry.get("tool") == SEARCH_KB else "expand"
    for ref in entry.get("source_refs") or []:
        head, sep, chunk_id = str(ref).rpartition("@")
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\tools.py:53-57`
```python
def _space(self, ctx: ToolContext) -> KnowledgeSpace | None:
    tenant = ctx.tenant
    if not isinstance(tenant, TenantScope):
        return None
    return self._resolver.resolve(tenant)
```

结论：
- 这些位置都依赖 `resolver.resolve(...)` 读取映射结果
- 用途是查询/图谱读取/工具执行前的数据空间定位
- 这些位置全部属于只读；没有新增、更新、删除 Azure index 或 Neo4j 数据的代码

### 1.5 后端入库链路读取映射配置
文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:221-230`
```python
kb = KnowledgeSettings()
key = kb.azure_search_key.get_secret_value()
if not kb.indexes or not kb.azure_search_endpoint or not key:
    raise RuntimeError("入库配置不完整: 缺少索引映射或 Azure 配置")

invalid_indexes = [index_name for index_name in kb.indexes.values() if not index_name.strip()]
if invalid_indexes:
    raise RuntimeError("入库配置不完整: 索引映射值无效")

if any(_contains_forbidden_index(index_name) for index_name in kb.indexes.values()):
    raise RuntimeError("禁止写入 jp-poc 索引")
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:303-307`
```python
adapter = SdkIngestAdapter(
    mode="azure",
    index_resolver=lambda saas_id: kb.indexes.get(saas_id),
    sinks_factory=_sinks_factory,
    index_guard=_ensure_index_exists,
)
```

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:69-87`
```python
if self._mode == "azure":
    resolved = self._index_resolver(saas_id)
    if resolved is None:
        return IngestOutcome(
            succeeded=False,
            error_code="no_index",
            error_message="该租户未配置索引",
        )
    index_name = resolved
    if _contains_forbidden_index(index_name):
        return IngestOutcome(
            succeeded=False,
            error_code="forbidden_index",
            error_message="禁止写入该索引",
        )
    if self._index_guard is not None:
        guard_outcome = self._index_guard(index_name)
        if guard_outcome is not None:
            return guard_outcome
```

结论：
- 这里也读取了 `kb.indexes`
- 但和前面的检索链路不同，这里是会写入的位置：它先根据租户解析 index，再把数据交给 sink 执行入库
- 这段本身是“解析 + 守卫”，真正写动作发生在 sink 内部，但这是明确的写入链路入口

---

## 2. 第 1 条中“会写入”的位置，以及 key= `jp` 时会写到哪里、写什么
### 2.1 明确属于写入链路的位置
本次在 `tap-ai-backend` 范围内，发现第 1 条里明确属于“会写入”的只有这一组：
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
    if shared_driver is not None:
        sinks.append(
            Neo4jGraphSink(
                uri=kb.neo4j_uri,
                user=kb.neo4j_user,
                ******
                scope=index_name,
                database=kb.neo4j_database,
                driver=shared_driver,
            )
        )
    return tuple(sinks)
```

结论：
- Azure sink 写入目标：`index_name=index_name`
- Neo4j sink 写入目标：`scope=index_name`
- 所以只要某个租户映射到了某个 index 名称，Azure index 和 Neo4j scope 都会用同一个值

### 2.2 当 key 为 `jp` 时，写到哪个 index / scope
已确认事实：
- 后端代码里没有把 `jp` 硬编码映射成具体值
- 它是通过 `kb.indexes.get(saas_id)` 从配置读取

依据: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:303-307`
```python
adapter = SdkIngestAdapter(
    mode="azure",
    index_resolver=lambda saas_id: kb.indexes.get(saas_id),
    sinks_factory=_sinks_factory,
    index_guard=_ensure_index_exists,
)
```

因此结论：
- 当 key 为 `jp` 时，写到的 Azure index = `kb.indexes["jp"]`
- 当 key 为 `jp` 时，写到的 Neo4j scope = `kb.indexes["jp"]`
- 由于本次禁止读取 `.env`，所以具体字符串值未读取，不能推测

### 2.3 key= `jp` 时会执行什么写操作
后端本仓范围内已确认的动作：
- 构造 `AzureAISearchSink(index_name=kb.indexes["jp"])`
- 若 `library_kb_graph_enabled=True`，再构造 `Neo4jGraphSink(scope=kb.indexes["jp"])`
- 然后把文件交给 `TapIngestClient(..., sinks=sinks)` 执行入库

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:112-123`
```python
with tempfile.TemporaryDirectory(prefix="tap_ai_kb_ingest_") as temp_dir:
    sinks = self._sinks_factory(index_name)
    if self._mode == "memory" and not sinks:
        sinks = (MemorySink(),)
    client = TapIngestClient(
        parser_registry=ParserRegistry.default(),
        chunk=DefaultChunker(),
        sinks=sinks,
        work_dir=temp_dir,
        )
        report = client.ingest([source])

结论：
- 在 tap-ai-backend 本仓静态范围里，能确认的是：会把文档入到该 index，并在图谱开关开启时同步写该 scope 的图谱数据
- 更细的“写哪些节点/边/字段”属于 SDK 内部实现，不在本题这个后端仓范围里展开

3. TAP_AI_KB_KG_RELATION_TYPES 应该怎么写，才能被 KnowledgeSettings.kg_relation_types 正确读成 6 个值
3.1 KnowledgeSettings 完整类定义
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:21-76

```python
class KnowledgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAP_AI_KB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    # saas_id → index 名称映射 (JSON，如 {"hk":"hk-kb-chunk-tap-dit"}; 未列出的租户不启用知识库。
    indexes: dict[str, str] = {}
    azure_search_endpoint: str = ""
    # 查询密钥 (query key)。
    azure_search_key: SecretStr = SecretStr("")
    vector_field: str = "content_vector"
    # LiteLLM 上的 embedding 模型别名；必须与摄取时一致 (3072 维)。
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    # 为空时不启用图谱；本地联调如 bolt://localhost:7687。
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    # Community 只有一个用户库。
    neo4j_database: str = "neo4j"
    neo4j_timeout_s: float = 3.0
    # 实体向量匹配 (需要 SDK 写入实体 embedding)。
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
    # 表示不过滤 (待 Golden Set 标定)。
    min_vector_score: float = 0.0
    snippet_chars: int = 400
    expand_chars: int = 1500
    kg_max_edges: int = 10
    # 子图允许遍历的业务关系类型 (白名单)。
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

3.2 是否存在 field_validator / 其他解析逻辑
搜索结果: 未找到

搜索命令:
```bash
rg -n "class KnowledgeSettings|field_validator|model_validator|validator" C:\Users\234393\Desktop\tap-ai-backend\src\tap_
```

结论:
- KnowledgeSettings 里没有 field_validator
- 也没有为 kg_relation_types 单独写自定义解析逻辑

3.3 后端在哪里读取 kg_relation_types
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:60-69
```python
graph = Neo4jKnowledgeGraph(
    uri=kb.neo4j_uri,
    user=kb.neo4j_user,
    database=kb.neo4j_database,
    timeout_s=kb.neo4j_timeout_s,
    entity_vector=kb.kg_entity_vector,
    entity_min_score=kb.kg_entity_min_score,
    relation_types=kb.kg_relation_types,
)
```

结论:
- kg_relation_types 会直接作为 relation_types 传给 Neo4jKnowledgeGraph

3.4 应该怎么写 .env
我的判断（基于已读代码）：
- 由于字段类型是 tuple[str, ...]
- 同时代码里没有自定义 validator 去拆逗号字符串
- pydantic-settings 对复杂类型环境变量通常按 JSON 解析
- 所以最稳妥、与当前定义最匹配的写法应为 JSON 数组字符串，不是裸逗号串

可直接写进 .env 的示例：
```env
TAP_AI_KB_KG_RELATION_TYPES=["NEXT","HANDLED_BY","PART_OF","CONTAINS","USES","REQUIRES"]
```

这行的目标结果：
- KnowledgeSettings.kg_relation_types 读成 6 个值：`("NEXT", "HANDLED_BY", "PART_OF", "CONTAINS", "USES", "REQUIRES")`

4. library_kb_graph_enabled 在哪里定义、默认值是什么、在哪里被读取
4.1 定义位置与默认值
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:259-260
```python
# 入库时是否同时写知识图谱（K9 使用）。
library_kb_graph_enabled: bool = Field(default=False)


结论:
- 定义位置: `tap_ai.config.settings.Settings`
- 默认值: False

4.2 被读取的位置
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:236-247
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
        auth=(kb.neo4j_user, password),
    )
```

结论:
- 这里读取 library_kb_graph_enabled
- 它决定是否创建 Neo4j driver，也就决定后面是否追加 Neo4jGraphSink

4.3 读取后的实际效果
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:290-300
```python
if shared_driver is not None:
    sinks.append(
        Neo4jGraphSink(
            uri=kb.neo4j_uri,
            user=kb.neo4j_user,
            ******,
            scope=index_name,
            database=kb.neo4j_database,
            driver=shared_driver,
        )
    )
```

结论:
- library_kb_graph_enabled=False：只会有 Azure sink
- library_kb_graph_enabled=True：会额外追加 Neo4jGraphSink

5. 后端入库链路（sdk_ingest.py）构造 Neo4jGraphSink 时传了哪些参数；打开大模型关系抽取是否只需 KB_KG_LLM_ENABLED=1

5.1 Neo4jGraphSink 传入参数
文件: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:292-299
```python
Neo4jGraphSink(
    uri=kb.neo4j_uri,
    user=kb.neo4j_user,
    ******,
    scope=index_name,
    database=kb.neo4j_database,
    driver=shared_driver,
)
```

已确认参数:
- uri=kb.neo4j_uri
- user=kb.neo4j_user
- scope=index_name
- database=kb.neo4j_database
- driver=shared_driver

说明:
- 中间有一行被查看工具脱敏成 ******
- 按参数位置看，这是密码参数，但我这里只按工具可见事实写，不臆造行文

5.2 后端代码里是否直接控制 LLM 关系抽取开关
已确认事实:
- tap-ai-backend 的 sdk_ingest.py 里没有出现 KB_KG_LLM_ENABLED
- 也没有调用 llm_enabled()

搜索结果: 未找到

搜索命令:
```bash
rg -n "KB_KG_LLM_ENABLED|llm_enabled" C:\Users\234393\Desktop\tap-ai-backend -g "*.py"
```

5.3 SDK 中 llm_enabled() 原文依据
文件: C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\kg_llm_extract.py:35-61
```python
LLM_ENABLED_ENV = "KB_KG_LLM_ENABLED"
MAX_PROMPT_CHARS = 30000
_MAX_LABEL = 80
_LEXICON_TYPES = (STAGE, ROLE, ACTION)
_TRUTHY = {"1", "true", "yes", "on"}

def llm_enabled(env: dict[str, str] | None = None) -> bool:
    """`KB_KG_LLM_ENABLED` 是否为开启状态（默认关闭）。"""
    value = (env if env is not None else os.environ).get(LLM_ENABLED_ENV, "0")
    return value.strip().lower() in _TRUTHY
```

5.4 SDK 里何时会启用 LLM 关系抽取
文件: C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\cli\main.py:186-193
```python
relation_extractor: Any | None = DefaultRelationExtractor(cooccurrence_roles=kg_cooccurrence_roles)
if no_kg_relations:
    relation_extractor = None
elif sink in ("neo4j", "azure-neo4j") and (kg_extractor == "llm" or (kg_extractor is None and llm_enabled())):
    # 仅在开关打开时才创建 LLM 客户端; 缺配置会抛 ConfigurationError。
    relation_extractor = combine_extractors(
        relation_extractor, LLMRelationExtractor(OpenAILLMProvider.from_env())
    )
```

文件: C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\cli\main.py:119-123
```python
"--kg-extractor",
type=click.Choice(["rule", "llm"], case_sensitive=False),
default=None,
help="Neo4j: relation extractor; 'llm' adds LLM extraction on top of rules "
"(default: rule, or llm when KB_KG_LLM_ENABLED=1)",
```

5.5 最终结论: 只设环境变量够不够
已确认事实:
- 在 SDK 自己的 CLI 里，若 sink 是 neo4j / azure-neo4j，且没有显式传 --kg-extractor，那么 KB_KG_LLM_ENABLED=1 就能让 llm_enabled() 返回真，从而启用 LLM 关系抽取

但对本题这个后端链路，我的结论是: 不够直接下“只设环境变量就一定行”的结论。

原因:
- tap-ai-backend 的 sdk_ingest.py 不是走 SDK CLI 参数装配这条链路
- 它只是 TapIngestClient(..., sinks=sinks)，本仓代码里没有显式构造 LLMRelationExtractor
- 也没有把 KB_KG_LLM_ENABLED 传进任何 llm_enabled() 判断

所以本题范围内能严谨落地的结论是:
- 对 SDK CLI 来说: 只设 KB_KG_LLM_ENABLED=1 可以触发默认启用 LLM 抽取
- 对 tap-ai-backend 这条 sdk_ingest.py 链路来说: 仅凭当前已读代码，不能证明只设这个环境变量就一定生效；至少在后端仓代码里，没看到显式接这条开关的装配逻辑
- 因此，若问“后端这条链路是否必须改代码”，当前最稳妥说法是: 现有已读代码不足以证明无需改代码；至少后端仓里没有看到显式启用 LLM relation extractor 的代码

核对表

| 编号 | 状态（完成/未找到/未做） | 证据所在的文件:行号 |
| ---- | ---- | ---- |
| 1 | 完成 | knowledge/settings.py:21-31 &nbsp; knowledge/plugin.py:23-35 &nbsp; knowledge/spaces.py:20-39 &nbsp; knowledge/extension.py:72-83,97-106,144-157 &nbsp; knowledge/tools.py:53-57 &nbsp; plugins/ingest/sdk_ingest.py:221-230,303-307,69-87 |
| 2 | 完成 | plugins/ingest/sdk_ingest.py:275-301,303-307,112-123 |
| 3 | 完成 | knowledge/settings.py:21-76 ; 未找到 validator 的搜索依据: `rg -n "class KnowledgeSettings` |
| 4 | 完成 | config/settings.py:259-260 &nbsp; plugins/ingest/sdk_ingest.py:236-247,290-300 |
| 5 | 完成 | plugins/ingest/sdk_ingest.py:292-299 ; 后端未找到 KB_KG_LLM_ENABLED/llm_enabled 的搜索依据; SDK 依据 fwd-tap-ingest/src/tap_ingest_sdk/sinks/kg_llm_extract.py:35-61 、cli/main.py:186-193,119-123 |
```
