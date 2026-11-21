---
name: change-impact
description: >
  对知识库中文档的新旧版本做变更影响分析：逐条找出改了什么，判断每处变更对谁、有多大影响，
  查出知识库里哪些内容因此过时（区分新契约和存量保单）、该替换 / 并列 / 切换 / 下线，逐句给出修订建议稿，
  交付可签批的 Word 分析报告和可分派跟踪的 Excel 处置跟踪表，处置完成后再核验是否改完、改对。
  文档提交审核时也可以自动触发，出具“审核前预分析”。品牌、字体、文字、先验口径全部来自共享配置 tap-config。
  当用户说“这个条款/制度/规则改了，影响有哪些”“新旧版对比一下”“这次修订要改哪些内容”“出一份变更影响分析”
  “监管新规出来了，我们哪些东西要跟着改”“知识库改完了，帮我核一下”时使用；用户只给了新版、让你自己找旧版也适用。
  不用于：只想看两段文字差在哪（直接回答）；单纯写一份新文档（kb-to-word）；检查一份文档本身是否合规（规范检查 skill）。
---

# 变更影响分析

回答四个问题，每个结论都要能追溯到原文：**改了什么、对谁有多大影响、知识库哪些内容要怎么改、谁在什么时候做**。

## 分工

| 谁 | 做什么 | 依据 |
|---|---|---|
| 脚本 | 比对、找候选、初筛打分、护栏检查、核验、渲染。这些工作是确定的、可复现的 | `tap-config/impact.json`（先验）、`rules.json` |
| 你（模型） | 读原文，判断每条变更的性质、级别、对谁生效，判断每篇候选内容是否过时、怎么处置，写修订建议稿 | **`reference/methods.md`**（方法）、参考判例 |
| 人 | 确认“待人工确认”清单，审核修订建议稿，按流程修改知识库 | 报告与跟踪表 |

配置里的类别、权重、下限只是**先验**，给你一个起点。配置没写到的情况，回到 methods.md 的四个问题去判断，不要因为“没有规则”就跳过。不能越过的线只有几条，见 **`reference/boundaries.md`**：只读、不编造、风险判断交给人确认。

**以后判断得更准，靠的是积累判例，不靠补规则**：确认过的判断用 `experience.py add` 入库，遇到相似变更时会自动作为参考出现。

```
① 明确范围 → ② 取得两个版本 → ③ prepare（比对 + 候选 + 初筛 + 判例 → 工作包）
→ ④ 补查（检索 / 语义 / 图谱）→ ⑤ 写 judgments.json → ⑥ check 自查
→ ⑦ finish（定级 + 报告 + 跟踪表 + 修订建议稿）→ ⑧ 质检交付
→ ⑨ 处置后 verify 核验 → ⑩ 经验入库
```

脚本在 `scripts/`，配置在 `../tap-config/`（找不到时设置环境变量 `TAP_CONFIG_HOME`）。所有命令都支持 `--config 额外配置.json`、`--font-cn` 等覆盖项。

---

## ① 明确范围

从用户的话里推断。**能推断的不问**，只问会明显改变结论的，一次最多 3 个：被修订的文档、新旧版本、生效日期、影响范围（产品名 / 制度名，作为 `scope_terms`）、读者（管理层 brief / 执行 full）。生效日期没给时，报告里标【待补充】。

## ② 取得两个版本

- 在 TAP 中按文档名查元数据，取新版和上一个**已生效**版本（查询方式见 `reference/impact-search.md`）。
- 支持 .docx / .md / .txt / .pdf / kb-to-word 内容 JSON。扫描件需要先 OCR。
- **拿不到旧版就不要凭记忆写旧内容**，明确告诉用户缺什么。

## ③ prepare：生成工作包

写 event.json（手工发起时 `trigger` 写 `manual`，格式见 `reference/auto-trigger.md`），然后：

```bash
python scripts/run.py prepare --event work/event.json --work work/
```

依次完成比对（`changes.json`）、找候选内容（`refs.json`）、初筛（`prior.json`）、找判例（`precedents.json`），生成：

- `work/workpack.md`：待判断清单，包括变更、复核提示、候选内容、参考判例和补查语句
- `work/judgments.template.json`：判断文件骨架

先看工作包开头的统计和“注意”：

- 变更数异常多：多半是格式差异或标题识别失败
- 有图片、公式或扫描页：这些内容没参与比对，要在报告里写明
- 复核提示：可能是段落拆分、同义改写或表格结构变化，读原文后确认

## ④ 补查（不要只信关键词）

关键词没匹配上，不等于没有影响。按工作包里的“建议补查”，再加上同义说法和客户的口语问法：

- 用 TAP Retrieval / qa_advance 检索，结果存成 JSON
- 有向量检索、知识图谱的，结果同样存成 JSON，每条加 `via`（`vector` / `graph`）

把这些结果追加到 event.json 的 `corpus`，重新 `prepare`。做法见 `reference/impact-search.md`，后续规划见 `reference/next-steps.md`。

## ⑤ 写 judgments.json（核心）

按 `reference/methods.md`，把模板填好另存为 `work/judgments.json`：

- **每条变更**：verdict（实质 / 措辞 / 并入 / 排除）、一句话事实、level、direction（对客户有利还是不利）、applies（新契约 / 存量 / 全部 / 内部）、reasoning（不改会出什么事）、evidence（原文引文）、confidence、actions
- **每篇候选内容**：读全文后判断 verdict（过时 / 部分过时 / 对存量仍有效 / 需复核 / 不受影响）、disposal（替换 / 并列 / 生效日切换 / 加注 / 下线 / 保持），逐句写修订建议稿
- **复核提示**：结论写进 `diff_review`
- **回测问题**：每条重大 / 较大变更写 1-2 个，写明 expect 和 reject
- **经验**：值得以后参考的写进 `lesson`

判断可以和初筛不一样，写清理由就行。比初筛低很多的，会自动列入待人工确认，这是正常的。

## ⑥ check：护栏自查

```bash
python scripts/judgments.py check work/prior.json --refs work/refs.json --judgments work/judgments.json
```

只检查通用护栏，不校验业务规则：引文能否在原文找到、修订稿有没有新增数字或日期、有没有合规禁用词、有没有越权字段、初筛为重大 / 较大的变更是否都判断了。**有 error 必须改**（退出码 2）。warning 和待人工确认的项目会写进报告。

## ⑦ finish：出报告

```bash
python scripts/run.py finish --work work/ --out-dir out/ --notes work/notes.json --render
# 发管理层：--variant brief
```

`notes.json` 可选，写报告补充信息：summary、notice、owners、department、audience 等。原来 notes 里的 `overrides` 写法仍然支持，但同一条变更以 judgments 为准。

输出：

- `<名称>.docx`：分析报告。有待人工确认项时标为“初稿”。自动触发时标为“审核前预分析”
- `<名称>_跟踪表.xlsx`：包括变更清单、处置跟踪、受影响内容（含处置方式）、修订建议、待人工确认
- `<名称>_修订建议.json`：逐篇“原文 → 建议改为”，状态为待审核
- `<名称>_报告内容.json` / `_跟踪表内容.json`：可以微调后用 kb-to-word / kb-to-excel 重新渲染
- `<名称>_质检报告.md`

报告结构（完整版）：

1. 结论摘要（含待人工确认清单）
2. 变更概览
3. 重点变更逐条分析：判断、理由、证据、比对复核、参考判例、与初筛的差异
4. 影响范围：受影响内容、处置方式、修订建议稿、补查语句
5. 处置计划
6. 合规与对客告知
7. 分析局限：未比对的内容、未补查的范围、低置信判断
8. 附录

## ⑧ 质检交付

`--render` 会自动跑 Word 质检。交付前按 `reference/quality-rubric.md` 自查，至少确认：

- [ ] 每条重大 / 较大变更都读过原文，判断写了理由和证据
- [ ] 存量保单的口径单独判断过，没有把对存量仍有效的内容直接改成新口径
- [ ] 修订建议稿没有新增事实，缺的信息写了【待补充】
- [ ] 复核提示都给了结论，未比对的内容在“分析局限”里写明
- [ ] 没有把被修订文档本身算进受影响内容
- [ ] 对外引用的结论已注明“以合规部确认为准”

交付说明（在对话里）：

```
✅ 已生成《xx产品条款》变更影响分析报告（初稿，待确认 4 项）与处置跟踪表
实质变更 9 项：重大 2、较大 3、一般 4；需处置内容 6 篇（替换 3、新旧并列 2、下线 1），修订建议 11 句
最需要关注：C04 等待期由 90 天调整为 30 天（重大，新契约适用，存量按原合同）……
待人工确认：C04 定级、KB-FAQ-0102 新旧并列口径……
与初筛不同：C08 初筛较大 → 判为一般（理由…）
分析局限：附件费率表为图片，未比对
```

## ⑨ 处置后核验

知识库按建议修改后，导出修订后的内容。重大 / 较大变更的回测问题交给 qa_advance 再问一遍，结果存成 JSON：

```bash
python scripts/verify.py work/scored.json --corpus 修订后导出.jsonl --qa 回测结果.json -o work/verify.json
python scripts/build_report.py work/scored.json --out-dir out/ --verify work/verify.json --render   # 核验结果写进跟踪表
```

核验内容：

- 逐篇销项：建议稿是否上线、原句是否撤下
- 回归扫描：全库是否还有新冒出来的旧口径
- 问答回测：新口径有没有出现，旧口径有没有残留

生效日切换的内容，未到切换日时记为“待核验”。

## ⑩ 经验入库

业务或合规负责人确认后：

```bash
python scripts/experience.py add work/scored.json --judgments work/judgments.json --confirmed-by 张三
python scripts/experience.py retire EXP-0003 --reason "监管口径调整，不再适用"   # 停用，不删除
```

没写 `--confirmed-by` 的判例记为 pending，不参与以后的参考。

## 写作要求

- **变化说明写事实，不写评价**：写“等待期由 90 天调整为 30 天”，不写“大幅优化”。
- **影响写到具体对象**：写“理赔 FAQ 第 2 问”“核心系统等待期参数”，不写“相关材料”。
- **处置写成可执行的动作**：动词 + 对象 + 时限。
- **不确定就说不确定**：缺什么、没查什么，写进“分析局限”。
