## 1
import sqlite3
print(sqlite3.connect("ingest.db").execute(
    "select status, count(*) from files group by status").fetchall())


## 2
## 修复重新上传无法入队的问题。请把 kb_admin/state_store.py 的 enqueue_files 改成"复活"语义，不要再用 INSERT OR IGNORE 静默忽略：

def enqueue_files(db, batch_id, files):   # files = [(path, file_hash), ...]
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL;")
    for path, h in files:
        row = con.execute("SELECT id, status FROM files WHERE file_hash=?", (h,)).fetchone()
        if row is None:
            # 新文件：插入 pending
            con.execute(
                "INSERT INTO files(batch_id, path, file_hash, status, attempts) "
                "VALUES(?,?,?, 'pending', 0)", (batch_id, path, h))
        else:
            fid, status = row
            if status in ('failed', 'dead', 'processing'):
                # 之前失败/死信/卡住的：复活为 pending，清零重试次数和错误
                con.execute(
                    "UPDATE files SET status='pending', attempts=0, error=NULL, "
                    "batch_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (batch_id, fid))
            elif status == 'completed':
                pass   # 已成功入库，默认跳过（幂等）
            # pending / 已在队列中的：不动
    con.commit(); con.close()

## 注意：不要改 file_hash 的 UNIQUE 约束（幂等还靠它），只改这里的处理逻辑。

##3
#在 kb_admin/state_store.py 增加一个函数，并在 kb_poc/ui/api_admin.py 暴露一个接口 /api/admin/retry：

def retry_failed(db, batch_id=None):
    con = sqlite3.connect(db)
    if batch_id:
        con.execute("UPDATE files SET status='pending', attempts=0, error=NULL, "
                    "updated_at=CURRENT_TIMESTAMP "
                    "WHERE status IN('failed','dead') AND batch_id=?", (batch_id,))
    else:
        con.execute("UPDATE files SET status='pending', attempts=0, error=NULL, "
                    "updated_at=CURRENT_TIMESTAMP WHERE status IN('failed','dead')")
    n = con.total_changes
    con.commit(); con.close()
    return n   # 返回重新入队了几个

#前端 modern_chat_page.js 在有 failed/dead 时显示一个"重试失败文件"按钮，调这个接口。



##4
#改 batch_progress()（和 /api/admin/batches/{batch_id}）：返回 completed / processing / pending / failed / dead 五种状态的计数，外加一个失败清单 [{path, status, attempts, error}]（status 为 failed 或 dead 的行）。
#前端 modern_chat_page.js 把这五个数都显示出来，并把失败清单连同 error 一起展示，让用户清楚知道哪些没成功、为什么、以及能点"重试"。
