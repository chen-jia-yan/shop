---
id: 2026-11-21-data-no-delete
type: decision
project: tap-ai-backend
subject: 数据可以写入；删除数据要先评估风险、告诉用户、等用户同意，不能乱删（包括运行测试）
tags: 删除, 风险评估, Neo4j, Azure, 数据库, 测试
status: active
priority: high
created: 2026-11-21
verified: 2026-11-21
supersedes: 2026-11-02-jp-poc-readonly
source: 用户 11-21 说明
citations:
  - user:2026-11-21 数据可以写入，但是不能删除，哪怕运行测试什么的，也不能将数据真的删除
  - user:2026-11-21 删数据要先问我，等我同意，并且要评估风险，告知我，不是不能删，是不能乱删
  - src/tap_ai/plugins/ingest/sdk_ingest.py#_contains_forbidden_index
---
事实：Neo4j、数据库、搜索索引都可以写入。删除（DELETE / DETACH DELETE / DROP / TRUNCATE / REMOVE / 删除接口 / 清空索引）不是禁止，而是必须先经过用户同意。Azure jp-poc 索引手上只有查询密钥，实际上仍是只读。本地 TAP_AI_LIBRARY_KB_GRAPH_ENABLED=false。
原因：数据和同事共用，删错了无法恢复；测试里的清理代码最容易在没人注意时误删真实数据。
怎么用：要删除时先告诉用户 ① 要删什么 ② 范围（先做只读计数）③ 能不能恢复 ④ 删之前建议做什么（备份、软删除、换测试库），然后等用户回复“同意”；守卫会核对用户是否真的同意过这一条命令，同意只生效一次。测试和脚本通过 kit_run.py 运行，没经同意的删除会被拦下（KitDeleteBlocked）；同意后用 kit_run.py --allow-delete 运行，每次删除都记日志。测试优先用假对象，不连真实库。
