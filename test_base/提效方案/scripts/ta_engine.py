"""分析核心（Python 版）：与“测试分析助手”页面里的 engine.js 逐条对应，规则编号、判断顺序、结论文字都相同。

两边必须保持一致：
- 规则内容只有一份：config/rules.json（页面“配置 → 判断规则 → 导出规则”得到的就是这个文件）。
- 修改判断逻辑时，engine.js 和本文件要一起改，并运行 evals/check_consistency.py 确认两边结果相同。

输入的用例字段与页面相同：
    uid, run, seq, id, name, result, error, stack, exceptionRaw, pageText, screenshot, start, module, device,
    以及人工记录：obs {kind, text}, ocrText, dataCheck, dataNote, override {cat, reason}, rerun (pass|fail), r2 {same}, parent
classify_all() 会给每个失败用例写入 auto（判断结果）、final（最终分类）、plan（重跑建议）。
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent.parent / "config" / "rules.json"

CATS = {
    "ENVIRONMENT": {"name": "环境问题", "owner": "环境/运维"},
    "POPUP_INTERFERENCE": {"name": "弹窗干扰", "owner": "测试"},
    "SCRIPT_ISSUE": {"name": "脚本问题", "owner": "测试"},
    "TEST_DATA": {"name": "测试数据问题", "owner": "测试"},
    "PRODUCT_DEFECT": {"name": "疑似产品缺陷", "owner": "开发"},
    "NEEDS_HUMAN": {"name": "需人工判断", "owner": "待定"},
}
REASONS = {
    "pending_data_check": "有业务报错，等待数据核查",
    "unknown_popup": "出现不在清单中的弹窗",
    "insufficient_evidence": "没有报错信息或报错过于笼统",
    "conflicting_evidence": "证据互相矛盾",
    "no_rule_matched": "没有规则命中",
    "assertion_no_values": "断言失败但没有期望值/实际值",
    "masked_failure": "代码把“没找到”变成了空值，真实原因被掩盖",
    "system_config": "系统提示缺少配置",
    "control_state": "控件不可用，原因待确认",
    "generic_error": "报错过于笼统，真实原因在别处",
    "env_boundary": "处在环境中断的边界",
}
OBS_KINDS = {
    "normal": "页面正常，要操作的控件在屏幕上",
    "popup": "有弹窗或对话框挡在前面",
    "blank": "页面空白、报错页或一直在加载",
    "other": "停在别的窗口或页面（上一步没生效）",
    "disabled": "要操作的控件是灰色不可用的",
    "desktop": "锁屏、黑屏或远程桌面断开",
    "unclear": "截图看不出原因",
}
CHECK_KINDS = {
    "biz": {"name": "业务报错 → 核查测试数据",
            "options": {"ok": ["数据存在且状态正确", "PRODUCT_DEFECT"], "missing": ["数据不存在", "TEST_DATA"],
                        "used": ["数据已被使用", "TEST_DATA"], "invalid": ["数据状态不符合用例前提", "TEST_DATA"]}},
    "lock": {"name": "数据被占用 → 查占用来源",
             "options": {"lock_prev": ["被本批次前面的用例占用（失败后没有释放）", "SCRIPT_ISSUE"],
                         "lock_other": ["被其他人或其他批次占用", "TEST_DATA"], "lock_unknown": ["查不到占用来源", "TEST_DATA"]}},
    "cfg": {"name": "缺少配置 → 核查系统配置",
            "options": {"cfg_missing": ["应该存在，但测试环境缺失", "ENVIRONMENT"], "cfg_ok": ["配置正确，系统仍然报错", "PRODUCT_DEFECT"],
                        "cfg_unsupported": ["本来就不支持（用例前提不成立）", "SCRIPT_ISSUE"]}},
    "dtp": {"name": "日期设置失败 → 核查日期值",
            "options": {"dtp_out": ["日期超出允许范围", "TEST_DATA"], "dtp_in": ["日期在范围内，仍然设置失败", "SCRIPT_ISSUE"]}},
}
DATA_CHECK = {v: o[0] for k in CHECK_KINDS.values() for v, o in k["options"].items()}
PLAN = {"go": "建议立即重跑", "fix": "处理后再重跑", "no": "不需要重跑", "done": "已重跑"}


def load_rules(path: str | Path | None = None) -> dict:
    """读取规则文件。页面导出的文件是 {"tool": "ta-rules", "rules": {...}}，也接受直接的 {...}。"""
    p = Path(path) if path else RULES_FILE
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    return data.get("rules", data) if isinstance(data, dict) else {}


# ======================= 文本工具 =======================
_rx_cache: dict = {}


def to_matcher(p: str):
    if p in _rx_cache:
        return _rx_cache[p]
    if p.startswith("re:"):
        try:
            m = re.compile(p[3:], re.I | re.A)  # 与页面（JavaScript）一致：\w \d \b 只认英文字母和数字
        except re.error:
            m = None
    else:
        m = p.lower()
    _rx_cache[p] = m
    return m


def find_any(text, lst):
    """在 text 里找第一个命中的规则项，返回 {"pattern", "hit"}。"""
    if not text:
        return None
    low = text.lower()
    for p in lst or []:
        m = to_matcher(p)
        if m is None:
            continue
        if isinstance(m, str):
            i = low.find(m)
            if i >= 0:
                return {"pattern": p, "hit": text[i:i + len(m)]}
        else:
            r = m.search(text)
            if r:
                return {"pattern": p, "hit": r.group(0)}
    return None


def has_exc(exc, lst) -> bool:
    if not exc:
        return False
    e = exc.lower()
    return any(e == x.lower() or e.endswith("." + x.lower()) for x in (lst or []))


def short_type(t: str) -> str:
    if not t:
        return ""
    p = t.split(".")
    last = p.pop()
    return p.pop() + ".error" if last == "error" and p else last


def extract_exception(text) -> str:
    if not text:
        return ""
    m = re.search(r"\b((?:[a-z_]\w*\.)*[A-Z][A-Za-z0-9]*(?:Exception|Error|Failure|Failed))\b", text, re.A)
    return m.group(1).split(".")[-1] if m else ""


def extract_alert_text(text) -> str:
    if not text:
        return ""
    m = (re.search(r"Alert\s*Text\s*[:：]\s*([^\n}]+)", text, re.I) or re.search(r"\{Alert text\s*:\s*([^}]*)\}", text, re.I)
         or re.search(r"unexpected alert open:\s*\{?([^\n}]+)", text, re.I))
    return re.sub(r"^Alert text\s*:\s*", "", m.group(1).strip(), flags=re.I) if m else ""


def extract_interceptor(text) -> str:
    if not text:
        return ""
    m = re.search(r"Other element would receive the click:\s*(<[^>]{0,400}>)", text, re.I) or \
        re.search(r"is not clickable at point[^\n]*?(<[^>]{0,400}>)", text, re.I)
    return m.group(1) if m else ""


NORMALIZERS = [
    (re.compile(r"\(Session info:[^)]*\)", re.I), ""),
    (re.compile(r"Stacktrace:[\s\S]*", re.I), ""),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I | re.A), "<uuid>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I | re.A), "<hex>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I | re.A), "<hex>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?", re.A), "<time>"),
    (re.compile(r"\d+", re.A), "<n>"),
    (re.compile(r"\s+"), " "),
]


def signature(text, mx=160) -> str:
    if not text:
        return ""
    s = text
    for rx, rep in NORMALIZERS:
        s = rx.sub(rep, s)
    return s.strip().lower()[:mx]


def js_round(x: float) -> int:
    return int(math.floor(x + 0.5))


def parse_time(s):
    if not s:
        return None
    t = str(s).strip().replace("/", "-")
    for f in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(t[:25], f).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t).timestamp()
    except ValueError:
        return None


# ======================= Python 日志与异常链解析 =======================
FRAME_RE = re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+),\s*in\s+([\w<>.]+)', re.A)
CHAIN_SPLIT = re.compile(r"During handling of the (?:above )?exception,? another exception occurred:?|"
                         r"The above exception was the direct cause of the following exception:?", re.I)
EXC_FIND = re.compile(r"(?:^|[\s>])((?:[A-Za-z_]\w*\.)*(?:[A-Z]\w*(?:Error|Exception|Exit|Warning|Failure|NotVisible|NotEnabled|NotFound|Interrupt)|Exception)|(?:[A-Za-z_]\w*\.)+error)(?::[ \t]?|\s*$)", re.A)
TB = "Traceback (most recent call last):"


def analyze_log(text, rules):
    if not text or not re.search(r"Traceback|During handling|Exception:|Error:", text):
        return None
    is_fw = lambda f: find_any(f["file"], rules.get("framework_paths"))
    segs = []
    for s in CHAIN_SPLIT.split(text):
        body = s
        tb = s.find(TB)
        if tb >= 0:
            body = s[tb + len(TB):]
        frames, end = [], 0
        for m in FRAME_RE.finditer(body):
            frames.append({"file": re.sub(r"\s+", "", m.group(1)), "line": int(m.group(2)), "func": m.group(3)})
            end = m.end()
        tail = body[end:]
        em = EXC_FIND.search(tail)
        typ = em.group(1) if em else ""
        msg = tail[em.end():].strip() if em else ""
        handler = any(f["func"] in (rules.get("handler_funcs") or []) for f in frames)
        segs.append({"type": typ, "msg": msg, "frames": frames, "project": [f for f in frames if not is_fw(f)],
                     "handler": handler, "exit": typ.endswith("SystemExit")})
    main = [s for s in segs if not s["handler"] and not s["exit"] and s["type"]]
    root = main[0] if main else None
    with_test = next((s for s in segs if any(re.match(r"test", f["func"], re.I) for f in s["project"])), None) or \
        next((s for s in segs if s["project"]), None)
    path = [f["func"] + "（" + re.split(r"[\\/]", f["file"])[-1] + " 第" + str(f["line"]) + "行）" for f in with_test["project"]] if with_test else []
    root_at = root["project"][-1] if root and root["project"] else None
    test_fn = ""
    if with_test:
        test_fn = next((f["func"] for f in with_test["project"] if re.match(r"test", f["func"], re.I)), "")
    first = CHAIN_SPLIT.split(text)[0]
    tbi = first.find(TB)
    if tbi >= 0:
        step_log = first[:tbi]
    else:
        em = EXC_FIND.search(first)
        step_log = first[:em.start()] if em else first
    step_log = step_log.strip()
    popup_text = None
    for s in main:
        pm = re.search(r"pop-?up error:\s*([\s\S]*)", s["msg"], re.I)
        if pm:
            popup_text = re.sub(r"\s+", " ", pm.group(1)).strip()
            break
    sys_msgs = [m.group(1) + ": " + m.group(2).strip() for m in
                re.finditer(r"(Validation Error|Error Message|Life/Asia Message)\s*:\s*(.+?)(?=\s{2,}|Traceback|$)", step_log, re.I)]
    if popup_text:
        sys_msgs.insert(0, popup_text)
    success = []
    for p in rules.get("success_marks") or []:
        h = find_any(step_log, [p])
        if h:
            success.append(h["hit"])
    wl = re.search(r"dict_keys\(\[([\s\S]*?)\]\)", text)
    windows = [x[1:-1] for x in re.findall(r"'[^']+'", wl.group(1))] if wl else []
    m1 = re.search(r"Could not find '([^']+)'", text)
    m2 = re.search(r"Can't find window ([^\n]+?)(?=\s+During|\s*$)", text)
    expect_win = (m1.group(1) if m1 else "") or (m2.group(1) if m2 else "")
    sn = [re.sub(r"^[\d/]+\s*", "", re.sub(r"^.*?finding transaction window\s*", "", m.group(1), flags=re.I)).strip()
          for m in re.finditer(r"([A-Za-z][\w/&.' -]{2,80}?)\s*\([^)]{2,30}\)\s*window wait success", step_log, re.A)]
    main_text = "\n".join([step_log] + [s["type"] + ": " + s["msg"] for s in main])
    return {
        "segs": segs, "root": root, "rootAt": root_at, "path": path, "testFn": test_fn, "stepLog": step_log,
        "popupText": popup_text, "sysMsgs": sys_msgs, "success": success, "windows": windows, "expectWin": expect_win,
        "screen": sn[0] if sn else "", "types": [s["type"] for s in main], "mainText": main_text,
        "shotFailed": any(s["handler"] and re.search(r"screen grab failed", s["msg"], re.I) for s in segs),
        "handlerErr": "；".join(s["type"] + ": " + s["msg"] for s in segs if s["handler"]),
    }


# ======================= 证据 =======================
def evidence_of(c):
    ev = []

    def add(kind, label, text, **extra):
        if text:
            ev.append(dict({"id": "E" + str(len(ev) + 1), "kind": kind, "label": label, "text": text}, **extra))

    L = c.get("L")
    if L:
        add("step", "步骤日志（失败前打印的内容）", L["stepLog"])
        sysm = [x for x in L["sysMsgs"] if x]
        if L["popupText"] is not None or L["sysMsgs"]:
            add("sys", "系统提示原文（弹窗/校验信息）", "（弹窗出现了，但脚本没有读到文字）" if L["popupText"] == "" and not sysm else "\n".join(sysm))
        if L["root"]:
            add("root", "最先发生的异常", L["root"]["type"] + (": " + L["root"]["msg"] if L["root"]["msg"] else ""))
        if L["path"]:
            add("loc", "失败位置（项目代码调用链）", " → ".join(L["path"]))
        if L["windows"]:
            add("win", "当时打开的窗口", "\n".join(L["windows"]))
        if L["handlerErr"]:
            add("handler", "失败处理过程中的异常（截图/清理）", L["handlerErr"])
        add("stack", "完整日志", "\n".join(x for x in [c.get("error"), c.get("stack")] if x))
    else:
        add("msg", "报错信息", c.get("error"))
        add("exc", "异常类型", c.get("exception"), derived=not c.get("exceptionRaw"))
        add("page", "页面/弹窗文字", c.get("pageText") or c.get("alertText"), derived=not c.get("pageText"))
        add("stack", "堆栈/日志", c.get("stack"))
    shots = c.get("shots") or []
    if shots:
        for s in shots:
            add("shot", "截图", s.get("name"))
    else:
        add("shot", "截图（路径）", c.get("screenshot"))
    o = c.get("obs") or {}
    if o.get("kind") or o.get("text"):
        add("obs", "截图观察（人工记录）", (OBS_KINDS.get(o.get("kind"), "") if o.get("kind") else "") +
            (("；" if o.get("kind") else "") + "截图中的文字：" + o["text"] if o.get("text") else ""))
    if c.get("ocrText"):
        add("ocr", "截图文字（自动识别，可能有误）", c["ocrText"])
    if c.get("rerun"):
        r2 = c.get("r2") or {}
        add("rerun", "重跑记录", ("重跑通过" if c["rerun"] == "pass" else "重跑仍失败，但报错与第一次不同（第二次已作为单独一条记录）"
                              if r2.get("same") is False else "重跑仍失败，报错与第一次相同") + ("：" + c["rerunNote"] if c.get("rerunNote") else ""))
    if c.get("parent"):
        add("rerun", "第一次执行", "这是重跑（第 2 次）的结果；第 1 次执行失败的报错与这次不同")
    if c.get("dataCheck"):
        add("data", "人工核查结果", DATA_CHECK.get(c["dataCheck"], c["dataCheck"]) + ("：" + c["dataNote"] if c.get("dataNote") else ""))
    return ev


def ev_id(ev, kind):
    return next((e["id"] for e in ev if e["kind"] == kind), None)


def check_of(c, kind):
    d = c.get("dataCheck")
    return d if d and d in CHECK_KINDS[kind]["options"] else None


def _s(x):
    return "" if x is None else str(x)


# ======================= 分类 =======================
def classify_core(c, ctx, rules, use_ocr):
    ev = evidence_of(c)
    E = lambda k: ev_id(ev, k)
    L = c.get("L")
    text = L["mainText"] if L else "\n".join(x for x in [c.get("error"), c.get("stack")] if x)
    exc = c.get("exception") or ""

    def out(cat, status, rule, why=None, need=None, hits=None, **extra):
        r = {"cat": cat, "status": status, "rule": rule, "why": why or [], "need": need or [], "hits": hits or [], "flags": [], "ev": ev}
        r.update(extra)
        return r

    any_exc = (lambda lst: any(has_exc(short_type(t), lst) or has_exc(t, lst) for t in L["types"])) if L else (lambda lst: has_exc(exc, lst))
    root_txt = L["root"]["type"] + ": " + L["root"]["msg"] if L and L["root"] else ""
    where = "，位置 " + L["rootAt"]["func"] + " 第" + str(L["rootAt"]["line"]) + "行（" + _s(E("loc")) + "）" if L and L["rootAt"] else ""
    o = c.get("obs") or {}
    manual_t = (o.get("text") or "").strip()
    obs_t = manual_t or ((c.get("ocrText") or "").strip() if use_ocr else "")
    EO = lambda: E("obs") if manual_t else E("ocr")

    # ---------- 环境 ----------
    env_hit = None
    if has_exc(exc, rules.get("env_exceptions")):
        env_hit = out("ENVIRONMENT", "confirmed", "ENV1", ["异常类型 " + exc + " 表示浏览器/驱动/设备无法启动会话（" + _s(E("exc") or E("root")) + "）"], [], [exc])
    else:
        h = find_any(text, rules.get("env_patterns"))
        if h:
            if L:
                src = E("step") if find_any(L["stepLog"], [h["pattern"]]) else E("sys") if find_any("\n".join(L["sysMsgs"]), [h["pattern"]]) else E("root")
            else:
                src = E("msg") or E("stack")
            desk = bool(re.search(r"SetCursorPos|active desktop|DESKTOP_UNAVAILABLE", h["hit"], re.I))
            back = bool(re.search(r"transport-level|forcibly closed|network-related|Timeout expired", h["hit"], re.I))
            why = ["报错中出现环境类关键字“" + h["hit"] + "”（" + _s(src) + "）"]
            if desk:
                why.append("含义：执行机没有可交互的桌面（远程桌面窗口最小化、断开或锁屏时会这样），脚本无法移动鼠标、输入文字")
            elif back:
                why.append("含义：被测系统与数据库/后台服务之间的连接中断，是被测系统运行环境的问题，不是脚本问题")
            env_hit = out("ENVIRONMENT", "confirmed", "ENV-DESK" if desk else "ENV2", why, ["向环境负责人确认该时段执行机/服务的状态；环境恢复后重跑"], [h["hit"]],
                          groupKey="env:desktop" if desk else "env:backend-connection" if back else "env:" + h["pattern"].lower())
    if not env_hit and ctx["mass"].get(c["uid"]):
        m = ctx["mass"][c["uid"]]
        env_hit = out("ENVIRONMENT", "suspected", "ENV3", ["同一报错特征在本次运行中出现在 " + str(m["n"]) + " 个用例（占失败数 " + str(m["pct"]) + "%）" + ("，" + m["span"] if m["span"] else "")],
                      ["确认该时段环境（服务、网络、设备）是否异常；如果是同一个产品问题导致的大面积失败，请改为疑似产品缺陷"], [])
    if env_hit:
        return env_hit

    alert_text = c.get("alertText") or ""
    page_text = "\n".join(x for x in [c.get("pageText"), alert_text] + (L["sysMsgs"] if L else []) + ([obs_t] if obs_t else []) if x)
    biz_in_page = find_any(page_text, rules.get("business_errors"))

    # ---------- 系统提示 ----------
    if (L and (L["popupText"] is not None or L["sysMsgs"])) or obs_t:
        sysm = "\n".join([x for x in (L["sysMsgs"] if L else []) if x] + ([obs_t] if obs_t else []))
        sys_ev = "、".join(x for x in [E("sys") if L and (L["popupText"] is not None or L["sysMsgs"]) else None, EO() if obs_t else None] if x)
        if L and L["popupText"] == "" and not sysm:
            return out("NEEDS_HUMAN", "suspected", "SYS-EMPTY", ["提交后出现了弹窗，脚本报“pop-up error”，但没有读到弹窗文字（" + _s(E("sys")) + "）"],
                       ["看截图" + ("（" + E("shot") + "）" if E("shot") else "") + "，把弹窗文字抄到“截图观察”里，页面会重新判断；建议修改弹窗处理函数，读取对话框内全部文字后再关闭"], [], reason="unknown_popup")
        lock = find_any(sysm, rules.get("lock_messages"))
        if lock:
            k = check_of(c, "lock")
            why = ["系统提示“" + lock["hit"] + "”（" + sys_ev + "）：用例要用的保单/合同正被其他会话占用"]
            if k:
                why.append("核查结果：" + DATA_CHECK[k] + "（" + _s(E("data")) + "）")
            if k == "lock_prev":
                return out("SCRIPT_ISSUE", "confirmed", "CHK-LOCK1", why, ["修改前面那个用例的清理步骤：失败后也要关闭窗口、释放保单"], [lock["hit"]], checkKind="lock")
            return out("TEST_DATA", "confirmed", "DATA-LOCK", why, [] if k else ["人工核查：查占用来源，本批次前面失败的用例有没有留下未关闭的窗口；有没有其他批次或同事同时使用这张保单"],
                       [lock["hit"]], groupKey="data:lock", checkKind="lock")
        cfg = find_any(sysm, rules.get("config_messages"))
        if cfg:
            k = check_of(c, "cfg")
            why = ["系统提示“" + cfg["hit"] + "”（" + sys_ev + "）：被测系统缺少某项配置"]
            if k:
                why.append("核查结果：" + DATA_CHECK[k] + "（" + _s(E("data")) + "）")
                return out(CHECK_KINDS["cfg"]["options"][k][1], "confirmed", "CHK-CFG", why, [], [cfg["hit"]], checkKind="cfg")
            return out("NEEDS_HUMAN", "suspected", "SYS-CFG", why, ["人工核查：这项配置在测试环境中是否应该存在。应该存在但缺失 → 环境问题；配置正确仍报错 → 产品缺陷"], [cfg["hit"]],
                       reason="system_config", checkKind="cfg")
        crash = find_any(sysm, rules.get("crash_messages"))
        if crash:
            return out("PRODUCT_DEFECT", "suspected", "SYS-CRASH", ["被测程序弹出未处理异常对话框“" + crash["hit"] + "”（" + sys_ev + "）"], ["保存对话框中的异常详情，确认同样操作能否重现"], [crash["hit"]])
        nz = find_any(obs_t, rules.get("noise_popups")) if obs_t else None
        if nz:
            return out("POPUP_INTERFERENCE", "confirmed", "OBS-POPN", ["截图中有弹窗，文字“" + nz["hit"] + "”在干扰弹窗清单中（" + _s(EO()) + "）"], ["给脚本加上这个弹窗的处理（出现时关闭）"], [nz["hit"]])

    # ---------- 原生对话框 ----------
    if has_exc(exc, rules.get("alert_exceptions")):
        noise = find_any(alert_text, rules.get("noise_popups"))
        if noise:
            return out("POPUP_INTERFERENCE", "confirmed", "POP1", ["出现原生对话框（" + _s(E("exc")) + "），文字“" + noise["hit"] + "”在干扰弹窗清单中（" + _s(E("page") or E("msg")) + "）"], [], [noise["hit"]])
        if not find_any(alert_text, rules.get("business_errors")):
            return out("NEEDS_HUMAN", "suspected", "POP1-未知", ["出现原生对话框（" + _s(E("exc")) + "）" + ("，文字为“" + alert_text + "”" if alert_text else "，但报错里没有带出弹窗文字")],
                       ["判断这个弹窗是干扰还是业务报错，并补充到“规则配置 → 弹窗清单”"], [alert_text] if alert_text else [], reason="unknown_popup")

    # ---------- 业务报错 ----------
    is_assert = has_exc(exc, rules.get("assertion_exceptions"))
    biz = biz_in_page or (find_any(c.get("error"), rules.get("business_errors")) if (is_assert or not exc) else None)
    if biz:
        src = (E("page") or E("sys") or EO()) if biz_in_page else (E("msg") or E("root"))
        k = check_of(c, "biz")
        if k == "ok":
            return out("PRODUCT_DEFECT", "confirmed", "BIZ2", ["出现业务报错“" + biz["hit"] + "”（" + _s(src) + "）", "数据已核查且正常（" + _s(E("data")) + "），系统仍报错"], [], [biz["hit"]], checkKind="biz")
        if k:
            return out("TEST_DATA", "confirmed", "BIZ1", ["出现业务报错“" + biz["hit"] + "”（" + _s(src) + "）", "数据核查结果：" + DATA_CHECK[k] + "（" + _s(E("data")) + "）"], [], [biz["hit"]], checkKind="biz")
        return out("NEEDS_HUMAN", "suspected", "BIZ3", ["出现业务报错“" + biz["hit"] + "”（" + _s(src) + "）", "只凭报错文字分不清是测试数据问题还是系统问题"],
                   ["人工核查：查这条用例用到的数据，选择核查结果后会自动重新分类"], [biz["hit"]], reason="pending_data_check", checkKind="biz")

    # ---------- 网页弹框 ----------
    clickish = has_exc(exc, rules.get("intercept_exceptions")) or has_exc(exc, rules.get("locator_exceptions"))
    noise_in_page = find_any(c.get("pageText"), rules.get("noise_popups"))
    if noise_in_page and clickish:
        return out("POPUP_INTERFERENCE", "confirmed", "POP2", ["失败时页面上有弹框，文字“" + noise_in_page["hit"] + "”在干扰弹窗清单中（" + _s(E("page")) + "）",
                                                              "异常类型 " + exc + " 属于点击/定位失败（" + _s(E("exc")) + "）"], [], [noise_in_page["hit"]])
    if has_exc(exc, rules.get("intercept_exceptions")):
        el = extract_interceptor(text)
        kw = find_any(el, rules.get("overlay_keywords")) if el else None
        why = ["点击被其他元素挡住（" + _s(E("exc")) + "）"]
        if el:
            why.append("挡住点击的元素：" + el[:160] + ("，包含弹框特征“" + kw["hit"] + "”" if kw else ""))
        return out("POPUP_INTERFERENCE", "suspected", "POP3" if kw else "POP3-弱", why,
                   ["看截图" + ("（" + E("shot") + "）" if E("shot") else "") + "确认遮挡物是什么：弹窗、加载遮罩，还是页面布局变化（布局变化应改为脚本问题）"], [kw["hit"]] if kw else [])

    # ---------- 桌面端（pywinauto）与 Python 日志 ----------
    if L and L["root"]:
        done = "步骤日志显示业务操作已经成功（“" + L["success"][0] + "”，" + _s(E("step")) + "），失败发生在之后的结果校验阶段" if L["success"] else ""
        shot = "（" + E("shot") + "）" if E("shot") else "（当前没有截图）"
        extra = {"phase": "verify"} if done else {}
        mk = find_any(root_txt, rules.get("masked_patterns"))
        if mk:
            line = re.split(r"[\\/]", L["rootAt"]["file"])[-1] + " 第" + str(L["rootAt"]["line"]) + "行" if L["rootAt"] else "报错所在行"
            return out("NEEDS_HUMAN", "suspected", "MASK1",
                       ["最先发生的异常是 " + L["root"]["type"] + "：" + L["root"]["msg"][:120] + where,
                        "含义：前一步查找控件/窗口/数据时没找到，函数返回了 " + ("None" if "NoneType" in mk["hit"] else "False") + "，代码没有检查就继续使用，才出现这个报错。真实原因是“前一步没找到什么”，报错没有说"],
                       ["打开 " + line + "，看这一行用的变量来自哪个查找函数，查的是哪个控件/数据", "看失败时截图" + shot + "：要找的控件是否在屏幕上、是否被其他窗口挡住、页面是否停在别的界面",
                        "建议修改脚本：查找函数找不到时直接抛出带控件名称的异常，不要返回 False/None"], [mk["hit"]], reason="masked_failure", **extra)
        if any_exc(rules.get("desk_ambiguous")):
            return out("SCRIPT_ISSUE", "confirmed", "DSK-AMB", ["异常 ElementAmbiguousError：定位条件同时匹配到多个控件（" + _s(E("root")) + "）" + where] + ([done] if done else []),
                       ["定位条件需要改得更精确（加上所在窗口、控件类型或序号）", "同时检查是否有前面用例留下的窗口没关，导致出现了多个同名控件"], [], **extra)
        opt = find_any(root_txt, rules.get("desk_option_missing"))
        if opt:
            return out("SCRIPT_ISSUE", "suspected", "DSK-OPT", ["下拉框里没有脚本要选的选项：" + opt["hit"] + "（" + _s(E("root")) + "）" + where] + ([done] if done else []),
                       ["看截图或手工打开这个下拉框，确认实际选项名称：名称改了 → 改脚本；选项本应存在却没有 → 疑似产品缺陷", "建议脚本报错时把下拉框里的全部选项一起打印出来"], [opt["hit"]], **extra)
        dtp = find_any(root_txt, rules.get("desk_datetime"))
        if dtp:
            k = check_of(c, "dtp")
            why = ["日期控件设置失败：“" + dtp["hit"] + "”（" + _s(E("root")) + "）" + where]
            if k:
                why.append("核查结果：" + DATA_CHECK[k] + "（" + _s(E("data")) + "）")
                return out(CHECK_KINDS["dtp"]["options"][k][1], "confirmed", "CHK-DTP", why, [], [dtp["hit"]], checkKind="dtp", **extra)
            return out("SCRIPT_ISSUE", "suspected", "DSK-DTP", why, ["人工核查：记录脚本要设置的日期值和控件允许的范围：超出范围 → 测试数据问题；在范围内仍失败 → 脚本问题", "建议脚本报错时打印要设置的日期"],
                       [dtp["hit"]], checkKind="dtp", **extra)
        if any_exc(rules.get("desk_not_enabled")):
            return out("NEEDS_HUMAN", "suspected", "DSK-DIS", ["要点击/输入的控件处于不可用（灰色）状态：ElementNotEnabled（" + _s(E("root")) + "）" + where],
                       ["看截图" + shot + "确认是哪个按钮不可用、界面上有没有提示", "按钮不可用通常是业务规则限制（前面必填项没填、保单状态不允许这项操作）：数据不满足 → 测试数据问题；步骤漏了 → 脚本问题；条件都满足仍不可用 → 疑似产品缺陷"],
                       [], reason="control_state", **extra)
        if any_exc(rules.get("desk_not_visible")):
            return out("SCRIPT_ISSUE", "suspected", "DSK-VIS", ["控件存在但不可见：ElementNotVisible（" + _s(E("root")) + "）" + where],
                       ["看截图" + shot + "：控件所在的页签/区域是否没切换过去、窗口是否被最小化或被其他窗口挡住", "界面正常但控件被隐藏 → 可能是被测系统界面改了，需要确认"], [], **extra)
        nf = any_exc(rules.get("desk_not_found")) or find_any(root_txt, rules.get("desk_not_found"))
        if nf:
            why = ["找不到窗口或控件" + ("“" + L["expectWin"] + "”" if L["expectWin"] else "") + "（" + _s(E("root")) + "）" + where]
            if done:
                why.append(done)
            return out("NEEDS_HUMAN", "suspected", "DSK-NF", why,
                       ["看截图" + shot + "确认当时屏幕上是什么窗口：目标窗口没打开 → 前一步操作没生效（重跑确认）；打开了但名称不同 → 脚本问题；出现了别的对话框 → 按对话框文字判断",
                        "如果日志里列出了当时打开的窗口，检查有没有前面用例留下的窗口"], [], reason="insufficient_evidence", **extra)
        if L["root"]["type"] == "Exception" and not find_any(L["root"]["msg"], list(rules.get("business_errors") or []) + ["not found"]):
            return out("NEEDS_HUMAN", "suspected", "GEN1", ["报错只说明“" + L["root"]["msg"][:100] + "”（" + _s(E("root")) + "），没有说明原因" + where],
                       ["看步骤日志" + ("（" + E("step") + "）" if E("step") else "") + "最后几行和截图" + shot + "，找系统给出的提示"], [], reason="generic_error")

    # ---------- 脚本问题 ----------
    if has_exc(exc, rules.get("invalid_selector")):
        return out("SCRIPT_ISSUE", "confirmed", "SCR2", ["定位表达式本身写错（" + _s(E("exc")) + "）"], [], [exc])
    if has_exc(exc, rules.get("code_errors")):
        in_test = find_any(c.get("stack") or c.get("error"), rules.get("test_code_paths"))
        return out("SCRIPT_ISSUE", "confirmed" if in_test else "suspected", "SCR3",
                   ["测试代码运行时错误 " + exc + "（" + _s(E("exc")) + "）"] + (["堆栈中出现测试代码路径“" + in_test["hit"] + "”（" + _s(E("stack")) + "）"] if in_test else []),
                   [] if in_test else ["堆栈中没有找到测试代码路径，也可能是被测系统返回了异常数据，请看堆栈确认出错位置"], [exc])
    if has_exc(exc, rules.get("locator_exceptions")):
        return out("SCRIPT_ISSUE", "suspected", "SCR1", ["找不到元素/等待超时（" + _s(E("exc")) + "），没有弹框文字和业务报错证据"],
                   ["看截图" + ("（" + E("shot") + "）" if E("shot") else "，当前没有截图") + "：页面正常、只是元素变了 → 脚本问题；页面空白、报错、缺少整块内容 → 改为疑似产品缺陷；页面上有弹窗 → 改为弹窗干扰"], [exc])

    # ---------- 断言 ----------
    if is_assert:
        ea = find_any(c.get("error"), rules.get("expected_actual"))
        if ea:
            return out("PRODUCT_DEFECT", "suspected", "AST1", ["断言失败且有明确的期望值与实际值（" + _s(E("msg")) + "）"], ["对照当前需求确认期望值是否过时；过时请改为脚本问题"], [ea["hit"]])
        return out("NEEDS_HUMAN", "suspected", "AST2", ["断言失败，但没有期望值和实际值（" + _s(E("msg")) + "）"], ["查看日志确认断言的内容"], [], reason="assertion_no_values")

    if not c.get("error") and not c.get("stack"):
        return out("NEEDS_HUMAN", "suspected", "NONE", ["没有报错信息"], ["查看原始日志或截图"], [], reason="insufficient_evidence")
    return out("NEEDS_HUMAN", "suspected", "NONE", ["没有规则命中" + ("（异常类型 " + exc + "）" if exc else "")], ["人工判断后可在“规则配置”中补充规则"], [], reason="no_rule_matched")


OBS_SKIP = re.compile(r"^(BIZ|SYS-CFG|SYS-CRASH|DATA-LOCK|CHK|OBS-POPN|AST)")


def classify(c, ctx, rules):
    r = classify_core(c, ctx, rules, False)
    o = c.get("obs") or {}
    # 截图自动识别的文字：只在没有人工记录时使用；结论变了就降为“待复核”
    if c.get("ocrText") and not o.get("text"):
        r2 = classify_core(c, ctx, rules, True)
        if r2["cat"] != r["cat"] or r2["rule"] != r["rule"]:
            id_o, was = ev_id(r2["ev"], "ocr"), RULE_NAMES.get(r["rule"], r["rule"])
            if r["status"] == "confirmed" and r["cat"] != "NEEDS_HUMAN":
                r["why"] = r["why"] + ["截图识别的文字提示可能是另一种情况：" + RULE_NAMES.get(r2["rule"], r2["rule"]) + "（" + _s(id_o) + "）。日志证据已能确认，保持原判断；如截图与日志矛盾请人工确认"]
            else:
                r2.update(status="suspected", ocr=True, why=r2["why"] + ["这个判断用到了截图自动识别的文字（" + _s(id_o) + "），识别可能有误；只看日志时判断为：" + was],
                          need=["打开截图核对识别出的文字；无误就点“采用识别文字”，结论会变为已确认"] + r2["need"])
                r = r2
    if not o.get("kind") or o["kind"] == "unclear" or (r["status"] == "confirmed" and r["cat"] != "NEEDS_HUMAN") or OBS_SKIP.search(r["rule"]):
        return r
    E, was = ev_id(r["ev"], "obs"), "（规则原本判断：" + RULE_NAMES.get(r["rule"], r["rule"]) + "）"

    def setr(cat, status, rule, why, need, **extra):
        r.update(cat=cat, status=status, rule=rule, why=[why + "（" + _s(E) + "）" + was] + r["why"], need=need,
                 reason=(r.get("reason") or "insufficient_evidence") if cat == "NEEDS_HUMAN" else None, checkKind=None)
        r.update(extra)
        return r

    T = "“" + re.sub(r"\s+", " ", o["text"])[:60] + "”" if o.get("text") else ""
    k = o["kind"]
    if k == "normal":
        return setr("SCRIPT_ISSUE", "confirmed", "OBS-OK", "人工看截图：页面正常，要操作的控件就在屏幕上，说明页面和环境没有问题，是脚本没有找到或没有操作到它", ["对照截图核对脚本的定位条件（窗口标题、控件名称、序号），改好后重跑验证"])
    if k == "popup":
        if T:
            return setr("NEEDS_HUMAN", "suspected", "OBS-POPU", "截图中有弹窗挡在前面，文字" + T + "不在任何弹窗清单中", ["判断这个弹窗是干扰（与被测功能无关）还是系统报错，然后在“配置 → 判断规则 → 弹窗清单”里补上，以后会自动判断"], reason="unknown_popup")
        return setr("POPUP_INTERFERENCE", "suspected", "OBS-POP", "截图中有弹窗挡在前面", ["把弹窗上的文字抄到“截图中的文字”里，页面会判断它是干扰还是系统报错"])
    if k == "blank":
        return setr("PRODUCT_DEFECT", "suspected", "OBS-BLANK", "截图中页面没有正常显示（空白、报错页或一直在加载）", ["手工打开同一页面确认能否重现：能重现 → 提缺陷；不能重现 → 重跑确认是否偶发"])
    if k == "other":
        return setr("NEEDS_HUMAN", "suspected", "OBS-OTHER", "截图中屏幕停在别的窗口或页面，说明上一步操作没有生效", ["先重跑；仍失败时看上一步的日志，确认那一步为什么没生效"], reason="insufficient_evidence")
    if k == "disabled":
        return setr("NEEDS_HUMAN", "suspected", "OBS-DIS", "截图中要操作的控件是灰色不可用的", ["按钮不可用通常是业务规则限制：数据不满足条件 → 测试数据问题；前面漏了步骤 → 脚本问题；条件都满足仍不可用 → 疑似产品缺陷"], reason="control_state")
    if k == "desktop":
        return setr("ENVIRONMENT", "confirmed", "OBS-DESK", "截图是锁屏、黑屏或远程桌面断开的画面，执行机当时没有可用的桌面", ["向环境负责人确认执行机的会话状态；恢复后重跑"])
    return r


RERUN_GO = {"DSK-NF": "找不到窗口可能是前一步偶发没生效，重跑一次可区分偶发和必现", "SCR1": "找不到元素可能是页面加载慢，重跑一次可区分偶发和定位失效",
            "DSK-VIS": "控件不可见可能是页面没切换完，重跑一次确认", "SYS-EMPTY": "弹窗可能是偶发，重跑一次看是否再出现", "POP1-未知": "对话框可能是偶发，重跑一次确认",
            "POP3": "遮挡多为偶发弹框，重跑一次确认", "POP3-弱": "遮挡多为偶发，重跑一次确认", "AST1": "断言不一致先重跑一次排除偶发；仍失败再提单",
            "OBS-OTHER": "上一步操作没生效，可能是偶发，重跑一次确认", "OBS-BLANK": "页面没显示出来，先重跑一次排除偶发，仍失败再提单", "OBS-POP": "弹窗多为偶发，重跑一次确认"}


def rerun_plan(c):
    a, f = c["auto"], c["final"]
    r = a["rule"]
    if c.get("parent"):
        return {"b": "no", "why": "这是重跑产生的第2次记录，单独分析"}
    if c.get("rerun"):
        r2 = c.get("r2") or {}
        return {"b": "done", "why": "重跑已通过：偶发失败，不提单" if c["rerun"] == "pass" else "重跑失败，报错与第一次不同（第2次单独成一条）" if r2.get("same") is False else "重跑失败，报错与第一次相同：问题必现"}
    if a.get("checkKind") and not c.get("dataCheck") and not c.get("override"):
        return {"b": "fix", "why": "先做人工核查（" + CHECK_KINDS[a["checkKind"]]["name"].split(" → ")[0] + "），不核查直接重跑结果不会变"}
    if "环境中断边界" in a["flags"]:
        return {"b": "go", "why": "紧挨环境中断的起点，很可能也受环境影响"}
    if f == "ENVIRONMENT":
        return {"b": "fix", "why": "先补上测试环境缺失的配置，再重跑"} if c.get("dataCheck") == "cfg_missing" else {"b": "go", "why": "环境问题与用例无关；确认环境已恢复后重跑"}
    if f == "POPUP_INTERFERENCE":
        return {"b": "go", "why": "弹窗多为偶发，重跑可确认；反复出现就给脚本加弹窗处理"}
    if r in RERUN_GO and not c.get("override"):
        return {"b": "go", "why": RERUN_GO[r]}
    if f == "PRODUCT_DEFECT":
        return {"b": "no", "why": "已判断是系统问题，直接起草 Jira，重跑不会改变结果"}
    if f == "TEST_DATA":
        return {"b": "fix", "why": "先释放被占用的保单（或换一张），再重跑" if r == "DATA-LOCK" else "先补数据或换数据，再重跑"}
    if f == "SCRIPT_ISSUE":
        return {"b": "fix", "why": "先修前面用例的清理步骤（失败后关闭窗口、释放保单），再重跑" if r == "CHK-LOCK1" else "脚本本身有错，直接重跑结果不会变；修好脚本后再重跑验证"}
    if "有残留窗口" in a["flags"]:
        return {"b": "go", "why": "屏幕上有前面用例留下的窗口，单独重跑可排除干扰"}
    if r == "MASK1":
        return {"b": "fix", "why": "真实原因被掩盖，先看截图确认没找到的是什么，否则重跑多半同样失败"}
    return {"b": "fix", "why": "证据不足，先看截图和日志判断原因；能判断后再决定是否重跑"}


def is_fail(result, rules) -> bool:
    if not result:
        return False
    r = str(result).strip().lower()
    if re.match(r"^(passed|pass|success|ok|通过|成功|skipped|skip|跳过)$", r):
        return False
    return any(w.lower() in r for w in rules.get("fail_words") or [])


def prepare(c, rules):
    c["L"] = analyze_log("\n".join(x for x in [c.get("error"), c.get("stack")] if x), rules)
    L = c["L"]
    if L and L["root"] and not c.get("exceptionRaw"):
        c["exception"] = short_type(L["root"]["type"])
    r = L and L["root"]
    if r:
        at = " @" + L["rootAt"]["func"] if L["rootAt"] else " @" + L["path"][-1].split("（")[0] if L["path"] else ""
        c["sig0"] = signature(short_type(r["type"]) + " " + r["msg"].split("\n")[0] + at)
    else:
        c["sig0"] = signature((c["exception"] + " " if c.get("exception") else "") + (c.get("error") or c.get("stack") or "").split("\n")[0])


def make_case(row: dict, rules: dict) -> dict:
    """把一条原始记录（页面导入后的字段）补齐成分析用的用例，与 engine.js 的 toCases 相同。"""
    c = dict(row)
    for k in ("error", "stack", "exceptionRaw", "pageText", "screenshot", "start", "module", "device", "name", "result"):
        c[k] = _s(c.get(k)).strip()
    c["error"], c["stack"] = c["error"][:8000], c["stack"][:20000]
    raw = c["exceptionRaw"]
    c["exception"] = raw.split(".")[-1] if raw else extract_exception(c["error"]) or extract_exception(c["stack"])
    c["alertText"] = extract_alert_text(c["error"]) or extract_alert_text(c["stack"])
    if "failed" not in c:
        c["failed"] = is_fail(c["result"], rules)
    return c


def to_cases(rows, mapping, rules, run_id, start_idx=0):
    """与 engine.js 的 toCases 相同：rows 是原始记录，mapping 是 {页面字段: 原始列名}。"""
    out = []
    for i, r in enumerate(rows):
        g = lambda k: _s(r.get(mapping[k])).strip() if mapping.get(k) else ""
        n = start_idx + i + 1
        row = {k: g(k) for k in ("name", "result", "error", "stack", "exceptionRaw", "pageText", "screenshot", "start", "module", "device")}
        row.update(uid=run_id + "#" + str(n), seq=n, run=run_id, id=g("id") or "第" + str(n) + "行")
        out.append(make_case(row, rules))
    return out


def classify_all(cases, rules):
    for c in cases:
        prepare(c, rules)
    base = [c for c in cases if not c.get("parent")]
    failed = [c for c in base if c.get("failed")]
    mass, by_sig = {}, {}
    for c in failed:
        if c["sig0"]:
            by_sig.setdefault(_s(c.get("run")) + "|" + c["sig0"], []).append(c)
    for lst in by_sig.values():
        run = lst[0].get("run")
        run_failed = len([x for x in failed if x.get("run") == run])
        pct = js_round(len(lst) * 100 / max(run_failed, 1))
        if len(lst) < rules.get("mass_min_cases", 5) or pct < rules.get("mass_ratio", 30):
            continue
        run_cases = sorted([x for x in base if x.get("run") == run], key=lambda x: x["seq"])
        idx = sorted(run_cases.index(c) for c in lst)
        contiguous = idx[-1] - idx[0] + 1 == len(idx)
        ts = sorted(t for t in (parse_time(c.get("start")) for c in lst) if t is not None)
        mins = js_round((ts[-1] - ts[0]) / 60) if len(ts) >= 2 else None
        if not contiguous and (mins is None or mins > rules.get("mass_window_min", 15)):
            continue
        span = "在执行顺序上连续（第 " + str(lst[0]["seq"]) + "–" + str(lst[-1]["seq"]) + " 个）" if contiguous else "集中在 " + str(mins) + " 分钟内"
        for c in lst:
            mass[c["uid"]] = {"n": len(lst), "pct": pct, "span": span}
    for c in cases:
        if not c.get("failed"):
            continue
        c["auto"] = classify(c, {"mass": {} if c.get("parent") else mass}, rules)
        c["sig"] = c["auto"].get("groupKey") or c["sig0"]
        c["final"] = c["override"]["cat"] if c.get("override") else c["auto"]["cat"]
        if c.get("rerun") == "fail":
            diff = (c.get("r2") or {}).get("same") is False
            c["auto"]["flags"].append("重跑报错不同" if diff else "重跑仍失败")
            c["auto"]["why"].append("重跑仍失败，但报错与第一次不同：第二次的失败已作为单独一条记录分析" if diff else "重跑仍失败，报错与第一次相同：问题必现")
        if c.get("rerun") == "pass":
            c["auto"]["flags"].append("重跑通过")
            c["auto"]["why"].append("重跑通过（" + _s(ev_id(c["auto"]["ev"], "rerun")) + "）：这次失败不是必现，属于偶发；分类仍按第一次失败的原因，便于统计哪类问题经常偶发")
        if c.get("parent"):
            c["auto"]["flags"].append("重跑第2次")
    cross_case(base, rules)
    for c in cases:
        if c.get("failed"):
            c["auto"]["brief"] = brief(c) + ("（依据截图识别的文字，待确认）" if c["auto"].get("ocr") else "")
            c["plan"] = rerun_plan(c)
    return cases


RULE_NAMES = {
    "ENV1": "浏览器/设备无法启动", "ENV2": "连接或服务故障", "ENV-DESK": "执行机桌面不可用", "ENV3": "大面积相同报错",
    "SYS-EMPTY": "弹窗文字未读到", "DATA-LOCK": "数据被占用", "CHK-LOCK1": "数据被前面用例占用",
    "SYS-CFG": "系统缺少配置", "CHK-CFG": "配置已核查", "SYS-CRASH": "被测程序崩溃",
    "POP1": "干扰对话框", "POP1-未知": "未知对话框", "BIZ1": "业务报错·数据有问题", "BIZ2": "业务报错·数据正常", "BIZ3": "业务报错·待核查数据",
    "POP2": "干扰弹框", "POP3": "点击被弹框遮挡", "POP3-弱": "点击被遮挡",
    "MASK1": "掩盖型报错", "DSK-AMB": "匹配到多个控件", "DSK-OPT": "下拉框无此选项", "DSK-DTP": "日期设置失败", "CHK-DTP": "日期已核查",
    "DSK-DIS": "控件不可用", "DSK-VIS": "控件不可见", "DSK-NF": "找不到窗口或控件", "GEN1": "笼统报错",
    "SCR1": "找不到元素或超时", "SCR2": "定位写法错误", "SCR3": "测试代码错误", "AST1": "断言值不一致", "AST2": "断言失败无数值", "NONE": "无规则命中",
    "OBS-OK": "截图：页面正常", "OBS-POP": "截图：有弹窗", "OBS-POPN": "截图：干扰弹窗", "OBS-POPU": "截图：未知弹窗", "OBS-BLANK": "截图：页面异常",
    "OBS-OTHER": "截图：停在别处", "OBS-DIS": "截图：控件灰色", "OBS-DESK": "截图：桌面不可用",
}


def rule_name(c):
    return "人工判定" if c.get("override") else RULE_NAMES.get(c["auto"]["rule"], c["auto"]["rule"])


def _q(s):
    return "“" + re.sub(r"\s+", " ", _s(s))[:60] + "”"


def brief(c):
    if c.get("override"):
        return "人工判定：" + _s(c["override"].get("reason"))
    a, L = c["auto"], c.get("L") or {}
    hits = a["hits"]
    hit = hits[0] if hits else None
    m = (L.get("root") or {}).get("msg") or ""
    fn = L["rootAt"]["func"] if L.get("rootAt") else ""
    ew = L.get("expectWin") or ""
    obs_text = (c.get("obs") or {}).get("text")
    B = {
        "ENV1": lambda: "异常 " + _s(c.get("exception")) + " 表示浏览器/设备会话无法创建 → 执行环境问题",
        "ENV-DESK": lambda: "报错" + _q(hit) + "：执行机没有可交互的桌面，无法操作鼠标键盘 → 环境问题，与用例本身无关",
        "ENV2": lambda: "报错" + _q(hit) + "属于连接或服务故障 → 环境问题",
        "ENV3": lambda: "同一报错在本次多个用例连续出现 → 疑似环境问题，待确认",
        "SYS-EMPTY": lambda: "提交后出现弹窗，但脚本没读到文字 → 原因未知，需看截图",
        "DATA-LOCK": lambda: "系统提示" + _q(hit) + "：保单正被其他会话占用 → 测试数据问题",
        "CHK-LOCK1": lambda: "保单被本批次前面失败的用例占用（未释放）→ 前面用例的清理步骤有问题",
        "SYS-CFG": lambda: "系统提示" + _q(hit) + "：缺少系统配置 → 需确认配置是否应该存在",
        "CHK-CFG": lambda: "系统提示" + _q(hit) + "，核查结果：" + DATA_CHECK.get(c.get("dataCheck"), ""),
        "SYS-CRASH": lambda: "被测程序弹出未处理异常 → 疑似产品缺陷",
        "POP1": lambda: "对话框" + _q(hit) + "在干扰清单中 → 弹窗干扰",
        "POP1-未知": lambda: "出现不在清单中的对话框 → 需判断是不是干扰",
        "BIZ1": lambda: "业务报错" + _q(hit) + "，核查确认数据有问题 → 测试数据问题",
        "BIZ2": lambda: "业务报错" + _q(hit) + "，核查确认数据正常 → 系统有问题",
        "BIZ3": lambda: "出现业务报错" + _q(hit) + " → 要核查数据，才能区分是数据问题还是系统问题",
        "POP2": lambda: "页面有干扰弹框" + _q(hit) + "挡住操作 → 弹窗干扰",
        "POP3": lambda: "点击被带弹框特征的元素挡住 → 疑似弹框遮挡，需看截图",
        "POP3-弱": lambda: "点击被其他元素挡住 → 需看截图确认遮挡物",
        "MASK1": lambda: "报错" + _q(m) + "是因为前一步没找到控件或数据（返回了空值）→ 真实原因被掩盖，需查 " + (fn or "报错所在函数"),
        "DSK-AMB": lambda: "定位条件同时匹配到多个控件 → 脚本定位需要加限定",
        "DSK-OPT": lambda: "下拉框里没有" + _q(hit) + " → 疑似选项名称变了",
        "DSK-DTP": lambda: "日期控件设置失败 → 需核查日期值是否超出允许范围",
        "CHK-DTP": lambda: "日期控件设置失败，核查结果：" + DATA_CHECK.get(c.get("dataCheck"), ""),
        "DSK-DIS": lambda: "要操作的控件是灰色不可用 → 需看截图确认原因",
        "DSK-VIS": lambda: "控件存在但不可见 → 疑似页签或区域没切换过去",
        "DSK-NF": lambda: "找不到" + ("窗口" + _q(ew) if ew else "窗口或控件") + " → 需看截图确认当时的屏幕",
        "GEN1": lambda: "只有笼统报错" + _q(m) + " → 需看步骤日志和截图",
        "SCR1": lambda: "找不到元素或等待超时，没有弹框和业务报错 → 疑似定位失效，需看截图",
        "SCR2": lambda: "定位表达式写错 → 脚本问题",
        "SCR3": lambda: "测试代码运行错误 " + _s(c.get("exception")) + " → 脚本问题",
        "AST1": lambda: "断言期望值与实际值不同 → 疑似产品缺陷，需确认期望值没有过时",
        "AST2": lambda: "断言失败但没有期望值和实际值 → 需看日志",
        "NONE": lambda: "没有规则能解释这个报错 → 需人工判断",
        "OBS-OK": lambda: "人工看截图：页面正常、控件在屏幕上 → 脚本没找到它，定位需要修改",
        "OBS-POP": lambda: "截图中有弹窗挡在前面 → 弹窗干扰（文字待补充）",
        "OBS-POPN": lambda: "截图中的弹窗" + _q(hit) + "在干扰清单中 → 弹窗干扰",
        "OBS-POPU": lambda: "截图中有弹窗" + _q(obs_text) + "，不在任何清单中 → 需判断是干扰还是系统报错",
        "OBS-BLANK": lambda: "截图中页面没有正常显示 → 疑似产品问题，需确认能否重现",
        "OBS-OTHER": lambda: "截图中停在别的窗口/页面，上一步没生效 → 先重跑确认",
        "OBS-DIS": lambda: "截图中控件是灰色不可用 → 需判断是数据、步骤还是系统问题",
        "OBS-DESK": lambda: "截图是锁屏/黑屏/断开画面 → 执行机桌面不可用，环境问题",
    }
    s = B[a["rule"]]() if a["rule"] in B else (a["why"][0] if a["why"] else "")
    if a.get("phase") == "verify":
        s += "（业务已提交成功，失败发生在结果校验）"
    fl = a["flags"]
    if "环境中断边界" in fl:
        s += "；紧挨环境中断的起点，建议先重跑"
    if "有残留窗口" in fl:
        s += "；屏幕上有前面用例留下的窗口"
    if "重跑仍失败" in fl:
        s += "；重跑仍失败，问题必现"
    if "重跑报错不同" in fl:
        s += "；重跑失败但报错不同，第2次单独分析"
    if "重跑通过" in fl:
        s += "；重跑已通过（偶发），不提单"
    return s


def cross_case(cases, rules):
    runs = {}
    for c in cases:
        runs.setdefault(c.get("run"), []).append(c)
    for lst in runs.values():
        lst.sort(key=lambda x: x["seq"])
        is_env = lambda c: c.get("failed") and c.get("auto") and c["auto"]["cat"] == "ENVIRONMENT" and c["auto"]["status"] == "confirmed"
        k = len(lst)
        while k > 0 and is_env(lst[k - 1]):
            k -= 1
        tail_n = len(lst) - k
        if tail_n >= (rules.get("mass_min_cases") or 5):
            start_c = lst[k]
            for c in lst[k:]:
                c["auto"]["why"].append("从第 " + str(start_c["seq"]) + " 个用例（" + _s(start_c["id"]) + "）起，后面连续 " + str(tail_n) + " 个用例都因环境原因失败，直到运行结束：环境在这之前中断后没有恢复")
            prev = lst[k - 1] if k > 0 else None
            if prev and prev.get("failed") and prev.get("auto"):
                prev["auto"]["flags"].append("环境中断边界")
                prev["auto"]["need"].insert(0, "这个用例紧挨着环境中断的起点（第 " + str(start_c["seq"]) + " 个用例起全部因环境失败），它的失败可能也受环境影响：先重跑，再判断")
                if prev["auto"]["cat"] != "ENVIRONMENT" and not prev["auto"].get("reason"):
                    prev["auto"]["reason"] = "env_boundary"
        for c in [x for x in lst if x.get("failed") and x.get("auto")]:
            L = c.get("L")
            if L and L["shotFailed"]:
                c["auto"]["flags"].append("失败时截图失败")
                c["auto"]["need"].append("失败处理时截图失败（screen grab failed），这说明当时桌面已不可用；报告里如果显示了截图，那不是这个用例失败时的画面")
            if c["auto"]["cat"] == "ENVIRONMENT" and c["auto"]["hits"] and c["auto"]["hits"][0]:
                seen = [x for x in lst if not x.get("failed") and find_any(_s(x.get("error")) + "\n" + _s(x.get("stack")), [c["auto"]["hits"][0]])]
                if seen:
                    c["auto"]["why"].append("同样的报错也出现在本次通过的用例日志中：" + "、".join(_s(x["id"]) for x in seen[:5]) + "（那些用例没有因此失败），说明这段时间环境本身不稳定")
            if L and L["screen"] and c["auto"]["cat"] != "ENVIRONMENT":
                ok_same = [x for x in lst if not x.get("failed") and x.get("L") and x["L"]["screen"] == L["screen"]]
                if ok_same:
                    c["auto"]["need"].append("同一功能“" + L["screen"] + "”在本次运行中有通过的用例（" + "、".join(_s(x["id"]) for x in ok_same[:5]) + "），对比两者的测试数据和参数，差异处就是重点怀疑对象")
            if L and L["windows"]:
                others = [w for w in L["windows"] if not re.search(r"^WindowsForms|Main Menu", w, re.I) and w != L["expectWin"]]
                if others:
                    cnt = {}
                    for w in others:
                        cnt[w] = cnt.get(w, 0) + 1
                    c["auto"]["flags"].append("有残留窗口")
                    c["auto"]["why"].append("找不到目标窗口时，屏幕上还开着其他功能的窗口：" + "、".join(w + (" ×" + str(n) if n > 1 else "") for w, n in cnt.items()) +
                                            "（" + _s(ev_id(c["auto"]["ev"], "win")) + "）：前面的用例失败后没有关闭窗口")


# ======================= 截图文字识别结果（识别截图.bat 生成的 .ocr.json） =======================
# 与页面 engine.js 的 ocrLines / ocrText 相同：英文识别结果为主，中文结果只补充含中文的行
CJK = re.compile(r"[㐀-鿿豈-﫿]")


def ocr_lines(o):
    langs = (o or {}).get("langs") or []
    if not langs:
        return []
    en = next((l for l in langs if re.match(r"^en", l.get("lang") or "", re.I)), None)
    zh = next((l for l in langs if re.match(r"^zh", l.get("lang") or "", re.I)), None)
    base = list((en or langs[0] or {}).get("lines") or [])
    if zh and zh is not en:
        base += [l for l in zh.get("lines") or [] if CJK.search(l.get("t") or "")]
    if not en and not zh:
        for x in langs[1:]:
            base += x.get("lines") or []
    return sorted(base, key=lambda l: (l["b"][1], l["b"][0]))


def ocr_text(ocrs) -> str:
    parts = ["\n".join(re.sub(r"(?<=[㐀-鿿]) (?=[㐀-鿿])", "", l.get("t") or "") for l in ocr_lines(o)) for o in ocrs if o]
    return "\n".join(p for p in parts if p)[:4000]


def load_ocr_index(paths) -> dict:
    """读取一个或多个 .ocr.json，按截图指纹（sha256）和文件名建索引；重名的文件不按文件名对应。"""
    by_sha, by_name, dup = {}, {}, set()
    for p in paths or []:
        data = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        if data.get("tool") != "ta-ocr":
            raise ValueError(f"{p} 不是「识别截图.bat」生成的识别结果文件")
        for im in data.get("images") or []:
            if not im.get("langs"):
                continue
            if im.get("sha256"):
                by_sha[im["sha256"].lower()] = im
            n = re.split(r"[\\/]", im.get("name") or "")[-1].lower()
            if n:
                if n in by_name and by_name[n] is not im:
                    dup.add(n)
                by_name[n] = im
    for n in dup:
        by_name.pop(n, None)
    return {"bySha": by_sha, "byName": by_name}


def ocr_for_files(files, index) -> str:
    """按截图文件找识别结果：先按指纹，再按文件名。"""
    import hashlib
    found = []
    for f in files or []:
        o = None
        try:
            o = index["bySha"].get(hashlib.sha256(Path(f).read_bytes()).hexdigest())
        except OSError:
            pass
        o = o or index["byName"].get(re.split(r"[\\/]", str(f))[-1].lower())
        if o and o not in found:
            found.append(o)
    return ocr_text(found)


# ======================= 工作文件（页面“保存工作文件 / 打开工作文件”与 skill 共用） =======================
# {"tool": "ta-workspace", "v": 1, "saved_at", "saved_by": "page" | "skill", "masked": true,
#  "rules": {...}, "runs": [{id, name, total, at}], "cases": [页面用例字段 + 人工记录 + analysis]}
WS_INPUT_FIELDS = ("uid", "run", "seq", "id", "name", "result", "failed", "error", "stack", "exceptionRaw", "pageText",
                   "screenshot", "start", "duration", "module", "device", "parent", "attempt")
WS_HUMAN_FIELDS = ("obs", "ocrText", "dataCheck", "dataNote", "override", "rerun", "rerunNote", "r2")
WS_TEXT_FIELDS = ("name", "error", "stack", "pageText", "ocrText", "dataNote", "rerunNote")


def read_workspace(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("tool") != "ta-workspace":
        raise ValueError(f"{path} 不是工作文件（页面“保存工作文件”或 skill 生成的 workspace.json）")
    return data


def write_workspace(path, runs, cases, rules, mask=None):
    """写工作文件。mask：脱敏函数，写出前对所有文字字段脱敏（必须打码后才能交给模型）。"""
    from datetime import datetime as _dt
    m = mask or (lambda s: s)
    out = []
    for c in cases:
        o = {k: c[k] for k in WS_INPUT_FIELDS + WS_HUMAN_FIELDS if c.get(k) not in (None, "")}
        for k in WS_TEXT_FIELDS:
            if o.get(k):
                o[k] = m(o[k])
        if (o.get("obs") or {}).get("text"):
            o["obs"] = dict(o["obs"], text=m(o["obs"]["text"]))
        if (o.get("r2") or {}).get("error"):
            o["r2"] = dict(o["r2"], error=m(o["r2"]["error"]))
        if c.get("failed") and c.get("auto"):
            o["analysis"] = mask_deep(result_of(c), m)
        out.append(o)
    doc = {"tool": "ta-workspace", "v": 1, "saved_at": _dt.now().isoformat(timespec="seconds"), "saved_by": "skill",
           "masked": mask is not None, "rules": rules, "runs": runs, "cases": out}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def mask_deep(x, m):
    if isinstance(x, str):
        return m(x)
    if isinstance(x, list):
        return [mask_deep(v, m) for v in x]
    if isinstance(x, dict):
        return {k: mask_deep(v, m) for k, v in x.items()}
    return x


def result_of(c) -> dict:
    """一个失败用例的判断结果（写进文件用；与页面“导出工作文件”里的 result 字段相同）。"""
    a = c["auto"]
    return {"category": c["final"], "auto_category": a["cat"], "status": a["status"], "rule_id": a["rule"], "rule_name": rule_name(c),
            "brief": a.get("brief", ""), "why": a["why"], "need": a["need"], "flags": a["flags"], "reason_code": a.get("reason"),
            "check_kind": a.get("checkKind"), "phase": a.get("phase"), "from_ocr": bool(a.get("ocr")),
            "evidence": [{k: e[k] for k in ("id", "kind", "label", "text")} for e in a["ev"]],
            "rerun_plan": {"advice": c["plan"]["b"], "reason": c["plan"]["why"]}, "signature": c.get("sig")}
