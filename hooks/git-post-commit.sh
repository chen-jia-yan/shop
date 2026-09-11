#!/bin/bash
# ============================================================
# git-post-commit.sh — PostToolUse(Bash) Git 提交后增强
# 事件: PostToolUse, matcher: Bash(git commit *)
# 可选 Hook，当前工作流不强制启用
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
COMMAND=$(json_get ".tool_input.command" <<< "$INPUT")

# 只处理 git commit 命令
if ! echo "$COMMAND" | grep -qE "git\s+commit"; then
  exit 0
fi

# 记录提交统计
TIMESTAMP=$(date '+%Y-%m-%dT%H:%M:%S')
COMMIT_LOG="$TRACK_DIR/git-commits.log"

# 获取最新 commit 信息
COMMIT_MSG=$(git log -1 --oneline 2>/dev/null || echo "unknown")
FILES_CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | wc -l || echo "0")

echo "[$TIMESTAMP] $COMMIT_MSG | ${FILES_CHANGED} files" >> "$COMMIT_LOG"

log_event "PostToolUse" "ok" "git_commit: $COMMIT_MSG"
exit 0
