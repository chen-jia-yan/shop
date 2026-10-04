from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_poc.config import KBSettings
from kb_poc.parsing.base import ArtifactReference, FlowchartEdge, FlowchartGraph, FlowchartNode, ParsedDocument, ParsedSegment

SEGMENT_CACHE_DIR = Path("data") / "chunk_studio" / "cache"


def build_cache_path(settings: KBSettings, source_file: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in source_file)
    return settings.resolve(SEGMENT_CACHE_DIR) / f"{safe_name}.segments.json"


def save_document_snapshot(settings: KBSettings, document: ParsedDocument) -> Path:
    target = build_cache_path(settings, document.source_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_document_to_dict(document), ensure_ascii=False), encoding="utf-8")
    return target


def load_document_snapshot(settings: KBSettings, source_file: str) -> ParsedDocument | None:
    target = build_cache_path(settings, source_file)
    if not target.exists():
        return None
    return _document_from_dict(json.loads(target.read_text(encoding="utf-8")))


def _document_to_dict(document: ParsedDocument) -> dict[str, Any]:
    return {
        "source_file": document.source_file,
        "doc_type": document.doc_type,
        "language": document.language,
        "product_name": document.product_name,
        "cycle_stage": document.cycle_stage,
        "artifact_refs": document.artifact_refs.to_dict(),
        "segments": [_segment_to_dict(segment) for segment in document.segments],
    }


def _segment_to_dict(segment: ParsedSegment) -> dict[str, Any]:
    return {
        "text": segment.text,
        "locator": segment.locator,
        "cell_range": segment.cell_range,
        "title_path": segment.title_path,
        "section_title": segment.section_title,
        "content_type": segment.content_type,
        "block_type": segment.block_type,
        "source_kind": segment.source_kind,
        "evidence_level": segment.evidence_level,
        "semantic_tags": list[str](segment.semantic_tags),
        "entities": list[str](segment.entities),
        "table_headers": list[str](segment.table_headers),
        "artifact_path": segment.artifact_path,
        "ocr_blocks": list[dict[str, Any]](segment.ocr_blocks),
        "flowchart": _flowchart_to_dict(segment.flowchart),
    }


def _document_from_dict(payload: dict[str, Any]) -> ParsedDocument:
    refs = payload.get("artifact_refs") or {}
    return ParsedDocument(
        source_file=str(payload.get("source_file") or ""),
        doc_type=str(payload.get("doc_type") or ""),
        language=payload.get("language"),
        product_name=payload.get("product_name"),
        cycle_stage=payload.get("cycle_stage"),
        artifact_refs=ArtifactReference(
            ocr_path=refs.get("ocr_path"),
            structured_path=refs.get("structured_path"),
            semantic_path=refs.get("semantic_path"),
        ),
        segments=[_segment_from_dict(item) for item in payload.get("segments") or []],
    )


def _segment_from_dict(payload: dict[str, Any]) -> ParsedSegment:
    return ParsedSegment(
        text=str(payload.get("text") or ""),
        locator=str(payload.get("locator") or "unknown"),
        cell_range=payload.get("cell_range"),
        title_path=payload.get("title_path"),
        section_title=payload.get("section_title"),
        content_type=payload.get("content_type"),
        block_type=payload.get("block_type"),
        source_kind=payload.get("source_kind"),
        evidence_level=payload.get("evidence_level"),
        semantic_tags=list(payload.get("semantic_tags") or []),
        entities=list(payload.get("entities") or []),
        table_headers=list(payload.get("table_headers") or []),
        artifact_path=payload.get("artifact_path"),
        ocr_blocks=list(payload.get("ocr_blocks") or []),
        flowchart=_flowchart_from_dict(payload.get("flowchart")),
    )


def _flowchart_to_dict(flowchart: FlowchartGraph | None) -> dict[str, Any] | None:
    return flowchart.to_dict() if flowchart is not None else None


def _flowchart_from_dict(payload: dict[str, Any] | None) -> FlowchartGraph | None:
    if not payload:
        return None
    return FlowchartGraph(
        nodes=[
            FlowchartNode(
                node_id=str(item.get("node_id") or ""),
                text=str(item.get("text") or ""),
                x=int(item.get("x") or 0),
                y=int(item.get("y") or 0),
                bbox=dict(item.get("bbox") or {}),
                lane=str(item.get("lane") or ""),
                col_header=str(item.get("col_header") or ""),
            )
            for item in payload.get("nodes") or []
        ],
        edges=[
            FlowchartEdge(
                source_id=str(item.get("source_id") or ""),
                target_id=str(item.get("target_id") or ""),
                source_text=str(item.get("source_text") or ""),
                target_text=str(item.get("target_text") or ""),
                source_lane=str(item.get("source_lane") or ""),
                target_lane=str(item.get("target_lane") or ""),
            )
            for item in payload.get("edges") or []
        ],
    )