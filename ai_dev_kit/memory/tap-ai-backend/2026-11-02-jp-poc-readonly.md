---
id: 2026-11-02-jp-poc-readonly
type: decision
project: tap-ai-backend
subject: jp-poc 索引和图谱只读，入库链路一律拒绝写入
tags: jp-poc, 只读, Azure, Neo4j
status: superseded
priority: high
created: 2026-11-02
verified: 2026-11-18
superseded_by: 2026-11-21-data-no-delete
source: 用户确认的安全约束
citations:
  - user:2026-11-02 jp-poc 只能读，只能用查询密钥；Neo4j 写入只允许导入脚本且限定 scope=jp-poc
  - src/tap_ai/plugins/ingest/sdk_ingest.py#_contains_forbidden_index
---
事实：Azure 的 jp-poc 索引只读；Neo4j 中 scope=jp-poc 的数据只能由导入脚本写入；hk 的 Neo4j 数据现阶段不删不改。
原因：jp-poc 是共享的演示数据，hk 的 Neo4j 与同事共用。
怎么用：任何写入前先确认目标索引和 scope；本地把 TAP_AI_LIBRARY_KB_GRAPH_ENABLED 设为 false。
