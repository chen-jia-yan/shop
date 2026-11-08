# 任务:让批处理 worker 全程使用健康的 .venv312,消除子进程跳到 base Python 的问题

## 已确认的事实
- `.venv312`(项目原始 venv)是健康的:直接启动时 `sys.executable` 指向 .venv312,paddleocr 从 .venv312\Lib\site-packages 正确导入,不跳 base。
- 之前子进程跳到 base Python312,是因为运行/派生时用到了**另一个坏掉的 venv(.venv-clean312,跳板 stub)或 base 解释器**,不是 .venv312。
- base Python312 未安装 paddleocr;.venv-clean312 是坏的。二者都不能用。

## 请修复(目标:全程只用 .venv312)
1. **worker 及其所有子进程只使用 .venv312 解释器**:
   - 确认启动 worker 用的是 `.venv312\Scripts\python.exe`。
   - 在创建进程池之前设置:`import multiprocessing as mp; mp.freeze_support(); mp.set_executable(sys.executable)`(此时 sys.executable = .venv312,可信)。
   - 所有 `subprocess.Popen`/`run` 启动 Python 子进程时,统一用 `sys.executable`(= 当前 .venv312),不要用裸 `"python"`、不要用硬编码的 base 路径、不要用 `sys._base_executable`、不要引用 .venv-clean312。
2. **清除对坏环境的引用**:全局搜索并移除任何指向 `.venv-clean312`、`Python312`(base)、或裸 `python` 的解释器路径/启动命令。
3. **移除 run_worker.py 的自我 re-exec**:若 run_worker.py 存在"用另一个解释器重新启动自己"的逻辑,删除它;worker 只应在当前 .venv312 进程内直接运行主循环,不重新拉起自己。
4. **子进程环境**:启动子进程时传入的 env,确保 `VIRTUAL_ENV` 指向 .venv312、PATH 前置 .venv312\Scripts,并移除任何指向 .venv-clean312 或旧路径的条目;不设 PYTHONHOME。
5. **启动自检日志**:worker 与每个子进程(池 worker、process_one_file)启动时打印 `sys.executable` 和 `paddleocr.__file__`,用于确认全部在 .venv312 下。

## 约束
- 只用标准库;不删除 PaddleOCR 模型缓存;不改动批处理/两阶段/OCR 主逻辑,只修解释器与环境的选择。

## 验收标准
- 用 .venv312 启动 worker 后,进程树中所有 python 进程(worker + 池子进程 spawn_main + process_one_file)都是 `.venv312\Scripts\python.exe`,**无任何 Python312(base)或 .venv-clean312 进程**。
- 自检日志显示各进程 sys.executable 与 paddleocr.__file__ 均在 .venv312 下。
- 杀掉 worker 后无子进程残留或被重新拉起。