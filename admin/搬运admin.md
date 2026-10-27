# 知识库管理后端搬运方案（细化版）
状态：调研增强版方案（未实现）
目标：把 jap-cycle-poc 的知识库管理后端能力迁入 tap-ai-backend，并把执行步骤细化到可以按小步落地、逐步验收、尽量不出问题。
备注：目前我是想先将ui界面展示知识库信息，文档数量，向量块数量，最近更新时间，搜索文件名，展示文件名，文件大小，分块，索引状态（已索引/失败）文件类型，全部状态（筛选）--已索引，失败，待处理 以及上传文件这些急着需要的内容先搬过去，不是整个知识库管理页面的内容
结论先说：这件事可以做成，但前提是 tap-ai-backend 现有 Library 架构去“重组接入”，不能直接平移旧项目控制面板代码。只要把“控制面元数据、队列状态、上传落盘、worker回写、索引查询”这几块边界切清楚，并且分阶段只读上线、逐步放开写操作，整体是可以在不影响原有聊天主链和现有 Library 路由的前提下跑起来的。

## 2. 先回答你最关心的几个问题
### 2.1 按这个方案，能不能成功运行起来？
结论：能，但有两个前提必须先定。
前提1：tap-ai-backend 里这次先接的是知识库管理控制面，不是把旧项目整套 worker / OCR / ingestion 全并进来。
前提2：要先明确下面二选一中的哪条路线：

| 关键问题 | 推荐结论 | 原因 |
| ---- | ---- | ---- |
| 队列状态存哪里 | 先保留独立 SQLite 队列表，控制面主数据落 MySQL | 风险最低，最接近旧项目真实行为；如果第一步就把 claim/mark 全改成 MySQL，变量太多 |
| worker 放哪里 | 第一阶段先不搬 worker 进 ai-backend 进程内 | 旧项目 worker 依赖本地文件、子进程、OCR、索引写入，耦合重；先把控制面跑通更稳 |

也就是说，第一阶段最稳的做法是：ai-backend 先接“管理接口 + MySQL 控制面主记录 + SQLite 队列桥接 + 外部 worker 回写协议”。这样成功率最高。

### 2.2 旧项目这个上传逻辑是增量上传吗？
结论：是增量上传，而且不是简单“每次全量重建”。它本质上是“基于文件身份判定的增量上传 + 失败重试”。

### 2.3 这个“增量”能不能原样搬到 ai-backend？
结论：能保留语义，但不能照搬实现。
能保留的语义：
- 重复文件不重复处理
- 新文件才入队
- 失败文件可重试
- 管理页看到的是本次扫描结果 + 真实队列状态

不建议照搬的实现：
- JsonAdminStore
- KnowledgeAdminService 大而全编排
- 直接从 JSON + SQLite 拼列表

原因很简单：tap-ai-backend 已经明确是：
- API 薄壳：api/*.py
- 用例逻辑：application/*.py
- ORM / Repo：persistence/*.py
- 装配统一：bootstrap.py
- Settings 统一：config/settings.py
这个从 tap-ai-backend\src\tap_ai\bootstrap.py、application\library_chunks.py、persistence\library_draft_repo.py 都能直接看出来。
所以正确做法是：保留“增量判定规则”，重写“数据落点和调用方式”。

## 3. 这次重新核对后，确认的关键事实
### 3.1 ai-backend 里已经有可复用骨架，但现在还是“占位态”
证据：tap-ai-backend\src\tap_ai\bootstrap.py
- if getattr(app_settings, "library_enabled", False):
- 构造了 ChunkReviewService
- 构造了 EvalService
- 但 chunk_source=None
- publisher=None
- _mount_routers() 只挂了：
  - library_chunks_router
  - library_eval_router

这说明：
1. Library 方向已经被项目接受；
2. 新功能应该继续落在 Library 体系里；
3. 但“知识库管理控制面”还没真正接上。

### 3.2 ai-backend 的持久化风格已经很稳定
证据：tap-ai-backend\src\tap_ai\persistence\models.py 与 library_draft_repo.py 可以确认：
- 时间字段统一是 BigInteger 毫秒时间戳
- 常见字段有 deleted、delete_time
- repo 层负责分页、软删、条件状态流转
- application service 不直接拼 SQL

所以如果这次迁移想“不破坏原有风格”，那就必须：
- 主记录进 ORM / repo
- HTTP 响应走 dto.py
- 业务错误走 BusinessError("CCB001", "...")

### 3.3 旧项目的“运行态成功闭环”其实分成两半
这点很关键，之前方案里提了，但这次把证据补全了。

A. 上传与入队半链路
jap-cycle-poc\kb_admin\services.py
- upload_files()：先落盘
- enqueue_saved_files()：再做增量判定、拆子批、写 SQLite 队列

B. worker 完成后的回写半链路
jap-cycle-poc\kb_admin\runtime\upload.py
- index_repo.begin_document_upsert(...)
- append_document_chunks(...)
- finalize_document_upsert(...)
- 然后调用 KnowledgeAdminService().sync_worker_managed_document(...)
- 回写 chunk_count / text_chunk_count / ocr_chunk_count / status="active"

也就是说，旧项目不是“上传接口做完一切”，而是“上传控制面 + worker 执行面 + 回写同步”三段式闭环。

这会直接影响迁移设计：

如果 ai-backend 只搬上传接口，不定义 worker 回写入囗或回写适配层，最后管理页一定会卡在 pending / processing，不会真正闭环。

这是一个真实高风险点，不是假问题。

## 4. 最稳的迁移路线：先跑控制面，再接执行面
### 4.1 推荐总路线
我建议把迁移拆成 4 个阶段、14 个小步。先只做读，再做写，再接回写，最后才考虑深度整合 worker。

## 5. 详细到小步的落地方案
阶段 A：把数据模型和接口骨架先搭起来（只读优先）

步骤 A1：新增配置开关，不接业务逻辑
做什么 在 tap-ai-backend\src\tap_ai\config\settings.py 增加知识库管理控制面的配置项。建议新增字段
```python
library_admin_enabled: bool = Field(default=False)
library_admin_upload_root: str = Field(default="")
library_admin_queue_db_path: str = Field(default="")
library_admin_worker_callback_token: str = Field(default="")
library_admin_use_sqlite_queue: bool = Field(default=True)
```
怎么写
- 继续放在 Library 配置块下面
- 默认全给安全默认值
- 不改现有字段意义

步骤 A2：先定义 contracts，请求/响应模型定死
做什么 在 tap-ai-backend\src\tap_ai\contracts\library.py 里只追加知识库管理控制面请求模型，不改已有 chunks/eval 契约。建议新增模型组
- LibraryAdminDocumentListRequest
- LibraryAdminBatchListRequest
- LibraryAdminJobListRequest
- LibraryAdminFailedFileListRequest
- LibraryAdminRetryRequest
- LibraryAdminUploadRequest
- LibraryAdminDocumentActionRequest

建议字段 文档列表至少要覆盖：
- keyword
- status
- page
- page_size
- saas_id/workspace_id/project_id/user_id

怎么写 延续现有 BaseModel + Field(...) 风格，和 LibraryFileListRequest 保持一致。

步骤 A3：在 dto.py 里追加响应模型
做什么 在 tap-ai-backend\src\tap_ai\api\dto.py 追加控制面响应 DTO。建议新增
- LibraryAdminDocumentData
- LibraryAdminDocumentListData
- LibraryAdminBatchData
- LibraryAdminBatchListData
- LibraryAdminJobData
- LibraryAdminJobListData
- LibraryAdminFailedFileData
- LibraryAdminFailedFileListData
- LibraryAdminUploadResultData

怎么写 参照现在已有的：
- LibraryFileListData
- ChunkDraftData
- EvalRunData

即：
- 单条 Data
- 列表 Data
- model_config = {"from_attributes": True}

步骤 A4：先补 ORM，不写业务---ocr逻辑在sdk里，应该不用补 看下怎么能够最简便

做什么 在 tap-ai-backend\src\tap_ai\persistence\models.py 里追加3~4张表。
推荐最小表集
1. LibraryManagedDocument
2. LibraryManagedBatch
3. LibraryManagedJob
4. LibraryManagedDocumentVersion（可选但建议第一版就上）

怎么写
字段风格跟现有 LibraryChunkDraft 一致：
- id / create_time / update_time / deleted / delete_time
- 租户字段：saas_id/workspace_id/project_id/user_id
- 文档字段：file_name/source_file/file_hash/size_bytes/status/chunk_count/...

这里一定不要怎么写 不要把“文件队列状态”也直接塞进同一张文档表里做复杂状态流转。

步骤 A5：新增 repo · 先只做查询能力
做什么 新增：
- persistence/library_admin_repo.py
- persistence/library_admin_queue_repo.py（如果保留SQLite队列桥接）

第一阶段 repo 只实现这些
- list_documents()
- get_document()
- list_batches()
- get_batch()
- list_jobs()
- list_failed_files()

怎么写 完全参考 library_draft_repo.py：
- repo 内处理过滤条件
- repo 内做分页
- repo 返回 ORM 或简单对象
- service 再决定报错与组合输出

为什么先只做查询 因为读接口最容易先跑通，也最不容易影响原系统。这样能先验证：
- 路由挂载没问题
- DTO 没问题
- ORM 没问题
- session_factory 没问题

步骤 A6：新增 application service · 只做只读用例
做什么 新增 tap-ai-backend\src\tap_ai\application\library_admin.py 建议服务名：LibraryAdminService

第一阶段只放只读方法
- list_documents()
- get_document()
- list_batches()
- get_batch()
- list_jobs()
- list_failed_files()

怎么写 完全参照 ChunkReviewService 的写法：
- dataclass service
- 依赖 repo
- 对不存在/非法参数抛 BusinessError
- 不在 service 里写 SQL

步骤 A7：新增 API 路由文件 · 但先只挂只读接口
做什么 新增 tap-ai-backend\src\tap_ai\api\library_admin.py 首批只挂 6 个只读接口
- POST /tap/ai/library-admin/documents/list
- GET /tap/ai/library-admin/documents/{document_id}
- POST /tap/ai/library-admin/batches/list
- GET /tap/ai/library-admin/batches/{batch_id}
- POST /tap/ai/library-admin/jobs/list
- POST /tap/ai/library-admin/failed-files/list

怎么写 参照 api/library_chunks.py：
- router = APIRouter(prefix="/tap/ai/library-admin", tags=["library-admin"])
- _service(request) 从 app.state 取 service
- 接口层只做参数接收和 DTO 序列化

步骤 A8：在 bootstrap.py 条件装配 · 但默认不开启
做什么 在 bootstrap.py 中：
1. library_admin_enabled=True 时才构造 LibraryAdminService
2. _mount_routers() 中条件挂载 library_admin_router
3. app.state.library_admin_service = ...

怎么写
模仿现有 Library 装配：
- 现在已有：
  - app.state.library_chunk_service = ...
  - app.state.library_eval_service = ...
- 新增：
  - app.state.library_admin_service = ...

阶段 B：再接上传 · 但先只做“落盘 + 入管理记录 + 入队”
步骤 B1：把上传落盘能力抽成独立 port / helper，不直接抄旧 storage
做什么 新增一个上传落盘适配层，例如：
- application/library_admin_upload.py 或
- persistence/library_file_storage.py

职责只做两件事
1. 校验上传文件名和路径安全
2. 保存到 library_admin_upload_root

为什么不能直接抄旧的 ManagedFileStorage 旧项目是围绕 source_dir 和本地知识库目录组织的，跟 ai-backend 当前目录结构未必一致，而且要避免把路径策略写死。

步骤 B2：把“增量判定”逻辑迁成纯函数/独立模块
做什么 把旧项目这部分思路迁过来，但不要原样搬：
- 来源证据：jap-cycle-poc\kb_admin\filters\plan.py
- 核心能力：把上传文件分成 queued / retry / skipped / filtered

建议新文件
- application/library_admin_enqueue.py

内部函数建议
- build_upload_plan(...)
- classify_uploaded_file(...)

怎么写 输入：
- 本次上传文件元信息
- DB 中现有文档记录
- 现有队列状态
输出：
- queue_items
- retry_items
- skipped_items
- filtered_items
- scan_summary

步骤 B3：上传接口第一版只做到“可控入队”，不直接处理索引
做什么 新增写接口：
- POST /tap/ai/library-admin/upload 第一版接口内部只做
1. 收文件
2. 安全落盘
3. 生成 upload plan
4. 写 MySQL 控制面主记录
5. 写 SQLite 队列表（如果启用 SQLite 队列）
6. 返回扫描结果

不要在这个接口里做什么
- 不直接 OCR
- 不直接切片
- 不直接写 Azure AI Search
- 不在 HTTP 请求里同步跑重活

步骤 B4：把“批次/任务/文件”写入顺序定死，避免脏数据
做什么 上传入队时固定事务顺序：
1. 创建批次主记录
2. 创建文档记录/版本记录（必要时）
3. 创建任务记录
4. 写队列状态
5. commit

推荐实现
- MySQL 主记录一个事务
- SQLite 队列作为第二步写入
- 如果 SQLite 失败，要把 MySQL 主记录标记为失败批次，而不是假装成功

风险高于前面几步，但这是实打实的运行风险，不是假问题。

---

阶段 C：补“worker 回写闭环”，这是能否真正跑通的关键

步骤 C1：先定义一个回写协议，不急着搬 worker
做什么 新增一个 ai-backend 可调用的内部回写接口或 service 方法。推荐优先级 优先做 service + 内部函数，再决定是否暴露 HTTP。建议方法名
- sync_managed_document_result(...)
- mark_job_completed(...)
- mark_job_failed(...)

输入至少要有
- file_path 或 document_id
- chunk_count
- text_chunk_count
- ocr_chunk_count
- status
- error_message（失败时）

证据来源 旧项目是这么回写的：
- runtime/upload.py -> sync_worker_managed_document(...)

为什么这一步必须有 因为没有回写，管理页永远只能看到 pending / processing，不会变成 active / completed。

风险高。这是闭环的关键路径。

步骤 C2：先做“假回写测试”，确认控制面闭环无误 ---这步有必要吗
做什么 在不接真实 worker 的情况下，先用测试或脚本模拟回写：
- 入队一条记录
- 人工调用回写方法
- 检查文档状态、批次状态、任务状态、chunk_count 是否同步更新

怎么核验成功 至少要看到：
1. 文档列表里的 chunk_count 更新了
2. 文档状态从 pending/processing 走到了最终态
3. 批次汇总状态正确
4. 失败文件列表可见失败数据

为什么要先假回写 这样能先证明控制面设计没问题，再去接真实 worker，定位更容易。

步骤 C3：再决定 worker 对接方式，不建议第一版内嵌 --我的想法是设计好步骤，按步骤一步步来，一起实现了，而不是分第一版，第二版迭代实现，那样我会忘，会乱

做什么 第二阶段再决定：
- 外部 worker 调 ai-backend 回写接口
- 还是 ai-backend 内部有一个管理命令 / worker 进程 推荐第一版：外部 worker + ai-backend 回写协议 原因 旧项目 worker 依赖：
- 子进程
- OCR
- 大文件切片
- 索引写入
- 本地文件路径 这些都不是 ai-backend 当前主链的一部分，一次性并进来太容易牵连现有系统。---可否直接调用他的sdk入库逻辑
风险 中高。不是不能做，而是第一版不建议做。

阶段 D：最后才补写操作：重试、重建、删除

步骤 D1：先做“失败文件重试”
为什么它优先于重建/删除 因为它最贴近旧队列语义，也最容易复用旧逻辑。证据 jap-cycle-poc\kb_admin\services.py：
- retry_failed_files() 会把 failed/dead 重置为 pending
- 再刷新批次状态 在 ai-backend 里怎么做
- 更新 queue repo
- 重置选中文件状态
- 重算相关批次聚合状态
- 返回 retried/file_ids/batch_ids

风险 中。要注意不能误重试全部文件。

步骤 D2：再做“重建文档”
本质是什么 不是简单改个状态，而是把已有文档重新入队处理。在 ai-backend 里建议做法
- 新建一个 rebuild job
- 关联原 document_id
- 保留历史版本
- 不直接覆盖当前版本记录，等新处理成功再切 active version 为什么 这样最安全，回滚也容易。风险 中高。这里如果直接覆盖，很容易损坏当前可用文档状态。

步骤 D3：删除文档最后做 ---删除文档的逻辑先不做 等后续有时间了再补上去
为什么最后做 因为删除涉及：
- 控制面主记录
- 索引文档
- 文件源数据是否删
- 是否软删/硬删

旧项目这里就已经区分了：
- hard_delete=False 默认只软删

这说明删除天然比重试更敏感。在 ai-backend 里建议 第一版只做软删：
- 文档主记录软删
- 任务批次仍可审计查询
- 不自动删源文件
- 不自动删索引，除非明确走 rebuild / purge 操作 风险高。必须最后做。

---

6. 真实风险清单（只列有证据、确实可能发生的）

风险1：只搬上传接口，不搬回写闭环，系统会一直卡在处理中
结论：这是最真实的风险。证据：
- 旧项目上传只是 upload_files() + enqueue_saved_files()
- 真正把 chunk_count/status 写回去的是 runtime/upload.py -> sync_worker_managed_document() 后果：
- 批次永远 processing
- 文档 chunk_count 不更新
- 失败文件列表不准确 规避方案：
- 第一版必须定义回写 service / 接口
- 上线前先做假回写联调

风险2：如果把文档状态和队列状态混成一套，会把状态机搞乱
证据：
- 旧项目队列状态在 SQLite：pending/processing/completed/failed/dead
- 文档管理状态回写时会设为 active
- 两者不是一个层级 后果：
- 前端筛选选项混乱
- completed 和 active 混用
- 删除/重建时逻辑冲突 规避方案：
- MySQL 存文档控制面状态
- SQLite/MySQL 队列表单独存运行状态
- service 层再做聚合视图

风险 3：如果第一版就把 claim/mark 全改写成 MySQL，成功率会下降

证据：
- 旧项目 state_store.py 的真实运行逻辑是围绕 SQLite 原子更新写的
- claim_pending() 里直接 BEGIN IMMEDIATE
- mark() 还会顺手重算批次状态 后果：
- 第一版变量太多
- 很难判断问题出在迁移语义还是存储实现 规避方案：
- 第一阶段先保留 SQLite 队列桥接
- 等控制面稳定后再评估是否并表到 MySQL

风险 4：上传路径如果写死，会重现你之前问过的共享目录/异机启动问题 ---路径不要写死

证据：
- 你前面已经多次问到 start.bat、共享目录、监听地址、写死路径问题
- 这类问题在知识库上传场景里同样会复现 后果：
- 测试机能跑，换机器挂掉
- worker 找不到文件
- 上传目录和索引目录不一致 规避方案：
- 上传根目录走 settings
- 回写时保存相对路径或规范化路径
- 不在代码里写死桌面路径、盘符路径

风险 5：如果用 file_name 做增量判重，会误伤同名不同文件 用 doc_id 呢

证据：
- 旧项目最终依赖的是 file_hash 唯一约束，而不是只看名字
- state_store.py 明确有 file_hash TEXT UNIQUE 后果：
- 新文件被误判成重复
- 旧文件被错误覆盖 规避方案：
- ai-backend 中增量判定必须以内容哈希为主、文件名为辅
- 文档展示层可以显示 file_name，但业务判重不要只看 file_name

7. 哪些点不用过度担心

下面这些不是当前的高风险点：
1. API 路由风格是否能接进去：这个没问题，现成范本就是 api/library_chunks.py 和 api/library_eval.py
2. application service 风格是否有落点：有，ChunkReviewService 就是标准范本。
3. ORM / repo 风格是否清楚：也很清楚，LibraryChunkDraft 和 DraftRepo 已经说明了。
4. 会不会影响聊天主链 / LangGraph：只要控制面单独 feature flag，不会影响。因为这次根本不碰 chat 主链。所以这次最该关注的不是“风格能不能接”，而是：
- 数据边界切没切清
- 回写闭环有没有补上
- 增量判定是不是保真

8. ai-backend 里怎么核验“不影响原有代码内容”

这里给你一套最稳核验顺序。

8.1 启用方式必须走 feature flag

要求：
- library_enabled=False 时，现有行为逐字不变
- library_enabled=True 但 library_admin_enabled=False 时，只挂 chunks/eval，不挂 admin
- 只有两个都打开时才挂 admin 路由 核验点
1. 不开 admin 开关时，/openapi.json 里看不到 library-admin
2. 原有 chat/files/conversations 路由完全不变
3. 原有 library chunks/eval 路由仍可访问

8.2 先做“只读冒烟”

实现完阶段 A 后，先测：
- /tap/ai/library-admin/documents/list
- /tap/ai/library-admin/batches/list
- /tap/ai/library-admin/jobs/list
- /tap/ai/library-admin/failed-files/list 通过标准
- 路由能进
- DTO 正常返回
- 分页字段齐全
- 空数据时返回空列表，不报 500

8.3 再做“上传但不接真实 worker”的可控测试

测试方式：
1. 上传一个新文件
2. 检查 upload 返回里有没有：
   - queued_items
   - skipped_items
   - retry_items
   - filtered_items
3. 检查 DB 里批次、文档、任务是否生成
4. 检查 queue 表是否有 pending 记录

通过标准
- 新文件 -> queued
- 重复文件 -> skipped
- 失败文件复传 -> retry

8.4 再做“假回写闭环测试”
1. 手工调用回写 service
2. 把某条 pending 记录置为 completed
3. 回写 chunk_count/text_chunk_count/ocr_chunk_count
4. 重新查 document/batch/job 列表
通过标准
- 文档 chunk_count 变化正确
- 批次状态聚合正确
- failed-files 列表不再包含该文件

8.5 最后做“原有功能回归核验”
至少核这些：
- /tap/ai/conversations/*
- /tap/ai/files/*
- /tap/ai/library/files/list
- /tap/ai/library/eval/*
目标 证明这次新增控制面没有影响原有聊天、文件、library chunks、library eval。

9. 具体建议的测试拆分

单测层
重点给这些模块补单测：
1. build_upload_plan()
2. LibraryAdminService.list_documents()
3. LibraryAdminService.upload()
4. LibraryAdminService.retry_failed_files()
5. sync_managed_document_result()

API层
参照 tests/unit/test_library_chunks_api.py / tests/api/test_library_eval_api.py 的风格，补：
- admin list 路由
- upload 路由
- retry 路由
- detail 路由

集成层
最少做 3 条：
1. 新文件上传 -> pending
2. 重复上传 -> skipped
3. 假回写 -> completed / active

10. 最终优化后的搬运建议（推荐版本）

推荐版本：V1 稳妥版
V1 范围：
- MySQL：文档/版本/批次/任务主记录
- SQLite：队列状态
- ai-backend：只负责管理接口 + 上传落盘 + 增量入队 + 回写聚合
- worker：暂时外置
优点
- 最接近旧项目真实行为
- 风险最低
- 最容易跑通
- 对现有 ai-backend 侵入最小
缺点
- 短期内是双存储 但这个缺点是可接受的，因为它能换来更高的可落地性。

不推荐版本：V1 就全改 MySQL + 内嵌 worker
为什么不推荐 因为这会把下面几件事绑在一次改动里：
- 控制面迁移
- 队列状态机迁移
- worker 执行迁移
- 本地文件目录策略迁移
- 回写闭环迁移
变量太多，出了问题不好拆。

11. 最终结论
这次把方案再细化后，结论更明确了：
1. 可以搬，而且能跑起来。
2. 旧项目上传逻辑本质上就是增量上传，证据已经在 target_mode="incremental"、build_enqueue_plan()、file_hash UNIQUE 这三处拿到了。
3. 最真实的风险不是风格问题，而是闭环问题：如果没有 worker 回写适配，系统表面上能上传，实际上跑不闭环。
4. 第一阶段最稳方案是：
   - ai-backend 接控制面
   - MySQL 存主记录
   - SQLite 保留队列语义
   - 外部 worker 处理重活
   - ai-backend 提供回写聚合
5. 只要按“先只读、再上传、再假回写、再真实对接”的顺序推进，成功率是高的，而且不会影响原有聊天主链和现有 library 功能。
