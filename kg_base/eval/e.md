目标：用新判官跑出新基线，校验判官是否稳定、是否与人工判断一致，并把新字段接进分析页面。
约束：不碰 Azure 索引、不重新入库；结果写新文件，不覆盖旧结果。

E1. 跑新基线：用日文 gold 集 + 确认版 key_points，开 KB_EVAL_JUDGE_V2 和 KB_EVAL_ATTRIBUTION，跑一次完整评估，结果存为 evals/results/baseline_v2_<日期>.json。

E2. 稳定性检查：同样配置再跑一次，对比两次结果：
- 每题每维分数差的绝对值，统计差为 0 / 1 / ≥2 的题数；
- risk_level 不一致的题；
- 列出差 ≥2 的题和两次的理由。
稳定的判官，绝大多数题分差应为 0。差 ≥2 的题要贴给我看。

E3. 人工校准表：随机抽 10 道题，生成 evals/human_calibration.md，每题列出问题、标准答案、必答要点、待评答案、判官的四维分数+理由、attribution 标注。留空栏位让我填"我认为的分数"。我填完后，写个小脚本统计判官与我的分差。

E4. 分析页面（evals/analysis.html）新增展示：
- badcase 抽屉里新增「必答要点核对」栏：每个要点显示 hit/partial/miss/wrong 和答案原话。
- 新增「来源可追溯」栏：每条结论按 SOURCE(绿) / DERIVED(橙) / UNSUPPORTED(红) / CONTRADICTED(深红) 着色，显示 chunk_id。
- 列表页新增 risk_level 列和筛选；顶部卡片新增"高风险题数"和"平均推断占比"。
- 字段缺失时该栏隐藏，兼容旧结果文件。
- 页面必须保持纯本地离线，不引入任何外部库或 CDN。

E5. 新旧对比说明：生成一份 evals/judge_v1_vs_v2.md，列出每题新旧四维分数，标出变化大的题，并写明"v2 分数不可与 v1 直接比较，今后以 baseline_v2 为基线"。

完成后停，把 E2 的稳定性统计和 E3 的校准表给我。