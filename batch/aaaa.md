# 任务:修复 worker.py 在 Windows spawn 下把主模块重跑成第二个 worker 的问题

## 根因(已定位)
Windows 多进程用 spawn,会重新 import 主模块 kb_admin/worker.py。当前 worker.py 的启动逻辑(创建 ProcessPoolExecutor、跑主循环、初始化等)没有被 `if __name__ == "__main__"` 正确隔离,导致每次 spawn 重新导入主模块时,又完整执行了一遍 worker 启动,派生出第二个 `-m kb_admin.worker`(进程树:venv worker → 另一个 worker → spawn_main)。同时该子进程用的是系统 Python312 而非 venv,因为 multiprocessing 的 spawn 启动器接管了进程创建,未用 sys.executable。

## 需要修复
1. **把所有"会启动进程/跑主循环"的代码移入 `if __name__ == "__main__":`**
   - worker.py 顶层(模块作用域)不得执行任何:创建 ProcessPoolExecutor、启动主循环、初始化 OCR 引擎、claim 任务等副作用。
   - 将这些整理进一个 `def main(): ...`,只在 `if __name__ == "__main__": main()` 里调用。
   - 模块被 import 时,只应加载函数/类定义,不产生任何进程启动副作用。
2. **强制 multiprocessing 用 venv 解释器,并做 spawn 安全初始化**,在 `main()` 最前面(或 `__main__` 保护内)加:
   - `import multiprocessing as mp`
   - `mp.freeze_support()`
   - `mp.set_start_method("spawn", force=True)`(与当前行为一致)
   - `mp.set_executable(sys.executable)` —— 确保 spawn 出来的子进程用 venv 的 python,而不是系统 Python312。
   - 若用 concurrent.futures.ProcessPoolExecutor,可通过 `mp_context=mp.get_context("spawn")` 传入已配置的上下文。
3. **确保 ProcessPoolExecutor 的 initializer 和目标函数都是模块顶层可 pickle 的函数**,不依赖模块级启动副作用。

## 约束
- 只用标准库 + 已安装包;不新增依赖;不删除 PaddleOCR 模型缓存;保持原有批处理/两阶段/隔离逻辑不变。

## 验收标准
- 启动 `python -m kb_admin.worker` 后,进程树中只有**一个** `-m kb_admin.worker`(venv 的 .venv312\Scripts\python.exe),其下**直接**是若干 `spawn_main(...)` 池 worker;**不再出现第二个 `-m kb_admin.worker`**,也不再出现 `Python312\python.exe` 的 worker。
- import kb_admin.worker(不作为主程序)时,不会启动任何进程。
- 杀掉 worker 后无子进程被重新拉起。