#!/bin/bash
# ============================================================
# session-start.sh — SessionStart 会话生命周期管理
# 事件: SessionStart
# stdin JSON: {hook_event_name, source: "startup"|"resume"|"clear"|"compact", model, session_id, cwd, ...}
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
SOURCE=$(json_get ".source" <<< "$INPUT")
MODEL=$(json_get ".model" <<< "$INPUT")
SESSION=$(json_get ".session_id" <<< "$INPUT")

TIMESTAMP=$(date '+%Y-%m-%dT%H:%M:%S')

# ---- 会话启动日志 ----
SESSION_LOG="$TRACK_DIR/session-starts.jsonl"
echo "{\"ts\":\"$TIMESTAMP\",\"source\":\"$SOURCE\",\"model\":\"$MODEL\",\"session\":\"$SESSION\"}" >> "$SESSION_LOG"

# ---- 依赖工具检查 ----
MISSING_TOOLS=""
for tool in jq node pnpm git; do
  if ! command -v "$tool" &>/dev/null; then
    MISSING_TOOLS="$MISSING_TOOLS $tool"
  fi
done

# ---- Memory 目录检查（CC 原生路径，与 auto-memory.sh 一致） ----
MEMORY_DIR="$HOME/.claude/projects/E--wukuang-fe-minmetals-gu-fin-asset/memory"
NEW_MEMORIES=""
if [ -d "$MEMORY_DIR" ]; then
  # 查找最近 24 小时内新增的 memory 文件
  NEW_MEMORIES=$(find "$MEMORY_DIR" -name "*.md" -mtime -1 2>/dev/null | head -5)
fi

# ---- 向 Claude 注入上下文 ----
CONTEXT="📋 会话启动 | 来源: $SOURCE | 模型: ${MODEL:-unknown} | 时间: $TIMESTAMP"

if [ -n "$NEW_MEMORIES" ]; then
  CONTEXT="$CONTEXT\n🧠 最近 24h 新增记忆:\n$NEW_MEMORIES"
fi

if [ -n "$MISSING_TOOLS" ]; then
  CONTEXT="$CONTEXT\n⚠️ 缺失工具:$MISSING_TOOLS（部分 Hook 功能可能不可用）"
fi

log_event "SessionStart" "ok" "source=$SOURCE model=$MODEL"

cat <<SESSION
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"$CONTEXT"}}
SESSION

exit 0
