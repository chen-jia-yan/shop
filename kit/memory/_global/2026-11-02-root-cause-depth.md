---
id: 2026-11-02-root-cause-depth
type: lesson
project: _global
subject: 第一个报错不一定是根因，要一直追到能解释为什么
tags: 调试, 根因, 依赖
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: kg_schema 循环导入事故
citations:
  - user:2026-11-02 “缺 pptx”下面还藏着 kg_schema 与 sinks 的循环导入
---
事实：表面原因（缺少 python-pptx）被修好之后，真正的问题（循环导入）才暴露出来。
原因：只修表面原因会让人以为问题解决了。
怎么用：修 bug 时写出“为什么会这样”的完整链条；修完后用独立进程单独导入每个模块再验证一次。
