# 根治gost
根据这个文件来执行

我打算按最小、可回退的方式改，主要动 `kb_admin\worker.py`，可能顺带看一下 `kb_admin\process_one_file.py`，只是确认重文件子进程链已经用 `sys.executable`：

- **第一刀：强制 multiprocessing 也走当前 venv**
在 `kb_admin\worker.py` 里、创建 `ProcessPoolExecutor` 之前，加 `multiprocessing.set_executable(sys.executable)`。
目的很直接：Windows spawn 像“重新开一个新的 python 去 import 主模块”，这一步如果不钉死解释器，它就可能偷跑到 `C:\Program Files\Python312\python.exe`。
你文档里说的 `spawn_main(...) --multiprocessing-fork`，就是这条链。

- **第二刀：确认入口守卫**
检查 `kb_admin\worker.py` 的启动入口是不是已经在 `if __name__ == "__main__":` 下面。
这个像“电闸开关”，没有它，spawn 子进程重新 import 主模块时，可能又把 worker 主循环再跑一遍，自己生自己。

- **第三刀：退出时把孩子带走**
现在 `worker.py` 已经有 `try/finally` 和 `pool.shutdown(...)`，但我要再确认：
1. `KeyboardInterrupt` / 异常退出时也能走到；
2. 重文件那条 `subprocess.Popen` 如果 worker 退出，不能留孤儿。

这里大概率要在 `kb_admin\worker.py` 里给重文件子进程补“退出清理”逻辑，比如保留当前在跑的 Popen 句柄，结束时显式 `terminate/kill`。

- **第四刀：启动时做兜底清扫 + 单实例锁**
- 启动 worker 时，先扫一遍“本项目相关、但父进程已经没了的 python 幽灵进程”，只清理明确属于这个项目链路的，不乱杀别的 Python。
- 再加一个简单 PID 锁文件，防止同一时间起两个 worker。这个锁我会尽量做得傻瓜一点，避免引入复杂状态机。

- **第五刀：加诊断日志**
- 启动时打印 `sys.executable=... mp_executable=...`，这样一眼就能看出 multiprocessing 走的是不是 `.venv312`。

我预计会动的文件：
- 主要：`C:\Users\234393\Desktop\jap‑cycle‑poc\kb_admin\worker.py`
- 可能只读确认：`C:\Users\234393\Desktop\jap‑cycle‑poc\kb_admin\process_one_file.py`
- 如果做锁文件，优先还是放在 `worker.py` 里，不额外扩散文件，除非现有项目里已经有可复用的锁工具。

风险先说透：
1. “启动时清扫幽灵进程”这一步最敏感，清理范围如果判错，可能误杀别的 Python 任务。所以我只会匹配命令行里明确带本项目路径 / `spawn_main` / worker 链的进程。
2. 单实例锁如果写得太死，可能会挡住“上次异常退出但锁没清掉”的正常重启。所以会做“PID 还活着才算有效锁”的判断。
3. `set_executable(sys.executable)` 对 Windows spawn 是正解，但我会先确认现在的 `worker.py` 创建进程池的位置，避免放得太晚，导致已经来不及影响子进程。

这一步先停在说明，不直接改，符合文档要求。接下来可以做什么：你确认后，我就先只读 `kb_admin\worker.py` 和 `kb_admin\process_one_file.py`，把“具体改哪几个函数、锁文件放哪、幽灵进程怎么精确识别”讲清楚，然后再动手。