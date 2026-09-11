#!/bin/bash
# ============================================================
# hook-utils.sh — Hook 公共函数库
# 所有 Hook 脚本统一 source 这个文件，避免重复代码
# ============================================================

# --- 目录初始化 ---
HOOK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACK_DIR="$HOOK_ROOT/../.track"
LOG_DIR="$TRACK_DIR"
mkdir -p "$TRACK_DIR" 2>/dev/null
mkdir -p "$LOG_DIR" 2>/dev/null

# --- JSON 解析 ---
# 优先级：jq > node > python3
_JSON_PARSER=""
_detect_json_parser() {
  if [ -n "$_JSON_PARSER" ]; then return; fi
  if command -v jq &>/dev/null; then
    _JSON_PARSER="jq"
  elif command -v node &>/dev/null; then
    _JSON_PARSER="node"
  elif command -v python3 &>/dev/null; then
    _JSON_PARSER="python3"
  else
    _JSON_PARSER="none"
  fi
}

# 从 stdin JSON 提取字段值（安全，不抛异常）
# 用法: json_get ".hook_event_name" <<< "$INPUT"
json_get() {
  local field="$1"
  _detect_json_parser
  case "$_JSON_PARSER" in
    jq)
      jq -r "${field} // \"\"" 2>/dev/null || echo ""
      ;;
    node)
      node -e "
        const fs=require('fs');
        try{
          const d=JSON.parse(fs.readFileSync(0,'utf8'));
          const keys='${field}'.replace(/^\./,'').split('.');
          let v=d;
          for(const k of keys) v=(v||{})[k];
          process.stdout.write(v===null||v===undefined?'':String(v));
        }catch(e){process.stdout.write('');}
      " 2>/dev/null || echo ""
      ;;
    python3)
      python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  keys='${field}'.replace('.','').split('.')
  v=d
  for k in keys: v=v.get(k,'') if isinstance(v,dict) else ''
  print(v if v else '')
except: print('')
" 2>/dev/null
      ;;
    *) echo "" ;;
  esac
}

# 从 stdin JSON 提取嵌套字段（支持 .tool_input.command 这样的路径）
json_get_raw() {
  local field="$1"
  _detect_json_parser
  case "$_JSON_PARSER" in
    jq)
      jq -r "${field} // empty" 2>/dev/null
      ;;
    node)
      node -e "
        const fs=require('fs');
        try{
          const d=JSON.parse(fs.readFileSync(0,'utf8'));
          const keys='${field}'.replace(/^\./,'').split('.');
          let v=d;
          for(const k of keys) v=(v||{})[k];
          if(v!==null&&v!==undefined){
            if(typeof v==='string')process.stdout.write(v);
            else process.stdout.write(JSON.stringify(v));
          }
        }catch(e){}
      " 2>/dev/null
      ;;
    python3)
      python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  keys='${field}'.replace('.','').split('.')
  v=d
  for k in keys: v=v.get(k,'') if isinstance(v,dict) else ''
  if v: print(v)
except: pass
" 2>/dev/null
      ;;
    *) ;;
  esac
}

# --- 日志系统 ---
HOOK_LOG="$TRACK_DIR/hook-executions.jsonl"

log_event() {
  local event="$1"   # hook_event_name
  local status="$2"  # ok | blocked | warned | error
  local detail="$3"  # 额外信息
  local ts
  ts=$(date '+%Y-%m-%dT%H:%M:%S')
  local entry
  entry=$(node -e "
    process.stdout.write(JSON.stringify({
      ts:'${ts}',
      event:'${event}',
      status:'${status}',
      detail:'${detail//\'/\\\'}'
    }))
  " 2>/dev/null || echo "{\"ts\":\"$ts\",\"event\":\"$event\",\"status\":\"$status\",\"detail\":\"$detail\"}")
  echo "$entry" >> "$HOOK_LOG"
  # 日志轮转：超过 500 行自动归档
  if [ -f "$HOOK_LOG" ]; then
    local lines
    lines=$(wc -l < "$HOOK_LOG" 2>/dev/null || echo "0")
    if [ "$lines" -gt 500 ]; then
      mv "$HOOK_LOG" "${HOOK_LOG}.$(date '+%Y%m%d').bak" 2>/dev/null
    fi
  fi
}

# --- 通知系统 ---
notify_windows() {
  local title="$1"
  local message="$2"
  # 清理特殊字符防止 PowerShell 炸
  local safe_msg
  safe_msg=$(echo "$message" | sed "s/'/''/g; s/\"/'/g; s/[\\\`\$]//g" | cut -c1-120)
  powershell.exe -NoProfile -WindowStyle Hidden -Command "
    Add-Type -AssemblyName System.Windows.Forms;
    \$n = New-Object System.Windows.Forms.NotifyIcon;
    \$n.Icon = [System.Drawing.SystemIcons]::Information;
    \$n.BalloonTipTitle = '${title}';
    \$n.BalloonTipText = '${safe_msg}';
    \$n.Visible = \$true;
    \$n.ShowBalloonTip(5000);
    Start-Sleep -Seconds 6;
    \$n.Dispose();
  " 2>/dev/null || true
}

# --- 安全响应 ---
# 输出阻塞 JSON 并退出
block_tool() {
  local reason="$1"
  cat <<BLOCKED
{"decision":"block","reason":"🛑 Hook 拦截：${reason}"}
BLOCKED
  exit 2
}

# 输出警告（不阻塞，注入提示）
warn_tool() {
  local message="$1"
  cat <<WARN
{"systemMessage":"⚠️ ${message}"}
WARN
  exit 0
}

# --- 文件检查 ---
# 判断是否为受保护文件
is_protected_file() {
  local filepath="$1"
  local basename
  basename=$(basename "$filepath")
  case "$basename" in
    .env|.env.*|settings.json|settings.local.json|CLAUDE.md|*.pem|*.key|id_rsa*)
      return 0 ;;
    *)
      # 检查路径中是否包含 .claude/hooks/ （保护 Hook 自身）
      case "$filepath" in
        *.claude/hooks/*) return 0 ;;
        *) return 1 ;;
      esac
      ;;
  esac
}

# --- 初始化日志（每次会话只写一次） ---
_detect_json_parser
BOOTSTRAP_LOG="$TRACK_DIR/hook-bootstrap.log"
# 轮转：超过 200 行自动归档
if [ -f "$BOOTSTRAP_LOG" ]; then
  BOOT_LINES=$(wc -l < "$BOOTSTRAP_LOG" 2>/dev/null || echo "0")
  if [ "$BOOT_LINES" -gt 200 ] 2>/dev/null; then
    mv "$BOOTSTRAP_LOG" "${BOOTSTRAP_LOG}.$(date '+%Y%m%d').bak" 2>/dev/null
  fi
fi
echo "[$(date '+%H:%M:%S')] parser=$_JSON_PARSER project=$CLAUDE_PROJECT_DIR" >> "$BOOTSTRAP_LOG" 2>/dev/null
