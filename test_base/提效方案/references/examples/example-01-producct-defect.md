# 范例 1：业务报错 + 数据核查正常 → 产品缺陷

> 参照 ROTQA-5339 的格式整理。截图中的具体用例编号、步骤为示意，正式使用前请替换为同事B审核过的真实单据。

## 输入（groups.json 中的一组）

- 分类：`PRODUCT_DEFECT`，规则 `BIZ2`，状态 `confirmed`
- 用例：Case7、Case9、Case12（HK / BM）
- 证据：
  - G01-E1：弹框文字 `Agent record not found`
  - G01-E2：截图 `Case7_fail.png`
  - G01-E3：重跑 1 次仍失败
  - G01-E4：数据核查 `agent_code=40100` 结果 `ok`（同事B，SIT2 只读账号查询 AGENT 表，状态 Active）
- 测试数据：agent code 40100，product code UR67

## 输出

**Summary**

```
[NBS Regression] HK - BM cases failed due to agent record not found
```

**Description**

```
h3. 1. 现象
在代理人选择页点击 Submit 后，系统弹框提示 {{Agent record not found}}，流程无法继续。

h3. 2. 受影响的用例（共 3 个）
|| 用例编号 || 用例名称 || 失败步骤 || 截图 ||
| Case7 | PolSchedule BZ600 new business submission | Click Submit on agent selection page | !Case7_fail.png|thumbnail! |
| Case9 | PolSchedule BZ610 new business submission | Click Submit on agent selection page | !Case9_fail.png|thumbnail! |
| Case12 | PolSchedule UR67 new business submission | Click Submit on agent selection page | !Case12_fail.png|thumbnail! |

h3. 3. 重现步骤
# 以核保员账号登录 NBS SIT2
# 新建投保单，产品选择 UR67
# 在代理人选择页输入 agent code 40100
# 点击 Submit

h3. 4. 预期结果
系统带出代理人信息，进入下一步。

h3. 5. 实际结果
弹框提示 {{Agent record not found}}。

h3. 6. 已做的排查
* 已在 SIT2 数据库用只读账号查询 AGENT 表，agent 40100 记录存在，状态为 Active（核查人：同事B，2026-11-03 16:10）
* 已自动重跑 1 次，仍然失败
* 同一次回归中，其他模块用例正常，排除整体环境问题

h3. 7. 测试数据
* Agent code: 40100
* Product code: UR67

h3. 8. 推测与待确认
* 推测：代理人查询接口读取的数据源可能与 AGENT 表不一致，请开发确认
* 待确认：上一次回归（2026-10-27）该用例通过，期间是否有相关代码或配置变更
```

**claims**

```json
[
  {"text": "点击 Submit 后弹框提示 Agent record not found", "type": "fact", "evidence_ids": ["G01-E1", "G01-E2"]},
  {"text": "重跑 1 次仍然失败", "type": "fact", "evidence_ids": ["G01-E3"]},
  {"text": "agent 40100 在 AGENT 表中存在且为 Active", "type": "fact", "evidence_ids": ["G01-E4"]},
  {"text": "代理人查询接口读取的数据源可能不一致", "type": "inference", "evidence_ids": []}
]
```

**其他字段**：Priority = High（命中“出单”相关模块）；Components = SYSTEM-QA；System = NBS；Labels = regression, auto-triage, run-2026-11-03_142142, HK。

## 为什么这样写

- 标题的根因直接用了弹框原文，没有写推测原因。
- “已做的排查”中每一条都有证据：数据核查有核查人、时间和方法。
- 推测单独放在第 8 节，并且写明“推测”。
