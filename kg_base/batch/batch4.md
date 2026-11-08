# 任务：批处理"止血"加固（第一批，5 项），消除内存耗尽导致的 0xc0000005 原生崩溃

## 背景
本地日文知识库 ingest 系统，8 个 worker 进程并行处理 Excel/PPT（解析+OCR+artifact+embedding），运行时内存单调爬升，触发两处 MemoryError（artifacts.py 的 json.dumps、embedding.py 的 response.json），最终 Python 在原生库栈崩溃（0xc0000005），连带 IDE 被系统杀掉。本次只做能直接消除崩溃的 5 项改动，不做其他重构。

## 硬约束
- 只用标准库 + 已装的包，禁止新增任何 pip 依赖。
- Windows + 多进程 spawn：worker/初始化函数必须是模块顶层函数；只传可 pickle 的参数（file_id、path 字符串），不要传图对象/实例。
- 不破坏现有的断点续跑（pending/processing/completed/failed/dead 状态机）。
- 每项独立可验证；先输出改动计划和 diff，我确认后再实现。

## 改动 1：并发 8 → 4（内存是瓶颈，不是 CPU）
- 在 kb_admin/worker.py 把 MAX_WORKERS 从 8 改为 4，提为顶部常量，方便回调。
- 目的：先把内存峰值压下来，稳定后再谨慎回调。

## 改动 2：artifact 流式写盘，别建大字符串（内存杀手 A）
- 在 artifacts.py：把所有 `json.dumps(payload, indent=2)` 后再写文件的写法，改成直接流式写文件对象、去掉 indent：
```
import json
with open(target, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)   # 不建中间大字符串、不 indent
```
- 增加上限保护：定义 MAX_ARTIFACT_BYTES（如 20*1024*1024）。写入前估算大小，超限就截断内容或跳过该 artifact，并 logging.warning 记录是哪个文件、多大。绝不允许一个超大 artifact 把内存顶爆。

## 改动 3：embedding 单请求封顶 + 分批（内存杀手 B，兼治 429）
- 在 embedding.py：
  - 单次请求的条数封顶（EMBED_BATCH = 16），超出就分多批提交后拼接结果。
  - 单条文本长度封顶（如 MAX_CHARS = 8000），超长先截断，避免单条巨型输入。
```
def embed_texts(client, texts, batch=16, max_chars=8000):
    texts = [t[:max_chars] for t in texts]
    out = []
    for i in range(0, len(texts), batch):
        resp = client.embeddings.create(input=texts[i:i+batch])
        out.extend(resp.data)
    return out
```
- 保留/加上对 429、503 的指数退避重试（已有就复用），单文件 embedding 失败只标记该文件失败，不阻塞整批。

## 改动 4：worker 进程回收，释放原生库内存碎片
- 在 kb_admin/worker.py 创建进程池时加 max_tasks_per_child（Python 3.12 支持）：
```
from concurrent.futures import ProcessPoolExecutor
pool = ProcessPoolExecutor(
    max_workers=MAX_WORKERS,
    initializer=init_worker,
    max_tasks_per_child=20,   # 每处理 20 个任务换新进程，把内存还给系统
)
```
- 注意：换进程后新进程会重跑 init_worker（重新初始化 PaddleOCR），这是预期行为。

## 改动 5：原生崩溃自愈 + 毒丸文件防护（生产底线）
- 0xc0000005 是原生崩溃，try/except 抓不到，worker 会直接死，进程池进入 BrokenProcessPool、所有在飞任务作废。必须能自愈：
```
from concurrent.futures.process import BrokenProcessPool

def new_pool():
    return ProcessPoolExecutor(MAX_WORKERS, initializer=init_worker,
                               max_tasks_per_child=20)

pool = new_pool()
while True:
    rows = claim_pending(DB, MAX_WORKERS, MAX_ATTEMPTS)   # 原子标 processing
    if not rows:
        break   # 或 sleep 轮询
    futs = {pool.submit(process_one, fid, p): (fid, p) for fid, p in rows}
    try:
        for fut in as_completed(futs):
            fid, path = futs[fut]
            try:
                handle(fut.result()); mark(DB, fid, "completed")
            except Exception as e:                     # 普通业务异常：单文件隔离
                mark(DB, fid, "failed", error=str(e))
    except BrokenProcessPool:
        # 有 worker 原生崩溃：本轮在飞任务处理见下（毒丸防护）
        for fut, (fid, _) in futs.items():
            if not fut.done():
                bump_crash_and_requeue(DB, fid)
        pool.shutdown(wait=False, cancel_futures=True)
        pool = new_pool()                              # 重建，继续
```
- 毒丸文件防护（关键，别漏）：在 state_store 增加/复用一个 crash_count 字段。bump_crash_and_requeue(DB, fid) 的逻辑：crash_count+1；若 crash_count >= 2，把该文件标记为 'dead'（error='疑似导致原生崩溃，已隔离'），不再重试；否则退回 'pending'。防止某个文件每次都让进程池崩、无限循环拖垮整批。
- 可选增强：检测到 BrokenProcessPool 后，对退回的这批用 max_workers=1 串行重跑一轮，以便把真正的"毒丸"文件精确隔离出来（只有它会再次崩，从而被计数标 dead），其他文件正常完成。

## 交叉约束与验收
- 全程不得新增依赖；不得改动 PaddleOCR 模型缓存目录。
- 单文件失败（普通异常）只标 failed；疑似原生崩溃的隔离为 dead；其余文件不受影响。
- 断点续跑仍有效：中途 kill，重启后从 pending 续跑，completed 不重做。

## 验收标准（请一并给出验证步骤）
1. 用之前崩溃的那批（含重 Excel/大量 OCR）重跑，任务管理器内存曲线平稳、不再单调爬升到爆。
2. 故意放一个超大/畸形文件模拟 worker 崩溃：整批不崩，进程池自动重建，该文件在 2 次崩溃后被标 dead，其余文件全部完成。
3. 中途 Ctrl+C，重启 worker，从 pending 续跑，无重复处理、无重复写 Azure。

先输出：改动文件清单 + 每个文件的关键 diff + state_store 的 crash_count 改动，等我确认后再实现，不要顺带改其他东西。
</parameter>



