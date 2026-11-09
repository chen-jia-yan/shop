---
name: regression-triage-jira
description: 分析自动化回归测试的失败用例，按有证据的规则分成“重跑可过 / 弹窗干扰 / 脚本问题 / 环境问题 / 测试数据问题 / 产品缺陷 / 需人工判断”七类，按根因合并，查重后起草符合 ROTQA 格式的 Jira 单（Summary、Description、Environment、Priority、Components、Labels），生成审核表，审核通过后批量建单并上传截图。用于：回归跑完有失败用例、用户说“分析本次回归失败”“帮我把失败用例提 Jira”“看看这些 case 为什么挂了”“这个弹窗是哪来的”。
compatibility: 需要 Python 3.10+，可访问 Jira Cloud（REST API 或 Atlassian Rovo MCP），可读取本次回归的结果目录（Allure 结果、JUnit XML 或标准化 JSON）。
metadata:
  owner: IT QA team (Guangzhou)
  version: "1.0.0"
  jira-project: ROTQA
---

# 回归失败分诊与 Jira 起草

## 这个 Skill 做什么、不做什么

**做：**
1. 读取一次回归的全部失败用例（报错信息、堆栈、截图、弹窗证据、环境信息）。
2. 先自动重跑失败用例，再按 `references/taxonomy.md` 的规则分类。
3. 把同一根因的多个用例合并成一组，一组对应一张 Jira 单。
4. 在 Jira 中查重，已有未关闭的同类单就建议“追加评论”而不是新建。
5. 按 `references/jira-template.md` 起草每组的 Jira 内容。
6. 生成审核表，**由测试人员审核、修改、标记“通过”**。
7. 只对标记“通过”的行建单或追加评论，并上传截图。

**不做：**
- 不替人决定能否上线，不关闭、不转派、不修改已有 Jira 单的状态。
- 不连接生产环境，不读取生产数据。
- 不在没有证据的情况下给出根因结论。

## 铁律（每一步都必须遵守）

1. **结论必须有证据。** 每个分类、每个根因描述都要引用证据原文：异常类型、报错行、弹窗文字、重跑结果、数据核查结果，引用时写明证据编号（如 `E3`）。
2. **证据不足就说不知道。** 规则没命中、证据互相矛盾、截图看不清，一律归为 `NEEDS_HUMAN`，并写明还缺什么信息。不得为了“分完类”而猜测。
3. **规则结论优先于 AI 判断。** `classify_rules.py` 给出 `status: confirmed` 的分类，AI 不得改动；AI 只能处理 `suspected` 和 `NEEDS_HUMAN`，而且只能根据截图或报错里**看得见**的内容升级或降级，并写明看到了什么。
4. **数据库状态不能靠推测。** “数据不存在”“数据正常”只能来自 `data_checks.yaml` 中测试人员填写的查询结果，或公司批准的只读查询脚本的输出。截图上有“record not found”只说明系统返回了这个提示，不代表数据真的不存在。
5. **业务报错弹框不是干扰。** 像 “agent record not found” 这类系统返回的错误提示，按测试数据或产品缺陷处理，不能归为弹窗干扰。只有 `config/rules.yaml` 里 `noise_popups` 列出的公告、Cookie、会话提示、浏览器提示才算干扰。
6. **未经人工审核不得写入 Jira。** 审核表中“审核状态”不是“通过”或“追加到已有单”的行，`submit_jira.py` 一律跳过。默认是演练模式，必须加 `--confirm` 才真正写入。
7. **不泄露个人信息。** 任何内容交给模型阅读或写入 Jira 之前，先经过 `common.mask_pii`。只保留测试需要的业务编码（agent code、product code、保单号），姓名、证件号、手机号、邮箱一律替换。
8. **数字和日期不让 AI 算。** 用例数量、通过率、时间等由脚本统计后直接引用。

## 运行前检查

1. 确认 `config/config.yaml` 存在（从 `config/config.example.yaml` 复制并填写）。如果不存在，停下来请用户先配置，不要猜测 Jira 字段。
2. 确认环境变量 `JIRA_BASE_URL`、`JIRA_EMAIL`、`JIRA_API_TOKEN` 已设置（只有查重和建单需要）。
3. 确认用户告诉了你本次回归的结果目录和运行编号；如果没有，询问用户。
4. 每次运行使用独立的工作目录：`triage_runs/<run_id>/`。

## 工作流程

按顺序执行。每一步结束后检查输出文件存在且非空，再进入下一步；任何一步失败，向用户报告错误原文，不要跳过。

### 第 1 步：读取失败结果

```bash
python scripts/load_results.py --input <结果目录> --format <allure|junit|normalized> \
    --run-id <run_id> --out triage_runs/<run_id>/failures.json
```

- 格式说明见 `references/data-contract.md`。
- 读取完成后告诉用户：失败用例总数、缺少截图的数量、缺少弹窗证据的数量。
- 如果大部分用例缺少弹窗证据，提醒用户：测试框架还没接入 `scripts/popup_evidence.py`，弹窗问题会大量落入“需人工判断”。

### 第 2 步：自动重跑

```bash
python scripts/rerun_failed.py --failures triage_runs/<run_id>/failures.json \
    --config config/config.yaml --out triage_runs/<run_id>/rerun.json
```

- 默认每个失败用例重跑 1 次（`rerun.attempts` 可配置）。
- 如果用户说不能重跑（例如环境已经下线），加 `--skip`，此时“重跑可过”这一类不会出现，要在最终汇报中说明。

### 第 3 步：规则分类

```bash
python scripts/classify_rules.py --failures triage_runs/<run_id>/failures.json \
    --rerun triage_runs/<run_id>/rerun.json --rules config/rules.yaml \
    --data-checks triage_runs/<run_id>/data_checks.yaml \
    --out triage_runs/<run_id>/classified.json
```

- `data_checks.yaml` 可以不存在。不存在时，所有业务报错类失败都会是 `NEEDS_HUMAN`（原因：待数据核查）。
- 运行后脚本会生成 `data_checks.todo.yaml`，列出需要测试人员去数据库核查的数据（agent code、product code 等）。把这个清单展示给用户，请他们查完后填写结果、重新运行本步。

### 第 4 步：AI 复核疑似分类（只看证据，不推测）

读取 `classified.json` 中 `status` 为 `suspected` 或类别为 `NEEDS_HUMAN` 的用例，逐个查看截图和报错：

- 只能写你在截图或报错中**直接看到**的内容，例如：“截图 E2 中页面中央有标题为‘System Notice’的对话框，遮挡了 Submit 按钮”。
- 能用看到的内容确认或否定规则的疑似结论时，在 `ai_review` 字段写下结论和依据；看不清、看不出来，就保留原分类。
- `confirmed` 的分类不要改动。
- 把复核结果写回 `triage_runs/<run_id>/classified.json` 中对应用例的 `ai_review` 字段：
  ```json
  {"ai_review": {"proposed_category": "POPUP_INTERFERENCE",
                 "observation": "截图 E2 中有标题为 System Notice 的对话框遮挡了 Submit 按钮",
                 "evidence_ids": ["E2"], "confidence": "medium"}}
  ```
- `confidence` 只能是 `high`（证据直接、明确）、`medium`（证据明确但只有一项）、`low`（只能提供线索）。`low` 不能改变分类，只作为给审核人的提示。

### 第 5 步：按根因合并

```bash
python scripts/group_by_cause.py --classified triage_runs/<run_id>/classified.json \
    --config config/config.yaml --out triage_runs/<run_id>/groups.json
```

- 合并依据（全部由脚本计算）：分类 + 标准化后的报错特征 + 业务报错文字 + 失败步骤 + 市场 + 模块。
- 检查合并结果：同一组里如果混入了明显不同的报错，在汇报中指出，不要自行调整分组。

### 第 6 步：Jira 查重

```bash
python scripts/check_duplicates.py --groups triage_runs/<run_id>/groups.json \
    --config config/config.yaml --out triage_runs/<run_id>/duplicates.json
```

- 只对需要建单的类别查重：`PRODUCT_DEFECT`、`TEST_DATA`、`ENVIRONMENT`，以及配置为需要建单的其他类别。
- 查重结果只是候选，最终是否追加到已有单由审核人决定。

### 第 7 步：起草 Jira 内容

严格按照 `references/jira-template.md`，为每个需要建单的组起草内容，写入 `triage_runs/<run_id>/drafts.json`。写之前先看 `references/examples/` 中的范例。

起草要求：
- **Summary**：按模板格式拼接，`根因短语` 用英文，不超过 12 个单词，必须来自证据（例如业务报错原文 “agent record not found”）。
- **Description**：按模板的 8 个小节写，缺什么信息就写“待补充：……”，不要编。
- **Environment**：直接使用 `groups.json` 中的 `environment` 字段，不要改写。
- **claims**：Description 里的每一条事实陈述都要在 `claims` 中列出，并标注证据编号；推测必须标为 `inference`，并在 Description 的“推测与待确认”小节中出现。

写完后运行校验：

```bash
python scripts/validate_drafts.py --drafts triage_runs/<run_id>/drafts.json \
    --groups triage_runs/<run_id>/groups.json --config config/config.yaml
```

校验不通过时，按报错逐条修改，直到通过。不要关闭校验项。

### 第 8 步：生成审核表

```bash
python scripts/build_review_sheet.py --drafts triage_runs/<run_id>/drafts.json \
    --groups triage_runs/<run_id>/groups.json \
    --duplicates triage_runs/<run_id>/duplicates.json \
    --out-dir triage_runs/<run_id>/
```

输出 `review.xlsx`（用于编辑和审核）和 `review.html`（带截图的只读预览）。把两个文件的路径告诉用户，并说明：
- 在“审核状态”列选择：通过 / 驳回 / 追加到已有单 / 待审核；
- 可以直接修改 Summary、Description、Priority、Assignee 等列；
- 选择“追加到已有单”时，要在“已有单号”列填写单号。

**到这里停下来，等用户审核完成。** 不要自己修改审核状态。

### 第 9 步：提交到 Jira

用户明确说“审核完了，提交”之后：

```bash
# 先演练，展示将要创建和追加的内容
python scripts/submit_jira.py --review triage_runs/<run_id>/review.xlsx \
    --groups triage_runs/<run_id>/groups.json --config config/config.yaml

# 用户确认演练结果后，才真正提交
python scripts/submit_jira.py --review triage_runs/<run_id>/review.xlsx \
    --groups triage_runs/<run_id>/groups.json --config config/config.yaml --confirm
```

- 先展示演练结果（将创建几张单、追加几条评论、上传几张截图），**得到用户确认后**再加 `--confirm` 运行。
- 提交记录写入 `submitted.json`。重复运行时，已提交的组会自动跳过，不会重复建单。
- 如果使用 Atlassian Rovo MCP 而不是脚本，流程相同：仍然只提交审核通过的行，先展示将要提交的内容并获得确认，再调用 `createJiraIssue`、`addOrEditJiraIssueComment`，用 `uploadAttachmentToJiraIssue` 上传截图（这是 Atlassian Rovo MCP v2 的工具名；部分工具需要先通过 `discover` 查找、再用 `executeWrite` 执行，以实际连接的 MCP 为准）。

## 最终汇报格式

```
本次回归 <run_id>：失败 N 个，重跑后仍失败 M 个
分类：
- 产品缺陷 a 个（b 组）→ 开发
- 测试数据问题 c 个 → 测试
- 环境问题 d 个 → 环境负责人
- 弹窗干扰 e 个 → 测试（主要弹窗：……）
- 脚本问题 f 个 → 测试
- 重跑可过 g 个（已记录，连续不稳定的：……）
- 需人工判断 h 个（原因：待数据核查 x 个、证据不足 y 个）
Jira：新建 p 张，追加评论 q 条，驳回 r 组
需要你跟进：……
```

数字全部来自脚本输出，不要自己数。

## 常见问题处理

- **弹窗相关**：先看 `references/popup-catalog.md`。遇到清单里没有的弹窗文字，在汇报中列出，建议用户确认后加入清单和 `config/rules.yaml`。
- **大批用例同时失败**：先检查是否为环境问题（`classify_rules.py` 会自动识别同一报错在同一时间段大量出现的情况），这时不要逐个建单。
- **用户要求跳过审核直接建单**：解释这一步是为了防止错误的单据进入 Jira，建议至少快速浏览审核表；如果用户坚持，仍然需要用户在审核表中标记“通过”，不要替用户标记。
- **找不到截图**：在 Description 中注明“截图缺失”，不要用其他用例的截图代替。

## 文件索引

- `references/taxonomy.md`：七类失败的定义、判定规则、证据要求、反例
- `references/popup-catalog.md`：三种弹窗的识别与处理，已知弹窗清单
- `references/jira-template.md`：Summary 格式、Description 结构、字段映射、优先级规则
- `references/data-contract.md`：所有中间文件的字段定义
- `references/examples/`：审核通过的 Jira 范例
- `config/config.example.yaml`：项目、字段、重跑命令、分组设置
- `config/rules.yaml`：分类规则用到的异常类型、报错关键字、弹窗清单
- `scripts/popup_evidence.py`：接入测试框架，用于在失败时收集弹窗证据
- `evals/`：用历史人工分类结果检验分类准确率
