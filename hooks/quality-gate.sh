#!/bin/bash
# ============================================================
# quality-gate.sh — Stop 事件质量门控
# 事件: Stop
# stdin JSON: {hook_event_name, stop_hook_active, last_assistant_message, session_id, cwd, ...}
# 退出 0=批准停止, 2=阻止停止+反馈
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')

# 提取最后一条 assistant 消息（可能是对象或字符串）
LAST_MSG=$(json_get ".last_assistant_message.text" <<< "$INPUT")
if [ -z "$LAST_MSG" ]; then
  LAST_MSG=$(json_get ".last_assistant_message" <<< "$INPUT")
fi

if [ -z "$LAST_MSG" ] || [ "$LAST_MSG" = "{}" ]; then
  exit 0
fi

# 只取前 3000 字符检查
MSG_PREVIEW=$(echo "$LAST_MSG" | cut -c1-3000)

ISSUES=""

# ---- 检查1：待办清单 + 进度总结 格式完整性 ----
HAS_TODO=$(echo "$MSG_PREVIEW" | grep -c '\*\*【待办清单】\*\*' 2>/dev/null || echo "0")
HAS_PROGRESS=$(echo "$MSG_PREVIEW" | grep -c '\*\*【进度总结】\*\*' 2>/dev/null || echo "0")

if [ "$HAS_TODO" -eq 0 ] 2>/dev/null || [ "$HAS_PROGRESS" -eq 0 ] 2>/dev/null; then
  ISSUES="$ISSUES\n⚠️ 回复缺少格式尾：【待办清单】+【进度总结】"
fi

# ---- 检查2：代码块闭合 ----
TICK_COUNT=$(echo "$LAST_MSG" | grep -o '```' | wc -l 2>/dev/null || echo "0")
TICK_COUNT=$(echo "$TICK_COUNT" | tr -d ' ')
if [ "$((TICK_COUNT % 2))" -ne 0 ] 2>/dev/null; then
  ISSUES="$ISSUES\n⚠️ 代码块 \`\`\` 未闭合（$TICK_COUNT 个标记，应为偶数）"
fi

# ---- 检查3：是否有改动但未提 lint ----
# 通过 .track/file-changes.jsonl 判断本轮是否有文件改动
TRACK_FILE="$TRACK_DIR/file-changes.jsonl"
LINT_MENTIONED=$(echo "$MSG_PREVIEW" | grep -ci "pnpm lint\|pnpm run lint\|lint 通过\|lint 验证" 2>/dev/null || echo "0")

if [ -f "$TRACK_FILE" ] && [ "$LINT_MENTIONED" -eq 0 ] 2>/dev/null; then
  # 检查最近 5 分钟内是否有代码改动
  RECENT_CHANGES=$(find "$TRACK_FILE" -mmin -5 2>/dev/null)
  if [ -n "$RECENT_CHANGES" ] && [ -s "$TRACK_FILE" ]; then
    ISSUES="$ISSUES\n💡 本轮有代码改动但未提及 lint 验证结果。建议补上。"
  fi
fi

# ---- 汇总 ----
if [ -n "$ISSUES" ]; then
  log_event "Stop" "quality_issue" "$(echo "$ISSUES" | tr '\n' ' ')"
  cat <<GATE
{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"📋 质量门控（来自 quality-gate Hook）：$ISSUES"}}
GATE
  exit 0
fi

log_event "Stop" "quality_ok" "格式完整，代码块闭合"
exit 0
