# 失败计数与 dead 判定规则（请按此实现）

## 两个独立计数器，分别记录两类故障
- attempts：软失败（进程还活着、异常被 try/except 捕获），如 解析报错、embedding 报错、被判超时。
- crash_count：硬失败（进程直接死），如 BrokenProcessPool、原生崩溃(0xc0000005)、OOM 被杀、重文件独立子进程非零退出/被 kill。
（若 files 表还没有 crash_count 列，请新增，默认 0。）

## 递增规则
- 捕获到的普通异常 / 超时判失败 → attempts += 1（超时归 attempts，不归 crash_count）。
- 进程池崩坏、原生崩溃、子进程被杀/非零退出 → crash_count += 1。
- 池崩坏时无法归因到单个文件的场景：把当轮在飞文件都 crash_count += 1（重文件走独立子进程后可精确归因，只 +1 到该文件）。

## dead 判定（两阈值，或逻辑，同时生效）
```
MAX_ATTEMPTS = 3     # 软失败上限
CRASH_LIMIT  = 2     # 硬崩溃上限（更低，毒丸更快隔离）
# 满足任一即转 dead：
#   attempts    >= MAX_ATTEMPTS
#   crash_count >= CRASH_LIMIT
```
- 两个计数器互不相加、互不干扰，各自独立判断。
- crash_count 阈值更低（2）：一个文件能把进程原生搞崩两次，基本可断定它有毒，不再重试；设 2 而非 1 是给一次偶发（当时内存紧张）的容错。

## 复活与重置
- 重新上传 / 复活文件（failed/dead/卡住 → 重新入队 pending）时，attempts 和 crash_count 都清零，给它全新机会。
- 成功 completed 的文件不需要重置。

## claim 过滤
- claim_pending 领取任务时，排除已 dead 的；对可重试的 failed/ocr_pending，需同时满足 attempts < MAX_ATTEMPTS 且 crash_count < CRASH_LIMIT 才领取，否则应已被判为 dead。

