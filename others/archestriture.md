# 知识库项目代码架构文档
## 1. 项目整体骨架
项目根目录下，真正和“知识库入库、管理、检索”强相关的核心目录如下：

| 路径 | 作用 | 备注 |
|---|---|---|
| `kb_admin/` | 管理面与 worker 调度层 | 负责上传、入队、SQLite状态机、worker调度、失败重试、管理数据同步 |
| `kb_poc/` | 知识库核心能力层 | 负责解析、OCR、切片、embedding、索引写入、检索问答 |
| `data/kb_admin/` | 管理层持久化数据目录 | `state.db`、`documents.json`、`jobs.json`、`batches.json` 等都在这里 |
| `sample_docs/` | 默认知识库源文件目录 | 上传或待入库文件通常落到这里或其子目录 |
| `logs/` | 日志目录 | worker 等运行日志会写在这里 |
| `tests/` | 测试目录 | 用于回归验证核心链路 |

从职责上看，这个项目可以粗分成四层：

| 分层 | 主要目录/文件 | 负责什么 |
|---|---|---|
| 接口层 | `kb_poc/ui/api_admin.py` | 对外提供上传、重建、查询、失败重试等 HTTP 接口 |
| 管理调度层 | `kb_admin/` | 接收文件、入队、状态流转、worker调度、管理数据维护 |
| 入库处理层 | `kb_admin/ingestion.py`、`kb_poc/ingestion/ingestor.py` | 统一把解析结果变成 chunk，并完成 embedding 与索引写入 |
| 内容能力层 | `kb_poc/parsing/`、`kb_poc/retrieval/`、`kb_poc/indexing/` | 文件解析/OCR、向量生成、索引读写、检索问答 |

> `kb_admin` 不是 parser，它更像**入库控制塔**。它的核心价值：把上传文件、SQLite队列、worker多进程、失败恢复、管理层文档资料串联起来。

## 2. `kb_admin` 目录结构与职责
### 2.1 根目录关键文件

| 文件 | 作用 | 调用关系 |
|---|---|---|
| `kb_admin/services.py` | `KnowledgeAdminService` 总装配入口 | API、worker、admin service 都从这里拿 store / state / index / ingest / retry / query |
| `kb_admin/state_store.py` | SQLite 状态机底座 | 管入队、claim、mark、control、health、stuck恢复 |
| `kb_admin/worker.py` | worker 主循环 | claim 任务、分 light/heavy、启动子进程、回写状态 |
| `kb_admin/process_one_file.py` | heavy 文件独立子进程入口 | 专门处理重文件，输出 chunk jsonl |
| `kb_admin/ingestion.py` | admin这条链的流式 ingestion 收口 | 负责 chunk 流式生成、embedding、jsonl落盘、全量重建统计 |
| `kb_admin/storage.py` | 文件保存与哈希计算 | 上传文件保存到 source 目录，供后续入队 |
| `kb_admin/models.py` | 管理层模型定义 | `ManagedDocument`、`ManagedJob`、`ManagedBatch` 等 |

### 2.2 `admin/` 子目录

| 文件 | 作用 | 关键类/函数 |
|---|---|---|
| `kb_admin/admin/ingest.py` | 管理端上传、入队、单文档重建、全量重建 | `AdminIngestService` |
| `kb_admin/admin/query.py` | 管理端列表与详情查询 | `AdminQueryService` |
| `kb_admin/admin/retry.py` | 失败文件分类、筛选和重试 | `AdminRetryService` |
| `kb_admin/admin/worker_sync.py` | worker结果同步回管理层 | `AdminWorkerSyncService` |
| `kb_admin/admin/store_support.py` | documents/jobs/batches/audit 的读写辅助 | `AdminStoreSupport` |
| `kb_admin/admin/serializers.py` | 管理层对象序列化 | API 返回结构整理 |

### 2.3 `worker_support/` 子目录

| 文件 | 作用 | 关键内容 |
|---|---|---|
| `kb_admin/worker_support/config.py` | worker 配置中心 | 并发、timeout、内存阈值、heavy判定阈值 |
| `kb_admin/worker_support/dispatch.py` | claim 与 light/heavy 分流 | `claim_capacity()`、`split_claimed_rows()` |
| `kb_admin/worker_support/pool.py` | light 文件进程池执行 | `new_pool()`、`submit_rows()`、`wait_for_all_light_tasks()` |
| `kb_admin/worker_support/heavy.py` | heavy 文件启停、轮询、超时清理 | `start_heavy_subprocess()`、`poll_heavy_subprocess()` |
| `kb_admin/worker_support/indexing.py` | jsonl → index repo → 管理层同步 | `upsert_with_retry()`、`sync_managed_document()` |
| `kb_admin/worker_support/runtime.py` | 多进程、锁文件、孤儿进程清理 | worker启动保护和运行环境收口 |

### 2.4 `repositories/` 子目录

| 文件 | 作用 | 备注 |
|---|---|---|
| `kb_admin/repositories/json_store.py` | 管理数据 JSON 持久化 | 保存 `documents.json`、`jobs.json`、`batches.json`、`audit.json` |
| `kb_admin/repositories/azure_index_repository.py` | Azure AI Search 版本的管理索引仓储 | 封装 begin/append/finalize document upsert |
| `kb_admin/repositories/local_index_repository.py` | 本地JSON索引仓储 | 本地模式使用 |
| `kb_admin/repositories/index_repository.py` | 索引仓储抽象接口 | 给上层统一调用 |

### 2.5 `ops/` 子目录
这里主要是支撑能力，不直接做主业务主流程，但是影响稳定性和吞吐。

| 文件 | 作用 |
|---|---|
| `kb_admin/ops/enqueue_filter.py` | 入队前过滤垃圾文件，例如 `~$`、`Thumbs.db`、`.lnk` |
| `kb_admin/ops/rate_limit.py` | embedding / Azure 写入限流器工厂 |
| `kb_admin/ops/health.py` | 内存负载、worker健康检查 |
| `kb_admin/ops/supervisor.py` | worker守护/管理相关辅助 |

## 3. `kb_poc` 目录结构与职责
> `kb_poc` 是真正处理文档内容的地方：解析/OCR、切chunk、embedding、建索引、检索问答都在这里；`kb_admin` 只是把这些能力编排成可运营系统。

### 3.1 配置与入口

| 文件 | 作用 | 关键点 |
|---|---|---|
| `kb_poc/config.py` | 全局配置模型 `KBSettings` | source_dir、index_path、OCR、embedding、Azure Search 等 |
| `kb_poc/__main__.py` / `kb_poc/cli.py` | 命令行入口 | `python -m kb_poc ingest` 做全量入库 |
| `kb_poc/ui/api_admin.py` | HTTP API | 上传、重建、管理查询、检索问答对外暴露 |

### 3.2 `parsing/` 子目录

| 文件 | 作用 | 关键点 |
|---|---|---|
| `kb_poc/parsing/base.py` | 解析层基础模型 | `ParsedDocument`、`ParsedSegment`、解析选项 |
| `kb_poc/parsing/excel_parser.py` | Excel解析 | 支持OCR；heavy模式可关闭高重复cell blocks |
| `kb_poc/parsing/pptx_parser.py` | PPT/PPTX解析 | 支持图像OCR、流程图信息提取 |
| `kb_poc/parsing/ppt_ocr.py` | PaddleOCR封装 | OCR引擎配置与初始化入口 |
| `kb_poc/parsing/markdown_parser.py` | markdown纯文本解析 | 纯文本类文档使用 |
| `kb_poc/parsing/pdf_parser.py` | PDF解析 | 文本+图像OCR分支 |

### 3.3 `ingestion/` 子目录

| 文件 | 作用 | 关键点 |
|---|---|---|
| `kb_poc/ingestion/ingestor.py` | 项目共享 ingestion核心 | 统一 `kb_admin` 和 `python -m kb_poc ingest` 两条链路 |
| `kb_poc/ingestion/legacy_converter.py` | 旧Office转OOXML | `.ppt`/`.xls`/`.doc`兼容转换 |

### 3.4 `retrieval/` 与 `indexing/`

| 文件 | 作用 | 关键点 |
|---|---|---|
| `kb_poc/retrieval/embedding.py` | embedding客户端封装 | `text‑embedding‑3‑large`、限流、重试、client cache |
| `kb_poc/indexing/factory.py` | 根据配置选择索引后端 | Azure Search或者本地JSON |
| `kb_poc/indexing/base.py` | 索引读写抽象 | add chunk / search / delete document |

## 4. 运行模式：两条入库链路
当前代码有两条入库主链，现在已经统一到同一套 ingestion 核心上。

| 入口 | 典型场景 | 真实落点 |
|---|---|---|
| `/api/admin/upload` → `KnowledgeAdminService().enqueue_saved_files(...)` | 网页上传交给worker异步处理 | `kb_admin` 调度链 |
| `python -m kb_poc ingest` | 手动全量重建 | `kb_poc.ingestion.ingestor.ingest_directory()` |

- `kb_admin`：走 SQLite + worker + 多进程调度；
- `kb_poc ingest`：走单进程全量重建。

> 历史痛点：两条链路实现不一致，一条偏流式，一条偏全量list加载；现在统一到ingestion层流式处理；差异主要来自**调度方式不同**。

## 5. 一个文件从“上传/入队”到“完成”完整路线图
以用户上传文件，worker处理并写入索引的主链路。

### 第1步：HTTP上传进入管理层
入口：`kb_poc/ui/api_admin.py`

关键路径：
1. `POST /api/admin/upload` 接收multipart文件流
2. `_stream_multipart_to_storage()` 直接落盘到source目录，不完整加载进内存
3. 交给 `KnowledgeAdminService.enqueue_saved_files()`
4. **不在API线程做OCR / embedding / 索引写入**。

> 做的事情：
> - 接收multipart文件流；
> - 直接落盘source目录，不全部放内存；
> - 把已经保存好的物理文件路径交给kb_admin管理层；
> - 真正重计算不在API请求线程。

### 第2步：管理层建立批次写入SQLite队列
入口：`kb_admin/admin/ingest.py`

关键函数：`AdminIngestService.enqueue_saved_files()`

1. `enqueue_filter`过滤脏文件；
2. 生成 `ManagedBatch`、`ManagedDocument`；
3. 调用 `state_store.enqueue_files()`；
4. 在SQLite `files` 表写入记录，状态为 `queued`，记录 `batch_id`、`path`、`file_hash`、`stage="queued"`。

> SQLite状态机核心表在 `kb_admin/state_store.py`。

### 第3步：worker从SQLite claim待处理文件
入口：`kb_admin/worker.py` worker主循环

关键函数链：
1. worker.run() 循环；
2. `claim_capacity()` 查询当前机器内存负载，判断还能认领多少任务；
3. `claim_pending(db_path, limit, max_attempts)`：从 `files` 表挑 `pending/failed`、没超过重试上限的记录；状态更新为 `processing`；
4. `split_claimed_rows(rows)` 根据 `is_heavy_path(path)` 分成 light、heavy两组。

> 做的事情：
> - 看control表确认worker没有被暂停；
> - 看机器内存负载，决定是否继续claim；
> - 从files表选出pending/failed且未超过重试次数的记录；
> - 将记录状态改成processing；
> - 按文件规则分成light / heavy两类。

### 第4步：light / heavy两条路径分流
#### 4.1 light 文件路径
文件：`kb_admin/worker_support/pool.py`

关键函数：
- `new_pool()`：创建 `ProcessPoolExecutor`
- `submit_rows()`：把light任务提交进程池
- `process_one(file_id, path)`：子进程真正解析单个文件
- `wait_for_all_light_tasks()`：等待完成、超时判断、写索引、回写状态

路径特点：
- 使用进程池并发处理；
- 子进程启动时 `init_worker()` 预热OCR引擎；
- 解析完成输出jsonl，父worker统一做索引写入；
- timeout超时标记失败，必要时重建进程池。

#### 4.2 heavy 文件路径
文件：`kb_admin/worker_support/heavy.py` + `kb_admin/process_one_file.py`

关键函数：
- `is_heavy_path(path)`：判断是否heavy；
- `start_heavy_subprocess(file_id, path, stage)`：启动独立Python子进程；
- `poll_heavy_subprocess(task)`：轮询是否完成、是否超时；
- `process_one_file.main()`：独立子进程真正处理单个文件。

路径特点：
- 不走light的`ProcessPoolExecutor`；
- 每个heavy文件一个独立Python进程；
- 支持受控双heavy并发，不再死锁在单heavy串行；
- 超时由 `timeout_for_path()` 动态计算，不是全部写死420秒。

### 第5步：单文件解析、OCR、切chunk、embedding
真正核心收口：`kb_admin/ingestion.py`

关键函数链：
1. `iter_chunks_for_path(path, settings, include_ocr=True, ocr_engine=None)`
2. `_iter_embedded_chunks(...)`
3. `kb_poc.ingestion.ingestor.build_document_stream(...)`
4. `kb_poc.ingestion.ingestor.iter_document_chunks(...)`
5. `kb_poc.ingestion.ingestor.embed_chunk_batch(...)`

| 阶段 | 代码落点 | 做的事 |
|---|---|---|
| 路由parser | `build_document_stream()` | 根据后缀调用Excel/PPT/PDF/markdown parser |
| 文件解析 | `kb_poc/parsing/*.py` | 文件转为 `ParsedDocument` / `ParsedSegment` |
| segment切chunk | `iter_document_chunks()` | 将解析结果拆成 `DocumentChunk` |
| 小批量embedding | `embed_chunk_batch()` | 调用embedding client生成向量 |
| 元数据标注 | `finalize_chunk_batch()` | 给chunk打上来源标记 text/ocr |

> “全流式”指 ingestion层是generator流式；parser内部不一定generator。parser一次性产出ParsedDocument；ingestion之后分批embedding、分批落jsonl、分批写索引，不再把整个文档全部chunk全加载内存。

### 第6步：写chunk jsonl，作为parse与index的解耦层
落点：`kb_admin/ingestion.py`

1. 解析+embedding完成的chunk逐条写到 `data/kb_admin/jsonl/file‑<id>.jsonl`；
2. worker父进程后续再读取jsonl做索引写入；
3. parse/OCR与索引上传解耦；失败更容易定位是前半段解析，还是后半段索引写入。

### 第7步：chunk批次写入索引
落点：`kb_admin/worker_support/indexing.py`

函数链：
1. `upsert_with_retry(index_repo, document_id, version_id, batch_chunks)`
2. `index_repo.begin_document_upsert(document_id, version_id)`
3. `index_repo.append_document_chunks(document_id, version_id, batch)`
4. `index_repo.finalize_document_upsert(...)`

> index_repo 实现二选一：
> - 配置Azure → `azure_index_repository.py`
> - 本地模式 → `local_index_repository.py`

### 第8步：同步回管理层文档状态
落点：`kb_admin/worker_support/indexing.py` → `sync_managed_document()`

1. 更新 `documents.json` 的 `chunk_count`、`status`、`updated_at`；
2. 管理界面看到的文档状态和chunk计数来源于这里。

### 第9步：回写SQLite终态
落点：`kb_admin/state_store.mark_file_completed / mark_file_failed`

- 成功：`files.status = completed`；
- 失败：`files.status = failed`，记录error，增加attempt计数。

## 6. 全量重建链路怎么走
除了worker异步链路，还有全库重建链路。

### 6.1 管理端触发全量重建
入口：`kb_admin/admin/ingest.py :: rebuild_all_documents()`
- 建立 `ManagedJob`；
- 调用 `kb_poc.ingestion.ingestor.build_full_rebuild_stream()`；
- 流式产出chunk，调用index_repo；
- 更新管理层documents状态。

### 6.2 CLI触发全量重建
```bash
python -m kb_poc ingest
```
入口：`kb_poc/cli.py` → `ingestor.ingest_directory()`
- 扫描source目录；
- 单进程流式解析、embedding、写入索引；
- **不走SQLite worker队列**。

> 适合做完整修复、对比验证；不适合web上传用户实时业务。

## 7. 当前关键状态机
> 注意：`stage`字段更多用于日志，调度流转主要看`files.status`。

files表核心status：
- `pending`：待worker认领；
- `processing`：worker已经claim正在处理；
- `completed`：全部成功；
- `failed`：失败，可以重试。

`attempt`：重试计数；超过阈值不会再自动认领。

> `kb_admin/state_store.py`是SQLite状态机全部实现，目前职责很厚重。

## 8. 当前已做性能优化点

| 优化项 | 代码位置 | 收益 |
|---|---|---|
| ingestion层全流式 | `kb_admin/ingestion.py`、`kb_poc/ingestion/ingestor.py` | 避免整个文档全部chunk驻留内存 |
| heavy独立子进程+受控双并发 | `kb_admin/worker.py`、`kb_admin/worker_support/heavy.py` | 避免单个heavy大文件阻塞整体吞吐 |
| OCR引擎进程内复用 | `pool.py`、`process_one_file.py` | 避免每个文件反复初始化PaddleOCR |
| embedding批放大 | ingestion层 | 减少embedding请求次数 |
| embedding/Azure写入限流+重试 | `kb_poc/retrieval/embedding.py`、`azure_index_repository.py` | 降低429/503冲击 |
| 入队脏文件过滤 | `kb_admin/ops/enqueue_filter.py` | 垃圾文件不进入队列浪费worker资源 |

## 9. 工程维护关注事项
### 9.1 `kb_admin/state_store.py` 过肥
现在schema、migration、enqueue、claim、mark、control、health、reconcile、retry全部在一个文件，维护压力大。
设想后续拆分：
- `state_store_schema.py`
- `state_store_queue.py`
- `state_store_state.py`
- `state_store_control.py`

> 建议等worker新链路稳定后再重构，不要和稳定性验证并行。

### 9.2 管理层JSON store仍然是全量读写
`kb_admin/repositories/json_store.py`：`documents.json` / `jobs.json` / `batches.json` 整体读写。
文件量大之后会成为热点瓶颈；长期看迁SQLite或者细粒度KV存储。

### 9.3 `AdminIngestService.ingest_file()` append粒度偏细
`kb_admin/admin/ingest.py`
```python
for chunk in iter_chunks_for_path(...):
    self.service.index_repo.append_document_chunks(document_id, version_id, [chunk])
```
现在是单chunk append；可以改成小批量append，减少Azure调用次数。

## 10. 快速排障查阅清单
遇到“很慢 / 超时多 / 状态不对 / 管理页面显示不准”，按下面顺序定位：

| 问题类型 | 优先查阅文件 |
|---|---|
| 文件为什么没有进队列 | `kb_admin/admin/ingest.py`、`kb_admin/ops/enqueue_filter.py`、`kb_admin/state_store.py` |
| worker为什么不处理任务 | `kb_admin/worker.py`、`kb_admin/worker_support/dispatch.py`、state.db control表 / files表 |
| heavy为什么超时 | `kb_admin/worker_support/heavy.py`、`kb_admin/process_one_file.py`、worker.log |
| OCR为什么慢 | `kb_admin/worker_support/pool.py`、`kb_admin/process_one_file.py`、`kb_poc/parsing/ppt_ocr.py` |
| embedding为什么慢/报429 | `kb_poc/retrieval/embedding.py`、`kb_admin/ingestion.py`、`kb_poc/config.py` |
| Azure写入为什么慢 | `kb_admin/worker_support/indexing.py`、`kb_poc/indexing/azure_search_store.py` |
| 管理页面状态为什么不对 | `kb_admin/admin/worker_sync.py`、`kb_admin/repositories/json_store.py`、`kb_admin/admin/query.py` |

## 11. 一句话总结架构
> **`kb_admin`负责把文件变成“可调度任务”；`kb_poc`负责把文件内容变成“可检索知识”；中间依靠SQLite状态机、流式ingestion、jsonl中间文件、index repository把整条处理链路稳定衔接起来。**

后续重点验证：worker真实跑数，重点验证 dual‑heavy、heavy timeout，管理端单文件重建append粒度是否还需要优化。

---
