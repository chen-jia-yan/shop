---
name: regression-triage-jira
description: 分析自动化回归测试的失败用例。导入执行结果（报告网页 .mhtml/.html、JSON、CSV、JUnit、Allure），自动识别截图文字，按有证据的规则把每个失败用例分成“环境问题 / 弹窗干扰 / 脚本问题 / 测试数据问题 / 疑似产品缺陷 / 需人工判断”，给出判断依据和重跑建议；在本机页面上复核、重跑、分派，一个用例起草一张 ROTQA 格式的 Jira 单，人工审核后导出或提交。用于：回归跑完有失败用例、“分析本次回归失败”“帮我把失败用例提 Jira”“这些 case 为什么挂了”“这个弹窗是哪来的”“打开测试分析助手”。
compatibility: Windows + Python 3.10+（只用 Python 自带的库，不用 pip 安装）。截图文字识别用 Windows 自带 OCR。提交 Jira 需要本机环境变量 JIRA_BASE_URL、JIRA_API_TOKEN（Cloud 还要 JIRA_EMAIL）。
metadata:
  owner: IT QA team (Guangzhou)
  version: "2.0.0"
  jira-project: ROTQA
---

# 回归失败分诊与 Jira 起草（测试分析助手）

这个 skill 自带一个本机页面（`assets/`）。页面只负责显示和操作，**分析、导入、截图识别、Jira 起草和提交全部由 `scripts/` 里的 Python 完成**，页面和命令行用的是同一套判断，结果相同。服务只监听 127.0.0.1，数据不出本机。

## 怎么用

| 场景 | 做法 |
|---|---|
| 测试同事日常使用 | 双击桌面的“测试分析助手”（第一次运行 `python scripts/ta.py shortcut` 创建；没有命令行窗口），或双击 `打开测试分析助手.bat`。不要让 AI 运行 `ta.py open`（服务会一直运行，AI 会卡住）。导入报告 → 失败分诊 → 重跑 → 分派 → Jira 提报 |
| 用户让 AI 分析一份报告 | `python scripts/ta.py analyze <报告文件> --name 批次名 --env U401`，读取输出；需要细节用 `python scripts/ta.py show <批次> --json` |
| 导入重跑结果 | 页面“数据导入”选“重跑结果”；或 `ta.py analyze <文件> --rerun-of <批次编号>` |
| 改规则、改代码之后 | `python scripts/ta.py check`；改了 scripts/ 代码再跑 `python evals/selftest.py` |

导入后会自动在后台识别新截图的文字（`tools/识别截图.bat`，Windows 自带 OCR，不弹窗口），识别完自动重新分析，不需要手动导入识别结果。报告网页里直接嵌入的截图、MHTML 里的截图都会自动取出来。

## AI 分析时的步骤

1. 用 `ta.py analyze` 导入并分析（或用户已在页面导入，用 `ta.py list` / `ta.py show` 读取）。
2. 先看整批：环境从哪个用例开始中断、同一报错大面积出现（结果里已写进依据）。
3. 对 `confirmed` 的结论直接采用；对“待复核”和“需人工判断”，按 `references/root-cause-method.md` 看证据，告诉用户还缺什么（看哪张截图、查哪条数据）。
4. 用户确认的结论，让用户在页面上记录（截图观察、核查结果、人工改判），不要自己改数据文件。
5. Jira 在页面“Jira 提报”里起草、审核、提交。

## 铁律

1. **结论必须有证据。** 引用证据原文和编号（如 `E3`）。证据不足就是“需人工判断”，写明还缺什么，不猜。
2. **规则结论优先。** `confirmed` 的结论 AI 不改；AI 只能根据看得见的内容补充 `suspected` 和“需人工判断”的用例，并写明看到了什么。
3. **截图自动识别的文字只是线索。** 依据它得出的结论一律“待复核”，要人核对截图后才算数。
4. **数据库状态不能推测。** “数据不存在 / 数据正常”只能来自人工核查结果。
5. **业务报错弹窗不是干扰。** 只有 `noise_popups` 里的公告、会话、浏览器提示才算干扰。
6. **未经人工审核不写入 Jira。** 只有页面上“审核通过”的单才能导出或提交；提交前先预检（查重）。
7. **账号只放环境变量。** Jira Token 不写进页面、配置文件或对话。
8. **数字由脚本统计。** 用例数、比例、时间直接引用结果，不让 AI 算。

## 文件

```
打开测试分析助手.bat      双击启动
SKILL.md / README.md
assets/                  页面（只有显示和操作）
scripts/
  ta.py                  命令行入口：open / analyze / list / show / export / ocr / check
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
  vision.example.yaml    视觉模型（暂未启用）
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
