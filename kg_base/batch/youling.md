# 任务:用探针精确定位"谁在启动第二个 -m kb_admin.worker"

## 现状
supervisor 已禁用,但进程树仍是:venv worker(24292)→ 第二个 -m kb_admin.worker(系统 Python312, 15296)→ 它的池子进程(22356)。
15296 的命令行是显式的 `-m kb_admin.worker`,不是 multiprocessing 的标准派生(标准派生是 `-c "...spawn_main..."`)。说明代码里仍有一处显式用 subprocess/os 启动了 worker 模块,但用字符串搜索没找到(模块名可能是变量拼接)。请用运行时探针定位它。

## 请这样做
1. 在 worker 的入口最开始(`if __name__ == "__main__"` 里,任何池创建/任务启动之前)插入一段**探针**,拦截并记录所有子进程启动调用的调用栈:
   - 对 `subprocess.Popen.__init__` 做包装:在调用原始实现前,用 `traceback.format_stack()` 打印完整调用栈,并打印本次启动的 `args`。
   - 同样包装 `os.system`、`os.spawnv`/`os.spawnl` 系列(若被用到)。
   - 只需日志,不改变原有行为(记录后照常执行原调用)。
2. 运行 worker 一次,复现出第二个 `-m kb_admin.worker`,在日志里找到那条启动调用对应的**完整调用栈**——它会明确指出是哪个文件、哪一行、哪个函数发起了这次启动。
3. 把该处代码贴出来并判断:
   - 若是多余的"自启动/后台 worker"逻辑 → 移除或禁用;
   - 若确有必要 → 改为使用 `sys.executable`,并保证只启动一层、且被单实例锁保护。
4. 额外确保池子进程也用 venv 解释器:在创建池之前加 `import multiprocessing as mp; mp.freeze_support(); mp.set_executable(sys.executable)`,消除子进程跑成 Python312 的问题。

## 约束
- 只用标准库;不删除 PaddleOCR 模型缓存;探针仅用于定位,定位后可保留为可开关的调试日志。

## 交付
- 贴出探针捕获到的完整调用栈,指明启动第二个 worker 的确切代码位置。
- 修复后,进程树只剩一个 venv 的 `-m kb_admin.worker` + 若干 `.venv312` 的 `spawn_main` 池子进程,无任何 Python312 进程。