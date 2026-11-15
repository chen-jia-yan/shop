---
name: regression-triage-jira
description: 分析自动化回归测试的失败用例，先按有证据的规则把每个用例分成“弹窗干扰 / 脚本问题 / 环境问题 / 测试数据问题 / 产品缺陷 / 需人工判断”六类，再根据原因列出需要重跑的用例，人工确认后重跑；一个用例一张单，查重后起草符合 ROTQA 格式的 Jira 单（Summary、Description、Environment、Priority、Components、Labels），生成审核表，审核通过后批量建单并上传截图。用于：回归跑完有失败用例、用户说“分析本次回归失败”“帮我把失败用例提 Jira”“看看这些 case 为什么挂了”“这个弹窗是哪来的”。
compatibility: 需要 Python 3.10+，可访问 Jira Cloud（REST API 或 Atlassian Rovo MCP），可读取本次回归的结果目录（Allure 结果、JUnit XML、标准化 JSON，或“测试分析助手”页面保存的工作文件）。
metadata:
  owner: IT QA team (Guangzhou)
  version: "1.3.0"
  jira-project: ROTQA
---

# 回归失败分诊与 Jira 起草

## 这个 Skill 做什么、不做什么

**做：**
1. 读取一次回归的全部失败用例（报错信息、堆栈、截图、弹窗证据、环境信息）。
2. 按 `references/taxonomy.md` 的规则逐个分析原因并分类；分类不依赖重跑。
3. 根据原因列出需要重跑的用例（建议立即重跑 / 处理后再重跑 / 不需要重跑），用户确认后才重跑；重跑结果只用来确认判断，不改变分类。
4. 默认一个用例一张 Jira 单（环境问题合并为一张）；同一原因的其他用例列为相关用例。
5. 在 Jira 中查重，已有未关闭的同类单就建议“追加评论”而不是新建。
6. 按 `references/jira-template.md` 起草每张单的 Jira 内容。
7. 生成审核表，**由测试人员审核、修改、标记“通过”**。
8. 只对标记“通过”的行建单或追加评论，并上传截图。

**不做：**
- 不替人决定能否上线，不关闭、不转派、不修改已有 Jira 单的状态。
- 不连接生产环境，不读取生产数据。
- 不在没有证据的情况下给出根因结论。

## 铁律（每一步都必须遵守）

1. **结论必须有证据。** 每个分类、每个根因描述都要引用证据原文：异常类型、报错行、弹窗文字、截图观察、数据核查结果，引用时写明证据编号（如 `E3`）。
2. **证据不足就说不知道。** 规则没命中、证据互相矛盾、截图看不清，一律归为 `NEEDS_HUMAN`，并写明还缺什么信息。不得为了“分完类”而猜测。
3. **规则结论优先于 AI 判断。** `classify_rules.py` 给出 `status: confirmed` 的分类，AI 不得改动；AI 只能处理 `suspected` 和 `NEEDS_HUMAN`，而且只能根据截图或报错里**看得见**的内容升级或降级，并写明看到了什么。
4. **数据库状态不能靠推测。** “数据不存在”“数据正常”只能来自测试人员填写的核查结果（页面上选择的核查结果，或 `data_checks.yaml`），或公司批准的只读查询脚本的输出。截图上有“record not found”只说明系统返回了这个提示，不代表数据真的不存在。
5. **业务报错弹框不是干扰。** 像 “agent record not found” 这类系统返回的错误提示，按测试数据或产品缺陷处理，不能归为弹窗干扰。只有 `config/rules.json` 里 `noise_popups` 列出的公告、Cookie、会话提示、浏览器提示才算干扰。
6. **未经人工审核不得写入 Jira。** 审核表中“审核状态”不是“通过”或“追加到已有单”的行，`submit_jira.py` 一律跳过。默认是演练模式，必须加 `--confirm` 才真正写入。
7. **不泄露个人信息。** 任何内容交给模型阅读或写入 Jira 之前，先经过 `common.mask_pii`。只保留测试需要的业务编码（agent code、product code、保单号），姓名、证件号、手机号、邮箱一律替换。
8. **数字和日期不让 AI 算。** 用例数量、通过率、时间等由脚本统计后直接引用。
9. **先看整批，再看单个。** 逐条判断之前，先看断崖（某个用例之后连续因环境失败到结束）、通过用例中出现的同样报错、同功能通过/失败对比、残留窗口（`references/root-cause-method.md` 第 1 步）。大面积环境原因的失败合并成一张单，不逐个提单；其他原因默认一个用例一张单。
10. **看异常链的第一段，不看最后一行。** Python 日志的最后一行几乎总是 `SystemExit: 0` 或截图函数的 `screen grab failed`，都不是原因。先读步骤日志里的系统原话（`pop-up error:`、`Validation Error:`），再读最先发生的异常和项目代码里的失败位置。
11. **报错是现象，不是根因。** 结论分“现象 / 直接原因 / 根因”三层，证据支持到哪一层就写到哪一层，其余写“待确认”。掩盖型报错（`'bool'/'NoneType' object ...`）不得直接判为脚本问题。
12. **截图是 C 级证据。** 先验证截图有效（不是 `screen grab failed`、时间/窗口/保单号对得上），只描述看得见的东西；勾选框、灰色按钮、密集数字不凭截图下结论（`references/evidence-and-screenshots.md`）。

13. **先分类，后重跑。** 不得在分类之前把失败用例全部重跑。先由 `classify_rules.py` 给出原因和重跑建议（`rerun_plan.json`），把名单交给用户确认，再用 `rerun_failed.py --plan` 只重跑确认过的用例。
14. **重跑结果不是分类。** 没有“重跑可过”这一类。重跑通过只说明这次失败是偶发的（不提单，但保留原分类和原因，连续出现要处理）；重跑仍失败且报错相同，说明可以复现，写进同一张单的 *2nd run*；报错不同，第 2 次单独分析、单独提单。
15. **页面和 skill 是同一套判断。** 分类由 `scripts/ta_engine.py` 完成，它是“测试分析助手”页面 `engine.js` 的 Python 版：规则编号、判断顺序、一句话结论完全相同。规则只有一份 `config/rules.json`（页面“判断规则 → 导出规则 → 下载规则文件”得到的就是它）；人工记录（截图观察、核查结果、人工改判、重跑结果）放在工作文件 `workspace.json` 里，页面和 skill 都能读写。不要另写一套判断，也不要手工改 classified.json 里的分类。改了判断逻辑，`engine.js` 和 `ta_engine.py` 一起改，并运行 `python evals/check_consistency.py`，输出“一致”才算完成。
16. **截图必须打码后才能交给模型。** 交给模型看的截图先用页面“下载打码截图”或同样的打码规则处理（证件号、手机号、邮箱、卡号、人名清单）；没有文字识别结果的截图无法定位个人信息，不发给模型。脚本写出的 classified.json、workspace.json 里的文字都已脱敏。

## 页面与 skill 怎么配合

```
            ┌──────── 测试分析助手（页面，离线）────────┐
报告/表格 ─▶│ 导入 → 自动分析 → 看截图、记观察、选核查结果 │── 保存工作文件 ─▶ workspace.json
            └──────────────────────────────────────────┘                     │
                     ▲  打开工作文件                                          ▼
                     └──── triage_runs/<run_id>/workspace.json ◀── skill（load_results → classify_rules → … → Jira）
```

- 从页面开始：页面导入、复核后“保存工作文件”，skill 用 `load_results.py --format workspace` 读取，`classify_rules.py --workspace` 带上页面上的人工记录。
- 从 skill 开始：`classify_rules.py` 每次都会写出 `triage_runs/<run_id>/workspace.json`；不熟悉命令的同事在页面“打开工作文件”，看截图、补人工记录，保存后交回 skill 再跑一次第 2 步。
- 两边对同一份数据给出的分类、规则、重跑建议相同；不同说明规则文件不一致，按页面提示统一后再继续。

## 运行前检查

1. 确认 `config/config.yaml` 存在（从 `config/config.example.yaml` 复制并填写）。如果不存在，停下来请用户先配置，不要猜测 Jira 字段。
2. 确认环境变量 `JIRA_BASE_URL`、`JIRA_EMAIL`、`JIRA_API_TOKEN` 已设置（只有查重和建单需要）。
3. 确认用户告诉了你本次回归的结果目录和运行编号；如果没有，询问用户。
4. 每次运行使用独立的工作目录：`triage_runs/<run_id>/`。

## 工作流程

按顺序执行。每一步结束后检查输出文件存在且非空，再进入下一步；任何一步失败，向用户报告错误原文，不要跳过。

```
1 读取失败结果 → 2 规则分类（含重跑建议）→ 3 AI 复核疑似 → 4 确认重跑名单并重跑 → 5 带上重跑结果再分类
→ 6 整理成单（一个用例一张）→ 7 Jira 查重 → 8 起草并校验 → 9 生成审核表（停下等审核）→ 10 提交
```

### 第 1 步：读取失败结果

```bash
python scripts/load_results.py --input <结果目录或工作文件> --format <allure|junit|normalized|workspace> \
    --run-id <run_id> --out triage_runs/<run_id>/failures.json
```

- 格式说明见 `references/data-contract.md`。`workspace` 是页面“保存工作文件”得到的文件。
- 读取完成后告诉用户：失败用例总数、缺少截图的数量、缺少弹窗证据的数量。
- 如果大部分用例缺少弹窗证据，提醒用户：测试框架还没接入 `scripts/popup_evidence.py`，弹窗问题会大量落入“需人工判断”。
- 截图文字识别（可选，Windows）：把报告文件或截图文件夹拖到 `tools/识别截图.bat` 上，用 Windows 自带 OCR 生成 `截图识别结果.ocr.json`（不安装软件，截图不出本机）。第 2 步用 `--ocr` 带上它，页面和 skill 用的是同一个结果文件、同样的对应方式（按截图指纹）。
- 模型识图（可选）：接口和指令写在 `config/vision.yaml`，用法和结果核对规则见 `references/vision-model.md`。默认关闭（`mode: off`）；开启后模型只描述截图，结论仍须人工确认；截图先打码（铁律 16）。

### 第 2 步：规则分类（不先重跑）

```bash
python scripts/classify_rules.py --failures triage_runs/<run_id>/failures.json \
    --out triage_runs/<run_id>/classified.json \
    [--workspace <页面保存的工作文件>] [--ocr <截图识别结果.ocr.json>] \
    [--data-checks triage_runs/<run_id>/data_checks.yaml]
```

- 规则默认读 `config/rules.json`。工作文件里的规则与它不同时脚本会提示，以 `config/rules.json` 为准。
- 这一步不需要 `--rerun`。每个用例先按证据判断原因和分类。
- 需要人工核查的用例（业务报错、数据被占用、缺少配置、日期设置失败）会列在 `data_checks.todo.yaml`，每项写明要查什么、可选结果。两种方式填写，效果相同：在页面打开 `workspace.json` 直接选核查结果后保存；或在 `data_checks.yaml` 里填写（格式见 data-contract.md 第 4 节）。填完重新运行本步。
- 脚本同时给每个用例写入重跑建议 `rerun_plan`，并在同目录生成 `rerun_plan.json`：
  - `go` 建议立即重跑：环境问题（确认环境恢复后）、弹窗干扰、环境中断起点附近的用例、偶发类报错；
  - `fix` 处理后再重跑：测试数据问题（先补数据或释放数据）、脚本问题（先修脚本）、待数据核查、证据不足（先判断原因）；
  - `no` 不需要重跑：产品缺陷等重跑结果不会变的情况。
  标准见 `references/taxonomy.md` 的“重跑标准”。

### 第 3 步：AI 复核疑似分类（只看证据，不推测）

**开始之前先完整读一遍 `references/root-cause-method.md`，按它的 7 个步骤逐条复核。** Windows 桌面程序（LAS 等）的报错含义查 `references/pywinauto-desktop.md`；截图判读按 `references/evidence-and-screenshots.md`。

读取 `classified.json` 中 `status` 为 `suspected` 或类别为 `NEEDS_HUMAN` 的用例，逐个查看截图和报错：

- 先看每个用例的 `brief`（一句话结论）、`why`（判断依据，带证据编号）、`need`（还需确认什么）、`log_summary`（失败位置、业务成功标记、当时打开的窗口）和 `flags`（如“环境中断边界”“失败时截图失败”“有残留窗口”）。有“失败时截图失败”的用例没有有效截图，不要用报告里的图片下结论。
- `from_ocr: true` 的用例：结论用到了截图自动识别的文字，可能识别有误，先核对截图。
- `phase: verify` 的用例：业务操作已经提交成功，失败在结果校验阶段，不要写成业务功能缺陷。
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
- 每条复核结论都要按 `root-cause-method.md` 第 6 步的格式写出“现象 / 直接原因 / 根因 / 依据 / 反证检查 / 下一步”，写进 `ai_review.analysis`。

### 第 4 步：确认重跑名单并重跑

1. 把 `rerun_plan.json` 的名单按“建议立即重跑 / 处理后再重跑 / 不需要重跑”列给用户，每个用例附一句原因。
2. **等用户确认**要重跑哪些（可以增减）。`fix` 类的用例要等用户说数据或脚本已处理好。
3. 只重跑确认过的用例：

```bash
# 只重跑 go 类
python scripts/rerun_failed.py --failures triage_runs/<run_id>/failures.json \
    --plan triage_runs/<run_id>/rerun_plan.json --config config/config.yaml \
    --out triage_runs/<run_id>/rerun.json
# fix 类已处理好，一起重跑：加 --include-fix；用户增减的用例：用 --only Case7,Case9
```

- 默认每个用例重跑 1 次（`rerun.attempts` 可配置）。
- 用户说不能重跑（例如环境已经下线）时加 `--skip`，在最终汇报中说明“未重跑”。不重跑不影响分类。

### 第 5 步：带上重跑结果再分类

```bash
python scripts/classify_rules.py --failures triage_runs/<run_id>/failures.json \
    --rerun triage_runs/<run_id>/rerun.json \
    [--workspace triage_runs/<run_id>/workspace.json] [--data-checks triage_runs/<run_id>/data_checks.yaml] \
    --out triage_runs/<run_id>/classified.json
```

- 每个重跑过的用例会多一个 `rerun_result`：`pass`（重跑通过，偶发）、`fail_same`（同样报错，可复现）、`fail_diff`（报错不同）。
- **分类不会因为重跑结果改变。** `pass` 的用例保留原分类和原因，只是不提单；同一用例连续多次偶发，在汇报里提醒处理。
- 第 3 步写的 `ai_review` 会自动保留（脚本按用例编号从原来的 classified.json 读回）。

### 第 6 步：整理成单（默认一个用例一张）

```bash
python scripts/group_by_cause.py --classified triage_runs/<run_id>/classified.json \
    --rerun triage_runs/<run_id>/rerun.json \
    --config config/config.yaml --out triage_runs/<run_id>/groups.json
```

- `grouping.one_case_per_ticket: true`（默认）：一个用例一个组、一张单；同一原因的其他用例写在 `related_case_ids`，供查重和汇报。
- 环境问题仍合并为一组，交给环境负责人。
- 重跑 `pass` 的用例 `needs_jira = false`；`fail_diff` 的第 2 次执行单独成组（`group_id` 以 `-2` 结尾，分类为需人工判断），要单独分析。
- 不要自行调整分组；发现同组里报错明显不同，在汇报中指出。

### 第 7 步：Jira 查重

```bash
python scripts/check_duplicates.py --groups triage_runs/<run_id>/groups.json \
    --config config/config.yaml --out triage_runs/<run_id>/duplicates.json
```

- 只对需要建单的组查重；同一原因的多个用例很可能命中同一张已有单，这时建议“追加到已有单”。
- 查重结果只是候选，最终是否追加由审核人决定。

### 第 8 步：起草 Jira 内容

严格按照 `references/jira-template.md`，为每个需要建单的组起草内容，写入 `triage_runs/<run_id>/drafts.json`。写之前先看 `references/examples/` 中的范例。

起草要求：
- **Summary**：`[{system} Regression] {market} - {module} {case_id} failed due to {cause}`，`cause` 用英文，不超过 12 个单词，必须来自证据（例如业务报错原文 “agent record not found”）。
- **Description**：简洁。先用一两句话说清楚“在哪个环境、哪个功能、做什么操作时出现什么问题，请帮忙看看”，再写 `*1st run*` 的报错和截图；重跑同样失败时写 `*2nd run*` 和截图；最后是测试数据（agent code、product code、保单号）。不写长篇分析，缺的信息不要编。
- **Environment**：直接使用 `groups.json` 中的 `environment` 字段，不要改写。
- **claims**：Description 里的每一条事实都要在 `claims` 中列出并标注证据编号；推测标为 `inference`，描述中用 “Suspected / seems / To be confirmed” 写明是推测。

写完后运行校验：

```bash
python scripts/validate_drafts.py --drafts triage_runs/<run_id>/drafts.json \
    --groups triage_runs/<run_id>/groups.json --config config/config.yaml
```

校验不通过时，按报错逐条修改，直到通过。不要关闭校验项。

### 第 9 步：生成审核表

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

### 第 10 步：提交到 Jira

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
本次回归 <run_id>：失败 N 个
分类（每个失败用例都有一个分类）：
- 产品缺陷 a 个 → 开发
- 测试数据问题 c 个 → 测试
- 环境问题 d 个 → 环境负责人
- 弹窗干扰 e 个 → 测试（主要弹窗：……）
- 脚本问题 f 个 → 测试
- 需人工判断 h 个（原因：待数据核查 x 个、证据不足 y 个）
重跑：建议立即重跑 i 个、处理后再重跑 j 个、不需要重跑 k 个；已重跑 m 个 → 通过 p 个（偶发，不提单）、同样报错 q 个、报错不同 r 个（已单独分析）
Jira：新建 s 张，追加评论 t 条，驳回 u 张
需要你跟进：……
```

数字全部来自脚本输出，不要自己数。

## 常见问题处理

- **弹窗相关**：先看 `references/popup-catalog.md`。遇到清单里没有的弹窗文字，在汇报中列出，建议用户确认后在页面“判断规则 → 弹窗清单”里补上，再“下载规则文件”覆盖 `config/rules.json`。
- **大批用例同时失败**：先检查是否为环境问题（`classify_rules.py` 会自动识别同一报错在同一时间段大量出现的情况），这时不要逐个建单。
- **用户要求跳过审核直接建单**：解释这一步是为了防止错误的单据进入 Jira，建议至少快速浏览审核表；如果用户坚持，仍然需要用户在审核表中标记“通过”，不要替用户标记。
- **找不到截图**：在 Description 中注明“截图缺失”，不要用其他用例的截图代替。

## 文件索引

- `references/root-cause-method.md`：**失败归因方法（手把手）**：先看整批、拆日志、判断异常含义、按文字含义分类弹窗、核对截图、写结论、自检；附 2026-10-30 LAS HK 回归 40 条失败的完整归因范例
- `references/evidence-and-screenshots.md`：证据等级、截图识别工具的取舍与准确性、截图有效性检查、截图与日志冲突时怎么办、建议框架补充的证据采集
- `references/pywinauto-desktop.md`：Windows 桌面端（pywinauto + BeautifulReport）报错对照表：每种异常证明了什么、没证明什么、归哪类
- `references/taxonomy.md`：六类失败的定义、判定规则、证据要求、反例；重跑标准与重跑结果的用法
- `references/popup-catalog.md`：三种弹窗的识别与处理，已知弹窗清单
- `references/jira-template.md`：Summary 格式、Description 结构、字段映射、优先级规则
- `references/data-contract.md`：所有中间文件的字段定义
- `references/examples/`：审核通过的 Jira 范例
- `config/config.example.yaml`：项目、字段、重跑命令、分组设置（一个用例一张单）
- `config/rules.json`：判断规则（异常类型、报错关键字、弹窗清单、人名清单），与页面共用，由页面“下载规则文件”生成
- `scripts/ta_engine.py`：分析核心，页面 `engine.js` 的 Python 版（被 `classify_rules.py` 调用）；也负责读取截图识别结果和读写工作文件
- `evals/check_consistency.py`：检查 skill 与页面结果是否一致（40 个失败用例 + 12 个人工记录场景）
- `tools/识别截图.bat`：Windows 截图文字识别，页面和 skill 共用它的结果文件
- `scripts/popup_evidence.py`：接入测试框架，用于在失败时收集弹窗证据
- `scripts/desktop_evidence.py`：接入桌面端测试框架，失败时采集窗口清单、对话框文字、控件状态；用例开始前检查桌面是否可交互
- `evals/`：用历史人工分类结果检验分类准确率；`evals/las_hk_20261030/` 是第一批真实数据样本
