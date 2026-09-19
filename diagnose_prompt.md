# 任务：实现运维诊断模块 diagnose.py + supervisor 触发 + 人工审批，纯标准库/复用现有 client

## 背景与约束
本地日文知识库 ingest 系统：web 进程 + 独立 worker（ProcessPoolExecutor 消费 SQLite 里的 pending 任务）+ supervisor 守护进程（已有：监控内存、重启 worker、回收卡死任务、写 health 表）。现在要加一个「诊断大脑」：当系统进入 CRITICAL 时，用现有的聊天模型读 health 数据，产出结构化诊断和建议动作，但**默认不自动执行危险操作，需人工审批**。

硬约束：
- 只用标准库 + 项目已有的聊天模型 client（就是 RAG agent 用的那个 Azure OpenAI chat 部署，与 embeddings client 是同资源不同用途）。禁止新增 pip 依赖。
- 不走检索/向量搜索，这只是一次普通 LLM 调用，把 health 数据当输入。
- 模型输出绝不直接自动执行破坏性动作；只能调用下面白名单里的既有函数。
- Windows；先输出改动计划和 diff，我确认后再实现。

## 改动 1：ops_diagnostic_skill.md（诊断 system prompt）
- 把我已有的那份运维诊断 skill 存为项目内文件 ops_diagnostic_skill.md。
- 在其末尾追加一条：输出必须是**严格 JSON**，字段：
  {"status": "...", "severity": "OK|WARN|CRITICAL", "diagnosis": "...", "root_cause": "...",
   "action": "pause_dispatch|resume_dispatch|set_max_inflight|retry_failed|quarantine_file|restart_worker|escalate_human",
   "action_args": {...}, "reason": "...", "needs_human": true|false}
- 便于程序解析；除 JSON 外不要输出其他内容。

## 改动 2：state_store 增补
- get_recent_logs(db, n=20)：返回最近 n 条 supervisor/worker 日志（可从日志表或读日志文件尾部）。
- ops_recommendations 表：id, ts, severity, action, action_args(JSON), reason, state('proposed'|'approved'|'applied'|'rejected'), applied_ts。
- 提供：add_recommendation(...)、list_recommendations(state=...)、set_recommendation_state(id, state)。

## 改动 3：diagnose.py
```
import json, logging
from kb_admin.state_store import get_health, get_recent_logs, add_recommendation

OPS_SKILL = open("ops_diagnostic_skill.md", encoding="utf-8").read()
log = logging.getLogger("ops")

def diagnose_health(chat_client, db, model):
    payload = {"health": get_health(db), "recent_logs": get_recent_logs(db, 20)}
    resp = chat_client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": OPS_SKILL},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        temperature=0,
        response_format={"type": "json_object"},   # 若部署支持；否则自行 json.loads 容错
    )
    try:
        rec = json.loads(resp.choices[0].message.content)
    except Exception as e:
        log.error("诊断输出解析失败：%s", e); return None
    add_recommendation(db, rec)                     # 落库为 'proposed'
    log.warning("诊断建议：%s", rec)
    return rec
```

## 改动 4：supervisor 触发（带冷却，别刷爆 LLM）
- 在 supervisor 循环里，仅当进入 CRITICAL（memory_load>=92 持续 / worker_alive=false / dead 短时激增 / 反复 BrokenProcessPool）才调 diagnose_health。
- 冷却：同一 CRITICAL 状态下最多每 N 分钟调一次（如 5 分钟），或仅在「状态从非 CRITICAL 跳变为 CRITICAL」时调一次。避免每个轮询周期都调模型。

## 改动 5：人工审批 + apply_action（关键护栏）
- 配置项：AUTO_APPLY_SAFE（默认 False）。
- 动作分两类：
  - 可逆的安全动作：pause_dispatch / resume_dispatch / set_max_inflight —— 若 AUTO_APPLY_SAFE=True 允许自动执行；否则同样入审批。
  - 影响性/破坏性动作：retry_failed / quarantine_file / restart_worker —— **永远需要人工审批**，绝不自动执行。escalate_human 只告警不动作。
- apply_action(db, rec) 把白名单动作映射到既有函数：
  - pause_dispatch/resume_dispatch → set_control(db, paused=...)
  - set_max_inflight(n) → set_control(db, max_inflight=n)
  - retry_failed → retry_failed(db)
  - quarantine_file(doc_id) → mark(db, doc 对应 file, 'dead', error='人工确认隔离')
  - restart_worker → 交给 supervisor 重启
  - escalate_human → 仅记录告警
- 审批入口：暴露 /api/admin/recommendations（列出 proposed）、/api/admin/recommendations/{id}/approve、/reject。approve 时调 apply_action 并把 state 改 applied；reject 改 rejected。前端给运维一个简单列表 + 批准/驳回按钮。

## 验收标准（请给出验证步骤）
1. 模拟 memory_load>=92：supervisor 触发一次 diagnose，ops_recommendations 里出现一条 proposed，日志有结构化建议。
2. 冷却生效：持续 CRITICAL 时不会每个周期都调模型。
3. 破坏性动作（retry_failed/quarantine/restart）在未审批时绝不执行；approve 后才通过 apply_action 生效。
4. AUTO_APPLY_SAFE=True 时，仅 pause/set_max_inflight 可自动执行，其余仍需审批。
5. 诊断输出解析失败时安全降级（记错误、不执行任何动作）。

先输出：改动文件清单 + 关键 diff（diagnose.py、state_store 的 ops_recommendations/get_recent_logs、supervisor 触发与冷却、apply_action 与审批接口），等我确认后再实现。


