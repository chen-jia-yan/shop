---
id: 2026-11-02-kg-schema-leaf
type: lesson
project: fwd-tap-ingest
subject: kg_schema.py 必须是最底层文件，不得导入 tap_ingest_sdk 的模块
tags: 循环导入, kg_schema, SDK
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: 修1b
citations:
  - src/tap_ingest_sdk/kg_schema.py#本文件不得导入
---
事实：kg_schema.py 曾导入 sinks._kg_schema，而后者又反过来导入 kg_schema，先导入 kg_schema 时就会报错。
原因：后端图谱接口直接导入 kg_schema，一定会触发这个问题。
怎么用：kg_schema.py 只能导入标准库；类型常量只在这里定义一次，其他文件从这里导入。
