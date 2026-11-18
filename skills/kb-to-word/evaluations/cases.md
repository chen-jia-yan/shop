# 评测用例：知识生成 Word

分两部分：**A 脚本用例**（用自带示例验证渲染和质检）、**B 端到端用例**（接上 TAP 后验证 skill 的判断和写作）。

## A. 脚本用例

| # | 命令 | 预期 |
|---|---|---|
| A1 | `python scripts/render_docx.py examples/product_manual.json out/product.docx` | 成功；风格 classic；一级标题 7 个；生成目录；表 2 个、图 3 个（结构图、时间线、流程图）；【待补充】3 处 |
| A2 | `python scripts/render_docx.py examples/claims_guide.json out/claims.docx` | 成功；风格 minimal；无目录（toc=false）；表 1 个、图 2 个；【待补充】3 处 |
| A3 | `python scripts/render_docx.py examples/q3_analysis.json out/q3.docx` | 成功；风格 premium；目录；表 1 个、图 4 个；【请确认】1 处 |
| A4 | A1 加 `--style premium`、`--style minimal` 各生成一份 | 三份内容一致，只有封面、标题色、表头不同 |
| A5 | `python scripts/review_docx.py out/product.docx --doc-type product` | 通过（退出码 0）；说明中列出【待补充】3 处 |
| A6 | A5 加 `--final` | 不通过（退出码 1），原因是占位符未处理 |
| A7 | `python scripts/review_docx.py out/claims.docx --doc-type claims` | 通过 |
| A8 | 在 product_manual.json 某段加入“本产品保本稳赚，比存银行划算”后渲染并质检 | 不通过：收益承诺 2 处（保本、稳赚）、存款类比 1 处 |
| A9 | 删除 product_manual.json 中所有含“等待期”的内容后质检 | 不通过：缺少必备要素“等待期” |
| A10 | 把某个 table 的一行删掉一列后渲染 | 退出码 2，提示“第 N 个元素（表格）第 M 行有 X 列，表头是 Y 列” |
| A11 | 把某个元素的 type 改成 `diagram` | 退出码 2，提示未知类型 |

**打开 Word 时重点看：**
- [ ] 打开时没有“无法读取的内容”提示
- [ ] 封面单独一页，后面没有多出空白页
- [ ] 正文第一页页脚显示“第 1 页 / 共 N 页”
- [ ] 目录更新域后显示页码
- [ ] 图表中文正常显示（不是方块）
- [ ] 跨页表格每页都有表头

## B. 端到端用例（接上 TAP 后）

| # | 用户输入 | 关键检查点 |
|---|---|---|
| B1 | “把安康重疾整理成一份给客户的产品说明书” | 类型 product、对外；包含犹豫期/等待期/责任免除/风险提示；无内部信息；数字都有出处 |
| B2 | “给新人讲讲核保，做成培训材料” | 类型判断为 **training**（不是 underwriting）；有学习目标和自测题 |
| B3 | “写一份三季度个险经营分析，给领导看” | 风格 premium；第一章就是结论 + KPI；图表 caption 写结论 |
| B4 | “出一页纸说明一下理赔要带什么” | 1-2 页；无目录；以清单为主 |
| B5 | “帮我写一份客户方案”（没说客户情况） | 应询问客户家庭情况（最多 3 问并给默认）；不编造客户信息 |
| B6 | 主题在知识库中检索不到 | 告知未找到并建议换说法；不生成空壳文档 |
| B7 | 两份制度对同一时限说法不同（30 天 / 15 天） | 用更新时间新的；文中或交付说明提示冲突 |
| B8 | “客服热线是多少”只能靠推测 | 写【待补充】，绝不编造号码 |
| B9 | “帮我写个制度，越详细越好” | 分条写“第 X 条”；有适用范围、职责、生效；附版本记录和签批栏 |
| B10 | 质检出现“必须修改” | 回到撰写阶段修改后重新渲染，不直接交付 |
| B11 | 用户只问“等待期是多少天” | 不触发本 skill（交给 qa_advance） |
| B12 | 用户要“做成 PPT” | 不触发本 skill（交给 kb-to-ppt） |

**评分**：每条按六维评分（reference/quality-rubric.md），各项 ≥4 分为通过。
