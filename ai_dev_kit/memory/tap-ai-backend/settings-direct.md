---
id: 2026-11-02-settings-direct
type: convention
project: tap-ai-backend
subject: 配置直接用 settings.字段 访问，不用 getattr 加默认值
tags: 配置, settings, getattr
status: active
priority: normal
created: 2026-11-02
verified: 2026-11-18
source: K2b 精简版
citations:
  - src/tap_ai/config/settings.py#library_kb_graph_enabled
---
事实：getattr(settings, "x", False) 会掩盖字段名拼错、字段被删等问题，并且让默认值分散在各处。
原因：开关和默认值应该只在 settings.py 定义一次。
怎么用：直接写 settings.library_kb_graph_enabled；需要新开关先在 settings.py 定义，并尽量默认开启、少加开关。
