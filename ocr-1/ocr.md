# PaddleOCR 初始化与配置梳理报告
## 总述
本项目存在**两套PaddleOCR初始化入口**：
1. 主解析链：`kb_poc/parsing/ppt_ocr.py`，用于PPT/Excel图片OCR解析；
2. worker预热链：`kb_poc/parsing/ocr_provider.py` 的 `LocalPaddleProvider`，主要用于worker子进程预热、单图识别接口。

两套读取同一套`KBSettings`配置源，但**不是同一个实例、实参传递不完全一致**。
> 检索（retrieval）流程**不使用OCR**，OCR仅发生在文档入库/解析阶段。

---

## 1.全部OCR初始化/配置点清单
| 文件 | 函数/类 | 作用 | 读到/传入的参数 | 备注 |
|---|---|---|---|---|
| `kb_poc/config.py` | `KBSettings`字段 | OCR全局配置源头 | `local_ocr_provider`、`local_ocr_language`、`local_ocr_enable_binarized`、`local_ocr_fallback_confidence`、`local_ocr_cpu_threads`、`local_ocr_enable_mkldnn`、`local_ocr_use_angle_cls` | 全项目OCR配置来源，从环境变量加载 |
| `kb_poc/config.py` | `KBSettings.load()` | 加载环境变量OCR配置 | `KB_LOCAL_OCR_PROVIDER`、`KB_LOCAL_OCR_LANGUAGE`、`KB_LOCAL_OCR_ENABLE_BINARIZED`、`KB_LOCAL_OCR_FALLBACK_CONFIDENCE`、`KB_LOCAL_OCR_CPU_THREADS`、`KB_LOCAL_OCR_ENABLE_MKLDNN`、`KB_LOCAL_OCR_USE_ANGLE_CLS` | 配置写入settings，但不是全部字段都会被后续代码实际使用 |
| `kb_poc/cli.py` | `main()` | ingest执行时打印OCR配置 | `provider`、`mkldnn`、`angle_cls`、`cpu_threads` | 仅打印，**不会初始化OCR引擎** |
| `kb_poc/parsing/ppt_ocr.py` | `build_ppt_ocr(local_ocr_provider)` | 主解析链OCR工厂函数 | `local_ocr_provider`，仅用来判断是否创建PaddleOCR | **没有传入`language/cpu_threads/mkldnn`** |
| `kb_poc/parsing/ppt_ocr.py` | `PaddleOCRLocal` | 主解析链OCR包装类 | 类字段硬编码默认 `language='japan'` | ⚠️ 不会读取settings中的`local_ocr_language`，写死默认值 |
| `kb_poc/parsing/ppt_ocr.py` | `PaddleOCRLocal._get_paddle_ocr()` | 懒加载底层PaddleOCR实例 | 调用`_create_paddleocr(lang=self.language)` | 同一个`PaddleOCRLocal`实例内部只会构建一次底层引擎 |
| `kb_poc/parsing/ppt_ocr.py` | `_create_paddleocr(lang)` | **主链真正PaddleOCR初始化点** | 仅传递`lang`；如果构造签名支持，则额外传`use_angle_cls=True` | ❌ 不传递`cpu_threads`、`enable_mkldnn` |
| `kb_poc/parsing/ocr_provider.py` | `LocalPaddleProvider.__init__()` | worker预热OCR provider初始化入口 | 默认形参：`lang='japan'`，`use_angle_cls=False`，`cpu_threads=1` | worker预热会使用这套 |
| `kb_poc/parsing/ocr_provider.py` | `LocalPaddleProvider._build_ocr()` | provider链真正PaddleOCR初始化 | 签名支持时传入`lang`、`use_angle_cls`；签名支持且非空时传入`cpu_threads` | ❌ 不传递`enable_mkldnn` |
| `kb_admin/process_one_file.py` | `main()` | 重文件独立子进程启动预热 | `LocalPaddleProvider()`，无自定义入参 | 使用类内部默认参数 |
| `kb_poc/ingestion/ingestor.py` | `ingest_directory()` | 全量ingest构建共享OCR引擎 | `build_ppt_ocr(settings.local_ocr_provider)` | 多文件复用同一个`shared_ocr`对象 |
| `kb_admin/ingestion.py` | `build_chunks_for_stage()` | worker单文件阶段处理 | `build_ppt_ocr(settings.local_ocr_provider)` | 每处理单个文件，可能新建一套OCR包装器 |
| `kb_poc/parsing/pptx_parser.py` | `parse_pptx_file()` | PPT解析OCR入口 | `ocr_engine` 或者内部调用`build_ppt_ocr(settings.local_ocr_provider)` | PPT解析真正调用OCR的入口 |
| `kb_poc/parsing/excel_parser.py` | `parse_excel_file()` | Excel解析OCR入口 | `ocr_engine` 或者内部调用`build_ppt_ocr(settings.local_ocr_provider)` | Excel解析真正调用OCR的入口 |
| `kb_admin/worker.py` | `init_worker()` | worker子进程池预热 | `LocalPaddleProvider()` | 每个worker子进程启动执行一次预热provider |

## 2.真正传给PaddleOCR(...)的参数清单
| 文件 | 函数 | 最终传给PaddleOCR(...)的参数 |
|---|---|---|
| `kb_poc/parsing/ppt_ocr.py` | `_create_paddleocr(lang)` | `lang`；如果PaddleOCR构造签名支持，额外传 `use_angle_cls=True` |
| `kb_poc/parsing/ocr_provider.py` | `LocalPaddleProvider._build_ocr()` | `lang`；签名支持时传`use_angle_cls=self.use_angle_cls`；签名支持且`cpu_threads`非空，传`cpu_threads=self.cpu_threads` |

## 3.配置项现状排查表（配置存在，但不一定真正生效）
| 参数 | 配置里是否存在 | 主解析链 ppt_ocr.py 是否使用 | ocr_provider.py 是否使用 | 现状判断 |
|---|---|---|---|---|
| `lang` | 有 | 使用，但硬编码写死`PaddleOCRLocal.language='japan'`默认值 | 使用，默认`japan` | 配置存在，但**主链没有读取settings.local_ocr_language**，硬编码默认日语 |
| `use_angle_cls` | 有 | 使用，写死为`True`（签名支持的情况下） | 使用，默认`False` | 两套实现逻辑不一致 |
| `cpu_threads` | 有 | 未使用 | 使用（签名支持时） | **仅在ocr_provider.py生效，主解析链完全没传** |
| `enable_mkldnn` | 有 | 未使用 | 未使用 | 仅配置/日志项，两套初始化均没有传给底层PaddleOCR |
| `enable_binarized` | 有 | 没有直接作为初始化参数 | 未使用 | 属于预留配置，当前链路没有控制OCR初始化 |
| `fallback_confidence` | 有 | 没有用于OCR初始化 | 未使用 | 配置存在，但不属于PaddleOCR初始化参数 |

> 一句话总结：**配置名义是同一套，两套代码实际落地传入的字段不完全一样**。

## 4.ingest / retrieval / 批处理多进程，分别哪里调用OCR
### A. ingest（入库流程）
> ✅ 使用OCR
- 入口：`kb_poc/cli.py → main() → ingest_directory(...)`
- 创建共享OCR：`kb_poc/ingestion/ingestor.py → ingest_directory()`
```python
shared_ocr = build_ppt_ocr(settings.local_ocr_provider)
```
- 将`shared_ocr`向下传递给解析函数：
    - `parse_pptx_file(path, settings=settings, ocr_engine=shared_ocr)`
    - `parse_excel_file(path, settings=settings, ocr_engine=shared_ocr)`

> 结论：全量ingest单进程模式，**同一个进程内多个文件复用同一个shared_ocr引擎实例**。

### B. retrieval（检索流程）
> ❌ **完全不用OCR**
检索链路文件：`kb_poc/qa/answerer.py`、`kb_poc/retrieval/retriever.py`；
处理对象是已经入库完成的chunk、embedding，不会重新识别图片，和OCR初始化无关。

### C.批处理多进程 worker
> ✅ 使用OCR，行为和全量ingest不一样
1. worker单文件业务逻辑：`kb_admin/ingestion.py → build_chunks_for_stage(...)`
当`include_ocr=True`：
```python
ocr_engine = build_ppt_ocr(settings.local_ocr_provider)
```
再把`ocr_engine`传给`parse_pptx_file(...)` / `parse_excel_file(...)`。

2. worker进程预热（备用provider，**不是PPT/Excel解析真正在用的对象**）
- `kb_admin/worker.py → init_worker() → LocalPaddleProvider()`
- `kb_admin/process_one_file.py → main() → LocalPaddleProvider()`

> ⚠️区分：
> - PPT/Excel解析真正使用：`build_ppt_ocr()`产出的`PaddleOCRLocal / CompositeOCR`；
> - `LocalPaddleProvider()`：worker预热/备用provider对象，**不是主解析链路往下传递的OCR实例**。

## 5.两套OCR：是否同一套配置、同一个实例？
### 配置来源
| 项目 | 结论 |
|---|---|
| 配置来源 | 均来自`KBSettings` / 环境变量 |
| provider开关 | 两套都读取`local_ocr_provider` |
| language | settings有配置，**主链ppt_ocr没有读取该配置**，硬编码默认`japan` |
| use_angle_cls | 逻辑不一致；ppt_ocr支持就开启；ocr_provider默认关闭 |
| cpu_threads | 只在`ocr_provider.py`生效 |
| mkldnn | settings有配置，两套初始化均没有传递到底层PaddleOCR |

### 是否同一个实例
**不是同一个实例**
1. 全量ingest单进程：同一个进程内复用同一个`shared_ocr`；
2. worker多进程：**每个子进程持有独立OCR对象，进程之间不能共享实例**；
3. worker预热生成的`LocalPaddleProvider()` 和业务解析`build_ppt_ocr()`返回的OCR，是两套完全独立对象。

## 6.多进程OCR实例分配逻辑
1. 是否进程池共用一套OCR？
> ❌不是。**每个子进程拥有自己独立OCR实例**。Python多进程内存隔离，PaddleOCR模型实例无法跨子进程共享。

2. 是否每个文件都初始化一次？
- **全量ingest单进程**：否。`ingest_directory()`提前构建`shared_ocr`，多个文件复用同一个OCR包装对象；同一个对象内部多张图片复用底层PaddleOCR实例。
- **worker单文件模式**：`build_chunks_for_stage()`每处理一个文件，调用一次`build_ppt_ocr()`；每个文件会新建OCR包装器对象；**同一个文件内部多张图片复用底层PaddleOCR实例**。
- **worker预热逻辑**：`init_worker()` / `process_one_file.py` 在**子进程启动时初始化一次`LocalPaddleProvider()`**，每个子进程仅一次预热，不是每张图片一次。

## 7.总场景清单
| 场景 | 入口文件 -> 函数 | 是否使用OCR | 使用哪套类 | 真正传给PaddleOCR参数 | 是否跨文件复用 |
|---|---|---|---|---|---|
| 全量入库 ingest | `kb_poc/cli.py → main() → kb_poc/ingestion/ingestor.py::ingest_directory()` | 是 | `ppt_ocr.py`的`PaddleOCRLocal/CompositeOCR` | `lang`可选；支持签名时`use_angle_cls=True` | ✅是；同一进程多个文件复用同一个`shared_ocr` |
| worker处理普通文件 | `kb_admin/worker.py → process_one() → kb_admin/ingestion.py::build_chunks_for_stage()` | full阶段启用OCR | `ppt_ocr.py`的`PaddleOCRLocal/CompositeOCR` | `lang`可选；支持签名时`use_angle_cls=True` | ❌通常否；每个文件新建OCR包装器；文件内部图片复用底层引擎 |
| worker重文件 | `kb_admin/process_one_file.py → main() → kb_admin/ingestion.py::build_chunks_for_stage()` | full阶段启用OCR | `ppt_ocr.py`的`PaddleOCRLocal/CompositeOCR` | `lang`可选；支持签名时`use_angle_cls=True` | ❌通常否；每个独立子进程文件新建 |
| worker子进程预热 | `kb_admin/worker.py → init_worker()` | 是，预热备用 | `ocr_provider.py`的`LocalPaddleProvider` | `lang`可选、`use_angle_cls`、可选`cpu_threads` | ❌每个子进程一次，进程隔离 |
| heavy重文件子进程预热 | `kb_admin/process_one_file.py → main()` | 是，预热备用 | `ocr_provider.py`的`LocalPaddleProvider` | `lang`可选、`use_angle_cls`、可选`cpu_threads` | ❌每个重文件子进程一次 |
| 检索retrieval | `kb_poc/qa/answerer.py` / `kb_poc/retrieval/*` | ❌否 | 不使用OCR | 无 | 无 |

> 重点提示：worker里面存在两条OCR对象线路；**PPT/Excel业务解析真正执行的是`ppt_ocr.py`那一套，预热provider只是备用对象**。

---

## 核心问题汇总（可用于排错）
1. **语言配置不生效**：settings里的`local_ocr_language`配置项，**主解析链路ppt_ocr没有读取**，硬编码默认日语`japan`；只有`ocr_provider.py`会读取语言参数。
2. **参数两套行为不一致**
    - `use_angle_cls`：主链写死True；provider链默认False；
    - `cpu_threads`：只有provider链路生效，主解析链路完全没有传入；
    - `enable_mkldnn`：配置存在，但两套代码都没有传给底层PaddleOCR，属于无效配置。
3. **多进程不能共享模型实例**，每个worker子进程都有自己独立OCR对象；全量ingest单进程模式才支持多文件复用OCR实例。
4. worker进程预热的`LocalPaddleProvider`对象，**并不会被传给PPT/Excel解析逻辑使用**，业务解析仍然会再次调用`build_ppt_ocr()`新建一套OCR包装器。

如果你需要，我可以再帮我输出一份「无效配置项」单独排错表格，或者输出改造伪代码，修复两套OCR参数不一致的问题。

