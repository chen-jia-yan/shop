# kb_admin/diagnose.py
import json, logging
from kb_admin.state_store import get_health, get_recent_logs

OPS_SKILL = open("ops_diagnostic_skill.md", encoding="utf-8").read()  # 上一条那份

def diagnose_health(client, db):
    health = get_health(db)                    # health 表最新快照
    logs = get_recent_logs(db, n=20)           # 最近告警/日志
    user_msg = json.dumps({"health": health, "recent_logs": logs}, ensure_ascii=False)

    resp = client.chat.completions.create(     # 复用 RAG agent 那个聊天模型
        model="你的-chat-deployment",
        messages=[
            {"role": "system", "content": OPS_SKILL},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    result = resp.choices[0].message.content
    logging.getLogger("ops").warning("诊断结果:\n%s", result)  # 落盘给你看
    return result                              # 交给人审批后再执行控制动作



supervisor循环里
# supervisor 循环里
snap = get_health(db)
if snap["memory_load"] >= 92 or not snap["worker_alive"]:   # CRITICAL 条件
    diagnose_health(chat_client, db)                        # 触发一次诊断


