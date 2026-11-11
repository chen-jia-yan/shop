# 评测样本：2026-10-30 LAS HK 回归（真实数据）

- 来源：测试平台报告 `Nov-06 LAS-HK-Regression-Test`（51 个用例，成功 11，失败 40；执行机 HK_Regression / RGT_AVD_11；开始 2026-10-30 21:38:45，耗时 02h31m53s）。
- `raw_logs.md`：报告中每个用例“展开”后的日志原文（汇总中没有第 21 条；第 18 条含两段日志，均为成功）。
- `labels.csv`：按 `references/root-cause-method.md` 逐条人工归因的结果（40 条失败）。

## 已验证

网页版“测试分析助手”已用这 51 条日志验证：40 条失败的分类与 `labels.csv` **全部一致**（环境 27、测试数据 1、脚本 4、需人工判断 8），No.25 被标为“环境中断边界”，No.31 识别出 2 个残留的 Service Fee 窗口，No.7 识别出通过用例 No.15 中的同样报错。

## Python 版评测（待在公司电脑上运行）

Python 版 `classify_rules.py` 的同等逻辑尚未在真实环境中运行过。运行方法：

1. 把 `raw_logs.md` 转成 `failures.json`（`--format normalized`，见 `references/data-contract.md` 1.3 节）：
   每个失败用例一条，`case_id` 用 `No.<编号>`，日志原文放进 `error_message`；
   另外加上 `execution_index`（执行序号，含成功用例，No.N 去掉缺失的第 21 条后的顺序）和顶层 `total_cases: 50`。
   注意：汇总文件里的换行是复制时折行产生的，下一行以 `_` 或 `\` 开头时应直接拼接，否则用空格拼接。
2. `python scripts/classify_rules.py --failures failures.json --rules config/rules.yaml --out classified.json`
3. `python evals/eval_classify.py --classified classified.json --labels evals/las_hk_20261030/labels.csv`
