"""通用事件钩子：一个脚本处理 Copilot 的多种事件，第一个参数是事件名。

    kit_events.py prompt          userPromptSubmitted   记录一轮开始、清掉“该你了”；识别用户对删除的“同意 / 不要”
    kit_events.py transform       userPromptTransformed 在模型看到的消息末尾附一行提示（模式 / 可能适用的能力 / 需求缺什么）
    kit_events.py tool            postToolUse           记工具和能力的使用；确认“问一次”；缺包缺配置时提醒一次查全；
                                                        发现“拆成很多小步”时提醒一次做完；运行中删除被拦时登记待同意
    kit_events.py tool_fail       postToolUseFailure    同上，失败时的恢复建议
    kit_events.py stop            agentStop             一轮结束：计时、token；机器人亮“该你了”
    kit_events.py subagent_start  subagentStart         给代理带上红线和当前模式
    kit_events.py subagent_stop   subagentStop          记代理耗时
    kit_events.py notification    notification          需要你确认或回答时，机器人亮“该你了”
    kit_events.py compact         preCompact            记一次上下文压缩
    kit_events.py end             sessionEnd            会话结束

任何异常都吞掉并记日志，输出 {}，绝不影响会话。agentStop 从不阻止结束。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kitlib  # 必须在上一行把 tools 目录加进 sys.path 之后再导入

TOOLS = kitlib.KIT_ROOT / "tools"
DEV_REQUEST = re.compile(r"(实现|新增|增加|添加|修复|修改|改成|改为|重构|迁移|开发|写一个|写个|接入|支持|报错|bug|fix|implement|refactor)", re.I)
HINT_TAG = "[ai-dev-kit 提示]"

# 常见的环境问题：(类型, 正则, 说明)。只提示一次“先查全再一起装”，不替用户装。
ENV_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("module", re.compile(r"No module named ['\"]?([\w.\-]+)"), "缺 Python 包 {0}"),
    ("command", re.compile(r"(?i)'([\w.\-]+)' is not recognized as an internal or external command|([\w.\-]+): command not found|不是内部或外部命令"), "缺命令行工具 {0}"),
    ("command", re.compile(r"(?i)The term '([\w.\-]+)' is not recognized as (?:the )?name of a cmdlet"), "缺命令 {0}"),
    ("config", re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]{2,})\s*\n\s*Field required|KeyError: '([A-Z][A-Z0-9_]{2,})'|environment variable ['\"]?([A-Z][A-Z0-9_]{2,})"), "缺配置项 {0}"),
    ("version", re.compile(r"(?i)(?:requires|required) (?:python|version) ?[<>=!~]+ ?[\d.]+|ImportError: cannot import name"), "版本不匹配"),
]
SKILL_ERRORS = re.compile(r"(?i)(不是内嵌|不是内置|无法调用.{0,6}skill|skill.{0,20}(not found|unknown|not available|is not a built-?in)|unknown skill|no such skill)")


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw.strip() else {}
    return data if isinstance(data, dict) else {}


def _metrics(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        import kit_metrics

        return kit_metrics.record(event, payload)
    except Exception as exc:
        kitlib.log_event("events", {"where": f"metrics:{event}", "error": repr(exc)[:200]})
        return {}


# ---------------------------------------------------------------- userPromptTransformed：附一行提示


def build_hint(prompt: str, cwd: str, cfg: dict[str, Any]) -> str:
    text = prompt.strip()
    if not text or text.startswith("/") or HINT_TAG in text or len(text) < 4:
        return ""
    parts: list[str] = []
    if (cfg.get("capabilities", {}) or {}).get("auto_suggest", True):
        try:
            import kit_catalog

            found = kit_catalog.match(text)
        except Exception as exc:
            kitlib.log_event("events", {"where": "match", "error": repr(exc)[:200]})
            found = []
        names = []
        for _, item in found:
            kind = "代理" if item["kind"] == "agent" else "技能"
            names.append(f"{kind} {item['name']}" + ("（会改文件，先问用户）" if item.get("writes") else "（只读，可直接用）"))
        if names:
            parts.append("可能适用：" + "、".join(names))
    if DEV_REQUEST.search(text) and len(text) >= 8:
        try:
            import prompt_lint

            rep = prompt_lint.analyze(text)
        except Exception:
            rep = {}
        if rep and rep.get("score", 100) < 50:
            missing = [d["label"] for d in rep.get("dimensions", []) if not d.get("ok")][:4]
            if missing:
                parts.append(f"需求还缺：{'、'.join(missing)}。不清楚的地方先合并成一次提问，别逐个问")
    if not parts:
        return ""
    info = kitlib.current_mode(cfg, cwd)
    hint = f"{HINT_TAG} 模式：{info['label']}；" + "；".join(parts) + "。不合适就忽略这行。"
    return hint[:240]


def on_transform(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = kitlib.load_config()
    transformed = payload.get("transformedPrompt")
    if not isinstance(transformed, str) or not transformed.strip():
        return {}
    hint = build_hint(str(payload.get("prompt") or ""), str(payload.get("cwd") or os.getcwd()), cfg)
    if not hint:
        return {}
    return {"modifiedTransformedPrompt": transformed.rstrip() + "\n\n" + hint}


# ---------------------------------------------------------------- postToolUse：环境问题提醒


def env_hint(text: str, session: str) -> str:
    if not text:
        return ""
    found: list[str] = []
    for kind, pattern, label in ENV_PATTERNS:
        m = pattern.search(text)
        if m:
            name = next((g for g in m.groups() if g), "") if m.groups() else ""
            found.append(label.format(name).strip())
    skill = bool(SKILL_ERRORS.search(text))
    if not found and not skill:
        return ""
    seen_path = kitlib.DATA_DIR / "env_hints.json"
    seen = kitlib.load_json(seen_path, {}) or {}
    key = session + "|" + ("skill" if skill else ",".join(sorted(set(found))))
    if key in seen:
        return ""
    seen[key] = kitlib.now()
    if len(seen) > 200:
        seen = dict(list(seen.items())[-100:])
    kitlib.save_json(seen_path, seen)
    if skill:
        return (f"{HINT_TAG} 这像是技能没有挂到 Copilot 上（自己目录里的技能不会自动加载）。"
                f"运行 python \"{TOOLS / 'kit_skill.py'}\" check <技能目录> 校验格式，再用 add 挂到本机，"
                "然后在会话里输入 /skills reload。不要自己猜原因反复重试。")
    return (f"{HINT_TAG} 发现环境问题：{'、'.join(dict.fromkeys(found))}。不要一个一个试：先运行 "
            f"python \"{TOOLS / 'kit_env.py'}\" scan 一次查出所有缺的包、命令和配置，"
            "再把要装的合并成一条命令，问用户同意后执行；缺的是配置项时只说名字，不读取它的值。")


def _tool_text(payload: dict[str, Any]) -> str:
    result = payload.get("toolResult") or payload.get("tool_result") or {}
    if isinstance(result, dict):
        return str(result.get("textResultForLlm") or result.get("text_result_for_llm") or "")
    return str(payload.get("error") or "")


def on_tool(payload: dict[str, Any], failed: bool) -> tuple[dict[str, Any], int]:
    session = str(payload.get("sessionId") or payload.get("session_id") or "")
    args = payload.get("toolArgs", payload.get("tool_input", ""))
    if not failed:
        kind = kitlib.approval_confirm(session, kitlib.args_digest(args))
        if kind:
            kitlib.log_event("guard", {"decision": "user-approved", "kind": kind, "session": session[:12]})
            if kind.startswith("out-of-scope:"):
                _scope_add(kind.split(":", 1)[1], str(payload.get("cwd") or os.getcwd()))
        _metrics("tool", payload)
    text = str(payload.get("error") or "") if failed else _tool_text(payload)
    hints: list[str] = []
    blocked = delete_blocked_hint(payload, text, session)
    if blocked:
        hints.append(blocked)
    env = env_hint(text[-6000:], session)
    if env:
        _metrics("env_hint", payload)
        hints.append(env)
    try:
        batch = batch_hint(payload)
    except Exception as exc:  # 提醒失败不影响会话
        kitlib.log_event("events", {"where": "batch", "error": repr(exc)[:200]})
        batch = ""
    if batch:
        hints.append(batch)
    hint = "\n".join(hints)
    if failed:
        return ({}, 0) if not hint else ({"_text": hint}, 2)
    return ({"additionalContext": hint} if hint else {}), 0


def _scope_add(rel: str, cwd: str) -> None:
    """你在确认框里同意改了方案外的文件：把它补进修改范围，验证时不再报越界、之后也不再问。"""
    scope_root, scope = kitlib.find_scope(cwd)
    if not scope_root or not scope or scope.get("files") is None:
        return
    if kitlib.match_any(rel, list(scope.get("files", [])) + list(scope.get("globs", []))):
        return
    scope["files"] = list(scope.get("files", [])) + [rel]
    scope["added_during_task"] = list(scope.get("added_during_task", [])) + [rel]
    kitlib.save_json(scope_root / kitlib.SCOPE_DIRNAME / kitlib.SCOPE_FILENAME, scope)
    kitlib.log_event("guard", {"decision": "scope-added", "file": rel})


def delete_blocked_hint(payload: dict[str, Any], text: str, session: str) -> str:
    """测试或脚本运行中有删除被拦下：告诉模型怎么继续（默认：直接加 --allow-delete 重跑，守卫会当场问用户）。"""
    if "KitDeleteBlocked" not in text and "想删除数据" not in text:
        return ""
    args = payload.get("toolArgs") or payload.get("tool_input") or {}
    command = str(args.get("command") or "") if isinstance(args, dict) else str(args)
    if not command or "--allow-delete" in command:
        return ""
    import kit_rules

    details = re.findall(r"禁删保护：(.{0,160}?)，已拦下", text)[:4]
    risk = kit_rules.assess(text[-4000:])
    risk.what = details or ["测试或脚本运行中的删除调用（详见上面的报错）"]
    ask_mode = str(((kitlib.load_config().get("guard", {}) or {}).get("ask_mode", "ask"))).lower()
    if ask_mode != "deny":
        return (f"{HINT_TAG} 运行中有删除数据的操作被拦下了，数据没被删。如果这次删除是需要的：不用停下来问，"
                f"直接用 kit_run.py --allow-delete -- <原命令> 重新运行，守卫会弹确认框（带下面的风险评估）让用户当场决定；"
                f"如果是测试里不该有的清理代码，改成用假对象，然后继续。\n{risk.render()}")
    kitlib.delete_request(session, kitlib.delete_core(command), risk.render())
    return (f"{HINT_TAG} 运行中有删除数据的操作被拦下了，数据没被删。如果这次删除是需要的："
            f"把下面的风险评估告诉用户，等用户回复“同意”后，用 kit_run.py --allow-delete -- <原命令> 重新运行；"
            f"如果是测试里不该有的清理代码，改成用假对象。\n{risk.render()}")


# ---------------------------------------------------------------- subagentStart：给代理带上红线


def subagent_context(payload: dict[str, Any]) -> str:
    cfg = kitlib.load_config()
    cwd = str(payload.get("cwd") or os.getcwd())
    info = kitlib.current_mode(cfg, cwd)
    lines = [f"[ai-dev-kit] 当前模式：{info['label']}。",
             "红线：不读 .env；删除数据时守卫会当场请用户确认（同意就继续，不要先停下来问）；不用 git add .；共享模块保持接口兼容；"
             "被守卫拒绝就跳过那一步、继续其余工作；"
             "同类的改动先列全再一次做完；"
             "没运行的验证不要说通过。"]
    proj = info.get("project")
    if proj and not proj.get("_auto"):
        shared, _ = kitlib.shared_areas(proj)
        if shared:
            lines.append("共享模块（可改，改之前要有测试基线）：" + "、".join(shared))
    scope_root, scope = kitlib.find_scope(cwd)
    if scope:
        files = list(scope.get("files", [])) + list(scope.get("globs", []))
        lines.append("本次只允许修改：" + ("、".join(files[:12]) if files else "（不允许修改文件）"))
    return "\n".join(lines)


def on_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    session = str(payload.get("sessionId") or payload.get("session_id") or "")
    status = kitlib.delete_consent(session, str(payload.get("prompt") or ""))
    if status:
        kitlib.log_event("events", {"where": "delete_consent", "status": status, "session": session[:12]})
    _metrics("prompt", payload)
    batch_reset(session)
    return {}


# ---------------------------------------------------------------- 一次做完：发现“拆成很多小步”时提醒
#
# 同一轮对话里出现这些情况，就提醒模型先列全、再一次做完（每类每轮只提醒一次）：
#   - 同一个文件改了 3 次以上（一个参数、一个配置地改）
#   - 一轮里零散的小编辑超过 6 次
#   - 同一条测试 / 运行命令跑了 3 次以上（跑一次修一个）
#   - 装包、改配置这类命令分了 2 次以上
# 只提醒，不拦截；模型觉得确实需要分步（例如每步要看结果再决定）可以继续。

BATCH_PATH = kitlib.DATA_DIR / "batch_state.json"
EDIT_NAMES = {"edit", "str_replace", "str_replace_editor", "apply_patch", "create", "write", "insert", "multi_edit"}
INSTALL_CMD = re.compile(r"(?i)\b(pip|uv\s+pip|uv\s+add|poetry\s+add|conda|npm|pnpm|yarn)\s+(install|add|i)\b|\buv\s+add\b")
CONFIG_CMD = re.compile(r"(?i)(\$env:\w+\s*=|\bset(x)?\s+\w+=|\bexport\s+\w+=|git\s+config\b|setx\b)")
RUN_CMD = re.compile(r"(?i)\b(pytest|mypy|ruff\s+check|python\s+\S+\.py|uv\s+run\s+\S+|npm\s+(run\s+)?test)\b")
CONFIG_FILE = re.compile(r"(?i)(settings|config|conf|\.env\.|\.ya?ml$|\.toml$|\.ini$|\.json$)")


def batch_reset(session: str) -> None:
    data = kitlib.load_json(BATCH_PATH, {}) or {}
    data[session] = {"edits": {}, "edit_count": 0, "runs": {}, "installs": 0, "configs": 0, "hinted": []}
    for sid in list(data)[:-10]:
        data.pop(sid, None)
    kitlib.save_json(BATCH_PATH, data)


def _command_key(cmd: str) -> str:
    """把命令归一：去掉 kit_run 包装、-k / 具体测试名，同一类运行算同一条。"""
    core = kitlib.delete_core(cmd)
    core = re.sub(r"(?i)(::\S+|\s-k\s+\S+|\s--lf\b|\s-x\b|\s--tb=\S+)", "", core)
    return " ".join(core.split()[:4])


def batch_hint(payload: dict[str, Any]) -> str:
    session = str(payload.get("sessionId") or payload.get("session_id") or "")
    tool = str(payload.get("toolName") or payload.get("tool_name") or "").lower()
    args = payload.get("toolArgs") or payload.get("tool_input") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"command": args}
    if not isinstance(args, dict):
        return ""
    data = kitlib.load_json(BATCH_PATH, {}) or {}
    st = data.setdefault(session, {"edits": {}, "edit_count": 0, "runs": {}, "installs": 0, "configs": 0, "hinted": []})
    hints: list[tuple[str, str]] = []
    path = str(args.get("path") or args.get("file_path") or args.get("filePath") or "")
    command = str(args.get("command") or args.get("cmd") or "")
    if tool in EDIT_NAMES and path:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        st["edits"][name] = int(st["edits"].get(name, 0)) + 1
        st["edit_count"] = int(st.get("edit_count", 0)) + 1
        if st["edits"][name] == 3:
            what = "配置" if CONFIG_FILE.search(name) else "代码"
            hints.append((f"file:{name}", f"{name} 这一轮已经改了 3 次。先把这个文件里所有要改的{what}一次列全"
                                          "（同类的参数、配置项、调用点一起），用一次编辑改完，不要一处一处改。"))
        if st["edit_count"] == 7:
            hints.append(("many-edits", "这一轮的修改拆成了很多小步。剩下的同类改动先用一次搜索列全"
                                        "（例如 grep 所有调用点、所有用到这个配置名的地方），列成清单后批量改完，再统一验证一次。"))
    if command:
        if INSTALL_CMD.search(command):
            st["installs"] = int(st.get("installs", 0)) + 1
            if st["installs"] == 2:
                hints.append(("installs", f"已经分 2 次装包了。先运行 python \"{TOOLS / 'kit_env.py'}\" scan 一次查出所有缺的包、"
                                          "命令和配置，合并成一条命令，问用户一次。"))
        if CONFIG_CMD.search(command):
            st["configs"] = int(st.get("configs", 0)) + 1
            if st["configs"] == 2:
                hints.append(("configs", "配置一条一条地在设。先把需要的所有配置项列全（名字、用途、要不要用户提供值），"
                                         "合并成一次设置或一次问用户。"))
        if RUN_CMD.search(command):
            key = _command_key(command)
            st["runs"][key] = int(st["runs"].get(key, 0)) + 1
            if st["runs"][key] == 3:
                hints.append((f"run:{key}", f"“{key}” 这一轮已经跑了 3 次，像是在跑一次修一个。换成一次看全所有问题："
                                            "pytest 去掉 -x、用 -q --tb=line 列出全部失败；类型检查和 lint 一次跑完整个目录；"
                                            "把所有问题分好类后一起修，最后再跑一次确认。"))
    hinted = list(st.get("hinted", []))
    fresh = [text for key, text in hints if key not in hinted]
    st["hinted"] = hinted + [key for key, _ in hints if key not in hinted]
    data[session] = st
    kitlib.save_json(BATCH_PATH, data)
    if not fresh:
        return ""
    return f"{HINT_TAG} 一次做完：" + " ".join(fresh) + "（如果每一步确实要看上一步的结果再决定，可以继续分步，但要说明原因。）"


# ---------------------------------------------------------------- 入口


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    out: dict[str, Any] = {}
    code = 0
    try:
        payload = _read_payload()
        if event == "prompt":
            out = on_prompt(payload)
        elif event == "transform":
            out = on_transform(payload)
        elif event in ("tool", "tool_fail"):
            out, code = on_tool(payload, failed=event == "tool_fail")
        elif event == "stop":
            _metrics("stop", payload)
        elif event == "subagent_start":
            _metrics("subagent_start", payload)
            out = {"additionalContext": subagent_context(payload)}
        elif event == "subagent_stop":
            _metrics("subagent_stop", payload)
        elif event == "notification":
            _metrics("notification", payload)
        elif event == "compact":
            _metrics("compact", payload)
        elif event == "end":
            _metrics("session_end", payload)
    except Exception as exc:
        kitlib.log_event("events", {"event": event, "error": repr(exc)[:300]})
        out, code = {}, 0
    if code == 2:  # postToolUseFailure：退出码 2 时 stdout 会附在失败信息后面给模型看
        sys.stdout.write(str(out.get("_text", "")))
        sys.stdout.flush()
        return 2
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
