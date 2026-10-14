from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_poc.config import KBSettings
from kb_poc.tool_schemas import (
    KGSyncApplyInput, KGSyncApplyOutput,
    KGSyncPlanInput, KGSyncPlanOutput, KGSyncEntityPreview,
    KGSyncRollbackInput, KGSyncRollbackOutput,
    KGSyncStatusInput, KGSyncStatusOutput,
)
from .extractors.base import ChunkText
from .extractors.rule_extractor import RuleExtractor
from .extractors.llm_extractor import LLMExtractor

# ⚠️对齐点1：确认模块路径
from kb_poc.kg import kg_incremental as inc


def _flag(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _count(x: Any) -> int:
    return len(x) if isinstance(x, (list, tuple, set, dict)) else int(x or 0)


def _merge_subgraphs(base: dict, extracted, exclude_ids: list[str]) -> dict:
    """把『现成匹配子图』和『抽取器子图』并起来，去重；剔除人工排除的新实体。"""
    excl = set(exclude_ids or [])
    nodes: dict[str, dict] = {}
    for n in base.get("nodes", []):
        nodes[n["id"]] = n
    for n in extracted.nodes:
        if n["id"] in excl:
            continue
        nodes.setdefault(n["id"], n)

    seen: set[tuple] = set()
    edges: list[dict] = []
    for e in list(base.get("edges", [])) + list(extracted.edges):
        if e["source"] in excl or e["target"] in excl:
            continue
        key = (e["source"], e.get("type"), e["target"])
        if key in seen:
            continue
        seen.add(key)
        edges.append(e)
    return {"nodes": list(nodes.values()), "edges": edges}


@dataclass(slots=True)
class KGSyncSkillRuntime:
    settings: KBSettings

    # ---------- 内部工具 ----------
    def _extractor(self):
        return LLMExtractor(self.settings) if _flag("KB_KGSYNC_EXTRACTOR", "rule") == "llm" else RuleExtractor()

    def _resolve_doc(self, file_path, doc_id, warnings) -> tuple[str | None, str | None, str | None]:
        """文件 → (doc_id, file_hash, source_file)。优先用 backfill 产出的映射表。"""
        if doc_id:
            fh = doc_id.split("::", 1)[1] if "::" in doc_id else doc_id
            return doc_id, fh, None
        # ⚠️对齐点2：确认映射文件路径与键名
        kv = Path(self.settings.resolve("data/kg/kg_versions")) if hasattr(self.settings, "resolve") else Path("kg_versions")
        mapping_path = kv / "business_kg_enriched.source_file_to_doc.json"
        source_file = Path(file_path).name if file_path else None
        try:
            mapping = json.loads(mapping_path.read_text("utf-8")).get("source_file_to_doc_id", {})
            did = mapping.get(source_file) or mapping.get(file_path)
            if did:
                fh = did.split("::", 1)[1] if "::" in did else did
                return did, fh, source_file
        except FileNotFoundError:
            warnings.append(f"未找到映射文件 {mapping_path}")
        warnings.append(f"无法由文件解析 doc_id：{file_path}；需补 state.db 查询或内容哈希。")
        return None, None, source_file

    def _load_chunk_texts(self, file_hash, source_file, warnings) -> list[ChunkText]:
        """读取某文档所有 chunk 的正文。⚠️对齐点6：路径/字段按你们真实结构。"""
        if not file_hash:
            return []
        jsonl = Path(f"data/kb_admin/jsonl/file-{file_hash}.jsonl")
        out: list[ChunkText] = []
        try:
            for line in jsonl.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                md = row.get("metadata", {})
                out.append(ChunkText(
                    chunk_id=str(row.get("chunk_id", "")),
                    content=str(row.get("content", "")),
                    source_file=str(md.get("source_file", source_file or "")),
                    page_or_sheet=str(md.get("page_or_sheet", "")),
                ))
        except FileNotFoundError:
            warnings.append(f"未找到正文文件 {jsonl}；该文档只能做已有实体匹配，无法抽新实体。")
        return out

    def _compute_plan(self, op, file_path, doc_id, exclude_ids):
        warnings: list[str] = []
        kg = inc.get_active_graph()  # ⚠️对齐点1
        did, fh, src = self._resolve_doc(file_path, doc_id, warnings)
        if not did:
            return None, [], src, warnings

        if op == "delete":
            # ⚠️对齐点3：ops 结构
            plan = inc.plan_delta([{"op": "delete", "doc_id": did}], kg)
            return plan, [], src, warnings

        # add / update：现成匹配 + 抽取器补新实体
        base = inc.build_subgraph_for_document(did, kg)  # ⚠️对齐点1 返回 {nodes,edges}
        chunk_texts = self._load_chunk_texts(fh, src, warnings)
        existing_labels = {n["label"]: n["id"] for n in kg.get("nodes", []) if n.get("type") != "Chunk"}
        extracted = self._extractor().extract(chunk_texts, existing_labels, did)
        merged = _merge_subgraphs(base, extracted, exclude_ids)

        # ⚠️对齐点4：plan_delta 需支持预构建子图（见 mini-patch）
        plan = inc.plan_delta([{"op": op, "doc_id": did, "subgraph": merged}], kg)

        preview = [
            KGSyncEntityPreview(id=n["id"], type=n["type"], label=n["label"], reason=n.get("_reason", "rule_new"))
            for n in extracted.nodes
            if n.get("type") != "Chunk" and n.get("_reason") == "rule_new" and n["id"] not in exclude_ids
        ]
        return plan, preview, src, warnings

    @staticmethod
    def _plan_counts(plan) -> dict[str, int]:
        g = lambda k: _count(getattr(plan, k, None))  # noqa: E731
        return {
            "nodes_added": g("nodes_added"), "nodes_removed": g("nodes_removed"), "nodes_touched": g("nodes_touched"),
            "edges_added": g("edges_added"), "edges_removed": g("edges_removed"), "edges_touched": g("edges_touched"),
        }

    # ---------- 对外工具（每个对应一个 tool）----------
    def kg_sync_status(self, _: KGSyncStatusInput) -> KGSyncStatusOutput:
        kg = inc.get_active_graph()
        man = inc._load_manifest()
        nodes, edges = kg.get("nodes", []), kg.get("edges", [])
        unresolved = sum(1 for n in nodes if n.get("type") != "Chunk" and not n.get("source_docs"))
        rpt = (f"当前版本：{man.get('active')}\n节点：{len(nodes)}  边：{len(edges)}  "
               f"无来源实体：{unresolved}\n抽取器：{_flag('KB_KGSYNC_EXTRACTOR','rule')}  "
               f"存储：{_flag('KB_KGSYNC_STORE','json')}  启用：{_flag('KB_KGSYNC_ENABLED','0')}")
        return KGSyncStatusOutput(
            active_version=man.get("active"), node_count=len(nodes), edge_count=len(edges),
            unresolved_count=unresolved, extractor=_flag("KB_KGSYNC_EXTRACTOR", "rule"),
            store=_flag("KB_KGSYNC_STORE", "json"), enabled=_flag("KB_KGSYNC_ENABLED", "0") not in ("0", "false", "no", "off", ""),
            report_text=rpt)

    def kg_sync_plan(self, inp: KGSyncPlanInput) -> KGSyncPlanOutput:
        plan, preview, src, warnings = self._compute_plan(inp.op, inp.file_path, inp.doc_id, inp.exclude_entity_ids)
        if plan is None:
            return KGSyncPlanOutput(op=inp.op, doc_id=inp.doc_id, source_file=src,
                                    nodes_added=0, nodes_removed=0, nodes_touched=0,
                                    edges_added=0, edges_removed=0, edges_touched=0,
                                    new_entities_for_review=[], warnings=warnings,
                                    report_text="无法解析文档，无法预演。\n" + "\n".join(warnings))
        c = self._plan_counts(plan)
        rpt = (f"【预演·{inp.op}】{src or inp.doc_id}\n"
               f"节点：+{c['nodes_added']} / -{c['nodes_removed']} / ~{c['nodes_touched']}\n"
               f"边：  +{c['edges_added']} / -{c['edges_removed']} / ~{c['edges_touched']}\n"
               f"规则新抽实体待人工确认：{len(preview)} 个\n"
               + ("\n".join(f"  - [{p.type}] {p.label}" for p in preview) if preview else "")
               + ("\n⚠ " + "；".join(warnings) if warnings else "")
               + "\n（此为预演，未写入。确认后用 kg_sync_apply，confirm=True）")
        return KGSyncPlanOutput(op=inp.op, doc_id=inp.doc_id, source_file=src, **c,
                                new_entities_for_review=preview, warnings=warnings, report_text=rpt)

    def kg_sync_apply(self, inp: KGSyncApplyInput) -> KGSyncApplyOutput:
        man_before = inc._load_manifest()
        if not inp.confirm:
            return KGSyncApplyOutput(ok=False, from_version=man_before.get("active"), to_version=None,
                                     delta_file=None, message="未确认：请带 confirm=True 才会写入。先用 kg_sync_plan 预演。")
        plan, _, src, warnings = self._compute_plan(inp.op, inp.file_path, inp.doc_id, inp.exclude_entity_ids)
        if plan is None:
            return KGSyncApplyOutput(ok=False, from_version=man_before.get("active"), to_version=None,
                                     delta_file=None, message="无法解析文档：" + "；".join(warnings))
        inc.apply_delta(plan)  # ⚠️对齐点5：复用现成写盘+版本+changelog
        man_after = inc._load_manifest()
        return KGSyncApplyOutput(ok=True, from_version=man_before.get("active"),
                                 to_version=man_after.get("active"), delta_file=None,
                                 message=f"已应用 {inp.op}：{man_before.get('active')} → {man_after.get('active')}。可用 kg_sync_rollback 回退。")

    def kg_sync_rollback(self, inp: KGSyncRollbackInput) -> KGSyncRollbackOutput:
        inc.rollback()  # ⚠️对齐点1：若支持指定版本，这里透传 inp.to_version
        man = inc._load_manifest()
        return KGSyncRollbackOutput(ok=True, active_version=man.get("active"),
                                    message=f"已回退，当前版本：{man.get('active')}")
