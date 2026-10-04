# 任务：修复 PaddleOCR 在 PPT ingest 时的不稳定与低识别率问题

## 背景
这是一个知识库 ingest 项目，用 PaddleOCR 识别 PPT/Excel 中的嵌入图片。运行环境：CPU 版 Python 3.12.10、PaddleOCR 2.10.0、PaddlePaddle 2.6.2。单次 ingest 约 239 张图，其中约 81 张通过尺寸门槛。图片中位数只有 152×141，混有透明 PNG、图标、流程图截图。当前在 batch ingest 时会出现内存增长、崩溃、识别不稳定。**不要升级 PaddleOCR 到 3.x 或改用 PP-StructureV3 / PaddleOCR-VL（CPU 上会 OOM）。**

## 根本原因
`parsing/ppt_ocr.py` 里 `_extract_with_paddle_ocr()`、`extract_blocks_with_paddle_ocr()` 以及 PPStructure 路径，每次识别都在函数内 `ocr = PaddleOCR(...)` / `engine = PPStructure(...)` 重新实例化。加上每张图跑 4 个预处理变体（original/upscaled/grayscale_contrast/binarized），导致一次 ingest 有数百次模型加载，引发内存泄漏和崩溃。

## 需要你做的改动（按优先级）

1. **实例只创建一次、全程复用（最重要）**
   - 把真正的 `PaddleOCR` 实例放进项目级 OCR 包装器（`build_ppt_ocr` 构造时初始化一次），PPStructure 用懒加载但同样只建一次。
   - 删除 `ppt_ocr.py` 中所有函数内部的 `PaddleOCR(...)` / `PPStructure(...)` 调用，改为调用传入的共享实例的方法。
   - 构造参数加上 `enable_mkldnn=True`、`cpu_threads=<物理核数>`、`use_angle_cls=True`。

2. **4 个预处理变体改为级联（cascade），而非每张全跑**
   - 先判断尺寸：仅当 width<1200 或 height<800 时用 Lanczos 放大 2×，大图不动。
   - 先跑一档 OCR；只有当无文本或平均置信度低于阈值时，才回退到"灰度+对比度增强(1.8)"这一档。
   - 默认关闭 Otsu 二值化变体（二值图常导致 PaddleOCR 掉点），保留为可配置开关。

3. **线程安全约束**
   - 不要在多线程间共享同一个 PaddleOCR 实例（非线程安全）。保持单线程顺序处理；如需并行，用进程池且每进程各自持有独立实例。

4. **图片筛选与预处理修正**
   - 收紧 `should_attempt_ocr()`：在现有 min_width/min_height 基础上增加长宽比异常、近纯色/高透明占比的过滤，减少图标/logo 噪声。
   - 透明 PNG 在转 RGB 前先合成到白色背景（alpha_composite），避免透明区被当黑色导致小字丢失。

## 约束
- 保持对外接口（`build_ppt_ocr`、`parse_pptx_file`、`parse_excel_file`、`_convert_and_parse`）签名不变。
- 不引入新的重型依赖，不升级 Paddle 相关版本。
- 改动集中在 `parsing/ppt_ocr.py` 和 OCR 包装器构造处。

## 验收标准
- 一次完整 ingest（约 81 张有效图）内存平稳、无崩溃。
- 全程只初始化一次 PaddleOCR / PPStructure 实例（可用日志或计数断言验证）。
- 单张图默认最多跑 1~2 次 OCR，而非 4 次。
- 输出识别文本质量不低于改动前。

先给出改动的文件清单和关键 diff，再实现。

