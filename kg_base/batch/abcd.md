# 任务:修复 worker 自己又拉起第二个"系统 Python"worker 的问题(幽灵进程根因)

## 现象与证据
Windows 上运行 worker 时,进程树是:
```
PID 11360  (.venv312\Scripts\python.exe)  -m kb_admin.worker      ← 我用 venv 启动的 worker
  └ PID 23940  (Python312\python.exe)      -m kb_admin.worker      ← 它又拉起的“系统 Python”worker(幽灵)
       └ PID 21020 (Python312\python.exe)  spawn_main(...)         ← 23940 的 multiprocessing 子进程
```
问题有两个:
1. worker 通过 `subprocess.Popen` 自启动子进程时,用了**裸的 `"python"`**,在 PATH 上解析成了**系统 Python(Python312)**,而不是当前 venv(.venv312),导致冒出一个用错解释器、带系统环境的 worker。
2. worker **自己又启动了一个 worker**(worker→worker),这是多余的一层;每次启动都会重新生成这个幽灵,杀掉子进程后还会被重新拉起。

## 需要修复

### 1. 所有自启动子进程一律用当前解释器
- 全项目搜索 `subprocess.Popen` / `subprocess.run` / `os.spawn*` 等,凡是启动 Python 的地方,把命令里的 `"python"` / `"python.exe"` 一律替换为 `sys.executable`(当前运行的 venv 解释器)。
- 例:`subprocess.Popen(["python", "-m", "kb_admin.worker", ...])` → `subprocess.Popen([sys.executable, "-m", "kb_admin.worker", ...])`。
- 隔离重文件用的子进程(process_one_file 等)同样必须用 `sys.executable`,确保子进程和父进程用同一个 venv 环境。

### 2. 去掉 worker 再拉起 worker 的重复层
- 定位 `kb_admin.worker` 里"启动另一个 `-m kb_admin.worker`"的代码路径,判断它是否必要:
  - 如果这是一个多余的自启动/守护包装,**直接移除**,让 `python -m kb_admin.worker` 只运行一个 worker 主循环本身。
  - 如果确实需要 supervisor(守护+自动重启),则只保留**单层**结构:supervisor 进程负责拉起并监控**一个** worker;worker 主循环内部不得再启动另一个 worker。且 supervisor 拉起 worker 也必须用 `sys.executable`。
- 结果:正常启动后,进程树里只应有"一个 worker(+ 它的 ProcessPool / 隔离子进程)",不再出现第二个 `-m kb_admin.worker`。

### 3. 单实例锁(防止再次出现双份)
- worker 启动时获取单实例锁(PID 锁文件或 SQLite `control` 表写运行状态)。已有实例在运行则拒绝启动并打印提示(如 `worker already running, pid=...`)。正常退出释放锁;残留锁(对应 PID 已不存在)自动清理。

## 约束
- 只用 Python 标准库 + 已安装包,不新增需下载依赖;Windows spawn,入口 `if __name__ == "__main__"`;不改动索引与批处理主逻辑之外的行为;不删除 PaddleOCR 本地模型缓存。

## 验收标准
- 启动 worker 后,`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select ProcessId,ParentProcessId,CommandLine` 中只有**一个** `-m kb_admin.worker`,且其可执行路径为 `.venv312\Scripts\python.exe`(venv),不再出现 `Python312\python.exe` 的第二个 worker。
- 杀掉 worker 后不会有子进程被自动重新拉起。
- 再次启动时被单实例锁拒绝,不出现两个 worker 并存。
