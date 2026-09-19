# 任务：实现知识库管理动作执行器 kb_admin_actions.py，复用现有审批机制，纯标准库/复用现有 client

## 背景与约束
本地知识库 ingest 系统已有：SQLite 状态库、incremental ingest（enqueue/reindex）、按 doc_id 删除文档 chunk 的能力、ops_recommendations 审批表 + /api/admin/recommendations 审批接口（诊断模块建的）。现在加一个「自然语言管理台」：运维输入自然语言 → 模型（用 kb_admin 管理 skill 当 system prompt）输出白名单动作 JSON → 系统执行，其中破坏性动作复用现有审批机制。

硬约束：
- 只用标准库 + 已有聊天模型 client。禁止新增依赖，禁止让模型或本模块执行任何原始 SQL。
- 模型只能触发白名单动作；破坏性动作（delete_document / retry_failed）必须走人工审批，绝不自动执行。
- Windows；先输出计划和 diff，我确认后实现。

## 改动 1：kb_admin_actions.py
- 定义动作分类：
  READ = {"list_documents","get_status","find_documents"}
  WRITE = {"add_files","scan_folder","reindex"}
  DESTRUCTIVE = {"delete_document","retry_failed"}
- execute_admin_action(db, index_repo, action, args) 把每个动作映射到既有函数：
  - list_documents/get_status/find_documents → 查 SQLite 返回结果
  - add_files/scan_folder → enqueue_files（走现有 incremental 入队）
  - reindex → 现有 reindex 流程（先删旧 chunk 再插新）
  - delete_document(doc_id) → 现有「按 doc_id 删除该文档全部 chunk」+ 从 SQLite 移除/标记
  - retry_failed → 现有 retry_failed(db)
- handle_admin_request(chat_client, db, index_repo, model, nl_text):
  1. 用 kb_admin 管理 skill 当 system prompt，nl_text + 当前状态摘要当 user 消息，temperature=0，要求 JSON 输出。
  2. 解析出 {intent, action, action_args, needs_human, explanation}。
  3. 分派：
     - action=clarify/escalate_human → 直接把问题/理由返回给运维，不执行。
     - READ 类 → 立即执行并返回结果（可再调一次模型把结果组织成自然语言答复）。
     - WRITE 类 → 按配置：默认执行前给运维确认；确认后执行。
     - DESTRUCTIVE 类 → 不执行，调 add_recommendation 落一条 proposed（复用 ops_recommendations 表和 /api/admin/recommendations 审批接口），等人工 approve 后由 apply/execute 生效。
  4. 解析失败或动作不在白名单 → 安全降级：不执行、记日志、提示人工。

## 改动 2：审批接口复用
- 复用诊断模块已建的 ops_recommendations 表与 approve/reject 接口；管理动作作为同一套 proposed 动作走审批。approve 时调 execute_admin_action 真正执行 delete/retry。

## 改动 3：入口
- 加 /api/admin/nl-command，接收运维自然语言指令，调 handle_admin_request，返回：执行结果（读类）或“已提交审批 + 将要执行什么”（破坏类）。

## 验收标准
1. “有多少文档、几个失败” → 立即返回真实计数（读类，无需审批）。
2. “删掉 設計書_1.2” → 模型先 find_documents 定位 doc_id，再提出 delete_document，落为 proposed；未审批前索引不动；approve 后该文档 chunk 才被删。
3. 指令含糊（“把那个文件删了”）→ 返回 clarify 反问，不猜、不删。
4. 任何超范围请求（“清空索引”）→ escalate_human，不执行。
5. 模型输出非白名单动作或非法 JSON → 安全降级，不执行。

先输出：文件清单 + kb_admin_actions.py 关键实现 + /api/admin/nl-command 接口 + 与 ops_recommendations 审批的对接点，等我确认后再实现。


