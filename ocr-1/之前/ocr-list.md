# OCR 部分改动清单

## 一、现状与问题(基于代码梳理)
OCR 仅用于文档入库/解析阶段,检索(retrieval)不使用。当前实现有四个问题,既拖慢又易混乱:

1. **worker 每文件新建 OCR、不复用**
   `kb_admin/ingestion.py::build_chunks_for_stage()` 每处理一个文件都调用一次 `build_ppt_ocr()` 新建 OCR 包装器 → 每个文件重新加载模型 → 严重拖慢。
   (对比:`kb_poc/ingestion/ingestor.py::ingest_directory()` 单进程模式用 `shared_ocr` 复用,速度正常。)

2. **两套 OCR 并存,其一形同虚设**
   - 真正用于解析:`kb_poc/parsing/ppt_ocr.py` 的 `build_ppt_ocr()` → `PaddleOCRLocal` → `_create_paddleocr()`。
   - 仅用于 worker 预热、未真正参与解析:`kb_poc/parsing/ocr_provider.py` 的 `LocalPaddleProvider`(`kb_admin/worker.py::init_worker()`、`kb_admin/process_one_file.py::main()` 中初始化)。
   预热的 provider 与解析实际使用的对象是两套独立实例,造成浪费与困惑。

3. **多处配置未真正生效**
   - `enable_mkldnn`:两套初始化均未传给底层 PaddleOCR(仅在 `kb_poc/cli.py` 打印,无实际作用)。
   - `local_ocr_language`:主解析链 `PaddleOCRLocal` 未读取该配置,硬编码为 `japan`。
   - `cpu_threads`:仅 `ocr_provider.py` 生效,主解析链未传。
   配置项存在于 `kb_poc/config.py::KBSettings`,但改动大多不影响真正解析。

4. **参数两套不一致**
   `use_angle_cls`:主解析链写死 `True`;`LocalPaddleProvider` 默认 `False`。

## 二、改动目标
统一为单一 OCR 创建路径 + 每进程只创建一次并复用 + 配置项真实贯通,以显著提速并消除双实例混乱。

## 三、具体改动
1. **统一创建入口**:保留一个 OCR 创建函数(以真正用于解析的 `ppt_ocr.py` 为准),ingest、worker、重文件子进程统一走它;移除或归并 `ocr_provider.py::LocalPaddleProvider`(若保留预热,则让"预热"创建的就是后续复用的同一实例)。

2. **每进程复用(提速核心)**:
   - worker:在进程池 `initializer`(`init_worker`)中创建一个 OCR 实例并存为进程内模块级全局;`process_one` / `build_chunks_for_stage` 复用该实例,不再每文件 `build_ppt_ocr()`。
   - Windows 为 spawn 模式:OCR 实例不可 pickle、不能跨进程传递,必须在每个子进程内创建一次(initializer 或懒加载 + 全局缓存)。
   - 重文件子进程 `process_one_file.py`:每子进程处理单文件,创建一次即可,确认不重复创建。
   - ingest 单进程:维持现有 `shared_ocr` 复用。

3. **配置贯通**:`enable_mkldnn`、`cpu_threads`、`use_angle_cls`、`local_ocr_language` 从 `KBSettings` 单一来源读取并真正传入唯一的创建函数;当前 PaddleOCR 版本不支持的参数不传(如已移除的 `show_log`);无法生效的配置项从 config 移除,避免误导。

4. **参数统一**:全局使用同一套 OCR 参数,消除主链/provider 不一致。

## 四、需保持不变
- 解析正确性(日文识别正常)。
- 重文件独立子进程隔离;子进程解释器使用 `sys.executable`(.venv312)。
- 失败重试 / 崩溃计数 / 断点续跑 / 按文件哈希的幂等增量 / embedding 限速与批量。
- 仅用标准库 + 已安装包;不删除 PaddleOCR 本地模型缓存;Windows spawn,入口置于 `if __name__ == "__main__"` 下。

## 五、验收标准
- 加诊断日志:每次真正创建 OCR 实例打印 `OCR engine created pid=... count=N`;跑一批文件后,创建次数 ≈ 进程数(不随文件数增长)。
- 单文件处理耗时明显下降,接近 ingest 单进程水平。
- 代码中仅存一条 OCR 创建路径;`config` 中 mkldnn/线程/语言等改动能真实影响 OCR 行为。
- 重文件隔离、重试、续跑、解析正确性均不回退。

## 六、实施顺序建议
建议在"两阶段合并为单趟处理"的改造完成并验证后再做本项(两者都涉及 `kb_admin/worker.py`,分步实施避免冲突)。