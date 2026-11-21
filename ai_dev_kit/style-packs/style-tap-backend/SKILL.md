---
name: style-tap-backend
description: tap-ai-backend 项目的代码风格包：分层、接口、服务、仓储条件更新、插件与契约、配置、后台任务、测试共 8 张卡片。用于在 tap-ai-backend 里写代码、迁移代码（例如把知识库/知识图谱模块从 POC 搬到后端）、评审改动时，先按任务类型打开对应卡片照着写。
---

# tap-ai-backend 风格包

## 怎么用
1. 先判断这次改动属于哪一类，打开对应卡片（不用全部读，省额度）：

| 改动类型 | 卡片 |
|---|---|
| 新功能放哪一层、文件怎么分 | patterns/01-layering.md |
| 新增/修改接口 | patterns/02-http-api.md |
| 业务逻辑、错误码 | patterns/03-service.md |
| 数据库模型、状态更新 | patterns/04-repo-conditional-update.md |
| 插件、契约（端口）、启动装配 | patterns/05-plugin-contracts-bootstrap.md |
| 配置项、功能开关 | patterns/06-settings.md |
| 后台任务、批量处理、超时 | patterns/07-background-worker.md |
| 单元测试 | patterns/08-tests.md |

2. 按卡片的“必须 / 禁止”写；写完逐条过“检查项”。
3. 卡片和代码冲突时，**以代码为准**：先打开卡片“来源”里列的文件看现在的写法，再告诉用户卡片需要更新（用 /kit-extract-pattern 核对）。

## 卡片的可信程度（重要）
- 这些卡片是根据我们迁移过程中确认过的约定整理的（例如：接口只用 GET/POST、配置直接用 settings、ORM 类放顶层、状态用条件更新、新功能默认关闭）。
- 卡片顶部写着“核对状态”。状态为“待核对”的卡片，第一次使用前请运行一次 /kit-extract-pattern 的“核对旧卡片”，对照来源文件把样例改成和代码完全一致，并把状态改成“已核对”。

## 项目级硬规则（任何卡片都适用）
1. 不改同事的问答知识插件 `src/tap_ai/plugins/extensions/knowledge/`（唯一例外：`backends/kg_browse.py`，需任务明确要求）。
2. 只读资源不写：jp-poc 搜索索引只读（只用查询密钥）；共享 Neo4j 可以写入；要删除任何数据先评估风险并等用户同意（守卫会核对）。
3. 测试用 fake，不连真实 MySQL / Azure Search / Neo4j / 大模型；不读真实 .env。
4. 不改 pyproject.toml / uv.lock；不对已有文件运行 ruff format。
