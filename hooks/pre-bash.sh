#!/bin/bash
# ============================================================
# pre-bash.sh — PreToolUse(Bash) 命令安全拦截
# 事件: PreToolUse, matcher: Bash
# stdin JSON: {hook_event_name, tool_name, tool_input: {command}, session_id, cwd, ...}
# 退出 0=放行, 2=阻塞
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
COMMAND=$(json_get ".tool_input.command" <<< "$INPUT")
EVENT=$(json_get ".hook_event_name" <<< "$INPUT")
SESSION=$(json_get ".session_id" <<< "$INPUT")

if [ -z "$COMMAND" ]; then
  exit 0
fi

# ---- 黑名单：exit 2 绝对拦截 ----
# 使用 grep -Eq 做正则匹配，大小写不敏感

# rm -rf / (根目录) 或 rm -rf /* (根下所有)
if echo "$COMMAND" | grep -iqE "rm\s+-rf\s+/(\*|$|\s+$)"; then
  log_event "PreToolUse" "blocked" "rm -rf / 拦截: $COMMAND"
  block_tool "命令包含 rm -rf / 或 rm -rf /* ，已拦截。如需执行请手动操作。"
fi

# rm -rf ~ (用户主目录)
if echo "$COMMAND" | grep -iqE "rm\s+-rf\s+~($|\s+$)"; then
  log_event "PreToolUse" "blocked" "rm -rf ~ 拦截"
  block_tool "命令包含 rm -rf ~ ，已拦截。"
fi

# rm -rf . (当前目录)
if echo "$COMMAND" | grep -iqE "rm\s+-rf\s+\.($|\s+$)"; then
  log_event "PreToolUse" "blocked" "rm -rf . 拦截"
  block_tool "命令包含 rm -rf . (当前目录)，已拦截。"
fi

# git push --force 到主分支
if echo "$COMMAND" | grep -iqE "git\s+push\s+(-f|--force)\s+origin\s+(main|master)"; then
  log_event "PreToolUse" "blocked" "force push main/master 拦截"
  block_tool "禁止 force push 到 main/master。请用正常 push 或创建新分支。"
fi

# DROP / 危险数据库操作 — 仅在直接执行 SQL 时拦截（不拦 heredoc/echo 中的文档文本）
if echo "$COMMAND" | grep -iqE "(mysql|psql|sqlcmd|sqlite3|mongo|redis-cli).*(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)"; then
  log_event "PreToolUse" "blocked" "数据库危险操作拦截"
  block_tool "数据库破坏性操作已拦截。请手动执行。"
fi

# fork bomb
if echo "$COMMAND" | grep -q "():{ :|:& };:"; then
  log_event "PreToolUse" "blocked" "fork bomb"
  block_tool "检测到 fork bomb 模式，已拦截。"
fi

# dd 磁盘操作
if echo "$COMMAND" | grep -iqE "dd\s+if="; then
  log_event "PreToolUse" "blocked" "dd 磁盘操作"
  block_tool "dd 磁盘操作已拦截。"
fi

# ---- 高风险警告：不拦截但注入提示 ----
WARN_MSG=""
if echo "$COMMAND" | grep -iqE "git\s+reset\s+--hard"; then
  WARN_MSG="⚠️ 高风险：git reset --hard 会丢弃所有未提交改动"
elif echo "$COMMAND" | grep -iqE "git\s+clean\s+-fd"; then
  WARN_MSG="⚠️ 高风险：git clean -fd 会删除所有未跟踪文件"
elif echo "$COMMAND" | grep -iqE "npm\s+unpublish"; then
  WARN_MSG="⚠️ 高风险：npm unpublish 会从 registry 移除包"
elif echo "$COMMAND" | grep -iqE "docker\s+rm\s+-f"; then
  WARN_MSG="⚠️ 高风险：强制删除 Docker 容器"
elif echo "$COMMAND" | grep -iqE "kubectl\s+delete"; then
  WARN_MSG="⚠️ 高风险：kubectl delete 会影响集群资源"
fi

# ---- 审计日志：记录所有 Bash 命令 ----
log_event "PreToolUse" "ok" "command=$(echo "$COMMAND" | cut -c1-120)"

if [ -n "$WARN_MSG" ]; then
  log_event "PreToolUse" "warned" "$WARN_MSG"
  warn_tool "$WARN_MSG | 命令: $(echo "$COMMAND" | cut -c1-80)"
fi

exit 0
