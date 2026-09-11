# AI-Powered Intelligent Testing Platform
# 示例代码清单
# ============================
# 本目录包含 AI 测试平台各模块的关键示例代码。
# 每个子目录对应一个技术组件，含完整的代码 + 配置 + 说明。

## 目录结构

```
code-samples/
├── ai-requirement-analyzer/   # 需求分析 — Azure Function (Python)
│   ├── function_app.py        #   主函数：解析 PRD，提取可测试需求点
│   ├── function.json          #   Azure Functions 绑定配置
│   └── pyproject.toml         #   依赖管理
│
├── ai-testcase-generator/     # 用例生成 — Azure Function (Python)
│   └── function_app.py        #   主函数：基于需求点生成结构化测试用例
│
├── ai-failure-analyzer/       # 失败分析 — Azure Function (Python)
│   └── function_app.py        #   主函数：分析失败日志，关键字+LLM双重分类
│
├── ai-report-generator/       # 报告生成 — Azure Function (Python)
│   └── function_app.py        #   主函数：聚合数据，LLM 生成摘要报告
│
├── playwright-scripts/        # Playwright 测试脚本
│   ├── templates/
│   │   ├── login-test.spec.ts      # 登录测试模板（数据驱动）
│   │   └── workflow-test.spec.ts   # 工作流测试模板（采购审批）
│   ├── playwright-executor/
│   │   ├── executor.ts             # AI 用例执行器
│   │   └── translator.ts           # 用例→脚本翻译器
│   ├── playwright.config.ts        # Playwright 配置
│   └── package.json
│
├── power-automate/             # Power Automate 工作流
│   ├── orchestration-pipeline.json   # 主测试编排流程
│   ├── scheduled-report.json         # 定时报告推送
│   └── copilot-triggered-test.json   # Copilot 触发的按需测试
│
├── dataverse/                  # Dataverse 数据模型
│   ├── entity-definitions.json     # 5 张核心表的逻辑定义
│   └── api-client.ts               # Web API 调用示例 (TypeScript)
│
├── copilot-studio/             # Copilot Studio Agent
│   └── agent-definition.json       # Agent 定义 + Skill + Topic 配置
│
└── power-apps/                 # Power Apps 前端
    ├── model-driven-dashboard.json # 模型驱动应用的仪表盘和视图配置
    └── powerfx-formulas.powerfx    # 关键 Power Fx 公式示例
```

## 数据流

PRD文档 → [需求分析函数] → 结构化需求点
    ↓
[用例生成函数] → 测试用例 → 写入 Dataverse
    ↓
[Playwright 执行器] → 执行测试 → 结果写入 Dataverse
    ↓
[失败分析函数] → 分析结果 ← 更新 Dataverse
    ↓
[报告生成函数] → 测试报告 → 推送 Teams/Outlook/SharePoint
    ↓
[Power Apps 仪表盘] ← Dataverse 实时数据展示
[Teams Copilot] ← 用户自然语言查询

## 关键集成点

| 步骤 | 集成方式 |
|------|----------|
| Function ↔ OpenAI | Azure OpenAI SDK (Python) |
| Function ↔ Dataverse | Dataverse Web API (OAuth/Managed Identity) |
| Power Automate ↔ Function | HTTP trigger (Function Key 认证) |
| Copilot Studio ↔ Flow | 内置 Power Automate 连接器 |
| Power Apps ↔ Dataverse | 内置 Dataverse 连接器 |
| Playwright → Dataverse | 通过 HTTP trigger 回调 |
| Azure DevOps → Power Automate | Webhook 回调 |
