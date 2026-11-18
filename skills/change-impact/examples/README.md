# 示例：运行一遍完整流程

> 示例样本均为虚构产品，仅用于演示。脚本在当前环境**还没实际跑过**，第一次运行请对照下面“预期结果”核对。

```bash
cd change-impact
python scripts/diff_docs.py examples/sample_terms_v2.3.md examples/sample_terms_v3.0.md -o work/changes.json \
  --doc-name "示例重大疾病保险条款" --old-label "v2.3" --new-label "v3.0" --source "产品条款修订"
  # 有生效日期时加 --effective-date YYYY-MM-DD

python scripts/find_refs.py work/changes.json --corpus examples/kb_sample.jsonl -o work/refs.json \
  --scope-term "示例重大疾病"

python scripts/score.py work/changes.json --refs work/refs.json -o work/scored.json        # 初筛
# 核对 changes.json 中的编号，修改 examples/notes.json 后：
python scripts/score.py work/changes.json --refs work/refs.json --notes examples/notes.json -o work/scored.json
python scripts/build_report.py work/scored.json --notes examples/notes.json --out-dir out/ --render
```

## 预期结果（用于核对脚本是否正常）

| 旧版 → 新版 | 应识别为 | 自动级别（未给生效日） | 说明 |
|---|---|---|---|
| 标题 v2.3 → v3.0 | 修改 | 轻微 | notes 中忽略 |
| 投保年龄 60 → 65 周岁 | 修改·投保规则 | 一般（下限） | 投保须知、系统校验规则 |
| 犹豫期 15 → 20 日 | 修改·重要期间 | 较大（下限） | 话术、回访脚本含旧值 |
| 等待期 90 → 30 天 | 修改·保险责任 / 重要期间 | 较大（下限）→ 人工升为重大 | FAQ、说明书、话术含旧值 |
| 轻症给付 20% → 30% | 修改·保险责任 | 较大（下限） | 说明书、FAQ 含旧值 |
| 新增中症疾病保险金 | 新增·保险责任 | 较大（下限） | |
| 责任免除删除第（六）项 | 修改·责任免除（删除整项） | 较大（下限） | 免责条款提示书含被删原文 |
| 事故通知“应当”→“可以” | 修改·理赔（义务放宽） | 一般 | 理赔操作指引含旧口径 |
| 核定时限 5 → 3 个工作日 | 修改·理赔 | 一般 | 理赔操作指引含旧值 |
| 理赔材料表适用情形增加中症 | 修改 | 轻微 | 建议人工看是否升级 |
| 宽限期条款仅编号顺延 | 措辞调整 | 轻微 | 列入附录一 |
| 职责条款增加客服部对客说明 | 修改·组织与职责 | 轻微 | |

受影响内容：应命中 KB-FAQ-0101、KB-FAQ-0102、KB-MAN-0210、KB-TIP-0033、KB-SCR-0405、KB-CLM-0120；
**不应命中** KB-FAQ-0309（另一款医疗险的“等待期 90 天”，被 `--scope-term` 排除）和 KB-POL-0007。
