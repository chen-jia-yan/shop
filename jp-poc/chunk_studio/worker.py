## 知识库管理总调度
## 不断从SQLite领任务，分轻重两条产线，把解析+ocr——切片丢给子进程，结果落盘后分批写进索引、再把任务记成完成或失败。

from __future__ import annotations
import logging
import os
import gc
import time
import traceback

from collections import deque 
from concurrent.futures import ProcessPoolExecutor, TimeoutError, as_completed
from concurrent.futures.process import BrokenProcessPool

from pathlib import Path
from typing import Any

from kb_admin.health import memory_load_percent
# 防日志文件无限张
from kb_admin.logging_utils import configure_rotating_logger, configure_worker_log_sink
# 文件锁，清理残留进程，配置多进程启动模式，规整DB路径
from kb_admin.process_guard import (
    WORKER_LOCK_PATH,
    acquire_worker_lock,
    cleanup_active_heavy_processes,
    cleanup_orphan_spawn_processes,
    configure_multiprocessing,
    normalize_db_path,
    release_worker_lock,
)
# 重文件专属--超时常量、并发上限、超时错误构造、重文件判定、重文件子进程
from kb_admin.runtime import FILE_PROCESS_TIMEOUT_SECONDS, HEAVY_LIMIT, build_timeout_error, is_heavy_path, run_heavy_subprocess
# 任务表（SQLite）操作：领任务、标状态、回滚、重排、读控制开关、记pid
from kb_admin.state_store import (
    DEFAULT_DB_PATH,
    bump_crash_and_requeue,
    claim_pending,
    init_db,
    mark,
    read_control,
    reset_stuck,
    rollback_all_inflight_rows,
    rollback_inflight_rows,
    set_worker_pid,
)
from kb_poc.config import KBSettings
from kb_poc.parsing.ppt_ocr import build_configured_ppt_ocr

MAX_WORKERS = 4
MAX_ATTEMPTS = 3
MAX_TASKS_PER_CHILD = 200  #防内存泄露累积，又不至于太频繁换进程把预热的ocr推到重建
POLL_SECONDS = 10 
# 迟滞防抖，避免阈值附近反复启停---但是解决不了内存泄露问题，还是要靠子进程隔离。（后续要加）    
MEMORY_SOFT_LIMIT = 85  # worker 开始放缓/暂缓领新任务
MEMORY_HARD_LIMIT = 92  # worker 暂停，等待内存回落
MEMORY_RESUME_LIMIT = 80  # 恢复正常领任务
MEMORY_BACKOFF_SECONDS = 3  # 内存高时，每次等待 3 秒后再检查
DB = str(DEFAULT_DB_PATH)    # 任务表路径
INDEX_UPLOAD_BATCH_SIZE = 64  # 入索引时每批最多写 64 个 chunk---太大吃内存，太小往返次数多

#改下写法--log.info("... %s", x)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
configure_worker_log_sink("worker.log")
log = configure_rotating_logger(name="worker", file_name="worker.log")

# 每个子进程启动只初始化一次，避免反复重建 OCR 引擎。
_ocr = None  # ---确认下是否真复用了， 否则inie——worker的预热白做）

# 给每个提交出去的轻任务拍一张“快照字典”
# 作用：存file_id/path/stage/started_at，方便在 future 回调里处理结果或超时。
# 衔接： run（）里第343行给每个future建一份，之后喂给_handle_light_future_result()和_handle_light_future_timeout()，里面用context取file_id/path/stage/started_at。
def _build_future_context(row: tuple[int, str, str]) -> dict[str, Any]:
    file_id, path, stage = row
    return {
        "file_id": file_id,
        "path": path,
        "stage": stage,
        "started_at": time.perf_counter(),
    }

# 进程池每开一个进程就自动跑一个子进程初始化函数，初始化OCR引擎。
# 怎么用：作为initializer传给ProcessPoolExecutor，子进程启动时就会调用它，初始化OCR引擎。
def init_worker() -> None:
    global _ocr
    try:
        settings = KBSettings.load()
        _ocr = build_configured_ppt_ocr(
            provider=settings.local_ocr_provider,
            language=settings.local_ocr_language,
            use_angle_cls=settings.local_ocr_use_angle_cls,
            cpu_threads=settings.local_ocr_cpu_threads,
            enable_mkldnn=settings.local_ocr_enable_mkldnn,
            profile_label="light",
        )
        if _ocr is not None:
            log.info(msg="worker OCR initialized pid=%s", *(os.getpid(),))   ## 日志写法改一下
        else:
            log.info(msg="worker OCR disabled pid=%s", *(os.getpid(),))
    except Exception as exc:
        log.exception(msg="worker OCR init failed: %s", *(exc,))
        raise   # 出错后往外抛--初始化失败的子进程不该带病干活，宁可让它崩，让池重建。
    ## 代价：一次ocr初始化失败会让整池BrokenProcessPool.


# 被submit到进程池，在子进程中执行的 纯 CPU函数（解析+OCR+切片），结果落盘，避免把整份 chunk 列表回传到父进程。
#怎么用：父进程通过pool.submit(process_one,file_id,path)间接触发，不直接调。
def process_one(file_id: int, path: str) -> tuple[int, str, int]:
    global _ocr
    # 懒加载导入--减少进程启动负担、避开循环依赖。
    from kb_admin.ingestion import build_chunk_batch_path, write_chunk_batches

    try:
        file_path = Path(path)  # 把path 包成Path,文件不存在就抛FileNotFoundError（早失败）
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        settings = KBSettings.load()
        batch_path = build_chunk_batch_path(file_id)  # 算出切片落盘路径
        started_at = time.perf_counter()
        chunk_count = write_chunk_batches(  #做解析+ocr+切片写盘，返回chunk条数
            file_path,
            settings,
            include_ocr=True,
            output_path=batch_path,
            ocr_cpu_threads=settings.local_ocr_cpu_threads,
            ocr_profile_label="light",
        )
        elapsed = time.perf_counter() - started_at
        #计时打日志--只回路径不回内容---为什么：几千个chunk跨进程回传要序列化、又慢又占内存，落盘换路径最省。
        log.info(msg="file processed pid=%s file_id=%s seconds=%.2f path=%s", *(os.getpid(), file_id, elapsed, path))
        return file_id, str(batch_path), chunk_count
    except Exception as exc:
        # 把子进程里的异常尽量转换成普通 Python 异常返回给父进程，避免直接打爆整个进程池。
        raise RuntimeError(f"process_one failed for {path}: {exc}\n{traceback.format_exc()}") from exc

#批量投递+记住每张小票对应哪个文件
# submit_rows:把一批轻任务逐个pool.submit(process_one,...),返回{future:(file_id,path,stage)}映射。
# 提交时若池已坏，吞掉BrokenProcessPool返回空字典，交给 上层（run）重建
def _submit_rows(pool: ProcessPoolExecutor, rows: list[tuple[int, str, str]]) -> dict[Any, tuple[int, str, str]]:
    try:
        return {pool.submit(process_one, *(file_id, path)): (file_id, path, stage) for file_id, path, stage in rows}
    except BrokenProcessPool as exc:
        log.error(msg="worker pool broken while submitting tasks: %s", *(exc,))
        return {}

# 衔接：run（） 在启动（302）、提交失败（335）、池崩（363）三处都用它重建池。
def new_pool() -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=MAX_WORKERS,
        initializer=init_worker,
        max_tasks_per_child=MAX_TASKS_PER_CHILD,
    )

# 容错与节流

## 池崩善后--进程池（BrokenProcessPool)崩的时候的收拾函数
def _handle_broken_pool(db_path: str, futures: dict[Any, tuple[int, str, str]], exc: BrokenProcessPool) -> None:
    error = f"worker pool broken: {exc}"
    for future, (file_id, path, _stage) in futures.items():
        if future.done():
            continue
        # 把还没done的任务逐个bump_crash_and_requeue（崩溃计数+1并重排）
        bump_crash_and_requeue(db_path, file_id, error=error)
        log.error(msg="requeued file_id=%s path=%s after native crash", *(file_id, path))
    rollback_all_inflight_rows(db_path, error=error)
    # 把处理中的行整体回滚
    # 为什么：一次段错误/OOM不该让整批任务凭空小时，要么重排，要么回滚，保证不丢活。

# 全局软刹车
## 决定要不要领新任务 的内存闸
def _wait_for_memory_headroom() -> bool:
    load = memory_load_percent()
    if load < MEMORY_SOFT_LIMIT:
        return True
    gc.collect()
    log.warning(msg="memory pressure high: %s%%", *(load,))
    time.sleep(MEMORY_BACKOFF_SECONDS)
    
    if load < MEMORY_HARD_LIMIT:
        return False  #--跳过本轮--注意：这里用的是睡前的旧load（小bug，应睡醒重读）
    while True:
        load = memory_load_percent()
        if load < MEMORY_RESUME_LIMIT:
            return False
        gc.collect()
        time.sleep(MEMORY_BACKOFF_SECONDS)
        # 局限：他只让worker少领活，但管不住已在跑的进程--所以防不住单个大文件把内存顶爆（那要靠给子进程设内存硬限）

# 领任务签的三道闸， 返回（rows,throttled)
def _claim_capacity(db_path: str) -> tuple[list[tuple[int, str, str]], bool]:
    control = read_control(db_path)  #读控制表
    #若被人工paused --> 睡一会、返回([],True)
    if control["paused"]:  
        log.info("dispatcher paused by control table")
        time.sleep(POLL_SECONDS)
        return [], True
    #内存不够 --> 返回([],True)
    if not _wait_for_memory_headroom():
        return [], True
    # 算本轮上限limit=clamp （控制表max_inflight,0,MAX_WORKERS);
    # 为0 就睡着返回。  为什么：运维能动态调并发
    limit = max(0, min(MAX_WORKERS, int(control["max_inflight"])))
    if limit <= 0:
        time.sleep(POLL_SECONDS)
        return [], True
    # 真正领回一批、返回（rows，False）
    rows = claim_pending(db_path, limit, MAX_ATTEMPTS)
    return rows, False

# 分流与记账小帮手
## 分light（list）和heavy（deque）
def _split_claimed_rows(rows: list[tuple[int, str, str]]) -> tuple[list[tuple[int, str, str]], deque[tuple[int, str, str]]]:
    light_rows: list[tuple[int, str, str]] = []
    heavy_rows: deque[tuple[int, str, str]] = deque()
    for row in rows:
        if is_heavy_path(row[1]):
            heavy_rows.append(row)
        else:
            light_rows.append(row)
    return light_rows, heavy_rows

## 删掉落盘的临时切片文件（存在才删）
def _cleanup_chunk_file(chunk_file_path: str | None) -> None:
    if not chunk_file_path:
        return
    chunk_file = Path(chunk_file_path)
    if chunk_file.exists():
        chunk_file.unlink()
## 完成的任务--标记+打完成日志
def _complete_processed_row(db_path: str, file_id: int, path: str, stage: str, chunk_count: int, indexed_count: int, mode: str):
    mark(db_path, file_id, status="completed")
    log.info(msg="completed %s file_id=%s path=%s stage=%s chunks=%d indexed=%d", *(mode, file_id, path, stage, chunk_count, indexed_count))
## 失败任务--标记+打失败日志
def _fail_processed_row(db_path: str, file_id: int, path: str, error: str, *, mode: str, reason: str) -> None:
    mark(db_path, file_id, status="failed", error=error)
    log.error(msg="%s %s file_id=%s path=%s error=%s", *(reason, mode, file_id, path, error))
## 打一条结构化耗时汇总（解析秒/入库秒/总秒）
## 为什么单拎出来？轻重两条产线共用，收口到一处，避免到处重复写+日志格式统一。
def _log_stage_summary(path: str, *, mode: str, stage: str, chunk_count: int, indexed_count: int, parse_seconds: float, upsert_seconds: float, total_seconds: float):
    log.info(
        msg="file stage summary mode=%s path=%s stage=%s chunks=%d indexed=%d parse_seconds=%.2f upsert_seconds=%.2f total_seconds=%.2f",
        *(mode, path, stage, chunk_count, indexed_count, parse_seconds, upsert_seconds, total_seconds)
    )

# 两条产线的收尾处理
## 重文件全流程---从解析--入库--记账的完整处理
def _process_heavy_row(db_path: str, index_repo: Any, row: tuple[int, str, str]) -> None:
    from kb_admin.ingestion import upsert_with_retry

    file_id, path, stage = row  # 解包row
    chunk_file_path = None  # 占位（保证finally能安全引用）；打总计时
    total_started_at = time.perf_counter()
    try:
        parse_started_at = time.perf_counter()
        # run_heavy_subprocess(...)起独立子进程带超时啃大文件，返回落盘路径和条数
        chunk_file_path, chunk_count = run_heavy_subprocess(file_id, path, log=log, timeout_seconds=FILE_PROCESS_TIMEOUT_SECONDS)
        parse_elapsed = time.perf_counter() - parse_started_at
        upsert_started_at = time.perf_counter()
        ## 分批写索引，返回写入条数 -- 衔接：索引层，也是幂等的落点
        indexed_count = upsert_with_retry(index_repo, path, chunk_file_path, log=log, batch_size=INDEX_UPLOAD_BATCH_SIZE)
        #算总耗时，打阶段汇总
        upsert_elapsed = time.perf_counter() - upsert_started_at
        total_elapsed = time.perf_counter() - total_started_at
        _log_stage_summary(
            path,
            mode="heavy",
            stage=stage,
            chunk_count=chunk_count,
            indexed_count=indexed_count,
            parse_seconds=parse_elapsed,
            upsert_seconds=upsert_elapsed,
            total_seconds=total_elapsed,
        )
        #标完成
        _complete_processed_row(db_path, file_id, path, stage, chunk_count, indexed_count, mode="heavy")
    # 标失败--（这是重文件唯一的超时防线）
    except TimeoutError:
        _fail_processed_row(db_path, file_id, path, build_timeout_error(), mode="heavy", reason="timed out")
    # bump_crash_amd_requeue 重排（有MAX_ATTEMPTS)封顶
    except Exception as exc:
        bump_crash_and_requeue(db_path, file_id, error=str(exc))
        log.error(msg="crashed heavy file_id=%s path=%s error=%s", *(file_id, path, exc))
    finally:   # 无论成败都擦临时文件
        _cleanup_chunk_file(chunk_file_path)

# 轻文件收活
## 一个轻任务做完后的处理，结构和重文件版几乎对称
## 怎么用： run()第353行对每个完成的future调。
def _handle_light_future_result(db_path: str, index_repo: Any, future: Any, context: dict[str, Any]) -> None:
    from kb_admin.ingestion import upsert_with_retry
    #从快照context里取file_id/path/stage
    file_id = int(context["file_id"])
    path = str(context["path"])
    stage = str(context["stage"])
    chunk_file_path = None   # 占位 
    try:
        _, chunk_file_path, chunk_count = future.result()  # 接住process_one的返回（路径+条数）。衔接：process_one
        parse_elapsed = time.perf_counter() - float(context["started_at"])
        upsert_started_at = time.perf_counter()    #解析耗时=现在-快照里的estarted_at;再upsert,算入库耗时，总耗时。
        indexed_count = upsert_with_retry(index_repo, path, chunk_file_path, log=log, batch_size=INDEX_UPLOAD_BATCH_SIZE)
        upsert_elapsed = time.perf_counter() - upsert_started_at
        total_elapsed = parse_elapsed + upsert_elapsed
        _log_stage_summary(
            path,
            mode="light",
            stage=stage,
            chunk_count=chunk_count,
            indexed_count=indexed_count,
            parse_seconds=parse_elapsed,
            upsert_seconds=upsert_elapsed,
            total_seconds=total_elapsed,
        )
        _complete_processed_row(db_path, file_id, path, stage, chunk_count, indexed_count, mode="light")
    except Exception as exc:
        _fail_processed_row(db_path, file_id, path, str(exc), mode="light", reason="failed")
    finally:
        _cleanup_chunk_file(chunk_file_path)
# 为什么和重文件分两套？  轻的是“并行先跑，事后统一收future”，重的是“当场同步跑完”，两种时序不同，所以计时和收活逻辑分开写

#轻文件超时--把一个超时的轻任务标失败
#取context，算slapsed，mark（failed+超时错误）
## 注意：两个已知问题：
#1.future.cancel() 对已在运行的任务无效，子进程还会继续空耗；
#2.配合run（）里的收活逻辑。“1秒没全完成就判超时”的误判bug就发生在这--详见之前那份风险报告
def _handle_light_future_timeout(db_path: str, future: Any, context: dict[str, Any]) -> None:
    file_id = int(context["file_id"])
    path = str(context["path"])
    elapsed = time.perf_counter() - float(context["started_at"])
    mark(db_path, file_id, status="failed", error=build_timeout_error())
    future.cancel()
    log.error(msg="timed out light file_id=%s path=%s timeout=%ss elapsed_seconds=%.2f", *(file_id, path, FILE_PROCESS_TIMEOUT_SECONDS, elapsed))

# 主循环
#启动段:开机自检
def run(run_once: bool = False) -> None:
    db_path = normalize_db_path(DB) #规整DB路径
    configure_multiprocessing()  #配置多进程启动方式
    cleanup_orphan_spawn_processes()   #清理残留的进程
    acquire_worker_lock(WORKER_LOCK_PATH)  #抢文件锁--保证全机只有一个worker在跑，抢不到不开工。
    init_db(db_path)   # 建表
    reset_stuck(db_path)  #恢复上次遗留的processing （崩溃自愈）
    set_worker_pid(db_path, os.getpid())  #记自己的pid

    from kb_admin.services import KnowledgeAdminService
    # 拿到索引仓库index_repo（入库的目的），打启动日志
    index_repo = KnowledgeAdminService().index_repo
    log.info(msg="worker started db=%s backend=%s", *(db_path, type(index_repo).__name__))
    #建进程池
    pool = new_pool()
#为什么顺序重要：先抢锁再动数据，先复位残留再领新活，避免两个实例互相踩或重复处理。
    try:
#_claim_capacity领一批；若有上轮没轮到的deferred_heavy,先补到这批前面再清空
        deferred_heavy: deque[tuple[int, str, str]] = deque()
        while True:
            rows, throttled = _claim_capacity(db_path)
            if deferred_heavy:
                rows = list[tuple[int, str, str]](rows) + list[tuple[int, str, str]](deferred_heavy)
                deferred_heavy.clear()
# 没活时--run_once就退出；
# 若有上轮没轮到的deferred_heavy,先补到这批前面再清空；
#否则睡10秒再来      
            if not rows:
                if run_once:
                    log.info("no pending rows, exiting run_once")
                    break
                if throttled:
                    continue
                log.info(msg="no pending rows, sleeping %s seconds", *(POLL_SECONDS,))
                time.sleep(POLL_SECONDS)
                continue
#分流； light全选； heavy从队头取到HEAVY_LIMIT个为止，剩下的塞回deferred_heavy,下轮再处理
#为什么：限制重活并发，别一次放太多把内存顶爆
            light_rows, heavy_rows = _split_claimed_rows(rows)
            selected_rows = list[tuple[int, str, str]](light_rows)
            selected_heavy: list[tuple[int, str, str]] = []
            while heavy_rows and len(selected_heavy) < HEAVY_LIMIT:
                selected_heavy.append(heavy_rows.popleft())
            deferred_heavy.extend(heavy_rows)
# 打一条“这轮领了多少，轻几重几，还欠几个重”的日志
            log.info(
                msg="claimed %d row(s), selected_light=%d selected_heavy=%d deferred_heavy=%d",
                *(len(rows), len(selected_rows), len(selected_heavy), len(deferred_heavy))
            )
# 提交轻活
# 若提交失败（池坏）--回滚这批轻活，关旧池，建新池，continue；
## ⚠️注意： 这条continue会把本轮已领的selected_heavy丢掉成卡单（已知风险）
            futures = _submit_rows(pool, selected_rows)
            if selected_rows and not futures:
                rollback_inflight_rows(db_path, selected_rows, error="worker pool broken while submitting tasks")
                pool.shutdown(wait=False, cancel_futures=True)
                pool = new_pool()
                log.warning("worker pool rebuilt after submit failure")
                continue
# 同步逐个处理重活   ⚠️注意：这会阻塞下面收轻活，是已知的结构问题（拖累轻活超时计时）
            for file_id, path, stage in selected_heavy:
                _process_heavy_row(db_path, index_repo, row=(file_id, path, stage))

# 收轻活--给每个future建快照；循环用as_completed(timeout=1)取完成的去_handle_light_future_result;其余判超时。
#⚠️注意：这段“1秒没完成就判全超时：的逻辑有严重bug，慢一点的轻文件会被误杀。
            try:
                future_contexts = {future: _build_future_context(row) for future, row in futures.items()}
                pending_futures = dict[Any, tuple[int, str, str]](futures)
                while pending_futures:
                    try:
                        completed = list[Any](as_completed(list(pending_futures), timeout=1))
                    except TimeoutError:
                        completed = []

                    for future in completed:
                        pending_futures.pop(future)
                        _handle_light_future_result(db_path, index_repo, future, future_contexts[future])

                    timed_out = [future for future, context in future_contexts.items() if future in pending_futures]
                    if timed_out:
                        for future in timed_out:
                            _handle_light_future_timeout(db_path, future, future_contexts[future])
                            pending_futures.pop(future)
#except BrokenProcessPool --> _handle_broken_pool善后+重建池
#作用：优雅退出
            except BrokenProcessPool as e:
                _handle_broken_pool(db_path, futures, e)
                pool.shutdown(wait=False, cancel_futures=True)
                pool = new_pool()
                log.warning("worker pool rebuilt after broken pool exception")
#清理重文件进程  --> 清空pid  --> pool.shutdown(wait=True)等活干完 --》释放文件锁。
#⚠️注意：只有抛异常/ctrl+c 才会走到这；运维直接SIGTERM杀可能跳过finally，建议加信号处理做优雅停机 
    finally:
        cleanup_active_heavy_processes()
        set_worker_pid(db_path, pid=None)
        pool.shutdown(wait=True, cancel_futures=False)
        release_worker_lock(WORKER_LOCK_PATH)


if __name__ == "__main__":
    run(run_once=False)  #常驻模式，领空了也不退出，睡一会继续