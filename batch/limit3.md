# 任务:修复批处理"每个文件重装 OCR 模型"导致的严重降速

## 现象与根因
本地批处理系统(kb_admin/worker.py:ProcessPoolExecutor + process_one + 两阶段 text/full + 重文件隔离)。同样的文件,原始 `python -m kb_poc ingest`(单进程、循环处理)每个文件近乎秒过;新批处理系统在并发=1、batch=64 下,每个文件要 3-4 分钟。日志里 `worker OCR ready` 几乎每个文件出现一次。

判断:OCR 引擎(LocalPaddleProvider / PaddleOCR)被**反复重新初始化**(模型加载要几十秒),而不是每个 worker 只装一次复用。诱因包括:进程池 worker 频繁重建、超时后整池重建把热引擎丢弃、两阶段可能各自初始化引擎。这是导致降速的主因,不是配额或 embedding。

## 硬性约束
- 只用 Python 标准库 + 已安装包,不新增需下载依赖;不改动/不删除 PaddleOCR 本地模型缓存;Windows spawn,入口 `if __name__ == "__main__"`;索引仍用 Azure AI Search。

## 要实现的改造

### 1. OCR 引擎每个 worker 只初始化一次并复用(最关键)
- 在进程池 `initializer`(init_worker)里创建**一个** LocalPaddleProvider 实例,存为 worker 进程内的模块级/全局单例。
- `process_one()` 处理每个文件时**复用这个已存在的实例**,严禁在 process_one 内部或每个文件、每个任务里新建 OCR 引擎。
- 明确:一个 worker 进程的生命周期内,OCR 模型只加载一次。

### 2. 文本阶段不加载 OCR 引擎
- phase='text'(include_ocr=False)时,完全不初始化、不触碰 OCR 引擎;只有 phase='full'(OCR 阶段)才使用已初始化的引擎。避免为不需要 OCR 的阶段付模型加载成本。

### 3. 别让池churn丢弃热引擎
- 调大 `max_tasks_per_child`(比如从很小的值提到 200 或更高,或设为 None 长期复用),减少 worker 重建频率——每次重建都会重装模型。
- 超时处理:重文件走独立可杀子进程(subprocess.Popen + kill)时,**只杀那个子进程**,不要整锅重建承载 OCR 热引擎的共享池。仅在真正的 BrokenProcessPool 时才重建池。
- 目标:恢复性场景(超时、单文件失败)不应导致 OCR 引擎被反复丢弃重装。

### 4. 加诊断日志,用来验证
- 每次真正初始化 OCR 引擎时,打印一条明确日志,如 `INFO OCR engine initialized pid=... count=N`(N 为该进程累计初始化次数,正常应恒为 1)。
- 每个文件处理打印耗时分解:`file_id=.. ocr_init_ms=.. parse_ms=.. embed_ms=.. total_ms=..`,方便定位时间花在哪。

### 5.(次要)解析与 embedding 解耦
- 在不破坏上面改动的前提下,让 embedding 通过异步/队列进行,避免 embedding 的等待阻塞解析。此项优先级低于 1-4。

## 验收标准
- 一整批文件跑下来,"OCR engine initialized" 出现次数 ≈ worker 数量,**不再随文件数增长**(不是每个文件一次)。
- 单个纯文本文件恢复到秒级;含图文件的耗时主要花在真实 OCR/embedding,而非 `ocr_init_ms`。
- 超时或单文件失败时,共享热池不被整体重建;OCR 引擎不被反复重装。
- 日志的 `ocr_init_ms` 在同一 worker 的第 2 个文件起应接近 0。

