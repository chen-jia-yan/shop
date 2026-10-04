# 任务：为本地批处理系统加一个 watchdog（内存背压 + 自愈 + 告警），纯标准库

## 背景与约束
本地日文知识库 ingest 系统：web 进程收文件写 SQLite（ingest.db），独立 worker 进程用 ProcessPoolExecutor 消费 pending 任务做 OCR/解析/embedding/写 Azure AI Search。之前因 8 并发处理重文件导致内存耗尽 → MemoryError → Python 原生崩溃 0xc0000005。现在要加一个 watchdog 做内存背压、卡死回收、worker 自愈、健康告警。

硬约束：
- 只用 Python 标准库（内存监控用 ctypes 调 Windows API，禁止用 psutil 或任何需下载的包）。
- Windows 环境。不破坏现有 SQLite 状态机（pending/processing/completed/failed/dead）和断点续跑。
- 先输出改动计划和 diff，我确认后再实现。

## 改动 1：health.py —— 系统内存读取（ctypes，无依赖）
用 Windows API GlobalMemoryStatusEx 读系统内存占用百分比：
```
import ctypes
class _MEMSTAT(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
def memory_load_percent():
    st = _MEMSTAT(); st.dwLength = ctypes.sizeof(_MEMSTAT)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.dwMemoryLoad          # 0-100，系统内存占用百分比
```

## 改动 2：control 表 + dispatcher 内存背压
- 在 state_store 增加一张 control 表（单行）：paused(bool)、max_inflight(int，默认=MAX_WORKERS)。提供 read_control(db) / set_control(db, paused, max_inflight)。
- 在 worker 的调度循环里，每轮领任务前：
  - 读 control；若 paused，sleep 后跳过本轮不领新任务（让在飞的跑完）。
  - 领取数量 = min(max_inflight, 空闲 worker 数)，即控制同时在飞任务数，而不是改池子大小。
- 内存软/硬阈值（可作为顶部常量，先用这些起始值）：
  - 派发前若 memory_load_percent() >= 85：本轮不领新任务，sleep 3s，并 gc.collect()。
  - >= 92：额外多等，直到降到 80 以下再恢复领取。

## 改动 3：卡死任务回收（按超时）
- 在 state_store 增加 reset_stuck_timeout(db, seconds=600)：把 status='processing' 且 updated_at 早于 now-seconds 的行重置为 'pending'（视为超时，可 attempts+1）。
- supervisor 定期调用它，避免 worker 崩溃/卡死留下永远 processing 的孤儿任务。

## 改动 4：supervisor.py —— 独立守护进程
独立运行（python -m kb_admin.supervisor），循环（如每 5 秒）：
1. worker 存活检查：记录 worker 的 pid（worker 启动时把自己 pid 写进 control 表或一个 pidfile）；若进程已不存在，用 subprocess.Popen 重新拉起 worker（命令：python -m kb_admin.worker）。
2. reset_stuck_timeout(db)：回收卡死任务。
3. 采集健康快照并写入 health 表（见改动 5）。
4. 告警：内存>=85、pending 积压超过阈值、最近 dead 增长、反复重建进程池——任一触发就 logging.warning 到磁盘日志（单独的 supervisor.log）。
所有函数模块顶层；启动放 if __name__=="__main__"。注意：supervisor 只做轻量监控和拉起，绝不在自己进程里跑 OCR/embedding，保证它自身不会 OOM。

## 改动 5：health 表（给上层 agent 诊断用的数据源）
- state_store 增加 health 表，supervisor 每轮 upsert 一行快照：ts、memory_load、pending_count、processing_count、failed_count、dead_count、worker_alive(bool)、last_alert(text)。
- 提供 get_health(db) 返回最新快照。这张表将来给知识库 agent 的诊断层读，用来解释“系统现在什么状态、要不要处理”。

## 验收标准（请给出验证步骤）
1. 用重文件批次重跑：内存接近阈值时 dispatcher 自动暂停领新任务、内存回落后恢复，全程不触发 MemoryError/崩溃。
2. 手动 kill 掉 worker 进程：supervisor 在几秒内把它重新拉起，处理从 pending 续上。
3. 制造一个卡死的 processing 行：超时后被 reset 回 pending 并重新处理。
4. health 表能实时反映内存/各状态计数/worker 存活。

先输出：新增/改动文件清单 + 关键 diff（health.py、supervisor.py、state_store 的 control/health/reset_stuck、worker 调度循环的背压改动），等我确认后再实现。


