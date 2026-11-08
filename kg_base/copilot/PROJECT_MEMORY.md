# 项目操作记忆(PROJECT_MEMORY)
> 规则:开工先读本文件;改动后只在"变更日志"追加,不删旧条目;结构各节保持更新。

## 1. 项目概述
- 一句话:日语保险知识库入库系统。资料 → 本地 OCR / 切片 / 向量化 → Azure AI Search → 检索问答。本地跑、运行成本 $0。
- 环境:Windows 11,Python 3.12.10,虚拟环境 `.venv312`(底座是 AppData 的 Python,venv 为启动壳)。
- 编辑者:GitHub Copilot CLI(自动加载 copilot-instructions.md)。

## 2. 架构与关键文件
- 切片:`kb_poc/ingestion/ingestor.py`(`_chunk_document` / `_chunk_profile`;参数读模块级全局常量 CHUNK_SIZE / PPT_/OCR_/PDF_ CHUNK_SIZE 等)。
- 解析:`kb_poc/parsing/`(pptx_parser / excel_parser;OCR 走 `ppt_ocr.py` 的 build_ppt_ocr → PaddleOCRLocal → _create_paddleocr)。
- 调度/编排:`kb_admin/worker.py`、`state_store.py`、`process_one_file.py`(重文件隔离)。
- 向量化:copilot_provider 的 text-embedding-3-large(API,按 token 计费、会限速)。
- chunk 可视化工作台:独立模块 `kb_chunk_studio/`;UI 设计定稿 `chunk_studio_target.html`。

## 3. 硬性约束(不可违反)
- 不重写切片/解析/embedding/索引核心逻辑;只做新增 / 透传 / 可选 override。
- UI 改动只碰前端;后端接口名/参数/返回字段只增不改。
- 子进程用 `sys.executable`(.venv312);单实例锁;重文件隔离、续跑、幂等、限速不变。
- OCR 本地免费;唯一外部计费是 embedding。业务数据不外传、不入日志明文、不进仓库。

## 4. 冻结契约(改前必核对,详见 docs/CONTRACTS.md)
- chunk 工作台前端调用的接口与返回 JSON 结构(待 Copilot 补全列出)。
- UI 设计定稿:`chunk_studio_target.html`(布局/样式/交互为准,数据可换)。

## 5. 当前状态(按模块)
| 模块 | 状态 |
| --- | --- |
| 入库主链路(单趟) | 可用 |
| 幽灵进程/解释器 | 已根治(mp 用 .venv312;退出零残留;硬杀后锁需手删) |
| OCR 提速(线程/计时) | 进行中 |
| 轻重文件判定放宽 | 待办 |
| embedding 8192 兜底 | 待办(在 embedding 层分窗合并,不改切分) |
| chunk 工作台 Phase 1-3 | 已做,UI 对齐定稿中 |
| chunk 工作台 Phase 4(应用生效+评估) | 未开始 |

## 6. 进行中 / 待办(带优先级)
- P0:(由 Copilot 续填)
- P1:
- P2:

## 7. 已知问题 / 坑(影响 + 应对 + 状态)
- venv 是 AppData python 启动壳 → 进程树"壳+本体"成对,正常;重建需重装包,受离线/权限限制,暂不动。
- 硬杀(taskkill /F)后 worker.pid.lock 需手删(自动清死锁待做)。
- embedding 单输入上限 8192 token;保留表格完整性会超 → 在 embedding 层兜底。
- 垃圾文件(~$ / Thumbs.db / .lnk)进链造成无效失败 → 门口过滤(状态见上)。

## 8. 决策记录(避免重复讨论)
- 两阶段(文本→OCR)已合并为单趟:简化状态机、减少重复开销。
- OCR 每进程复用 + max_tasks_per_child=30:复用提速 + 内存设上限(防内存累积)。
- chunk 工作台采用"独立模块 + 两个细口子(读产物 / 调 _chunk_document)",不碰主链路。

## 9. 术语表
- 收排认切译存问 = 上传/排队/OCR/切片/向量化/入库/问答。
- heavy(重文件)= 走独立子进程隔离;light = 走进程池并发。
- chunk / token / 向量 = 段落 / 模型的长度单位 / 代表语义的数字。

## 10. 运行与运维
- 启动 worker:自己在 .venv312 终端 `python -m kb_admin.worker`;停止:该终端 Ctrl+C。
- 被锁:杀占锁 PID(`taskkill /PID <pid> /T /F`)→ 删 `data\kb_admin\worker.pid.lock` → 重启。
- 验证改动:静态 + 单文件小测,勿真跑整 worker。

## 11. 变更日志(只追加,带日期)
- 2026-10-01 初始化本文件;确立套件(操作契约 + 本记忆 + 任务模板)。