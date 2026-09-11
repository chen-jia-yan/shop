#!/bin/bash
# ============================================================
# notify-done.sh — Stop 事件 Windows Toast 通知
# 事件: Stop
# stdin JSON: {hook_event_name, last_assistant_message, session_id, ...}
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')

# 提取最后一条消息文本（可能是对象嵌套）
PREVIEW=$(json_get ".last_assistant_message.text" <<< "$INPUT")
if [ -z "$PREVIEW" ] || [ "$PREVIEW" = "null" ]; then
  PREVIEW=$(json_get ".last_assistant_message" <<< "$INPUT")
fi

# Fallback
if [ -z "$PREVIEW" ] || [ "$PREVIEW" = "null" ] || [ "$PREVIEW" = "{}" ]; then
  PREVIEW="Claude Code 任务完成"
fi

# 清理后取前 80 字符
PREVIEW=$(echo "$PREVIEW" | head -1 | cut -c1-80)

# ---- 通知 ----
notify_windows "Claude Code" "$PREVIEW"

# ---- 日志 ----
echo "[$(date '+%H:%M:%S')] $PREVIEW" >> "$LOG_DIR/notifications.log" 2>/dev/null

log_event "Stop" "notified" "preview=$(echo "$PREVIEW" | cut -c1-50)"
exit 0
