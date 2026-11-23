---
name: kit-eval-writer
description: 把一次真实事故（Copilot 犯过的错、漏掉的检查）写成评估用例，放进工具包的回归测试里，保证以后同样的错误一定会被拦住或发现。用于一次执行出了问题、修好之后，或者新增了技能、规则、检查之后需要证明它有效时。
---

# 把事故写成评估用例

## 用户会这样说
- 把这次事故写成用例
- 保证以后这种错误一定能被拦住
- 给新规则写个回归测试
- 守卫拦错了，加个反向用例
风险：会改文件

## 不适用
- 给项目代码补单元测试（用 /kit-write-code）

## 为什么
- Anthropic 的评估实践：从 20～50 个真实失败案例开始，比凭空想的测试更有价值；能用代码判分的就用代码判分；回归用例的通过率应接近 100%。
- 工具包的用例都来自本项目的真实事故和真实需求。每修一个新事故，就加一条，防线只会越来越厚。

## 四种用例（evals/cases 目录下的 JSON 文件）
| type | 测什么 | 判分方式 | 是否消耗额度 |
|---|---|---|---|
| guard | 守卫是否拦住危险操作、该问的问、该放的放 | 期望 deny / ask / none（可再要求 rule） | 否 |
| static | 静态检查能否发现问题代码 | 在临时 git 仓库里制造改动，期望 fail / pass | 否 |
| prompt | 提示词体检能否识别含糊需求 | 期望识别出缺少的维度、分数范围 | 否 |
| output | 一键验证能否识别假通过 | 给测试命令的原始输出，期望 fail / pass | 否 |
| agent | 代理在真实调用中是否做对 | 输出里必须出现 / 不能出现的正则 | 是（默认不跑） |

## 绝对禁止
1. 绝对禁止在用例里写真实密钥、真实数据、真实内部地址（用例里的路径、命令都是虚构的，跑完不留任何东西）。
2. 绝对禁止为了让用例通过而降低期望（例如把 expect 从 deny 改成 none）。用例失败说明防线有漏洞，要修防线。
3. 绝对禁止一条用例测多件事。

## 步骤
1. **描述事故**：一句话写清“发生了什么、应该被什么拦住或发现”。
2. **选类型**：能用守卫拦的 → guard；能从代码改动里发现的 → static；需求写得不清楚导致的 → prompt；只能看代理行为的 → agent。
3. **用脚手架生成骨架**：
   `{{PYTHON}} {{KIT_ROOT}}/tools/kit_new.py case <用例id> --type <类型>`
4. **填内容**（字段说明）：
   - 通用：`id`、`type`、`title`（这条防什么）、`incident`（来自哪次事故）
   - guard：`payload`（`toolName` + `toolArgs`，模拟 Copilot 的一次工具调用），`expect`（deny / ask / none），可选 `expect_rule`（例如 data-delete、scratch-delete、auto-kit-run）、`guard_config`、`context`（project / other，默认 project）、`mode`（chat / workbench / project）、`shared` + `shared_allow`（共享模块）、`baseline: true`（已记录基线）、`files`（预先写进临时目录的文件 {路径: 内容}）；命令里可以用 `{kit}` 表示工具包目录
   - static：`check`（检查名，见 `checks.py --list`），`before`（改动前的文件 {路径: 内容}），`after`（改动后的文件，内容为 null 表示删除），`expect`（fail / pass），可选 `scope`、`project`
   - prompt：`text`，`expect_missing`（goal / location / context / constraints / done / verify / output / examples），可选 `expect_max_score` / `expect_min_score`
   - output：`output`（测试命令原始输出），`exit_code`，`check_name`（默认 tests），`expect`（fail / pass）
   - guard 额外可选：`scope`（写进临时目录的修改范围），路径里可以用 `{cwd}` 表示临时项目目录
   - static 的文件内容可以写成 `{"text": "...", "encoding": "utf-16"}` 来制造编码事故
   - agent：`agent`（代理 id），`prompt`，`expect_all`（必须出现的正则），`expect_none`（不能出现的正则），可选 `timeout`
5. **同时写一条反向用例**（推荐）：例如拦截 `git add .` 的同时，确认 `git add -- 具体文件` 的分析命令不被误拦；防止规则过宽。
6. **运行**：`{{PYTHON}} {{KIT_ROOT}}/tools/run_evals.py --case <用例id>`，再跑全部 `run_evals.py` 确认没有影响其他用例。
7. agent 类用例跑完后，打开保存的完整输出读一遍，不要只看通过/失败。

## 输出格式
```
【事故】……
【用例类型与理由】……
【用例 JSON】……
【反向用例 JSON】……
【运行结果】（原始输出）
```
