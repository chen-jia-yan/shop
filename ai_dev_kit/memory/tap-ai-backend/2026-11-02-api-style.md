---
id: 2026-11-02-api-style
type: convention
project: tap-ai-backend
subject: 接口只用 GET/POST，业务错误返回 HTTP 200 加 code
tags: 接口, 规范, 错误码
status: active
priority: normal
created: 2026-11-02
verified: 2026-11-18
source: 后端接口规范
citations:
  - src/tap_ai/api/library_kb.py#@router.post
---
事实：新接口只用 GET 和 POST；业务错误返回 HTTP 200 加 {code, message}（例如 CCB001）；分页返回 items、total、page、page_size。
原因：前端和已有接口按这个约定处理。
怎么用：写接口前先加载风格包里的“HTTP 接口”卡片。
