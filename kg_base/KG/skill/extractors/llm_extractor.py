from __future__ import annotations

from .base import ChunkText, EntityExtractor, SubGraph


class LLMExtractor(EntityExtractor):
    """包一层你们现成的 kg_extractor.py。仅当开关=llm 时启用（要联网、要花钱）。"""

    name = "llm"

    def __init__(self, settings):
        self.settings = settings

    def extract(self, chunks, existing_labels, source_doc_id):
        # ⚠️对齐点1：确认 extract_from_chunks 的签名与返回
        from kb_poc.kg.kg_extractor import extract_from_chunks

        raw = [{"content": c.content,
                "metadata": {"source_file": c.source_file, "page_or_sheet": c.page_or_sheet}}
               for c in chunks]
        source_file = chunks[0].source_file if chunks else ""
        sub = extract_from_chunks(raw, self.settings, source_file=source_file)

        nodes = sub.get("nodes", [])
        edges = sub.get("edges", [])
        for n in nodes:
            n.setdefault("source_docs", [source_doc_id])
        for e in edges:
            e.setdefault("source_docs", [source_doc_id])
            e.setdefault("provenance_inferred", False)  # LLM 抽取视为精确
        return SubGraph(nodes=nodes, edges=edges)
