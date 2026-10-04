#这是知识库后台的”控制面板“--KnowledgeAdminService
# 前端 UI 的所有管理操作都打到KnowledgeAdminService上：
# 列文档 任务 批次、上传入队、单文件入库、替换 删除 重建 重试失败、把worker处理结果同步会账本。
#编排三套存储：
# 1.JSON--给ui看的”管理层元数据“：ManagedDocument，Job，Batch，Audit；
# 2.SQLite（任务队列）-- files，batches表；
# 3.索引仓库 -- 向量、检索索引（AI Search或本地）

from pathlib import Path
from collections.abc import Iterable

from .filters import build_enqueue_plan  #算这批文件哪些入队，哪些跳过、去重、过滤 的计划
from .runtime.heavy import is_heavy_path  #重文件判定--和worker一一致

from kb_poc.config import KBSettings

from .azure_index_repository import AzureDocumentIndexRepository
from .index_repository import DocumentIndexRepository
#真正解析切片 build_chunks_for_path，全量重建rebuild_all_documents
from .ingestion import build_chunks_for_path, rebuild_all_documents
from .json_store import JsonAdminStore
from .local_index_repository import LocalDocumentIndexRepository
from .models import AuditEvent, DocumentVersion, ManagedBatch, ManagedDocument, new_id, utc_now#（时间戳）
from .state_store import batch_progress, enqueue_files, init_db, list_batches as list_sqlite_batches
from .storage import ManagedFileStorage


class KnowledgeAdminService:
    #一次性将三套存储拉起来
    #作用：加载配置--解析源目录，索引路径 -- 建json，SQLite --用工厂_build_index_repo挑索引后端；
#⚠️注意：设计风险❗：_init_很”重“--做磁盘I/O、建库、构造索引仓库。如果这个service是每个HTTP请求new一个，开销不小。
# 建议：做成单例、依赖注入，进程内复用一个实例。
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
        
#读接口：查询+合并两套账本
    # 从json账本取文档，按include_deleted/status/query过滤，排序，分页返回
    def list_documents(self, *, include_deleted: bool = False, status: str | None = None, query: str | None = None, offset: int = 0, limit=None):
        documents = self.store.list_documents()
        if not include_deleted:
            documents = [item for item in documents if item.status != "deleted"]
        if status:
            documents = [item for item in documents if item.status == status]
        if query:
            lowered = query.strip().lower()
            documents = [item for item in documents if lowered in item.title.lower() or lowered in item.file_name.lower()]
        documents.sort(key=lambda item: {"updated_at": item.updated_at, reverse=True})
        total = len(documents)
    #⚠️：真实bug：limit=None是默认值，而documents[offset+limit]在limit为None时会TypeError (None不能参与切片加法)。应给默认值或对None单独处理。
        page = documents[offset: offset + limit]
        return {"items": [self._serialize_document(item) for item in page], "total": total, "offset": offset, "limit": limit}

    #查单文档并附最近50条审计
    def get_document(self, document_id: str) -> dict | None:
        document = self._find_document(document_id)
        if document is None:
            return None
        payload = self._serialize_document(document)
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(entity_type="document", entity_id=document_id, limit=50)]
        return payload

    def list_jobs(self, *, batch_id: str | None = None, document_id: str | None = None, status: str | None = None) -> dict:
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
                batch_value = str(batch.get("batch_id")) or ""
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
        jobs.extend(ManagedJob.from_dict(item) for item in sqlite_only_jobs if item.get("job_id") not in persisted_job_ids)
        jobs.sort(key=lambda item: {"updated_at": item.updated_at, reverse=True})
        return {"items": [item.to_dict() for item in jobs]}
    #⚠️ 只在json账本里线性查，不认SQLite的 sqlite_file_*任务 --和list_job能列出sqlite任务不一致，用户详情可能404 
    def get_job(self, job_id: str) -> dict | None:
        job = next((item for item in self.store.list_jobs() if item.job_id == job_id), None)
        if job is None:
            return None
        payload = job.to_dict()
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(entity_type="job", entity_id=job_id, limit=50)]
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
            batch_id = str(sqlite_item.get("batch_id")) or ""
            if not batch_id or batch_id in sqlite_batch_ids:
                continue
            items.append(sqlite_item)
        items.sort(key=lambda item: {get: str(item.get("created_at")) or "", reverse=True})
        return {"items": items}
    # 先试SQLite进度，失败回退JSON，再附jobs+audit
    def get_batch(self, batch_id: str) -> dict | None:
        try:
            payload = self._sqlite_batch_payload(batch_id)
        except ValueError:
            batch = next((item for item in self.store.list_batches() if item.batch_id == batch_id), None)
            if batch is None:
                return None
            payload = batch.to_dict()
        payload["jobs"] = [item.to_dict() for item in self.store.list_jobs() if item.batch_id == batch_id]
        payload["audit"] = [item.to_dict() for item in self.store.list_audit_events(entity_type="batch", entity_id=batch_id, limit=50)]
        return payload
    #纯透传
    def list_audit_events(self, *, entity_type: str | None = None, entity_id: str | None = None, limit: int = 100) -> dict:
        return {"items": [item.to_dict() for item in self.store.list_audit_events(entity_type=entity_type, entity_id=entity_id, limit=limit)]}

# 失败文件面板
    # 兼容 UI 的失败文件面板，直接从 sqlite files 表读取失败/死亡文件。
    #作用：直接对SQLite files表跑SQL，取status为failed/dead的行，分类错误类型返回给UI
    #参数化查询（这条五参数，竞态SQL），没有注入问题
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
            "error_types": sorted({item["error_type"] for item in items if item.get("error_type")})
        }

    #⚠️：问题最密集的方法之一
    # 按 file_id 或错误类型 批量把失败文件重置成pending，再刷新对应batch状态。
    def retry_failed_files(self, *, file_ids: list[int] | list[str] | None = None, error_types: list[str] | None = None) -> dict:
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
                error_type = self.classify_failed_file_error(str(row["error"] or ""))
                if normalized_ids and file_id in normalized_ids:
                    matched_ids.append(file_id)
                    touched_batches.add(str(row["batch_id"] or ""))
                if normalized_error_types and error_type in normalized_error_types:
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
                parameters=(utc_now(), *matched_ids),
            )
        for batch_id in touched_batches:
            progress = batch_progress(batch_id, db_path=self.state_db_path)
            connection.execute(
                sql="UPDATE batches SET status = ? WHERE batch_id = ?",
                parameters=(str(progress["status"]), batch_id),
            )
        return {"retried": len(matched_ids), "file_ids": matched_ids, "batch_ids": sorted(batch_id for batch_id in touched_batches if batch_id)}

# 上传与入队（异步队列路径）
    # 标准上传，走批量排队batch
    def upload_files(self, files: list[tuple[str, bytes]], *, requested_by: str = "流程图", batch_name: str = "") -> dict:
        saved_paths: list[str] = []                     # “*”之后强制关键字传参
        saved_names: list[str] = []
        for filename, content in files: #逐个把上传字节落盘  save_upload返回【路径，相对路径】，这里只要路径，相对路径用_丢弃
            file_path, _ = self.storage.save_upload(filename, content)
            saved_paths.append(str(file_path))
            saved_names.append(str(filename).replace("\\", "/").strip().lstrip("/"))  #斜杠转写 
        return self.enqueue_saved_files(saved_paths, saved_names=saved_names, requested_by=requested_by, batch_name=batch_name)
        #落盘完就把活交给enqueue_saved_files。   拆成了两步--将存文件与排队 职责分开
# 算计划
    # 把已经落盘的文件，创建batch批量任务，拆分子批 sub‑batch
    #核心方法：把已落盘文件变成“批次+子批+队列记录”
    def enqueue_saved_files(self, saved_paths: list[str], *, saved_names: list[str] | None = None, requested_by: str = "流程图", batch_name: str = ""):
        if not saved_paths:  # 空输入直接报错
            raise ValueError("No uploaded files were saved")
        # 算：入队计划--哪些真要入队，哪些重复跳过，那些是重试，哪些被过滤
        enqueue_plan = self._build_enqueue_plan(saved_paths, saved_names=saved_names)
        queue_paths = enqueue_plan["queue_paths"]    #真要入队的
        skipped_items = enqueue_plan["skipped_items"]  #要跳过的
        retry_items = enqueue_plan["retry_items"]   #要重试的
        queued_items = enqueue_plan["queued_items"]  #入队条目
        filtered_items = enqueue_plan.get("filtered_items", []) #被过滤的
        duplicate_skip_count = len(skipped_items)  #记录 因重复而被跳过的 数量
        #没有可入队文件时的早返回
        # 如果没有入队的，就直接返回“扫描汇总”  dict(...)拷一份，避免改到原计划里的数据。
        if not queue_paths:
            scan_summary = dict(enqueue_plan["scan_summary"])
            # 准备批次显示名
            normalized_names = saved_names or [Path(path).name for path in saved_paths]
            normalized_batch_name = batch_name.strip() or f"{normalized_names[0]} 等 {len(normalized_names)} 个文件"
            #[*a,*b,*c]是解包合并列表 -- 把三类条目拼成一个列表给前端展示
            items = [*retry_items, *skipped_items, *filtered_items]
            #返回一个batch_id=None的结构，明确告诉前端“这次没建批次，没入队”，并带上汇总（message）
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
        #生成父批次的唯一id （形如batch_xxx)
        batch_id = new_id("batch")
        # 批次显示名的素材：优先用 入队条目 里的文件名；都没有再返回saved_names或路径名。  多级or回退，保证总能取到名字。
        normalized_names = [item["file_name"] for item in queued_items] or (saved_names or [Path(path).name for path in saved_paths])
        #定批次名-逻辑同上； 拷一份扫描汇总备用
        normalized_batch_name = batch_name.strip() or f"{normalized_names[0]} 等 {len(normalized_names)} 个文件"
        scan_summary = dict(enqueue_plan["scan_summary"])
        # 把要入队的文件拆成若干“子批”---控制每批规模。避免一个超大批次队列/内存压垮
        child_batches = self._split_sub_batches(queue_paths)
        #建 父批次 对象：记总文件数，初始状态pending，增量模式，子批总数，总字节，重文件数，扫描汇总。
        batch = ManagedBatch(
            batch_id=batch_id,
            batch_name=normalized_batch_name,
            file_count=len(queue_paths),
            status="pending",
            target_mode="incremental",
            batch_index=1,  #表示它是顶层
            batch_total=max(1, len(child_batches)),
            total_size_bytes=int(scan_summary["total_size_bytes"]),
            heavy_file_count=int(scan_summary["heavy_file_count"]),
            scan_summary=scan_summary,
        )
        #将父批次写进账本   （这里写的是json，  下一步enqueue_file写的是SQLite---两套账本在这里开始分头记（简隐患）
        self._append_batch(batch)
        #遍历每个子批--给每个子批生成自己的ID  list(child_batches)是多余包装，child_batches本就是列表
        for index, child_paths in enumerate(list(child_batches), start=1):
            child_batch_id = new_id("subbatch")
            #真正写入SQLite的一步：把这个子批的文件登记进files表
            enqueue_files(child_batch_id, child_paths, db_path=self.state_db_path, batch_name=f"{normalized_batch_name}‑子批 {index}/{len(child_batches)}")
            #给子批也建一个ManageBatch,记父id，文件数，字节数，重文件数，各自的扫描汇总
            child_batch = ManagedBatch(
                batch_id=child_batch_id,
                parent_batch_id=batch_id,
                batch_name=f"{normalized_batch_name}‑子批 {index}/{len(child_batches)}",
                file_count=len(child_paths),
                status="pending",
                target_mode="incremental",
                batch_index=index,
                batch_total=len(child_batches),
                total_size_bytes=sum(Path(path).stat().st_size for path in child_paths if Path(path).exists()),
                heavy_file_count=sum(1 for path in child_paths if self._is_heavy_file(Path(path))),
                scan_summary=self._pre_scan_files(child_paths),
            )   #同一批文件被反复state（隐患）
            #子批写进json
            self._append_batch(child_batch)
            #记一条审计“批次已入队”
            self._audit(entity_type="batch", batch.batch_id, event_type="batch_created", message=f"Batch enqueued for {len(queue_paths)} file(s)", batch=batch.to_dict(), items=[*queued_items, *retry_items])
        #返回成功结果
        return {"batch_id": batch_id, "batch_id": str, "filename": str, "content": bytes | None = None, *, file_path: Path | None = None, requested_by=""}
#替换
    #用新文件替换已有的文档内容--content(字节)和file_path(已落盘路径) 二选一传
    def replace_document(self, document_id: str, filename: str, content: bytes | None, *, file_path: Path | None = None, requested_by=""):
        #先按id找到现有文档；找不到抛error
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        #把活交给共用引擎_ingest_file，并把现有文档作为exisiting传进去---这样引擎会在同一个文档上追加新版本，而不是新建文档
        return self._ingest_file(filename, content, existing=document, file_path=file_path, requested_by=requested_by)
#删
    # hard_delete 决定是否连磁盘源文件一起删（默认只软删，不动文件）
    def delete_document(self, document_id: str, *, hard_delete: bool = False) -> dict:
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        #第一处写入：先从索引里删掉这个文档的所有切片，返回删了多少块。--为什么先删索引：让索引立刻搜不到他
        deleted_chunks = self.index_repo.delete_document_chunks(document_id)
        #第二处写入：把文档对象标记成已删除（块数清零，状态deleted，记删除/更新时间），再写回json
        #这是软删--记录还在，只是状态变了，可追溯。
        document.chunk_count = 0
        document.status = "deleted"
        document.deleted_at = utc_now()
        document.updated_at = utc_now()
        self._upsert_document(document)
        #只有显示要求硬删，且文件确实存在，才unlink(真删磁盘文件)--这一步不可逆
        file_path = self.source_dir / document.relative_path
        if hard_delete and file_path.exists():
            file_path.unlink()
            #记一条文件已删除审计
        self._audit(entity_type="document", document.document_id, event_type="document_deleted", message="Document deleted from management la")
        # 返回序列化后的文档+删了多少块。  {**a,"x":y}是展开a，再加一个字段 的写法
        return {**self._serialize_document(document), "deleted_chunk_count": deleted_chunks}
#重建单个文档
    #按磁盘上的源文件重新解析入库一个文档
    def rebuild_document(self, document_id: str, *, requested_by: str = "流程图") -> dict:
        document = self._find_document(document_id)
        if document is None:
            raise FileNotFoundError(document_id)
        #拼出源文件路径
        file_path = self.source_dir / document.relative_path
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))
        #交给_ingest_file：content=None表示“没有新字节，从file_path读磁盘文件”，existing=document保证在原文档上重建
        return self._ingest_file(document.file_name, content=None, existing=document, file_path=file_path, requested_by=requested_by)
#全量重建
    #先建rebuild_all类型的任务，落账本--这样前端能看见“全量重建进行中”。
    def rebuild_all(self, *, requested_by: str = "流程图") -> dict:
        job = ManagedJob(job_id=new_id("job"), job_type="rebuild_all", status="running", stage="queued", target_mode="full", requested_by=requested_by)
        self._append_job(job)
        self._audit(entity_type="job", job.job_id, event_type="job_created", message="Full rebuild job created", payload={"target_mode": "full"})
        #进try块：把任务阶段推进到rebuilding，然后调外部的rebuild_all_documents真正重建全部文档的索引
        try:
            self._update_job(job, stage="rebuilding", message="Running full ingest_directory rebuild")
            stats = rebuild_all_documents(self.source_dir, self.index_path, self.settings)
            #重建完对账，比对磁盘文件在不在，从索引读实际块数，更新每个文档的状态
            self._sync_documents_after_full_rebuild()
            self._finish_job(job, status="completed", stage="completed", message="Full rebuild completed")
            self._audit(entity_type="job", job.job_id, event_type="job_completed", message="Full rebuild completed", payload={"document_count":""})
            return {"job": job.to_dict(), "stats": stats.model_dump()}
        #先标记成failed，记下错误审计，再raise把异常继续抛给上层
        except Exception as exc:
            self._finish_job(job, status="failed", stage="failed", message=str(exc), error_message=str(exc))
            self._audit(entity_type="job", job.job_id, event_type="job_failed", message="Full rebuild failed", payload={"error": str(exc)})
            raise

    #重试失败任务
    #現在json里线性查这个job
    def retry_job(self, job_id: str) -> dict:
        job = next((item for item in self.store.list_jobs() if item.job_id == job_id), None)
        #如果json里没有：若id是sqlite_file_*（队列伪任务），转交retry_worker_file走队列重试；否则报错
        #这就是“两种任务来源”在重试侧的分流。
        if job is None:
            if job_id.startswith("sqlite_file_"):
                return self.retry_worker_file(job_id)
            raise FileNotFoundError(job_id)
        #按任务类型分派：全量重建任务--重跑全量；否则必须有关联文档，用rebuild_document重建该文档。
        if job.job_type == "rebuild_all":
            return self.rebuild_all(requested_by="retry")
        if not job.document_id:
            raise FileNotFoundError(job_id)
        return self.rebuild_document(job.document_id, requested_by="retry")
#重试队列文件
    #把队列里的某个文件重新入队
    def retry_worker_file(self, job_id: str, *, requested_by: str = "retry") -> dict:
        file_id = self._parse_sqlite_file_job_id(job_id)
        #开SQLite连接，按file_id查这一行
        with self._state_connection() as connection:
            row = connection.execute(
                #此处图片内SQL被截断
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

    ## 是否要加一个後端邏輯，即使前端或者進程出現問題時，也能夠在後端單獨實現增量重建
    
"""
核心引擎 _ingest_file 同步入库全流程
"""

    #签名、取/建文档、校验
    def _ingest_file(self, filename: str, content: bytes | None, *, batch_id: str | None = None, existing: ManagedDocument | None = None, persist_job_history=True, file_path: Path | None = None, requested_by=""):
        #有现成文档就用，没有就新建
        document = existing or ManagedDocument(document_id=new_id("doc"), title=Path(filename).stem, file_name=Path(filename).name, relative_path="")
        if content is None and file_path is None:
            raise ValueError("Either content or file_path is required")
        #算这份文件的内容哈希：有字节就对字节算，都则对磁盘文件算。
        file_hash = self.storage.file_hash(content) if content is not None else self.storage.file_hash_for_path(file_path)
        #这就是同步路径的幂等核心：
        # 如果文档已有一个“活跃版本”、他的哈希和这次完全相同、且文档当前是active--说明内容没变，直接跳过，不重新解析、不重新入索引，只记一条document_skipped审计后返回(job=None表示没真正干活)。
        #为什么重要：重复提交同一文件（或重试）不会白跑一遍昂贵的解析+ocr，也不会污染索引
        # 幂等--做一次和做多次结果一样
        active = document.active_version()
        if active and active.file_hash == file_hash and document.status == "active":
            document.chunk_count = active.chunk_count
            self._audit(entity_type="document", document.document_id, event_type="document_skipped", message="Skipped unchanged document", payload={})
            return {"document": self._serialize_document(document), "job": None, "file_name": filename, "file_hash": file_hash, "size_bytes":0}
        #内容变了，所以建一个新版本对象
        #为什么要版本：文档保留历史版本 + 一个“活跃版本指针”，便于审计/回滚
        version = DocumentVersion(version_id=new_id("ver"), file_name=Path(filename).name, storage_path="", file_hash=file_hash, size_bytes=0)
        # 建一个“增量入库”任务，初始running/queued
        job = ManagedJob(job_id=new_id("job"), job_type="ingest‑document", status="running", stage="queued", target_mode="incremental", document_id=document.document_id)
        #两种模式：
        # 需要留痕（用户手动触发）就把任务写进账本、绑到文档、记审计；
        #不需要（内部/批量调用）就只在文档上记一个“最新任务id”，不往任务历史里塞。
        #为什么留这个开关：批量入库时每个文件都建一条任务历史会把列表刷爆，内部调用轻量模式即可。
        if persist_job_history:
            self._append_job(job)
            self._link_job(document, job.job_id)
            self._audit(entity_type="job", job.job_id, event_type="job_created", message="Incremental document ingest job created", payload={})
        else:
            document.latest_job_id = job.job_id
        # 若没传现成路径（是带字节来的），就落盘得到save_path，并把他记进cleanup_path 
        # --意图是：万一后面失败，好把这个刚存的临时文件删掉（可惜清理代码在被截段的except里--见隐患)
        try:
            saved_path = file_path
            cleanup_path: Path | None = None
            if saved_path is None:
                saved_path, relative_path = self.storage.save_upload(filename, content)
                cleanup_path = saved_path
            # 若传了现成路径：算它相对源目录的相对路径；若不在源目录下，就原样用绝对路径
            #relative_to 是python 3.9+ 的路径判断
            else:
                relative_path = str(saved_path.relative_to(self.source_dir)) if saved_path.is_relative_to(self.source_dir) else saved_path
            #回填版本的存储路径；更新文档的文件名/标题/相对路径；把状态切到processing(正在处理)；清掉删除标记和上次错误。状态机在这里推进：文档进入“处理中”
            version.storage_path = str(saved_path)
            document.file_name = Path(filename).name
            document.title = Path(filename).stem
            document.relative_path = relative_path
            document.status = "processing"
            document.deleted_at = None
            document.last_error = ""
            #把新版本挂进文档的版本列表，并把“活跃版本指针”指向它，然后写回账本。
            #还原时合并：追加版本+置活跃指针+落盘一次
            document.versions.append(version)
            self._upsert_document(document)
            #后续逻辑图片截断
        except Exception:
            #异常处理截断
            raise
        
class KnowledgeAdminService:

    def _append_job(self, job: ManagedJob) -> None:
        jobs = self.store.list_jobs()
        jobs.append(job)
        self.store.save_jobs(jobs)

    def _replace_job(self, job: ManagedJob) -> None:
        jobs = self.store.list_jobs()
        for index, item in enumerate[ManagedJob](jobs):
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
        for index, item in enumerate[ManagedBatch](batches):
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

    #文件绑定job_id，记录这个文档关联哪些任务
    def _link_job(self, document: ManagedDocument, job_id: str) -> None:
        document.job_ids.append(job_id)
        document.latest_job_id = job_id
        self._upsert_document(document)

    def _ingest_file(self, filename: str, content: bytes | None, *, batch_id: str | None = None, existing: ManagedDocument | None = None):
        document.deleted_at = None
        document.last_error = ""
        document.versions.append(version)
        document.active_version_id = version.version_id
        self._upsert_document(document)
        
#解析切片+统计文本/ocr块
        #把任务阶段推进到parsing，然后调外部build_chunks_for_path做真正的解析+ocr+切片，拿到全部chunk---这是最耗时的一步，且是同步执行的（在当前请求里跑完）
        self._update_job(job, stage="parsing", message="File saved, parsing content")
        full_chunks = build_chunks_for_path(saved_path, self.settings, include_ocr=True)
        #统计有多少文本块，多少ocr块；靠每个chunk的元数据source_kind是否已“ocr：”开头来区分。
        #ocr数=总数-文本数（max(0, ...)防负数兜底）
        version.text_chunk_count = sum(1 for chunk in full_chunks if not str(chunk.metadata.source_kind or "").startswith("ocr:"))
        version.ocr_chunk_count = max(0, len(full_chunks) - version.text_chunk_count)
        #记总块数（版本和文档各记一份），把版本状态推进到parsed(已解析)
        version.chunk_count = len(full_chunks)
        document.chunk_count = len(full_chunks)
        version.status = "parsed"
#三段式upsert写索引--重点
        #为什么不一次写完，要分begin/append/finalize三步？
        #这是“原子替换+支持大文档”的经典设计：
        #begin--为这个文档的新版本开一个“暂存槽”
        #append--把切片分流式塞进暂存槽（文档再大也不必一次性全装进内存）；
        #finalize--一次性把“当前生效版本”切换到新版本、清掉旧版本。
        #好处，新旧版本检索只能看见一种，不会出现出现“中间态”   这跟先删后插相比，避免了删到插之间的空窗
        self._update_job(job, stage="indexing", message=f"Upserting {len(full_chunks)} chunks")
        self.index_repo.begin_document_upsert(document.document_id, version.version_id)
        self.index_repo.append_document_chunks(document.document_id, version.version_id, full_chunks)
        self.index_repo.finalize_document_upsert(document.document_id, version.version_id)
        
#标为active+完成任务
        version.status = "indexed"
        document.status = "active"
        self._upsert_document(document)
        if persist_job_history:
            self._finish_job(job, status="completed", stage="completed", message="Document indexed successfully")
    
    

#worker结果回写账本
    #全量重建之后同步元数据；比对磁盘文件是否存在，读取索引内块数量更新document状态；
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

    #序列化文档(内部模型--API返回dict)
    def _serialize_document(self, document: ManagedDocument) -> dict:
        payload = document.to_dict()
        payload["chunk_stats"] = document.chunk_count
        payload["job_count"] = len(document.job_ids)
        payload["storage_path"] = str((self.source_dir / document.relative_path).resolve())
        payload["index_backend"] = "azure_search" if self.settings.azure_search_configured else "local_json"
        payload["index_target"] = self.settings.azure_search_index if self.settings.azure_search_configured else str(self.index_path)
        return payload

    #预扫描文件，遍历文件，累计总大小，重文件数，给每个文件记name/size/is_heavy
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
        return {"file_count": len(paths), "total_size_bytes": total_size_bytes, "heavy_file_count": heavy_file_count, "files": file_items}

    # 文件拆分子批，每子批上限：8个文件或64MB，两个阈值用关键字默认值，调用方可覆盖
    def _split_sub_batches(self, paths: list[str], *, max_files: int = 8, max_bytes: int = 64 * 1024 * 1024) -> list[list[str]]:
        #装箱用的三个变量：结果箱子列表；当前箱，当前箱累计字节
        batches: list[list[str]] = []
        current: list[str] = []
        current_bytes = 0
        #逐个文件，取大小（不存在的算0）
        for raw_path in paths:
            path = Path(raw_path)
            size_bytes = path.stat().st_size if path.exists() else 0
            # 装箱核心：当前箱非空，且“再加这个会超件数或超字节”，就封箱，开新箱
            if current and (len(current) >= max_files or current_bytes + size_bytes > max_bytes):
                batches.append(current)
                current = []
                current_bytes = 0
            #把文件放进当前箱爱那个，累加字节。循环完封最后一箱
            current.append(raw_path)
            current_bytes += size_bytes
        if current:
            batches.append(current)
        return batches or [paths]  #兜底 把所有文件当一个箱返回，保证不返回空
    #把入队决策委托出去
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

    @staticmethod  #纯格式化：把扫描汇总的数字拼成一句中文给前端
    def _build_upload_message(scan_summary: dict) -> str:
        requested = int(scan_summary.get("requested_file_count") or 0)
        queued = int(scan_summary.get("queue_file_count") or 0)
        skipped = int(scan_summary.get("skipped_file_count") or 0)
        filtered = int(scan_summary.get("filtered_file_count") or 0)
        return f"本次识别 {requested} 个文件: 入队 {queued} 个, 跳过 {skipped} 个, 过滤 {filtered} 个"

    @staticmethod
    def _normalize_relative_key(value: str | None) -> str:
        return str(value or "").replace("\\", "/").strip().strip("/").lower()

    @staticmethod #判断是否为重文件
    def _is_heavy_file(path: Path) -> bool:
        return is_heavy_path(str(path))

    def _build_index_repo(self) -> DocumentIndexRepository:
        if self.settings.azure_search_configured:
            return AzureDocumentIndexRepository(self.settings)
        return LocalDocumentIndexRepository(self.index_path)

    def _find_document(self, document_id: str) -> ManagedDocument | None:
        for item in self.store.list_documents():
            if item.document_id == document_id:
                return item
        return None

    def _upsert_document(self, document: ManagedDocument) -> None:
        document.updated_at = utc_now()
        documents = self.store.list_documents()
        for index, item in enumerate[ManagedDocument](documents):
            if item.document_id == document.document_id:
                documents[index] = document
                self.store.save_documents(documents)
                return
        documents.append(document)
        self.store.save_documents(documents)

    def sync_worker_managed_document(
        self,
        *,
        file_path: str | Path,
        chunk_count: int,
        text_chunk_count: int,
        ocr_chunk_count: int,
        status: str = "active",
        updated_at: str | None = None,
    ) -> dict:
        path = Path(file_path)
        relative_path = str(path.relative_to(self.source_dir)) if path.is_relative_to(self.source_dir) else path.name
        normalized_relative = self._normalize_relative_key(relative_path)
        normalized_name = self._normalize_relative_key(path.name)
        document = next(
            (
                item
                for item in self.store.list_documents()
                if self._normalize_relative_key(item.relative_path) == normalized_relative
                or self._normalize_relative_key(item.file_name) == normalized_name
            ),
            None,
        )
        if document is None:
            document = ManagedDocument(
                document_id=new_id("doc"),
                title=path.stem,
                file_name=path.name,
                relative_path=relative_path,
            )
        file_hash = self.storage.file_hash_for_path(path) if path.exists() else ""
        active_version = document.active_version()
        if active_version and active_version.file_hash == file_hash:
            version = active_version
        else:
            version = DocumentVersion(
                version_id=new_id("ver"),
                file_name=path.name,
                storage_path=str(path),
                file_hash=file_hash,
                size_bytes=path.stat().st_size if path.exists() else 0,
                status="indexed",
            )
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
        path = Path(file_path)
        total_chunks = build_chunks_for_path(path, self.settings, include_ocr=True)
        chunk_count = len(total_chunks)
        text_chunk_count = sum(1 for chunk in total_chunks if not str(chunk.metadata.source_kind or "").startswith("ocr:"))
        ocr_chunk_count = max(0, chunk_count - text_chunk_count)
        return chunk_count, text_chunk_count, ocr_chunk_count

    def backfill_worker_managed_documents(self) -> dict:
        from kb_admin.state_store import _connect

        updated = 0
        created = 0
        with _connect(self.state_db_path) as connection:
            rows = connection.execute(
                """
                SELECT path, status, updated_at
                FROM files
                WHERE status = 'completed'
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        existing_ids = {item.document_id for item in self.store.list_documents()}
        for row in rows:
            raw_path = str(row["path"])
            path = Path(raw_path)
            if not path.exists():
                continue
            indexed_chunk_count = self.index_repo.get_document_chunk_stats(f"worker::{path.resolve().as_posix()}").chunk_count
            chunk_count, text_chunk_count, ocr_chunk_count = self.estimate_worker_chunk_breakdown(path)
            if indexed_chunk_count > 0:
                chunk_count = indexed_chunk_count
                ocr_chunk_count = max(0, chunk_count - text_chunk_count)
            before = {item.document_id for item in self.store.list_documents()}
            payload = self.sync_worker_managed_document(
                file_path=path,
                chunk_count=chunk_count,
                text_chunk_count=text_chunk_count,
                ocr_chunk_count=ocr_chunk_count,
                status="active",
                updated_at=str(row["updated_at"]),
            )
            after_id = str(payload.get("document_id")) or ""
            if after_id and after_id not in before:
                created += 1
            else:
                updated += 1
        return {"created": created, "updated": updated}

    def _state_connection(self):
        from kb_admin.state_store import _connect

        return _connect(self.state_db_path)

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

    def _serialize_failed_file_row(self, row: __getitem__) -> dict:
        path = Path(str(row["path"]) or "")
        error = str(row["error"]) or ""
        error_type = self._classify_failed_file_error(error)
        return {
            "file_id": int(row["id"]),
            "batch_id": str(row["batch_id"]) or "",
            "batch_name": str(row["batch_name"]) or "",
            "file_name": path.name,
            "path": str(path),
            "status": str(row["status"]) or "failed",
            "stage": str(row["stage"]) or "done",
            "attempts": int(row["attempts"]) or 0,
            "crash_count": int(row["crash_count"]) or 0,
            "error": error,
            "error_type": error_type,
            "retryable": True,
            "skip_reason": "",
            "updated_at": str(row["updated_at"]) or "",
        }

    @staticmethod
    def _parse_sqlite_file_job_id(job_id: str) -> int:
        pass

class KnowledgeAdminService:

    @staticmethod
    def _parse_sqlite_file_job_id(job_id: str) -> int:
        prefix = "sqlite_file_"
        if not str(job_id).startswith(prefix):
            raise FileNotFoundError(job_id)
        try:
            return int(str(job_id)[len(prefix):])
        except ValueError as exc:
            raise FileNotFoundError(job_id) from exc

    def _update_job(self, job: ManagedJob, *, stage: str, message: str) -> None:
        job.stage = stage
        job.message = message
        job.updated_at = utc_now()
        self._replace_job(job)

    def _finish_job(self, job: ManagedJob, *, status: str, stage: str, message: str, error_message: str = "") -> None:
        job.status = status
        job.stage = stage
        job.message = message
        job.error_message = error_message
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        self._replace_job(job)

    def _audit(self, entity_type: str, entity_id: str, event_type: str, message: str, payload: dict) -> None:
        self.store.append_audit_event(AuditEvent(event_id=new_id("audit"), event_type=event_type, entity_type=entity_type, entity_id=entity_id))

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
            jobs.append(
                {
                    "job_id": f"sqlite_file_{file_id}",
                    "job_type": "ingest_document",
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
                    "updated_at": str(item.get("updated_at") or progress.get("updated_at") or progress.get("created_at") or ""),
                }
            )
        return jobs

    @staticmethod
    def _batch_status(batch: ManagedBatch) -> str:
        processed_count = batch.completed_count + batch.failed_count
        if processed_count < batch.file_count:
            return "running"
        if batch.failed_count == 0 and batch.completed_count == batch.file_count:
            return "completed"
        if batch.completed_count == 0 and batch.failed_count == batch.file_count:
            return "failed"
        return "partial_failed"