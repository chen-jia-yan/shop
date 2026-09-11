# 项目 Skills 速查手册

> 自动发现自 `.claude/skills/`，所有 skill 均可通过 Skill 工具直接调用。

---

## 一、开发流程类（superpowers）

| Skill | 触发场景 | 一句话用法 |
|---|---|---|
| `superpowers:using-superpowers` | **每次新对话开始时** | 建立 skill 查找和使用规范，确保后续 skill 被正确调用 |
| `superpowers:writing-plans` | 接到多步骤需求、复杂任务时 | 动手写代码前先出计划，获用户确认后再执行 |
| `superpowers:executing-plans` | 已有写好的计划要执行时 | 按计划分阶段执行，每个 checkpoint 停下来 review |
| `superpowers:subagent-driven-development` | 计划中有多个独立任务可并行时 | 派 subagent 并行执行互不依赖的任务 |
| `superpowers:dispatching-parallel-agents` | 2 个以上互不依赖的独立任务 | 并行派发 agent 加速执行 |
| `superpowers:brainstorming` | 创建新功能、改行为、加组件之前 | 先探索用户意图和设计方向，再动手 |

## 二、质量保障类（superpowers）

| Skill | 触发场景 | 一句话用法 |
|---|---|---|
| `superpowers:test-driven-development` | 写任何功能或修 bug，实现代码之前 | 先写测试，再写实现 |
| `superpowers:systematic-debugging` | 遇到任何 bug、测试失败、意外行为 | 先诊断根因，再提议修复，不猜 |
| `superpowers:verification-before-completion` | 声称"做完了/修好了/通过了"之前 | 先跑验证命令看输出，再说话 |
| `superpowers:requesting-code-review` | 完成功能、修复 bug、准备合并前 | 调 code-review 验证工作质量 |
| `superpowers:receiving-code-review` | 收到 review 反馈时 | 技术严谨地验证每条建议，不盲目照搬 |
| `superpowers:finishing-a-development-branch` | 实现完成、测试全过、准备合并时 | 引导完成分支收尾（合并/PR/清理） |
| `superpowers:using-git-worktrees` | 需要隔离工作空间时 | 创建隔离 worktree 保护当前工作区 |

## 三、项目专用类

| Skill | 触发场景 | 一句话用法 |
|---|---|---|
| `feature-dev` | 实现新功能时 | 7 阶段系统化开发：探索→澄清→设计→实现→审查→总结 |
| `frontend-design` | 创建前端 UI 组件/页面时 | 生成不落俗套的高品质 UI |
| `karpathy-guidelines` | 写/审/重构代码时 | 避免过度设计，精简化改动，显式化假设 |
| `code-review` | review diff 的正确性和简洁性 | 查 bug + 查冗余 + 查规范 |
| `simplify` | 清理代码冗余和过度设计时 | 只做质量清理，不找 bug |
| `verify` | 需要确认改动真正生效时 | 跑起应用看行为 |
| `run` | 想看改动在真实应用中效果时 | 启动应用截图确认 |

## 四、工具类

| Skill | 触发场景 | 一句话用法 |
|---|---|---|
| `deep-research` | 需要深度调研时 | 多源搜索→交叉验证→生成引用报告 |
| `docx` | 创建/编辑 Word 文档时 | 处理 .docx 的创建、编辑、批注、修订 |
| `pdf` | 创建/编辑 PDF 时 | 提取/合并/拆分/填表 |
| `find-skills` | 想装新 skill 时 | 查找可安装的社区 skill |
| `superpowers:writing-skills` | 创建或修改 skill 时 | 创建前验证、创建后测试 |

## 五、内置默认（无需手动调用）

| Skill | 说明 |
|---|---|
| `security-review` | 审查当前分支改动的安全问题，自动触发 |
| `update-config` | 修改 settings.json，用 `/config` 或手动调 |
| `fewer-permission-prompts` | 减少权限弹窗 |
| `loop` | 设置定时循环任务 |

---

## 六、关键使用原则

1. **session 开始先调 `using-superpowers`**——建立整套流程框架
2. **写代码前先调 `writing-plans` + `brainstorming`**——想清楚再动手
3. **写实现前先调 `test-driven-development`**——测试先行
4. **声称完成前先调 `verification-before-completion`**——证据说话
5. **遇到 bug 先调 `systematic-debugging`**——诊断再修复

## 七、关于 security-guidance 和 typescript-lsp

这俩不是 skill，是**插件**，无法复制到项目 skills：

- **security-guidance**：hook 插件，在 Edit/Write/Stop/Commit 时自动触发安全审查（3 层：正则→LLM→Agent），需装为 plugin
- **typescript-lsp**：LSP 插件，提供 TS/JS 代码智能提示，需 `npm install -g typescript-language-server`
