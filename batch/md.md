# Worker调度问题验证记录
## 现象概述
这次验证没有达到预期，新逻辑已经落地，但实际运行worker之后，`file_id=73`没有被继续领起，仍然停留在 `text_done / ocr_pending`；说明至少一条核心验收没有通过。

> 启动命令：`python -m kb_admin.worker`

### file_id=73 当前数据库状态
- `status = text_done`
- `stage = ocr_pending`
- `attempts = 1`
- `crash_count = 0`

现象：worker进程正常在跑，但是73这条记录的状态、时间戳、错误信息完全没有变化，worker没有claim这条任务。
> 排除旧问题：不是“重文件把共享池打崩”，而是 **claim / 调度链路存在漏洞，导致 ocr_pending 任务没有真正进入执行**

worker日志路径：
```
C:\Users\234393\Desktop\jap‑cycle‑poc\logs\worker.log
```

---

## worker.log 日志片段
```log
2026-09-20 14:55:13,048 INFO worker started db=C:\Users\234393\Desktop\jap-cycle-poc\ingest.db backend=LocalDocumentIndexRepository
2026-09-20 14:55:13,066 INFO claimed 2 row(s), selected=2 deferred_heavy=0
2026-09-20 14:55:13,300 ERROR failed file_id=66
path=C:\Users\234393\Desktop\jap-cycle-poc\sample_docs\業務設計要約(MR2023Rev2)_SalesTool_設計書_1.3.xlsx error=A process in the process pool was terminated abruptly while the future was running or pending.
2026-09-20 14:55:13,326 ERROR failed file_id=71
path=C:\Users\234393\Desktop\jap-cycle-poc\sample_docs\業務設計要約(MR2023Rev2)_SalesTool_申込書_1.1.xlsx error=A process in the process pool was terminated abruptly while the future was running or pending.
2026-09-20 14:55:13,353 INFO claimed 2 row(s), selected=2 deferred_heavy=0
2026-09-20 14:55:13,376 ERROR failed file_id=66
path=C:\Users\234393\Desktop\jap-cycle-poc\sample_docs\業務設計要約(MR2023Rev2)_SalesTool_設計書_1.3.xlsx error=worker pool broken while submitting tasks: A child process terminated abruptly, the process pool is not usable anymore
2026-09-20 14:55:13,400 ERROR failed file_id=71
path=C:\Users\234393\Desktop\jap-cycle-poc\sample_docs\業務設計要約(MR2023Rev2)_SalesTool_申込書_1.1.xlsx error=worker pool broken while submitting tasks: A child process terminated abruptly, the process pool is not usable anymore

2026-09-20 15:03:17,029 INFO worker started db=C:\Users\234393\Desktop\jap-cycle-poc\ingest.db backend=LocalDocumentIndexRepository
2026-09-20 15:03:17,048 INFO claimed 1 row(s), selected=1 deferred_heavy=0
2026-09-20 15:03:24,637 INFO worker OCR ready
2026-09-20 15:04:17,943 INFO completed file_id=71
path=C:\Users\234393\Desktop\jap-cycle-poc\sample_docs\業務設計要約(MR2023Rev2)_SalesTool_申込書_1.1.xlsx chunks=82 indexed=82
2026-09-20 15:45:09,275 INFO no pending rows, sleeping 10 seconds
```

> 报错关键点：
> 1. `A process in the process pool was terminated abruptly` 子进程突然终止
> 2. `worker pool broken while submitting tasks ... the process pool is not usable anymore` 进程池彻底损坏，无法继续提交任务

---

## 当前判断
1. “重文件独立沙箱 + pool 崩坏不直接炸主循环” 代码已经落地，但本次验证**不能证明该特性达标**。
2. 直接失败点：**file_id=73 没有被重新 claim**，验收点「73 能自动继续二阶段」未通过。
3. 日志**没有出现新实现的 heavy subsuccess 执行日志**，说明本次运行中新路径根本没有命中73这条任务。
4. worker进程已经停掉，现场环境保留，日志可复看。

### 待排查方向
- `ocr_pending / text_done` 状态的任务，claim筛选逻辑是否漏掉该记录；
- process pool崩溃后，任务状态流转、重试、deferred_heavy筛选分支是否生效；
- heavy任务子路径是否真正被走到。



