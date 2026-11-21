# 示例：运行一遍完整流程

> 示例样本都是虚构产品，仅用于演示。脚本在当前环境**还没实际跑过**，第一次运行请对照下面的“预期结果”核对。

## 推荐：一键流程

```bash
cd change-impact
python scripts/run.py prepare --event examples/event.json --work work/
# 读 work/workpack.md，按 reference/methods.md 判断。
# 可以先参考 examples/judgments.json（编号以 work/judgments.template.json 为准，不一致时先核对再改）
cp examples/judgments.json work/judgments.json
python scripts/judgments.py check work/prior.json --refs work/refs.json --judgments work/judgments.json
python scripts/run.py finish --work work/ --out-dir out/ --notes examples/notes.json --render
```

处置后核验与经验入库：

```bash
python scripts/verify.py work/scored.json --corpus 修订后导出.jsonl --qa 回测结果.json -o work/verify.json
python scripts/build_report.py work/scored.json --notes examples/notes.json --out-dir out/ --verify work/verify.json --render
python scripts/experience.py add work/scored.json --judgments work/judgments.json --confirmed-by 确认人
```

`experience/cases.jsonl` 里的 5 条判例是**示例**，状态为 pending，默认不参与参考。想看效果可以 `experience.py find work/prior.json --include-pending`。正式使用前请清空或替换为真实、已确认的判例。

## 分步运行（排查问题时用）

```bash
python scripts/diff_docs.py examples/sample_terms_v2.3.md examples/sample_terms_v3.0.md -o work/changes.json \
  --doc-name "示例重大疾病保险条款" --old-label "v2.3" --new-label "v3.0" --source "产品条款修订"
python scripts/find_refs.py work/changes.json --corpus examples/kb_sample.jsonl -o work/refs.json --scope-term "示例重大疾病"
python scripts/score.py work/changes.json --refs work/refs.json -o work/prior.json                       # 初筛
python scripts/score.py work/changes.json --refs work/refs.json --judgments examples/judgments.json \
  --notes examples/notes.json -o work/scored.json
python scripts/build_report.py work/scored.json --notes examples/notes.json --out-dir out/ --render
```

不写判断、只用 notes 的 overrides（旧写法）也能出报告。这种情况下初筛为重大 / 较大的变更会全部列入待人工确认，报告标为“初稿”。

## 预期结果（用于核对脚本是否正常）

| 旧版 → 新版 | 应识别为 | 初筛级别（未给生效日） | 示例判断 |
|---|---|---|---|
| 标题 v2.3 → v3.0 | 修改 | 轻微 | 排除 |
| 投保年龄 60 → 65 周岁 | 修改·投保规则 | 一般（下限） | 一般，新契约 |
| 犹豫期 15 → 20 日 | 修改·重要期间 | 较大（下限） | 较大，新契约 |
| 等待期 90 → 30 天 | 修改·保险责任 / 重要期间 | 较大（下限） | **重大**，新契约（存量按原合同） |
| 轻症给付 20% → 30% | 修改·保险责任 | 较大（下限） | 较大，新契约 |
| 新增中症疾病保险金 | 新增·保险责任 | 较大（下限） | 较大 |
| 责任免除删除第（六）项 | 修改·责任免除 | 较大（下限） | 较大，新契约 |
| 事故通知“应当”→“可以” | 修改·理赔（义务放宽） | 一般 | 一般，存量口径待合规确认 |
| 核定时限 5 → 3 个工作日 | 修改·理赔 | 一般 | 一般，新旧统一执行 |
| 理赔材料表适用情形增加中症 | 修改 | 轻微 | 沿用初筛 |
| 宽限期条款仅编号顺延 | 措辞调整（应有“段落拆分 / 合并”或无提示） | 轻微 | 附录一 |
| 职责条款增加客服部对客说明 | 修改·组织与职责 | 轻微 | 沿用初筛 |

受影响内容和示例处置：

| 内容 | 示例判断 | 处置 |
|---|---|---|
| KB-FAQ-0101 投保篇 FAQ | 过时 | 生效日切换 |
| KB-FAQ-0102 保障篇 FAQ | 部分过时 | **新旧并列**（待人工确认） |
| KB-MAN-0210 产品说明书 | 过时 | 生效日切换 |
| KB-TIP-0033 免责条款提示书 | 过时 | 生效日切换 |
| KB-SCR-0405 销售话术 | 过时 | 生效日切换 |
| KB-CLM-0120 理赔操作指引 | 部分过时 | **新旧并列**（待人工确认，含【待补充】） |

**不应命中** KB-FAQ-0309（另一款医疗险的“等待期 90 天”，被 `scope_terms` 排除）和 KB-POL-0007。

示例没有生效日期，所以“生效日切换”的 4 篇内容会因为缺切换日列入待人工确认。在 event.json 的 `new.effective_date` 填上日期后，这几项就不再列入。
