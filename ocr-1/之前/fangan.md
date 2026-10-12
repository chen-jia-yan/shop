1. retriever.py： `_merge_candidates` 整個方法（L261–317）

```python
def _merge_candidates(self, query: str, lexical_candidates: list[ScoredChunk], source_file_hint: str | None = None) -> list[ScoredChunk]:
    if not lexical_candidates:
        self.last_debug["vector_status"] = "vector_fallback_no_lexical"
    merged: dict[str, ScoredChunk] = {}
    lexical_scores = [candidate.score for candidate in lexical_candidates]
    lexical_max = max(lexical_scores) if lexical_scores else 0.0
    lexical_min = min(lexical_scores) if lexical_scores else 0.0
    for candidate in lexical_candidates:
        chunk_id = candidate.chunk.metadata.get("chunk_id")
        lexical_norm = self._normalize_score(candidate.score, lexical_min, lexical_max)
        merged[chunk_id] = ScoredChunk(
            score=lexical_norm,
            term_coverage=candidate.term_coverage,
            chunk=candidate.chunk,
            retrieval_sources=("bm25",),
            lexical_score=candidate.score,
            vector_score=0.0,
        )

    vector_candidates = self._vector_candidates(query)
    vector_scores = [candidate.score for candidate in vector_candidates]
    vector_max = max(vector_scores) if vector_scores else 0.0
    vector_min = min(vector_scores) if vector_scores else 0.0
    for candidate in vector_candidates:
        chunk_id = candidate.chunk.metadata.get("chunk_id")
        vector_norm = self._normalize_score(candidate.score, vector_min, vector_max)
        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = ScoredChunk(
                score=vector_norm,
                # 向量獨有候選此前 term_coverage 恆為 0(隨後被兜底成 0.01), 門禁必拒；
                # 這裡補算真實內容詞覆蓋率, 和 BM25 側用同一把尺
                term_coverage=candidate.term_coverage or self._content_coverage(query, candidate.chunk.normalized),
                chunk=candidate.chunk,
                retrieval_sources=("vector",),
                lexical_score=0.0,
                vector_score=candidate.vector_score,
            )
            continue
        merged[chunk_id] = ScoredChunk(
            score=(existing.score * self.config.hybrid_bm25_weight) + (vector_norm * self.config.hybrid_vector_weight),
            term_coverage=max(existing.term_coverage, candidate.term_coverage),
            chunk=existing.chunk,
            retrieval_sources=tuple(sorted(set(existing.retrieval_sources + candidate.retrieval_sources))),
            lexical_score=existing.lexical_score,
            vector_score=candidate.vector_score,
        )

    # 歸一化分數處於 0–1 區間, 映射回 0–5 以兼容現有 min_score 閾值
    SCALE_FACTOR = 5.0
    for item in merged.values():
        item.score *= SCALE_FACTOR
        if item.term_coverage <= 0:
            item.term_coverage = 0.01
        if source_file_hint and self._chunk_matches_source_hint(item.chunk.metadata, source_file_hint):
            item.score += 0.35
            item.term_coverage = max(item.term_coverage, 0.35)
    return sorted(merged.values(), key=lambda item: item.score * max(item.term_coverage, 0.05), reverse=True)




2. retriever.py： `_vector_candidates` 整個方法（L375–422）

```python
def _vector_candidates(self, query: str) -> list[ScoredChunk]:
    if self._embedding_client is None:
        self.last_debug["vector_status"] = "embedding_client_unavailable"
        return []
    query_embedding = self._embedding_client.embed_texts([query])[0]
    self.last_debug["embedding_query_vector_dim"] = len(query_embedding)
    self.last_debug["embedding_query_vector_preview"] = query_embedding[:8]
    if isinstance(self.store, LocalKnowledgeStore):
        chunks = self.store.load()
        candidates: list[ScoredChunk] = []
        lexical = score_chunks(query, chunks, top_k=max(self.config.rerank_top_n, self.config.top_k))
        lexical_map = {item.chunk.metadata.get("chunk_id"): item.term_coverage for item in lexical}
        for chunk in chunks:
            if not chunk.embedding:
                continue
            similarity = cosine_similarity(query_embedding, chunk.embedding)
            if similarity <= 0:
                continue
            candidates.append(
                ScoredChunk(
                    score=similarity * self.config.hybrid_vector_weight,
                    term_coverage=lexical_map.get(chunk.metadata.get("chunk_id"), 0.0),
                    chunk=chunk,
                    retrieval_sources=("vector",),
                    lexical_score=0.0,
                    vector_score=similarity,
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        self.last_debug["vector_status"] = "ok" if candidates else "no_positive_similarity"
        self.last_debug["vector_candidates"] = len(candidates[: self.config.rerank_top_n])
        self.last_debug["top_vector_candidates"] = [
            {
                "chunk_id": item.chunk.metadata.get("chunk_id"),
                "vector_score": item.vector_score,
                "score": item.score,
                "term_coverage": item.term_coverage,
            }
            for item in candidates[: min(5, len(candidates), self.config.rerank_top_n)]
        ]
        return candidates[: self.config.rerank_top_n]
    if hasattr(self.store, "vector_search"):
        results = self.store.vector_search(query=query, embedding=query_embedding, top_k=self.config.rerank_top_n)
        self.last_debug["vector_status"] = "ok" if results else "empty_remote_vector_result"
        self.last_debug["vector_candidates"] = len(results)
        return results
    self.last_debug["vector_status"] = "store_without_vector_search"
    return []


3.retriever.py： helper 方法
_content_coverage（L253–259）
    @staticmethod
def _content_coverage(query: str, normalized_content: str) -> float:
    """內容詞覆蓋率(不帶 idf 權重的簡版):給向量召回的候選補一把和 BM25 側相同的尺。"""
    terms, _ = content_terms(query)
    terms = [t for t in dict.fromkeys(terms) if len(t) >= 2]
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in normalized_content) / len(terms)

_chunk_matches_source_hint（L349–357）
@staticmethod
def _chunk_matches_source_hint(metadata: dict[str, object], source_file_hint: str) -> bool:
    source_file = str(metadata.get("source_file") or "")
    if not source_file:
        return False
    normalized_source = source_file.lower()
    normalized_hint = source_file_hint.lower()
    base_hint = normalized_hint.rsplit(".", 1)[0]
    return normalized_source == normalized_hint or normalized_source.rsplit(".", 1)[0] == base_hint

_normalize_score（L369–373）
@staticmethod
def _normalize_score(value: float, min_value: float, max_value: float) -> float:
    if max_value <= min_value:
        return 1.0 if value > 0 else 0.0
    return (value - min_value) / (max_value - min_value)



4. retriever.py ： search() 方法裡「 收集詞法候選 → 合併 → 重排序 → gate → 截斷 top_k 」（L71–193，完整）

```python
def search(self, query: str, top_k: int | None = None, alternate_queries: list[str] | None = None, query_intent: str = "lookup") -> list[SearchHit]:
    limit = top_k or self.config.top_k
    alternate_queries = [item for item in (alternate_queries or []) if item and item.strip() and item.strip() != query.strip()]
    min_coverage = self.config.coverage_threshold_for_intent(query, query_intent=query_intent)
    source_file_hint = self._detect_source_file_hint(query)
    primary_lexical_candidates = self._collect_lexical_candidates([query], limit)
    alternate_coverage_by_chunk: dict[str, float] = {}
    if alternate_queries:
        for candidate in self._collect_lexical_candidates(alternate_queries, limit):
            chunk_id = candidate.chunk.metadata.get("chunk_id")
            alternate_coverage_by_chunk[chunk_id] = max(alternate_coverage_by_chunk.get(chunk_id, 0.0), candidate.term_coverage)
    self.last_debug = {
        "query": query,
        "query_for_retrieval": query,
        "alternate_queries": alternate_queries,
        "query_intent": query_intent,
        "source_file_hint": source_file_hint,
        "hybrid_bm25_weight": self.config.hybrid_bm25_weight,
        "hybrid_vector_weight": self.config.hybrid_vector_weight,
        "embedding_client_enabled": self._embedding_client is not None,
        "reranker_type": self._settings.reranker_type,
    }
    if isinstance(self._reranker, CrossEncoderReranker):
        self.last_debug["reranker_backend"] = self._reranker.backend
    exact_hits = self._exact_match_hits(query, limit, query_intent=query_intent)
    if exact_hits:
        self.last_rejected = []
        self.last_gate_reasons = []
        self.last_debug.update(
            {
                "exact_match": True,
                "lexical_candidates": 0,
                "vector_candidates": 0,
                "merged_candidates": len(exact_hits),
                "accepted_hits": len(exact_hits),
                "retrieval_sources": ["exact"],
            }
        )
        return exact_hits
    lexical_queries = [query, *alternate_queries]
    if source_file_hint:
        lexical_queries.extend(self._build_source_file_queries(source_file_hint))
    lexical_candidates = self._collect_lexical_candidates(lexical_queries, limit)

    merged = self._merge_candidates(query, lexical_candidates, source_file_hint=source_file_hint)
    reranked = self._reranker.rerank(query, merged, top_k=max(limit, self.config.rerank_top_n))
    self.last_debug["lexical_candidates"] = len(lexical_candidates)
    self.last_debug["merged_candidates"] = len(merged)
    self.last_debug["top_candidates"] = [
        {
            "chunk_id": item.chunk.metadata.get("chunk_id"),
            "score": item.score,
            "lexical_score": item.lexical_score,
            "vector_score": item.vector_score,
            "term_coverage": item.term_coverage,
            "retrieval_sources": list(item.retrieval_sources),
        }
        for item in merged[: min(5, len(merged))]
    ]

    accepted: list[SearchHit] = []
    rejected: list[SearchHit] = []
    rescued_count = 0
    self.last_gate_reasons = []
    for item in reranked:
        hit = SearchHit(
            content=item.chunk.content,
            metadata=ChunkMetadata.from_dict(item.chunk.metadata),
            score=item.score,
            rerank_score=item.rerank_score,
            term_coverage=item.term_coverage,
            source_consistency=item.source_consistency,
            retrieval_sources=list(item.retrieval_sources),
        )
        # Gate is temporarily bypassed so we can observe raw retrieval behavior first.
        # Keep a success-shaped decision object only for debug-field compatibility.
        decision = self._reranker.gate(
            query,
            item,
            rerank_threshold=self.config.rerank_score_threshold,
            coverage_threshold=min_coverage if query_intent == "process" else max(min_coverage,
            self.config.evidence_coverage_threshold),
            query_intent=query_intent,
        )
        hit.metadata.source_consistency = decision.source_consistency
        effective_coverage = max(item.term_coverage, alternate_coverage_by_chunk.get(hit.metadata.chunk_id, 0.0))
        # 向量救援(預設關, KB_VECTOR_RESCUE)：純向量強命中中允許繞過覆蓋率門禁，
        # 用於"文檔通篇不含查詢詞、僅語義相關"的硬案例
        vector_rescued = (
            VECTOR_RESCUE_ENABLED
            and "vector" in item.retrieval_sources
            and item.vector_score >= VECTOR_RESCUE_MIN_SCORE
            and effective_coverage < min_coverage
        )
        if item.score >= self.config.min_score and (effective_coverage >= min_coverage or vector_rescued):
            hit.term_coverage = effective_coverage
            if vector_rescued:
                hit.retrieval_sources = [*hit.retrieval_sources, "vector_rescue"]
                rescued_count += 1
            accepted.append(hit)
        else:
            rejected.append(hit)
            self.last_gate_reasons.extend(decision.reasons)

    self.last_rejected = rejected[:limit]
    self.last_debug.update(
        {
            "accepted_hits": len(accepted),
            "rejected_hits": len(rejected),
            "vector_rescued": rescued_count,
            "top_rejected_rerank": max((hit.rerank_score for hit in rejected), default=0.0),
            "top_rejected_coverage": max((hit.term_coverage for hit in rejected), default=0.0),
            "retrieval_sources": sorted({source for hit in accepted + rejected for source in hit.retrieval_sources}),
            "gate_reasons": sorted(set(self.last_gate_reasons)),
        }
    )
    if not accepted and rejected:
        logger.info(
            "query=%r rejected by evidence gate; top rerank=%.3f top coverage=%.3f",
            query,
            max(hit.rerank_score for hit in rejected),
            max(hit.term_coverage for hit in rejected),
        )
    return accepted[:limit]



5. reranker.py : HeuristicReranker.rerank 整個方法（L42–87）
def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
    normalized_query = normalize(query)
    query_terms, _ = content_terms(query)
    query_ids = {normalize(token) for token in _ID_PATTERN.findall(query)}
    reranked: list[ScoredChunk] = []
    for candidate in candidates:
        metadata = candidate.chunk.metadata
        normalized_content = candidate.chunk.normalized
        rerank_score = candidate.score * max(candidate.term_coverage, 0.01)
        rerank_score += candidate.lexical_score * 0.15
        rerank_score += candidate.vector_score * 0.15

        title = normalize((metadata.get("title_path") or "") + " " + (metadata.get("section_title") or ""))
        if title and any(term and term in title for term in query_terms):
            rerank_score += TITLE_MATCH_BOOST

        if metadata.get("content_type") == "table":
            rerank_score += TABLE_MATCH_BOOST

        if metadata.get("source_kind") == "ocr":
            rerank_score -= OCR_SCORE_PENALTY

        exact_entity_hits = 0
        for token in query_ids:
            if token in normalized_content:
                exact_entity_hits += 1
                rerank_score += EXACT_ID_BOOST
        if exact_entity_hits:
            rerank_score += ENTITY_MATCH_BOOST * exact_entity_hits

        source_consistency = _source_consistency_score(query_terms, metadata, normalized_content)
        reranked.append(
            ScoredChunk(
                score=candidate.score,
                term_coverage=candidate.term_coverage,
                chunk=candidate.chunk,
                rerank_score=rerank_score,
                source_consistency=source_consistency,
                retrieval_sources=candidate.retrieval_sources,
                lexical_score=candidate.lexical_score,
                vector_score=candidate.vector_score,
            )
        )

    reranked.sort(key=lambda item: item.rerank_score, reverse=True)
    return reranked[:top_k]

————————————————————————————

6. reranker.py : gate 整個方法（L89–122）
def gate(self, query: str, candidate: ScoredChunk, rerank_threshold: float, coverage_threshold: float, query_intent: str = "lookup") -> GateDecision:
    reasons: list[str] = []
    accepted = True
    effective_coverage_threshold = coverage_threshold
    effective_source_threshold = SOURCE_CONSISTENCY_THRESHOLD

    if query_intent == "explain":
        effective_coverage_threshold = min(coverage_threshold, 0.30)
        effective_source_threshold = min(SOURCE_CONSISTENCY_THRESHOLD, 0.45)
    elif query_intent == "process":
        effective_coverage_threshold = min(coverage_threshold, 0.20)
        effective_source_threshold = min(SOURCE_CONSISTENCY_THRESHOLD, 0.35)
        rerank_threshold = min(rerank_threshold, 0.18)

    if candidate.rerank_score < rerank_threshold:
        accepted = False
        reasons.append("rerank score below threshold")

    if candidate.term_coverage < effective_coverage_threshold:
        accepted = False
        reasons.append("evidence coverage below threshold")

    if candidate.source_consistency < effective_source_threshold:
        accepted = False
        reasons.append("source consistency below threshold")

    query_ids = {normalize(token) for token in _ID_PATTERN.findall(query)}
    if query_ids and not any(token in candidate.chunk.normalized for token in query_ids):
        accepted = False
        reasons.append("exact id not matched")

    return GateDecision(
        accepted=accepted,
        rerank_score=candidate.rerank_score,
        evidence_coverage=candidate.term_coverage,
        source_consistency=candidate.source_consistency,
        reasons=reasons,
    )



7. reranker.py：模組頂部相關常量/正則（L1–23）
from __future__ import annotations

import math
import re
from dataclasses import dataclass
import logging
from typing import Protocol

from openai import OpenAI

from ..config import (
    ENTITY_MATCH_BOOST,
    EXACT_ID_BOOST,
    OCR_SCORE_PENALTY,
    SOURCE_CONSISTENCY_THRESHOLD,
    TABLE_MATCH_BOOST,
    TITLE_MATCH_BOOST,
)
from ..indexing.store import ScoredChunk
from .text_tokenizer import content_terms, normalize

_ID_PATTERN = re.compile(r"[A-Za-zA-Z a-z 0-90-9 ]{4,}")
logger = logging.getLogger(__name__)

————————————————————————————

8. store.py：ScoredChunk 的類定義（L56–65，含前置 @dataclass(slots=True)）
@dataclass(slots=True)
class ScoredChunk:
    score: float
    term_coverage: float
    chunk: _StoredChunk
    rerank_score: float = 0.0
    source_consistency: float = 0.0
    retrieval_sources: tuple[str, ...] = ()
    lexical_score: float = 0.0
    vector_score: float = 0.0

————————————————————————————

9. config.py：檢索相關的常量塊（L26–57） + KB_TOP_K 預設值（L159）
# ==========================================
# Retrieval and reranking
# ==========================================
#  bigram 模式（中/英）：負樣本上界 0.063, 正樣本下界 0.178
#  內容詞模式（日語）  ：負樣本上界 0.348, 正樣本下界 0.346（重疊，見 README 說明）
#  換語料後必須重新標定，不能直接沿用。
MIN_SCORE = float(os.getenv("KB_MIN_SCORE", "1.0"))
MIN_TERM_COVERAGE = float(os.getenv("KB_MIN_TERM_COVERAGE", "0.12"))
MIN_TERM_COVERAGE_CONTENT = float(os.getenv("KB_MIN_TERM_COVERAGE_CONTENT", "0.40"))
COVERAGE_PARTIAL = os.getenv("KB_COVERAGE_PARTIAL", "1").strip().lower() not in ("0", "false", "no", "off", "")
VECTOR_RESCUE_ENABLED = os.getenv("KB_VECTOR_RESCUE", "0").strip().lower() not in ("0", "false", "no", "off", "")
VECTOR_RESCUE_MIN_SCORE = float(os.getenv("KB_VECTOR_RESCUE_MIN_SCORE", "0.80"))

# df/N 停用詞 超過該比例、且絕對篇數超過 MIN_STOPWORD_DF 的詞，視為本語料的停用詞，不計入覆蓋率。
MAX_DF_RATIO = float(os.getenv("KB_MAX_DF_RATIO", "0.1"))
MIN_STOPWORD_DF = int(os.getenv("KB_MIN_STOPWORD_DF", "20"))

# 整句原文命中的加權。
PHRASE_BOOST = float(os.getenv("KB_PHRASE_BOOST", "0.25"))
HYBRID_VECTOR_WEIGHT = float(os.getenv("KB_HYBRID_VECTOR_WEIGHT", "0.60"))
HYBRID_BM25_WEIGHT = float(os.getenv("KB_HYBRID_BM25_WEIGHT", "0.40"))
RERANK_TOP_N = int(os.getenv("KB_RERANK_TOP_N", "20"))

RERANK_SCORE_THRESHOLD = float(os.getenv("KB_RERANK_SCORE_THRESHOLD", "0.72"))
SOURCE_CONSISTENCY_THRESHOLD = float(os.getenv("KB_SOURCE_CONSISTENCY_THRESHOLD", "0.60"))
EVIDENCE_COVERAGE_THRESHOLD = float(os.getenv("KB_EVIDENCE_COVERAGE_THRESHOLD", "0.30"))
RERANKER_TYPE = (os.getenv("KB_RERANKER_TYPE", "heuristic")).strip().lower()
CROSS_ENCODER_SCORE_THRESHOLD = float(os.getenv("KB_CROSS_ENCODER_SCORE_THRESHOLD", "0.80"))
OCR_SCORE_PENALTY = float(os.getenv("KB_OCR_SCORE_PENALTY", "0.08"))
TABLE_MATCH_BOOST = float(os.getenv("KB_TABLE_MATCH_BOOST", "0.10"))
TITLE_MATCH_BOOST = float(os.getenv("KB_TITLE_MATCH_BOOST", "0.12"))
ENTITY_MATCH_BOOST = float(os.getenv("KB_ENTITY_MATCH_BOOST", "0.18"))
EXACT_ID_BOOST = float(os.getenv("KB_EXACT_ID_BOOST", "0.25"))

以及 top_k 預設值（L159）：
    top_k=int(os.getenv("KB_TOP_K", "5")),

