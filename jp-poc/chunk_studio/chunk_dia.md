# service.py 只读分析报告
## 1、函数清单
### 公共接口函数
| 函数 | 作用 | 调用了哪些 |
|---|---|---|
| build_context | 构建 ChunkStudioContext(含 settings/chunk_dir/artifact_dir/source_dir) | KBSettings.load、CHUNK_BATCH_DIR、artifact_base_dir |
| list_files | 遍历 `file‑*.json`，列出所有已入库文件清单 | read_chunk_batches、_extract_file_id、human_size |
| get_file_detail | 按 file_id 返回单文件详情(含 chunks/tree/profiles) | read_chunk_batches、_serialize_chunk、_build_tree、_default_profiles |
| preview_file_detail | 核心：取快照 → 用主链路 `_chunk_document`，跑两组参数生成 baseline vs preview 对比 | get_file_detail、_load_or_create_snapshot、_chunk_document(×2)、_serialize_chunk、_build_tree、_build_summary |
| list_file_drafts | 列出某个文件的所有草稿 | list_saved_drafts(→ draft_store) |
| create_draft | 跑 preview → 用预览 chunks 作为初始数据 + 调用 save 生成草稿 | preview_file_detail、_normalize_editable_chunk、save_draft(→ draft_store) |
| get_draft_detail | 加载单个草稿并补充 summary | load_draft(→ draft_store)、_build_summary |
| save_draft_detail | 覆盖保存草稿(全量更新 edited_chunks + operations) | load_draft、save_draft、_normalize_editable_chunk、_build_summary |
| edit_draft_chunks | 单次编辑操作(split/merge/move_boundary)应用到草稿 | load_draft、_normalize_editable_chunk、_apply_operation、save_draft、_build_summary |
| get_artifact_detail | 读取 artifact 文件内容 + 收集关联 artifacts | safe_under、_read_artifact_payload、_collect_related_artifacts |

### 内部辅助函数
| 函数 | 作用 | 调用了哪些 |
|---|---|---|
| _serialize_chunk | DocumentChunk → 字典(含 token/quality/ocr_blocks) | _estimate_tokens、_judge_quality |
| _build_tree | 按 locator 分组建树状结构 | (纯数据组装) |
| _read_artifact_payload | 读 artifact 文件(.json → JSON解析，其他 → 纯文本) | (纯文件读写) |
| _collect_related_artifacts | 按 source_file+locator 前缀匹配收集关联产物 | _sanitize、_read_artifact_payload |
| _estimate_tokens | 粗估 token 数：`len//4` | (纯计算) |
| _judge_quality | 按 token范围/末尾标点/多余空行判定 good/warn/bad | (纯判断) |
| _extract_file_id | 从 `file‑{id}.json` 提取 id | (正则) |
| _sanitize | 文件名安全化(非字母数字→_) | (纯字符串) |
| _default_profiles | 返回4组默认 chunk_size/overlap | (无依赖) |
| _build_summary | 统计 chunks 的token分布+质量分布 | (纯统计) |
| _normalize_editable_chunk | 把 dict 标准化为 editable chunk 格式 | _estimate_tokens、_judge_quality、_make_chunk_id |
| _apply_operation | 按 type 分派 split/merge/move_boundary | _apply_split、_apply_merge、_apply_boundary_shift |
| _apply_split | 按 offset 一分为二 | _find_chunk_index、_normalize_editable_chunk、_make_chunk_id |
| _apply_merge | 合并相邻两个 chunk | _find_chunk_index、_normalize_editable_chunk、_make_chunk_id |
| _apply_boundary_shift | 调整相邻 chunk 边界 | _find_chunk_index、_normalize_editable_chunk、_make_chunk_id |
| _find_chunk_index | 按 draft_chunk_id 在列表中找下标 | (纯遍历) |
| _make_chunk_id | text hash 取数字转12位 id | (正则+hash) |
| _load_or_create_snapshot | 缓存优先 → 缓存未命中则 real parse(含OCR)并落缓存 | load_document_snapshot、_find_source_path、parse_*、_build_ocr_engine、save_document_snapshot |
| _find_source_path | 在 source_dir 下递归搜索文件名 | (rglob) |
| _build_ocr_engine | 构建 PaddleOCR 引擎 | build_configured_ppt_ocr |

## 2、原样贴出关键代码段
### a) `/artifact` 函数 — 路径限制全过程
```python
# 行 201‑219
def get_artifact_detail(context: ChunkStudioContext, artifact_path: str, ...) -> dict[str, Any]:
    normalized = unquote(artifact_path or "").strip().replace("/", "\\")
    if not normalized:
        raise ValueError("artifact_path is required")

    target = safe_under(context.settings.project_root, normalized) # ← 关键：safe_under
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    ...
```
`safe_under` 的实现（api_common.py 行 10‑14）：
```python
def safe_under(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ValueError("Path escapes source directory")
    return candidate
```
**结论：已做限制。**`safe_under` 先把传入路径拼到 `project_root` 下，resolve 后再检查 `project_root` 是否在 candidate 的所有父目录中。如果传入 `../../etc/passwd`，resolve后根不在 candidate.parents 中，直接抛 `ValueError`。

### b) `/preview` — 切分逻辑
```python
# 行 97‑117
def preview_file_detail(context, file_id, profile_overrides):
    detail = get_file_detail(context, file_id)
    snapshot = _load_or_create_snapshot(context, detail["file"]["source_file"])
    baseline_chunks = _chunk_document(snapshot)                     # 主链路
    preview_chunks = _chunk_document(snapshot, profile_overrides=profile_overrides) # ← 主链路(带参数覆盖)
    ...
```
**结论：**走的是同一条主链路 `_chunk_document`（来自 `kb_poc.ingestion.ingestor`），自己没另写切分逻辑。只是在参数上区分 baseline（默认）和 preview（用户 override）。

### c) 文档内容获取：缓存 vs 实时解析
```python
# 行 456‑472
def _load_or_create_snapshot(context: ChunkStudioContext, source_file: str) -> ParsedDocument:
    cached = load_document_snapshot(context.settings, source_file) # ← 先查缓存
    if cached is not None:
        return cached                                              # 命中：直接返回，不触发 OCR

    source_path = _find_source_path(context.source_dir, source_file)
    suffix = source_path.suffix.lower()
    if suffix in {".md", ".txt", ".pdf"}:
        document = parse_markdown_file(source_path)                 # md/pdf 不走 OCR
    elif suffix in {".xlsx", ".xlsm"}:
        document = parse_excel_file(source_path, ..., ocr_engine=_build_ocr_engine(...)) # ← 走 OCR
    elif suffix == ".pptx":
        document = parse_pptx_file(source_path, ..., ocr_engine=_build_ocr_engine(...)) # ← 走 OCR
    ...
    save_document_snapshot(context.settings, document)              # ← 缓存落盘
    return document
```
**结论：**先走 `segment_cache` 的JSON缓存快照。缓存命中 → 零解析、零OCR。缓存未命中 → 根据文件类型走 real parse：`.md/.txt/.pdf` 不触发OCR；`.xlsx/.pptx` 会触发OCR（调用`_build_ocr_engine` → `build_configured_ppt_ocr`）。解析完后写入缓存。

### d) 新建/保存草稿时 draft_id 的确定
创建草稿（service.py 行 124‑146）：
```python
def create_draft(...):
    ...
    payload = save_draft(context.settings, {
        "name": ...,
        "file_id": file_id,
        ...
    })
    # ← 注意：这里没传 draft_id！
```
save_draft（draft_store.py 行 52‑61）：
```python
def save_draft(settings, payload):
    ...
    draft_id = str(payload.get("draft_id")) or uuid4().hex # ← 有就用现有的，没有就 uuid4 生成
    payload["draft_id"] = draft_id
    ...
```
**结论：**新建时 `create_draft` 不传 `draft_id`，`save_draft` 自动用 `uuid4().hex` 生成一个新ID并写回 payload。后续 `save_draft_detail` / `edit_draft_chunks` 都会传已有的 `draft_id`，`save_draft` 从 payload 里取到就沿用不变。

## 3、【preview 会不会重新跑 OCR？】
正常情况下不会。preview链路：`preview_file_detail` → `_load_or_create_snapshot` → 先查 `segment_cache`。只要之前打开过同一个文件（缓存JSON已存在），就直接反序列化为 `ParsedDocument`，完全不碰 parse/OCR。

只有**首次打开、缓存文件不存在**时才会走 real parse。此时 `.xlsx` / `.pptx` 会触发OCR。但解析完立即写入缓存，后续同文件再 preview 就不再跑 OCR。

