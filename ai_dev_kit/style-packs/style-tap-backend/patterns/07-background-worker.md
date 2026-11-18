# 后台任务、批量处理与超时

核对日期：2026-11-18
核对状态：待核对（依据 library_kb_worker 与批量上传排障经验整理；首次使用前请对照来源文件核对）

## 何时使用
- 文档解析、切片、向量化、写索引、写图谱这类耗时任务。
- 批量上传、失败重试、超时处理。

## 必须
1. 任务有明确状态：`pending → processing → completed / failed`，失败次数达到上限转 `dead`；每次状态变化都用条件更新（见卡片 04）。
2. 领取任务用“条件更新抢占”：只有把 pending 成功改成 processing 的 worker 才处理它。
3. 每个任务的处理包在 try/except 里：任何异常都要 `attempts + 1` 并写入 `failed` 和简短错误原因（不含密钥），绝不能停在 processing。
4. 启动时或定时回收“processing 超过 N 分钟”的任务（改回 pending 或 failed），N 来自配置。
5. **解析前先过滤**不能处理的文件：加密/带锁文件、不支持的类型、超过大小上限的文件——直接标记为 failed（原因写清），不要送进解析器。
6. 并发数来自配置（线程/进程池大小、同时调用外部服务的 Semaphore 数量）。
7. 同一文件（按 file_hash）重复上传要幂等：已完成的返回 skipped，不产生第二份数据。
8. 超时用库自带的 timeout 参数；需要强制终止的耗时解析放进进程池，超时后取消/回收该进程任务。
9. 失败原因做分类（路径、加密、超时、数据库、索引写入、大文件），便于批量统计和定位。

## 禁止
1. 用 `threading.Thread` + `join(timeout)` 实现超时（真实事故：超时后线程仍在后台继续写数据）。
2. 捕获异常后只打日志、不改状态。
3. 在多个线程之间共享同一个数据库 Session。
4. 无限重试。
5. 先删除旧数据再写新数据且中间失败无法恢复（应先写新、确认成功再删旧，或在同一事务里完成）。

## 精简样例
```python
async def run_once(self) -> int:
    claimed = 0
    for doc in await self._repo.list_pending(limit=self._settings.library_kb_worker_batch):
        if not await self._repo.transition(doc.id, "pending", "processing"):
            continue  # 被别的 worker 抢走
        claimed += 1
        try:
            reason = precheck(doc.path, self._settings)  # 加密/类型/大小
            if reason:
                await self._repo.fail(doc.id, reason, final=True)
                continue
            chunks = await asyncio.wait_for(self._parse(doc.path), self._settings.library_kb_parse_timeout)
            await self._writer.upsert_chunks(doc.index_name, chunks)
            await self._repo.transition(doc.id, "processing", "completed")
        except Exception as exc:  # 任何失败都要落状态
            await self._repo.fail(doc.id, classify_error(exc), final=doc.attempts + 1 >= 3)
    return claimed
```
（字段名、配置名以项目实际为准；样例展示结构。）

## 反例
```python
t = threading.Thread(target=parse_and_write, args=(path,))
t.start()
t.join(timeout=60)
if t.is_alive():
    mark_failed(doc_id, "timeout")   # 错：线程还在跑，稍后会继续写索引，状态和数据不一致
```

## 检查项
- [ ] 状态变化都是条件更新
- [ ] 任何异常都会落到 failed / dead
- [ ] 有 processing 超时回收
- [ ] 解析前过滤加密/不支持/超大文件
- [ ] 并发数、超时来自配置
- [ ] 重复上传幂等
- [ ] 没有线程 + join(timeout)

## 来源
- src/tap_ai/application/library_kb_worker.py — 后台处理循环
- src/tap_ai/application/library_kb.py — 上传、重试入口
- src/tap_ai/persistence/library_kb_repo.py — 状态更新
