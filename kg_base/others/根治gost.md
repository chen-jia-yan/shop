# 任务:根治幽灵进程(多进程 spawn 用错解释器 + 退出留孤儿)

## 实锤诊断(基于现场排查)
worker 跑在 .venv312 里,但 multiprocessing 生的子进程跑在 base python(`C:\Program Files\Python312`),命令行是 `spawn_main(...) --multiprocessing-fork`。父进程死后子进程变孤儿、不被清理,重启又生新的。要从两个根因同时修:①子进程用错解释器 ②退出不清理子进程。

## 请先说明再动手
先读 `kb_admin/worker.py`(进程池创建、主循环、退出处理)和 `kb_admin/process_one_file.py`,用大白话说清打算怎么改、动哪几处、风险在哪,等我确认再改。分小步、可回退。

## 具体改动
1. **强制子进程用当前 venv 的 python**:在创建进程池之前(worker 启动处)加 `multiprocessing.set_executable(sys.executable)`;所有 `subprocess.Popen` 启动的重文件子进程也统一用 `sys.executable`。目的:spawn 出来的孩子必须和父进程用同一个 .venv312 python,绝不能是 base python。
2. **确认有 `__main__` 守卫**:worker 的启动代码必须在 `if __name__ == "__main__":` 下(spawn 会重新 import 主模块,没守卫会重复起 worker)。检查并补齐。
3. **退出时清理子进程**:把进程池用 try/finally 包住(或 `with`),正常退出、异常、KeyboardInterrupt(ctrl+C)都要走到 `executor.shutdown(cancel_futures=True)`;重文件的 Popen 子进程在退出时也要 kill,别留孤儿。
4. **启动时清扫 + 单实例锁(兜底)**:worker 启动时,先扫掉上一轮遗留的 `spawn_main` python 孤儿(仅限本项目、非当前进程的子进程),再用一个 PID 锁文件防止同时跑两个 worker 实例。保持简单,别过度设计。
5. **诊断日志**:启动时打印一行 `sys.executable=... mp_executable=...`,方便我确认用的是 venv 而不是 base。

## 必须保持不变
- 每进程复用 OCR、`max_tasks_per_child`、内存回收逻辑不变。
- 重文件独立子进程隔离、超时、池重建不变。
- 失败重试 / 崩溃计数 / 断点续跑 / 幂等 / embedding 限速批量不变。
- 只用已装的包(优先标准库/ctypes;别为这个装新包)。

## 验收标准
- worker 跑起来时,再查一次 `Get-CimInstance Win32_Process -Filter "name='python.exe'"`:所有 python 进程都在 **.venv312**,**没有一个在 `C:\Program Files\Python312`**。
- worker 正常结束或 ctrl+C 后,**没有遗留的 python 孤儿**。
- 反复重启 worker,python 进程数不累积。
