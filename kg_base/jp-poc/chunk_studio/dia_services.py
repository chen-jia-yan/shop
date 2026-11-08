"""
知识库后台控制面服务（KnowledgeAdminService）

说明：
- 
"""

from pathlib import Path
from collections.abc import Iterable

from .filters import build_enqueue_plan
from .runtime.heavy import is_heavy_path

from kb_poc.config import KBSettings

from .azure_index_repository import AzureDocumentIndexRepository
from .index_repository import DocumentIndexRepository
from .ingestion import build_chunks_for_path, rebuild_all_documents
from .json_store import JsonAdminStore
from .local_index_repository import LocalDocumentIndexRepository
# [改] 补上 ManagedJob：原 import 缺它，但 list_jobs / _ingest_file / rebuild_all 都在用
from .models import AuditEvent, DocumentVersion, ManagedBatch, ManagedDocument, ManagedJob, new_id, utc_now
from .state_store import batch_progress, enqueue_files, init_db, list_batches as list_sqlite_batches
from .storage import ManagedFileStorage

# 统一任务类型常量：  两者按 job_type 过滤会分裂，这里统一成一个来源
JOB_TYPE_INGEST_DOCUMENT = "ingest_document"
# [改] 操作者默认值：原来默认成无意义的 "流程图"，归属字段从源头就不可信，改成 "system"
DEFAULT_ACTOR = "system"


class KnowledgeAdminService:
    def __init__(self, settings: KBSettings | None = None):
        self.settings = settings or KBSettings.load()
        self.source_dir = self.settings.resolve(self.settings.source_dir)
        self.index_path = self.settings.resolve(self.settings.index_path)
        self.admin_root = self.settings.project_root / "data" / "kb_admin"
        self.store = JsonAdminStore(self.admin_root)
        self.storage = ManagedFileStorage(self.source_dir)
        self.state_db_path = self.admin_root / "state.db"
        init_db(self.state_db_path)
        self.index_repo = self._build_index_repo()

    # ---------- 读查询 ----------

    def list_documents(self, *, include_deleted: bool = False, status: str | None = None,
                        query: str | None = None, offset: int = 0, limit: int | None = None) -> dict:
        documents = self.store.list_documents()
        if not include_deleted:
            documents = [item for item in documents if item.status != "deleted"]
        if status:
            documents = [item for item in documents if item.status == status]
        if query:
            lowered = query.strip().lower()
            documents = [item for item in documents
                         if lowered in item.title.lower() or lowered in item.file_name.lower()]
        documents.sort(key=lambda item: item.updated_at, reverse=True)
        total = len(documents)
        # limit 为 None 时 offset+limit 会抛 TypeError，这里单独处理“取到末尾”
        page = documents[offset:] if limit is None else documents[offset: offset + limit]
        return {"items": [self._serialize_document(item) for item in page],
                "total": total, "offset": offset, "limit": limit}

    # 获取单个文档详情
    def get_document(self, document_id: str) -> dict | None:
        document = self._find_document(document_id)
        if document is None:
            return None
        payload = self._serialize_document(document)
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(
            entity_type="document", entity_id=document_id, limit=50)]
        return payload

    def list_jobs(self, *, batch_id: str | None = None, document_id: str | None = None,
                  status: str | None = None) -> dict:
        jobs = self.store.list_jobs()
        sqlite_batches: set[str] = set()
        if batch_id:
            jobs = [item for item in jobs if item.batch_id == batch_id]
            sqlite_batches.add(batch_id)
        if document_id:
            jobs = [item for item in jobs if item.document_id == document_id]
        if status:
            jobs = [item for item in jobs if item.status == status]
        if not batch_id:
            for batch in self.list_batches().get("items", []):
                # [改] str(x) or "" 对 None 会得到 "None"，改成 str(x or "")
                batch_value = str(batch.get("batch_id") or "")
                if batch_value:
                    sqlite_batches.add(batch_value)
        sqlite_only_jobs: list[dict] = []
        for current_batch_id in sorted(sqlite_batches):
            sqlite_only_jobs.extend(self._sqlite_jobs_payload(current_batch_id))
        if document_id:
            sqlite_only_jobs = [item for item in sqlite_only_jobs if item.get("document_id") == document_id]
        if status:
            sqlite_only_jobs = [item for item in sqlite_only_jobs if item.get("status") == status]
        persisted_job_ids = {item.job_id for item in jobs}
        jobs.extend(ManagedJob.from_dict(item) for item in sqlite_only_jobs
                    if item.get("job_id") not in persisted_job_ids)
        jobs.sort(key=lambda item: item.updated_at, reverse=True)
        return {"items": [item.to_dict() for item in jobs]}

    def get_job(self, job_id: str) -> dict | None:
        job = next((item for item in self.store.list_jobs() if item.job_id == job_id), None)
        if job is None:
            return None
        payload = job.to_dict()
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(
            entity_type="job", entity_id=job_id, limit=50)]
        return payload

    def list_batches(self) -> dict:
        batches = self.store.list_batches()
        sqlite_batch_ids: set[str] = set()
        items: list[dict] = []
        for item in batches:
            payload = item.to_dict()
            try:
                sqlite_payload = self._sqlite_batch_payload(item.batch_id)
                sqlite_batch_ids.add(item.batch_id)
                payload.update(sqlite_payload)
            except ValueError:
                pass
            items.append(payload)
        for sqlite_item in self._list_sqlite_batches():
            batch_id = str(sqlite_item.get("batch_id") or "")  
            if not batch_id or batch_id in sqlite_batch_ids:
                continue
            items.append(sqlite_item)
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"items": items}

    def get_batch(self, batch_id: str) -> dict | None:
        try:
            payload = self._sqlite_batch_payload(batch_id)
        except ValueError:
            batch = next((item for item in self.store.list_batches() if item.batch_id == batch_id), None)
            if batch is None:
                return None
            payload = batch.to_dict()
        payload["jobs"] = [item.to_dict() for item in self.store.list_jobs() if item.batch_id == batch_id]
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(
            entity_type="batch", entity_id=batch_id, limit=50)]
        return payload

    def list_audit_events(self, *, entity_type: str | None = None, entity_id: str | None = None,
                          limit: int = 100) -> dict:
        return {"items": [item.to_dict() for item in self.store.list_audit_events(
            entity_type=entity_type, entity_id=entity_id, limit=limit)]}

    # 兼容 UI 的失败文件面板，直接从 sqlite files 表读取失败/死亡文件。
    def list_failed_files(self) -> dict:
        with self._state_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, batch_id, batch_name, path, status, stage, attempts, crash_count, error, updated_at
                FROM files
                WHERE status IN ('failed', 'dead')
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        items = [self._serialize_failed_file_row(row) for row in rows]
        return {
            "items": items,
            "total": len(items),
            "error_types": sorted({item["error_type"] for item in items if item.get("error_type")}),
        }

    # 按 file_id 或错误类型重试失败文件，保持 UI 的批量重试入口可用。
    def retry_failed_files(self, *, file_ids: list[int] | list[str] | None = None,
                           error_types: list[str] | None = None) -> dict:
        normalized_ids = {int(item) for item in (file_ids or []) if str(item).strip().isdigit()}
        normalized_error_types = {str(item).strip().lower() for item in (error_types or []) if str(item).strip()}
        with self._state_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, batch_id, status, error
                FROM files
                WHERE status IN ('failed', 'dead')
                """
            ).fetchall()
            matched_ids: list[int] = []
            touched_batches: set[str] = set()
            for row in rows:
                file_id = int(row["id"])
                error_type = self._classify_failed_file_error(str(row["error"] or ""))
                if (normalized_ids and file_id in normalized_ids) or \
                   (normalized_error_types and error_type in normalized_error_types):
                    matched_ids.append(file_id)
                    touched_batches.add(str(row["batch_id"] or ""))
            if not matched_ids:
                return {"retried": 0, "file_ids": [], "batch_ids": []}
            placeholders = ",".join("?" for _ in matched_ids)
        
            connection.execute(
                f"""
                UPDATE files
                SET status = 'pending', stage = 'pending', attempts = 0, crash_count = 0, error = NULL, updated_at = ?
                WHERE id IN ({placeholders})
                """,
                (utc_now(), *matched_ids),
            )
            for batch_id in touched_batches:
                if not batch_id:
                    continue
                progress = batch_progress(batch_id, db_path=self.state_db_path)
                connection.execute(
                    "UPDATE batches SET status = ? WHERE batch_id = ?",
                    (str(progress["status"]), batch_id),
                )
        return {"retried": len(matched_ids), "file_ids": matched_ids,
                "batch_ids": sorted(batch_id for batch_id in touched_batches if batch_id)}

    # ---------- 异步队列入库路径 ----------

    # 标准上传，走批量排队 batch
    def upload_files(self, files: list[tuple[str, bytes]], *, requested_by: str = DEFAULT_ACTOR,
                     batch_name: str = "") -> dict:
        saved_paths: list[str] = []
        saved_names: list[str] = []
        for filename, content in files:
            file_path, _ = self.storage.save_upload(filename, content)
            saved_paths.append(str(file_path))
            saved_names.append(str(filename).replace("\\", "/").strip().lstrip("/"))
        return self.enqueue_saved_files(saved_paths, saved_names=saved_names,
                                        requested_by=requested_by, batch_name=batch_name)

    # 把已经落盘的文件创建 batch 批量任务，并拆分子批 sub-batch
    def enqueue_saved_files(self, saved_paths: list[str], *, saved_names: list[str] | None = None,
                            requested_by: str = DEFAULT_ACTOR, batch_name: str = "") -> dict:
        if not saved_paths:
            raise ValueError("No uploaded files were saved")
        enqueue_plan = self._build_enqueue_plan(saved_paths, saved_names=saved_names)
        queue_paths = enqueue_plan["queue_paths"]
        skipped_items = enqueue_plan["skipped_items"]
        retry_items = enqueue_plan["retry_items"]
        queued_items = enqueue_plan["queued_items"]
        filtered_items = enqueue_plan.get("filtered_items", [])
        duplicate_skip_count = len(skipped_items)
        if not queue_paths:
            scan_summary = dict(enqueue_plan["scan_summary"])
            normalized_names = saved_names or [Path(path).name for path in saved_paths]
            normalized_batch_name = batch_name.strip() or f"{normalized_names[0]} 等 {len(normalized_names)} 个文件"
            items = [*retry_items, *skipped_items, *filtered_items]
            return {
                "batch_id": None,
                "batch_name": normalized_batch_name,
                "batch": None,
                "items": items,
                "queued_items": [],
                "retry_items": retry_items,
                "skipped_items": skipped_items,
                "filtered_items": filtered_items,
                "duplicate_skip_count": duplicate_skip_count,
                "scan_summary": {**scan_summary, "queue_file": 0, "duplicate_skip_count": duplicate_skip_count},
                "sub_batches": [],
                "message": self._build_upload_message(scan_summary),
            }
        batch_id = new_id("batch")
        normalized_names = [item["file_name"] for item in queued_items] or \
            (saved_names or [Path(path).name for path in saved_paths])
        normalized_batch_name = batch_name.strip() or f"{normalized_names[0]} 等 {len(normalized_names)} 个文件"
        scan_summary = dict(enqueue_plan["scan_summary"])
        child_batches = self._split_sub_batches(queue_paths)
        batch = ManagedBatch(
            batch_id=batch_id,
            batch_name=normalized_batch_name,
            file_count=len(queue_paths),
            status="pending",
            target_mode="incremental",
            batch_index=1,
            batch_total=max(1, len(child_batches)),
            total_size_bytes=int(scan_summary["total_size_bytes"]),
            heavy_file_count=int(scan_summary["heavy_file_count"]),
            scan_summary=scan_summary,
        )
        self._append_batch(batch)
        sub_batches: list[dict] = []
        for index, child_paths in enumerate(list(child_batches), start=1):
            child_batch_id = new_id("subbatch")
            child_label = f"{normalized_batch_name}-子批 {index}/{len(child_batches)}"
            enqueue_files(child_batch_id, child_paths, db_path=self.state_db_path, batch_name=child_label)
            child_batch = ManagedBatch(
                batch_id=child_batch_id,
                parent_batch_id=batch_id,
                batch_name=child_label,
                file_count=len(child_paths),
                status="pending",
                target_mode="incremental",
                batch_index=index,
                batch_total=len(child_batches),
                total_size_bytes=sum(Path(path).stat().st_size for path in child_paths if Path(path).exists()),
                heavy_file_count=sum(1 for path in child_paths if self._is_heavy_file(Path(path))),
                scan_summary=self._pre_scan_files(child_paths),
            )
            self._append_batch(child_batch)
            sub_batches.append(child_batch.to_dict())
        # [改] 审计移到循环外，对父批记一次（原来在子批循环里、且是非法的位置参数+未定义入参）
        self._audit("batch", batch.batch_id, "batch_created",
                    f"Batch enqueued for {len(queue_paths)} file(s)",
                    {"batch": batch.to_dict(), "items": [*queued_items, *retry_items]})
        return {
            "batch_id": batch_id,
            "batch_name": normalized_batch_name,
            "batch": batch.to_dict(),
            "items": [*queued_items, *retry_items, *skipped_items, *filtered_items],
            "queued_items": queued_items,
            "retry_items": retry_items,
            "skipped_items": skipped_items,
            "filtered_items": filtered_items,
            "duplicate_skip_count": duplicate_skip_count,
            "scan_summary": scan_summary,
            "sub_batches": sub_batches,
            "message": self._build_upload_message(scan_summary),
        }

    # ---------- 同步单文档入库路径 ----------

    def replace_document(self, document_id: str, filename: str, content: bytes | None, *,
                         file_path: Path | None = None, requested_by: str = DEFAULT_ACTOR) -> dict:
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        return self._ingest_file(filename, content, existing=document,
                                 file_path=file_path, requested_by=requested_by)

    def delete_document(self, document_id: str, *, hard_delete: bool = False) -> dict:
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        deleted_chunks = self.index_repo.delete_document_chunks(document_id)
        document.chunk_count = 0
        document.status = "deleted"
        document.deleted_at = utc_now()
        document.updated_at = utc_now()
        self._upsert_document(document)
        file_path = self.source_dir / document.relative_path
        if hard_delete and file_path.exists():
            file_path.unlink()
       
        self._audit("document", document.document_id, "document_deleted",
                    "Document deleted from management layer", {"hard_delete": hard_delete})
        return {**self._serialize_document(document), "deleted_chunk_count": deleted_chunks}

    def rebuild_document(self, document_id: str, *, requested_by: str = DEFAULT_ACTOR) -> dict:
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        file_path = self.source_dir / document.relative_path
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))
        return self._ingest_file(document.file_name, content=None, existing=document,
                                 file_path=file_path, requested_by=requested_by)

    def rebuild_all(self, *, requested_by: str = DEFAULT_ACTOR) -> dict:
        job = ManagedJob(job_id=new_id("job"), job_type="rebuild_all", status="running",
                         stage="queued", target_mode="full", requested_by=requested_by)
        self._append_job(job)
        self._audit("job", job.job_id, "job_created", "Full rebuild job created", {"target_mode": "full"})
        try:
            self._update_job(job, stage="rebuilding", message="Running full ingest_directory rebuild")
            stats = rebuild_all_documents(self.source_dir, self.index_path, self.settings)
            self._sync_documents_after_full_rebuild()
            self._finish_job(job, status="completed", stage="completed", message="Full rebuild completed")
            self._audit("job", job.job_id, "job_completed", "Full rebuild completed", {})
            return {"job": job.to_dict(), "stats": stats.model_dump()}
        except Exception as exc:
            self._finish_job(job, status="failed", stage="failed", message=str(exc), error_message=str(exc))
            self._audit("job", job.job_id, "job_failed", "Full rebuild failed", {"error": str(exc)})
            raise

    # 重试失败任务
    def retry_job(self, job_id: str) -> dict:
        job = next((item for item in self.store.list_jobs() if item.job_id == job_id), None)
        if job is None:
            if job_id.startswith("sqlite_file_"):
                return self.retry_worker_file(job_id)
            raise FileNotFoundError(job_id)
        if job.job_type == "rebuild_all":
            return self.rebuild_all(requested_by="retry")
        if not job.document_id:
            raise FileNotFoundError(job_id)
        return self.rebuild_document(job.document_id, requested_by="retry")

    def retry_worker_file(self, job_id: str, *, requested_by: str = "retry") -> dict:
        file_id = self._parse_sqlite_file_job_id(job_id)
        with self._state_connection() as connection:
            
            row = connection.execute(
                "SELECT id, batch_id, batch_name, path, status FROM files WHERE id = ?",
                (file_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(job_id)
            path = Path(str(row["path"] or ""))
            if not path.exists():
                raise FileNotFoundError(str(path))
            batch_id = str(row["batch_id"] or "")
            batch_name = str(row["batch_name"] or "")
            enqueue_files(batch_id, paths=[str(path)], db_path=self.state_db_path, batch_name=batch_name)
        return {
            "job_id": job_id,
            "file_id": file_id,
            "batch_id": batch_id,
            "file_name": path.name,
            "path": str(path),
            "status": "pending",
            "stage": "queued",
            "requested_by": requested_by,
        }

    # 单文档入库的核心实现：解析 -> 切片 -> 三段式 upsert 入索引
    # TODO: 后端兜底的增量重建（前端/进程异常时也能单独触发）尚未实现，见文末“未改”说明
    def _ingest_file(self, filename: str, content: bytes | None, *, batch_id: str | None = None,
                     existing: ManagedDocument | None = None, persist_job_history: bool = True,
                     file_path: Path | None = None, requested_by: str = DEFAULT_ACTOR) -> dict:
        document = existing or ManagedDocument(
            document_id=new_id("doc"), title=Path(filename).stem,
            file_name=Path(filename).name, relative_path="")
        if content is None and file_path is None:
            raise ValueError("Either content or file_path is required")
        file_hash = self.storage.file_hash(content) if content is not None \
            else self.storage.file_hash_for_path(file_path)
        # 幂等：活跃版本哈希一致且文档处于 active，视作未变更，直接跳过
        active = document.active_version()
        if active and active.file_hash == file_hash and document.status == "active":
            document.chunk_count = active.chunk_count
            self._audit("document", document.document_id, "document_skipped",
                        "Skipped unchanged document", {"file_hash": file_hash})
            return {"document": self._serialize_document(document), "job": None,
                    "file_name": filename, "file_hash": file_hash, "size_bytes": 0}
        version = DocumentVersion(version_id=new_id("ver"), file_name=Path(filename).name,
                                  storage_path="", file_hash=file_hash, size_bytes=0)
        job = ManagedJob(job_id=new_id("job"), job_type=JOB_TYPE_INGEST_DOCUMENT, status="running",
                         stage="queued", target_mode="incremental", document_id=document.document_id,
                         requested_by=requested_by, batch_id=batch_id)
        if persist_job_history:
            self._append_job(job)
            self._link_job(document, job.job_id)
            self._audit("job", job.job_id, "job_created",
                        "Incremental document ingest job created", {"document_id": document.document_id})
        else:
            document.latest_job_id = job.job_id
        cleanup_path: Path | None = None
        try:
            saved_path = file_path
            if saved_path is None:
                saved_path, relative_path = self.storage.save_upload(filename, content)
                cleanup_path = saved_path  # 新落盘的临时文件，失败时需清理
            else:
                relative_path = str(saved_path.relative_to(self.source_dir)) \
                    if saved_path.is_relative_to(self.source_dir) else str(saved_path)
            version.storage_path = str(saved_path)
            document.file_name = Path(filename).name
            document.title = Path(filename).stem
            document.relative_path = relative_path
            document.status = "processing"
            document.deleted_at = None
            document.last_error = ""
        
            document.versions.append(version)
            document.active_version_id = version.version_id
            self._upsert_document(document)
            self._update_job(job, stage="parsing", message="File saved, parsing content")
            full_chunks = build_chunks_for_path(saved_path, self.settings, include_ocr=True)
            version.text_chunk_count = sum(
                1 for chunk in full_chunks
                if not str(chunk.metadata.source_kind or "").startswith("ocr:"))
            version.ocr_chunk_count = max(0, len(full_chunks) - version.text_chunk_count)
            version.chunk_count = len(full_chunks)
            document.chunk_count = len(full_chunks)
            version.status = "parsed"
            self._update_job(job, stage="indexing", message=f"Upserting {len(full_chunks)} chunks")
            # 三段式 upsert：begin 占位 -> append 批量写 -> finalize 提交，保证替换的原子性
            self.index_repo.begin_document_upsert(document.document_id, version.version_id)
            self.index_repo.append_document_chunks(document.document_id, version.version_id, full_chunks)
            self.index_repo.finalize_document_upsert(document.document_id, version.version_id)
            version.status = "indexed"
            document.status = "active"
            self._upsert_document(document)
            if persist_job_history:
                self._finish_job(job, status="completed", stage="completed",
                                 message="Document indexed successfully")
                self._audit("job", job.job_id, "job_completed",
                            "Document indexed successfully", {"chunk_count": len(full_chunks)})
            return {"document": self._serialize_document(document), "job": job.to_dict(),
                    "file_name": filename, "file_hash": file_hash, "size_bytes": version.size_bytes}
        except Exception as exc:
            # 标记失败 + 记录错误 + 清理孤儿文件 + 抛出
            document.status = "failed"
            document.last_error = str(exc)
            document.updated_at = utc_now()
            self._upsert_document(document)
            if persist_job_history:
                self._finish_job(job, status="failed", stage="failed",
                                 message=str(exc), error_message=str(exc))
                self._audit("job", job.job_id, "job_failed", "Document ingest failed", {"error": str(exc)})
            if cleanup_path is not None and Path(cleanup_path).exists():
                Path(cleanup_path).unlink()
            raise

    # 全量重建后同步元数据：比对磁盘文件是否存在，读索引块数更新 document 状态
    def _sync_documents_after_full_rebuild(self) -> None:
        documents = self.store.list_documents()
        for document in documents:
            file_path = self.source_dir / document.relative_path
            if document.status == "deleted":
                document.chunk_count = 0
                continue
            if not file_path.exists():
                document.chunk_count = 0
                document.status = "missing"
                document.last_error = "Source file missing during full rebuild"
            else:
                chunk_count = self.index_repo.get_document_chunk_stats(document.document_id).chunk_count
                document.chunk_count = chunk_count
                if chunk_count > 0:
                    document.status = "active"
                    document.last_error = ""
                else:
                    document.status = "pending_reindex"
            document.updated_at = utc_now()
        self.store.save_documents(documents)

    # ---------- 控制面 <-> 数据面 的桥 ----------

    def sync_worker_managed_document(self, *, file_path: str | Path, chunk_count: int,
                                     text_chunk_count: int, ocr_chunk_count: int,
                                     status: str = "active", updated_at: str | None = None) -> dict:
        path = Path(file_path)
        relative_path = str(path.relative_to(self.source_dir)) \
            if path.is_relative_to(self.source_dir) else path.name
        normalized_relative = self._normalize_relative_key(relative_path)
        normalized_name = self._normalize_relative_key(path.name)
        # [改] 身份匹配收敛：先按相对路径精确匹配；只有相对路径没命中时，才退回文件名匹配。
        #      （原来是“路径或文件名”并列，不同目录的同名文件会被误判成同一个文档）
        documents = self.store.list_documents()
        document = next(
            (item for item in documents
             if self._normalize_relative_key(item.relative_path) == normalized_relative), None)
        if document is None:
            document = next(
                (item for item in documents
                 if self._normalize_relative_key(item.file_name) == normalized_name), None)
        if document is None:
            document = ManagedDocument(document_id=new_id("doc"), title=path.stem,
                                       file_name=path.name, relative_path=relative_path)
        file_hash = self.storage.file_hash_for_path(path) if path.exists() else ""
        active_version = document.active_version()
        # [改] 幂等修复：哈希一致则复用现有版本且不再 append；仅新建版本时 append，
        #      避免反复 sync 同一文件时版本列表堆积重复项
        if active_version and active_version.file_hash == file_hash:
            version = active_version
        else:
            version = DocumentVersion(version_id=new_id("ver"), file_name=path.name,
                                      storage_path=str(path), file_hash=file_hash,
                                      size_bytes=path.stat().st_size if path.exists() else 0,
                                      status="indexed")
            document.versions.append(version)
        document.active_version_id = version.version_id
        version.storage_path = str(path)
        version.size_bytes = path.stat().st_size if path.exists() else version.size_bytes
        version.status = "indexed" if status == "active" else status
        version.chunk_count = int(chunk_count)
        version.text_chunk_count = int(text_chunk_count)
        version.ocr_chunk_count = int(ocr_chunk_count)
        version.error_message = ""
        document.file_name = path.name
        document.title = path.stem
        document.relative_path = relative_path
        document.status = status
        document.chunk_count = int(chunk_count)
        document.deleted_at = None
        document.last_error = ""
        if updated_at:
            document.updated_at = str(updated_at)
        self._upsert_document(document)
        return self._serialize_document(document)

    def estimate_worker_chunk_breakdown(self, file_path: str | Path) -> tuple[int, int, int]:
        # 注意：这是“重活”——会重新解析+OCR，仅在索引拿不到块数时作为兜底使用
        path = Path(file_path)
        total_chunks = build_chunks_for_path(path, self.settings, include_ocr=True)
        chunk_count = len(total_chunks)
        text_chunk_count = sum(1 for chunk in total_chunks
                               if not str(chunk.metadata.source_kind or "").startswith("ocr:"))
        ocr_chunk_count = max(0, chunk_count - text_chunk_count)
        return chunk_count, text_chunk_count, ocr_chunk_count

    def backfill_worker_managed_documents(self) -> dict:
        updated = 0
        created = 0
        with self._state_connection() as connection:
            rows = connection.execute(
                """
                SELECT path, status, updated_at
                FROM files
                WHERE status = 'completed'
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        # [改] 一次性记录已有文档 id，循环内增量维护；原来每个文件都全量读账本算 before，是 O(n²)
        known_ids = {item.document_id for item in self.store.list_documents()}
        for row in rows:
            path = Path(str(row["path"]))
            if not path.exists():
                continue
            indexed_chunk_count = self.index_repo.get_document_chunk_stats(
                f"worker::{path.resolve().as_posix()}").chunk_count
            # [改] 去重活：索引已有真实块数就直接用，不再无条件重新解析/OCR；
            #      仅索引为空时才回退到 estimate（重活）。
            #      代价：已索引文件的 text/ocr 细分无法从索引单独拿到，这里记 0，
            #      细分应由 worker 落库时带出（见文末“未改”说明）。
            if indexed_chunk_count > 0:
                chunk_count, text_chunk_count, ocr_chunk_count = indexed_chunk_count, 0, 0
            else:
                chunk_count, text_chunk_count, ocr_chunk_count = self.estimate_worker_chunk_breakdown(path)
            payload = self.sync_worker_managed_document(
                file_path=path, chunk_count=chunk_count, text_chunk_count=text_chunk_count,
                ocr_chunk_count=ocr_chunk_count, status="active", updated_at=str(row["updated_at"]))
            document_id = str(payload.get("document_id") or "")  # [改] str(x or "")
            if document_id and document_id not in known_ids:
                created += 1
                known_ids.add(document_id)
            else:
                updated += 1
        return {"created": created, "updated": updated}

    # ---------- 账本增改工具（读整份 -> 改 -> 写回整份）----------

    def _append_job(self, job: ManagedJob) -> None:
        jobs = self.store.list_jobs()
        jobs.append(job)
        self.store.save_jobs(jobs)

    def _replace_job(self, job: ManagedJob) -> None:
        jobs = self.store.list_jobs()
        for index, item in enumerate(jobs):  # [改] 原来是 enumerate[ManagedJob](jobs)，会 TypeError
            if item.job_id == job.job_id:
                jobs[index] = job
                break
        self.store.save_jobs(jobs)

    def _append_batch(self, batch: ManagedBatch) -> None:
        batches = self.store.list_batches()
        batches.append(batch)
        self.store.save_batches(batches)

    def _replace_batch(self, batch: ManagedBatch) -> None:
        batches = self.store.list_batches()
        for index, item in enumerate(batches):  # [改] 同上，去掉非法下标
            if item.batch_id == batch.batch_id:
                batches[index] = batch
                break
        self.store.save_batches(batches)

    def _update_batch(self, batch: ManagedBatch, *, status: str, current_file_name: str, message: str) -> None:
        batch.status = status
        batch.current_file_name = current_file_name
        batch.message = message
        batch.updated_at = utc_now()
        self._replace_batch(batch)

    # 文档绑定 job_id，记录这个文档关联了哪些任务
    def _link_job(self, document: ManagedDocument, job_id: str) -> None:
        document.job_ids.append(job_id)
        document.latest_job_id = job_id
        self._upsert_document(document)

    def _update_job(self, job: ManagedJob, *, stage: str, message: str) -> None:
        job.stage = stage
        job.message = message
        job.updated_at = utc_now()
        self._replace_job(job)

    def _finish_job(self, job: ManagedJob, *, status: str, stage: str, message: str,
                    error_message: str = "") -> None:
        job.status = status
        job.stage = stage
        job.message = message
        job.error_message = error_message
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        self._replace_job(job)

    # [改] 审计不再是黑洞：原来收了 message/payload 却只落三个字段，这里真正写入
    # [模型] 依赖 AuditEvent 支持 message / payload 字段（需在 models.py 补上）
    def _audit(self, entity_type: str, entity_id: str, event_type: str,
               message: str = "", payload: dict | None = None) -> None:
        self.store.append_audit_event(AuditEvent(
            event_id=new_id("audit"),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            payload=payload or {},
        ))

    def _find_document(self, document_id: str) -> ManagedDocument | None:
        for item in self.store.list_documents():
            if item.document_id == document_id:
                return item
        return None

    def _upsert_document(self, document: ManagedDocument) -> None:
        document.updated_at = utc_now()
        documents = self.store.list_documents()
        for index, item in enumerate(documents):  # [改] 去掉非法下标 enumerate[ManagedDocument]
            if item.document_id == document.document_id:
                documents[index] = document
                self.store.save_documents(documents)
                return
        documents.append(document)
        self.store.save_documents(documents)

    # ---------- SQLite 投影工具（把队列实时态算成 UI 需要的 dict）----------

    def _sqlite_batch_payload(self, batch_id: str) -> dict:
        progress = batch_progress(batch_id, db_path=self.state_db_path)
        status = str(progress["status"])
        current = int(progress["current"])
        file_count = int(progress["file_count"])
        latest_item = next(iter(progress.get("recent_files") or []), {})
        current_file_name = str(latest_item.get("file_name") or "")
        message = str(latest_item.get("message") or "")
        if not message:
            message = f"Progress {current}/{file_count}"
        return {
            "batch_id": str(progress["batch_id"]),
            "batch_name": str(progress.get("batch_name") or ""),
            "file_count": file_count,
            "status": "running" if status in {"pending", "processing"} and current < file_count else status,
            "queue_status": status,
            "target_mode": "incremental",
            "job_ids": [],
            "completed_count": int(progress["completed"]),
            "failed_count": int(progress["failed"]),
            "pending_count": int(progress["pending"]),
            "dead_count": int(progress["dead"]),
            "processing_count": int(progress["processing"]),
            "failed_files": list(progress["failed_files"]),
            "recent_files": list(progress.get("recent_files") or []),
            "current": current,
            "current_file_name": current_file_name,
            "message": message,
            "created_at": str(progress["created_at"]),
            "updated_at": str(progress.get("updated_at") or progress["created_at"]),
            "started_at": progress.get("started_at"),
            "finished_at": progress.get("finished_at"),
            "elapsed_seconds": progress.get("elapsed_seconds"),
        }

    def _list_sqlite_batches(self) -> list[dict]:
        batch_ids: list[str] = []
        for row in list_sqlite_batches(self.state_db_path):
            batch_id = str(row.get("batch_id") or "")
            if not batch_id:
                continue
            batch_ids.append(batch_id)
        return [self._sqlite_batch_payload(batch_id) for batch_id in batch_ids]

    def _sqlite_jobs_payload(self, batch_id: str) -> list[dict]:
        try:
            progress = batch_progress(batch_id, db_path=self.state_db_path)
        except ValueError:
            return []
        jobs: list[dict] = []
        for item in progress.get("recent_files") or []:
            file_id = int(item.get("id") or 0)
            jobs.append({
                "job_id": f"sqlite_file_{file_id}",
                "job_type": JOB_TYPE_INGEST_DOCUMENT,  # [改] 统一用常量，与 _ingest_file 保持一致
                "status": str(item.get("status") or "pending"),
                "stage": str(item.get("status") or "pending"),
                "target_mode": "incremental",
                "document_id": None,
                "version_id": None,
                "batch_id": batch_id,
                "message": str(item.get("error") or item.get("message") or ""),
                "error_message": str(item.get("error") or ""),
                "file_name": str(item.get("file_name") or item.get("path") or ""),
                "requested_by": "queue",
                "created_at": str(progress.get("created_at") or ""),
                "started_at": None,
                "finished_at": None,
                "updated_at": str(item.get("updated_at") or progress.get("updated_at")
                                  or progress.get("created_at") or ""),
            })
        return jobs

    # [改] 删除了原 _batch_status：它没有被任何地方调用，且与 _sqlite_batch_payload 是两套
    #      状态算法，保留只会制造“两处算出不同状态”的分叉。批次状态统一以 SQLite 进度为准。

    # ---------- SQLite 连接与小工具 ----------

    def _state_connection(self):
        # 注：_connect 是 state_store 的私有函数，理想情况应由 state_store 暴露公开接口
        from kb_admin.state_store import _connect
        return _connect(self.state_db_path)

    @staticmethod
    def _parse_sqlite_file_job_id(job_id: str) -> int:
        prefix = "sqlite_file_"
        if not str(job_id).startswith(prefix):
            raise FileNotFoundError(job_id)
        try:
            return int(str(job_id)[len(prefix):])
        except ValueError as exc:
            raise FileNotFoundError(job_id) from exc

    @staticmethod
    def _classify_failed_file_error(error: str) -> str:
        lowered = str(error or "").strip().lower()
        if not lowered:
            return "unknown"
        if "timeout" in lowered:
            return "timeout"
        if "ocr" in lowered:
            return "ocr"
        if "openpyxl" in lowered or "xlsx" in lowered or "excel" in lowered:
            return "excel"
        if "ppt" in lowered or "powerpoint" in lowered:
            return "ppt"
        if "permission" in lowered or "access is denied" in lowered:
            return "permission"
        if "not found" in lowered or "missing" in lowered:
            return "missing"
        return "processing"

    # [改] row 注解改为合理类型；None 处理用 (row[x] or 默认) 包裹，避免 int(None) 抛错或得到 "None"
    def _serialize_failed_file_row(self, row) -> dict:
        path = Path(str(row["path"] or ""))
        error = str(row["error"] or "")
        error_type = self._classify_failed_file_error(error)
        return {
            "file_id": int(row["id"] or 0),
            "batch_id": str(row["batch_id"] or ""),
            "batch_name": str(row["batch_name"] or ""),
            "file_name": path.name,
            "path": str(path),
            "status": str(row["status"] or "failed"),
            "stage": str(row["stage"] or "done"),
            "attempts": int(row["attempts"] or 0),
            "crash_count": int(row["crash_count"] or 0),
            "error": error,
            "error_type": error_type,
            "retryable": True,
            "skip_reason": "",
            "updated_at": str(row["updated_at"] or ""),
        }

    # 预扫描文件，统计大小，标记 heavy 大文件
    def _pre_scan_files(self, paths: list[str]) -> dict:
        total_size_bytes = 0
        heavy_file_count = 0
        file_items: list[dict] = []
        for raw_path in paths:
            path = Path(raw_path)
            size_bytes = path.stat().st_size if path.exists() else 0
            is_heavy = self._is_heavy_file(path)
            total_size_bytes += size_bytes
            heavy_file_count += int(is_heavy)
            file_items.append({"name": path.name, "size_bytes": size_bytes, "is_heavy": is_heavy})
        return {"file_count": len(paths), "total_size_bytes": total_size_bytes,
                "heavy_file_count": heavy_file_count, "files": file_items}

    # 文件拆分子批：按文件数或字节上限切分
    def _split_sub_batches(self, paths: list[str], *, max_files: int = 8,
                           max_bytes: int = 64 * 1024 * 1024) -> list[list[str]]:
        batches: list[list[str]] = []
        current: list[str] = []
        current_bytes = 0
        for raw_path in paths:
            path = Path(raw_path)
            size_bytes = path.stat().st_size if path.exists() else 0
            if current and (len(current) >= max_files or current_bytes + size_bytes > max_bytes):
                batches.append(current)
                current = []
                current_bytes = 0
            current.append(raw_path)
            current_bytes += size_bytes
        if current:
            batches.append(current)
        return batches or [paths]

    def _build_enqueue_plan(self, saved_paths: list[str], *, saved_names: list[str] | None = None) -> dict:
        plan = build_enqueue_plan(
            saved_paths=saved_paths,
            saved_names=saved_names,
            documents=self.store.list_documents(),
            storage=self.storage,
            normalize_key=self._normalize_relative_key,
            is_heavy_path=is_heavy_path,
        )
        return plan.to_dict()

    @staticmethod
    def _build_upload_message(scan_summary: dict) -> str:
        requested = int(scan_summary.get("requested_file_count") or 0)
        queued = int(scan_summary.get("queue_file_count") or 0)
        skipped = int(scan_summary.get("skipped_file_count") or 0)
        filtered = int(scan_summary.get("filtered_file_count") or 0)
        return f"本次识别 {requested} 个文件: 入队 {queued} 个, 跳过 {skipped} 个, 过滤 {filtered} 个"

    @staticmethod
    def _normalize_relative_key(value: str | None) -> str:
        return str(value or "").replace("\\", "/").strip().strip("/").lower()

    # 判断是否为重文件
    @staticmethod
    def _is_heavy_file(path: Path) -> bool:
        return is_heavy_path(str(path))

    def _build_index_repo(self) -> DocumentIndexRepository:
        if self.settings.azure_search_configured:
            return AzureDocumentIndexRepository(self.settings)
        return LocalDocumentIndexRepository(self.index_path)

    # 序列化文档（内部模型 -> API 返回 dict）
    def _serialize_document(self, document: ManagedDocument) -> dict:
        payload = document.to_dict()
        payload["chunk_stats"] = document.chunk_count
        payload["job_count"] = len(document.job_ids)
        payload["storage_path"] = str((self.source_dir / document.relative_path).resolve())
        payload["index_backend"] = "azure_search" if self.settings.azure_search_configured else "local_json"
        payload["index_target"] = self.settings.azure_search_index \
            if self.settings.azure_search_configured else str(self.index_path)
        return payload


