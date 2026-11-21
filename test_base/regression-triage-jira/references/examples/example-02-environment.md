# 范例 2：环境问题 → 一次运行只建一张单

## 输入

- 分类：`ENVIRONMENT`，规则 `ENV2`（报错匹配 `503 Service Unavailable`）和 `ENV3`（同一特征 18 个用例，14:40–14:52）
- 用例：18 个，覆盖 HK/BM、HK/UW、MO/BM
- 重跑：重跑建议是“环境恢复后立即重跑”，但到 16:00 环境仍未恢复，未重跑
- 证据：
  - G03-E1：页面内容 `503 Service Unavailable`
  - G03-E2：18 个用例的同一报错特征，时间范围 14:40–14:52

## 输出

**Summary**

```
[NBS Regression] HK/MO - Multiple cases failed due to NBS test environment returned 503
```

**Description**

```
SIT2 NBS returned "503 Service Unavailable" when opening pages from 14:40 to 14:52, 18 regression cases failed. The environment is still not available at 16:00, could you help to check? Thanks!

*1st run* (2026-11-03 14:40–14:52): "503 Service Unavailable" on page open, same error for all 18 cases.
!Case21_fail.png|thumbnail!

|| Case || Module || Failed step ||
| ... | ... | ... |
```

**claims**

```json
[
  {"text": "打开页面返回 503 Service Unavailable", "type": "fact", "evidence_ids": ["G03-E1"]},
  {"text": "18 个用例报错相同，集中在 14:40–14:52", "type": "fact", "evidence_ids": ["G03-E2"]}
]
```

**其他字段**：Issue type = Task（按配置，环境问题建任务）；Priority = High（整批无法执行）。

## 为什么这样写

- 环境问题是唯一合并成一张单的情况：18 个用例只建 1 张单，避免刷屏；用小表列出全部用例。
- 先按报错判断为环境问题，再看重跑建议。环境恢复后重跑：
  - 全部通过：说明是临时性问题。分类仍是环境问题（`rerun_result: pass`），默认不提单，在汇报中记录发生时间；
  - 仍然失败：写 *2nd run*，说明环境问题持续。
- 没有猜测“服务器负载过高”之类的原因，只写看到的现象和时间。
