# chunk_studio首次打开慢根因分析报告
分析 chunk_studio 首次打开慢的根因并给出方案。
先找到 worker 入库时解析/OCR中间产物落盘位置、格式，以及现有缓存路径。

> OCR结果看起来没有落盘缓存，是纯内存的。 ----此处存在问题

## 调研报告：chunk_studio首次打开/preview慢的原因分析
### 1. Worker入库时的中间产物
路径和格式：

|产物|路径|格式|
|---|---|---|
|Chunk批次|`data/kb_admin/jsonl/file‑{id}.jsonl`|每行一个`DocumentChunk.to_dict()`的JSON|
|OCR artifacts|`data/artifacts/ocr/{doc}.{locator}.json`|`{source_file, locator, blocks:[StructuredBlock...]}`|
|Structured artifacts|`data/artifacts/structured/`|结构化文本块|
|Semantic artifacts|`data/artifacts/semantic/`|语义标签|

**关键发现**：
worker入库时，`ParsedDocument`(包含 segments + OCR文本)只在`_build_chunks()`内部临时存在，随后被`_chunk_document()`切分成`DocumentChunk`序列写入jsonl，`ParsedDocument`本身没有落盘。

OCR artifacts里存储的是blocks列表（结构化块），但不包含完整的`ParsedSegment`，缺少`title_path/section_title/content_type/flowchart`等字段，无法直接重建`ParsedDocument`。

### 2. segment_cache能否直接从worker中间产物转换？
**不能直接转换**。原因：
1. jsonl存储的是切分完成的`DocumentChunk`，并非原始的`ParsedDocument(segments)`。从chunk反向推导segment会丢失原始文本边界信息。
2. OCR artifacts仅保存blocks，缺失`ParsedSegment`的`title_path`、`flowchart`、`content_type`、`evidence_level`等字段。

这代表当前`segment_cache`缓存是唯一的`ParsedDocument`持久化副本，仅由chunk_studio自行生成。
但是存在优化路径：如果后续让worker在解析完成时顺带输出一份`.segments.json`，chunk_studio首次打开就可以直接读取缓存，完全跳过OCR，这就是**方案B**的核心思路。

### 3. 首次preview耗时卡点
调用链路：
`preview_file_detail → get_file_detail(读jsonl) + _load_or_create_snapshot(解析+OCR) + _chunk_document(切片×2)`

耗时拆解（以Excel/PPT为例）：

|步骤|首次(无缓存)|二次(有缓存)|说明|
|---|---|---|---|
|① get_file_detail — 读取jsonl|≈0.1s|≈0.1s|读取几十行jsonl，速度很快|
|② _load_or_create_snapshot — OCR引擎初始化|≈3‑10s|0s|PaddleOCR首次加载模型进程，缓存后无需初始化|
|③ _load_or_create_snapshot — 解析+OCR|≈5‑60s|0s|耗时取决于文件大小与图片数量|
|④ _chunk_document ×2|≈0.5‑3s|≈0.5‑3s|baseline + preview各切片一次|
|**合计**|**≈10‑70s**|**≈1‑5s**|‑|

**核心卡点：步骤②+③**。OCR引擎初始化 + 逐张图片执行OCR。该逻辑在HTTP请求内同步执行，造成浏览器长时间转圈等待。

### 4. 提速方案
#### 方案A：后台异步解析 + 前端轮询（推荐，风险最低）
**思路**：首次preview缓存未命中时，先返回`{"status": "parsing", "progress": "..."}`，后台执行异步解析+OCR，前端轮询接口直到任务完成。

**改动文件**
- `kb_chunk_studio/api.py`：`/preview`接口增加分支，缓存未命中时不阻塞，返回parsing状态
- `kb_chunk_studio/service.py`：新增`start_parse_task()` / `get_parse_status()`函数，采用线程或简易状态文件实现
- 前端（不在代码仓库）：增加轮询逻辑

**风险**：低。不改动解析/OCR/切片核心逻辑，外层封装异步逻辑；接口返回结构仅新增status字段。
**影响**：需要前端配合改造；用户体验从白屏长时间等待变为展示进度条。

#### 方案B：Worker入库时顺带写入segment缓存（最彻底，改动稍大）
**思路**：在`ingestion.py`的`_build_chunks()`或`write_chunk_batches()`中，解析拿到`ParsedDocument`之后，调用`segment_cache.save_document_snapshot()`导出一份`.segments.json`。worker处理过的文件，chunk_studio打开直接命中缓存，跳过OCR引擎初始化。

**改动文件**
- `kb_admin/ingestion.py`：在`_build_chunks()`解析完成后调用`save_document_snapshot(settings, parsed)`
- `segment_cache.py`：无需修改，已有save/load能力

**前提**：`ParsedDocument`对象在`_build_chunks()`执行期间保持有效。当前Excel/PPT解析后直接传入`_chunk_document()`，`ParsedDocument`为局部变量，只需要在调用`_chunk_document`前执行保存即可；确认`settings`可在该函数内访问（现有代码已具备settings参数）。

**风险**：低。仅增加JSON文件写入操作（毫秒级），不干扰核心业务逻辑。
**影响**：接口、chunk_studio均零改动；代价为worker入库阶段额外生成一份KB~几十KB的JSON文件。

### 最终建议
**方案A+B组合**：方案B解决**worker已处理文件实现秒开**；方案A兜底，保障**未经过worker处理的文件不会卡死浏览器**。
如果仅可选择其一，优先选择**方案B**，无需改动接口与前端，收益最直观。

