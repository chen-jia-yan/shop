#!/bin/bash
# ============================================================
# auto-memory.sh — Stop 事件自动记忆提取
# 事件: Stop
# stdin JSON: {hook_event_name, transcript_path, session_id, last_assistant_message, cwd, ...}
# 从本轮对话中提取关键文本，检测模式后写入 memory/
# ============================================================
source "$(dirname "$0")/hook-utils.sh"

INPUT=$(cat 2>/dev/null || echo '{}')
TRANSCRIPT=$(json_get ".transcript_path" <<< "$INPUT")
SESSION=$(json_get ".session_id" <<< "$INPUT")

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  log_event "Stop" "memory_skip" "transcript 不可用: $TRANSCRIPT"
  exit 0
fi

# ---- 记忆目录（CC 原生路径，与 session-start.sh 一致） ----
# CC 源码 memdir/paths.ts: $HOME/.claude/projects/<sanitized-git-root>/memory/
# 使用 git 仓库根目录做 sanitize，确保和 CC 原生记忆系统读写同一目录
MEMORY_DIR="$HOME/.claude/projects/E--wukuang-fe-minmetals-gu-fin-asset/memory"
mkdir -p "$MEMORY_DIR" 2>/dev/null

# ---- 从 transcript JSONL 提取纯文本 ----
# 优先 jq，fallback 到 node（jq 可能不在 PATH）
if command -v jq &>/dev/null; then
  EXTRACTED_TEXT=$(tail -80 "$TRANSCRIPT" 2>/dev/null | jq -r '
    select(.message.role == "user" or .message.role == "assistant") |
    .message.content[]? | select(.type == "text") | .text
  ' 2>/dev/null | tail -60)
else
  EXTRACTED_TEXT=$(tail -80 "$TRANSCRIPT" 2>/dev/null | node -e "
    const fs=require('fs'),rl=require('readline');
    const lines=[];
    const iface=rl.createInterface({input:process.stdin});
    iface.on('line',l=>{
      try{
        const d=JSON.parse(l);
        const role=d.message?.role;
        if(role!=='user'&&role!=='assistant')return;
        const texts=(d.message?.content||[]).filter(c=>c.type==='text').map(c=>c.text);
        if(texts.length)lines.push(texts.join(' '));
      }catch(e){}
    });
    iface.on('close',()=>process.stdout.write(lines.slice(-60).join('\n')));
  " 2>/dev/null)
fi

if [ -z "$EXTRACTED_TEXT" ] || [ ${#EXTRACTED_TEXT} -lt 20 ]; then
  log_event "Stop" "memory_skip" "提取文本不足: ${#EXTRACTED_TEXT} chars"
  exit 0
fi

TODAY=$(date '+%Y-%m-%d')
MEMORY_COUNT=0

# ---- 否定词过滤 + 置信度评分 ----
# 用 node 做语义评分，过滤掉否定句和低置信度匹配
# 原理：包含"不/别/没"等否定词 → 低分；包含"以后/偏好/默认/优先"等肯定词 → 高分
SCORED=$(echo "$EXTRACTED_TEXT" | node -e "
  const fs=require('fs'),rl=require('readline');
  const lines=[];
  const now=new Date();
  const iface=rl.createInterface({input:process.stdin});
  iface.on('line',line=>{
    if(!line.trim())return;
    // 否定词：降低置信度
    const negWords=['不','别','没','无','否','不要','别用','不建议','不能','别这样','算了','放弃'];
    const posWords=['以后都','偏好','习惯','我喜欢','默认','优先','下次','记住','常用','坚持','就用'];
    const decideWords=['决定','定了','方案','架构','选型','改用','不再用','改用','统一用','就按'];
    const pitfallWords=['坑','踩','不要用','避免','注意','千万别','慎重','小心','陷阱'];

    let score=0;
    let type='';

    // 否定词检测：包含否定词 → 扣分
    const hasNeg=negWords.some(w=>line.includes(w));
    if(hasNeg){score-=0.5;}

    // 偏好检测
    const posHits=posWords.filter(w=>line.includes(w));
    if(posHits.length>0){score=posHits.length * 0.6 + (hasNeg?-0.3:0); type='pref';}

    // 决策检测
    const decHits=decideWords.filter(w=>line.includes(w));
    if(decHits.length>0){score=decHits.length * 0.7 + (hasNeg?0:0.2); type='decision';}

    // 踩坑检测
    const pitHits=pitfallWords.filter(w=>line.includes(w));
    if(pitHits.length>0){score=pitHits.length * 0.5 + (hasNeg?0:0.3); type='pitfall';}

    if(score>=0.6 && type){
      lines.push({line,score,type});
    }
  });
  iface.on('close',()=>{
    // 按类型分组，每组取 Top 3 高分行
    const groups={};
    for(const l of lines){
      if(!groups[l.type])groups[l.type]=[];
      groups[l.type].push(l);
    }
    for(const t of Object.keys(groups)){
      groups[t].sort((a,b)=>b.score-a.score);
      groups[t]=groups[t].slice(0,3);
    }
    process.stdout.write(JSON.stringify(groups));
  });
" 2>/dev/null)

# ---- 解析评分结果，写入 memory ----
if [ -n "$SCORED" ] && [ "$SCORED" != "{}" ]; then
  # 偏好
  PREF_LINES=$(echo "$SCORED" | node -e "
    const fs=require('fs');
    try{
      const d=JSON.parse(fs.readFileSync(0,'utf8'));
      if(d.pref)process.stdout.write(d.pref.map(l=>l.line).join('\n'));
    }catch(e){}
  " 2>/dev/null)
  if [ -n "$PREF_LINES" ]; then
    PREF_FILE="$MEMORY_DIR/user-pref-${TODAY}.md"
    cat > "$PREF_FILE" <<PREFMEM
---
name: user-pref-${TODAY}
description: 用户偏好自动提取
metadata:
  type: user
---

## 来源
会话 $SESSION，$TODAY

## 检测到的偏好
$PREF_LINES

> ⚠️ 此记忆由 auto-memory.sh 自动提取。置信度 ≥ 0.6。请手动确认后保留或删除。
PREFMEM
    MEMORY_COUNT=$((MEMORY_COUNT + 1))
  fi

  # 决策
  DECISION_LINES=$(echo "$SCORED" | node -e "
    const fs=require('fs');
    try{
      const d=JSON.parse(fs.readFileSync(0,'utf8'));
      if(d.decision)process.stdout.write(d.decision.map(l=>l.line).join('\n'));
    }catch(e){}
  " 2>/dev/null)
  if [ -n "$DECISION_LINES" ]; then
    DECISION_FILE="$MEMORY_DIR/decision-${TODAY}.md"
    cat > "$DECISION_FILE" <<DECMEM
---
name: decision-${TODAY}
description: 架构决策自动提取
metadata:
  type: project
---

## 来源
会话 $SESSION，$TODAY

## 检测到的决策
$DECISION_LINES

> ⚠️ 此记忆由 auto-memory.sh 自动提取。置信度 ≥ 0.6。请手动确认后保留或删除。
DECMEM
    MEMORY_COUNT=$((MEMORY_COUNT + 1))
  fi

  # 踩坑
  PITFALL_LINES=$(echo "$SCORED" | node -e "
    const fs=require('fs');
    try{
      const d=JSON.parse(fs.readFileSync(0,'utf8'));
      if(d.pitfall)process.stdout.write(d.pitfall.map(l=>l.line).join('\n'));
    }catch(e){}
  " 2>/dev/null)
  if [ -n "$PITFALL_LINES" ]; then
    PITFALL_FILE="$MEMORY_DIR/pitfall-${TODAY}.md"
    cat > "$PITFALL_FILE" <<PITMEM
---
name: pitfall-${TODAY}
description: 踩坑记录自动提取
metadata:
  type: reference
---

## 来源
会话 $SESSION，$TODAY

## 检测到的踩坑记录
$PITFALL_LINES

> ⚠️ 此记忆由 auto-memory.sh 自动提取。置信度 ≥ 0.6。请手动确认后保留或删除。
PITMEM
    MEMORY_COUNT=$((MEMORY_COUNT + 1))
  fi
fi

# ---- 清理：超过 30 天的未确认记忆自动归档到 archive/ ----
mkdir -p "$MEMORY_DIR/archive" 2>/dev/null
find "$MEMORY_DIR" -maxdepth 1 -name "*.md" -mtime +30 -exec mv {} "$MEMORY_DIR/archive/" \; 2>/dev/null

if [ "$MEMORY_COUNT" -gt 0 ]; then
  log_event "Stop" "memory_extracted" "提取了 $MEMORY_COUNT 条记忆"
fi

exit 0
