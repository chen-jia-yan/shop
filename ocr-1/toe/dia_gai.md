# RRF改造方案文档
拿到真代码了。读完我先纠正一个关键点——比我们之前以为的还好办，但 Copilot 之前的”改合并排序”方向其实没用对地方：

1. `gate()` 方法里那些 rerank 0.72 / source_consistency / exact-id 阈值，在 `search()` 里根本没生效——看 L227-247，`decision` 只拿来取 `source_consistency` 和 debug，真正的接受判断是那行内联 `if item.score >= min_score(1.0) and (coverage >= min_coverage or vector_rescued)`。所以真正的硬门禁只有两条：`score≥1.0` 和 `coverage≥min_coverage`。

2. `_merge_candidates` 最后那个排序是”摆设”——因为 `rerank()` 收到的是全部 merged 候选、会重新排序取 top-20。所以决定谁进 top-20 的是 `rerank_score` 公式，不是合并排序。而 `rerank_score = score × max(coverage,0.01) + …` 又把 coverage 当乘数——这才是把低 coverage 的正确 chunk 埋掉的真凶。

所以真正要动的是两处：`rerank_score` 公式 和 `search()` 的内联接受判断。合并里只需补算 RRF 分供 rerank 用。下面是干净代码，全部挂在 `KB_RRF_ENABLED` 开关下（默认关，可回退）。让 Copilot 照着整体替换，别自由发挥。

① `config.py` — 新增两个常量（放在检索常量块里，L446 附近）# RRF 混合排序（排名融合，取代 coverage 乘数）。默认关，可回退。
```python
RRF_ENABLED = os.getenv("KB_RRF_ENABLED", "0").strip().lower() not in ("0", "false", "no", "off", "")

RRF_K = int(os.getenv("KB_RRF_K", "60"))
```

② `store.py` — 给 `ScoredChunk` 加一个字段
```python
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
    rrf_score: float = 0.0          # ← 新增
```

③ `retriever.py`

(a) 在现有 `from ..config import (...)` 里加上 `RRF_ENABLED, RRF_K`（和 `VECTOR_RESCUE_ENABLED` 并列）。

(b) 整体替换 `_merge_candidates`：
```python
def _merge_candidates(self, query: str, lexical_candidates: list[ScoredChunk], source_file_hint: str | None = None) -> list[ScoredChunk]:

    if not lexical_candidates:
        self.last_debug["vector_status"] = "vector_fallback_no_lexical"

    merged: dict[str, ScoredChunk] = {}

    lexical_scores = [candidate.score for candidate in lexical_candidates]
    lexical_max = max(lexical_scores) if lexical_scores else 0.0
    lexical_min = min(lexical_scores) if lexical_scores else 0.0

    # 各通道排名（按分数降序，1 起），供 RRF 使用
    lexical_rank: dict[str, int] = {}
    for rank, cand in enumerate(sorted(lexical_candidates, key=lambda c: c.score, reverse=True), start=1):
        lexical_rank.setdefault(cand.chunk.metadata.get("chunk_id"), rank)

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

    vector_rank: dict[str, int] = {}
    for rank, cand in enumerate(sorted(vector_candidates, key=lambda c: c.score, reverse=True), start=1):
        vector_rank.setdefault(cand.chunk.metadata.get("chunk_id"), rank)

    for candidate in vector_candidates:
        chunk_id = candidate.chunk.metadata.get("chunk_id")
        vector_norm = self._normalize_score(candidate.score, vector_min, vector_max)
        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = ScoredChunk(
                score=vector_norm,
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

    SCALE_FACTOR = 5.0
    for chunk_id, item in merged.items():
        item.score *= SCALE_FACTOR
        if item.term_coverage <= 0:
            item.term_coverage = 0.01
        if source_file_hint and self._chunk_matches_source_hint(item.chunk.metadata, source_file_hint):
            item.score += 0.35
            item.term_coverage = max(item.term_coverage, 0.35)

        # RRF：按各通道排名融合，不含 coverage。缺某通道则该项计 0。
        rrf = 0.0
        if chunk_id in lexical_rank:
            rrf += 1.0 / (RRF_K + lexical_rank[chunk_id])
        if chunk_id in vector_rank:
            rrf += 1.0 / (RRF_K + vector_rank[chunk_id])
        item.rrf_score = rrf

    if RRF_ENABLED:
        return sorted(merged.values(), key=lambda item: (item.rrf_score, item.term_coverage), reverse=True)
    return sorted(merged.values(), key=lambda item: item.score * max(item.term_coverage, 0.05), reverse=True)
```

(c) 替换 `search()` 里的接受判断块（从 `vector_rescued = (` 到 `self.last_gate_reasons.extend(decision.reasons)`，即 L241-255）：
```python
        # 向量救援(預設關, KB_VECTOR_RESCUE)
        vector_rescued = (
            VECTOR_RESCUE_ENABLED
            and "vector" in item.retrieval_sources
            and item.vector_score >= VECTOR_RESCUE_MIN_SCORE
            and effective_coverage < min_coverage
        )
        if RRF_ENABLED:
            # RRF 模式：信任 RRF 排名 + top_k，不再用 coverage/score 做硬否決
            accept = True
        else:
            accept = item.score >= self.config.min_score and (effective_coverage >= min_coverage or vector_rescued)
        if accept:
            hit.term_coverage = effective_coverage
            if vector_rescued and not RRF_ENABLED:
                hit.retrieval_sources = [*hit.retrieval_sources, "vector_rescue"]
                rescued_count += 1
            accepted.append(hit)
        else:
            rejected.append(hit)
            self.last_gate_reasons.extend(decision.reasons)
```

④ `reranker.py`

(a) 在 `from ..config import (...)` 里加上 `RRF_ENABLED`。

(b) 整体替换 `rerank`：
```python
def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
    normalized_query = normalize(query)
    query_terms, _ = content_terms(query)
    query_ids = {normalize(token) for token in _ID_PATTERN.findall(query)}
    reranked: list[ScoredChunk] = []
    for candidate in candidates:
        metadata = candidate.chunk.metadata
        normalized_content = candidate.chunk.normalized
        if RRF_ENABLED:
            # 以 RRF 融合分為主（×100 讓下面的加分成為微調而非主宰），去掉 coverage 乘數
            rerank_score = candidate.rrf_score * 100.0
        else:
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
                rrf_score=candidate.rrf_score,     # ← 保留，别丢
            )
        )
    reranked.sort(key=lambda item: item.rerank_score, reverse=True)
    return reranked[:top_k]
```

## 怎么开 / 验证 / 回退：

- 开：设环境变量 `KB_RRF_ENABLED=1`，并建议 `KB_TOP_K=10`（给召回留点余量；fix 后正确 chunk 排名应大幅上升，但先留 headroom）。

- 回退：删掉 `KB_RRF_ENABLED` 即可，所有逻辑原样恢复。

- 验证（装完必跑，别信手算）：

 - B 召回：对 12 道 gold 题真跑，报每题”正确 chunk 是否进 top_k + 排第几”。

 - C 噪音：挑 3 题把返回的 top-k 列出来，人眼看有没有明显不相关的混进来——因为 RRF 模式取消了硬否决、会把 top_k 填满，这步是防”为救召回放进垃圾”的关键。

 - D 回归：原本能过的题，确认仍返回正确 chunk。

我做的两个设计决定，先跟你交代清楚（这是取舍，不是定论）：

1. RRF 模式下接受判断变成”全收，靠 RRF 排名 + top_k 定去留”——因为 `coverage≥min_coverage` 这道闸对日文天然失效，是它误杀了 #1/#6。代价是：不会再有”空检索”，但也可能对烂问题返回弱结果。靠 C 的噪音抽查来判断要不要再加一道轻量下限。

2. 没有塞任何”按题目凑的魔法阈值”（不像上一版把 0.72 砍成 0.15）。唯一的”参数”就是 RRF_K=60（标准值）和 top_k。

先让 Copilot 整体替换这 4 处 → `KB_RRF_ENABLED=1` 真跑 B/C/D → 把三张结果贴回来，我逐题看完再决定是否正式落地、要不要补那道轻量下限。
