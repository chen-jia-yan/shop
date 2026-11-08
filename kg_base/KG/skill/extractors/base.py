from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ChunkText:
    """一个 chunk 的正文（抽取器的输入单元）。"""
    chunk_id: str
    content: str
    source_file: str
    page_or_sheet: str = ""


@dataclass(slots=True)
class SubGraph:
    """抽取器的输出：一组节点和边（与 KG 同构）。"""
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)


class EntityExtractor(Protocol):
    """可插拔抽取器接口。规则版/LLM 版都实现它，runtime 不关心用的是哪种。"""
    name: str

    def extract(
        self,
        chunks: list[ChunkText],
        existing_labels: dict[str, str],  # label -> 已有实体 id
        source_doc_id: str,
    ) -> SubGraph: ...
