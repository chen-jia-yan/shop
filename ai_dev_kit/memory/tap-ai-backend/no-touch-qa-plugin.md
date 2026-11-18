---
id: 2026-11-02-no-touch-qa-plugin
type: decision
project: tap-ai-backend
subject: 问答知识插件属于同事业务，我们的任务不修改它
tags: 边界, 同事, knowledge 插件
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: 用户 11-02 确认
citations:
  - user:2026-11-02 用户说明 k2b 里对问答的改动越线了，问答是别人的业务
  - src/tap_ai/plugins/extensions/knowledge/settings.py#KnowledgeSettings
---
事实：src/tap_ai/plugins/extensions/knowledge/ 下的 settings、plugin、tools、prompts、spaces 以及 azure_search、neo4j_graph 由同事负责，我们不改。
原因：越线修改会影响同事的问答业务。
怎么用：确实需要改动时，先停下来写进“要和同事沟通的事项”，由用户决定。
