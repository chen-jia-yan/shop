实现第 3 步：worker 进程池。请生成 kb_admin/worker.py，并在 kb_admin/state_store.py 里补齐它依赖的三个函数。只用标准库 + 已装的包，禁止新依赖。

# 1) state_store.py 需要保证这三个函数的语义（很重要，直接影响正确性）：
# - claim_pending(db, limit, max_attempts)：在一个事务里，SELECT 出 status IN('pending','failed') AND attempts<max_attempts 的前 limit 行，
#   并同时把它们 UPDATE 成 'processing'，返回 [(id, path), ...]。（原子领取，避免下一轮循环重复领同一批。）
# - mark(db, file_id, status, error=None)：更新该行 status；当 status=='failed' 时 attempts=attempts+1，
#   且当 attempts>=3 时把 status 改成 'dead'（不再被 claim_pending 领取）。更新 updated_at。
# - reset_stuck(db)：把所有 status=='processing' 的行重置回 'pending'（用于 worker 崩溃/重启后恢复在途任务）。
# enqueue_files 用 INSERT OR IGNORE(基于 file_hash UNIQUE) 实现幂等：已存在的文件不重复入队。

# 2) kb_admin/worker.py 完整代码（独立运行：python -m kb_admin.worker）：

import time, logging
from concurrent.futures import ProcessPoolExecutor, as_completed

from kb_admin.state_store import init_db, claim_pending, mark, reset_stuck
from kb_poc.parsing.ocr_provider import LocalPaddleProvider

MAX_WORKERS = 8          # 你有 10 物理核，留 2 个给系统
MAX_ATTEMPTS = 3
POLL_SECONDS = 2
DB = "ingest.db"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

# ---- 每个子进程启动时只初始化一次（关键：避免 PP-Structure/PaddleOCR 抢实例）----
_ocr = None
def init_worker():
    global _ocr
    _ocr = LocalPaddleProvider()          # 内部只 new 一次引擎
    log.info("worker OCR ready")

# ---- 子进程里跑：只做纯 CPU（解析+OCR+切片），只返回可 pickle 的 chunks ----
# 注意：参数只传 file_id 和 path（可 pickle），不要传图对象/实例（Windows spawn 要求）
def process_one(file_id, path):
    global _ocr
    from kb_admin.ingestion import build_chunks_for_path   # 你项目已有的解析入口
    chunks = build_chunks_for_path(path, ocr=_ocr)          # 内部用 _ocr 做 OCR，返回 list[dict]
    return file_id, chunks

# ---- 父进程：批量写 Azure AI Search，带 429/503 指数退避 ----
def upsert_with_retry(index_repo, chunks, tries=5):
    delay = 1.0
    for i in range(tries):
        try:
            index_repo.upsert_document_chunks(chunks)       # 批量上传，不要一条条
            return
        except Exception as e:
            if i == tries - 1:
                raise
            log.warning("Azure 写入失败，第 %d 次重试：%s", i + 1, e)
            time.sleep(delay); delay *= 2

def run(run_once=False):
    init_db(DB)
    reset_stuck(DB)                        # 恢复上次遗留的 processing
    from kb_admin.ingestion import get_index_repo
    index_repo = get_index_repo()

    with ProcessPoolExecutor(MAX_WORKERS, initializer=init_worker) as pool:
        while True:
            rows = claim_pending(DB, MAX_WORKERS, MAX_ATTEMPTS)   # 原子领取并标 processing
            if not rows:
                if run_once:
                    break                  # 跑完即退（批处理模式）
                time.sleep(POLL_SECONDS)   # 常驻模式：轮询等新任务
                continue

            futs = {pool.submit(process_one, fid, path): (fid, path)
                    for fid, path in rows}
            for f in as_completed(futs):
                fid, path = futs[f]
                try:
                    _, chunks = f.result()
                    upsert_with_retry(index_repo, chunks)  # 父进程集中写库
                    mark(DB, fid, "completed")
                    log.info("完成 %s", path)
                except Exception as e:
                    mark(DB, fid, "failed", error=str(e))  # attempts+1，满 3 次自动转 dead
                    log.error("失败 %s：%s", path, e)

if __name__ == "__main__":                 # Windows spawn 必须
    run(run_once=False)

# 3) 接入点（请对齐我项目实际函数名，不确定就先扫一遍代码再改）：
# - build_chunks_for_path(path, ocr) 若签名不同，改成用全局 _ocr 的形式；确保它内部 OCR 走传入的 ocr，而不是自己 new。
# - get_index_repo() / upsert_document_chunks() 换成我项目里实际的 Azure AI Search 写入入口。
# 先输出：state_store 三个函数的实现 + worker.py，然后停下来等我确认，不要顺带改其他文件。

