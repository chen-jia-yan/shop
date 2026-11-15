# 范例 1：业务报错 + 数据核查正常 → 产品缺陷（一个用例一张单）

> 口吻参照 ROTQA 已提的单。用例编号、时间为示意，正式使用前请替换为同事B审核过的真实单据。

## 输入（groups.json 中的一组）

- 分类：`PRODUCT_DEFECT`，规则 `BIZ2`，状态 `confirmed`
- 用例：Case7（HK / BM）；同一原因的相关用例：Case9、Case12（各自另有一张单）
- 重跑结果：`fail_same`（按重跑建议重跑 1 次，报错相同）
- 证据：
  - G01-E1：弹框文字 `Agent record not found`
  - G01-E2：第 1 次截图 `Case7_fail.png`
  - G01-E3：第 2 次（重跑）报错相同，截图 `Case7_rerun.png`
  - G01-E4：数据核查 `agent_code=40100` 结果 `ok`（同事B，SIT2 只读账号查询 AGENT 表，状态 Active）
- 测试数据：agent code 40100，product code UR67

## 输出

**Summary**

```
[NBS Regression] HK - BM Case7 failed due to agent record not found
```

**Description**

```
SIT2 NBS - BM encounter "agent record not found" when submitting agent 40100 on the agent selection page. I checked the agent data in DB, the record exists and is Active, could you help to check? Thanks!

*1st run* (2026-11-03 14:31): Popup "Agent record not found" displayed after clicking Submit.
!Case7_fail.png|thumbnail!

*2nd run (rerun)*: Failed again with the same error. The issue is reproducible.
!Case7_rerun.png|thumbnail!

*Test Data*: agent code 40100, product code UR67
```

**claims**

```json
[
  {"text": "点击 Submit 后弹框提示 Agent record not found", "type": "fact", "evidence_ids": ["G01-E1", "G01-E2"]},
  {"text": "重跑 1 次，报错相同", "type": "fact", "evidence_ids": ["G01-E3"]},
  {"text": "agent 40100 在 AGENT 表中存在且为 Active", "type": "fact", "evidence_ids": ["G01-E4"]}
]
```

**其他字段**：Priority = High（命中“出单”相关模块）；Components = SYSTEM-QA；System = NBS；Labels = regression, auto-triage, run-2026-11-03_142142, HK。

## 为什么这样写

- 一个用例一张单。Case9、Case12 是同一原因，各自另开一张；查重时它们很可能命中这张单，审核人可以改为“追加到已有单”。
- 第一段一两句话说清楚：哪个环境、哪个功能、做什么时出了什么错、已经排查过什么、请开发看看。
- 报错直接引用弹框原文；“已查过数据库”有核查记录作证据。
- 重跑报错相同，写在同一张单的 *2nd run*，附第 2 次截图。
- 没有推测就不写推测；有推测时用 seems / Suspected / To be confirmed 标明。
