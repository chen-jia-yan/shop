# DeepSeek Harness 落地借鉴方案

> 对照对象：AI_test 智能测试平台（基于微软生态的 Power Platform 架构）
> 参考来源：`deepseek-ai/deepseek-harness`（dsh），MIT 协议
> 定位：这份文档不是要推翻 Power Platform 架构，而是把 dsh 里「可移植、可落地」的设计思想，映射到 AI_test 当前的 7 阶段流水线上。

---

## 0. 先说清楚一个前提

AI_test 的技术栈是**微软低代码生态**（Power Automate + Azure Functions + Dataverse + Copilot Studio），dsh 是一个 **TypeScript 单仓 agent harness**。两者不是一个东西，不能照搬代码。

但 dsh 真正值钱的不是代码，是**几个底层设计思想**，这些思想是「架构模式」层面，跟语言和平台无关。本文就是把这几个思想抽出来，告诉你 AI_test 哪里能直接套、哪里需要改造、哪里不适用。

**一句话总结：借鉴 dsh 的「插件化」和「可验证状态机」，而不是它的 TypeScript 实现。**

---

## 1. 核心借鉴点 1：把 7 阶段流水线改造成「插件化 Pipeline」

### dsh 的做法

dsh 的灵魂是「**一切皆插件**」——连 agent 主循环、模型适配器、工具注册表本身都是插件，没有特权核心。你想加能力，就「挂一个插件到别人旁边」，插件卸载时所有注册自动回滚（reversible effects）。

### AI_test 的现状

当前 7 个模块（需求分析→用例生成→评审→脚本生成→执行→失败分析→报告）是**写死在 Power Automate 流程里的串行节点**。加一个新环节（比如「安全扫描」「性能基线对比」）就得改主流程、重新发布 Power Automate。

### 落地改造

把每个阶段抽象成**统一接口的「测试插件」**，注册到一个「流水线注册表」里：

```
Power Automate 主流程不再硬编码 7 个步骤，
而是读取一张「流水线插件配置表」(Dataverse: ait_pipeline_plugin)，
按注册顺序动态串联插件。
```

| 改造项 | 现状 | 改造后 |
|---|---|---|
| 环节定义 | 写死在 Flow 里 | 存 Dataverse 插件表，可动态增删 |
| 环节顺序 | Flow 固定顺序 | 插件表里的 `order` 字段决定 |
| 加新环节 | 改 Flow + 重新发布 | 注册一个新插件行，配置输入输出契约 |
| 环节实现 | 每个环节独立的 Function | 每个插件 = 一个 Azure Function + 统一的入参/出参 schema |

**统一的插件契约**（这是关键，参考 dsh 的 service 接口）：

```json
{
  "pluginId": "req-analysis",
  "pluginName": "需求分析",
  "order": 1,
  "inputSchema": { "documentId": "string", "fileUrl": "string" },
  "outputSchema": { "testPoints": "array", "confidence": "number" },
  "entryFunction": "https://xxx/req-analyzer",
  "status": "enabled"
}
```

这样你项目里「端到端全流程自动化」的愿景就变成：「端到端」是插件表串出来的，不是代码写死的。**这个改造对 Power Platform 是顺的，因为 Power Automate 本来就能读 Dataverse 表来动态决定调用链。**

---

## 2. 核心借鉴点 2：给「测试脚本执行」加统一的安全守卫管道

### dsh 的做法

dsh 有一个**完整的工具执行管道**，所有工具调用都要过这一关：

```
tool/call → tools/pre-execute（瀑布流：hook、权限、沙箱）
         → monotonic guards（单调守卫：deny / abstain）
         → approval（一次性审批）
         → tools/execute（环绕：超时、重试、指标）
         → tools/post-execute（接受、拦截、改写、加上下文）
         → tool/result
```

关键点：**pre-execute / execute / post-execute 是「瀑布流」**，每个监听器能决定「放行、改写、短路」。

### AI_test 的现状

当前「测试执行模块」是 Playwright 执行器直接跑脚本，执行前的安全控制是散的：脚本在 Blob 里，执行器拉下来就跑，没有统一的「执行前审批/策略」关卡。这跟你项目里「安全与权限设计」的目标有缺口。

### 落地改造

给 Playwright 脚本执行加一个**三层守卫**，对应 dsh 的 pre-execute / guards / approval：

| dsh 层 | AI_test 落地 | 实现方式 |
|---|---|---|
| `pre-execute` 瀑布流 | 执行前策略检查 | Azure Function 前置：校验脚本来源、是否评审通过、是否越权访问 |
| `monotonic guards` | 单调守卫（不可被绕过） | 固定的安全规则：脚本禁止访问生产库、禁止删除操作、禁止访问指定域名 |
| `approval` | 一次性审批 | 高风险脚本（涉及写操作/生产环境）执行前弹 Power Apps 审批卡 |

**落地示意图**：

```
脚本触发执行
   ↓
[pre-execute] 前置策略 Function：脚本是否评审通过？来源是否可信？
   ↓ deny → 拦截并通知
   ↓ allow
[guards] 单调守卫：检查脚本 AST 是否命中「危险操作」黑名单（删库、drop、rm -rf）
   ↓ deny → 硬拦截（不可绕过）
   ↓ allow
[approval] 高危脚本 → Power Automate 审批流 → 人批了才执行
   ↓
[execute] Playwright 执行器（含超时、重试、指标采集）
   ↓
[post-execute] 结果归一化 + 截图/日志归档 + 状态写回
```

**这一步直接补上了你项目里「安全与权限设计」里最薄的一块**——脚本执行本身的安全边界。dsh 的 `tools/pre-execute` 那套「瀑布流 + 单调守卫」是现成的参考模型。

---

## 3. 核心借鉴点 3：把「评审通过」改造成可验证的状态机

### dsh 的做法

dsh 的 goal 子系统把「目标」做成了一个**事件溯源（event-sourced）的状态机**，关键设计：

- **阶段（phase）**：`active` / `paused` / `blocked` / `complete`，四种状态清晰
- **blocked 带原因**：`{ code: "kebab-case", message: "..." }`，机器可路由 + 人类可读
- **Compare-and-set 引用**：每次 mutation 都带 `revision`，防止并发覆盖
- **所有变更都是 durable 事件**：追加到日志，可重放、可恢复

### AI_test 的现状

当前「用例评审模块」的状态是松散的：评审结果写回 `test_case_review` 表，状态字段是「通过/需修改/废弃」，但没有：

- 明确的**状态机**（一条用例的生命周期到底有哪些状态、怎么流转）
- **可验证的通过条件**（什么算「评审通过」，目前靠人主观判断）
- **变更追溯**（谁在什么时候改了什么状态，没有事件日志）

### 落地改造

给「用例生命周期」定义**明确状态机 + 可验证通过条件**：

```
用例状态机（参考 dsh 的 goal phase）：
  draft（草稿）
    → generating（AI 生成中）
    → pending_review（待评审）
    → [review] approved（评审通过）/ rejected（驳回）
    → approved → script_generated（已生成脚本）
    → executed（已执行）
    → [result] passed / failed / flaky
    → failed → analyzed（已分析）/ fixed（已修复）
```

**关键借鉴 2 点**：

1. **「评审通过」必须可验证**，不能是模糊的「人觉得可以」。参考 dsh 的 `blockedReason`，给每条驳回一个结构化的 `code + message`：

```
{
  "reviewStatus": "rejected",
  "rejectReason": {
    "code": "incomplete-steps",      // 机器可路由的稳定分类
    "message": "步骤不完整，缺少预期结果"
  }
}
```

2. **状态变更走事件日志**，而不是直接改字段。参考 dsh 的 event-sourced 设计，在 Azure SQL 里加一张 `TestCaseStateLog` 表（你的数据模型里已经有 `AIReasoningLog` 的思路，扩一个状态日志表），记录每次状态迁移：`谁 + 何时 + 从什么 → 变到什么 + 原因`。

这样你项目里「评审反馈闭环」（评审人的修改记录作为 fine-tuning 数据）就有据可依了。

---

## 4. 核心借鉴点 4：事件的「派发模式」分类，理清 Power Automate 的编排

### dsh 的做法

dsh 把事件分成 **5 种派发模式**，每种语义清晰：

| 模式 | 是否等待 | 顺序 | 有返回值 |
|---|---|---|---|
| `emit` | 否 | 注册顺序观察 | 无 |
| `waterfall` | 否 | 注册顺序 | 有（可短路） |
| `parallel` | 是 | 并行 | 无 |
| `serial` | 是 | 注册顺序 | 有 |
| `bail` | 否 | 直到一个 bail | 有 |

### AI_test 的现状

当前 8 个工作流（需求解析、用例生成、评审、脚本生成、执行、失败分析、报告、端到端主流程）是 Power Automate 里各自独立的 Flow，触发关系靠 Dataverse 表状态变更驱动。但**没有明确「这个环节的多个下游是并行还是串行、谁短路谁」**。

### 落地改造

给 AI_test 的每个工作流节点，标注**它属于哪种派发模式**，理清编排语义：

| AI_test 环节 | 对应 dsh 模式 | 说明 |
|---|---|---|
| 需求解析完成 → 通知 PM + 写索引 | `parallel` | 通知和索引可以并行，互不依赖 |
| 用例生成 → AI 去重 → 合并 | `serial` | 必须顺序：去重后才能合并 |
| 用例评审 → 评分 → 低于阈值退回 | `waterfall` | 评分是「短路」点：低于阈值直接退回，不继续 |
| 失败分析 → 分类 → 归因 | `bail` | 命中 flaky 判定就短路，不再走真实缺陷分析 |
| 报告聚合 | `parallel` | 多个维度数据并行聚合 |

**这一步的价值**：你现在的 Power Automate 流程是「线性串行」的，但实际业务里有些环节应该并行（省时间）、有些应该短路（省 token、省资源）。借用 dsh 的派发模式分类，能帮你**重新审视每个 Flow 的编排是否最优**。

---

## 5. 核心借鉴点 5：Profile / Bundle / Patch 的「组合式配置」

### dsh 的做法

dsh 启动一个实例 = 从**有序 layer 组合**出一棵插件树：

- **Profile**：命名组合（web / headless / sdk / acp）
- **Bundle**：分发格式，声明自己挂哪些 config row
- **Patch**：`cordis.patch.yml`，按 row id 覆盖某个 config

最妙的是 `--dump-config` 能打印「这台机器实际 boot 出来的完整树」，任何一行都能被自己的 patch 覆盖。

### AI_test 的现状

当前是四套环境（dev/test/staging/prod），配置靠 Power Platform 环境变量 + Azure 部署参数。但**没有一个「当前环境实际生效的完整配置清单」**，排查「为什么测试环境和生产行为不一样」很痛苦。

### 落地改造

借鉴「组合式配置 + 可 dump」的思想，给 AI_test 做一份**环境配置清单（配置即代码）**：

- 把每个环境的「AI 模型版本、prompt 模板、插件启用清单、阈值参数」都显式化到一份配置清单里
- 部署时按 `profile（环境） + patch（差异）` 的方式组合
- 加一个「配置 dump」能力：一键导出「当前环境实际生效的完整配置」，方便 diff 测试环境 vs 生产环境

这对应你项目里「部署与测试方案」的环境隔离，能显著降低「环境漂移」问题。

---

## 6. 一个「不要借鉴」的提醒

dsh 有一个东西**不建议 AI_test 现在引入**：

- **Cordis 的「全部插件化」架构在 Power Platform 里成本过高**。Power Automate + Dataverse 本身就是低代码，把「每个环节都做成可插拔插件」如果过度，会变成「为了一次性灵活性引入一套框架」。**只在「流水线环节」这一层做插件化（第 1 节），不要下沉到「每个 AI 能力都插件化」。**

另一个「暂缓」项：

- **dsh 的 native Landlock 沙箱、E2B 远程沙箱**。你的 Playwright 执行器如果已经跑在容器里，容器本身就是沙箱边界，不必立刻上 Landlock 这套。等执行器真正要跑「不受信任的 AI 生成脚本」时再考虑。

---

## 7. 落地优先级排序（按投入产出比）

| 优先级 | 借鉴点 | 投入 | 收益 | 对应你项目的模块 |
|---|---|---|---|---|
| ⭐⭐⭐ | 流水线插件化（第 1 节） | 中（改 Flow + 加插件表） | 高：新增环节不用改主流程 | 工作流设计、功能模块 |
| ⭐⭐⭐ | 执行安全守卫（第 2 节） | 中（加 3 层前置 Function） | 高：补安全缺口 | 安全与权限、测试执行 |
| ⭐⭐⭐ | 状态机 + 可验证通过条件（第 3 节） | 低（改数据模型 + 加状态表） | 高：评审闭环有据可依 | 数据模型、评审模块 |
| ⭐⭐ | 派发模式标注（第 4 节） | 低（文档标注） | 中：理清编排 | 工作流设计 |
| ⭐ | 组合式配置（第 5 节） | 中（配置重构） | 中：减少环境漂移 | 部署方案 |

**建议起步顺序**：先做第 3 节（投入最低、收益立竿见影），再做第 1、2 节（投入中等、是架构级提升），第 4 节顺手标注，第 5 节等项目稳定后再重构。

---

## 附：可以直接落地的具体改动清单

1. **新增 Dataverse 表** `ait_pipeline_plugin`（插件注册表）— 支持第 1 节
2. **新增 Dataverse 表** `ait_testcase_state_log`（用例状态事件日志）— 支持第 3 节
3. **新增 Azure Function** `execution-guard`（执行前守卫）— 支持第 2 节
4. **改造 `test_case_review` 表**：`rejectReason` 从自由文本改成 `code + message` 结构化 — 支持第 3 节
5. **工作流文档补充**：给 8 个 Flow 标注派发模式 — 支持第 4 节
