# 任务:heavy 文件 OCR 提速(不改核心逻辑、不删中间产物)

## 目标
单个 heavy 文件 OCR 太慢,20 分钟都跑不完。在不动解析逻辑、不删中间产物的前提下,通过"让 OCR 配置真生效 + 吃满 CPU + 加计时日志"来提速并定位瓶颈。

## 先说明再动手
先读 OCR 的创建与调用处(`kb_poc/parsing/ppt_ocr.py` 的 `build_ppt_ocr` / `_create_paddleocr`,以及 heavy 子进程 `kb_admin/process_one_file.py`),讲清:现在 `cpu_threads`、`enable_mkldnn` 有没有真的传进 PaddleOCR?每张图目前怎么调用?再动手。

## 具体改动
1. **确认并接通配置**:`cpu_threads`、`enable_mkldnn`、`use_angle_cls`、`language` 从 `KBSettings` 读取并**真正传给 PaddleOCR**。(若领导已把 OCR 统一成单路径,以那条为准;哪项没接通就补上。)
2. **heavy 子进程吃满核**:因为 heavy 单独跑,把 OCR 的 `cpu_threads` 设为可用核数(可留 1–2 核余量),Intel 机器开 `mkldnn`。做成可配置常量。
3. **每图计时日志**:每处理一张图打印 `OCR 第 k/N 张 尺寸=W×H 用时=Xs`;文件结束再打印总图数、OCR 总耗时、最慢的几张。

## 必须保持不变
解析正确性、中间产物(不删)、重文件隔离、续跑/重试/幂等、单实例锁、解释器(sys.executable / .venv312)。

## 验收标准
- 日志能看到每张图耗时 + 文件总耗时 + 最慢的图。
- 调大 `cpu_threads` / 开 `mkldnn` 后,单个 heavy 明显提速。
- 识别结果不变。