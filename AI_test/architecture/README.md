# AI-Powered Intelligent Testing Platform — 架构总览

## 项目概述

AI-Powered Intelligent Testing Platform（AI驱动智能测试平台）是一个基于微软生态构建的端到端测试自动化平台。核心能力是利用大语言模型（LLM）和 AI Search 技术，将"需求文档 → 测试用例 → 自动化脚本 → 执行 → 报告"这条测试链路全面智能化。

### 核心理念

| 维度 | 说明 |
|------|------|
| 智能生成 | 从需求文档自动生成测试用例和自动化脚本 |
| 人机协作 | AI 生成 + 人工评审，效率与质量兼顾 |
| 闭环反馈 | 失败分析结果反哺用例和脚本，持续优化 |
| 生态融合 | 深度集成微软生态（Power Platform、Azure、Teams） |

### 目标用户

- 测试工程师：用例生成、脚本编写、执行监控
- 业务分析师：需求上传与评审
- 测试经理：报告查看、质量度量
- 开发工程师：失败分析定位

---

## 技术选型理由

### 前端：Power Apps + Power Pages

| 选项 | 理由 |
|------|------|
| Power Apps | 低代码快速构建测试管理界面，与 Dataverse 原生集成，审批流可直接复用 Power Automate |
| Power Pages | 面向外部用户（客户、供应商）的门户，匿名/认证访问，支持 SEO，自带 GDPR 合规 |
| 为何不用 React/Angular | 项目深度依赖 Power Platform 生态（Dataverse、Power Automate），纯前端框架会丢失原生集成优势。Power Apps Component Framework (PCF) 可应对复杂交互场景 |

### 后端编排：Copilot Studio + Power Automate + Azure Functions

| 组件 | 职责 | 选型理由 |
|------|------|----------|
| Copilot Studio | AI 对话入口、需求交互 | 原生支持 Azure OpenAI，可配置自定义知识库，零代码构建 AI 助手 |
| Power Automate | 流程编排、审批流转 | 连接器丰富（Teams、Outlook、Jira、DevOps），可视化设计，非开发人员可维护 |
| Azure Functions | 复杂业务逻辑、AI 调用编排 | 处理 Power Automate 无法实现的逻辑（循环、条件分支复杂场景），C# / Python 编写，按需付费 |

### 数据存储

| 存储 | 用途 | 选型理由 |
|------|------|----------|
| Dataverse | 业务主数据（用例、需求、评审记录） | Power Platform 原生数据源，支持关系、安全角色、审计，无需额外持久化层 |
| SharePoint | 需求文档附件、静态资源 | 与 Teams 深度集成，用户上传/预览体验好 |
| Azure SQL | 测试执行结果、性能数据 | 复杂聚合查询性能优于 Dataverse，适合报表场景 |
| Azure Blob Storage | 截图、日志、报告文件 | 低成本非结构化存储，支持 CDN 分发 |

### AI 服务

| 服务 | 用途 | 理由 |
|------|------|------|
| Azure OpenAI Service | 用例生成、脚本生成、失败分析 | GPT-4o 文本理解与生成能力，支持 Function Calling 结构化输出 |
| Azure AI Search | 相似用例检索、需求知识图谱 | 向量搜索 + 关键词混合检索，RAG 模式的知识基础 |
| Azure Cognitive Search（历史） | 兼容旧版检索任务 | 平台升级过渡期间保留，后续逐步迁移至 AI Search |

### 自动化执行引擎

| 工具 | 场景 | 理由 |
|------|------|------|
| Playwright | 主执行引擎 | 现代化 API，支持多浏览器、多语言、自动等待，社区活跃 |
| Selenium | 兼容旧项目 | 遗留测试脚本复用，逐步迁移至 Playwright |

### 集成

| 系统 | 用途 | 方式 |
|------|------|------|
| Azure DevOps | 工作项同步、CI 触发、Bug 自动创建 | REST API + Service Hook |
| Jira | 可选 — 企业已有 Jira 时的适配 | REST API |
| Teams | 通知推送、审批卡片、报告分享 | Power Automate Teams Connector |
| Outlook | 邮件通知、报告附件 | Power Automate Outlook Connector |

---

## 架构层次

```mermaid
architecture-beta
    group ui[表现层 - Power Platform]
    service powerapps("Power Apps") in ui
    service powerpages("Power Pages") in ui
    service copilot("Copilot Studio") in ui

    group logic[应用层 - 流程编排]
    service automates("Power Automate") in logic
    service functions("Azure Functions") in logic

    group service[服务层 - AI与引擎]
    service openai("Azure OpenAI") in service
    service search("Azure AI Search") in service
    service player("Playwright Engine") in service
    service selenium("Selenium Engine") in service

    group data[数据层]
    service dataverse("Dataverse") in data
    service sql("Azure SQL") in data
    service sharepoint("SharePoint") in data
    service blob("Blob Storage") in data

    group integration[集成层]
    service devops("Azure DevOps") in integration
    service jira("Jira") in integration
    service teams("Teams") in integration
    service outlook("Outlook") in integration

    powerapps:L -- T:automates
    powerpages:L -- T:automates
    copilot:R -- T:functions
    automates:B -- T:functions
    functions:R -- T:openai
    functions:R -- T:search
    functions:B -- T:player
    functions:B -- T:selenium
    player:B -- T:dataverse
    player:B -- T:sql
    player:B -- T:blob
    functions:B -- T:dataverse
    functions:B -- T:sql
    functions:B -- T:blob
    functions:B -- T:sharepoint
    automates:R -- T:devops
    automates:R -- T:jira
    automates:R -- T:teams
    automates:R -- T:outlook
```

---

## 各层职责

### 1. 表现层 — Power Platform UI

| 组件 | 职责 |
|------|------|
| Power Apps | 内部用户核心工作台：用例管理、执行监控、报告查看、AI 助手面板 |
| Power Pages | 外部用户门户：提交需求、查看分配用例、查看报告 |
| Copilot Studio | AI 对话交互：需求导入引导、用例建议、报告解读、执行分析 |
| Teams 应用 | Power Apps for Teams 嵌入，让测试团队在 Teams 内完成全部工作 |

### 2. 应用层 — 流程编排

| 组件 | 职责 |
|------|------|
| Power Automate | 串联各环节：上传需求 → 通知 → 生成用例 → 推送评审 → 确认后生成脚本 → 调度执行 → 发送报告 |
| Azure Functions | 复杂逻辑处理：AI 调用编排（多轮对话）、结果格式化、批量数据处理、失败重试策略 |

编排模式：
```
Power Apps 触发 → Power Automate 协调 → Azure Functions 执行 AI 逻辑
                          ↓
                结果写回 Dataverse / SQL
                          ↓
                Power Automate 推送通知
```

### 3. 服务层 — AI 与执行引擎

| 组件 | 职责 |
|------|------|
| Azure OpenAI | 所有 NLP 任务：需求解析、用例生成、脚本生成、失败文本分析、报告总结 |
| Azure AI Search | 向量索引 + 语义搜索：相似用例检索、历史失败模式匹配 |
| Playwright | UI 自动化执行：浏览器操作、截图、网络拦截、性能采集 |
| Selenium | 兼容执行引擎：运行遗留脚本 |

### 4. 数据层

| 存储 | 核心实体 |
|------|----------|
| Dataverse | Requirement（需求）、TestCase（测试用例）、TestScript（测试脚本）、ReviewRecord（评审记录）、ExecutionRun（执行任务） |
| Azure SQL | ExecutionResult（执行结果明细）、PerformanceMetrics（性能指标）、FailureAnalysis（失败分析记录） |
| SharePoint | 上传的需求文档（PDF/Word）、附件 |
| Blob Storage | 执行截图（screenshots/）、日志（logs/）、报告（reports/）、AI 分析缓存（ai-cache/） |

### 5. 集成层

| 系统 | 集成方式 |
|------|----------|
| Azure DevOps | 功能：创建 Bug、更新 Test Case、CI 触发执行。方式：Service Hook → Azure Function webhook |
| Jira | 功能：创建 Issue、同步测试结果。方式：REST API（可选配置） |
| Teams | 功能：审批卡片、执行通知、报告推送。方式：Power Automate Teams Connector + Adaptive Cards |
| Outlook | 功能：邮件通知、报告附件。方式：Power Automate Outlook Connector |

---

## 技术决策记录（ADR）

### ADR-001：使用 Power Platform 而非定制开发前端

| 项目 | 内容 |
|------|------|
| 状态 | 已接受 |
| 决策 | 使用 Power Apps + Power Pages 作为前端，不使用 React / Angular 定制开发 |
| 理由 | 项目需深度集成 Dataverse、Power Automate、Copilot Studio，这些在 Power Platform 内是原生级集成。定制前端反而需要额外 API 网关层。且团队低代码能力可支持 |
| 后果 | 复杂交互场景需通过 PCF 自定义组件扩展；版本管理依赖 Power Platform 发布机制 |

### ADR-002：AI Search 作为 RAG 知识库

| 项目 | 内容 |
|------|------|
| 状态 | 已接受 |
| 决策 | 使用 Azure AI Search 作为测试知识库的向量搜索引擎 |
| 理由 | 测试领域有大量历史数据（相似用例、历史失败），向量搜索 + 关键词混合检索可以精准召回，搭配 Azure OpenAI 实现 RAG |
| 后果 | 需要设计索引 Schema（需求、用例、失败模式），初始化时需批量向量化存量数据 |

### ADR-003：Playwright 为主执行引擎

| 项目 | 内容 |
|------|------|
| 状态 | 已接受 |
| 决策 | Playwright 作为主自动化引擎，Selenium 用于兼容遗留脚本 |
| 理由 | Playwright 现代化 API、自动等待、多浏览器支持、网络拦截能力优于 Selenium，且社区增长趋势明显 |
| 后果 | 需要构建 Playwright 执行器服务和结果收集器，旧 Selenium 脚本需逐步迁移 |

### ADR-004：Azure Functions 而不是 Logic Apps 做复杂逻辑

| 项目 | 内容 |
|------|------|
| 状态 | 已接受 |
| 决策 | 使用 Azure Functions 处理 AI 编排等复杂业务逻辑 |
| 理由 | Power Automate 适合线性流程，但 AI 调用涉及多轮对话、循环、条件分支，Functions 的代码灵活性更适合 |
| 后果 | 需要维护 Functions 代码仓库，部署流水线不能完全低代码化 |

### ADR-005：Dataverse + Azure SQL 双存储

| 项目 | 内容 |
|------|------|
| 状态 | 已接受 |
| 决策 | Dataverse 存业务主数据，Azure SQL 存执行结果和分析数据 |
| 理由 | Dataverse 与 Power Platform 原生集成（安全、审计、角色），但复杂查询性能有限。Azure SQL 承载高吞吐的执行结果写入和聚合查询 |
| 后果 | 两个存储之间有交叉查询需求时，需通过 Azure Function 或 API 桥接，增加架构复杂度 |

---

## 关键非功能需求

### 性能

| 指标 | 目标 | 说明 |
|------|------|------|
| AI 用例生成 | < 30 秒 / 份需求 | 需求文档解析 + 用例生成 + 写入存储 |
| 脚本生成 | < 60 秒 / 套 | 根据用例生成 Playwright 脚本 |
| 页面加载 | < 3 秒 | Power Apps 首屏加载 |
| 并发执行 | 支持 50+ 个浏览器实例并行 | Playwright 执行器水平扩展 |
| 报告生成 | < 10 秒 | 聚合结果 + 模板填充 + AI 分析总结 |

### 可用性

| 级别 | 目标 | 实现方式 |
|------|------|----------|
| Power Platform | 99.9% | 微软 SLA 保障 |
| Azure Functions | 99.95% | 多区域部署 + 可用区 |
| AI Service | 99.9% | Azure OpenAI SLA，内置重试和降级逻辑 |
| Playwright 执行器 | 99.5% | 健康检查 + 自动重启 + 备用实例 |
| 数据层 | 99.99% | Azure SQL HA + Blob 异地冗余存储 |

### 可扩展性

| 维度 | 策略 |
|------|------|
| 水平扩展 | Azure Functions 弹性伸缩；Playwright 执行器容器化，Kubernetes / 容器组自动扩展 |
| 用例规模 | 百万级用例：AI Search 向量索引 + Dataverse 分页查询 |
| 用户规模 | 千人并发：Power Apps 通过 Dataverse 分片和缓存支撑 |
| 集成扩展 | Power Automate 连接器模式，新增系统只需添加新连接器 |

### 安全性

| 维度 | 措施 |
|------|------|
| 网络隔离 | Azure VNet 隔离，私有终结点连接所有 PaaS 服务 |
| 认证与授权 | Azure AD / Entra ID，Power Platform 安全角色，最小权限原则 |
| 数据加密 | 传输层 TLS 1.2+，存储层 Azure 静态加密 |
| AI 安全 | Azure OpenAI 内容过滤，PII 脱敏后送入模型，审计日志记录推理内容 |
| 网络边界 | API 需通过 Azure APIM 转发，禁止直接暴露 Functions 端点 |

### 可观测性

| 维度 | 工具 |
|------|------|
| 日志 | Application Insights，集中日志分析 |
| 指标 | Power Platform Analytics + Azure Monitor |
| 告警 | AI 用例生成失败、执行器宕机、存储接近阈值时自动告警 |
| 审计 | Dataverse 审计日志记录所有数据变更 |
