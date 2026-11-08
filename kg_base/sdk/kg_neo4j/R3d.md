# R3d_reply.md
## 1. 后端 `src/tap_ai/config/settings.py` 中所有类型为 bool 的字段：字段名、默认值、上一行注释
### 1.1 debug
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:61-62`
```python
# 默认 False（产线安全值）；可省略，需要时可被同名环境变量覆盖。
debug: bool = Field(default=False)
```

### 1.2 echo_sql
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:75-76`
```python
# 默认 False（产线安全值，避免回显/泄露 SQL）；可省略，可被环境变量覆盖。
echo_sql: bool = Field(default=False)
```

### 1.3 langfuse_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:82-83`
```python
# 凭证沿用 Langfuse SDK 的标准环境变量名；其余应用策略使用 TAP_AI_ 前缀。
langfuse_enabled: bool = Field(default=False)
```

### 1.4 langfuse_capture_content
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:102-103`
```python
# 默认不上传用户消息、模型上下文和答案；完成数据治理评审后再显式开启。
langfuse_capture_content: bool = Field(default=False)
```

### 1.5 skills_sync_strict
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:133-135`
```python
# 同步失败是否阻断应用启动。默认 False：只告警、不阻断（skill 属增强能力，
# 不应拖垮主服务）。需要强一致的环境可置 True。
skills_sync_strict: bool = Field(default=False)
```

### 1.6 react_skills_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:177-178`
```python
# 是否启用 Skill 索引/读取/执行链路。
react_skills_enabled: bool = Field(default=True)
```

### 1.7 react_capability_default_tools
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:198-199`
```python
# 未显式声明能力的模型采用的默认声明（探测通过即生效）。
react_capability_default_tools: bool = Field(default=True)
```

### 1.8 react_capability_default_vision
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:198-200`
```python
# 未显式声明能力的模型采用的默认声明（探测通过即生效）。
react_capability_default_vision: bool = Field(default=True)
```

### 1.9 react_capability_default_vision_with_tools
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:198-201`
```python
# 未显式声明能力的模型采用的默认声明（探测通过即生效）。
react_capability_default_vision_with_tools: bool = Field(default=True)
```

### 1.10 react_capability_probe_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:205-206`
```python
# 启动时是否对声明的能力做联调探测；关闭则直接信任配置声明。
react_capability_probe_enabled: bool = Field(default=True)
```

### 1.11 library_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:217-218`
```python
# 总开关。False 时不挂载任何 Library 路由、不构造任何 Library 服务。
library_enabled: bool = Field(default=False)
```

### 1.12 library_eval_llm_analysis_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:229-230`
```python
# 是否在评估成功后调用 LLM 做 badcase 根因分析。
library_eval_llm_analysis_enabled: bool = Field(default=False)
```

### 1.13 library_chunk_publish_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:231-232`
```python
# 切片提交落库的开关。
library_chunk_publish_enabled: bool = Field(default=False)
```

### 1.14 library_kb_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:233-234`
```python
# Library KB 总开关。只有 library_enabled 和它都为 True 时才挂载路由、构造服务。
library_kb_enabled: bool = Field(default=False)
```

### 1.15 library_kb_worker_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:235-236`
```python
# 后台入库处理的开关。
library_kb_worker_enabled: bool = Field(default=False)
```

### 1.16 library_kb_graph_enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:259-260`
```python
# 入库时是否同时写知识图谱（K9 使用）。
library_kb_graph_enabled: bool = Field(default=False)
```

## 2. 后端 `src/tap_ai/plugins` 下所有 `settings.py` 中的 bool 字段；以及 `kg_relation_types`、所有和 neo4j 有关的字段
本次在 `src/tap_ai/plugins` 下找到的 `settings.py` 只有 1 个：
`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py`

### 2.1 bool 字段
#### enabled
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:29-31`
```python
enabled: bool = False
# saas_id → index 名称映射（JSON），如 {"hk":"hk-kb-chunk-tap-dit"}; 未列出的租户不启用知识库。
indexes: dict[str, str] = {}
```
说明：这个字段上一行没有单独注释；它后面的注释说明了未列出的租户不启用知识库。

#### kg_entity_vector
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:46-47`
```python
# 实体向量匹配（需要 SDK 写入实体 embedding）。
kg_entity_vector: bool = False
```

### 2.2 kg_relation_types
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:63-64`
```python
# 子图允许遍历的业务关系类型（白名单）。
kg_relation_types: tuple[str, ...] = ("NEXT", "HANDLED_BY", "PART_OF", "REQUIRES")
```

### 2.3 所有和 Neo4j 有关的字段
#### neo4j_uri
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:39-40`
```python
# 为空时不启用图谱；本地联调如 bolt://localhost:7687。
neo4j_uri: str = ""
```

#### neo4j_user
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:40-42`
```python
neo4j_uri: str = ""
neo4j_user: str = "neo4j"
neo4j_password: SecretStr = SecretStr("")
```
说明：`neo4j_user` 上一行没有单独注释。

#### neo4j_password
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:41-42`
```python
neo4j_user: str = "neo4j"
neo4j_password: SecretStr = SecretStr("")
```
说明：`neo4j_password` 上一行没有单独注释。

#### neo4j_database
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:43-44`
```python
# Community 只有一个用户库。
neo4j_database: str = "neo4j"
```

#### neo4j_timeout_s
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py:44-45`
```python
neo4j_database: str = "neo4j"
neo4j_timeout_s: float = 3.0
```
说明：`neo4j_timeout_s` 上一行没有单独注释。

---
## 3. 第 1、2 条中每个 bool 字段的读取位置，以及 False 时会跳过什么
说明：本节按 `git grep` 结果整理，只列读取位置。若某字段本身就是定义而不是读取，不计为读取位置。

### 3.1 debug
读取位置：
（图片内该部分无内容）

### 3.2 echo_sql
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\db.py:15`
```python
echo=settings.echo_sql,
```
False 时会跳过什么：跳过 SQL 回显日志。

### 3.3 langfuse_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\observability\langfuse.py:101-106`
```python
if (
    not settings.langfuse_enabled
    or not settings.langfuse_public_key
    or not settings.langfuse_secret_key
):
    return NoopObservability()
```
False 时会跳过什么：跳过真实 Langfuse 客户端装配，直接走空实现。

### 3.4 langfuse_capture_content
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\observability\langfuse.py:115-118`
```python
return LangfuseObservability(
    client=client,
    capture_content=settings.langfuse_capture_content,
)
```
False 时会跳过什么：跳过把用户消息、上下文、答案等内容上传到 Langfuse。

### 3.5 skills_sync_strict
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:324`
```python
strict=app_settings.skills_sync_strict,
```
False 时会跳过什么：跳过“同步失败阻断启动”的严格分支，失败只告警不阻断主服务。

### 3.6 react_skills_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:490-499`
```python
if settings.react_skills_enabled:
    for tool in skill_tools.build_tools():
        tools.register(tool.spec().name, tool)
    catalog = build_catalog(default_target_dir())
    # L2/L3 读取与受管执行是独立端口，必须显式构造并注入；
    # 目录本身只提供 L1 索引，不承担读取/执行职责。
    skill_resource = LocalSkillResource(
        catalog, private_names=settings.react_skill_private_names
    )
    skill_executor = LocalSkillExecutor(catalog, executor)
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:549`
False 时会跳过什么：跳过 Skill 工具注册、catalog 构建、资源读取器和执行器装配。

### 3.7 react_capability_default_tools
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:615-618`
```python
default_flags: dict[str, Any] = {
    "supports_tools": bool(
        getattr(settings, "react_capability_default_tools", True)
    ),
}
```
False 时会跳过什么：未显式声明能力的模型默认不宣称支持 tools。

### 3.8 react_capability_default_vision
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:619-621`
```python
"supports_vision": bool(
    getattr(settings, "react_capability_default_vision", True)
),
```
False 时会跳过什么：未显式声明能力的模型默认不宣称支持视觉输入。

### 3.9 react_capability_default_vision_with_tools
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:622-624`
```python
"supports_vision_with_tools": bool(
    getattr(settings, "react_capability_default_vision_with_tools", True)
),
```
False 时会跳过什么：未显式声明能力的模型默认不宣称支持“视觉 + tools”组合。

### 3.10 react_capability_probe_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:645-649`
```python
if not getattr(settings, "react_capability_probe_enabled", True):
    # 关闭探测时直接信任配置声明。
    for model_id in container.capability_registry.names():
        container.capability_registry.mark_verified(model_id, verified=True)
    return
```
False 时会跳过什么：跳过启动时的能力联调探测，直接信任声明值。

### 3.11 library_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:373-395`
```python
if getattr(app_settings, "library_enabled", False):
    from tap_ai.application.library_chunks import ChunkReviewService
    from tap_ai.application.library_eval import EvalService
    from tap_ai.persistence.library_draft_repo import DraftRepo
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:397-399`
```python
if getattr(app_settings, "library_enabled", False) and getattr(
    app_settings, "library_kb_enabled", False
):
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:576-581`
```python
if getattr(settings, "library_enabled", False):
    from tap_ai.api.library_chunks import router as library_chunks_router
    from tap_ai.api.library_eval import router as library_eval_router
    app.include_router(library_chunks_router, tags=["library"])
    app.include_router(library_eval_router, tags=["library-eval"])
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:588-589`
```python
if getattr(settings, "library_enabled", False) and getattr(
    settings, "library_kb_enabled", False
):
```
False 时会跳过什么：跳过全部 Library 服务装配和 Library 路由挂载。

### 3.12 library_eval_llm_analysis_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_eval.py:575-578`
```python
async def _build_llm_analysis(self, run_id: str) -> dict[str, Any] | None:
    """仅在开关开启且存在 badcase 时调用一次 LLM 分析。"""
    if not getattr(self.settings, "library_eval_llm_analysis_enabled", False):
        return None
```
False 时会跳过什么：跳过 badcase 的 LLM 根因分析。

### 3.13 library_chunk_publish_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\library_chunks.py:147-153`
async def submit_draft(self, req: ChunkDraftIdRequest) -> Any:
    """提交草稿落库。"""
    draft = await self._get_required_draft(req.draft_id)
    self._ensure_editable_status(draft.status)
    if not self.settings.library_chunk_publish_enabled:
        raise BusinessError(code="CCB001", message="落库功能未启用")
False 时会跳过什么：跳过草稿提交落库。


## 3.14 library_kb_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:397-399`
```python
if getattr(app_settings, "library_enabled", False) and getattr(
    app_settings, "library_kb_enabled", False
):
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:588-593`
```python
if getattr(settings, "library_enabled", False) and getattr(
    settings, "library_kb_enabled", False
):
    from tap_ai.api.library_kb import router as library_kb_router
    app.include_router(library_kb_router, tags=["library-kb"])
```
False 时会跳过什么：跳过 KB 管理服务装配和 `library_kb` 路由挂载。

## 3.15 library_kb_worker_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:425-433`
```python
if getattr(app_settings, "library_kb_worker_enabled", False):
    app.state.library_kb_worker = KbIngestWorker(
        settings=app_settings,
        session_factory=session_factory,
        storage=blob_store,
        ingest=ingest,
        clock=now_ts,
    )
lifecycle.callback(app.state.library_kb_worker.stop, timeout=35)
```
False 时会跳过什么：跳过后台 KB 入库 worker 的创建和生命周期登记。

## 3.16 library_kb_graph_enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:236-247`
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
False 时会跳过什么：跳过 Neo4j driver 创建，也就不会把 `Neo4jGraphSink` 追加进 sink 列表。

## 3.17 插件 KnowledgeSettings.enabled
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:25-27`
```python
kb = KnowledgeSettings()
if not kb.enabled:
    return None
```
False 时会跳过什么：跳过整个知识库扩展装配。

## 3.18 插件 kg_entity_vector
读取位置：
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\plugin.py:60-68`
```python
graph = Neo4jKnowledgeGraph(
    uri=kb.neo4j_uri,
    user=kb.neo4j_user,
    ******
    database=kb.neo4j_database,
    timeout_s=kb.neo4j_timeout_s,
    entity_vector=kb.kg_entity_vector,
    entity_min_score=kb.kg_entity_min_score,
    relation_types=kb.kg_relation_types,
)
```
文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\service.py:109-116`
```python
vector, entities = await asyncio.gather(
    _embed(), self._safe_entities(space, rw.normalized, None)
)
if s.kg_entity_vector and self._graph is not None:
    # 向量已就绪后再补一次语义实体匹配。
    extra = await self._safe_entities(space, rw.normalized, vector)
    known = {e.id for e in entities}
    entities = [*entities, *(e for e in extra if e.id not in known)][:3]
```
False 时会跳过什么：跳过基于实体 embedding 的二次语义实体匹配。

---

## 补充：submit_draft 函数（第一张图顶部）
```python
async def submit_draft(self, req: ChunkDraftIdRequest) -> Any:
    """提交草稿落库。"""
    draft = await self._get_required_draft(req.draft_id)
    self._ensure_editable_status(draft.status)
    if not self.settings.library_chunk_publish_enabled:
        raise BusinessError(code="CCB001", message="落库功能未启用")
```
False 时会跳过什么：跳过草稿提交落库。

---
# 4. SDK 中所有读取环境变量的地方：先贴 git grep 全部原始输出，再整理成表格
## 4.1 git grep 原始输出
命令：
```bash
git -C C:\Users\234393\fwd-tap-common\fwd-tap-ingest --no-pager grep -n -E "os\.environ|getenv|BaseSettings|env_prefix" -- src
```
原始输出：
```
src/tap_ingest_sdk/cli/main.py:270:        endpoint = azure_endpoint or os.getenv("KB_AZURE_SEARCH_ENDPOINT")
src/tap_ingest_sdk/cli/main.py:271:        index_name = azure_index or os.getenv("KB_AZURE_SEARCH_INDEX")
src/tap_ingest_sdk/cli/main.py:272:        key = azure_key or os.getenv("KB_AZURE_SEARCH_KEY")
src/tap_ingest_sdk/cli/main.py:286:        index_name = azure_index or os.getenv("KB_AZURE_SEARCH_INDEX")
src/tap_ingest_sdk/cli/main.py:300:        uri = os.getenv("KB_NEO4J_URI")
src/tap_ingest_sdk/cli/main.py:301:        user = os.getenv("KB_NEO4J_USER")
src/tap_ingest_sdk/cli/main.py:302:        password = os.getenv("KB_NEO4J_PASSWORD")
src/tap_ingest_sdk/cli/main.py:306:        uri=uri, user=user, ****** scope=scope, database=os.getenv("KB_NEO4J_DATABASE") or None,
src/tap_ingest_sdk/cli/main.py:315:        cfg = {name: os.getenv(name) for name in names}
src/tap_ingest_sdk/cli/main.py:326:        if os.getenv("KB_EMBEDDING_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
src/tap_ingest_sdk/cli/main.py:336:        dimension=int(os.getenv("KB_EMBEDDING_DIMENSIONS") or 3072),
src/tap_ingest_sdk/cli/main.py:342:        dimension = int(os.getenv("KB_EMBEDDING_DIMENSIONS") or 3072)
src/tap_ingest_sdk/embeddings/_internal/config.py:32:        embedding_enabled=os.getenv("KB_EMBEDDING_ENABLED", "1").strip().lower()
src/tap_ingest_sdk/embeddings/_internal/config.py:34:        embedding_model=os.getenv("KB_EMBEDDING_MODEL"),
src/tap_ingest_sdk/embeddings/_internal/config.py:35:        copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
src/tap_ingest_sdk/embeddings/_internal/config.py:36:        copilot_provider_base_url=os.getenv("KB_EMBEDDING_BASE_URL"),
src/tap_ingest_sdk/embeddings/_internal/config.py:37:        copilot_provider_api_key=os.getenv("KB_EMBEDDING_API_KEY"),
src/tap_ingest_sdk/env_config.py:69:        if os.getenv(AUTOLOAD_DISABLE_VAR, "").strip().lower() in ("1", "true", "yes", "on"):
src/tap_ingest_sdk/lexicon/__init__.py:29:        path = os.getenv(_ENV_PATH)
src/tap_ingest_sdk/parsers/_internal/config.py:33:        local_ocr_language=os.getenv("KB_LOCAL_OCR_LANGUAGE", "japan"),
src/tap_ingest_sdk/parsers/_internal/config.py:34:        local_ocr_cpu_threads=int(os.getenv("KB_LOCAL_OCR_CPU_THREADS", "0")) or None,
src/tap_ingest_sdk/parsers/_internal/config.py:35:        enable_legacy_conversion=os.getenv("KB_ENABLE_LEGACY_CONVERSION", "1").strip()
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:41:        "GLOG_minloglevel": os.environ.get("GLOG_minloglevel"),
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:42:        "FLAGS_logtostderr": os.environ.get("FLAGS_logtostderr"),
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:43:        "FLAGS_v": os.environ.get("FLAGS_v"),
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:45:        os.environ["GLOG_minloglevel"] = "3"
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:46:        os.environ["FLAGS_logtostderr"] = "0"
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:47:        os.environ["FLAGS_v"] = "0"
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:64:        os.environ.pop(key, None)
src/tap_ingest_sdk/parsers/_internal/ppt_ocr.py:66:        os.environ[key] = value
src/tap_ingest_sdk/sinks/_azure.py:55:        self._source_url_base = source_url_base or os.getenv("KB_SOURCE_URL_BASE")
src/tap_ingest_sdk/sinks/_internal/config.py:88:        azure_search_endpoint=os.getenv("KB_AZURE_SEARCH_ENDPOINT"),
src/tap_ingest_sdk/sinks/_internal/config.py:89:        azure_search_key=os.getenv("KB_AZURE_SEARCH_KEY"),
src/tap_ingest_sdk/sinks/_internal/config.py:90:        azure_search_index=os.getenv("KB_AZURE_SEARCH_INDEX"),
src/tap_ingest_sdk/sinks/_internal/config.py:91:        azure_search_vector_field=os.getenv("KB_AZURE_SEARCH_VECTOR_FIELD", "content_vector"),
src/tap_ingest_sdk/sinks/_internal/config.py:92:        embedding_model=os.getenv("KB_EMBEDDING_MODEL"),
src/tap_ingest_sdk/sinks/_internal/config.py:93:        embedding_dimensions=int(os.getenv("KB_EMBEDDING_DIMENSIONS") or 3072),
src/tap_ingest_sdk/sinks/_internal/config.py:94:        aoai_endpoint=os.getenv("KB_AOAI_ENDPOINT"),
src/tap_ingest_sdk/sinks/_internal/config.py:95:        aoai_embedding_deployment=os.getenv("KB_AOAI_EMBEDDING_DEPLOYMENT"),
src/tap_ingest_sdk/sinks/_internal/config.py:96:        aoai_embedding_model=os.getenv("KB_AOAI_EMBEDDING_MODEL") or os.getenv("KB_EMBEDDING_MODEL"),
src/tap_ingest_sdk/sinks/_internal/config.py:97:        aoai_api_key=os.getenv("KB_AOAI_API_KEY"),
src/tap_ingest_sdk/sinks/_internal/config.py:98:        copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
src/tap_ingest_sdk/sinks/_internal/config.py:99:        copilot_provider_base_url=os.getenv("KB_EMBEDDING_BASE_URL"),
src/tap_ingest_sdk/sinks/_internal/config.py:100:        copilot_provider_api_key=os.getenv("KB_EMBEDDING_API_KEY"),
src/tap_ingest_sdk/sinks/kg_llm_extract.py:60:        value = (env if env is not None else os.environ.get(LLM_ENABLED_ENV, "0"))
src/tap_ingest_sdk/sinks/kg_llm_extract.py:203:        env = env if env is not None else dict(os.environ)
```

## 4.2 整理表格：环境变量名 | 默认值 | 作用
| 环境变量名 | 默认值 | 作用 |
| ---- | ---- | ---- |
| KB_AZURE_SEARCH_ENDPOINT | 无 | Azure AI Search endpoint |
| KB_AZURE_SEARCH_INDEX | 无 | Azure index 名；Neo4j-only 模式下也被当作 graph scope |
| KB_AZURE_SEARCH_KEY | 无 | Azure AI Search credential |
| KB_NEO4J_URI | 无 | Neo4j 连接地址 |
| KB_NEO4J_USER | 无 | Neo4j 用户名 |
| KB_NEO4J_PASSWORD | 无 | Neo4j 密码 |
| KB_NEO4J_DATABASE | None（不设时传 None） | Neo4j database 名 |
| KB_EMBEDDING_ENABLED | 1 | 是否启用 embedding；0/false/no/off 表示关闭 |
| KB_EMBEDDING_DIMENSIONS | 3072 | embedding 维度 |
| KB_EMBEDDING_MODEL | 无 | embedding 模型名；部分场景也作为 AOAI embedding model 回退值 |
| KB_COPILOT_PROVIDER_TYPE | 无 | embedding provider 类型兼容字段 |
| KB_EMBEDDING_BASE_URL | 无 | embedding provider base URL |
| KB_EMBEDDING_API_KEY | 无 | embedding provider API key |
| TAP_INGEST_SDK_NO_AUTOLOAD_ENV | 空字符串 | 禁止 SDK import 时自动加载 .env |
| TAP_INGEST_LEXICON | 无 | 追加外部 JSON 业务词典 |
| KB_LOCAL_OCR_LANGUAGE | japan | 本地 OCR 语言 |
| KB_LOCAL_OCR_CPU_THREADS | 0（随后转 None） | OCR CPU 线程数 |
| KB_ENABLE_LEGACY_CONVERSION | 1 | 是否启用 legacy conversion |
| GLOG_minloglevel | 读取当前环境值；写入时临时设 3 | 压低 Paddle / glog 日志级别 |
| FLAGS_logtostderr | 读取当前环境值；写入时临时设 0 | 控制 Paddle 日志输出到 stderr |
| FLAGS_v | 读取当前环境值；写入时临时设 0 | 控制 Paddle verbose 级别 |
| KB_SOURCE_URL_BASE | 无 | Azure sink 里拼 citation URL 的 base |
| KB_AZURE_SEARCH_VECTOR_FIELD | content_vector | Azure 向量字段名 |
| KB_AOAI_ENDPOINT | 无 | AOAI endpoint |
| KB_AOAI_EMBEDDING_DEPLOYMENT | 无 | AOAI embedding deployment |
| KB_AOAI_EMBEDDING_MODEL | 回退到 KB_EMBEDDING_MODEL | AOAI embedding model |
| KB_AOAI_API_KEY | 无 | AOAI API key |
| KB_KG_LLM_ENABLED | 0 | 是否开启 LLM 关系抽取 |
| KB_COPILOT_PROVIDER_BASE_URL | 无 | LLM 抽取的 OpenAI 兼容 base URL |
| KB_COPILOT_PROVIDER_API_KEY | 无 | LLM 抽取的 API key |
| KB_KG_LLM_MODEL | 无 | LLM 关系抽取模型名 |

---

# 5. SDK 中 OpenAILLMProvider 的完整类定义原文：它从哪些环境变量或参数读取模型地址、密钥、模型名
## 5.1 完整类定义原文
文件：`C:\Users\234393\fwd-tap-common\fwd-tap-ingest\src\tap_ingest_sdk\sinks\kg_llm_extract.py:183-218`
```python
class OpenAILLMProvider:
    """基于 OpenAI 兼容端点的 `LLMProvider`；复用 `KB_COPILOT_PROVIDER_*` 配置。"""

    def __init__(self, base_url: str, api_key: str, model: str, *, temperature: float = 0.0) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("LLM 抽取需要 openai 包: pip install openai") from exc
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._temperature = temperature

    def complete(self, messages: Any) -> str:
        response = self._client.chat.completions.create(
            model=self._model, messages=list(messages), temperature=self._temperature
        )
        return response.choices[0].message.content or ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> OpenAILLMProvider:
        env = env if env is not None else dict(os.environ)
        base_url = env.get("KB_COPILOT_PROVIDER_BASE_URL")
        api_key = env.get("KB_COPILOT_PROVIDER_API_KEY")
        model = env.get("KB_KG_LLM_MODEL")
        missing = [
            name
            for name, value in (
                ("KB_COPILOT_PROVIDER_BASE_URL", base_url),
                ("KB_COPILOT_PROVIDER_API_KEY", api_key),
                ("KB_KG_LLM_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(f"LLM 抽取已开启但缺少配置: {', '.join(missing)}")
        return cls(str(base_url), str(api_key), str(model))
```

## 5.2 它从哪些环境变量或参数读取模型地址、密钥、模型名

直接参数：

- `__init__(base_url, api_key, model, temperature=0.0)`

`from_env()` 读取的环境变量：

- `KB_COPILOT_PROVIDER_BASE_URL` → `base_url`
- `KB_COPILOT_PROVIDER_API_KEY` → `api_key`
- `KB_KG_LLM_MODEL` → `model`

---

## 6. 后端 `src/tap_ai/plugins/ingest/sdk_ingest.py` 中构造 `Neo4jGraphSink` 的完整原文（上下各20行）；以及 `library_kb_graph_enabled=False` 时走哪条分支

### 6.1 构造 `Neo4jGraphSink` 的完整原文（上下各20行）

文件：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:272-311`

```
checked_indexes.add(index_name)
return None

def _sinks_factory(index_name: str) -> Sequence[object]:
    from tap_ingest_sdk.sinks._azure import ( # type: ignore[import-untyped]
        AzureAISearchSink,
    )
    from tap_ingest_sdk.sinks._neo4j import ( # type: ignore[import-untyped]
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

adapter = SdkIngestAdapter(
    mode="azure",
    index_resolver=lambda saas_id: kb.indexes.get(saas_id),
    sinks_factory=_sinks_factory,
    index_guard=_ensure_index_exists,
)
if shared_driver is None:
    return adapter
return cast(ClosableIngestPort, _ClosableSdkIngestAdapter(adapter=adapter, driver=shared_driver))
```

### 6.2 `library_kb_graph_enabled=False` 时前置分支原文

文件: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:233-247`

```
shared_driver: Any | None = None
checked_indexes: set[str] = set()
checked_indexes_lock = Lock()
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

### 6.3 `library_kb_graph_enabled=False` 时走哪条分支

已确认事实：

- `shared_driver` 初始值是 `None`
- 当 `library_kb_graph_enabled=False` 时，不进入 `if getattr(settings, "library_kb_graph_enabled", False):`
- 因此 `shared_driver` 仍然是 `None`
- 到 `_sinks_factory()` 时，不进入 `if shared_driver is not None:` 这个分支

对应原文：`C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py:283-301`

```
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

**结论：**

- `library_kb_graph_enabled=False` 时，走的是**只保留 AzureAISearchSink，不追加 Neo4jGraphSink**这条分支。

---

## 证据列表

| 编号 | 状态（完成/未找到/未做） | 证据所在的文件:行号 |
| --- | --- | --- |
| 1 | 完成 | `src/tap_ai/config/settings.py:61-62,75-76,82-83,102-103,133-135,177-178,198-201,205-206,217-218,229-234,235-236,259-260` |
| 2 | 完成 | `src/tap_ai/plugins/extensions/knowledge/settings.py:29-47,63-64` |
| 3 | 完成 | `bootstrap.py:373-425,490-549,576-649`     `plugins/observability/langfuse.py:101-118`     `application/library_chunks.py:147-153`     `application/library_eval.py:575-578`     `plugins/extensions/knowledge/plugin.py:25-27,60-68`     `plugins/extensions/knowledge/service.py:109-116`     `plugins/ingest/sdk_ingest.py:236-247` |
| 4 | 完成 | SDK git grep 原始输出；   `cli/main.py:270-342`     `embeddings/_internal/config.py:32-37`     `env_config.py:67-74`     `lexicon/__init__.py:24-30`     `parsers/_internal/config.py:32-36`     `parsers/_internal/ppt_ocr.py:40-66`     `sinks/_azure.py:55`     `sinks/_internal/config.py:87-100`     `sinks/_kg_llm_extract.py:60,203-218` |
| 5 | 完成 | `src/tap_ingest_sdk/sinks/_kg_llm_extract.py:183-218` |
| 6 | 完成 | `src/tap_ai/plugins/ingest/sdk_ingest.py:233-247,272-311,283-301` |

