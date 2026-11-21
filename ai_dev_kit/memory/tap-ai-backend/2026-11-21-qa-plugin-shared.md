---
id: 2026-11-21-qa-plugin-shared
type: decision
project: tap-ai-backend
subject: 问答知识插件是共同开发的共享模块，可以改和优化，但不能改坏
tags: 共享模块, 同事, knowledge 插件, 兼容
status: active
priority: high
created: 2026-11-21
verified: 2026-11-21
supersedes: 2026-11-02-no-touch-qa-plugin
source: 用户 11-21 说明
citations:
  - user:2026-11-21 插件如果有问题可以改，那不是同事单人的，我也可以执行操作，进行优化，现在是在一起开发，只是不能改坏了
  - src/tap_ai/plugins/extensions/knowledge/settings.py#KnowledgeSettings
---
事实：src/tap_ai/plugins/extensions/knowledge/ 是和同事一起开发的共享模块，允许修改和优化。
原因：不是同事一个人的代码，但同事的问答业务依赖它，改坏了会直接影响对方。
怎么用：动手前先运行 run_checks.py --shared-baseline 记下当前测试结果；改动保持对外接口（函数签名、配置字段名、返回结构）兼容；改完用 run_checks.py 对比基线，通过的测试不能变少、失败不能变多；在总结里写清楚改了共享模块的哪些地方，方便同步给同事。
