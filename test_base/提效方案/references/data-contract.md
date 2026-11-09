# 数据格式约定（Data Contract）

所有脚本之间通过 JSON / YAML 文件传递数据，存放在 `triage_runs/<run_id>/` 下。字段名固定，脚本和 AI 都按本文件读写。

## 文件流转

```
结果目录 ──load_results──▶ failures.json
                              │
              rerun_failed ──▶ rerun.json
                              │
 data_checks.yaml ─┐          ▼
                   └▶ classify_rules ──▶ classified.json + data_checks.todo.yaml
                              │
                     （AI 复核写入 ai_review）
                              │
              group_by_cause ──▶ groups.json
                              │
           check_duplicates ──▶ duplicates.json
                              │
                   （AI 起草）──▶ drafts.json ──validate_drafts──▶ 通过
                              │
         build_review_sheet ──▶ review.xlsx + review.html
                              │
                   （人工审核 review.xlsx）
                              │
                 submit_jira ──▶ submitted.json
```

## 1. 输入：结果目录

`load_results.py` 支持三种格式：

### 1.1 Allure（`--format allure`）

读取 `allure-results/` 目录下的 `*-result.json`。使用的字段：

| Allure 字段 | 用途 |
|---|---|
| `name` / `fullName` | 用例名称 / 唯一标识 |
| `status` | 只读取 `failed` 和 `broken` |
| `statusDetails.message` / `statusDetails.trace` | 报错信息 / 堆栈 |
| `labels`（`name`=`market`/`module`/`system`/`case_id`/`suite`） | 用例标签 |
| `parameters` | 测试数据（agent_code、product_code 等） |
| `attachments`（`name`、`source`、`type`） | 截图、页面源码、弹窗证据 JSON |
| `steps` | 找出第一个失败的步骤 |
| `start` / `stop` | 执行时间（毫秒时间戳） |
| `historyId` | 关联历史结果 |

同目录下的 `environment.properties` 会作为环境信息读取。

### 1.2 JUnit XML（`--format junit`）

读取一个或多个 `*.xml`。`<testcase>` 下的 `<failure>`、`<error>` 视为失败。截图等附件通过 `<properties>` 传递：

```xml
<testcase classname="tests.hk.bm.test_new_business" name="test_case7_bz600" time="83.2">
  <properties>
    <property name="case_id" value="Case7"/>
    <property name="market" value="HK"/>
    <property name="module" value="BM"/>
    <property name="system" value="NBS"/>
    <property name="screenshot" value="screenshots/Case7_fail.png"/>
    <property name="evidence" value="evidence/Case7.json"/>
    <property name="agent_code" value="40100"/>
    <property name="product_code" value="UR67"/>
  </properties>
  <failure type="selenium.common.exceptions.ElementClickInterceptedException"
           message="element click intercepted: ...">堆栈内容</failure>
</testcase>
```

用 pytest 时，可以在 `conftest.py` 里用 `record_property("market", "HK")` 写入这些属性。

### 1.3 标准化 JSON（`--format normalized`）

如果你们的平台（例如 BLN）能导出结果，最简单的做法是写一个小转换脚本，输出下面 `failures.json` 中 `cases` 的格式，再用 `--format normalized` 读取。

## 2. failures.json

```json
{
  "run_id": "2026-11-03_142142",
  "source_format": "allure",
  "loaded_at": "2026-11-03T15:02:11+08:00",
  "environment": {
    "env_name": "NBS-SIT2",
    "browser": "MicrosoftEdge",
    "browser_version": "142.0.3595.53",
    "driver_version": "142.0.3595.53",
    "os": "Windows 11",
    "build": "NBS 5.12.0-rc3"
  },
  "cases": [
    {
      "case_id": "Case7",
      "case_name": "PolSchedule BZ600 new business submission",
      "nodeid": "tests/hk/bm/test_new_business.py::test_case7_bz600",
      "system": "NBS",
      "market": "HK",
      "module": "BM",
      "status": "failed",
      "started_at": "2026-11-03T14:31:05+08:00",
      "duration_sec": 83.2,
      "failed_step": "Click Submit on agent selection page",
      "case_steps": ["Login as underwriter", "Create new proposal", "..."],
      "error_type": "ElementClickInterceptedException",
      "error_message": "element click intercepted: ... Other element would receive the click: <div class=\"modal-backdrop\">",
      "stack_trace": "Traceback (most recent call last): ...",
      "business_error_text": "Agent record not found",
      "page_url": "https://nbs-sit2.example/agent/select",
      "screenshots": ["screenshots/Case7_fail.png"],
      "fullscreen_screenshot": "screenshots/Case7_fullscreen.png",
      "popup_evidence": {
        "popup_type": "html_modal",
        "alert_text": null,
        "dialogs": [{"tag": "div", "cls": "modal show", "id": "errDlg", "text": "Agent record not found"}]
      },
      "test_data": {"agent_code": "40100", "product_code": "UR67"},
      "history": [{"run_id": "2026-10-27_141530", "status": "passed"}],
      "evidence": [
        {"id": "E1", "kind": "error_message", "content": "element click intercepted: ..."},
        {"id": "E2", "kind": "screenshot", "path": "screenshots/Case7_fail.png"},
        {"id": "E3", "kind": "popup_text", "content": "Agent record not found"}
      ]
    }
  ]
}
```

说明：
- 缺失的字段填 `null` 或空列表，不要省略字段。
- `evidence` 由 `load_results.py` 自动生成编号，后续脚本追加的证据（重跑、数据核查）会接着编号。
- 所有文本字段已经过 `mask_pii` 处理。

## 3. rerun.json

```json
{
  "run_id": "2026-11-03_142142",
  "skipped": false,
  "results": {
    "Case7": {
      "attempts": [
        {"attempt": 1, "status": "failed", "started_at": "...", "duration_sec": 80.1,
         "error_type": "ElementClickInterceptedException", "error_message": "..."}
      ],
      "passed_on_rerun": false
    }
  }
}
```

## 4. data_checks.yaml（人工填写）

```yaml
- key: agent_code=40100        # 与 data_checks.todo.yaml 中的 key 一致
  result: ok                   # ok / missing / used / invalid_state
  checked_by: 同事B
  checked_at: 2026-11-03 16:10
  method: "SIT2 只读账号查询 AGENT 表"
  note: "记录存在，状态 Active"
```

## 5. classified.json

```json
{
  "run_id": "...",
  "cases": [
    {
      "case_id": "Case7",
      "category": "PRODUCT_DEFECT",
      "status": "confirmed",
      "rule_id": "BIZ2",
      "owner": "开发",
      "reason": "页面业务报错 'Agent record not found'，数据核查结果为 ok",
      "evidence_ids": ["E3", "E5"],
      "needs_human_reason": null,
      "flags": {"historically_flaky": false, "rerun_pass_with_business_error": false},
      "ai_review": null
    }
  ],
  "summary": {
    "total_failed": 40,
    "by_category": {"PRODUCT_DEFECT": 6, "...": 0},
    "popups": [{"text": "Agent record not found", "count": 6, "pages": ["/agent/select"]}]
  }
}
```

原始用例字段会一并保留在每个 case 中（脚本会把 failures.json 的字段合并进来），方便后续步骤读取。

## 6. groups.json

```json
{
  "run_id": "...",
  "environment": "Environment: NBS-SIT2\nBrowser: MicrosoftEdge 142...\n...",
  "groups": [
    {
      "group_id": "G01",
      "category": "PRODUCT_DEFECT",
      "owner": "开发",
      "system": "NBS",
      "market": "HK",
      "module": "BM",
      "signature": "PRODUCT_DEFECT|agent record not found|click submit on agent selection page",
      "root_cause_hint": "agent record not found",
      "case_ids": ["Case7", "Case9", "Case12"],
      "evidence": [{"id": "G01-E1", "case_id": "Case7", "ref": "E3", "kind": "popup_text", "content": "..."}],
      "screenshots": ["screenshots/Case7_fail.png", "..."],
      "test_data": {"agent_code": ["40100"], "product_code": ["UR67"]},
      "suggested_priority": "High",
      "needs_jira": true
    }
  ]
}
```

## 7. drafts.json（AI 写）

```json
{
  "run_id": "...",
  "drafts": [
    {
      "group_id": "G01",
      "summary": "[NBS Regression] HK - BM cases failed due to agent record not found",
      "description": "h3. 1. 现象\n...",
      "priority": "High",
      "labels": ["regression", "auto-triage", "run-2026-11-03_142142", "HK"],
      "claims": [
        {"text": "提交代理人时系统提示 Agent record not found", "type": "fact", "evidence_ids": ["G01-E1"]},
        {"text": "测试环境数据库中 agent 40100 记录存在", "type": "fact", "evidence_ids": ["G01-E4"]},
        {"text": "可能是代理人查询接口使用了错误的数据源", "type": "inference", "evidence_ids": []}
      ]
    }
  ]
}
```

## 8. review.xlsx 列定义

| 列 | 说明 | 是否可编辑 |
|---|---|---|
| group_id | 组编号 | 否 |
| 审核状态 | 待审核 / 通过 / 驳回 / 追加到已有单 | **是（必填）** |
| 已有单号 | 选择“追加到已有单”时必填 | 是 |
| 疑似重复 | 查重找到的单号和标题 | 否 |
| 分类 / 处理方 | 规则分类结果 | 否 |
| 人工分类 | 审核人不同意分类时填写 | 是 |
| 修改原因 | 填写人工分类时必填 | 是 |
| Summary / Description / Priority / Labels / Components / Assignee | Jira 字段 | 是 |
| 受影响用例 / 截图 / 证据摘要 / 推测与待确认 | 参考信息 | 否 |
| 审核备注 | 自由填写 | 是 |

## 9. submitted.json

```json
{
  "run_id": "...",
  "submitted": [
    {"group_id": "G01", "action": "create", "issue_key": "ROTQA-5401",
     "attachments": ["Case7_fail.png"], "submitted_at": "...", "submitted_by": "..."}
  ],
  "failed": [{"group_id": "G04", "error": "..."}]
}
```
