# AGENTS.md（项目级说明模板）

> 用法：复制到项目根目录，改名为 AGENTS.md，按实际情况填写。Copilot 在这个项目里工作时会自动读取。
> 注意：这个文件会进入项目仓库、团队共享，不要写个人路径、密钥和内部地址。
> 如果只是你个人使用、不想提交，可以放在 .github/copilot-instructions.md 并加入 .git/info/exclude。

## 项目简介
- 这是什么服务、主要模块在哪（2～4 行）。

## 目录约定
- `src/<包名>/api/`：接口层，只做参数和响应
- `src/<包名>/services/`：业务逻辑
- `src/<包名>/repositories/`：数据库读写
- `src/<包名>/plugins/`：插件，插件之间通过 contracts 交互
- `tests/unit/`：单元测试（只用 fake）

## 常用命令
- 测试：`uv run pytest tests/unit -q`
- lint：`uv run ruff check .`
- 类型检查：`uv run mypy src`（如果项目使用）

## 受保护区域（不要修改）
- `<路径>`：<原因，例如：其他同事负责的模块>

## 写法约定
- 配置直接用 `settings.xxx`，不要 `getattr(settings, ...)`
- ORM 模型类定义在模块顶层
- 状态更新用条件更新并检查影响行数
- （更多见风格包）

## 测试约定
- 不连真实外部服务、不读 .env
- 断言比较具体值；修 bug 必须带回归测试
