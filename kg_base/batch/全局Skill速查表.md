# 全局 Skill 速查表

> 安装目录：`~/.claude/skills/`，共 48 个，新会话自动加载。
> 三个来源：`ai-for-everyone-skill`（25） + `loop-engineering-skill`（8） + `system-prompt-skills`（15）

---

## 一、AI 项目方法论（25 个）— 吴恩达《AI for Everyone》蒸馏

### 🧠 1. 可行性判断

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `ab-mapping` | 把业务问题框成 A→B 输入输出 | "AI 能不能做X"、"这算不算机器学习问题" |
| `one-second-rule` | 用人类一秒反应时间判断技术可行性 | "这个 AI 能做吗"、"技术上可行吗" |
| `ml-feasibility` | 双因素评估：简单概念 + 充足数据 | "这个想法可行吗"、"需要多少数据" |

### 🎯 2. 项目选择与评估

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `cross-functional-brainstorming` | 跨职能团队找 AI 场景 | "该做什么 AI 项目"、"怎么找到 AI 落地场景" |
| `automate-task` | 把岗位拆成可自动化任务 | "替代 XX 岗位"、"全自动"、"AI 取代" |
| `triple-due-diligence` | 技术×商业×伦理三重尽调 | "这个项目值得做吗"、"该投入多少" |
| `three-value-drivers` | 降本 / 增收 / 新业务 | AI 价值驱动三途径 |

### 🔄 3. 项目执行流程

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `ml-vs-ds` | 判定 ML（产软件）还是 DS（产洞察） | 项目类型判定 |
| `ml-workflow` | 收集→训练→部署→迭代四步 | ML 项目执行流程 |
| `train-test-split` | 训练/测试集分离，AI 的"科学方法" | 模型评估 |
| `statistical-acceptance` | 不追求 100% 准确，统计化验收 | 验收标准设定 |
| `ai-pipeline` | 多组件串联系统设计，误差累积 | 复杂 AI 系统架构 |
| `ai-project-lifecycle` | 从立项到落地的完整流程 | AI 项目生命周期 |

### 🏛️ 4. 组织转型与团队

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `ai-transformation-playbook` | AI 转型五步指南 | 组织 AI 变革 |
| `pilot-momentum-flywheel` | 试点势能飞轮，先求成功 | 试点项目推进 |
| `role-tiered-training` | 高管/经理/工程师分层培训 | 团队 AI 能力建设 |
| `ai-team-building` | AI 团队角色与协作设计 | 组建 AI 团队 |

### 📊 5. 数据战略

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `data-flywheel` | 数据飞轮，AI 产品自我强化 | 数据战略设计 |
| `unified-data-warehouse` | 统一数据仓库，打破数据孤岛 | 数据基础设施 |
| `dont-wait-perfect-data` | 不等完美数据，先用起来再迭代 | 数据策略 |
| `dont-acquire-for-data` | 不为数据而收购，价值验证先行 | 并购决策 |
| `build-vs-buy` | AI 自建 vs 购买决策框架 | 技术选型 |
| `start-small-find-partner` | 从小处着手，寻找伙伴 | AI 入门策略 |
| `iterate-not-perfect` | 迭代而非完美，渐进式改进 | 产品迭代 |
| `ai-strategy-moat` | 用 AI 构建可持续竞争优势 | 战略规划 |

---

## 二、Loop 工程化（8 个）— Agent 循环系统设计

| Skill | 用在哪 | 触发方式 |
|---|---|---|
| `loop-worthiness-test` | 判断任务是否值得做成 Loop（四条标准） | "这件事值得做 loop 吗"、"该不该自动化" |
| `loop-three-elements` | Loop 三要素：Trigger / Action / Stop | "设计一个 loop"、"这个循环为什么不停止" |
| `loop-5plus1-architecture` | 5 大组件 + 1 脊柱的完整架构 | "设计一个完整的 loop 系统"、"我的 loop 缺什么" |
| `loop-build-path` | 从手动到自动的四步渐进路径 | "怎么开始做 loop"、"自动化第一步" |
| `maker-checker` | 用独立 agent 审查产出，避免自产自检 | "agent 自评不准确"、"产出质量不稳定" |
| `goal-verification` | 把模糊目标改造成可验证的停止条件 | "loop 停不下来"、"怎么定义完成" |
| `comprehension-gap` | 自动化越高，理解越少——认知风险管理 | "AI 生成的代码我看不懂"、"产出太多理解不过来" |
| `three-stage-evolution` | 评估个人/团队 AI 使用阶段，给下一步建议 | "我现在在哪个阶段"、"团队 AI 能力评估" |

---

## 三、System Prompt 设计（15 个）— AI 产品的提示词工程

### 身份与风格

| Skill | 用在哪 |
|---|---|
| `persona-design` | 定义 AI 的核心身份、角色声明、能力边界 |
| `personality-system` | 可切换的人格风格层（语气/口吻/性格） |

### 安全与防御

| Skill | 用在哪 |
|---|---|
| `safety-guardrails` | 多层安全防线、拒绝策略、价值观锚点 |
| `injection-defense` | 防 prompt 注入、越狱、社会工程攻击 |

### 对话与交互

| Skill | 用在哪 |
|---|---|
| `conversation-flow` | 意图分类、对话路由、澄清策略、自主度控制 |
| `output-formatting` | 格式规范、长度约束、反"AI 味"策略 |
| `voice-optimization` | 语音交互场景的输出优化 |
| `mobile-adaptation` | 移动端（手机/平板）场景适配 |

### 工具与能力

| Skill | 用在哪 |
|---|---|
| `tool-specification` | 工具接口定义、调用规范、权限与并行调度 |
| `agent-delegation` | 多代理协作架构、子代理分工、生命周期管理 |
| `search-integration` | 搜索触发策略、数据源选择、结果处理 |
| `citation-system` | 引用格式、信息溯源、来源标注 |

### 工程基础

| Skill | 用在哪 |
|---|---|
| `code-engineering` | Coding Agent 的 prompt 工程规范 |
| `context-management` | Token 预算、压缩策略、延迟加载 |
| `memory-system` | 记忆存储/检索/更新/应用生命周期 |

---

## 四、按场景快速查找

| 你想问... | 用哪个 |
|---|---|
| 这个需求能用 AI 做吗？ | `ab-mapping` → `one-second-rule` → `ml-feasibility`（按顺序） |
| 这个 AI 项目值得投吗？ | `triple-due-diligence` |
| 怎么开始做一个 AI 项目？ | `ml-vs-ds` → `ml-workflow` → `ai-project-lifecycle` |
| 怎么把业务流程自动化？ | `automate-task` → `loop-worthiness-test` → `loop-build-path` |
| 自动化 loop 出问题了 | `loop-three-elements` → `goal-verification` → `maker-checker` |
| 怎么设计 AI 产品的 prompt？ | `persona-design` → `conversation-flow` → `safety-guardrails` |
| AI 产品怎么防注入？ | `injection-defense` → `safety-guardrails` |
| 怎么给 AI 加工具？ | `tool-specification` → `agent-delegation` |
| 团队 AI 能力怎么提升？ | `three-stage-evolution` → `role-tiered-training` |
| 数据不够怎么办？ | `dont-wait-perfect-data` → `data-flywheel` |
| 自建还是买 AI 方案？ | `build-vs-buy` → `dont-acquire-for-data` |
| 怎么找到 AI 应用场景？ | `cross-functional-brainstorming` → `three-value-drivers` |

---

> **使用方式**：直接说需求，Agent 会自动匹配对应 skill。也可以用 `/skill-name` 手动调用。
> 更新日期：2026-08-22