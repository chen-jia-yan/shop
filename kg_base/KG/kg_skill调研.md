# kg_skill调研
## 1. kg_incremental.py 可复用函数
| 函数 | 文件:行号 | 作用 |
| ---- | ---- | ---- |
| `_read_json(path)` | L107-110 | 读 JSON 文件 |
| `_write_json_atomic(path, value)` | L76-104 | 原子写（临时文件+rename+fsync），不写坏已有文件 |
| `_load_manifest()` | L118-122 | 加载 manifest.json，不存在返回 `{active:null, history:[]}` |
| `_save_manifest(manifest)` | L125-127 | 原子写 manifest |
| `get_active_graph()` | L130-144 | 读当前 active 版本 KG（尊重 KB_KG_USE_VERSIONS 开关） |
| `plan_delta(ops, kg)` | L347-390 | 纯内存计算变更计划，不写盘，返回 DeltaPlan |
| `_plan_add() / _plan_delete() / _plan_update()` | L429+ | plan_delta 的子函数，处理三种操作 |
| `build_subgraph_for_document(doc_id, kg)` | L232-329 | 为单个文档构建子图（Chunk 节点 + 字符串匹配实体 + mentioned_in 边） |
| `_get_chunks_for_doc(doc_id)` | L170-191 | 从 state.db 查 doc_id → file_hash → 文件路径 |
| `apply_delta(plan)` | L684-727 | 正式应用：写 v{N+1}.json + 更新 manifest + 写 changelog |
| `rollback()` | L810+ | 回滚到上一版本（切 manifest.active 指向前一版） |
| `DeltaPlan dataclass` | L47-68 | 变更计划结构：nodes_added/removed/touched, edges_added/removed/touched, ops, orphan_edges 等 |

### 版本管理机制
- 基线：`kg_versions/business_kg_enriched.provenance.json`（16,790 节点）
- 增删改 → `apply_delta` → 写 `kg_versions/v{N}.json`（全量快照）+ 更新 `manifest.json` 的 `active` 和 `history`
- 每次 apply 还写 `changelog/delta_{ts}.json`
- rollback 只需切 `manifest.active` 指向前一版即可

---

## 2. kg_extractor.py 的输入输出接口
| 项 | 详情 |
| ---- | ---- |
| 入口函数 | `extract_from_chunks(chunks, settings, source_file)` → L278-332 |
| 输入 | chunks: `list[dict]`，每个含 `content(str)` + `metadata(dict` 含 `source_file/page_or_sheet)` |
| 调 LLM 的步骤 | `_build_extraction_prompt(chunks)` 构建 prompt → `client.create_chat_completion()` 调 LLM → `_parse_llm_response(content)` 解析 JSON |
| 输出（子图） | `{nodes: [...], edges: [...]}`，由 `_build_subgraph(chunks, extracted, source_file)` 组装（L154-275） |
| LLM 返回 JSON | `{entities: [{id, type, label}], relations: [{source, target, type}], mentioned_in: [[entity_id, chunk_index]]}` |
| 最终节点 | 实体节点（`{id:"Type:label", type, label}`）+ Chunk 节点（`{id:sha256[:12], type:"Chunk", label, metadata}`） |
| 最终边 | 语义边（`{source, target, type}`）+ mentioned_in 边（`{source:entity_id, target:chunk_id, type:"mentioned_in"}`） |
| 不调 LLM 的变体 | `extract_from_chunks_dry_run()`（L335-366）：调 LLM 但不写文件 |

---

## 3. 离线下如何拿到「某文档所有 chunk 的正文文字」
> 目前 KG 里的 Chunk 节点只有 metadata，没有 content 正文！

| 途径 | 说明 |
| ---- | ---- |
| `_get_chunks_for_doc(doc_id)`（L170） | 从 state.db 的 files 表查 file_hash → 仅返回文件路径，不含 chunk 内容 |
| `_get_chunks_from_kg(kg, source_file)`（L198） | 从 KG 现有 Chunk 节点中按 source_file 过滤，但 Chunk 节点只含 `{id, label, type, metadata, source_docs}`，无 content |
| `build_subgraph_for_document`（L232） | 用 Chunk 的 label（文件名/页数）+ metadata 做字符串匹配实体，不读正文 |

要拿正文需要从源头取：
- `state.db` → `file_hash` → 找到 `data/kb_admin/jsonl/file-{hash}.jsonl` → 读 chunk 的 `content` 字段
- 或者从 `kb_admin/state_store.py` 里的 SQLite `chunks` 表（如果有的话）

---

## 4. Skills 框架规范
每个 skill 在 `kb_poc/skills/{name}/` 下需含：

| 文件 | 作用 |
| ---- | ---- |
| `manifest.json` | 元数据：name, description, version, category, enabled, entrypoint, tools[], docs[], tags[], allows_mutation, requires_model, defaults |
| `runtime.py` | `@dataclass(slots=True) class XxxSkillRuntime`，settings 注入，每个 tool 一个方法 |
| `__init__.py` | 空即可 |

注册到系统：
1. `tool_schemas.py`：定义 Pydantic `XxxInput` / `XxxOutput`（继承 `BaseModel`）
2. `tool_registry.py`：在 `get_tool_registry()` 加 `ToolSpec(name, description, input_model, output_model, skill)`
3. `ToolDispatcher` 通过 `SkillLoader` 扫描 `skills/*/manifest.json` → 按 `entrypoint` 加载 runtime → 按 tool name 反射调用方法

现成可抄的模板：`rag_eval` skill（有 `manifest.json + runtime.py + tool_schemas` 的 `RunRagEvalInput/Output`）

---

## 5. 当前实体节点 / 边 / 来源标签的真实字段结构
实体节点（非 Chunk）：
```json
{
  "id": "Concept:特定3大疾病给付金特约2",
  "type": "Concept",  // Product|System|Process|Data|Document|Role|Channel|Concept
  "label": "特定3大疾病给付金特约2",
  "source_docs": ["doc::019d7a7b7f2059e3", ...]  // 引用计数列表
}
```

Chunk 节点：
```json
{
  "id": "74baf908182e",  // SHA256 前12位
  "type": "Chunk",
  "label": "#15_SFDC.pptx / slide-6",
  "metadata": {"source_file": "...", "page_or_sheet": "slide-6", "cell_range": ""},
  "source_docs": ["doc::06a7841404ed3988"]
}
```

边：
```json
{
  "source": "Concept:特定3大疾病给付金特约2",
  "target": "Product:FWD医疗商品",
  "type": "追加于",
  "source_docs": ["doc::019d7a7b7f2059e3", ...],
  "provenance_inferred": true  // 是否存在（规则推断=true，LLM抽取时=false）
}
```

关键发现：
- 所有节点和边都有 `source_docs: list[str]` 字段，是引用计数的核心
- 实体 ID 格式：`Type:label`（如 `System:SFDC`）
- Chunk ID 格式：12 位 SHA256 hex（无类型前缀）
- 边有 `provenance_inferred` 标记，区分规则推演 vs LLM 抽取
- `mentioned_in` 是特殊边类型，连接实体和 Chunk
