# 任务:找出并消除"仍在启动第二个系统 Python worker"的隐藏路径

## 现状(已部分修复)
之前进程树 3 层:venv worker → system worker → spawn_main。改用 sys.executable 后变 2 层:venv worker(.venv312\Scripts\python.exe)→ **system worker(Python312\python.exe),命令仍是 `-m kb_admin.worker`**。
关键判断:残留的第二个 worker 跑在**系统 Python312**,而 supervisor.py 已用 `sys.executable`(=venv),两者矛盾——说明**存在另一条用裸 `python`/写死系统 Python 路径/外部计划任务的启动路径**,尚未找到。

## 请系统性排查并修复
1. 全仓库搜索所有可能启动 Python 进程的地方(不要只看 supervisor.py):
   - 关键字:`"python"`、`python.exe`、`Python312`、`os.system`、`os.spawn`、`subprocess.Popen`、`subprocess.run`、`subprocess.call`、`shell=True`、`.bat`、`.cmd`、`start `。
   - 找出任何用裸 `"python"` 或硬编码解释器路径启动 `-m kb_admin.worker` 的代码,全部改为 `sys.executable`。
2. 检查是否存在**模块级(未被 `if __name__ == "__main__"` 保护)**的进程启动代码;Windows spawn 会在子进程重新导入主模块,任何模块级的 Popen 都会被重复触发。把所有启动逻辑移入 `if __name__ == "__main__"` 或显式入口函数。
3. 检查是否有 `.bat`/`.cmd` 脚本、Windows 计划任务、或服务在用系统 Python 启动 worker;若有,交由用户处理并在说明里列出。
4. 确认 worker 主循环内部**不再启动另一个 worker**;若需要 supervisor,只保留 supervisor→单 worker 一层,且全部用 `sys.executable`。

## 约束
- 只用标准库 + 已安装包,不新增依赖;Windows spawn;不删除 PaddleOCR 模型缓存。

## 验收标准
- 启动后进程树中只有**一个** `-m kb_admin.worker`,可执行路径为 `.venv312\Scripts\python.exe`;不再出现 `Python312\python.exe` 的 worker。
- 杀掉 worker 后无子进程被自动重新拉起;重启机器后无计划任务/服务自动拉起 worker。
- 列出排查中发现的所有 Python 启动点及其修改情况。

