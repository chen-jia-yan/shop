"""计量：每轮对话花了多久、等你多久、用了多少 token、调用了哪些技能 / 代理 / 工具。

数据只存在本机 ~/.ai-dev-kit/metrics/，没有任何示例数据：没用过就是空的，桌面机器人显示“还没有数据”。

数据从哪来（都由钩子写入，见 hooks/kit_events.py）：
    sessionStart          会话数
    userPromptSubmitted   一轮开始；上一轮结束到现在 = 等你回复的时间
    postToolUse           工具调用次数；skill / task 调用记为“用到的能力”
    subagentStart/Stop    代理调用次数和耗时
    agentStop             一轮结束：AI 干活的时间；从 transcriptPath 读真实 token，读不到就按字数估算并标“估算”
    notification          需要你确认 / 回答时，机器人亮“该你了”

token 估算方法：中文约 1.5 字 1 个 token，英文和代码约 4 个字符 1 个 token。只用来看趋势，不是账单。

用法：
    python kit_metrics.py today         # 今天的汇总
    python kit_metrics.py week          # 最近 7 天
    python kit_metrics.py probe FILE    # 检查一个 transcript 文件里有没有真实 token 字段
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import kitlib

METRICS_DIR = kitlib.DATA_DIR / "metrics"
STATE_PATH = METRICS_DIR / "state.json"
ALERT_PATH = kitlib.DATA_DIR / "alert.json"
WAIT_CAP = 30 * 60      # 等你超过 30 分钟就不再累计（多半是离开了）
TURN_CAP = 3 * 3600     # 单轮超过 3 小时按 3 小时算（多半是漏了结束事件）
RECENT_KEEP = 40
TOKEN_KEY = re.compile(r"(?i)^(input|prompt|output|completion|cache_read_input|cached_input)_?tokens$")
OUT_KEY = re.compile(r"(?i)^(output|completion)_?tokens$")
CJK = re.compile("[\\u4e00-\\u9fff]")
SKILL_TOOLS = {"skill", "use_skill", "load_skill"}
AGENT_TOOLS = {"task", "agent", "run_agent", "delegate"}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(CJK.findall(text))
    return int(cjk / 1.5 + (len(text) - cjk) / 4) + 1


def _day(ts: float | None = None) -> str:
    return time.strftime("%Y%m%d", time.localtime(ts or time.time()))


def _day_path(day: str) -> Path:
    return METRICS_DIR / f"day-{day}.json"


def empty_day(day: str) -> dict[str, Any]:
    return {"date": day, "sessions": 0, "turns": 0, "ai_sec": 0.0, "wait_sec": 0.0,
            "tokens": {"in": 0, "out": 0, "real_turns": 0, "est_turns": 0},
            "tools": {}, "caps": {}, "agents_sec": {}, "projects": {}, "guard": {"deny": 0, "ask": 0},
            "env_hints": 0, "nodelete_blocks": 0, "compactions": 0, "recent": []}


def load_day(day: str | None = None) -> dict[str, Any]:
    day = day or _day()
    data = kitlib.load_json(_day_path(day), None)
    base = empty_day(day)
    if isinstance(data, dict):
        base.update(data)
    return base


def _save_day(data: dict[str, Any]) -> None:
    kitlib.save_json(_day_path(str(data["date"])), data)


def _bump(table: dict[str, Any], key: str, value: float = 1) -> None:
    if key:
        table[key] = round(float(table.get(key, 0)) + value, 2)


def session_id(payload: dict[str, Any]) -> str:
    return str(payload.get("sessionId") or payload.get("session_id") or "default")


def _ts(payload: dict[str, Any]) -> float:
    raw = payload.get("timestamp")
    if isinstance(raw, (int, float)) and raw > 0:
        return raw / 1000.0 if raw > 1e11 else float(raw)
    return time.time()


def _project_name(cwd: str) -> str:
    if not cwd:
        return ""
    cfg = kitlib.load_config()
    kind, proj = kitlib.location_kind(cfg, cwd)
    if proj:
        return str(proj.get("name", ""))
    return Path(cwd).name or cwd


# ---------------------------------------------------------------- transcript 里的真实 token


def _walk_tokens(obj: Any, acc: dict[str, int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and TOKEN_KEY.match(str(k)):
                acc["out" if OUT_KEY.match(str(k)) else "in"] += int(v)
            elif isinstance(v, (dict, list)):
                _walk_tokens(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_tokens(v, acc)


def read_transcript(path: str, offset: int) -> tuple[dict[str, int], int, int]:
    """从上次读到的位置往后读 transcript，返回 (真实 token, 新位置, 新增字符数)。"""
    acc = {"in": 0, "out": 0}
    p = Path(path) if path else None
    if not p or not p.is_file():
        return acc, offset, 0
    size = p.stat().st_size
    if size < offset:  # 文件被重写过
        offset = 0
    with open(p, "rb") as f:
        f.seek(offset)
        raw = f.read(min(size - offset, 20_000_000))
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                _walk_tokens(json.loads(line), acc)
            except ValueError:
                continue
    return acc, offset + len(raw), len(text)


# ---------------------------------------------------------------- 写入


def _alert(kind: str, msg: str, session: str) -> None:
    kitlib.save_json(ALERT_PATH, {"kind": kind, "msg": kitlib.redact(msg, 160), "session": session, "ts": time.time()})


def clear_alert() -> None:
    if ALERT_PATH.exists():
        kitlib.save_json(ALERT_PATH, {})


def read_alert(max_age: float = 4 * 3600) -> dict[str, Any]:
    data = kitlib.load_json(ALERT_PATH, {}) or {}
    if not data or time.time() - float(data.get("ts", 0)) > max_age:
        return {}
    return data


def record(event: str, payload: dict[str, Any], cwd: str = "") -> dict[str, Any]:
    """记录一个钩子事件。返回给调用方的额外信息（例如这一轮的耗时），失败时抛异常由调用方吞掉。"""
    cfg = kitlib.load_config()
    if not (cfg.get("metrics", {}) or {}).get("enabled", True):
        return {}
    now = _ts(payload)
    sid = session_id(payload)
    cwd = cwd or str(payload.get("cwd") or "")
    state = kitlib.load_json(STATE_PATH, {}) or {}
    sess = state.setdefault(sid, {"cwd": cwd, "project": _project_name(cwd), "started": now, "offset": 0,
                                  "turn_start": 0, "turn_chars": 0, "waiting_since": now, "agents": {}})
    if cwd and cwd != sess.get("cwd"):
        sess["cwd"], sess["project"] = cwd, _project_name(cwd)
    day = load_day(_day(now))
    info: dict[str, Any] = {}

    if event == "session_start":
        day["sessions"] += 1
        sess["waiting_since"] = now
    elif event == "prompt":
        waited = now - float(sess.get("waiting_since") or now)
        if 0 < waited:
            day["wait_sec"] = round(day["wait_sec"] + min(waited, WAIT_CAP), 1)
        prompt = str(payload.get("prompt") or "")
        sess.update(turn_start=now, turn_chars=len(prompt), waiting_since=0, prompt_head=kitlib.redact(prompt, 40))
        day["turns"] += 1
        for name in re.findall(r"(?<![\w/])/([a-z][\w\-]{2,40})", prompt):
            if name.startswith(("kit-", "style-")) or name in _known_caps():
                _bump(day["caps"], name)
        clear_alert()
    elif event == "tool":
        name = str(payload.get("toolName") or payload.get("tool_name") or "?")
        _bump(day["tools"], name)
        args = payload.get("toolArgs") or payload.get("tool_input") or {}
        result = payload.get("toolResult") or payload.get("tool_result") or {}
        text = str(result.get("textResultForLlm") or result.get("text_result_for_llm") or "") if isinstance(result, dict) else ""
        sess["turn_chars"] = int(sess.get("turn_chars", 0)) + len(text) + len(json.dumps(args, ensure_ascii=False)[:20000])
        cap = _capability_from_tool(name, args)
        if cap:
            _bump(day["caps"], cap)
            info["capability"] = cap
        if "KitDeleteBlocked" in text:
            day["nodelete_blocks"] += 1
    elif event == "subagent_start":
        name = str(payload.get("agentName") or "")
        if name:
            sess["agents"][name] = now
            _bump(day["caps"], name)
    elif event == "subagent_stop":
        name = str(payload.get("agentName") or payload.get("agentType") or "")
        started = float(sess["agents"].pop(name, 0) or 0)
        if name and started:
            _bump(day["agents_sec"], name, min(now - started, TURN_CAP))
    elif event == "stop":
        start = float(sess.get("turn_start") or 0)
        dur = min(now - start, TURN_CAP) if start else 0.0
        real, new_off, grown = read_transcript(str(payload.get("transcriptPath") or payload.get("transcript_path") or ""),
                                               int(sess.get("offset", 0)))
        sess["offset"] = new_off
        if real["in"] or real["out"]:
            tin, tout, est = real["in"], real["out"], False
            day["tokens"]["real_turns"] += 1
        else:
            chars = max(int(sess.get("turn_chars", 0)), grown // 3)
            tin, tout, est = estimate_tokens("x" * chars), 0, True
            day["tokens"]["est_turns"] += 1
        day["tokens"]["in"] += tin
        day["tokens"]["out"] += tout
        if dur:
            day["ai_sec"] = round(day["ai_sec"] + dur, 1)
            _bump(day["projects"], str(sess.get("project") or "其他"), dur)
        day["recent"] = (day.get("recent", []) + [{
            "ts": now, "sec": round(dur, 1), "tokens": tin + tout, "est": est,
            "project": sess.get("project", ""), "head": sess.get("prompt_head", "")}])[-RECENT_KEEP:]
        sess.update(turn_start=0, turn_chars=0, waiting_since=now)
        info = {"sec": dur, "tokens": tin + tout, "est": est}
        _alert("turn_done", "这一轮做完了，该你看结果了", sid)
    elif event == "notification":
        ntype = str(payload.get("notification_type") or "")
        if ntype in ("permission_prompt", "elicitation_dialog"):
            label = "需要你确认一个操作" if ntype == "permission_prompt" else "有问题需要你回答"
            _alert(ntype, str(payload.get("message") or label), sid)
            sess["waiting_since"] = now
    elif event == "guard":
        decision = str(payload.get("decision") or "")
        if decision in day["guard"]:
            day["guard"][decision] += 1
    elif event == "env_hint":
        day["env_hints"] += 1
    elif event == "compact":
        day["compactions"] += 1
    elif event == "session_end":
        state.pop(sid, None)

    if event != "session_end":
        sess["seen"] = now
    for old in [k for k, v in state.items() if now - float(v.get("seen", now)) > 2 * 86400]:
        state.pop(old, None)
    kitlib.save_json(STATE_PATH, state)
    _save_day(day)
    return info


_CAPS_CACHE: set[str] = set()


def _known_caps() -> set[str]:
    if not _CAPS_CACHE:
        data = kitlib.load_json(kitlib.DATA_DIR / "catalog.json", {}) or {}
        _CAPS_CACHE.update(str(i.get("name", "")) for i in data.get("items", []))
    return _CAPS_CACHE


def _capability_from_tool(name: str, args: Any) -> str:
    low = name.lower()
    if not isinstance(args, dict):
        return ""
    if low in SKILL_TOOLS:
        return str(args.get("skill") or args.get("name") or args.get("skill_name") or "")
    if low in AGENT_TOOLS:
        return str(args.get("agent_type") or args.get("agentType") or args.get("agent") or args.get("name") or "")
    return ""


# ---------------------------------------------------------------- 汇总（桌面机器人读这里）


def merge_days(days: list[dict[str, Any]]) -> dict[str, Any]:
    total = empty_day(days[0]["date"] if days else _day())
    for d in days:
        for key in ("sessions", "turns", "env_hints", "nodelete_blocks", "compactions"):
            total[key] += d.get(key, 0)
        for key in ("ai_sec", "wait_sec"):
            total[key] = round(total[key] + float(d.get(key, 0)), 1)
        for key in ("in", "out", "real_turns", "est_turns"):
            total["tokens"][key] += (d.get("tokens", {}) or {}).get(key, 0)
        for table in ("tools", "caps", "agents_sec", "projects"):
            for k, v in (d.get(table, {}) or {}).items():
                _bump(total[table], k, v)
        for k in ("deny", "ask"):
            total["guard"][k] += (d.get("guard", {}) or {}).get(k, 0)
        total["recent"] = (total["recent"] + list(d.get("recent", [])))[-RECENT_KEEP:]
    return total


def summary(span: str = "today") -> dict[str, Any]:
    if span == "week":
        days = [load_day(_day(time.time() - i * 86400)) for i in range(6, -1, -1)]
        data = merge_days(days)
    else:
        data = load_day()
    tok = data["tokens"]
    data["token_total"] = tok["in"] + tok["out"]
    data["token_estimated"] = tok["est_turns"] > 0 and tok["real_turns"] == 0
    data["token_mixed"] = tok["est_turns"] > 0 and tok["real_turns"] > 0
    data["empty"] = data["turns"] == 0 and not data["tools"]
    return data


def channels(data: dict[str, Any], top: int = 6) -> list[dict[str, Any]]:
    """面板上的 5 个榜单（点按钮切换）。没数据的榜单 items 为空，由界面显示空状态。"""
    def ranked(table: dict[str, Any]) -> list[tuple[str, float]]:
        return sorted(((k, float(v)) for k, v in table.items() if v), key=lambda x: -x[1])[:top]

    time_items = ranked(data["projects"])
    if data["wait_sec"]:
        time_items = sorted(time_items + [("等你回复", float(data["wait_sec"]))], key=lambda x: -x[1])[:top]
    token_by_project: dict[str, float] = {}
    for r in data.get("recent", []):
        _bump(token_by_project, str(r.get("project") or "其他"), float(r.get("tokens", 0)))
    est = "（估算）" if data.get("token_estimated") else "（部分估算）" if data.get("token_mixed") else ""
    return [
        {"key": "time", "title": "时间都去哪了", "unit": "sec", "items": time_items},
        {"key": "caps", "title": "用到的技能和代理", "unit": "次", "items": ranked(data["caps"])},
        {"key": "tools", "title": "工具调用", "unit": "次", "items": ranked(data["tools"])},
        {"key": "tokens", "title": "token 去向" + est, "unit": "tok", "items": ranked(token_by_project)},
        {"key": "turns", "title": "最近几轮（每轮耗时）", "unit": "sec", "items": last_turns(data, top)},
    ]


def last_turns(data: dict[str, Any], top: int = 6) -> list[tuple[str, float]]:
    """最近几轮对话：新的在上面，名字是“时:分 你说的开头”。"""
    out: list[tuple[str, float]] = []
    for r in reversed(list(data.get("recent", []))[-top:]):
        when = time.strftime("%H:%M", time.localtime(float(r.get("ts") or 0)))
        out.append((f"{when} {r.get('head') or r.get('project') or ''}".strip(), float(r.get("sec") or 0)))
    return out


def last_turn(data: dict[str, Any]) -> dict[str, Any]:
    """最近一轮的记录（没有时返回空字典）。"""
    recent = list(data.get("recent", []))
    return dict(recent[-1]) if recent else {}


def fmt_sec(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}秒"
    if sec < 3600:
        return f"{sec // 60}分{sec % 60:02d}秒"
    return f"{sec // 3600}小时{(sec % 3600) // 60:02d}分"


def fmt_tok(n: float) -> str:
    n = int(n)
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="计量汇总")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("today")
    sub.add_parser("week")
    p = sub.add_parser("probe")
    p.add_argument("file")
    args = parser.parse_args(argv)
    if args.cmd == "probe":
        real, _, chars = read_transcript(args.file, 0)
        if real["in"] or real["out"]:
            print(f"找到真实 token 字段：输入 {real['in']}，输出 {real['out']}。面板会显示真实值。")
        else:
            print(f"没找到 token 字段（读了 {chars} 个字符）。面板会按字数估算，并标“估算”。")
        return 0
    data = summary(args.cmd)
    if data["empty"]:
        print("还没有数据。装好钩子、正常使用一轮对话后再看。")
        return 0
    tag = "（估算）" if data["token_estimated"] else "（部分估算）" if data["token_mixed"] else ""
    print(f"会话 {data['sessions']}，对话 {data['turns']} 轮；AI 干活 {fmt_sec(data['ai_sec'])}，等你 {fmt_sec(data['wait_sec'])}；"
          f"token {fmt_tok(data['token_total'])}{tag}")
    print(f"守卫：拦下 {data['guard']['deny']} 次，请你确认 {data['guard']['ask']} 次；禁删保护拦下 {data['nodelete_blocks']} 次")
    for ch in channels(data):
        print(f"\n[{ch['title']}]")
        if not ch["items"]:
            print("  （还没有数据）")
        for i, (name, value) in enumerate(ch["items"], 1):
            shown = fmt_sec(value) if ch["unit"] == "sec" else fmt_tok(value) if ch["unit"] == "tok" else f"{int(value)} 次"
            print(f"  {i}. {name}  {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
