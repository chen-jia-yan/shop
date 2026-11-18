# ai-dev-kit：个人 AI 开发工具包

给 GitHub Copilot CLI 用的一整套“规则 + 能力 + 防线”。离线可用，只依赖 Python 标准库。

## 它解决什么问题
| 你遇到的问题 | 工具包里的对应能力 |
|---|---|
| Copilot 注意力差，漏做、越界、谎报完成 | R3 提示词模板 + 自定义代理分工 + 结尾核对表 + 评审代理 |
| 说了“不要做”它还是做（读 .env、git add .、装包、改同事模块） | **钩子硬拦截**（guard.py）：调用工具前检查，违规直接拒绝 |
| 测试“通过”是假的（0 条、收集中断、全跳过、永真断言） | 一键验证 run_checks.py + 静态检查 checks.py |
| 写出来的代码不像项目自己的风格 | 风格包 style-tap-backend（8 张卡片，引用项目源文件） |
| 需求说不清楚 | 提示词体检 prompt_lint.py + 提示词教练代理 |
| 每次都要重新交代背景、踩过的坑又踩 | 记忆系统 mem.py（带引用、自动核对是否过期） |
| 新版本按 token 计费、旧版本额度多 | 两种模式：quota（完整）/ latest（省 token：固定前缀命中缓存、结果哈希缓存、输出裁剪） |
| 不想每次敲命令 | 桌面挂件：按钮来自 registry.json，可以随时增加 |
| 以后要加新能力 | 脚手架 kit_new.py：一条命令新增技能 / 代理 / 卡片 / 用例 / 按钮 / 项目 |

## 三分钟上手
```
cd <工具包目录>
python tools/install.py          # 安装（可以反复运行）
python tools/kit_doctor.py       # 体检：每项都会告诉你怎么修
python tools/selftest.py         # 自测：在临时目录里把每个模块跑一遍
python tools/run_evals.py        # 评估：37 条事故用例
widget\start_widget.bat          # 打开桌面挂件
```
安装后先打开 `kit.config.json`，把 quota 版本的 `launcher` 改成你公司 bat 的完整路径。

## 目录
```
agents/        6 个自定义代理（规划、执行、评审、验证、排障、提示词教练）
skills/        11 个技能（kit- 开头）
style-packs/   风格包（style-tap-backend + 新建模板）
hooks/         3 个钩子：session_start（注入上下文和记忆）、guard（写前拦截）、post_edit（写后检查）
tools/         所有命令行工具
templates/     提示词模板（通用规则固定在最前，方便命中缓存）
memory/        记忆库（一条一个 markdown 文件）
evals/cases/   评估用例
widget/        桌面挂件
instructions/  个人规则（合并进 ~/.copilot/copilot-instructions.md）、项目 AGENTS.md 模板
docs/          使用文档（从 01 开始按顺序读）
registry.json  挂件按钮定义
```

## 文档
1. docs/01-安装与升级.md
2. docs/02-日常使用.md
3. docs/03-钩子与自定义代理.md
4. docs/04-提示词助手.md
5. docs/05-记忆系统.md
6. docs/06-省token与两种版本.md
7. docs/07-扩展指南.md
8. docs/08-团队分发.md
9. docs/09-风险与对策.md
10. docs/10-需求核对表.md
