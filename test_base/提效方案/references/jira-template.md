# ROTQA Jira 起草模板

本模板根据 ROTQA-5339 的格式整理。**上线前请同事B核对**：字段名称、必填项、问题类型名称、System 字段的可选值，以确保与实际建单页面一致。

## 1. Summary（标题）

### 格式

```
[{system} Regression] {market} - {module} case(s) failed due to {root_cause}
```

| 部分 | 来源 | 示例 |
|---|---|---|
| `system` | `groups.json` 中的 `system`（从用例标签或配置读取） | `NBS` |
| `market` | 用例的市场标签 | `HK` |
| `module` | 用例的模块标签 | `BM` |
| `case(s)` | 组内用例数为 1 时写 `case`，大于 1 时写 `cases` | `cases` |
| `root_cause` | 英文短语，≤ 12 个单词，必须来自证据 | `agent record not found` |

### root_cause 的写法

- 有业务报错时：直接使用业务报错的关键部分，统一为小写。例如 `agent record not found`。
- 环境问题：写现象，例如 `NBS test environment returned 503`、`Edge driver version mismatch`。
- 断言失败：写哪个值不对，例如 `premium amount mismatch on quotation page`。
- **不要写推测的原因**，例如不能写 `due to database sync delay`，除非有证据证明。

### 示例

- `[NBS Regression] HK - BM cases failed due to agent record not found`
- `[NBS Regression] MO - UW case failed due to premium amount mismatch on quotation page`
- `[NBS Regression] HK - All cases failed due to NBS test environment returned 503`

## 2. Description（描述）

使用 Jira 文本格式（wiki markup），按以下 8 个小节书写。**没有信息的小节写“待补充：<缺什么>”，不能删除小节，也不能编造内容。**

```
h3. 1. 现象
{一到两句话，描述系统表现。引用报错原文，用 {{ }} 包起来。}

h3. 2. 受影响的用例（共 {n} 个）
|| 用例编号 || 用例名称 || 失败步骤 || 截图 ||
| {case_id} | {case_name} | {failed_step} | !{screenshot_file}|thumbnail! |

h3. 3. 重现步骤
# {步骤 1}
# {步骤 2}
# ...

h3. 4. 预期结果
{根据用例描述或断言中的期望值}

h3. 5. 实际结果
{报错原文 / 断言中的实际值}

h3. 6. 已做的排查
* {例如：已在测试环境数据库查询 agent 40100，记录存在，状态为 Active（核查人：xxx，时间：xxx）}
* {例如：已重跑 1 次，仍然失败}
* {例如：同一时段其他模块用例正常，排除环境问题}

h3. 7. 测试数据
* Agent code: {agent_code}
* Product code: {product_code}
* Policy no.: {policy_no}

h3. 8. 推测与待确认
* {所有推测写在这里，并标明“推测”}
* {需要开发确认的问题}
```

### 书写要求

- **现象、实际结果**：必须引用报错原文，不要改写。
- **重现步骤**：来自用例步骤（`case_steps`），不要自己编。如果没有用例步骤，写“待补充：请从 BLN 平台复制用例步骤”。
- **已做的排查**：只写真正做过的事，每条都要有对应证据（重跑记录、数据核查记录）。
- **测试数据**：只写业务编码，不写姓名、证件号、手机号。
- **截图**：用 `!文件名|thumbnail!` 引用，文件会在建单后作为附件上传。文件名必须和实际上传的文件名一致。
- 用例超过 20 个时，表格只列前 20 个，后面写“其余 {n} 个用例见附件 affected_cases.csv”，脚本会自动生成并上传这个附件。

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
| 同一组影响用例 ≥ 10 个 | High |
| 环境问题导致整批无法执行 | High |
| 其他产品缺陷 | Medium |
| 测试数据问题、脚本稳定性任务 | Low |

“影响出单、核保、支付、金额计算”通过模块标签和关键字判断，关键字在 `config.yaml` 的 `jira.priority_rules.high_impact_keywords` 中配置。这只是建议值，审核人有最终决定权。

## 5. 追加到已有单时的评论格式

```
h4. 自动回归 {run_id} 再次出现（{n} 个用例）
* 执行时间：{started_at}
* 环境：{env_name}
* 受影响用例：{case_id 列表}
* 报错原文：{{ {error_excerpt} }}
* 与原单是否一致：{审核人确认}
```

截图同样作为附件上传。
