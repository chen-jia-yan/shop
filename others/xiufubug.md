# 修复两个导致验证失败的路由/查询漏洞

## 现象
- file_id=73 状态 status=text_done, stage=ocr_pending，worker 一直不 claim 它，日志显示 "no pending rows"。
- file_id=66/71 是大 .xlsx，被当轻文件进了共享池，66 原生崩溃打坏池、连累 71；deferred_heavy=0，没有任何重文件子进程日志，说明重文件沙箱没对它们生效。

## Bug A：claim 漏掉第二阶段（ocr_pending）任务，必须修
- 现在 claim_pending 只按 status（pending/failed）筛，导致 stage=ocr_pending 的第二阶段任务永远不被领取。
- 修改 claim 查询：**同时领取两类任务**（在一个事务里原子领取并置为对应的处理中状态）：
  1. 第一阶段/新任务：status IN ('pending','failed') 且 attempts<MAX_ATTEMPTS 且 crash_count<CRASH_LIMIT → 领取后置 status='processing'。
  2. 第二阶段 OCR：stage='ocr_pending' 且 attempts<MAX_ATTEMPTS 且 crash_count<CRASH_LIMIT → 领取后置 stage='ocr_processing'。
- 确保回滚/重置逻辑覆盖 stage='ocr_processing' → 'ocr_pending'（和 processing→pending 一样），启动时和 pool 重建后都执行。
- 验证：73（text_done/ocr_pending）能被重新领取并完成第二阶段变 completed。

## Bug B：重文件判定必须覆盖大 Excel，否则沙箱形同虚设
- HEAVY_EXTENSIONS 目前只有 {.pdf,.ppt,.pptx}，把大 .xlsx 漏掉了，导致真正在崩的 Excel 走了共享池。
- 修改重文件判定：加入 .xlsx/.xls；并且**不要只靠后缀**——增加基于"文件大小超阈值 或 内嵌图片数超阈值"的判定，任一命中即判 heavy，走独立子进程沙箱。
- 验证：66/71 这类大 Excel 被判为 heavy，走重文件独立子进程（日志出现 heavy 子进程执行记录、deferred_heavy>0）；即使其中一个子进程崩溃，也只影响它自己，不再打坏共享池、不连累同批文件。

## 总验收
1. 73 被自动领取并完成二阶段（completed）。
2. 大 Excel 走重文件沙箱（有 heavy 子进程日志）；其崩溃不影响共享池和其他文件。
3. worker 主循环不因 pool 崩坏退出；所有中间态（processing / ocr_processing）在崩坏后都能回滚重跑。

先输出：claim 查询的新 SQL/逻辑 + 重文件判定的改动 + 回滚覆盖 ocr_processing 的 diff，确认后再实现。

