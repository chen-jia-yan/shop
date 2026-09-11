#!/bin/bash
# ============================================================
# file-track.sh — PostToolUse(Write|Edit) 文件改动追踪
# 事件: PostToolUse, matcher: Write|Edit
# stdin JSON: {hook_event_name, tool_name, tool_input: {file_path}, tool_response, session_id, ...}
# 记录项目文件改动历史，支持事后审计和趋势分析
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
FILE_PATH=$(json_get ".tool_input.file_path" <<< "$INPUT")
TOOL=$(json_get ".tool_name" <<< "$INPUT")
SESSION=$(json_get ".session_id" <<< "$INPUT")

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# 只追踪源码文件
case "$FILE_PATH" in
  *.ts|*.tsx|*.vue|*.js|*.jsx|*.scss|*.css|*.json|*.md)
    ;;
  *)
    exit 0
    ;;
esac

TIMESTAMP=$(date '+%Y-%m-%dT%H:%M:%S')

# 写入结构化追踪日志
TRACK_FILE="$TRACK_DIR/file-changes.jsonl"
cat >> "$TRACK_FILE" <<TRACK
{"ts":"$TIMESTAMP","session":"$SESSION","tool":"$TOOL","path":"$FILE_PATH"}
TRACK

# 自动归档：超过 100 行时保留最新 50 行
LINES=$(wc -l < "$TRACK_FILE" 2>/dev/null || echo "0")
if [ "$LINES" -gt 100 ] 2>/dev/null; then
  ARCHIVE_DIR="$TRACK_DIR/archive"
  mkdir -p "$ARCHIVE_DIR" 2>/dev/null
  ARCHIVE_FILE="$ARCHIVE_DIR/file-changes-$(date '+%Y%m%d-%H%M%S').jsonl"
  head -$((LINES - 50)) "$TRACK_FILE" > "$ARCHIVE_FILE" 2>/dev/null
  tail -50 "$TRACK_FILE" > "${TRACK_FILE}.tmp" 2>/dev/null
  mv "${TRACK_FILE}.tmp" "$TRACK_FILE" 2>/dev/null
fi

# 统计：改动频率 Top 文件（每 20 次改动统计一次）
if [ -f "$TRACK_FILE" ]; then
  CURRENT_COUNT=$(wc -l < "$TRACK_FILE" 2>/dev/null || echo "0")
  if [ "$((CURRENT_COUNT % 20))" -eq 0 ] 2>/dev/null && [ "$CURRENT_COUNT" -gt 0 ] 2>/dev/null; then
    TOP_FILES=$(tail -50 "$TRACK_FILE" 2>/dev/null | grep -o '"path":"[^"]*"' | sort | uniq -c | sort -rn | head -5)
    STATS_FILE="$TRACK_DIR/file-stats.log"
    echo "[$TIMESTAMP] 最近 50 次改动 Top 文件:" >> "$STATS_FILE"
    echo "$TOP_FILES" >> "$STATS_FILE"
    echo "---" >> "$STATS_FILE"
  fi
fi

exit 0
