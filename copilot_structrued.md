# Copilot 指令：批处理管线加固

修改或新增任何批量/并行文档处理代码时（OCR、解析、embedding、写索引、ingest、worker、multiprocessing、ProcessPoolExecutor），必须遵守以下规则。核心前提：瓶颈通常是内存不是 CPU；原生崩溃（0xc0000005/segfault）在 Python 里 try/except 抓不住，所以必须让系统在 worker 崩掉后还能活着并恢复。

## 内存纪律
- 不构建巨型内存字符串。写 JSON 用 json.dump(obj, file) 流式写，不先 json.dumps 成大字符串，不 indent。
- artifact/中间产物设大小上限，超限截断或跳过并记日志。
- embedding/外部请求：单请求条数封顶（≤16）、单条长度封顶（≤8k），超出分批；不发无界 payload。
- 并发数按内存定，不按 CPU 核数顶满。

## 进程池健壮性
- ProcessPoolExecutor + initializer，每 worker 初始化一次重型实例并复用，绝不在循环里反复 new。
- 设 max_tasks_per_child（如 20）定期回收 worker，释放原生库内存碎片。
- Windows spawn：只传可 pickle 的参数（路径、id），不传图对象/实例；worker 函数放模块顶层；启动放 if __name__=="__main__"。

## 原生崩溃自愈
- 捕获 BrokenProcessPool：未完成的在飞任务退回 pending，shutdown(cancel_futures=True) 后重建进程池继续。
- 毒丸文件防护：记 crash_count，某文件反复导致崩溃（≥2 次）就标 dead 隔离，不无限重试。

## 失败隔离与幂等
- 每文件 try/except 隔离，单文件失败只标记该文件，绝不中断整批。禁止 except: pass，错误必须记录。
- 稳定 key 做幂等；重启从 pending 续跑，已完成不重做；启动时把遗留的 processing 重置回 pending。
- 重试有上限，超限转 dead。

## 并发与准入
- 上传与处理解耦，收文件即入队返回；大文件流式落盘。
- 重文件（大 Excel/PPT、多图）走低并发或串行通道。
- 限制同时在处理的重任务数，用固定阈值，不做动态资源探测。

## 外部服务与背压
- 写索引/向量库用批量接口；对 429/503 用全局指数退避；每任务设超时。

## 可观测
- worker 单独写结构化日志到磁盘：每文件开始/结束、耗时、峰值内存、完整错误栈。

## 提交前自查
- [ ] 无巨型 json.dumps；embedding 请求有封顶
- [ ] 进程池有 max_tasks_per_child；重型实例每 worker 只建一次
- [ ] 处理了 BrokenProcessPool + 毒丸隔离
- [ ] 单文件 try/except，无 except: pass
- [ ] 幂等 + 续跑 + 启动重置 processing
- [ ] 并发按内存定；重文件分流
- [ ] 外部写入批量 + 429 退避 + 超时
- [ ] worker 落盘结构化日志


