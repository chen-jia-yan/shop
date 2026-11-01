## 终端命令输出

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git diff a1a06ac1 --stat
fatal: ambiguous argument 'a1a06ac1': unknown revision or path not in the working tree.
Use '--' to separate paths from revisions, like this:
'git <command> [<revision>...] -- [<file>...]'

(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git diff a1a06ac~1 --stat src/tap_ai/bootstrap.py
 src/tap_ai/bootstrap.py | 71 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 71 insertions(+)

(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git diff a1a06ac~1 -w --stat src/tap_ai/bootstrap.py
 src/tap_ai/bootstrap.py | 71 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 71 insertions(+)

(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git diff a1a06ac~1 src/tap_ai/bootstrap.py
diff --git a/src/tap_ai/bootstrap.py b/src/tap_ai/bootstrap.py
index 3919d33..889dcb9 100644
--- a/src/tap_ai/bootstrap.py
+++ b/src/tap_ai/bootstrap.py
@@ -21,6 +21,7 @@ from fastapi.responses import JSONResponse
 from tap_ai.config import plugins as plugin_config
 from tap_ai.container import AppContainer, container
 from tap_ai.core.errors import BusinessError
+from tap_ai.persistence.models import now_ts

logger = logging.getLogger(__name__)

@@ -369,6 +370,68 @@ def build_app(lifespan: Any = None, session_factory: Any = None) -> FastAPI:
 # /tap/ai/* 之下，并由各 api 路由在加入时挂载。
 _mount_routers(app)
```

## 新增代码片段（bootstrap.py）

```
# Library 评估服务（P3）：构造 EvalService，挂载到 app.state
if getattr(app_settings, "library_enabled", False):
    from tap_ai.application.library_chunks import ChunkReviewService
    from tap_ai.application.library_eval import EvalService
    from tap_ai.persistence.library_draft_repo import DraftRepo

    model_gateway = container.model_registry.get("model_gateway")
    library_chunk_service = ChunkReviewService(
        settings=app_settings,
        draft_repo=DraftRepo(session_factory),
        chunk_source=None,
        publisher=None,
    )
    library_eval_service = EvalService(
        settings=app_settings,
        session_factory=session_factory,
        prompt_library=default_prompt_library,
        model_gateway=model_gateway,
        qa_port=None,
    )
    app.state.library_chunk_service = library_chunk_service
    app.state.library_eval_service = library_eval_service
    lifecycle.callback(library_eval_service.shutdown)

if getattr(app_settings, "library_enabled", False) and getattr(
    app_settings, "library_kb_enabled", False
):
    from tap_ai.application.library_kb import KbAdminService
    from tap_ai.application.library_kb_worker import KbIngestWorker

    blob_store = container.storage_registry.get("blob_store")
    if blob_store is None:
        logger.warning("Library KB 未找到 blob_store，跳过 KB service/worker 装配")
    else:
        ingest = None
        if app_settings.library_kb_ingest_sink != "none":
            from tap_ai.plugins.ingest.sdk_ingest import build_ingest

            ingest = build_ingest(app_settings)
            closer = getattr(ingest, "close", None)
            if callable(closer):
                # 先登记 ingest.close，倒序关闭时才会先停 worker，再关共享 driver。
                lifecycle.callback(closer)
        app.state.library_kb_service = KbAdminService(
            settings=app_settings,
            session_factory=session_factory,
            storage=blob_store,
            ingest=ingest,
            inventory=None,
            audit_factory=AuditRepo,
        )
        if getattr(app_settings, "library_kb_worker_enabled", False):
            app.state.library_kb_worker = KbIngestWorker(
                settings=app_settings,
                session_factory=session_factory,
                storage=blob_store,
                ingest=ingest,
                clock=now_ts,
            )
            lifecycle.callback(app.state.library_kb_worker.stop, timeout=35)

return app

@@ -516,11 +579,19 @@ def _mount_routers(app: FastAPI) -> None:

    app.include_router(library_chunks_router, tags=["library"])
    app.include_router(library_eval_router, tags=["library-eval"])

    # P1：三个插座一律注入 None，后续阶段由同事替换为真实服务。
    app.state.qa_answer_port = None
    app.state.chunk_source_port = None
    app.state.chunk_publish_port = None

    if getattr(settings, "library_enabled", False) and getattr(
        settings, "library_kb_enabled", False
    ):
        from tap_ai.api.library_kb import router as library_kb_router

        app.include_router(library_kb_router, tags=["library-kb"])

def _register_capabilities(container: AppContainer, settings) -> None:
    """把模型能力注册进容器，并按需做启动联调验证。"""
```

## 后续终端命令

```
(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> git diff a1a06ac~1 src/tap_ai/main.py src/tap_ai/config/settings.py | Select-String
--- a/src/tap_ai/config/settings.py
--- a/src/tap_ai/main.py

(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> Test-Path .env
False

(tap-ai-backend) PS C:\Users\234393\Desktop\tap-ai-backend> Select-String -Path src/tap_ai/config/settings.py -Pattern "gpt-5.4"
src/tap_ai/config\settings.py:23:DEFAULT_MODEL = "openai/GPT-5.4"
src/tap_ai/config\settings.py:24:DEFAULT_SUMMARIZER_MODEL = "openai/GPT-5.4"
```
