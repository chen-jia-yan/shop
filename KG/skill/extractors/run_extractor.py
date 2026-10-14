from __future__ import annotations

import hashlib
import re

from .base import ChunkText, EntityExtractor, SubGraph


def _chunk_id(content: str) -> str:
    # ⚠️对齐点6：确认 Chunk id = sha256(正文 utf-8) 的前 12 位
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:12]


def _type_of(entity_id: str) -> str:
    return entity_id.split(":", 1)[0] if ":" in entity_id else "Concept"


def _label_of(entity_id: str, fallback: str) -> str:
    return entity_id.split(":", 1)[1] if ":" in entity_id else fallback


class RuleExtractor(EntityExtractor):
    """
    离线、免费、确定性的规则抽取器。能稳稳做到：
      1) 词典匹配——把文档正文里出现的【已有实体】连上 mentioned_in；
      2) 结构化规则——抽取有明显规律的【新实体】（默认空，模式由你确认后填）；
      3) 同一 chunk 共现 → 建弱关联边（标 provenance_inferred=True）。
    带类型的语义关系（包含/属于等）规则判不准，这里不瞎建，留给 LLM 版或人工。
    """

    name = "rule"
    MIN_LABEL_LEN = 2       # 防 1 字误匹配
    MAX_COOCCUR = 12        # 单 chunk 共现实体过多则跳过，避免边爆炸

    def __init__(self, aliases: dict[str, str] | None = None,
                 patterns: list[tuple[str, re.Pattern]] | None = None):
        # aliases: 别名 -> 规范 label（可放一个可编辑的 aliases.json 读进来）
        self.aliases = aliases or {}
        # patterns: [(实体类型, 已编译正则), ...]
        # 示例（先别启用，等你确认画面ID等模式是否要当实体）：
        #   patterns = [("Concept", re.compile(r"D\d{4}"))]
        self.patterns = patterns or []

    def extract(self, chunks, existing_labels, source_doc_id):
        nodes_by_id: dict[str, dict] = {}
        edges: list[dict] = []

        label_to_id = dict(existing_labels)
        for alias, canon in self.aliases.items():
            if canon in existing_labels:
                label_to_id[alias] = existing_labels[canon]

        def _ensure_chunk_node(ch: ChunkText, cid: str):
            nodes_by_id.setdefault(cid, {
                "id": cid, "type": "Chunk",
                "label": f"{ch.source_file} / {ch.page_or_sheet}".strip(" /"),
                "metadata": {"source_file": ch.source_file,
                             "page_or_sheet": ch.page_or_sheet, "cell_range": ""},
                "source_docs": [source_doc_id],
            })

        for ch in chunks:
            text = ch.content or ""
            if not text:
                continue
            cid = _chunk_id(text)
            present: list[str] = []

            # 1) 词典匹配已有实体
            for label, eid in label_to_id.items():
                if len(label) >= self.MIN_LABEL_LEN and label in text:
                    present.append(eid)
                    nodes_by_id.setdefault(eid, {
                        "id": eid, "type": _type_of(eid), "label": _label_of(eid, label),
                        "source_docs": [source_doc_id], "_reason": "matched_existing",
                    })
                    _ensure_chunk_node(ch, cid)
                    edges.append({"source": eid, "target": cid, "type": "mentioned_in",
                                  "source_docs": [source_doc_id], "provenance_inferred": True})

            # 2) 结构化规则抽新实体
            existing_ids = set(existing_labels.values())
            for etype, rx in self.patterns:
                for m in set(rx.findall(text)):
                    nid = f"{etype}:{m}"
                    if nid in existing_ids:
                        continue
                    present.append(nid)
                    nodes_by_id.setdefault(nid, {
                        "id": nid, "type": etype, "label": m,
                        "source_docs": [source_doc_id], "_reason": "rule_new",
                    })
                    _ensure_chunk_node(ch, cid)
                    edges.append({"source": nid, "target": cid, "type": "mentioned_in",
                                  "source_docs": [source_doc_id], "provenance_inferred": True})

            # 3) 同 chunk 共现 → 弱关联边
            uniq = list(dict.fromkeys(present))
            if 2 <= len(uniq) <= self.MAX_COOCCUR:
                for i in range(len(uniq)):
                    for j in range(i + 1, len(uniq)):
                        edges.append({"source": uniq[i], "target": uniq[j], "type": "related_chunk",
                                      "source_docs": [source_doc_id], "provenance_inferred": True})

        return SubGraph(nodes=list(nodes_by_id.values()), edges=edges)
