# 评测样本：2026-10-30 LAS HK 回归（真实数据）

- 来源：测试平台报告 `Nov-06 LAS-HK-Regression-Test`（51 个用例，成功 11，失败 40；执行机 HK_Regression / RGT_AVD_11；开始 2026-10-30 21:38:45，耗时 02h31m53s）。
- `raw_logs.md`：报告中每个用例“展开”后的日志原文（汇总中没有第 21 条；第 18 条含两段日志，均为成功）。
- `labels.csv`：按 `references/root-cause-method.md` 逐条人工归因的结果（40 条失败）。

## 已验证

网页版“测试分析助手”已用这 51 条日志验证：40 条失败的分类与 `labels.csv` **全部一致**（环境 27、测试数据 1、脚本 4、需人工判断 8），No.25 被标为“环境中断边界”，No.31 识别出 2 个残留的 Service Fee 窗口，No.7 识别出通过用例 No.15 中的同样报错。

## Python 版（skill）评测（待在公司电脑上运行）

skill 的分类现在由 `scripts/ta_engine.py` 完成，它是页面 `engine.js` 的 Python 版。同一份日志（`evals/consistency/las_hk_20261030_raw.txt`）和页面算出的标准答案（`evals/consistency/expected.json`）已经放好，直接运行：

```bash
python evals/check_consistency.py
```

输出“一致”就说明 skill 与页面结果完全相同（也就与 `labels.csv` 一致）。Python 在开发环境中无法运行，这一步还没有实际跑过；不一致时请把输出发给维护人。
