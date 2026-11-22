---
name: regression-triage-jira
description: 分析自动化回归测试的失败用例。导入执行结果（报告网页 .mhtml/.html、JSON、CSV、JUnit、Allure），自动识别截图文字，按有证据的规则把每个失败用例分成“环境问题 / 弹窗干扰 / 脚本问题 / 测试数据问题 / 疑似产品缺陷 / 需人工判断”，给出判断依据和重跑建议；在本机页面上复核、重跑、分派，一个用例起草一张 ROTQA 格式的 Jira 单，人工审核后导出或提交。用于：回归跑完有失败用例、“分析本次回归失败”“帮我把失败用例提 Jira”“这些 case 为什么挂了”“这个弹窗是哪来的”“打开测试分析助手”。
compatibility: Windows + Python 3.10+（只用 Python 自带的库，不用 pip 安装）。截图文字识别用 Windows 自带 OCR。提交 Jira 需要本机环境变量 JIRA_BASE_URL、JIRA_API_TOKEN（Cloud 还要 JIRA_EMAIL）。
metadata:
  owner: IT QA team (Guangzhou)
  version: "2.1.0"
  jira-project: ROTQA
---

# 回归失败分诊与 Jira 起草（测试分析助手）

这个 skill 自带一个本机页面（`assets/`）。页面只负责显示和操作，**分析、导入、截图识别、Jira 起草和提交全部由 `scripts/` 里的 Python 完成**，页面和命令行用的是同一套判断，结果相同。服务只监听 127.0.0.1，数据不出本机。

## 怎么用

| 场景 | 做法 |
|---|---|
| 测试同事日常使用 | 双击桌面的“测试分析助手”（第一次运行 `python scripts/ta.py shortcut` 创建；没有命令行窗口），或双击 `打开测试分析助手.bat`。导入报告 → 失败分诊 → 重跑 → 分派 → Jira 提报 |
| 用户把报告交给 AI 分析 | 按下面“AI 分析时的步骤”走完：规则先判 → AI 看截图、补判断 → 打开页面给用户复核。最终产物就是页面 |
| 导入重跑结果 | 页面“数据导入”选“重跑结果”；或 `ta.py analyze <文件> --rerun-of <批次编号>` |
| 改规则、改代码之后 | `python scripts/ta.py check`；改了 scripts/ 代码再跑 `python evals/selftest.py` |

导入后会自动在后台识别新截图的文字（`tools/识别截图.bat`，Windows 自带 OCR，不弹窗口），识别完自动重新分析。报告网页里直接嵌入的截图、MHTML 里的截图都会自动取出来。

## AI 分析时的步骤

规则只认关键字，不懂意思，也看不到图片里的内容。AI 负责补这两块：**看截图**、**读懂报错的意思**。AI 的结论写进工作区，页面上显示为“AI 判断·待复核”，由人确认。

1. **规则先判**：`python scripts/ta.py analyze <报告文件> --name 批次名 --env U401`（用户已在页面导入的，用 `ta.py list` 找批次）。
2. **确认自己能看图**：`python scripts/ta.py shots <批次>` 列出要看的用例（规则没能确认的）和截图完整路径。先打开第一张截图：
   - 能看到图片内容 → 继续第 3 步；
   - 看不到图片（当前模型不支持图片，或只拿到文件名/乱码）→ 告诉用户“当前模型不能看图，只能依据报错和截图识别文字（`ocr_text`）判断”，跳过看图，只做第 4 步。
3. **逐条看截图**，对照 `brief`（规则的判断）和 `error`，写下看到的现象：`kind` 从 `obs_kinds` 里选一个，`text` 照抄弹窗或页面上的文字（看不清就不写，不猜）。
4. **补判断**：截图和报错都看过后，规则仍判为“需人工判断”或“待复核”、而 AI 能从报错的意思判断的，写 `ai`：`cat` 从 `categories` 里选，`reason` 写一句依据（引用报错原文或截图里看到的内容）。判断不了就不写。
5. **写入并重新分析**：把结果存成 `ai.json`，运行 `python scripts/ta.py record ai.json`，读取打印出的前后变化：
   ```json
   [{"uid": "R3#12", "obs": {"kind": "popup", "text": "Policy is being edited by batch job"}},
    {"uid": "R3#15", "obs": {"kind": "normal"}, "ai": {"cat": "SCRIPT_ISSUE", "reason": "截图上 Submit 按钮可见，日志报 ElementNotFoundError，定位条件写错"}}]
   ```
   要撤销某条，写 `"obs": null` 或 `"ai": null`。
6. **打开页面**：`python scripts/ta.py open --bg`（后台启动，立即返回；不要用不带 `--bg` 的 `open`，会卡住）。告诉用户：一共几条、改了哪几条、哪些仍需人工判断；复核、改分类、重跑、分派、提 Jira 都在页面上做。

## 铁律

1. **结论必须有证据。** 引用证据原文和编号（如 `E3`）。证据不足就是“需人工判断”，写明还缺什么，不猜。
2. **规则结论优先。** `confirmed` 的结论 AI 不改；AI 只补“待复核”和“需人工判断”的用例（已确认的用例，写了 obs 或 ai 也不会改变结论）。
3. **AI 和截图识别的结论只是线索。** AI 看图、AI 判断、截图识别文字得出的结论一律“待复核”，要人在页面上确认后才算数。
4. **只用 `ta.py record` 写入。** 不直接改 `workspace/` 里的文件；页面开着时 `record` 会通过页面的服务写入，页面刷新即可看到。
5. **数据库状态不能推测。** “数据不存在 / 数据正常”只能来自人工核查结果。
6. **业务报错弹窗不是干扰。** 只有 `noise_popups` 里的公告、会话、浏览器提示才算干扰。
7. **未经人工审核不写入 Jira。** 只有页面上“审核通过”的单才能导出或提交；提交前先预检（查重）。
8. **账号只放环境变量。** Jira Token 不写进页面、配置文件或对话。
9. **数字由脚本统计。** 用例数、比例、时间直接引用结果，不让 AI 算。

## 文件

```
打开测试分析助手.bat      双击启动
SKILL.md / README.md
assets/                  页面（只有显示和操作）
scripts/
  ta.py                  命令行入口：open / analyze / list / show / shots / record / export / ocr / check
  ta_engine.py           判断逻辑（唯一一份）
  ta_import.py           读取报告：html/mhtml（含内嵌截图）、json、allure、junit、csv
  ta_ocr.py              自动调用识别截图.bat，结果按图片内容缓存
  ta_store.py            工作区：批次、人工记录、截图、规则、纠错样本、修改记录、Jira 草稿
  ta_jira.py             Jira 起草、提交前检查、CSV、提交（urllib）
  ta_server.py           本机服务（127.0.0.1）
config/
  rules.json             判断规则 + 自定义规则 + 修改记录（团队共用）
  rules.default.json     默认规则（恢复默认、升级补新项用）
  corrections.json       纠错样本（团队共用）
  jira.json              Jira 字段配置（第一次保存后生成）
tools/识别截图.bat        截图文字识别（也可以手动把报告拖上去）
evals/                   check_consistency.py（基准样本）、selftest.py（自检）
references/              分类标准、分析方法、维护方法、数据格式、Jira 模板
workspace/               运行时数据（本机，不要提交到代码库）
```

## 参考

- 分类标准：`references/taxonomy.md`（唯一标准，含自定义规则）
- 分析方法：`references/root-cause-method.md`、`references/pywinauto-desktop.md`、`references/popup-catalog.md`、`references/evidence-and-screenshots.md`
- 维护（加规则、纠错样本、改代码）：`references/maintenance.md`
- 数据格式：`references/data-contract.md`
- Jira 格式：`references/jira-template.md`
