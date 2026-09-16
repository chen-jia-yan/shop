## yi
只做这一件事：新建 kb_admin/state_store.py，用标准库 sqlite3（禁止新依赖），开 PRAGMA journal_mode=WAL。
建表 files(id, batch_id, path, file_hash UNIQUE, status 默认 'pending', attempts 默认 0, error, updated_at) 和 batches(batch_id, file_count, status, created_at)。
提供函数：init_db()、enqueue_files(batch_id, paths)、claim_pending(limit)、mark(file_id, status, error=None)、batch_progress(batch_id)。
先输出骨架给我确认，再实现。暂时不要动其他文件。

## er
新建 kb_poc/parsing/ocr_provider.py：定义抽象基类 OCRProvider，方法 recognize(image_path: str)（只接收文件路径，不接收 PIL/ndarray）。
实现 LocalPaddleProvider：构造时只初始化一个 PaddleOCR 实例(lang='japan', use_angle_cls=False, cpu_threads=1)，全程复用；绝不在每张图/每个变体里重新 new。之前 PP-Structure 和 PaddleOCR 抢实例导致过崩溃，务必保证每个 Provider 只初始化它需要的那一个引擎。
不要改上层调用，先把这个类跑通。先出骨架我确认。

## san
新建 kb_admin/worker.py，独立脚本运行（不在 web 进程里）。
用 concurrent.futures.ProcessPoolExecutor(max_workers=8, initializer=init_worker)；init_worker 在每个子进程里建一个 LocalPaddleProvider。
主循环：claim_pending(8) 取任务 → submit(process_one, path) → as_completed 回收；成功 mark('completed')，异常 attempts+1 并 mark('failed', error)，attempts>=3 转 'dead'。
每个文件处理必须包 try/except，单文件失败绝不中断整批。处理前用 hashlib 算哈希，已 completed 的哈希跳过。worker 重启后自动只处理 pending 和 attempts<3 的 failed。
init_worker 和 process_one 必须是模块顶层函数；启动代码放在 if __name__=="__main__" 下（Windows spawn 要求）。先出骨架我确认。


## si
改 kb_poc/ui/api_admin.py 的 /api/admin/upload 和 kb_admin/services.py 的 upload_files()：收到文件→保存→算哈希→enqueue_files 写 pending→立即返回 batch_id(HTTP 202)，不在请求里做 OCR。
改状态接口 /api/admin/batches/{batch_id} 用 batch_progress() 从 SQLite 计数返回(completed/failed/pending/dead/current)。前端 modern_chat_page.js 的轮询逻辑尽量不动。

## wu
把写入 Azure AI Search 的地方改成批量上传文档(而不是一条条)，遇到 429/503 用指数退避重试若干次。不要换 SDK、不要新增依赖。

