## ai-dev-kit 个人规则（由工具包自动维护，请改 instructions/personal.md 后重新安装）

### 工作方式
1. 我的需求经常比较笼统。信息不够时先问我（一次最多 5 个问题，带选项和推荐项），不要猜；能从代码里查到的先自己查。
2. 一次只做一件事。需求里有多件事时，先列出拆分方案让我确认。
3. 改代码前先找项目里的同类写法作参照；项目有风格包（style- 开头的技能）就先加载。
4. 只改本次修改范围内的文件（会话开头会注入“本次修改范围”）；需要改别的文件时停下来说明原因。
5. 写测试只用假对象（fake），不连真实数据库、搜索服务、图数据库、大模型，不读真实 .env。

### 绝对禁止
1. 读取或打印 .env、.env.example、providers.json、任何密钥文件。
2. git 写操作（add / commit / push / pull / merge / rebase / reset / checkout / restore / stash / clean）。git 只允许 status / diff / log / show / grep / ls-files。提交由我自己执行。
3. 安装或卸载依赖；修改 pyproject.toml、uv.lock、requirements*.txt、工具配置。缺依赖时在报告里说明。
4. 用 PowerShell 的 >、Out-File、Set-Content 写文件（会产生 UTF-16）；只用编辑工具改文件。
5. 对已有文件运行 ruff format；用 # type: ignore、# noqa、skip、xfail、cast(Any, ...) 让检查通过。
6. 标识符用中文或全角字符；文件必须 UTF-8 无 BOM。
7. 对共享资源做写操作：只读的搜索索引、别的团队或别的范围的数据、共享图数据库里不属于本任务范围的数据。
8. 被 ai-dev-kit 守卫拒绝后换一种写法绕过去。被拒绝就停下，把操作和原因告诉我。

### 交付要求
1. 说“已完成”“已通过”时必须附证据：命令原始输出或 文件:行号。0 条测试、收集中断、全部跳过都算失败。
2. 做不完就如实说做到哪一步；不确定的地方明确写出来。
3. 结尾附核对表：每个编号一行，状态只能是 完成 / 未找到 / 未做 / 已停下。

### 可用的工具包能力（需要时加载对应技能）
- 规划 /kit-plan-task，写代码 /kit-write-code，评审 /kit-code-review，排障 /kit-debug-bug
- 验证 /kit-verify-change，提交方案 /kit-safe-commit，写提示词 /kit-prompt-craft
- 记忆 /kit-memory，提炼风格 /kit-extract-pattern，写评估用例 /kit-eval-writer，额度管理 /kit-context-budget
- 工具包位置：{{KIT_ROOT}}；Python：{{PYTHON}}
