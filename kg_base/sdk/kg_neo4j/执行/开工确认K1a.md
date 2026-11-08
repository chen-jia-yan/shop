# 开工前确认文档
## 1. src/tap_ingest_sdk/__init__.py 全文
```python
"""TAP content ingestion SDK.

V1 scope: synchronous pipeline for parsing, OCR, chunking, embedding and indexing.
"""
from __future__ import annotations

from .client import TapIngestClient
from .config import ChunkConfig, IngestConfig, ParserConfig
from .env_config import load_env_file
from .events import IngestEvent
from .exceptions import (
    ChunkingError,
    ConfigurationError,
    EmbeddingError,
    NonRetriableSinkError,
    OCRError,
    ParseError,
    PipelineCancelledError,
    RetriableSinkError,
    SinkError,
    SourceValidationError,
    TapIngestError,
    UnsupportedFileTypeError,
)
from .models import (
    DocumentChunk,
    FileIngestResult,
    IngestReport,
    ProcessedDocument,
    SourceDocument,
)
from .protocols import (
    Chunker,
    DocumentParser,
    DocumentSink,
    EmbeddingProvider,
    OCRLine,
    OCRProvider,
    ProgressListener,
    SinkResult,
)

__all__ = [
    "TapIngestClient",
    "IngestConfig",
    "ParserConfig",
    "ChunkConfig",
    "load_env_file",
    "SourceDocument",
    "ProcessedDocument",
    "DocumentChunk",
    "FileIngestResult",
    "IngestReport",
    "IngestEvent",
    "TapIngestError",
    "ConfigurationError",
    "SourceValidationError",
    "UnsupportedFileTypeError",
    "ParseError",
    "OCRError",
    "ChunkingError",
    "EmbeddingError",
    "SinkError",
    "RetriableSinkError",
    "NonRetriableSinkError",
    "PipelineCancelledError",
    "DocumentParser",
    "OCRProvider",
    "OCRLine",
    "Chunker",
    "EmbeddingProvider",
    "DocumentSink",
    "SinkResult",
    "ProgressListener",
]
```

### 已确认事实
- 当前 `__init__.py` 在模块顶部直接导入了 `client / config / events / exceptions / models / protocols`。
- 当前还不是 lazy import 结构。
- 当前 `__all__` 已明确列出 31 个对外暴露名，后续若改 lazy import，按任务要求必须保持一个不多、一个不少。

---

## 2. 命令
```bash
git grep -n -E "KB_EMBEDDING_ENABLED|KB_COPILOT|KB_AOAI" -- src tests README.md
```
### 原始输出
```
README.md:102:- Integrated vectorization (仅 Azure OpenAI): 设置 `KB_AOAI_ENDPOINT`、`KB_AOAI_EMBEDDING_DEPLOYMENT` 后索引绑定 vectorizer，模型须与入库 embedding 一致。
README.md:118:| `KB_AOAI_ENDPOINT` / `KB_AOAI_EMBEDDING_DEPLOYMENT` / `KB_AOAI_EMBEDDING_MODEL` / `KB_AOAI_API_KEY` | 可选，配置索引的 Azure OpenAI vectorizer |
src/tap_ingest_sdk/embeddings/_internal/config.py:32:        embedding_enabled=os.getenv("KB_EMBEDDING_ENABLED", "1").strip().lower()
src/tap_ingest_sdk/embeddings/_internal/config.py:35:        copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
src/tap_ingest_sdk/sinks/_internal/config.py:102:        aoai_endpoint=os.getenv("KB_AOAI_ENDPOINT"),
src/tap_ingest_sdk/sinks/_internal/config.py:103:        aoai_embedding_deployment=os.getenv("KB_AOAI_EMBEDDING_DEPLOYMENT"),
src/tap_ingest_sdk/sinks/_internal/config.py:104:        aoai_embedding_model=os.getenv("KB_AOAI_EMBEDDING_MODEL")
src/tap_ingest_sdk/sinks/_internal/config.py:106:        aoai_api_key=os.getenv("KB_AOAI_API_KEY"),
```

### 已确认事实
- `KB_AOAI_*` 目前只在 `README.md` 和 `src/tap_ingest_sdk/sinks/_internal/config.py` 中命中。
- `KB_EMBEDDING_ENABLED`、`KB_COPILOT_PROVIDER_TYPE` 目前都在 `src/tap_ingest_sdk/embeddings/_internal/config.py` 里读取。

---

## 3. 命令
```bash
git grep -n -E "embedding_enabled|copilot_provider_type|aoai_" -- src tests
```
### 原始输出
```
src/tap_ingest_sdk/embeddings/_internal/config.py:20:    embedding_enabled: bool = True
src/tap_ingest_sdk/embeddings/_internal/config.py:22:    copilot_provider_type: str | None = None
src/tap_ingest_sdk/embeddings/_internal/config.py:32:        embedding_enabled=os.getenv("KB_EMBEDDING_ENABLED", "1").strip().lower()
src/tap_ingest_sdk/embeddings/_internal/config.py:35:        copilot_provider_type=os.getenv("KB_COPILOT_PROVIDER_TYPE"),
src/tap_ingest_sdk/sinks/_internal/config.py:49:    embedding_enabled: bool = True
src/tap_ingest_sdk/sinks/_internal/config.py:56:    aoai_endpoint: str | None = None
src/tap_ingest_sdk/sinks/_internal/config.py:57:    aoai_embedding_deployment: str | None = None
src/tap_ingest_sdk/sinks/_internal/config.py:58:    aoai_embedding_model: str | None = None
src/tap_ingest_sdk/sinks/_internal/config.py:59:    aoai_api_key: str | None = None
src/tap_ingest_sdk/sinks/_internal/config.py:63:    return bool(self.aoai_endpoint and self.aoai_embedding_deployment and self.aoai_embedding_model)
src/tap_ingest_sdk/sinks/_internal/config.py:102:        aoai_endpoint=os.getenv("KB_AOAI_ENDPOINT"),
src/tap_ingest_sdk/sinks/_internal/config.py:103:        aoai_embedding_deployment=os.getenv("KB_AOAI_EMBEDDING_DEPLOYMENT"),
src/tap_ingest_sdk/sinks/_internal/config.py:104:        aoai_embedding_model=os.getenv("KB_AOAI_EMBEDDING_MODEL")
src/tap_ingest_sdk/sinks/_internal/config.py:106:        aoai_api_key=os.getenv("KB_AOAI_API_KEY"),
src/tap_ingest_sdk/sinks/azure.py:49:        aoai_endpoint=env.aoai_endpoint,
src/tap_ingest_sdk/sinks/azure.py:50:        aoai_embedding_deployment=env.aoai_embedding_deployment,
src/tap_ingest_sdk/sinks/azure.py:51:        aoai_embedding_model=env.aoai_embedding_model,
src/tap_ingest_sdk/sinks/azure.py:52:        aoai_api_key=env.aoai_api_key,
src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:43:    if not (settings.embedding_enabled and settings.embedding_model and settings.copilot_provider_base_url):
src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:118:        resource_url=settings.aoai_endpoint,
src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:119:        deployment_name=settings.aoai_embedding_deployment,
src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:120:        model_name=settings.aoai_embedding_model,
src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:121:        api_key=settings.aoai_api_key or None,
tests/test_azure_index.py:28:        aoai_endpoint="[https://x.openai.azure.com](https://x.openai.azure.com)",
tests/test_azure_index.py:29:        aoai_embedding_deployment="emb",
tests/test_azure_index.py:30:        aoai_embedding_model="text-embedding-3-small",
```

### 逐项说明：每个字段在哪里被读取、被谁使用
#### 3.1 embedding_enabled
- 定义位置1：`src/tap_ingest_sdk/embeddings/_internal/config.py:20`
- 环境变量读取位置：`src/tap_ingest_sdk/embeddings/_internal/config.py:32`
- 定义位置2：`src/tap_ingest_sdk/sinks/_internal/config.py:49`
- 使用位置：`src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:43`

if not (settings.embedding_enabled and settings.embedding_model and settings.copilot_provider_base_url):
    return None
### 已确认事实：

- `embedding_enabled` 不是“完全未使用”。
- 它会被 `azure_search_store.py` 的 `_build_embedding_client()` 读取，用于决定是否构造 `EmbeddingClient`。
- 目前从 grep 证据看，`embeddings/_internal/config.py` 里的 `embedding_enabled` 读取，并没有直接看到其他使用点；它是否仅为兼容保留，需要后续改动时最小化处理。

## 3.2 copilot_provider_type

- 定义位置：`src/tap_ingest_sdk/embeddings/_internal/config.py:22`
- 环境变量读取位置：`src/tap_ingest_sdk/embeddings/_internal/config.py:35`
- grep 结果中未发现其他读取/使用位置。

结论：`copilot_provider_type` 未使用。

## 3.3 aoai_endpoint

- 定义位置：`src/tap_ingest_sdk/sinks/_internal/config.py:56`
- 环境变量读取位置：`src/tap_ingest_sdk/sinks/_internal/config.py:102`
- 传递位置：`src/tap_ingest_sdk/sinks/azure.py:49`
- 使用位置：`src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:118`

```
resource_url=settings.aoai_endpoint,
```

## 3.4 aoai_embedding_deployment

- 定义位置：`src/tap_ingest_sdk/sinks/_internal/config.py:57`
- 环境变量读取位置：`src/tap_ingest_sdk/sinks/_internal/config.py:103`
- 传递位置：`src/tap_ingest_sdk/sinks/azure.py:50`
- 使用位置：`src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:119`

```
deployment_name=settings.aoai_embedding_deployment,
```

## 3.5 aoai_embedding_model

- 定义位置：`src/tap_ingest_sdk/sinks/_internal/config.py:58`
- 环境变量读取位置：`src/tap_ingest_sdk/sinks/_internal/config.py:104`
- 传递位置：`src/tap_ingest_sdk/sinks/azure.py:51`
- 使用位置：`src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:120`

```
model_name=settings.aoai_embedding_model,
```

## 3.6 aoai_api_key

- 定义位置：`src/tap_ingest_sdk/sinks/_internal/config.py:59`
- 环境变量读取位置：`src/tap_ingest_sdk/sinks/_internal/config.py:106`
- 传递位置：`src/tap_ingest_sdk/sinks/azure.py:52`
- 使用位置：`src/tap_ingest_sdk/sinks/_internal/azure_search_store.py:121`

---

## 4. 命令

```
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import pptx; print(pptx.__version__)"
```

### 原始输出

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'pptx'
```

### 已确认事实

- 当前后端 `.venv` 中没有安装 `pptx`。
- 这和任务背景是吻合的：这次就是要把 `kg_schema / lexicon` 从 `parsers / python-pptx` 依赖链里解开，避免轻量模块被 `pptx` 卡住。

---

## 5. pyproject.toml 中 [project] 的 dependencies 和 optional-dependencies 原文

### 原始摘录
[project]
name = "tap-ingest-sdk"
version = "0.2.0"
description = "TAP content ingestion SDK"
authors = [
  {name = "TAP Team", email = "tap.team@fwd.com"}
]
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "pydantic (>=2.0,<3.0.0)",
  "python-dotenv (>=1.0,<2.0.0)",
  "azure-search-documents (>=11.6,<12.0.0)",
  "azure-identity (>=1.17,<2.0.0)",
  "paddleocr (>=2.7,<3.0.0)",
  "paddlepaddle (>=2.6,<3.0.0)",
  "setuptools (>=65)",
  "Pillow (>=10.0,<11.0.0)",
  "openai (>=1.0,<2.0.0)",
  "pypdf (>=4.0,<5.0.0)",
  "openpyxl (>=3.1,<4.0.0)",
  "python-pptx (>=0.6,<1.0.0)",
  "python-docx (>=1.1,<2.0.0)",
  "click (>=8.1,<9.0.0)",
]

[project.optional-dependencies]
neo4j = [
  "neo4j (>=6.0,<7.0.0)",
]


# 验证结果
# 终端日志记录

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 15
src/tap_ai/persistence/db.py:13: in <module>
    engine = create_async_engine()
.venv/Lib/site-packages/sqlalchemy/ext/asyncio/engine.py:120: in create_async_engine
    sync_engine = _create_engine(url, **kw)
.venv/Lib/site-packages/sqlalchemy/util/deprecations.py:281: in warned
    return fn(*args, **kwargs)  # type: ignore[no-any-return]
.venv/Lib/site-packages/sqlalchemy/engine/create.py:617: in create_engine
    dbapi = dbapi_meth(**dbapi_args)
.venv/Lib/site-packages/sqlalchemy/dialects/mysql/aiomysql.py:229: in import_dbapi
    __import__("aiomysql"), __import__("pymysql")
E   ModuleNotFoundError: No module named 'aiomysql'
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'tap_ingest_sdk'
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m ruff check src tests 2>&1 | Select-Object -Last 30
FLY002 Consider `"create/modify/debug/review/ask/other"` instead of string join
--> tests\unit\test_intent_extractor.py:212:20
```

```
210         from tap_ai.core.intent_extractor import _VALID_ACTION_TYPES
211
212         expected = "/".join(
213             ["create", "modify", "debug", "review", "ask", "other"]
214         )
215         assert f"action_type 𝚊𝚞𝚝𝚑𝚘𝚛𝚒𝚣𝚎𝚍: {expected}" in INTENT_SYSTEM_PROMPT
216         assert set(expected.split("/")) == set(_VALID_ACTION_TYPES)
```

> 
> help: Replace with `"create/modify/debug/review/ask/other"`

```
RUF012 Mutable default value for class attribute
--> tests/unit/test_library_kb_ingest_plugin.py:38:30
```

```
36 class _FakeClient:
37     report = _FakeReport(items=(_FakeItem(status="succeeded", document_id="doc-1"),))
38     calls: list[list[Any]] = []
39
40     def __init__(self, **kwargs: Any) -> None:
```

> 
> help: Consider initializing in `__init__` or annotating with `typing.ClassVar`

```
Found 7 errors.
[*] 3 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git grep -n -E "KB_COPILOT|KB_AOAI|KB_KG_LLM_ENABLED|KB_EMBEDDING_ENABLED|NO_AUTOLOAD"
src/tap_ai/plugins/ingest/__init__.py:8:os.environ.setdefault("TAP_INGEST_SDK_NO_AUTOLOAD_ENV", "1")
```

> 
> 扫描了 279 个文件，发现 0 处问题

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> uv run python C:/Users/234393/Desktop/check_chars.py src tests
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> Set-Content -Path .env -Value "TAP_AI_KB_EMBEDDING_MODEL=should-not-load" -Encoding utf8
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys, os; sys.path.insert(0,'src'); import tap_ingest_sdk; print(os.getenv('TAP_AI_KB_EMBEDDING_MODEL'))"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'tap_ingest_sdk'
```

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> Remove-Item .env
```
