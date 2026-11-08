k7
补充（与原提示词冲突时以这里为准）：
1. 关闭方式：不在 main.py 的 finally 里调用 stop()。改为在 bootstrap.py 构造 worker 的地方，
   登记 lifecycle.callback(worker.stop, timeout=35)（写法照抄 bootstrap.py 中已有的 lifecycle 登记）。
   main.py 只在 Library 评估恢复代码的后面追加 start()
2. stop() 内部最多等 30 秒（必须小于 35）
3. 心跳间隔用 settings.library_kb_heartbeat_sec；心跳超时判断用 library_kb_stale_sec
4. 抢任务：claim_job 返回 True 后，调用 get_job 重新读取任务，记下 attempts 作为 expected_attempts；
   之后所有 mark_job_* 和 heartbeat 都传 expected_attempts=这个值
5. 调用 repo 方法一律写参数名（特别是 now 和 expected_attempts 都是整数，不得按位置传）
6. 每次回写都按这个顺序，在同一个事务中：
   a. 先更新任务（commit=False）
   b. 返回 True 才更新文档（commit=False），然后 commit
   c. 任务更新返回 False：rollback，记一条 info 日志"任务已被其他实例接手"，不更新文档，不删除任何文件
7. 处理结果：
   - 成功：mark_job_succeeded → mark_document_indexed（storage_path 等取自任务）；
     commit 成功后，如果文档原来的 storage_path 不为空、且不等于任务的 storage_path，删除原来的文件；删除失败只记 warning
   - 失败且 attempts < max_attempts：mark_job_retry → mark_document_requeued
   - 失败且 attempts >= max_attempts：mark_job_failed → mark_document_failed
   - 最终失败时不删除任务的存储文件（重试要用）
8. 心跳超时回收：list_stale_jobs(older_than=now - stale_sec*1000)，对每个任务按第 7 条的规则处理，
   mark_job_retry / mark_job_failed 都传 stale_before=同一个时间值；error_code 为 "stale"，error_message 为"处理中断（心跳超时）"
9. heartbeat 返回 False：停止心跳并记 info 日志；处理结果回写时会因 attempts 不一致而自动放弃
10. 时间单位：clock 返回毫秒，所有秒数配置换算成毫秒再比较（在一个地方换算，不要到处乘 1000）
11. 补充测试：
   - 旧 worker 晚到：mark_job_succeeded 返回 False 时，文档没有被更新，没有文件被删除
   - 心跳超时回收时传入了 stale_before
   - 成功时旧版本文件被删除；新旧 storage_path 相同时不删除
   - 最终失败时任务的存储文件还在
   - 测试中阻塞用的 threading.Event 必须在 finally 中 set()，防止测试结束后线程卡住



   k6
   补充（与原提示词冲突时以这里为准）：
1. 上传接口参数写法：files: Annotated[list[UploadFile], File()]；租户字段 saas_id、workspace_id、project_id、user_id 用 Annotated[str | None, Form()] = None
2. 文件数量为 0、超过 library_kb_max_files_per_upload 时，先返回业务错误，不读取任何文件内容
3. bootstrap.py 只追加。追加完成后贴出：
   git diff src/tap_ai/bootstrap.py
   git diff src/tap_ai/bootstrap.py | Select-String "^-[^-]"（必须没有输出）
4. 测试中开关打开时，不得因为 ingest=None 让应用启动失败



k5末尾
补充（以 K4 实际的 repo 方法为准，与原提示词冲突时以这里为准）：
1. 上传：
   - 分块写入照抄 application/files.py，块大小用 STORAGE_CHUNK_SIZE_BYTES；超过大小上限时，在异步生成器内部抛出 _FileTooLarge，
     捕获后调用 storage.delete 删除已写入的部分，该文件记为 rejected "文件超过大小上限"
   - 判重前，对每个文件调用 find_by_name_key、find_by_sha，组装 by_name、by_sha 后调用 rules.classify_upload
   - "重新处理失败的文件"和"文件已更新"：调用 requeue_document_for_upload，expected_status 传判重时读到的文档状态；
     返回 False 时，该文件改为 rejected "该文件正在被其他请求上传"，并删除已存储的文件
   - 新文件：document_key 用 rules.new_document_key()，调用 add_document（storage_path 为 None，status 为 pending）
   - 每个 queued 的文件都调用 add_job，任务中记录本次的 storage_path、content_sha256、size_bytes
   - 写库的 repo 调用都传 commit=False，整批最后统一 commit
   - 允许捕获 sqlalchemy.exc.IntegrityError：先 await session.rollback()，再把涉及的文件记为 rejected "该文件正在被其他请求上传"，并删除已存储的文件
2. 重试（替换原提示词第 2 条中 retry 的说明）：
   - document_ids 先去重，保持原顺序
   - 对每个文档：用 get_recent_jobs 取最近 1 个任务；
     · 文档不存在 → ignored "文档不存在"
     · 文档 status 不是 failed → ignored "只有失败的文档可以重试"
     · 没有任务，或最近任务的 storage_path 为空 → ignored "该文档没有可重新处理的文件"
     · 否则调用 mark_document_retry；返回 False → ignored "文档状态已变化，请刷新后重试"；
       返回 True → add_job，storage_path、content_sha256、size_bytes 取自这个最近任务
   - 不得使用文档自身的 storage_path 来重试
3. 调用 repo 方法一律写参数名（例如 now=now），不按位置传参
4. 补充测试：
   - 新文件第一次处理失败后可以重试，新任务的 storage_path 等于失败任务的 storage_path
   - "文件已更新"后新版本失败，重试时新任务用的是新版本的 storage_path 和 content_sha256
   - 从索引同步来的文档（没有任务）重试 → ignored
   - 同一个 id 传两次，只处理一次
   - requeue_document_for_upload 返回 False → rejected，并且存储中的文件被删除


   关于 SDK 接进后端，安装方式想跟你对一下：

1. 版本冲突：SDK 现在要求 Pillow<11、pypdf<5，后端是 Pillow>=11.1、pypdf>=5.1，两边没有交集，装不到一起。SDK 能放宽成 Pillow>=11.1、pypdf>=5.1 吗？另外 paddleocr 能不能改成可选安装（比如 tap-ingest-sdk[ocr]），后端默认不装？
2. 安装方式：我倾向于发布到私有包仓库（比如 Azure Artifacts），后端固定版本号安装。如果暂时没有私有仓库，就先用 git 依赖，固定到某个 tag。你那边哪种方便？构建时访问私有仓库或 git 的认证由谁来配？
3. 后端 pyproject.toml 和 uv.lock 的修改，需要在能联网的环境里做，这一步由谁来做比较合适？

这几点定下来以后，我这边的插件代码一天左右就能接上。