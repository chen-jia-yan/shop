# 数据格式

所有文件都是 UTF-8 JSON，在本机。

## 1. 工作区 `workspace/`

```
workspace/
  runs/<批次编号>/run.json      批次和用例
  runs/<批次编号>/shots/        截图文件
  ocr.json                     截图文字识别结果
  drafts.json                  Jira 草稿
  jira_log.json                导出、提交记录
  settings.json                个人设置（上次的字段对应、审核人、已看过的规则版本）
```

### run.json

```json
{"id": "R1731760000000", "name": "LAS HK 回归 20261030", "plan": "TestPlan000015", "device": "RGT_AVD_11", "env": "U401",
 "file": "report.mhtml", "at": "2026-11-16 21:00:00", "total": 60,
 "cases": [ { 用例 }, ... ]}
```

用例：原始字段（导入时取出） + 人工记录。分析结果不保存，每次读取时用当前规则重新算。

| 字段 | 说明 |
|---|---|
| `uid` | `<批次>#<序号>`；重跑报错不同产生的第 2 次记录是 `<批次>#<序号>#2` |
| `seq`、`id`、`name`、`result`、`failed` | 顺序、用例编号、名称、执行结果、是否失败 |
| `error`、`stack`、`exceptionRaw`、`pageText`、`start`、`module`、`device` | 报错、日志、异常类型、页面/弹窗文字、开始时间、模块、设备 |
| `screenshot` | 报告里写的截图路径或网址（内嵌截图已存成文件，不在这里） |
| `shots` / `shots2` | 第 1 次 / 重跑的截图：`[{name, file, sha}]` |
| `parent`、`attempt` | 第 2 次记录指向第 1 次的 `uid` |
| `obs` | 截图观察 `{kind, text, by, at}`，`kind` 见 `ta_engine.OBS_KINDS`；`by: "AI"` 表示 AI 看图写入（结论因它而变时为待复核） |
| `ai` | AI 判断 `{cat, reason, at}`，只对规则没能确认的用例生效，页面显示“AI 判断·待复核” |
| `dataCheck`、`dataNote` | 人工核查结果（见 `ta_engine.CHECK_KINDS`）和说明 |
| `override` | 人工改判 `{cat, reason, at}` |
| `rerun`、`rerunNote`、`rerunReq`、`r2` | 重跑结果 `pass`/`fail`、说明、发起时间、第 2 次信息 `{start, screenshot, error, same}` |

### ocr.json

```json
{"tool": "ta-ocr-index", "v": 1, "images": {"<sha256>": {"w": 1920, "h": 1080, "langs": [{"lang": "en-US", "lines": [{"t": "文字", "b": [x, y, w, h]}]}]}}}
```

识别失败的图记为 `{"error": "..."}`，不会反复识别。`tools/识别截图.bat` 手动生成的 `截图识别结果.ocr.json`（`"tool": "ta-ocr"`）可以拖进导入页，或 `ta.py ocr --import`。

## 2. 分析结果（`ta.py show --json`）

每个失败用例：

```json
{"uid": "...", "case_id": "No.23", "name": "...", "attempt": 1,
 "category": "TEST_DATA", "auto_category": "TEST_DATA", "status": "confirmed", "rule_id": "DATA-LOCK", "rule_name": "数据被占用",
 "brief": "一句话结论", "why": ["依据，带证据编号"], "need": ["下一步"], "flags": ["失败时截图失败"],
 "reason_code": null, "check_kind": "lock", "phase": null, "from_ocr": false,
 "evidence": [{"id": "E1", "kind": "sys", "label": "系统提示原文", "text": "..."}],
 "rerun_plan": {"advice": "fix", "reason": "..."}, "signature": "..."}
```

`status`：`confirmed` 规则确认 / `suspected` 待复核。`category` 是最终分类（人工改判优先）。

## 3. `config/rules.json`

```json
{"tool": "ta-rules", "v": 2,
 "rules": {"env_patterns": ["..."], "noise_popups": ["..."], "mass_min_cases": 5, ...},
 "custom": [{"id": "U1", "enabled": true, "name": "批处理锁单",
             "when": {"in": ["log", "popup"], "any": ["being edited by batch"], "all": [], "none": [], "exceptions": []},
             "then": {"category": "TEST_DATA", "status": "confirmed", "brief": "", "need": "", "rerun": "fix"},
             "note": "为什么加", "by": "维护人", "at": "2026-11-16 21:30"}],
 "changelog": [{"at": "2026-11-16 21:30", "by": "张三", "what": "自定义规则：新增 U1“批处理锁单”", "note": "LAS 批处理"}]}
```

`rules` 里缺少的项用 `rules.default.json` 补上。各项含义见 `taxonomy.md`，自定义规则见 `taxonomy.md` 第 8 节。

## 4. `config/corrections.json`

```json
{"tool": "ta-corrections", "v": 1,
 "items": [{"id": "C001", "expect": {"category": "TEST_DATA", "rule": "DATA-LOCK"}, "reason": "为什么是这个分类", "by": "张三", "at": "2026-11-16 21:30",
            "from": {"run": "批次名", "case_id": "No.23", "was": {"category": "NEEDS_HUMAN", "rule": "NONE"}},
            "case": {"id": "No.23", "error": "...", "stack": "...", "pageText": "...", "obs": {...}, "ocrText": "...", "dataCheck": "..."}}]}
```

`expect.rule` 可选：有就要求命中同一条规则。样本单独分析（不含整批规律，例如“环境中断后一直没恢复”）。

## 5. `config/jira.json`

字段配置见页面“配置 → Jira 与接口”。账号不在这里：`JIRA_BASE_URL`、`JIRA_EMAIL`（Cloud）、`JIRA_API_TOKEN` 只放环境变量。
`rerunUrl` 填了之后，“一键重跑”会 POST `{"run": 批次名, "cases": [用例编号]}`。

## 6. 本机服务接口（`ta_server.py`）

页面通过这些接口工作，其他程序也可以调用（只能本机访问；POST 必须带请求头 `X-TA: 1`）。

| 接口 | 作用 |
|---|---|
| `GET /api/state` | 全部数据和分析结果 |
| `POST /api/parse` → `/api/parse/preview` → `/api/import` | 解析文件、预览字段对应、导入（`info.mode = "rerun"` 导入重跑结果） |
| `POST /api/case` | 写人工记录 `{uids, set: {obs | dataCheck | dataNote | override | rerun | ...}}` |
| `POST /api/shots/add`、`/del`、`/match` | 补截图 |
| `POST /api/rules/save`、`/reset`、`/import`；`GET /api/rules/file` | 判断规则 |
| `POST /api/custom/save`、`/test` | 自定义规则 |
| `POST /api/corrections/add`、`/delete` | 纠错样本 |
| `POST /api/jira/new`、`/update`、`/csv`、`/payload`、`/submit`、`/cfg` | Jira |
| `POST /api/rerun/send` | 发起重跑 |
| `GET /api/export/cases.csv?run=` | 导出失败分诊 |
