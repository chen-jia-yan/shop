我刚核过当前实现，有几个已确认的事实：
- `kb_admin\worker.py` 现在创建 `ProcessPoolExecutor(...)` 时，没有显式传 `mp_context`。这意味着它走的是默认 multiprocessing context。
所以这里只要在创建进程池之前调用 `multiprocessing.set_executable(sys.executable)`，理论上就会作用到这个默认 context。上游 spawn 出来的孩子就该跟父进程一样用 `.venv312`。
- `kb_admin\process_one_file.py` 入口已经有 `if __name__ == "__main__":` 守卫。
- 重文件子进程这条链已经是 `sys.executable` 启动，在 `kb_admin\worker.py` 的 `_run_heavy_subprocess()` 里已经这么写了，所以这块不是主风险点，真正坑主要在 `ProcessPoolExecutor` 那条轻任务进程池。
- 当前代码里没有锁文件，也没有启动清扫幽灵进程的逻辑。

我准备这样改，还是尽量只动 `kb_admin\worker.py`：

## 1. 把 multiprocessing 解释器钉死到当前 venv
- 在 `worker.py` 里、第一次创建进程池之前，加 `import multiprocessing as mp` 和 `mp.set_executable(sys.executable)`。
- 同时会在日志里打印：
  - `sys.executable=...`
  - `mp_executable=...`
- 你提醒的那个坑我会明确处理：
  如果后面发现代码显式传了 `mp_context`，那只设全局 `set_executable()` 可能不够，得确认传给 `ProcessPoolExecutor` 的那个 context 也吃到这个设置。
- 但从我刚查到的当前代码看，现在没有自定义 `mp_context`，所以默认 context 场景下，这一刀是有效的，不是“看着改了实际没生效”。

## 2. 保留并确认 `__main__` 守卫
- `process_one_file.py` 已经有。
- `worker.py` 底部现在也有：
```python
if __name__ == "__main__":
    run(run_once=False)
```
这块我会再确认，不要因为加启动清扫 / 锁文件，把启动逻辑挪到守卫外面。
> 凡是会产生子进程、扫描进程、加锁的入口动作，都必须放在 `if __name__ == "__main__":` 链路内。

## 3. 退出时清理子进程，不留孤儿
- 轻任务进程池这边，已经有 `try/finally + pool.shutdown(...)`，但我会再加固：`KeyboardInterrupt` / 异常退出也要保证走到清理分支，`shutdown` 参数调整成更适合“收尾+不留孤儿”的模式。
- 重文件那边：`_run_heavy_subprocess()` 正常超时会 `kill()`，但父 worker 如果被 `Ctrl+C` / 异常打断，正在跑的 `Popen` 子进程仍有可能悬留。
- 方案：在 `worker.py` 维护一个“当前正在运行 heavy 子进程句柄集合”，在 `finally` / 异常退出分支里，对这些句柄显式做 `terminate/kill`。

## 4. 启动时清扫幽灵进程 + 简单PID单实例锁
启动 worker 时先做一轮清理，**匹配条件收得很严格，宁可漏杀不乱杀**：
- 只看 `python.exe`
- 排除自己当前 worker 进程 PID
- 命令行必须包含：`spawn_main` / `--multiprocessing‑fork`
- 命令行必须带上本项目路径，避免误伤其它项目的 Python。

> “响铃日志”：只要真杀掉进程，输出明显的 warning/error 日志，打印被杀死 PID + 完整命令行。
> 正常修完前面1‑3刀后，清扫应该大多是空扫；如果经常打印这条日志，代表还有漏的bug，不能静默吞掉。

锁文件逻辑：
- 锁文件做成“PID还活着才算有效锁”。
- 上次异常崩溃锁文件残留，但里面记录的PID已经不存在，允许正常启动，不会直接锁死。

## 5. 为什么尽量只改 worker.py
问题根因都集中在：worker 如何拉起进程池、如何退出、如何启动 heavy 子进程、启动入口。
`process_one_file.py` 更偏向被调用的单次脚本，已经有 `__main__`，本身不是常驻父进程，不适合把锁、进程清扫逻辑散到那里。

## 风险重申
1. **最大风险：启动清扫误杀**。匹配条件严格，宁可漏，不乱杀。
2. **锁文件处理不当阻塞重启**：必须校验锁内PID是否真实存活。
3. **`set_executable()` 放置太晚等于假修复**：必须放在任意 pool 创建之前；并且打日志现场可观测。

如果你确认，下一步就按这套方案动手，优先只修改 `kb_admin\worker.py`，一并落实：响铃日志、`set_executable`、锁文件、heavy子进程句柄清理。
改完之后，会检查当前机器Python进程链，验证是否还会混入 `C:\Program Files\Python312` 这类外部解释器。

---

### 预计改动文件
- 主要：`kb_admin\worker.py`
- 只读确认：`kb_admin\process_one_file.py`

### 改动要点总览
1. ✅ `mp.set_executable(sys.executable)`，放在进程池创建前 + 打印诊断日志
2. ✅ 严格守住 `if __name__ == "__main__"` 入口守卫，所有启动逻辑放在守卫内部
3. ✅ 加强 finally/信号处理：进程池 shutdown + heavy Popen 句柄 terminate/kill
4. ✅ 启动阶段严格条件的幽灵进程清扫，杀掉时输出明显告警日志
5. ✅ PID锁文件，校验PID存活，避免异常崩溃后锁死无法重启
6. ✅ 尽量只改动 worker.py，逻辑收敛，便于回退

