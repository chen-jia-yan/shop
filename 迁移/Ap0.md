## 1. `.github/copilot-instructions.md` 全文
来源: C:\Users\234393\Desktop\tap-ai-backend\.github\copilot-instructions.md:1-54

# Copilot Instructions — tap-ai-backend
FastAPI + LangGraph ReAct agent + LiteLLM backend. Import package is **tap_ai** (`src/tap_ai/`). Python ≥3.12, managed by `uv`. Docs/comments are in Chinese.

## Commands
```bash
uv sync && cp .env.example .env      # config = TAP_AI_* env vars
uv run uvicorn tap_ai.main:app --reload --port 9006  # dev server
uv run ruff check . && uv run ruff format --check . && uv run pytest -q && uv run mypy src  # full gate
uv run pytest tests/unit/test_decide.py::test_name -q # single test
```

- Fixtures `app` / `client` (session-scoped, built via `bootstrap.build_app()`) are in `tests/conftest.py`. Unit tests use hand-written fakes.
- `tests/api/test_health.py::test_health_ready_shape` needs the real MySQL/Redis.
- Real-LLM tests are skipped unless `TAP_AI_TEST_REAL_LLM=1`.
- `diagnose_*` / `probe_*` / `verify_*` / `run_*` scripts are manual tools, not tests.

### Architecture
- Layers: `api → application → core → contracts`, dependencies only point downward. `plugins/`, `prompts/` and `persistence/` implement the `contracts/` Protocols, and `registries/` resolves them by name. **core must never import `plugins`, `persistence`, or `prompts`.**
- `bootstrap.build_app()` is the only composition root. It handles `plugins → registries`, prompt injection, graph compilation, services on `app.state`, and routers in `_mount_routers`.
- Adding a capability:
  - Model gateway or storage: add a file in `plugins/<category>/` that exposes `build(...)` returning an object with `_port_name_`, then add one line to `config/plugins.py::ENABLED_PLUGINS`.
  - ReAct tool: implement `contracts/tool.py::ToolPort` in `plugins/tools/`. Declare `ToolSpec.effect` (`read` / `workspace_write` / `external_write`) and a JSON-schema `parameters`, then register it in `bootstrap._build_react_deps`. Do not add it to `ENABLED_PLUGINS`.
- Chat flow: `application/chat.py::ChatService` proceeds as follows:
  i. It takes the Redis per-conversation lock, then sends the first `phase:thinking` frame.
  ii. `_stream_reply` runs URL policy, then clarification (returns fixed text, `CLARIFICATION`, no graph), then 4-layer context compression.
  iii. `_run_react_flow` creates a per-run workspace and builds the attachment manifest, then drives the graph via `stream_react_run`.
  iv. Graph events are queued and turned into `ChatEvent`s.
  v. `enforce_scope` runs on the answer, then `ResultPersister` writes the reply and audit records (incl. `tool_trace`) in one transaction.
- ReAct graph (`core/graph.py`): `decide → render_context → agent ↔ tools → final_answer → finalize`.
  - `decide` only locks the model. It still parses `route`, but the graph does not branch on it.
  - `render_context` builds the messages and sets `tools_available` from the capability registry. If tools are unavailable, it goes straight to `final_answer`.
  - `final_answer` streams the reply with tools disabled. The graph does generate the reply.
  - Budgets and timeouts come from `settings.react_*`. Stop reasons are `RESULT_*` in `core/graph.py`.
  - The old route-based dispatch ( `task_runner`, Copilot CLI, file/query/execute flows) has been removed.
- SSE contract: `phase → token * → done / error`. `phase` values are `thinking` / `reading` / `acting` / `responding`. `token.stage` is `progress` or `final`. Only `final` deltas form the answer, and `join(final) == done.answer == persisted answer`. To add an event type, update `utils/streaming.py`, `application/chat.py::_react_event`, `api/chat.py::_chat_event_to_sse`, and `docs/API-文档.md` together.
- Business errors (`core/errors.py`) return HTTP 200 with `{code, message}`.

### Conventions
- Prompts are injected through a contract. Core components receive them via `self._prompts = resolve_prompt_library(prompts)` and call contract methods such as `decide_system()` / `render_skill_catalog()`. Search for method names, not prompt constants. To add a prompt, update `contracts/prompt_library.py`, `prompts/library.py`, and the `prompts/*.py` module.
- Settings live only in `config/settings.py`. Connection params have no defaults.
- Runtime resources (connection pools, clients, subprocesses) must be registered in `core/lifecycle.py`.
- Cross-cutting helpers:
  - cancellation: `utils/redis.py` (`is_cancelled`)
  - token accounting: the `contracts/token_usage.py` `ContextVar`
  - all LLM calls go through `plugins/models/llm.py`
  - workspace/path safety: `utils/workspace.py` `utils/path_safety.py`; shell allowlist: `plugins/executor/restricted.py`; HTTP policy: `core/policy/http_policy.py`
  - observability: `contracts/observability.py` + `plugins/observability/langfuse.py`; one trace per chat turn, one session per conversation; never import Langfuse from `core`

Further reading: `docs/代码导读-主流程与分层.md` (code map), `docs/设计-ReAct-Agent重构方案.md`, `docs/架构设计-系统总览.md` (architecture), `docs/API-文档.md`.

---

## 2. `pyproject.toml` 中 `[tool.ruff]`、`[tool.mypy]`、`[tool.pytest*]` 配置；以及测试 / ruff / mypy 命令
### 2.1 原样配置
来源: `C:\Users\234393\Desktop\tap-ai-backend\pyproject.toml:55-75`
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
  "e2e: 端到端用例, 触达真实 MySQL / Redis / LLM 网关; 默认跳过, 需 --run-e2e 开启",
]

[tool.ruff]
line-length = 88
target-version = "py312"
src = ["src", "tests"]
# 预置 skill 内的 scripts/*.py 是被 skill 调用的独立工具脚本, 不是 tap_ai 的模块。
extend-exclude = ["src/tap_ai/skills"]

[tool.mypy]
python_version = "3.12"
files = ["src"]
check_untyped_defs = true
# 同上: 预置 skill 资产不参与类型检查。
exclude = ["^src/tap_ai/skills/"]
```

### 2.2 运行单元测试、ruff、mypy 的确切命令
来源一: `C:\Users\234393\Desktop\tap-ai-backend\.github\copilot-instructions.md:7-12`
```bash
uv sync && cp .env.example .env
uv run uvicorn tap_ai.main:app --reload --port 9006
uv run ruff check . && uv run ruff format --check . && uv run pytest -q && uv run mypy src
uv run pytest tests/unit/test_decide.py::test_name -q
```

来源二: `C:\Users\234393\Desktop\tap-ai-backend\README.md:106-126`
```bash
uv run ruff check .
uv run ruff format .
uv run pytest -q
uv run mypy src

uv run pytest tests/e2e --run-e2e -q

uv run ruff check . && uv run ruff format --check . \
&& uv run pytest -q \
&& uv run mypy src
```

结论:
1. 单元/常规测试命令: `uv run pytest -q`
2. ruff 检查命令: `uv run ruff check .`
3. ruff 格式检查命令: `uv run ruff format --check .`
4. mypy 命令: `uv run mypy src`
5. 完整 gate: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q && uv run mypy src`

---

## 3. 现有路由前缀写在哪里? conversations 路由定义；现有接口用了哪些 HTTP 方法
### 3.1 路由前缀写法
来源: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\conversations.py:28`
```python
router = APIRouter(prefix="/tap/ai/conversations", tags=["conversations"])
```

**结论:** 现有业务路由前缀写在 `APIRouter(prefix=...)`, 不是把完整路径硬写在每个 handler 里。

### 3.2 conversations 路由定义
来源: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\conversations.py:35-89`
```python
@router.get("/messages/{conv_id}", response_model=list[MessageData])
...

@router.post("/add", response_model=ConversationData)
...

@router.post("/update", response_model=ConversationData)
...

@router.post("/list", response_model=ConversationListData)
...

@router.post("/delete")
...

@router.get("/{conv_id}", response_model=ConversationData)
...
```

### 3.3 现有接口用了哪些 HTTP 方法
来源: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api` 全目录搜索结果
- `audit.py`: GET/POST
- `chat.py`: POST
- `conversations.py`: GET/POST
- `files.py`: POST
- `models.py`: GET
- `health.py`: GET

证据: `C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\*.py` 搜索结果显示只出现了 `@router.get(...)`、`@router.post(...)`。

**结论:** 当前已确认接口只用了 GET、POST；未发现 PATCH、DELETE、PUT 路由。

## 4. 成功返回时外面有没有统一包装？贴一个 conversations 成功返回写法；分页返回模型定义
### 4.1 成功返回时外面有没有统一包装
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\conversations.py:44-74
```python
@router.post("/add", response_model=ConversationData)
async def create_conversation(...) -> ConversationData:
    conv = await _service(request).create(body)
    return ConversationData.model_validate(conv)

@router.post("/list", response_model=ConversationListData)
async def list_conversations(... ) -> ConversationListData:
    rows, total, page, page_size = await _service(request).list(body)
    items = [ConversationData.model_validate(r) for r in rows]
    return ConversationListData(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
```

**结论：**成功返回没有统一外层包装（例如没有统一 `{"code":...,"data":...}` 外壳），而是直接返回 DTO。

### 4.2 分页返回模型定义
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\api\dto.py:31-38
```python
class ConversationListData(BaseModel):
    """分页列表响应体。"""

    items: list[ConversationData]
    total: int
    page: int
    page_size: int
```

---

## 5. 配置类在哪个文件？贴一个布尔开关和一个字符串配置定义，以及环境变量命名规则
### 5.1 配置类位置
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:38-52
```python
class Settings(BaseSettings):
    ...
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="TAP_AI_",
    )
```
**结论：**配置类在 `src\tap_ai\config\settings.py`。

### 5.2 一个布尔开关定义写法
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:59-60
```python
debug: bool = Field(default=False)
```

### 5.3 一个字符串配置定义写法
来源：C:\Users\234393\Desktop\tap_ai\config\settings.py:64-69
```python
litellm_base_url: str = Field(default=...)
litellm_api_key: str = Field(default=...)
default_model: str = Field(default=DEFAULT_MODEL)
```

### 5.4 环境变量命名规则
来源：
- C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:3-5
- C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\config\settings.py:46-52
- C:\Users\234393\Desktop\tap-ai-backend\README.md:12

证据：
> 所有配置均由 `.env` / 环境变量驱动，本模块**不设任何默认值**。
> 每个字段对应一个 `TAP_AI_` 前缀的环境变量

```python
env_prefix="TAP_AI_"
```

> .env.example        # 环境变量模板（TAP_AI_ 前缀）

**结论：**环境变量命名规则是 `TAP_AI_` 前缀；个别 Langfuse 凭证还兼容标准环境变量名，见 `validation_alias=AliasChoices(...)`。

---

## 6. 找出调用 ModelGatewayPort.acompletion 的代码；怎么读取 StreamingCompletion；TextDelta 定义；能否拿到 token 用量
### 6.1 acompletion 的定义
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:125-131
```python
def acompletion(
    self,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
) -> StreamingCompletion: ...
```

### 6.2 调用 `acompletion` 的代码
已确认位置：
1. src\tap_ai\core\intent_extractor.py:35-46
2. src\tap_ai\core\summarizer.py:30-36
3. src\tap_ai\core\decide.py:167-171, 208-212

其中最清楚的一段证据：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\core\intent_extractor.py:35-47
```python
stream = self.gateway.acompletion(
    model=model or self._default_model,
    messages=[
        {"role": "system", "content": self._prompts.intent_system()},
        {"role": "user", "content": content},
    ],
    temperature=0.2,
)

parts: list[str] = []
async for token in stream:
    parts.append(token)
await stream.aclose()
raw = "".join(parts).strip()
```

### 6.3 `StreamingCompletion` 怎么读取
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:42-71
```python
class StreamingCompletion:
    ...
    def __aiter__(self) -> AsyncIterator[str]:
        return self._token_stream

    async def aclose(self) -> None:
        aclose = getattr(self._token_stream, "aclose", None)
        if aclose is not None:
            await aclose()
```

**结论：**读取方式是：
1. `async for token in stream` 逐token读取
2. 结束后 `await stream.aclose()` 关闭底层流

### 6.4 有没有 `.text`
已读到的 `StreamingCompletion` 定义中没有 `.text` 属性。当前已确认公开成员是：
1. `__aiter__`
2. `aclose()`
3. `usage`
4. `ttft_ms`

证据：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:49-62

### 6.5 `TextDelta` 的定义
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:177-182
```python
@dataclass(frozen=True)
class TextDelta:
    """正文增量。"""

    text: str
```

注意：`TextDelta` 是给 `astream_turn()` 那套回合流用的，不是 `acompletion()` 返回的 `StreamingCompletion` token流。

### 6.6 能否拿到 token 用量
能。

来源一：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:42-46
> 既可在 `async for` 中逐 token 消费，又可在消费结束后读取 :attr:`usage` 获取 token 用量（流式末尾的 usage chunk 解析而来）。

来源二：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:33-39
```python
class CompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    tool_tokens: int = 0
```

来源三：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:204-245
> 这里明确解析了 provider 返回的 usage；如果 provider 不返回 usage，则本地估算后 `result.set_usage(...)`。



## 7. acompletion 的调用会不会被 Langfuse 记录？
会。

证据链如下：

### 7.1 bootstrap 注入 observability 到模型插件
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:123-127
```python
observability = build_observability(settings)
container.register("observability", observability)
lifecycle.callback(observability.shutdown)
```

来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:66
```python
observability=container.get("observability"),
```

### 7.2 llm.py 的 acompletion 内部包了一层 observability.observe(...)
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:182-193
```python
with observability.observe(
    name=_generation_name(engine),
    as_type="generation",
    input=messages,
    model=model,
    model_parameters={"temperature": temperature},
    metadata={"engine": engine},
) as observation:
```

并在流结束后更新 output 和 usage：
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:246-249
```python
observation.update(
    output="".join(generated_chunks),
    usage_details=_usage_details(result.usage),
    metadata={"engine": engine, "estimated": not usage_seen},
)
```

### 7.3 Langfuse 实现位置
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\observability\langfuse.py:95-118
```python
def build_observability(...) -> ObservabilityPort:
    if (
        not settings.langfuse_enabled
        or not settings.langfuse_public_key
        or not settings.langfuse_secret_key
    ):
        return NoopObservability()
    client = client_factory(...)
    return LangfuseObservability(...)
```

结论：
1. 代码路径上 acompletion 会走 observability 记录。
2. 当 langfuse_enabled=false 或缺少凭证时，走 NoopObservability()，即不会真正写入 Langfuse。

## 8. bootstrap 中模型网关怎么拿到？container.get(...) 键名；lifespan / startup 钩子在哪里
### 8.1 模型网关怎么拿到
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:206-208
```python
gateway = container.model_registry.get("model_gateway")
summarizer = (
    Summarizer(gateway=gateway, prompts=default_prompt_library) if gateway else None
)
```markdown
## 8. bootstrap 中模型网关怎么拿到？container.get(...) 键名；lifespan / startup 钩子在哪里

### 8.1 模型网关怎么拿到
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:206-208
```python
gateway = container.model_registry.get("model_gateway")
summarizer = (
    Summarizer(gateway=gateway, prompts=default_prompt_library) if gateway else None
)
```

来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\bootstrap.py:310-312
```python
app.state.model_service = ModelService(
    gateway=container.model_registry.get("model_gateway")
)
```

**结论：**模型网关是通过 `container.model_registry.get("model_gateway")` 取的，不是直接 `container.get("model_gateway")`。

### 8.2 container.get(...) 的键名
已确认的键名有：
1. `observability` ——证据：bootstrap.py:126
2. `capability_verify` ——证据：bootstrap.py:199, 559

对应证据：
```python
container.register("observability", observability)
...
container.register("capability_verify", _verify)
```

### 8.3 lifespan / startup 钩子位置
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\main.py:57-124
```python
@asynccontextmanager
async def _lifespan(_app: object) -> AsyncIterator[None]:
    ...

app = build_app(lifespan=_lifespan)
```

结论：
1. lifespan 在 `src\tap_ai\main.py` 的 `_lifespan()`。
2. 当前已读代码中未看到单独的 `@app.on_event("startup")` 写法。


## 9. 列出 sql/ 下全部文件；ORM 模型里有没有 JSON 类型列；32 位 id、毫秒时间戳工具函数在哪里

### 9.1 sql/ 下全部文件名
来源：C:\Users\234393\Desktop\tap-ai-backend\sql

只有一个文件：
1. `001_create_tables.sql`

### 9.2 ORM 模型里有没有 JSON 类型列
有。

来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\models.py:16-17
```python
from sqlalchemy import (
    JSON,
    ...
)
```

示例列：
1. `Message.file_ids` —— models.py:130-133
2. `AiTrace.file_ids` —— models.py:201-203
3. `AiTrace.knowledge_refs` —— models.py:204-206
4. `AiTrace.token_details` —— models.py:207-210
5. `AiTrace.tool_trace` —— models.py:219-222

### 9.3 生成 32 位 id、毫秒时间戳的工具函数
来源：C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\persistence\models.py:59-71
```python
def _new_uuid() -> str:
    return uuid.uuid4().hex

def _now_ts() -> int:
    import time
    return int(time.time() * 1000)

def now_ts() -> int:
    return _now_ts()
```

## 10. 测试里怎么测仓储和数据库、怎么测接口。各贴一个例子

### 10.1 接口怎么测
来源：C:\Users\234393\Desktop\tap-ai-backend\tests\conftest.py:18-38
```python
from fastapi.testclient import TestClient
...
@pytest.fixture(scope="session")
def app():
    return build_app()

@pytest.fixture(scope="session")
def client(app) -> TestClient:
    return TestClient(app)
```

来源：C:\Users\234393\Desktop\tap-ai-backend\tests\api\test_health.py:8-15
```python
def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
```

**结论：**接口测试用 `fastapi.testclient.TestClient`。

来源：C:\Users\234393\Desktop\tap-ai-backend\tests\conftest.py:42-58
```python
@pytest.fixture
def isolated_session_factory():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from tap_ai.config.settings import import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        asyncio.run(engine.dispose())
```

再结合 tests\conftest.py:3-10 的说明：
```
模型与工具插件是假实现，
不触达真实 LLM / Copilot CLI；但 **数据库与 Redis 仍是进程级单例**
...
需要独立事件循环或真实 DB 交互的用例，应自行
`build_app(session_factory=...)` 注入隔离实现
```

结论：
1. 仓储/数据库测试不是 fake repository 模式，而是可注入隔离的 `session_factory`。
2. 已确认例子是通过 `create_async_engine(..., poolclass=NullPool)` 新建隔离 DB 会话工厂。
3. 是否存在 sqlite 专用仓储测试：当前已读内容未确认。


## 11. docs/ 下真实文件名
来源: C:\Users\234393\Desktop\tap-ai-backend\docs

已确认文件:
1. 设计-Token审计账本重构.md
2. 设计-ReAct-Agent重构方案.md
3. 架构设计-系统总览.md
4. 代码导读-主流程与分层.md
5. API-文档.md
6. superpowers\specs\2026-10-14-tapper-langgraph-blueprint.md
7. superpowers\specs\2026-10-14-observability-langfuse-design.md
8. superpowers\plans\2026-10-14-observability-langfuse.md

## 12. 旧项目（只读）：rag_gold_set.jsonl 前2行的字段名；LocalAnswerer.answer 内部用的 top_k；JUDGE_V2 提示词模板全文

### 12.1 rag_gold_set.jsonl 前2行字段名
来源: C:\Users\234393\Desktop\jap-cycle-poc\evals\rag_gold_set.jsonl:1-2

前2行都包含以下字段名：
1. question
2. ideal_answer
3. expected_source

### 12.2 LocalAnswerer.answer 内部用的 top_k
来源: C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\local_answer\answerer.py:58-81
```python
def answer(self, query: str, top_k: int | None = None) -> LocalAnswerResponse:
    ...
    top_k = top_k or self.retriever.config.top_k
    ...
    search_result = skill_rt.search_kb(
        query=query,
        alternate_queries=alternate_queries,
        top_k=top_k,
        query_intent=query_intent,
        include_rejected=False,
    )
```

结论：`LocalAnswerer.answer()` 内部实际用的是：
- 传入值 `top_k`；如果没传，则退回 `self.retriever.config.top_k`

固定值是多少：未确认。

### 12.3 JUDGE_V2 提示词模板全文
来源: C:\Users\234393\Desktop\jap-cycle-poc\kb_poc\skills\rag_eval\runtime.py:37-80
```python
JUDGE_V2_SYSTEM_PROMPT: str = (
    "你是保险业务知识库问答的严格评审员。请只根据下面提供的材料打分，不要使用你自己的知识。"
)

JUDGE_V2_USER_PROMPT_TEMPLATE: str = """【问题】{question}
【标准答案】{expected_answer}
【必答要点】（逐条编号）
{key_points}
【原始证据】(来自知识库原文，每段带 chunk_id)
{original_evidence}
【推断证据】(来自知识图谱/空间复原/流程图重建等推断，非原文；纯检索链路此项为空)
{derived_evidence}
【待评答案】{actual_output}

请按以下四个维度分别打 1~5 分。每个维度只评自己负责的那一件事，不要用其它维度的问题扣分。
1. 忠实度 faithfulness — 只管「答案里的每句话能否在【原始证据】或【推断证据】中找到支撑，有没有凭空编造」。不管答得对不对、全不全。
5=每句都有支撑；4=只有措辞层面的轻微引申；3=有1处无支撑的具体说法；2=有多处无支撑的说法；1=主要内容无支撑或编造。

2. 答案相关性 answer_relevance — 只管「是否在回答这个问题本身」。不管事实对错、要点全不全。
5=直接、聚焦地回答问题；4=回答了但夹带少量无关内容；3=部分在答、部分跑题；2=大部分没在答这个问题；1=答非所问，或只说"无法确认"而未作任何回应。

3. 完整性 completeness — 只管「【必答要点】覆盖了多少」。不管答案读起来丰不丰满，也不管多说了什么。
逐条判定每个要点: hit (明确说到且意思一致) / partial (说到一部分或表达含糊) / miss (没说到) / wrong (说到了但说错)。
覆盖率 = (hit数 + 0.5×partial数) ÷ 要点总数。
映射: ≥0.9→5；≥0.7→4；≥0.5→3；≥0.25→2；<0.25→1。

4. 正确性 correctness — 只管「答案里已经说出的内容，与【标准答案】是否一致」。不管说没说全。
5=说出的内容全部与标准答案一致；4=主干正确，有次要细节出入；3=主干正确但有1处明确错误；2=有关键事实错误；1=主要结论错误。
硬性规则: 只要日期、画面ID、金额、系统名、条款名这类关键事实有任何一处错误，正确性最高只能给2分。

只输出以下 JSON，不要输出任何其它文字：
{{
"faithfulness": {{"score": 1-5, "reason": "一句话说明依据"}},
"answer_relevance": {{"score": 1-5, "reason": "..."}},
"completeness": {{
    "score": 1-5,
    "coverage": 0.0-1.0,
    "key_points": [{{"id": 1, "status": "hit|partial|miss|wrong", "evidence": "答案中对应的原话，没有则留空"}}],
    "reason": "..."
}},
"correctness": {{"score": 1-5, "critical_error": true/false, "reason": "..."}},
"summary": "一句话总评：问题主要出在检索、内容缺失还是生成"
}}
"""
```

## 13. 旧项目（只读）：kb_chunk_studio 下的文件清单；service.py 里哪些函数会调用解析或 OCR

### 13.1 kb_chunk_studio 文件清单
来源: C:\Users\234393\Desktop\jap-cycle-poc\kb_chunk_studio

已确认文件:
1. __init__.py
2. api.py
3. draft_store.py
4. segment_cache.py
5. service.py

### 13.2 service.py 里哪些函数会调用解析或 OCR
先看直接依赖：
来源: C:\Users\234393\Desktop\jap-cycle-poc\kb_chunk_studio\service.py:23-27
```python
from kb_poc.parsing import parse_excel_file, parse_markdown_file, parse_pptx_file
from kb_poc.parsing.ppt_ocr import build_configured_ppt_ocr
```

再看调用点：
来源: C:\Users\234393\Desktop\jap-cycle-poc\kb_chunk_studio\service.py:622-662
```python
def _load_or_create_snapshot(context: ChunkStudioContext, source_file: str) -> ParsedDocument:
    ...
    if suffix == ".md":
        document = parse_markdown_file(source_path)
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        document = parse_excel_file(...)
    elif suffix == ".pptx":
        document = parse_pptx_file(...)
    ...
    return build_configured_ppt_ocr(
```

并且以下公开函数会经过 `_load_or_create_snapshot(...)`：
1. get_file_detail(...) ——证据: service.py:109
2. preview_file_detail(...) ——证据: service.py:138

结论：
1. 直接做解析 / OCR 的核心函数: `_load_or_create_snapshot()`
2. 会间接触发解析 / OCR 的公开函数:
   - get_file_detail()
   - preview_file_detail()

## 14. 顺带核对：新项目中“模型回复”的函数或方法是什么
按你这次额外要求，我把新项目里模型回包/回复相关的方法也一起标出来了。

### 14.1 纯文本补全回复入口
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:125-131
```python
def acompletion(...) -> StreamingCompletion
```

实现位置: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:100-108
```python
def acompletion(...):
    return _litellm_stream(...)
```

真正发给 LiteLLM 的位置: llm.py:194-203
```python
response = await litellm.acompletion(
    model=model,
    messages=messages,
    ...
    stream=True,
    stream_options={"include_usage": True},
    temperature=temperature,
)
```

### 14.2 ReAct 回合式模型回复入口
来源: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\contracts\model_gateway.py:133-141
```python
def astream_turn(...) -> StreamingAgentTurn
```

实现位置: C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\models\llm.py:117-127
```python
def astream_turn(...):
    return _litellm_turn_stream(...)
```

### 14.3 应用层把模型回复流给前端的主要入口
来源:
- C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:642
- C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\application\chat.py:697

已确认存在:
1. _stream_reply(...)
2. _stream_reply_impl(...)

它们是聊天主流程把模型 token / graph 事件转成 SSE 事件的核心入口。

一句话结论:
- 新项目里“模型回复”的底层方法是 `ModelGatewayPort.acompletion()`（纯文本流）和 `ModelGatewayPort.astream_turn()`（ReAct 回合流）
- 具体插件实现都在 `src\tap_ai\plugins\models\llm.py`

## 15. 和 遷移全.md 当前设计是否有冲突
基于这次只读核对，已确认的几个关键点如下:
1. 接口方法当前只有 GET/POST，没有 PATCH / DELETE。
2. 分页结构是 items / total / page / page_size。
3. 成功返回没有统一 data 外壳，业务错误才是 HTTP 200 + {code, message}。
4. 模型文本流读取方式是 `async for token in stream`，没有 `.text`。
5. 模型网关通过 `container.model_registry.get("model_gateway")` 获取。
6. acompletion 在启用 Langfuse 且配置完整时会被记录。
7. 旧项目 LocalAnswerer.answer() 的 top_k 不是写死值，而是“参数优先，否则取 self.retriever.config.top_k”。

如果后续 P1/P2 的提示词要严格贴合 backend 现状，最需要先改的就是:
1. PATCH / DELETE 设计要改成 POST .../update、POST .../delete 风格。
2. 不能假设成功返回统一包一层 data。
3. 评估判读读取模型返回时要按 StreamingCompletion 的真实读取方式写。
```



