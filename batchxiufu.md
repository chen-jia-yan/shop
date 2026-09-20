# 任务：重文件隔离沙箱 + 进程池崩坏后的闭环回滚

## 背景（基于现有实现）
worker.py 用 ProcessPoolExecutor(MAX_WORKERS=4) 处理任务；两阶段状态机：pending/processing/text_done/ocr_pending/ocr_processing/completed/failed/dead；claim_pending 从 pending/failed/ocr_pending 取任务；HEAVY_EXTENSIONS={.pdf,.ppt,.pptx} 且 >15MB 算 heavy，当前 HEAVY_LIMIT=1 但只是"每轮最多选 1 个 heavy"，heavy 仍在共享池里跑；process_one 在子进程构建 chunk、分批 embedding、写临时 JSONL，父进程用 begin/append/finalize 流式写索引。

问题：重文件在 OCR/full 阶段仍会让子进程原生崩溃 → 打坏整个共享 ProcessPoolExecutor → 连累同批文件卡在中间态（如 73 停在 ocr_pending 不推进），或被误标 dead（如 66）。

## 目标
把重文件的处理从共享池里剥离，放进"每次只处理一个文件的独立一次性子进程"，让重文件崩溃只影响它自己、绝不波及共享池；并把池崩坏后的状态回滚补成闭环，任何文件都不会卡在中间态。

## 硬约束
- 只用标准库 + 现有依赖，禁止新增 pip 包；Windows；先输出计划和 diff，我确认后再实现。
- 不改两阶段状态机的语义；轻文件仍走现有共享池路径，不动。

## 改动 1：重文件独立子进程沙箱
- 新增可独立运行的入口，如 kb_admin/process_one_file.py：
  `python -m kb_admin.process_one_file --id <fid> --path <path> --phase <text|full> --out <jsonl路径>`
  它只处理这一个文件：初始化自己的 OCR 引擎 → 构建该 phase 的 chunk → 分批 embedding → 写 JSONL → 通过 stdout 打印一行 JSON 结果（next_phase、chunk_count）→ 正常退出码 0；失败非 0。
- worker 的调度改造：
  - 轻文件：维持现状，走共享 ProcessPoolExecutor。
  - 重文件（HEAVY_EXTENSIONS 或 >15MB）：**不提交到共享池**，改用 subprocess.Popen 启动上面的独立子进程处理，一次只跑一个重文件（真正的单文件串行沙箱）。
  - 父进程监控该子进程：
    - 设超时 TASK_TIMEOUT_SECONDS；超时用 Popen.kill() **直接终止**（独立子进程可干净杀掉），标 failed(error='timeout')、crash_count+1。
    - 退出码 0：读 JSONL → 现有 begin/append/finalize 流式写索引 → 按 next_phase mark 成 text_done/ocr_pending 或 completed。
    - 退出码非 0 / 被系统杀 / 无结果：标 failed、crash_count+1；crash_count>=阈值→dead。
  - 关键效果：重文件子进程无论怎么崩，都**只影响它自己**，共享池（只剩轻文件）完全不受影响。
- 重文件沙箱与轻文件共享池可并行，但都要遵守现有内存背压（control 表 paused/max_inflight）；重文件并发恒为 1。

## 改动 2：进程池崩坏后的闭环回滚（补全恢复）
- reset_stuck / 恢复逻辑要覆盖**所有中间态**：processing → pending；ocr_processing → ocr_pending；并 crash_count+1，超阈值→dead。启动时和 pool 重建后都执行。
- _submit_rows 不要在 pool.submit 抛 BrokenProcessPool 时 raise 中断主循环；改为：把受影响的 selected_rows 温和回滚（processing→pending / ocr_processing→ocr_pending，crash_count+1），重建 pool，继续下一轮，不让主循环异常退出。
- _handle_broken_pool 除了处理 pending_futures 里的任务，还要扫一遍 DB 里所有仍停在 processing/ocr_processing 的行做同样回滚，确保像 73 这种不会卡在 ocr_pending/中间态无人推进。
- 验证 claim_pending 会重新领取回滚后的 pending 和 ocr_pending，使 73 能自动继续二阶段。

## 验收标准（请给出验证步骤）
1. 重文件（如 66）处理时即使子进程崩溃：只有 66 被标 failed/dead，**共享池和其他文件不受影响**，73 能继续推进到 completed。
2. 重文件卡死超过 TASK_TIMEOUT_SECONDS：被 Popen.kill() 干净终止并标 timeout，不再僵住。
3. 人为杀掉共享池的一个 worker（模拟池崩）：所有 processing/ocr_processing 的文件被回滚成 pending/ocr_pending 并最终跑完，无一卡在中间态。
4. 全程 worker 主循环不因 BrokenProcessPool 异常退出，能自愈继续。

先输出：改动文件清单 + 关键 diff（process_one_file.py 入口、worker 里重文件走 Popen 沙箱的调度、超时 kill、闭环回滚 reset，覆盖 ocr_processing），确认后再实现。

