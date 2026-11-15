# ROTQA Jira 起草模板

本模板根据 ROTQA-5339 的格式整理。**上线前请同事B核对**：字段名称、必填项、问题类型名称、System 字段的可选值，以确保与实际建单页面一致。

## 1. Summary（标题）

**默认一个用例一张单。** 同一原因的其他用例各自另开一张单，在汇报中列为相关用例；只有环境问题合并为一张单。

### 格式

```
[{system} Regression] {market} - {module} {case_id} failed due to {root_cause}
```

| 部分 | 来源 | 示例 |
|---|---|---|
| `system` | `groups.json` 中的 `system`（从用例标签或配置读取） | `LAS`、`NBS` |
| `market` | 用例的市场标签 | `HK` |
| `module` | 用例的模块标签；没有标签时用用例名里的功能名 | `Assurance`、`BM` |
| `case_id` | 用例编号（序号） | `test_27_TC_LAS_PaidToDateAdvance_01` |
| `root_cause` | 英文短语，≤ 12 个单词，必须来自证据 | `agent record not found` |

环境问题合并的单：`{module}` 后写 `cases`，不写用例编号，例如 `[NBS Regression] HK - All cases failed due to NBS test environment returned 503`。

### root_cause 的写法

- 有业务报错时：直接使用业务报错的关键部分，统一为小写。例如 `agent record not found`。
- 环境问题：写现象，例如 `NBS test environment returned 503`、`Edge driver version mismatch`。
- 断言失败：写哪个值不对，例如 `premium amount mismatch on quotation page`。
- **不要写推测的原因**，例如不能写 `due to database sync delay`，除非有证据证明。

### 示例

- `[LAS Regression] HK - Assurance test_12_TC_LAS_Assurance_03 failed due to popup error when search policy`
- `[NBS Regression] HK - BM test_05_TC_NBS_BM_01 failed due to agent record not found`
- `[NBS Regression] HK - All cases failed due to NBS test environment returned 503`

## 2. Description（描述）

**简洁，像同事之间说话一样。** 开发要一眼看懂“哪个环境、哪个功能、做什么时出了什么错、要我做什么”。不写长篇分析。使用 Jira 文本格式（wiki markup）。

### 结构

```
{env} {system} - {module} encounter {problem} when {action}. Could you help to check? Thanks!

*1st run* ({started_at}): {第 1 次的报错原文或现象，一句话}
!{第 1 次截图文件名}|thumbnail!

*2nd run (rerun)*: Failed again with the same error. The issue is reproducible.
!{第 2 次截图文件名}|thumbnail!

*Test Data*: agent code {agent_code}, product code {product_code}, policy no. {policy_no}
```

- 第一段：**一两句话**。做过的排查（例如已查数据库数据正常、换了 agent code 仍然报错）直接写进这一段，见下面的示例。
- `*1st run*`：必须有。报错原文用引号或 `{{ }}` 包起来，不要改写。
- `*2nd run*`：只有重跑过且仍然失败时才写。
  - 报错相同（`fail_same`）：写在同一张单里，如上。
  - 报错不同（`fail_diff`）：第 1 张单只写 1st run，并加一句 `The rerun failed with a different error, reported in a separate ticket.`；第 2 次单独成单（`attempt = 2`），这张单写 `*1st run* ... (handled separately)` 和 `*2nd run*` 的报错与截图。
  - 重跑通过（`pass`）：不提单。
- `*Test Data*`：只写业务编码（agent code、product code、保单号），不写姓名、证件号、手机号。没有就省略这一行。
- 推测要写明是推测：`seems`、`Suspected`、`To be confirmed`。
- 环境合并的单：第一段之后用一张小表列出受影响的用例；超过 20 个时只列前 20 个，后面写“其余 {n} 个用例见附件 affected_cases.csv”。

### 示例（来自 ROTQA 已提的单，按这个口吻写）

```
U401 LAS - Assurance encounter the popup error when search policy. Could you help to check? Thanks!

*1st run* (2026-10-30 10:12): Popup "Policy information cannot be retrieved" displayed after clicking Search.
!test_12_fail.png|thumbnail!
```

```
I tried to use agent code "50051" to run the BM cases, it still displays the "record not found" error. U401 NBS - BM case displays "agent record not found". I checked the agent data in DB and there seems to be no data error, could you help to check? Thanks!

*1st run* (2026-11-03 14:31): "agent record not found" displayed after submitting agent 48100.
!test_05_fail.png|thumbnail!

*2nd run (rerun)*: Failed again with the same error. The issue is reproducible.
!test_05_rerun.png|thumbnail!

*Test Data*: agent code 48100, product code UFK1
```

### 书写要求

- 报错原文不要改写；看不清的内容不要猜。
- “已查过数据库”之类的排查只写真正做过的事，并在 `claims` 中引用证据（数据核查记录）。
- **截图**：用 `!文件名|thumbnail!` 引用，文件会在建单后作为附件上传。文件名必须和实际上传的文件名一致。
- `validate_drafts.py` 会检查：第一段存在且不太长、有 `*1st run*`、重跑同样失败时有 `*2nd run*`、截图文件存在、事实有证据、没有个人信息。

## 3. Environment（环境）

由脚本根据运行记录直接生成，AI 不改写：

```
Environment: {env_name}
Browser: {browser} {browser_version}
Driver: {driver_version}
OS: {os}
Run ID: {run_id}
Build: {build}
Executed at: {started_at} (UTC+8)
```

> 如果 ROTQA 项目没有单独的 Environment 字段，`submit_jira.py` 会把这段内容放在 Description 最前面（由 `config.yaml` 的 `jira.environment_mode` 控制）。

## 4. 其他字段

| 字段 | 取值规则 | 配置位置 |
|---|---|---|
| Project | `ROTQA` | `jira.project_key` |
| Issue type | 默认 `Bug`；环境问题可配置为 `Task` | `jira.issue_type_by_category` |
| System（自定义字段） | 来自用例标签，例如 `NBS` | `jira.fields.system` |
| Components | 默认 `SYSTEM-QA` | `jira.default_components` |
| Priority | 按下表规则建议，审核人可修改 | `jira.priority_rules` |
| Labels | `regression`、`auto-triage`、`run-{run_id}`、市场代码 | `jira.default_labels` |
| Assignee | 不自动填写，由审核人填写（避免 AI 乱指派） | — |
| Reporter | 使用 API Token 对应的账号 | — |

### 优先级建议规则

| 条件 | 建议优先级 |
|---|---|
| 影响出单、核保、支付、金额计算的产品缺陷 | High |
| 同一原因影响的用例 ≥ 10 个（含相关用例） | High |
| 环境问题导致整批无法执行 | High |
| 其他产品缺陷 | Medium |
| 测试数据问题、脚本稳定性任务 | Low |

“影响出单、核保、支付、金额计算”通过模块标签和关键字判断，关键字在 `config.yaml` 的 `jira.priority_rules.high_impact_keywords` 中配置。这只是建议值，审核人有最终决定权。

## 5. 追加到已有单时的评论格式

```
Found again in regression {run_id}: {case_id} encounter {problem} when {action}.

*1st run* ({started_at}): {报错原文}
!{截图文件名}|thumbnail!
```

重跑仍然失败时同样补一行 `*2nd run*` 和截图。截图作为附件上传。是否与原单是同一问题由审核人确认。
