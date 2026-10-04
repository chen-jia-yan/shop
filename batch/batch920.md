# worker进程池问题复盘

## 现象
- 运行表面上一直是 `working`，但队列实际没有推进。
- 73 在文本阶段后能进入 `ocr_pending`，说明前半段和两阶段调度本身已经打通；但之后长时间无状态变化、无新错误、无日志推进。
- 同时另一个重文件 66 在同批执行中直接把进程池打坏，最终被记成 `dead`。
- 挂着的 worker 进程几乎不耗 CPU，也没有持续日志，表现更像进程池失效后的空转/僵住，不是正常 OCR 中。

## 是什么问题
现在的主题已经从**“状态机不对 / 索引写入不流式”**转移成：子进程池在处理重文件时仍会发生子进程异常退出，导致整个 `ProcessPoolExecutor` 失效。而当前 worker 没有把这个场景完整恢复成可继续推进 73 的状态。

更具体地说：
73 自身没有新的失败记录，但它依赖的 OCR/full 阶段并没有真的被执行完；与此同时，同轮或邻近轮次中的 66 把 pool 打坏，导致整体处理停滞。

## 可能原因
### 1. 子进程内部仍存在原生层崩溃
`process_one()` 虽然把 Python 异常包装成 `RuntimeError` 返回，但如果是 OCR 引擎、底层库、C 扩展、OpenMP、openpyxl/图像库之类触发的原生崩溃/进程被系统杀掉，是来不及转成 Python 异常的。
这类情况就会直接表现为 `BrokenProcessPool` / `child process terminated abruptly`。

### 2. 重文件的 OCR/full 阶段峰值内存仍然过高
已经修复的点：
- 删掉了三类明显放大器：
    - artifact 全量 `json.dumps` 预估导致的内存暴涨
    - 子进程把整份 chunk list 回传给父进程导致 IPC 放大
    - 索引整份 upsert 改成了 `begin/append/finalize` 流式写入

但 `write_chunk_batches()` 里仍然是：
1. `build_chunks_for_stage(...)`：一次性拿到 `List[DocumentChunk]`
2. 再一次性做 `_embed_chunks_in_batches(...)`
3. 最后写 JSONL

也就是 chunk/embedding/metadata 仍在子进程内整份驻留内存，只是 embedding 调用被分批了，请求批次小了，但整个文档对象图没有真正流式化。

### 3. worker 对 pool 崩坏后的恢复还不够闭环
- `run()` 里只有在 `as_completed(...)` / `future.result()` 过程中抛出 `BrokenProcessPool` 时，才会走 `_handle_broken_pool()`、重建 pool。
- 但 `_submit_rows()` 只在 `pool.submit(...)` 当场抛 `BrokenProcessPool` 时把 `selected_rows` 直接记为 `failed` 然后 raise；这会让主循环异常中断，不是温和和恢复。
- 同时，`_handle_broken_pool()` 只会 `bump_crash_and_requeue` 那些仍在 `pending_futures` 里的任务。像 73 这种如果尚未进入有效执行、或状态没有被完整回滚，就可能卡在 `ocr_pending`，而不是立刻继续重试。

### 4. 当前批处理模型会让重文件互相干扰
- 现在虽然有 `HEAVY_LIMIT = 1`，但这是每轮 `selected_rows` 中最多放 1 个 heavy，**不是全局单文件串行沙箱**。
- 并且存在 `deferred_heavy` 队列、pool 重建、下一轮 claim 再混合 light/heavy 的逻辑；如果 pool 已不稳定，其他文件可能先被标记 `dead`，重文件间仍可能共享同一个不健康的子进程池生命周期。

## 目前批处理实现是如何工作的
### 1. 队列与状态机
`files` 表核心状态：
- `pending`：待处理
- `processing`：文本/普通阶段处理中
- `text_done`：文本阶段已完成
- `ocr_pending`：等待 OCR/full 第二阶段
- `ocr_processing`：OCR/full 第二阶段处理中
- `completed` / `failed` / `dead`

`claim_pending()` 会从 `pending`、`failed`、`ocr_pending` 里取任务，并把：
- 普通任务置为 `processing`
- OCR 二阶段任务置为 `ocr_processing`

### 2. 两阶段调度
- `worker._phase_for_stage()`
    - `ocr_pending` → `full`
    - 其他 → `text`
- 子进程 `process_one(file_id, path, phase)`
    - `text` 阶段：`include_ocr=False`
    - `full` 阶段：`include_ocr=True`
- 完成后返回 `(file_id, next_phase, chunk_jsonl_path, chunk_count)`
    - 文本阶段若文件支持两阶段，则 `next_phase='ocr'`
    - `full` 阶段则 `next_phase='done'`
- 父进程据此 `mark(...)`
    - `next_phase == 'ocr'` → `text_done`，stage 收敛到 `ocr_pending`
    - 否则 → `completed`

### 3. 批处理与 heavy/light 分流
- `MAX_WORKERS = 4`
- `HEAVY_EXTENSIONS = {.pdf, .ppt, .pptx}`，以及大于 **15MB** 的文件也算 heavy
- 每轮 claim 后做 `_split_claimed_rows()`
    - light 先上
    - heavy 最多选 `HEAVY_LIMIT = 1`
    - 其余 heavy 暂存到 `deferred_heavy`

### 4. 子进程做什么
1. 初始化一次 OCR 引擎 `LocalPaddleProvider`
2. 构建 chunk
3. 分批做 embedding 请求：`EMBEDDING_BATCH_CHUNK_LIMIT = 12`
4. 把 chunk 结果写到临时 JSONL：`%TEMP%\jap‑cycle‑poc‑chunks\file‑{id}.jsonl`
5. **不再把整份 chunk list 通过进程间通信回传**

### 5. 父进程做什么
1. 读取 JSONL
2. 以 `INDEX_UPLOAD_BATCH_SIZE = 64` 批量读取并调用 index repo：
    - `begin_document_upsert`
    - `append_document_chunks`
    - `finalize_document_upsert`
3. 这样索引写入已是**流式/分批**，而不是整份文件一次性上传

### 6. 超时和内存保护
系统内存阈值：
- soft `85%`
- hard `92%`
- resume `80%`

- 单任务超时：`TASK_TIMEOUT_SECONDS = 240`
- 超时后会重建 pool
- 但这套保护更多是调度层保护，对**“子进程内部整份文档对象占满内存并原生崩掉”**并不能完全兜住。

## 当前结论
✅ 已经修好的部分：
- `ocr_pending` 能被真正重新调度
- terminal stage 已收敛成 `done`
- 索引写入已改成流式 `begin/append/finalize`
- 71 已完整跑通

⚠️ 仍未解决的核心：
> 重文件 OCR/full 阶段的子进程仍可能直接崩溃，导致进程池损坏。
> 这会把某些文件打成 `dead`（如 66），并让另一些文件停在中间态不推进（如 73）。

### 当前关键样本
| 文件 | 当前状态 | 说明 |
|------|----------|------|
| 71 | completed / done | 已验证跑通 |
| 73 | text_done / ocr_pending | 前半段成功，二阶段未推进 |
| 66 | dead / done | 本轮暴露出 BrokenProcessPool |
| 65 | dead / done | 之前问题文件，尚未在新链路下重测完成 |

## 下一步真正该修的方向
1. 不是继续盲跑，而是把子进程内的构建链路也做成**真正流式化/分段落盘**，至少避免 `write_chunk_batches()` 先把整个 `List[...]` 完整驻留内存再做 embedding。
2. 同时要把 `BrokenProcessPool` 后的任务回滚/重排逻辑补完整，避免文件停在 `ocr_pending` 或被非预期打死。

> 注：当前已经停掉 worker，不再后台跑任务，以上是基于现有代码与运行现场的问题复盘。

---

