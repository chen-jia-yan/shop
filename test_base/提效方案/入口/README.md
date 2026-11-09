# regression-triage-jira

回归测试失败分诊 + Jira 批量起草 Skill。按开放的 Agent Skills 规范编写（`SKILL.md` + `references/` + `scripts/`），可在 Claude Code、GitHub Copilot、Codex、Cursor 等支持 Skills 的 AI 工具中使用；所有脚本也可以脱离 AI 单独运行。

## 目录

```
regression-triage-jira/
├── SKILL.md                      # AI 执行的步骤、铁律、汇报格式
├── README.md                     # 本文件：安装、配置、验证
├── requirements.txt
├── config/
│   ├── config.example.yaml       # 复制为 config.yaml 后填写
│   └── rules.yaml                # 分类用的异常类型、报错关键字、弹窗清单
├── references/
│   ├── taxonomy.md               # 七类失败的判定规则（唯一标准）
│   ├── popup-catalog.md          # 三种弹窗的识别、处理、已知清单
│   ├── jira-template.md          # ROTQA 标题格式、描述 8 小节、字段规则
│   ├── data-contract.md          # 所有中间文件的字段定义
│   └── examples/                 # 3 个起草范例（含“不该起草”的反例）
├── scripts/
│   ├── common.py                 # 公共函数：脱敏、匹配、报错特征标准化
│   ├── popup_evidence.py         # 放进测试仓库：失败时收集弹窗证据（pytest 插件）
│   ├── load_results.py           # 1 读取 Allure / JUnit / 标准化 JSON
│   ├── rerun_failed.py           # 2 自动重跑失败用例
│   ├── classify_rules.py         # 3 规则分类（确定性，不调用模型）
│   ├── group_by_cause.py         # 5 按根因合并
│   ├── jira_client.py            # Jira Cloud REST API 封装
│   ├── check_duplicates.py       # 6 Jira 查重
│   ├── validate_drafts.py        # 7 校验 AI 起草的内容
│   ├── build_review_sheet.py     # 8 生成审核表 review.xlsx + 预览 review.html
│   └── submit_jira.py            # 9 演练 / 提交，查询字段 ID
└── evals/
    ├── eval_classify.py          # 分类准确率评测
    └── sample_run/               # 8 个虚构用例，覆盖七类主要路径
```

## 一、安装

```bash
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml     # Windows: copy
```

## 二、用示例数据验证（不需要 Jira，不需要测试环境）

```bash
mkdir -p triage_runs/sample
python scripts/load_results.py --input evals/sample_run/results.json --format normalized \
    --run-id sample --config config/config.example.yaml --out triage_runs/sample/failures.json
python scripts/classify_rules.py --failures triage_runs/sample/failures.json \
    --rerun evals/sample_run/rerun.json --rules config/rules.yaml \
    --data-checks evals/sample_run/data_checks.yaml --config config/config.example.yaml \
    --out triage_runs/sample/classified.json
python evals/eval_classify.py --classified triage_runs/sample/classified.json \
    --labels evals/sample_run/labels.csv
python scripts/group_by_cause.py --classified triage_runs/sample/classified.json \
    --config config/config.example.yaml --out triage_runs/sample/groups.json
```

预期分类：S01 产品缺陷（BIZ2）、S02 测试数据（BIZ1）、S03 环境问题（ENV2，虽然重跑通过）、S04 弹窗干扰（POP2）、S05 重跑可过（R1）、S06 脚本问题（SCR2）、S07 需人工判断（BIZ3，待核查 agent 40200）、S08 弹窗干扰（POP1）。评测应输出“达标”。同时会生成 `triage_runs/sample/data_checks.todo.yaml`，里面只有 `agent_code=40200`。

## 三、接入真实环境

1. **接入弹窗证据收集**：把 `scripts/popup_evidence.py` 复制到测试仓库，在 `conftest.py` 加 `pytest_plugins = ["popup_evidence"]`。说明见文件顶部。不接入也能用，但弹窗类问题大多会落入“需人工判断”。
2. **给用例打标签**：至少提供 `case_id`、`market`、`module`、`system`（Allure 用 `allure.label`，JUnit 用 `record_property`）。标题里的市场和模块来自这里。
3. **配置重跑命令**：填写 `config.yaml` 的 `rerun.command` 和 `rerun.workdir`。
4. **配置 Jira**：
   ```bash
   set JIRA_BASE_URL=https://<公司>.atlassian.net
   set JIRA_EMAIL=<你的邮箱>
   set JIRA_API_TOKEN=<API Token>
   python scripts/submit_jira.py --discover-fields --config config/config.yaml
   ```
   把输出中 System 字段的 fieldId 填入 `jira.fields.system`，并核对问题类型名称、必填字段。
5. **核对模板**：请同事B对照真实建单页面，核对 `references/jira-template.md`，并把 3–5 张写得好的真实 Jira 单替换到 `references/examples/`。
6. **补充规则**：把团队实际遇到的弹窗文字、业务报错写入 `config/rules.yaml` 和 `popup-catalog.md`。

## 四、上线前评测

1. 取最近 1–3 次回归中已经人工分析过的失败用例（建议 ≥ 100 个），整理成 `evals/labeled_cases.csv`。
2. 跑第 1、3 步得到 `classified.json`，再运行 `evals/eval_classify.py`。
3. 达标标准（可调整）：confirmed 用例准确率 ≥ 80%；真实缺陷被分到其他类的比例 ≤ 5%。
4. 每次修改 `rules.yaml` 后重新评测。

## 五、安全说明

- 只连接测试环境；数据核查必须由人或公司批准的只读脚本完成。
- 写入 Jira 前必须人工审核；`submit_jira.py` 默认演练，加 `--confirm` 才写入；每张单带 `triage-<run>-<group>` 标签防止重复。
- 文本在进入模型和写入 Jira 前都会脱敏（证件号、电话、邮箱、通过 Luhn 校验的卡号，以及测试数据中的姓名字段）。正则无法覆盖所有姓名，测试数据中的姓名字段请写入 `pii.sensitive_fields`。
- API Token 只放在环境变量中，不要写进配置文件或提交到代码仓库。

## 六、已知限制

- 本 Skill 中的脚本尚未在富卫的真实测试环境中运行过。首次使用请先跑第二节的示例验证，再用一次真实回归结果试运行，确认读取和分类无误后再提交 Jira。
- “BLN 平台”的结果格式未知。如果它能导出结果，写一个转换脚本输出 `data-contract.md` 第 2 节的格式，用 `--format normalized` 读取即可。
- 重跑命令默认按 pytest 编写；使用其他框架需要修改 `rerun.command`，并保证生成 JUnit XML。
