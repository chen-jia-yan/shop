#!/bin/bash
# ============================================================
# subagent-filter.sh — SubagentStop 子代理输出智能过滤
# 事件: SubagentStop
# stdin JSON: {hook_event_name, agent_id, agent_transcript_path, agent_type, last_assistant_message, ...}
# 子代理结束前，对冗长输出提取核心结论
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
AGENT_ID=$(json_get ".agent_id" <<< "$INPUT")
LAST_MSG=$(json_get ".last_assistant_message.text" <<< "$INPUT")
if [ -z "$LAST_MSG" ] || [ "$LAST_MSG" = "null" ]; then
  LAST_MSG=$(json_get ".last_assistant_message" <<< "$INPUT")
fi
TRANSCRIPT_PATH=$(json_get ".agent_transcript_path" <<< "$INPUT")

if [ -z "$LAST_MSG" ] || [ "$LAST_MSG" = "null" ]; then
  exit 0
fi

MSG_LEN=${#LAST_MSG}

# 短消息不需要过滤
if [ "$MSG_LEN" -lt 500 ]; then
  log_event "SubagentStop" "ok" "short_enough: $AGENT_ID ($MSG_LEN chars)"
  exit 0
fi

# ---- 智能提取核心结论 ----
# 策略：查找 "结论" / "总结" / "核心发现" / "Report" / "Summary" 等标记后的内容
SUMMARY=""

# 用 node 做智能截取（比 bash 字符串操作更可靠）
SUMMARY=$(node -e "
  const msg = $(echo "$LAST_MSG" | node -e "process.stdin.pipe(process.stdout)" 2>/dev/null || echo '""');
  const text = typeof msg === 'string' ? msg : (msg.text || '');
  if (text.length < 500) { process.stdout.write('SHORT'); process.exit(0); }

  // 查找后半部分的标记
  const markers = ['## 总结', '## Summary', '核心发现', '结论', 'Report:', '## 结论', '### 结论', 'TL;DR', '要点总结'];
  let bestIdx = -1;
  for (const m of markers) {
    const idx = text.lastIndexOf(m);
    if (idx > text.length * 0.3) { bestIdx = idx; break; }
  }

  if (bestIdx > 0) {
    process.stdout.write(text.slice(bestIdx, bestIdx + 2500));
  } else {
    // 没找到标记，取最后 40% 内容（结论通常在末尾）
    const start = Math.floor(text.length * 0.6);
    process.stdout.write(text.slice(start, start + 2000));
  }
" 2>/dev/null)

if [ -z "$SUMMARY" ] || [ "$SUMMARY" = "SHORT" ]; then
  log_event "SubagentStop" "ok" "filter_skip: $AGENT_ID"
  exit 0
fi

# ---- 注入过滤后的上下文 ----
log_event "SubagentStop" "filtered" "$AGENT_ID: ${MSG_LEN} -> ~${#SUMMARY} chars"

# 清理特殊字符
SAFE_SUMMARY=$(echo "$SUMMARY" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')

cat <<FILTERED
{"hookSpecificOutput":{"hookEventName":"SubagentStop","additionalContext":"📋 子 Agent ($AGENT_ID) 核心结论：\\n$SAFE_SUMMARY"}}
FILTERED

exit 0
