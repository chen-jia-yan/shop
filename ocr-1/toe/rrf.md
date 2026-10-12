【任务：把 coverage 在 合并/重排序/门禁 三关统一降级 + RRF，并逐关 trace 验证（plan mode 给 diff，先别落地，不碰数据）】

红线：只出 plan mode 方案 + diff + trace，不落地、不改配置、不写删索引、不跑评估。feature flag 可回退。

背景：已确认 coverage（bigram）对长日文/编号查询天然≈0，却被当乘数用在合并排序(317行)和重排序(42行)、当阈值用在门禁(coverage≥0.12 + rerank_score≥0.72)。只改合并排序为 RRF 不够——#12 装 RRF 后重排序分仍≈0.10 < 门禁 0.72，照样被拒。

要协调改三关（都用 feature flag 包起来）：
1. 合并（_merge_candidates）：按你已设计的 RRF 作主排序，coverage 仅作 tiebreaker，不再做乘数。
2. 重排序（HeuristicReranker.rerank）：rerank_score 不再乘 coverage；改成以 RRF/rank 融合分为主 + vector_score/lexical_score 加权 + 现有 title/table/ID 加分；coverage 最多做小加分，不做乘数。
3. 门禁（gate）：
   - coverage 阈值不再硬否决"RRF 靠前 / 向量 rank 高"的候选（coverage 降为软信号）；
   - 复核 rerank_score≥0.72、source_consistency≥0.50、MIN_SCORE≥1.0 这几个阈值在新分数体系下是否会误杀，必要时一并调整；
   - ID 精确命中(如 D3010)那条加分/门禁保留——它对 #7 有利。
   - VECTOR_RESCUE 不是这里的解（#7/#8 向量弱、#12 向量 0.677<0.80），别指望它。

验证（关键，必须做）：
A. 逐关 trace #12 和 #7：装上改动后，列出它们在 合并→重排序→门禁→截断 每一关的分数和去留，证明它们**最终进了 accepted[:20]**。只 trace 到合并排名不算数。
B. 回归：列出当前能通过的那几题，确认改动后它们**不被新规则挤掉/误杀**（召回别为了救 5 题牺牲原本对的）。

给我：三关 diff + A 的逐关 trace 表 + B 的回归清单。我 review 完再落地。
```