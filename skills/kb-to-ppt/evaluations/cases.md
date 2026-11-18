# 评测用例：知识生成 PPT

## A. 脚本用例（自带示例）

| # | 命令 | 预期 |
|---|---|---|
| A1 | `python scripts/render_pptx.py examples/q3_review.json out/经营汇报.pptx` | 成功；尊享深色；16 页（含自动插入的目录页）；构建报告无“文字放不下” |
| A2 | `python scripts/render_pptx.py examples/product_training.json out/上市培训.pptx` | 成功；橙白活力；20 页；用到 statement、icon_grid、pyramid、venn、compare、stairs、funnel、cycle、layers、big_number、gauge、columns、bullets |
| A3 | A1 加 `--theme orange`、`--theme minimal`、`--theme warm` | 四份内容一致，封面、章节页、配色不同 |
| A4 | A1 加 `--no-animation` | 质检报告中“有动画 0 页” |
| A5 | `python scripts/review_pptx.py out/经营汇报.pptx` | 通过；说明中显示 16 页、有动画 16 页、有切换效果 16 页；提示第 15 页有【请确认】 |
| A6 | `python scripts/review_pptx.py out/上市培训.pptx --external` | 通过（“不与存款类比”属于否定说法，不判违规） |
| A7 | 把 q3_review.json 某页 layout 删掉 | 按数据自动选择版式，构建报告中显示所选版式 |
| A8 | 在某个 bullets 页放 12 条要点 | 自动拆成 2 页，第 2 页标题加“（续）” |
| A9 | 把某页标题改成“区域分析” | 构建报告提示“标题像话题而不是结论” |
| A10 | 把 chart 的 values 少写一个 | 退出码 2，提示数据个数与分类个数不一致 |
| A11 | process 写 7 步 | 退出码 2，提示改用 timeline |

### 用 PowerPoint 打开后逐项看

- [ ] 打开时没有“修复”提示
- [ ] 封面图标、章节页大号数字、右侧章节导航显示正常，当前章节高亮
- [ ] 每页内容在出现后自动依次入场（浮入/缩放/擦除），约 2.5 秒播完
- [ ] 章节页切换为“推入”，其余为“淡化”
- [ ] 图标清晰、镂空部分颜色和底色一致
- [ ] 原生图表可以右键“编辑数据”
- [ ] 底部进度条随页码前进
- [ ] 每页备注栏有讲稿
- [ ] 中文字体与构建报告里显示的字体一致（默认取 brand.json 候选链第一个）

## B. 端到端用例（接上 TAP 后）

| # | 用户输入 | 关键检查点 |
|---|---|---|
| B1 | “用三季度经营数据做个 15 分钟的管理层汇报” | 先给标题大纲；结论先行；12-14 页；结尾是决策事项 |
| B2 | “给代理人做一份安康重疾的上市培训” | training 结构；有合规底线页；有课后任务 |
| B3 | “做一份给客户的产品介绍” | 对外合规：犹豫期、等待期、责任免除、以合同条款为准；`--external` 通过 |
| B4 | “项目进展汇报” | gauge/timeline 标当前；风险有应对与责任人 |
| B5 | 知识库查不到某个数字 | 写【待补充】并在交付说明中列出页码，不编造 |
| B6 | 用户只要“改成暖色风格” | 只换 `--theme warm` 重新渲染，不改内容 |
| B7 | 用户只问一个数字 | 不触发本 skill |
