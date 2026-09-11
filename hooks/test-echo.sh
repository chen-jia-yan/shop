#!/bin/bash
# ============================================================
# test-echo.sh — Stop 事件 Hook 系统健康检查
# 事件: Stop
# stdin JSON: {hook_event_name, session_id, stop_hook_active, ...}
# 每次触发记录日志，用于验证 Hook 系统正常工作
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
EVENT=$(json_get ".hook_event_name" <<< "$INPUT")
SESSION=$(json_get ".session_id" <<< "$INPUT")
STOP_ACTIVE=$(json_get ".stop_hook_active" <<< "$INPUT")
CWD=$(json_get ".cwd" <<< "$INPUT")

# 简短的本地日志（不依赖环境变量）
LOG="$HOME/.claude-hook-test.log"
echo "[$(date '+%H:%M:%S')] Hook 触发 | event=$EVENT | stop_active=$STOP_ACTIVE | cwd=$CWD" >> "$LOG"

# 同时写入项目级日志
log_event "Stop" "test_echo_ok" "session=$SESSION stop_active=$STOP_ACTIVE"

# 检查 JSON 解析是否正常（如果 event 为空说明解析失败）
if [ -z "$EVENT" ] || [ "$EVENT" = "null" ]; then
  echo "[$(date '+%H:%M:%S')] ⚠️ JSON 解析异常！stdin 前100字符: $(echo "$INPUT" | cut -c1-100)" >> "$LOG"
fi

exit 0
