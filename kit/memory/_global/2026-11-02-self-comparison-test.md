---
id: 2026-11-02-self-comparison-test
type: lesson
project: _global
subject: 对比测试的两边必须相互独立，不能拿模块和它自己比
tags: 测试, 无效测试, 对比
status: active
priority: normal
created: 2026-11-02
verified: 2026-11-18
source: 修1b 新旧白名单对比
citations:
  - user:2026-11-02 sinks._kg_schema 改为从 kg_schema 导入后，“新旧白名单相等”测试变成恒等
---
事实：当被比较的两个对象来自同一处定义时，相等测试永远通过，证明不了任何事情。
原因：这类测试会给出虚假的安全感。
怎么用：要证明“改动前后取值不变”，就拿上一次提交的版本（git show HEAD:路径）和当前版本比较。
