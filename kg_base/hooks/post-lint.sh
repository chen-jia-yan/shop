#!/bin/bash
# ============================================================
# post-lint.sh — PostToolUse(Write|Edit) 自动质量提示
# 事件: PostToolUse, matcher: Write|Edit
# stdin JSON: {hook_event_name, tool_name, tool_input: {file_path}, tool_response, ...}
# 退出 0=继续, 2=阻塞反馈
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
FILE_PATH=$(json_get ".tool_input.file_path" <<< "$INPUT")
TOOL=$(json_get ".tool_name" <<< "$INPUT")

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# ---- 只检查代码文件 ----
case "$FILE_PATH" in
  *.ts|*.tsx|*.vue|*.js|*.jsx|*.scss|*.css)
    ;;
  *)
    exit 0
    ;;
esac

CHECKS=""

# 检查1：是否有 console.log 残留（在新增代码中）
if [ -f "$FILE_PATH" ]; then
  CONSOLE_COUNT=$(grep -c "console\.\(log\|debug\|warn\)" "$FILE_PATH" 2>/dev/null || echo "0")
  if [ "$CONSOLE_COUNT" -gt 0 ] 2>/dev/null; then
    CHECKS="$CHECKS\n🔍 $FILE_PATH 含 $CONSOLE_COUNT 处 console.log/debug/warn"
  fi
fi

# 检查2：是否有 debugger 残留
if [ -f "$FILE_PATH" ]; then
  if grep -q "debugger" "$FILE_PATH" 2>/dev/null; then
    CHECKS="$CHECKS\n🐛 $FILE_PATH 含 debugger 语句"
  fi
fi

# 检查3：是否有 `any` 类型（TS 文件）
case "$FILE_PATH" in
  *.ts|*.tsx|*.vue)
    if [ -f "$FILE_PATH" ]; then
      ANY_COUNT=$(grep -c ": any" "$FILE_PATH" 2>/dev/null || echo "0")
      if [ "$ANY_COUNT" -gt 2 ] 2>/dev/null; then
        CHECKS="$CHECKS\n⚠️ $FILE_PATH 含 $ANY_COUNT 处 ': any' 类型"
      fi
    fi
    ;;
esac

# ---- 汇总输出 ----
if [ -n "$CHECKS" ]; then
  log_event "PostToolUse" "warned" "lint_hints: $FILE_PATH"
  cat <<HINTS
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"📋 代码质量提示（来自 post-lint Hook）：$CHECKS\n\n💡 建议运行 pnpm lint 验证。"}}
HINTS
  exit 0
fi

# 正常：只记录不改
log_event "PostToolUse" "ok" "clean: $FILE_PATH"
exit 0
