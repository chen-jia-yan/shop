---
id: 2026-11-02-zero-tests-is-failure
type: lesson
project: _global
subject: “0 个测试运行”和“收集阶段中断”都算失败
tags: pytest, 验收, 收集错误
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: 修1b 验收事故
citations:
  - user:2026-11-02 在错误目录跑 pytest 显示 no tests ran；缺 pptx 时 7 个文件收集失败，新测试其实一个都没跑
---
事实：pytest 显示 no tests ran、collected 0 items 或 Interrupted: N errors during collection 时，相关测试根本没执行，不能当作通过。
原因：曾经因此误以为新测试已通过，实际上从未运行。
怎么用：验收时必须贴出工作目录和测试数量；用 run_checks.py，它会自动识别这几种情况。
