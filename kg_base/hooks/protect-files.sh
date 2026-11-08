#!/bin/bash
# ============================================================
# protect-files.sh — PreToolUse(Write|Edit) 文件保护
# 事件: PreToolUse, matcher: Write|Edit
# stdin JSON: {hook_event_name, tool_name, tool_input: {file_path}, session_id, ...}
# 退出 0=放行, 2=阻塞
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
FILE_PATH=$(json_get ".tool_input.file_path" <<< "$INPUT")
TOOL=$(json_get ".tool_name" <<< "$INPUT")

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# ---- 保护关键文件 ----
if is_protected_file "$FILE_PATH"; then
  log_event "PreToolUse" "blocked" "保护文件写入拦截: $FILE_PATH"
  cat <<BLOCKED
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"🔒 目标文件 '$FILE_PATH' 属于保护文件（配置/密钥/Hook自身）。请确认是否继续写入。"}}
BLOCKED
  exit 0
fi

# ---- .claude/ 目录下的非 Hook 文件二次确认 ----
case "$FILE_PATH" in
  *.claude/CLAUDE.md|*.claude/settings.json|*.claude/settings.local.json)
    log_event "PreToolUse" "blocked" "Claude 配置文件保护: $FILE_PATH"
    cat <<BLOCKED
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"🔒 Claude Code 配置文件 '$FILE_PATH'。修改它会影响 AI 行为，请确认。"}}
BLOCKED
    exit 0
    ;;
esac

# ---- 记录所有文件写入到跟踪日志 ----
TRACK_FILE="$TRACK_DIR/file-changes.jsonl"
TIMESTAMP=$(date '+%Y-%m-%dT%H:%M:%S')
echo "{\"ts\":\"$TIMESTAMP\",\"tool\":\"$TOOL\",\"path\":\"$FILE_PATH\"}" >> "$TRACK_FILE"

# 超过 100 条自动归档
LINES=$(wc -l < "$TRACK_FILE" 2>/dev/null || echo "0")
if [ "$LINES" -gt 100 ]; then
  ARCHIVE="$TRACK_DIR/file-changes-$(date '+%Y%m%d').jsonl"
  tail -50 "$TRACK_FILE" > "${TRACK_FILE}.tmp" 2>/dev/null
  mv "${TRACK_FILE}.tmp" "$TRACK_FILE" 2>/dev/null
fi

log_event "PreToolUse" "ok" "allow_write: $FILE_PATH"
exit 0
