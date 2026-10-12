【任务：只读导出检索相关源码给我看（只粘贴，禁止任何修改/格式化/重构/落地）】

红线：只把下面这些**当前真实源码**原样粘贴出来，一个字都不要改，不要"顺手优化"，不写删索引、不改配置、不跑任何东西。

请逐个贴出完整源码（标好文件名+行号区间）：

retriever.py：
1. `_merge_candidates` 整个方法（完整）
2. `_vector_candidates` 整个方法（完整）
3. `_normalize_score`、`_content_coverage`、`_chunk_matches_source_hint` 这几个 helper（完整）
4. `search()` 方法里：从"收集词法候选"开始，经过 合并 → 重排序 → gate → 截断 top_k 的那整段（完整，含变量名如 accepted/rejected/min_coverage/query_intent 等）

reranker.py：
5. `HeuristicReranker.rerank` 整个方法（完整）
6. `gate` 整个方法（完整）
7. 模块顶部相关常量/正则（如 `_ID_PATTERN`、normalize 等）

store.py：
8. `ScoredChunk` 的类定义（完整，含装饰器——是不是 @dataclass、frozen、slots、有哪些字段、默认值）

config.py：
9. 检索相关的常量块（名字+默认值：top_k、RERANK_TOP_N、HYBRID_*_WEIGHT、MIN_SCORE、MIN_TERM_COVERAGE*、RERANK_SCORE_THRESHOLD、EVIDENCE_COVERAGE_THRESHOLD、VECTOR_RESCUE_* 等）

全部原样贴出，不下任何修改。