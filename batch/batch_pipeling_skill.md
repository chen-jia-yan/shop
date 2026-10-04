---
name: batch-pipeline-hardening
description: 编写、修改或审查任何批量/并行文档处理管线时必须遵守（OCR、解析、embedding、写索引、ingest、worker、multiprocessing、ProcessPoolExecutor）。目标是防止内存耗尽和原生崩溃（如 Windows 0xc0000005），保证坏文件能隔离、崩溃能自愈、可断点续跑。
---

# 批处理管线加固规则

处理批量/并行文档管线时，逐条遵守。核心前提：**瓶颈通常是内存不是 CPU；原生崩溃（0xc0000005/segfault）在 Python 里 try/except 抓不住，所以必须让系统在 worker 崩掉后还能活着并恢复。**

## 1. 内存纪律
- 不要构建巨型内存字符串。写 JSON 用 `json.dump(obj, file)` 流式写文件对象，不要先 `json.dumps` 成大字符串，不要 `indent`。
- 给 artifact/中间产物设大小上限，超限截断或跳过并记日志，绝不让单个超大对象顶爆内存。
- embedding/外部请求：单请求条数封顶（如 ≤16 条）、单条文本长度封顶（如 ≤8k），超出分批；绝不发无界 payload。
- 并发数按**内存**定，不是按 CPU 核数顶满。

## 2. 进程池健壮性
- 用 `ProcessPoolExecutor` + `initializer`，每个 worker 初始化一次重型实例（OCR 等）并全程复用，绝不在循环里反复 new。
- 设 `max_tasks_per_child`（如 20），定期回收 worker，释放原生库（Paddle/Pillow/numpy）累积的内存碎片。
- Windows spawn：只传可 pickle 的参数（路径、id），不要传图对象/数组/实例；worker 函数放模块顶层；启动放 `if __name__=="__main__"`。

## 3. 原生崩溃自愈（生产底线）
- 捕获 `concurrent.futures.process.BrokenProcessPool`：把本轮未完成的在飞任务退回 pending，`shutdown(cancel_futures=True)` 后重建进程池继续。
- 毒丸文件防护：给文件记 `crash_count`，某文件在崩溃中反复出现（如 ≥2 次）就标 `dead` 隔离，不再重试，避免无限循环拖垮整批。
- 可选：崩溃后对可疑批次用并发=1 串行重跑，精确隔离出真正有毒的文件。

## 4. 失败隔离与幂等
- 每个文件的处理包 try/except；单文件失败只标记该文件，`continue` 下一个，绝不中断整批。禁止 `except: pass`，错误必须记进 error 字段/日志。
- 用稳定 key 做幂等；重启后从 pending 续跑，已完成不重做；启动时把上次遗留的 `processing` 重置回 `pending`。
- 重试有上限，超限转死信（dead），不无限重试。

## 5. 并发与准入控制
- 上传与处理解耦：收文件即入队返回，处理在后台；大文件流式落盘，不在内存里同时持有全部字节。
- 重文件（大 Excel/PPT、大量图片）走低并发或串行通道，别和一堆小文件一起并发 OCR。
- 限制"同时在处理的重任务数"，用固定阈值，不要一上来做动态资源探测（复杂易错）。

## 6. 外部服务与背压
- 写索引/向量库用批量接口，不要一条条写。
- 对 429/503 用全局指数退避限流，不是每个文件各自猛重试。
- 每个任务设超时上限，卡死的自动判失败，不无限占用 worker。

## 7. 可观测
- worker 单独写结构化日志到磁盘：每文件开始/结束、耗时、峰值内存、完整错误栈。不要靠事后翻系统事件日志倒推崩溃。

## 提交前自查清单
- [ ] 没有巨型 `json.dumps`；embedding 请求有条数/长度封顶
- [ ] 进程池设了 `max_tasks_per_child`；重型实例每 worker 只建一次
- [ ] 处理了 `BrokenProcessPool`，有毒丸文件隔离
- [ ] 单文件 try/except 隔离，无 `except: pass`
- [ ] 幂等 + 断点续跑 + 启动重置 processing
- [ ] 并发按内存定；重文件分流
- [ ] 外部写入批量 + 429 退避；单任务超时
- [ ] worker 落盘结构化日志


