# kb‑chunk‑studio 模块分析报告
我已经把 `C:\Users\234393\Desktop\jap‑cycle‑poc` 的整体结构扫了一遍，并重点读完了 kb_chunk_studio 这块。结论先说：**kb_chunk_studio 不是主入库链路本身，而是一个「切块结果诊断 / 预览 / 人工编辑草稿层」**。它站在现有 chunk 结果上，提供文件列表、chunk 详情、重切预览、草稿保存、人工 split/merge/边界调整、以及 artifact 联查这些能力，主要服务于“看 chunk 切得对不对、调参数、做人工修正”。

先用大白话讲整体：这个板块的核心思路很清楚：先读取已经生成好的 `file‑*.json` chunk 批次文件，当作“当前正式结果”；如果你想测试别的 chunk 参数，它会重新解析原文件或读缓存快照，再跑 `_chunk_document()` 做 preview；如果你不只是看，还想手工改，它就把一份可编辑 chunk 列表存成 draft JSON，后续所有 split / merge / move_boundary 都落在 draft 上，不直接改正式入库结果。所以它本质上更像一个Chunk调参工作台 + 草稿箱，不是直接写回 Azure Search 的发布流程。

## 文件清单
| 文件 | 作用 | 我确认到的关键点 | 风险/注意点 |
|---|---|---|---|
| kb_chunk_studio\api.py | 提供 chunk studio 的后端API路由 | GET 包括 `/api/chunk‑studio/files`、`file`、`artifact`、`preview`、`drafts`、`draft`； POST 包括 `draft/create`、`draft/save`、`draft/edit` | 这里只是 HTTP 薄路由，真正逻辑都在 service.py |
| kb_chunk_studio\service.py | 业务核心 | 管文件列表、chunk详情、preview重切、draft创建/保存/编辑、artifact读取、质量评估、chunk操作应用 | 这是整个板块最重要的文件 |
| kb_chunk_studio\draft_store.py | 草稿持久化 | 草稿存到 `data\chunk_studio\drafts\*.json`；按 file_id 过滤；保存时自动补 draft_id / created_at / updated_at | 是纯文件存储，不是SQLite |
| kb_chunk_studio\segment_cache.py | 解析快照缓存 | 把 ParsedDocument 序列化到 `data\chunk_studio\cache\*.segments.json`，下次 preview 直接复用 | 避免每次 preview 都重跑解析/OCR，但缓存一致性要靠源文件名维持，不带 hash |
| kb_chunk_studio\ __init__.py | 模块导出 | 目前只导出 `handle_get` | 但 `api_admin.py` 直接从 kb_chunk_studio.api 导入 handle_get/handle_post，没问题 |

## service.py 的内部脉络
| 主题 | 代码位置 | 我读到的内容 |
|---|---|---|
| 上下文构建 | build_context | 用 KBSettings 组出 chunk_dir、artifact_dir、source_dir，后面所有操作都靠它定位项目数据目录 |
| 正式结果读取 | list_files / get_file_detail | 从 `kb_admin.ingestion.CHUNK_BATCH_DIR` 下读取 `file‑*.json`，通过 `read_chunk_batches()` 解析成 DocumentChunk；所以 chunk studio 的“基线”来自已生成 chunk 批次 |
| 预览重切 | preview_file_detail | 先取现有 file_detail，再 `_load_or_create_snapshot()` 拿 ParsedDocument，分别调用 `_chunk_document(snapshot, profile_overrides=…)` 做 baseline 与 preview 对比 |
| 草稿创建与保存 | create_draft / save_draft_detail / get_draft_detail | 草稿里会保存 base_chunks、edited_chunks、operations、profiles，而且 summary 是现算的，不是持久字段 |
| 人工编辑 | edit_draft_chunks + _apply_operation | 只支持三种操作：split、merge、move_boundary；每次操作后都会覆盖保存 draft，并追加到 operations |
| 质量评估 | _estimate_tokens / _judge_quality / _build_summary | token 是很粗略地按 len(text)//4 估算；少于20或多于350直接bad；过长且结尾不像完整句、或出现三连空行会 warn |
| artifact联查 | get_artifact_detail / _collect_related_artifacts | 可读取指定 artifact 文件，还能按 source_file + locator 找同一页/sheet 对应的其他阶段产物 |
| 源文件重解析 | _load_or_create_snapshot | `.md`/`.txt`/`.pdf` 走 `parse_markdown_file`；`.xlsx`/`.xlsm` 走 `parse_excel_file`；`.pptx` 走 `parse_pptx_file`；Excel/PPT preview 会建 OCR 引擎 |

## 关键设计点
1. 它依赖**已有 chunk 批次文件**作为入口。`list_files()` 是扫 `file‑*.json`，所以如果某文件还没进入 chunk batch，这里就看不到。
2. preview 不是在正式 chunk 上微调，而是重新从 ParsedDocument 再跑一遍 `_chunk_document()`。这意味着 preview 更接近“改 profile 后重新切”的模拟，而不是对当前 chunk做增量patch。
3. draft 编辑是纯前端/后端草稿，**不等于正式发布**。代码里我还没看到“把 draft 发布回主索引/主批次文件”的动作；目前更像人工修订工作区。
4. 缓存只按 source_file 文件名路径。如果不同目录下有同名文件，`_find_source_path()` 也是 rglob 找到第一个同名文件就返回，这里有潜在歧义；再加上 segment_cache 也是按 source_file 字符串做 safe_name，理论上会有同名冲突风险。
5. OCR preview 可能偏重。`_build_ocr_engine()` 每次 preview 解析 Excel/PPT 时会构造 OCR 引擎；虽然快照会减轻重复成本，但第一次 preview 仍可能慢。

## 和UI的接线关系
`kb_poc\ui\api_admin.py` 里已经把它接进主 Web 服务了。浏览器页面入口：
- `/chunk‑studio`
- `/chunk‑studio/chunk_studio.js`
- `/chunk‑studio/chunk_studio.css`

API入口则通过：
- `handle_chunk_studio_get(...)`
- `handle_chunk_studio_post(...)`

也就是说，这块不是孤立脚本，而是已经挂进现有 `admin/simple_api_server` 的一部分功能区。

## 事实与判断
| 类型 | 内容 |
|---|---|
| 已确认的事实 | kb_chunk_studio 负责 chunk 文件浏览、preview、draft、artifact详情；正式数据来源是 `file‑*.json`；草稿存本地JSON；preview会重跑`_chunk_document()` |
| 我的判断 | 这块目前完成度偏**内部调试工具**，已经够做人工诊断，但还不像完整的“人工修块发布系统”，因为我没看到 draft 回写正式 chunk 批次或触发重新索引的闭环 |

### 最小验证测试步骤
如果你想自己快速验证我这个判断：
1. 启动 `python -m kb_poc.ui.simple_api_server`
2. 打开 `/chunk‑studio`
3. 选一个已有 `file‑*.json` 的文件做 preview、create draft、edit
4. 再搜项目里有没有 `publish draft / apply draft to index / rewrite file‑*.json` 这类逻辑

如果没有，那就说明它现在确实主要停在“预览+草稿”层。

