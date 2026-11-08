# 任务:彻底移除 worker 的自启动/supervisor 层,消除幽灵进程

## 现状
进程树里始终有第二个用系统 Python312 运行的 `-m kb_admin.worker`(及其池子进程)。它的命令行是显式的 `-m kb_admin.worker`,说明代码里有地方用 subprocess/os.system 主动启动了另一个 worker。多次修改仍未根治。现在优先"断根 + 跑通",不再保留自动重启功能。

## 请执行
1. 全局搜索字符串 `kb_admin.worker`(排除 worker 模块定义自身),以及所有 `subprocess.Popen` / `subprocess.run` / `subprocess.call` / `os.system` / `os.spawn*`。列出每一处会启动 worker 子进程的代码。
2. **移除/禁用**这些"worker 再启动 worker""supervisor 自动拉起 worker"的代码路径,让 `python -m kb_admin.worker` 只运行一个单一的 worker 主循环本身,不再派生任何额外的 `-m kb_admin.worker` 子进程。(自动重启/守护功能暂时去掉,后续再单独、正确地实现。)
3. 保留并确认:所有真正需要的 ProcessPoolExecutor 池 worker 用 venv 解释器——在 `if __name__ == "__main__"` 保护内、创建池之前加:
   - `import multiprocessing as mp`
   - `mp.freeze_support()`
   - `mp.set_executable(sys.executable)`
4. 确认 worker.py 顶层(模块作用域)无任何进程启动副作用,全部收进 `if __name__ == "__main__": main()`。

## 约束
- 只用标准库 + 已安装包;不删除 PaddleOCR 模型缓存;保持批处理/两阶段/OCR/入库逻辑不变,只去掉"自启动第二个 worker"。

## 验收标准
- 启动后进程树中只有**一个** `-m kb_admin.worker`(路径为 .venv312\Scripts\python.exe),其下只有若干 `spawn_main` 池子进程,且这些子进程也用 .venv312 的 python,不再出现任何 Python312 的进程。
- 杀掉 worker 后无任何 worker 子进程被重新拉起。
- 列出被移除/禁用的所有自启动代码位置。