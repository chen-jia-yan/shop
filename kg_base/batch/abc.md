# 任务:清除残留的幽灵 worker 进程,并修复其无法被干净关闭、自动复活的问题

## 背景
在 Windows 上,worker 先前在系统终端里运行,用 Ctrl+C 关闭后并未被真正杀干净:有一个残留(孤儿)worker 进程仍在后台运行,带着终端的环境;其上很可能挂着一个会自动重启 worker 的守护进程(supervisor),导致"杀掉又复活、关不掉"。现在它还和 PyCharm 里启动的 worker 并存。请先清理现有幽灵进程,再修复根因。

## 第一部分:定位并杀掉现有幽灵进程(在集成终端执行)
> 执行前先停止 PyCharm / 编辑器里正在运行的 worker,避免误判。

1. 列出所有 python 进程及其命令行和父进程(PowerShell):
```
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```
2. 找出命令行包含 `kb_admin.worker` 或 supervisor 脚本的进程。若某个 worker 的 `ParentProcessId` 指向另一个 python 进程,那个父进程就是自动重启它的 supervisor。
3. **先杀 supervisor(父),用 `/T` 连子进程一起杀、`/F` 强杀:**
```
taskkill /PID <supervisor_PID> /T /F
```
4. 再次运行第 1 步的命令确认:不再有残留的 `kb_admin.worker` / supervisor 进程。
5. 如确认当前没有需要保留的 python 进程,可一次性清干净:
```
taskkill /IM python.exe /F
```
6. 报告清理前后进程列表对比,确认幽灵已消失。

## 第二部分:修复根因(改代码,防止再次出现)

### 1. 优雅退出
- worker 和 supervisor 注册 `signal.signal(SIGINT, ...)` 和 `SIGTERM` 处理器:收到信号后 `ProcessPoolExecutor.shutdown(wait=True, cancel_futures=True)`,并显式 `terminate()`/`kill()` 所有 `subprocess.Popen` 子进程,再退出。确保 Ctrl+C 不留孤儿。
- 用 `atexit` 兜底,进程退出时清理所有子进程。

### 2. 子进程随父进程一起死(Windows)
- 用 Windows Job Object,设置 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`,把所有子进程(池 worker、隔离子进程)加入该 Job;父进程一旦退出,子进程被系统自动全部杀掉。
- 通过标准库 `ctypes` 调用 Job Object API 实现(不新增依赖);若实现受限,退而求其次:退出时对自身进程树执行 `taskkill /T`。

### 3. 单实例锁,禁止重复启动
- worker 启动时先获取单实例锁:PID 锁文件,或在 SQLite `control` 表写一行"运行中 + PID + 启动时间"。
- 若检测到已有实例在运行(锁存在且对应 PID 仍存活),**拒绝启动并打印清晰提示**(例如"worker already running, pid=..."),而不是再起一个。
- 正常退出时释放锁;若锁对应的 PID 已不存在(残留锁),自动清理后再启动。

## 约束
- 只用 Python 标准库 + 已安装包,不新增需下载依赖;Windows spawn,入口 `if __name__ == "__main__"`;不改动索引与批处理主逻辑之外的行为。
- 不得删除 PaddleOCR 本地模型缓存。

## 验收标准
- 清理后进程列表中无残留 `kb_admin.worker` / supervisor。
- Ctrl+C 关闭 worker 后,`Get-CimInstance ... python.exe` 中不再有其子进程残留。
- 在已有实例运行时再次启动 worker,会被单实例锁拒绝并给出提示,不会出现两个 worker 并存。
- 重启后不再自动拉起旧的幽灵子进程。

