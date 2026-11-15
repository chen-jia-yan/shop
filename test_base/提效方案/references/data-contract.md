# 数据格式约定（Data Contract）

所有脚本之间通过 JSON / YAML 文件传递数据，存放在 `triage_runs/<run_id>/` 下。字段名固定，脚本和 AI 都按本文件读写。

## 文件流转

```
结果目录 / 页面工作文件 ──load_results──▶ failures.json
                              │
 data_checks.yaml ─┐          ▼        （规则 config/rules.json，截图文字 *.ocr.json）
 workspace.json ───┴▶ classify_rules ──▶ classified.json + workspace.json + rerun_plan.json + data_checks.todo.yaml
                              │                              │
                     （AI 复核写入 ai_review）        （页面打开 workspace.json：看截图、记观察、选核查结果，保存后交回）
                              │
          （人工确认重跑名单）rerun_failed --plan ──▶ rerun.json
                              │
              classify_rules --rerun ──▶ classified.json（加上 rerun_result，分类不变，ai_review 保留）
                              │
       group_by_cause --rerun ──▶ groups.json（默认一个用例一张单）
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

`load_results.py` 支持四种格式（第四种 `--format workspace` 读取页面“保存工作文件”得到的文件，见 5.2 节）：

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

也可以不填这个文件：在页面打开 `workspace.json`，在用例上直接选核查结果后“保存工作文件”，第 2 步加 `--workspace`。两种方式结果相同，工作文件里已有的以工作文件为准。

```yaml
# 按数据填写（业务报错）：key 与 data_checks.todo.yaml 一致
- key: agent_code=40100
  result: ok                   # ok / missing / used / invalid（旧写法 invalid_state 也可以）
  checked_by: 同事B
  checked_at: 2026-11-03 16:10
  method: "SIT2 只读账号查询 AGENT 表"
  note: "记录存在，状态 Active"
# 按用例填写（数据占用、缺少配置、日期设置失败）：key 写 case=<用例编号>，result 用 todo 里列出的选项
- key: case=test_27_TC_LAS_PaidToDateAdvance_01
  result: lock_prev            # lock_prev / lock_other / lock_unknown；cfg_missing / cfg_ok / cfg_unsupported；dtp_out / dtp_in
  note: "前一个用例失败后没关窗口"
```

一个用例涉及多项数据时：有一项有问题就按那一项判断；全部核查过且都是 `ok` 才算“数据正常”。

## 5. classified.json

```json
{
  "run_id": "...",
  "engine": "ta_engine（与页面 engine.js 相同）",
  "cases": [
    {
      "case_id": "Case7",
      "category": "PRODUCT_DEFECT", "category_cn": "产品缺陷", "owner": "开发",
      "auto_category": "PRODUCT_DEFECT",
      "status": "confirmed",
      "rule_id": "BIZ2", "rule_name": "业务报错·数据正常",
      "brief": "业务报错“Agent record not found”，核查确认数据正常 → 系统有问题",
      "reason": "（同 brief，供后续步骤使用）",
      "why": ["出现业务报错“record not found”（E3）", "数据已核查且正常（E5），系统仍报错"],
      "need": [],
      "needs_human_reason": null,
      "flags": [],
      "check_kind": "biz", "phase": null, "from_ocr": false,
      "group_key": null,
      "evidence": [{"id": "E1", "kind": "error_message", "label": "报错信息", "content": "..."}],
      "evidence_ids": ["E1", "E2", "E3", "E4", "E5"],
      "human": {"dataCheck": "ok", "dataNote": "agent_code=40100：记录存在，状态 Active"},
      "log_summary": null,
      "rerun_result": null,
      "rerun_plan": {"advice": "no", "reason": "已判断是系统问题，直接起草 Jira，重跑不会改变结果"},
      "ai_review": null
    }
  ],
  "summary": {
    "total_failed": 40,
    "by_category": {"PRODUCT_DEFECT": 6, "...": 0},
    "by_rule": {"ENV-DESK": 26, "...": 0},
    "by_rerun_advice": {"go": 28, "fix": 6, "no": 6}
  }
}
```

原始用例字段会一并保留在每个 case 中（脚本会把 failures.json 的字段合并进来），方便后续步骤读取。

- 分类、规则编号、`brief`、`why`、`need`、`flags`、`rerun_plan` 与页面上同一用例显示的完全相同（同一个分析核心，见 `taxonomy.md`）。
- `flags`：页面上显示的标记，例如“环境中断边界”“失败时截图失败”“有残留窗口”“重跑通过”“重跑仍失败”“重跑报错不同”。
- `evidence[].kind`：`error_message` 报错信息、`popup_text` 页面/弹窗文字、`system_message` 系统提示原文、`root_exception` 最先发生的异常、`step_log` 步骤日志、`failure_location` 失败位置、`open_windows` 当时打开的窗口、`handler_error` 截图/清理中的异常、`stack_trace` 完整日志、`screenshot` 截图、`screenshot_observation` 截图观察（人工）、`screenshot_text` 截图文字（自动识别）、`rerun` 重跑记录、`data_check` 核查结果。
- `from_ocr: true`：结论用到了截图自动识别的文字，状态一定是 `suspected`。
- `rerun_result`：没有重跑时为 `null`；重跑后为 `pass`（重跑通过，偶发）/ `fail_same`（同样报错）/ `fail_diff`（报错不同）。**不影响 `category`。**
- `rerun_plan.advice`：`go` 建议立即重跑 / `fix` 处理后再重跑 / `no` 不需要重跑 / `done` 已重跑。标准见 `taxonomy.md` 的“重跑标准”。
- 再次运行 `classify_rules.py`（加 `--rerun`）时，原 `classified.json` 中的 `ai_review` 会按 `case_id` 保留。
- 所有文字都经过脱敏（证件号、手机号、邮箱、卡号、`rules.json` 的 `pii_names`）。

### 5.2 workspace.json（工作文件，页面和 skill 共用）

`classify_rules.py` 每次写在 classified.json 同目录；页面“保存工作文件”得到的也是这个格式。页面“打开工作文件”、`load_results.py --format workspace`、`classify_rules.py --workspace` 都读它。

```json
{
  "tool": "ta-workspace", "v": 1, "saved_at": "2026-11-15T10:30:00", "saved_by": "page", "masked": true,
  "rules": {"env_patterns": ["..."], "...": "与 config/rules.json 的 rules 相同"},
  "runs": [{"id": "R1", "name": "LAS HK 2026-10-30", "total": 50}],
  "cases": [
    {"uid": "R1#25", "run": "R1", "seq": 25, "id": "No.25", "name": "...", "result": "Failed", "failed": true,
     "error": "...（已脱敏）", "stack": "", "screenshot": "No.25.png", "start": "2026-10-30 14:02",
     "obs": {"kind": "popup", "text": "Contract is currently used by other user"},
     "ocrText": "截图识别的文字（已脱敏）",
     "dataCheck": "lock_other", "dataNote": "...",
     "override": {"cat": "SCRIPT_ISSUE", "reason": "人工确认的原因"},
     "rerun": "fail", "r2": {"same": true},
     "analysis": {"category": "TEST_DATA", "rule_id": "DATA-LOCK", "status": "confirmed", "brief": "...", "rerun_plan": {"advice": "fix", "reason": "..."}}}
  ]
}
```

- 包含通过的用例（`failed: false`），整批规律（环境中断的起点、大面积相同报错）才能算对。skill 从结果文件读取、文件里没有通过用例的详情时，按执行序号补占位记录（名称为“（结果文件里没有通过用例的详情）”）。
- 人工记录：`obs` 截图观察（`kind`：normal / popup / blank / other / disabled / desktop / unclear）、`dataCheck` 核查结果（取值见第 4 节）、`override` 人工改判、`rerun` 重跑结果（pass / fail）和 `r2.same`（报错是否与第一次相同）。
- `analysis` 是保存时的分析结果，只供阅读；打开时会重新分析，不读取它。
- 截图本身不在文件里。页面打开后，截图按用例编号保留，或在“补充截图”里重新选择截图文件夹。

### 5.3 rules.json（判断规则，页面和 skill 共用）

`config/rules.json`：`{"tool": "ta-rules", "v": 1, "rules": {...}}`，31 项，项名与页面“判断规则”相同。由页面“导出规则 → 下载规则文件”生成，覆盖原文件即可。

### 5.1 rerun_plan.json（与 classified.json 同目录）

```json
{
  "run_id": "...",
  "go":  ["test_12_TC_LAS_...", "..."],
  "fix": ["test_27_TC_LAS_..."],
  "items": [{"case_id": "test_27_TC_LAS_...", "category": "TEST_DATA", "advice": "fix", "reason": "先补数据或换数据，再重跑"}]
}
```

`rerun_failed.py --plan` 默认只重跑 `go`，加 `--include-fix` 时连 `fix` 一起重跑。

## 6. groups.json

默认一个用例一个组（`one_case_per_ticket: true`），一个组对应一张 Jira 单；环境问题合并为一组。

```json
{
  "run_id": "...",
  "one_case_per_ticket": true,
  "environment": "Environment: NBS-SIT2\nBrowser: MicrosoftEdge 142...\n...",
  "groups": [
    {
      "group_id": "G01",
      "attempt": 1,
      "category": "PRODUCT_DEFECT",
      "category_cn": "产品缺陷",
      "owner": "开发",
      "status": "confirmed",
      "system": "NBS",
      "market": "HK",
      "module": "BM",
      "signature": "PRODUCT_DEFECT|agent record not found|click submit on agent selection page",
      "root_cause_hint": "agent record not found",
      "case_ids": ["Case7"],
      "related_case_ids": ["Case9", "Case12"],
      "rerun_results": {"Case7": "fail_same"},
      "cases": [{"case_id": "Case7", "case_name": "...", "failed_step": "...", "reason": "...",
                 "started_at": "...", "screenshots": ["..."], "rerun_result": "fail_same", "rerun_attempts": ["..."]}],
      "evidence": [{"id": "G01-E1", "case_id": "Case7", "ref": "E3", "kind": "popup_text", "content": "..."}],
      "screenshots": ["screenshots/Case7_fail.png"],
      "test_data": {"agent_code": ["40100"], "product_code": ["UR67"]},
      "suggested_priority": "High",
      "needs_jira": true
    }
  ]
}
```

- `related_case_ids`：同一原因的其他失败用例（各自另有一张单），用于查重、汇报和在评论里互相引用。
- `rerun_results`：组内用例的重跑结果。全部为 `pass` 时 `needs_jira = false`（偶发，不提单）。
- `attempt = 2`：重跑报错与第一次不同（`fail_diff`）时，第 2 次单独成组，`group_id` 为 `G01-2`，`first_attempt_group` 指向第 1 次的组，分类先为 `NEEDS_HUMAN`（规则 `RERUN-DIFF`）。

## 7. drafts.json（AI 写）

```json
{
  "run_id": "...",
  "drafts": [
    {
      "group_id": "G01",
      "summary": "[NBS Regression] HK - BM Case7 failed due to agent record not found",
      "description": "SIT2 NBS - BM encounter \"agent record not found\" when selecting agent 40100. I checked the agent data in DB seems no data error, could you help to check? Thanks!\n\n*1st run* (2026-11-03 14:31): ...\n!Case7_fail.png|thumbnail!\n\n*2nd run (rerun)*: Failed again with the same error. The issue is reproducible.\n!Case7_rerun.png|thumbnail!\n\n*Test Data*: agent code 40100, product code UR67",
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
