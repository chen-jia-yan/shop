"""解析 Python 测试日志（unittest / BeautifulReport / pytest）中的步骤日志和异常链。

一条失败日志通常是：
    <步骤日志：脚本在失败前打印的内容>
    Traceback (most recent call last): File "...", line N, in func ... <异常类型>: <信息>
    During handling of the above exception, another exception occurred:
    Traceback ... SystemExit: 0
    （可能还有截图函数 save_img 里的 OSError: screen grab failed）

规则（见 references/pywinauto-desktop.md 第 1 节）：
- 第一段是最先发生的异常，最接近原因；后面的段是处理它时又发生的异常。
- SystemExit 和截图/清理函数里的异常不作为失败原因。
- 项目代码里的最后一帧说明失败发生在哪个业务步骤、哪个底层操作。

本模块只做文本解析，不调用模型；与网页版“测试分析助手”的 analyzeLog 逻辑一致。
"""
from __future__ import annotations

import re

from common import match_any

FRAME_RE = re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+),\s*in\s+([\w<>.]+)')
CHAIN_SPLIT = re.compile(
    r"During handling of the (?:above )?exception,? another exception occurred:?"
    r"|The above exception was the direct cause of the following exception:?", re.I)
EXC_FIND = re.compile(
    r"(?:^|[\s>])((?:[A-Za-z_]\w*\.)*(?:[A-Z]\w*(?:Error|Exception|Exit|Warning|Failure|NotVisible|NotEnabled|NotFound|Interrupt)"
    r"|Exception)|(?:[A-Za-z_]\w*\.)+error)(?::[ \t]?|\s*$)")
TB_HEAD = "Traceback (most recent call last):"
POPUP_RE = re.compile(r"pop-?up error:\s*(.*)", re.I | re.S)
SYSMSG_RE = re.compile(r"(Validation Error|Error Message|Life/Asia Message)\s*:\s*(.+?)(?=\s{2,}|Traceback|$)", re.I | re.S)
WINDOWS_RE = re.compile(r"dict_keys\(\[(.*?)\]\)", re.S)
EXPECT_WIN_RES = [re.compile(r"Could not find '([^']+)'"), re.compile(r"Can't find window (.+?)(?=\s+During|\s*$)", re.S)]
SCREEN_RE = re.compile(r"([A-Za-z][\w/&.' -]{2,80}?)\s*\([^)]{2,30}\)\s*window wait success")


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def short_type(t: str | None) -> str:
    """'pywinauto.base_wrapper.ElementNotVisible' -> 'ElementNotVisible'；'pywintypes.error' 保留模块名。"""
    if not t:
        return ""
    parts = t.split(".")
    last = parts.pop()
    return f"{parts[-1]}.error" if last == "error" and parts else last


def _segment(seg: str, log_rules: dict) -> dict:
    body = seg
    i = seg.find(TB_HEAD)
    if i >= 0:
        body = seg[i + len(TB_HEAD):]
    frames, end = [], 0
    for m in FRAME_RE.finditer(body):
        frames.append({"file": re.sub(r"\s+", "", m.group(1)), "line": int(m.group(2)), "func": m.group(3)})
        end = m.end()
    tail = body[end:]
    em = EXC_FIND.search(tail)
    etype = em.group(1) if em else ""
    msg = tail[em.end():].strip() if em else ""
    fw = log_rules.get("framework_paths", [])
    handlers = set(log_rules.get("handler_funcs", []))
    return {
        "type": etype, "msg": msg, "frames": frames,
        "project": [f for f in frames if not match_any(f["file"], fw)],
        "handler": any(f["func"] in handlers for f in frames),
        "exit": etype.endswith("SystemExit"),
    }


def analyze_log(text: str | None, log_rules: dict) -> dict | None:
    """返回解析结果；文本里没有异常时返回 None。"""
    if not text or not re.search(r"Traceback|During handling|Exception:|Error:", text):
        return None
    raw_segs = CHAIN_SPLIT.split(text)
    segs = [_segment(s, log_rules) for s in raw_segs]
    main = [s for s in segs if s["type"] and not s["handler"] and not s["exit"]]
    root = main[0] if main else None

    with_test = next((s for s in segs if any(f["func"].lower().startswith("test") for f in s["project"])), None) \
        or next((s for s in segs if s["project"]), None)
    path = [f"{f['func']}（{_basename(f['file'])} 第{f['line']}行）" for f in (with_test or {}).get("project", [])]
    root_at = root["project"][-1] if root and root["project"] else None
    test_fn = next((f["func"] for f in (with_test or {}).get("project", []) if f["func"].lower().startswith("test")), "")

    first = raw_segs[0]
    i = first.find(TB_HEAD)
    if i >= 0:
        step_log = first[:i]
    else:
        em = EXC_FIND.search(first)
        step_log = first[:em.start()] if em else first
    step_log = step_log.strip()

    popup_text = None
    for s in main:
        pm = POPUP_RE.search(s["msg"])
        if pm:
            popup_text = re.sub(r"\s+", " ", pm.group(1)).strip()
            break
    sys_msgs = [f"{m.group(1)}: {m.group(2).strip()}" for m in SYSMSG_RE.finditer(step_log)]
    if popup_text:
        sys_msgs.insert(0, popup_text)

    success = []
    for p in log_rules.get("success_marks", []):
        hit = match_any(step_log, [p])
        if hit:
            m = re.search(p[3:], step_log, re.I) if p.startswith("re:") else None
            success.append(m.group(0) if m else p)

    wl = WINDOWS_RE.search(text)
    windows = re.findall(r"'([^']+)'", wl.group(1)) if wl else []
    expect_win = ""
    for rx in EXPECT_WIN_RES:
        m = rx.search(text)
        if m:
            expect_win = m.group(1).strip()
            break
    screens = [re.sub(r"^[\d/]+\s*", "", re.sub(r"^.*?finding transaction window\s*", "", m.group(1), flags=re.I)).strip()
               for m in SCREEN_RE.finditer(step_log)]

    main_text = "\n".join([step_log] + [f"{s['type']}: {s['msg']}" for s in main])
    handler_err = "；".join(f"{s['type']}: {s['msg']}" for s in segs if s["handler"])
    return {
        "segments": segs, "root": root, "root_at": root_at, "path": path, "test_fn": test_fn,
        "step_log": step_log, "popup_text": popup_text, "sys_msgs": [m for m in sys_msgs if m],
        "success_marks": success, "windows": windows, "expect_window": expect_win,
        "screen": screens[0] if screens else "", "types": [s["type"] for s in main],
        "main_text": main_text, "handler_error": handler_err,
        "screenshot_failed": any(s["handler"] and re.search("screen grab failed", s["msg"], re.I) for s in segs),
    }
