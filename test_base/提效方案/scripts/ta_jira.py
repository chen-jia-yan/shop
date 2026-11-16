"""Jira：起草（一个失败用例一张单）、提交前检查、导出 CSV、提交到 Jira。

起草的内容全部来自分析结果和原文，不调用 AI。提交只在页面上人工审核通过之后进行。
提交用本机环境变量里的账号：JIRA_BASE_URL、JIRA_EMAIL（Cloud 需要）、JIRA_API_TOKEN。账号和 Token 不写进任何文件。
团队共用的字段配置在 config/jira.json。
"""
from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

import ta_engine as E

OLD_TPL = "[{system} Regression] {market} - {module} {cases} failed due to {cause}"
DEFAULT_CFG = {
    "deploy": "cloud", "baseUrl": "", "project": "ROTQA", "issueType": "Bug", "issueTypeEnv": "Task",
    "system": "NBS", "systemField": "", "market": "HK", "components": "SYSTEM-QA", "labels": "regression, auto-triage",
    "envMode": "field", "titleTpl": "[{system} Regression] {market} - {module} {case} failed due to {cause}",
    "descTpl": "{env} {system} - {module} encounter {problem} when {action}. Could you help to check? Thanks!",
    "highKeywords": ["issue", "underwriting", "核保", "payment", "支付", "premium", "保费", "amount", "金额", "quotation", "报价"],
    "draftCats": ["PRODUCT_DEFECT", "NEEDS_HUMAN"], "rerunUrl": "", "maskOnExport": True,
}
FIELD_NAMES = {"summary": "Summary", "issueType": "Issue Type", "priority": "Priority", "system": "System", "components": "Components",
               "labels": "Labels", "assignee": "Assignee", "environment": "Environment", "data": "Test Data", "desc": "Description"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_cfg(path: Path) -> dict:
    try:
        c = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        c = {}
    c = {**DEFAULT_CFG, **{k: v for k, v in c.items() if not k.startswith("_")}}
    if c["titleTpl"] == OLD_TPL:
        c["titleTpl"] = DEFAULT_CFG["titleTpl"]
    c["draftCats"] = [k for k in c.get("draftCats") or [] if k in E.CATS]
    if os.environ.get("JIRA_BASE_URL") and not c.get("baseUrl"):
        c["baseUrl"] = os.environ["JIRA_BASE_URL"]
    return c


def save_cfg(path: Path, cfg: dict) -> dict:
    c = {k: cfg.get(k, v) for k, v in DEFAULT_CFG.items()}
    for k, v in DEFAULT_CFG.items():
        if isinstance(v, list) and isinstance(c[k], str):
            c[k] = [s.strip() for s in re.split(r"[,，]", c[k]) if s.strip()]
        if isinstance(v, bool):
            c[k] = bool(c[k])
    bad = [k for k in ("token", "password", "apiToken", "api_token") if k in cfg]
    if bad:
        raise ValueError("Jira 账号和 Token 不能写进配置文件，请放在环境变量 JIRA_API_TOKEN")
    Path(path).write_text(json.dumps({"_说明": "团队共用的 Jira 字段配置。账号和 Token 只放环境变量：JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN", **c}, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


# ============================================================ 个人信息检查（提交前）
PII = [
    ("<HKID>", re.compile(r"\b[A-Z]{1,2}\d{6}\s?\(?[0-9A]\)?(?![0-9])")),
    ("<CN_ID>", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("<MO_ID>", re.compile(r"(?<!\d)[157]\d{6}\(\d\)")),
    ("<EMAIL>", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("<PHONE>", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("<PHONE>", re.compile(r"\+85[23][\s-]?[2-9]\d{3}[\s-]?\d{4}(?!\d)")),
]
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
LABEL_PHONE = re.compile(r"((?:tel|phone|mobile|contact|電話|电话|手機|手机|聯絡|联系)[^0-9\n]{0,12})([2-9]\d{3}[\s-]?\d{4})(?!\d)", re.I)


def luhn(d: str) -> bool:
    t, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        t += n
        alt = not alt
    return t % 10 == 0


def mask(text):
    if not text:
        return text
    s = CARD.sub(lambda m: "<CARD>" if luhn(re.sub(r"\D", "", m.group(0))) else m.group(0), str(text))
    for r, rx in PII:
        s = rx.sub(r, s)
    return LABEL_PHONE.sub(r"\1<PHONE>", s)


# ============================================================ 英文短句
CAT_EN = {"ENVIRONMENT": "Environment issue", "POPUP_INTERFERENCE": "Popup interference", "SCRIPT_ISSUE": "Test script issue", "TEST_DATA": "Test data issue",
          "PRODUCT_DEFECT": "Suspected product defect", "NEEDS_HUMAN": "Needs manual analysis"}
CHECK_EN = {"ok": "data exists and is in the expected state", "missing": "data does not exist", "used": "data has already been used", "invalid": "data state does not meet the test precondition",
            "lock_prev": "locked by an earlier failed case in the same run (not released)", "lock_other": "locked by another user or run", "lock_unknown": "lock owner not found",
            "cfg_missing": "the configuration should exist but is missing in the test environment", "cfg_ok": "the configuration is correct but the system still fails",
            "cfg_unsupported": "the scenario is not supported (test precondition invalid)", "dtp_out": "the date is outside the allowed range", "dtp_in": "the date is within range but still cannot be set"}
_s = E._s


def _ws(s):
    return re.sub(r"\s+", " ", _s(s))


def english(c) -> dict:
    a, L = c["auto"], c.get("L") or {}
    hit = a["hits"][0] if a["hits"] else ""
    m = ((L.get("root") or {}).get("msg") or "").split("\n")[0][:160]
    fn = L["rootAt"]["func"] if L.get("rootAt") else ""
    o = c.get("obs") or {}
    sysT = _ws(o.get("text") or (a.get("ocr") and hit) or next((x for x in L.get("sysMsgs") or [] if x), "") or c.get("pageText") or c.get("alertText") or hit)[:120]
    chk = " Manual check: " + CHECK_EN.get(c["dataCheck"], c["dataCheck"]) + (" (" + c["dataNote"] + ")" if c.get("dataNote") else "") + "." if c.get("dataCheck") else ""
    exc, ew = _s(c.get("exception")), L.get("expectWin") or ""
    T = {
        "ENV1": ["The browser/device session could not be created (" + exc + ").", "Check the execution machine and driver, then rerun."],
        "ENV-DESK": ["The execution machine had no interactive desktop (\"" + _s(hit) + "\"), so the automation could not move the mouse or type. This usually happens when the remote desktop session is minimized, disconnected or locked.", "Environment owner to confirm the session state of the execution machine during the run; rerun after it is fixed."],
        "ENV2": ["Connection/service failure: \"" + _s(hit) + "\". The application lost its connection to the backend/database.", "Environment owner to confirm the database/service status at that time; rerun."],
        "ENV3": ["The same error occurred in many consecutive cases in this run.", "Confirm whether the environment was unstable at that time."],
        "SYS-EMPTY": ["A popup appeared after submission, but the script could not read its text.", "Check the screenshot to identify the popup."],
        "DATA-LOCK": ["The system reported \"" + sysT + "\": the policy/contract was locked by another session.", "Find and release the lock, then rerun."],
        "CHK-LOCK1": ["The policy was locked by an earlier failed case in the same run that did not release it.", "Fix the cleanup step of the earlier case."],
        "SYS-CFG": ["The system reported \"" + sysT + "\": a configuration is missing.", "Dev/config owner to confirm whether this configuration should exist in the test environment."],
        "CHK-CFG": ["The system reported \"" + sysT + "\".", "See manual check result."],
        "SYS-CRASH": ["The application showed an unhandled exception dialog.", "Capture the exception details and confirm whether it is reproducible."],
        "POP1": ["An unrelated dialog (\"" + _s(hit) + "\") blocked the test.", "Add handling for this dialog in the test script."],
        "POP1-未知": ["An unexpected dialog appeared.", "Identify whether the dialog is expected."],
        "BIZ1": ["The system returned \"" + sysT + "\" and the test data was found to be invalid.", "Fix the test data and rerun."],
        "BIZ2": ["The system returned \"" + sysT + "\" although the test data was verified to be correct.", "Dev to investigate."],
        "BIZ3": ["The system returned \"" + sysT + "\".", "Check the test data to distinguish a data issue from a system issue."],
        "POP2": ["A popup (\"" + _s(hit) + "\") blocked the operation.", "Add handling for this popup."],
        "POP3": ["The click was intercepted by an overlay element.", "Check the screenshot to identify the overlay."],
        "POP3-弱": ["The click was intercepted by another element.", "Check the screenshot to identify the element."],
        "MASK1": ["\"" + m + "\" at " + (fn or "the failing function") + ": a previous lookup returned no control/data (False/None) and the script continued, so the real cause is hidden.", "Check which control/data the lookup at this line was looking for; check the screenshot."],
        "DSK-AMB": ["The locator matched multiple controls (ElementAmbiguousError) at " + fn + ".", "Make the locator more specific; check for windows left open by earlier cases."],
        "DSK-OPT": ["The dropdown does not contain the option " + _s(hit) + ".", "Confirm the actual option name in the application."],
        "DSK-DTP": ["Failed to set the date in the Date Time Picker at " + fn + ".", "Confirm the date value and the allowed range."],
        "CHK-DTP": ["Failed to set the date in the Date Time Picker at " + fn + ".", "See manual check result."],
        "DSK-DIS": ["The control to operate was disabled (ElementNotEnabled) at " + fn + ".", "Check the screenshot to see why the control was disabled."],
        "DSK-VIS": ["The control exists but is not visible (ElementNotVisible) at " + fn + ".", "Check whether the right tab/section was opened."],
        "DSK-NF": ["Could not find " + ("the window \"" + ew + "\"" if ew else "the window/control") + (" at " + fn if fn else "") + ".", "Check the screenshot to see what was on screen; rerun."],
        "GEN1": ["Generic error: \"" + m + "\".", "Check the step log and screenshot for the actual system message."],
        "SCR1": ["Element not found / wait timeout (" + exc + ").", "Check the screenshot to confirm whether the locator is outdated."],
        "SCR2": ["Invalid locator.", "Fix the locator."],
        "SCR3": ["Test code error (" + exc + ").", "Fix the test code."],
        "AST1": ["Assertion failed with different expected and actual values.", "Confirm the expected value is still valid."],
        "AST2": ["Assertion failed without expected/actual values.", "Check the log."],
        "NONE": ["No rule matched this error.", "Manual analysis needed."],
        "OBS-OK": ["The screenshot shows the page loaded normally and the target control is on screen, but the script could not find/operate it.", "Fix the locator in the test script."],
        "OBS-POP": ["The screenshot shows a popup blocking the screen.", "Identify the popup and add handling for it."],
        "OBS-POPN": ["The screenshot shows an unrelated popup (\"" + _s(hit) + "\") blocking the test.", "Add handling for this popup in the test script."],
        "OBS-POPU": ["The screenshot shows an unexpected popup" + (" (\"" + _ws(o["text"])[:100] + "\")" if o.get("text") else "") + ".", "Confirm whether this popup is expected."],
        "OBS-BLANK": ["The screenshot shows the page was not displayed correctly (blank, error page or loading).", "Check whether it is reproducible manually."],
        "OBS-OTHER": ["The screenshot shows the screen stayed on another window/page; the previous step did not take effect.", "Rerun and check the previous step."],
        "OBS-DIS": ["The screenshot shows the control to operate was disabled.", "Check whether the test data meets the business rule."],
        "OBS-DESK": ["The screenshot shows a locked/black/disconnected desktop on the execution machine.", "Environment owner to check the execution machine session; rerun."],
    }
    if a.get("custom"):
        t = ["Matched team rule " + _s(a.get("ruleName")) + " (\"" + _ws(hit)[:100] + "\").", "See the rule note."]
    else:
        t = T.get(a["rule"], ["See the error log.", "Manual analysis needed."])
    basis = t[0] + chk
    if a.get("phase") == "verify":
        basis += " The business transaction had already been submitted successfully; the failure occurred during result verification."
    if c.get("override"):
        basis = "Reviewer conclusion: " + _s(c["override"].get("reason")) + " (" + CAT_EN[c["override"]["cat"]] + ")"
    return {"cat": CAT_EN[c["final"]], "status": "confirmed by reviewer" if c.get("override") else "confirmed by rule" if a["status"] == "confirmed" else "to be confirmed",
            "basis": basis, "next": t[1]}


GENERIC_FN = re.compile(r"^(_|test|setup|teardown|click|double_?click|input|type|send|set|get|find|wait|select|check|assert|win_|wait_|find_|click_|input_|set_|get_|select_|save_img|screenshot|main|run|execute|step)", re.I)
VERB = re.compile(r"^(search|add|create|submit|open|close|select|input|enter|save|approve|issue|cancel|terminate|reinstate|update|delete|check|verify|query|print|run|process|calculate|apply|pay|surrender|transfer|change|login|log in|logout|upload|download|generate|register|renew|assign|reject|confirm|edit|modify|view|import|export|send|book|post|reverse|withdraw|claim|endorse|lapse)\b")


def humanize(s) -> str:
    s = re.sub(r"^test_?\d*_?", "", _s(s), flags=re.I)
    s = re.sub(r"^TC_", "", s, flags=re.I)
    s = re.sub(r"^(las|nbs|win|app|ui|web|fwd)_", "", s, flags=re.I)
    s = re.sub(r"_\d+$", "", s)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"[_\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def feature_of(c) -> str:
    raw = _s(c.get("name") or (c.get("L") or {}).get("testFn") or "")
    h = humanize(re.sub(r"^test_?\d*_?(TC_)?(LAS|NBS|UL|HK)?_?", "", raw, flags=re.I))
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), h)


def _cut(s, n):
    s = _ws(s).strip()
    return s[:n - 1] + "…" if len(s) > n else s


def jira_phrase(c) -> dict:
    a, L = c["auto"], c.get("L") or {}
    hit = _ws(a["hits"][0] if a["hits"] else "").strip()
    o = c.get("obs") or {}
    sys_ = o.get("text") or (a.get("ocr") and (a["hits"][0] if a["hits"] else "")) or next((x for x in L.get("sysMsgs") or [] if x), "") or c.get("pageText") or c.get("alertText") or ""
    first = next((x for x in ((L.get("root") or {}).get("msg") or c.get("error") or c.get("stack") or "").split("\n") if x.strip()), "")
    ew, exc = L.get("expectWin") or "", _s(c.get("exception"))
    P = {
        "SYS-EMPTY": "a popup whose text could not be captured", "ENV1": "browser/device session error", "ENV-DESK": 'the "no active desktop" error',
        "ENV2": 'the connection error "' + _cut(hit, 80) + '"', "ENV3": "the same error in many cases",
        "DSK-NF": 'the "' + _cut(ew, 60) + '" window not found error' if ew else "the window/control not found error", "DSK-AMB": "the multiple matched controls error",
        "DSK-DIS": "a disabled control", "DSK-VIS": "an invisible control", "DSK-OPT": "the missing dropdown option " + _cut(hit, 60), "DSK-DTP": "the date setting error", "CHK-DTP": "the date setting error",
        "SCR1": "the element not found error", "SCR2": "an invalid locator", "SCR3": "a test code error (" + exc + ")",
        "AST1": "an assertion failure (expected and actual values are different)", "AST2": "an assertion failure",
        "OBS-BLANK": "a blank/error page", "OBS-OTHER": "the wrong window/page", "OBS-DIS": "a disabled control", "OBS-DESK": "a locked/disconnected desktop", "OBS-OK": "the element not found error",
    }
    if sys_ and re.match(r"^(SYS|DATA|CHK-LOCK|CHK-CFG|BIZ|POP1|POP2|OBS-POP)", a["rule"]):
        problem = 'the popup error "' + _cut(sys_, 100) + '"'
    elif re.match(r"^BIZ", a["rule"]) or (a.get("custom") and hit):
        problem = 'the "' + _cut(hit, 80) + '" error'
    else:
        problem = P.get(a["rule"]) or ('the error "' + _cut(first, 90) + '"' if first else "an error")
    fns = [f for f in (p.split("（")[0] for p in L.get("path") or []) if not GENERIC_FN.search(f) and humanize(f)]
    act = humanize(fns[-1]) if fns else ""
    feat = feature_of(c)
    action = (act if VERB.search(act) else "processing " + act) if act else ("running " + feat if feat else "running the case")
    short = re.split(r"(?<=\.)\s", english(c)["basis"])[0]
    return {"problem": problem, "action": action, "shortEn": short}


def test_data(c) -> dict:
    t = "\n".join(x for x in [c.get("error"), c.get("stack")] if x)
    out = {}
    for m in re.finditer(r"\b(agent\s*code|agent\s*no|policy\s*(?:no|number)|contract\s*(?:no|number)|product\s*code|plan\s*code|application\s*no)\b\s*[:：=]?\s*[\"']?([A-Z0-9][A-Z0-9\-]{2,19})\b", t, re.I):
        k = re.sub(r"\s+", " ", m.group(1)).lower()
        if k not in out and re.search(r"\d", m.group(2)):
            out[k] = m.group(2)
    return out


# ============================================================ 起草
EXC_EN = {"NoSuchElementException": "element not found", "TimeoutException": "page element wait timeout", "StaleElementReferenceException": "stale element reference",
          "ElementNotInteractableException": "element not interactable", "ElementClickInterceptedException": "click intercepted by another element",
          "InvalidSelectorException": "invalid element locator", "SessionNotCreatedException": "browser session could not be created"}


def _words(s):
    return " ".join(_ws(s).strip().split(" ")[:12])


def _first_line(c):
    return next((x for x in (c.get("error") or c.get("stack") or "").split("\n") if x.strip()), "")


def cause_phrase(c) -> dict:
    a, cat, L = c["auto"], c["final"], c.get("L") or {}
    hit = a["hits"][0] if a["hits"] else ""
    fn = " in " + L["rootAt"]["func"] if L.get("rootAt") else ""
    sys_ = (c.get("obs") or {}).get("text") or next((x for x in L.get("sysMsgs") or [] if x), "") or ""
    if (re.match(r"^BIZ", a["rule"]) or a.get("custom")) and hit:
        src = "\n".join(x for x in [c.get("pageText"), c.get("alertText"), sys_, c.get("error")] if x)
        line = next((l for l in src.split("\n") if _s(hit).lower() in l.lower()), hit)
        return {"text": _words(line).lower(), "sure": True}
    if sys_ and re.match(r"^(SYS|DATA|CHK-LOCK|CHK-CFG|OBS-POP)", a["rule"]):
        return {"text": 'popup error "' + _words(sys_) + '"', "sure": True}
    if cat == "ENVIRONMENT":
        return {"text": "test environment error (" + _words(hit or c.get("exception") or "unknown") + ")", "sure": bool(hit)}
    if cat == "POPUP_INTERFERENCE":
        return {"text": "unexpected popup" + (' "' + _words(hit) + '"' if hit else ""), "sure": bool(hit)}
    if c.get("exception") in EXC_EN:
        return {"text": EXC_EN[c["exception"]], "sure": False}
    if re.match(r"^AST", a["rule"]):
        return {"text": "assertion failed - " + _words(re.sub(r"^[\w.]*(Error|Exception|Failure)\s*:?\s*", "", _first_line(c))), "sure": False}
    ew = L.get("expectWin") or ""
    R = {"DSK-AMB": "locator matched multiple controls" + fn, "DSK-NF": ('window "' + _words(ew) + '" not found' if ew else "window/control not found") + fn,
         "DSK-VIS": "control not visible" + fn, "DSK-DIS": "control disabled" + fn, "DSK-OPT": "dropdown option not found (" + _words(hit) + ")",
         "DSK-DTP": "date picker value could not be set" + fn, "CHK-DTP": "date picker value could not be set" + fn,
         "MASK1": "control/data lookup returned empty" + fn, "GEN1": "generic error" + fn, "SYS-EMPTY": "unreadable popup after submission", "SYS-CRASH": "application unhandled exception",
         "SCR2": "invalid locator", "SCR3": "test code error (" + _s(c.get("exception")) + ")" + fn, "OBS-OK": "element not found although the page is displayed" + fn,
         "OBS-BLANK": "page not displayed correctly", "OBS-OTHER": "previous step did not take effect" + fn, "OBS-DIS": "control disabled" + fn, "OBS-DESK": "execution machine desktop unavailable"}
    if a["rule"] in R:
        return {"text": R[a["rule"]], "sure": a["status"] == "confirmed" or bool(c.get("override"))}
    return {"text": "[cause TBD]", "sure": False}


def priority_of(c, cfg) -> dict:
    cat = c["final"]
    if cat == "PRODUCT_DEFECT":
        txt = " ".join(_s(c.get(k)) for k in ("name", "module", "error")).lower()
        kw = next((w for w in cfg["highKeywords"] if w.lower() in txt), None)
        return {"v": "High", "why": "产品问题，涉及“" + kw + "”（出单/核保/支付/金额类）"} if kw else {"v": "Medium", "why": "其他产品问题"}
    if cat in ("TEST_DATA", "SCRIPT_ISSUE", "POPUP_INTERFERENCE"):
        return {"v": "Low", "why": "测试数据 / 脚本 / 弹窗类问题"}
    return {"v": "Medium", "why": "默认"}


def _base(p):
    return re.split(r"[\\/]", _s(p))[-1].strip()


def shot_list(shots, path) -> list[str]:
    lst = [_base(s["name"]) for s in shots] if shots else [_base(x) for x in _s(path).split(";")]
    return [x for x in lst if x][:3]


def _fmt_t(t):
    return " (" + _s(t).replace("T", " ")[:16] + ")" if t else ""


def _imgs(lst):
    return " ".join("!" + n + "|thumbnail!" for n in lst)


def run_lines(c, case_of) -> list[str]:
    P, out = jira_phrase(c), []
    if c.get("parent"):
        p = case_of(c["parent"])
        out.append("*1st run*" + _fmt_t(p and p.get("start")) + ": " + (jira_phrase(p)["shortEn"] if p and p.get("auto") else "failed with a different error.") + (" (handled separately)" if p else ""))
        out.append("*2nd run (rerun)*" + _fmt_t(c.get("start")) + ": " + P["shortEn"])
        s = shot_list(c.get("shots"), c.get("screenshot"))
        if s:
            out.append(_imgs(s))
        return out
    out.append("*1st run*" + _fmt_t(c.get("start")) + ": " + P["shortEn"])
    s1 = shot_list(c.get("shots"), c.get("screenshot"))
    if s1:
        out.append(_imgs(s1))
    r2 = c.get("r2") or {}
    if c.get("rerun") == "fail" and r2.get("same") is not False:
        out.append("*2nd run (rerun)*" + _fmt_t(r2.get("start")) + ": Failed again with the same error. The issue is reproducible.")
        s2 = shot_list(c.get("shots2"), r2.get("screenshot"))
        if s2:
            out.append(_imgs(s2))
    elif c.get("rerun") == "fail":
        out.append("*2nd run (rerun)*: Failed with a different error, reported in a separate ticket.")
    return out


def script_fields(d, c, run, cfg, case_of) -> dict:
    if not c:
        return {}
    mod = c.get("module") or feature_of(c) or "Regression"
    cause, P, pr = cause_phrase(c), jira_phrase(c), priority_of(c, cfg)
    redundant = re.sub(r"^(processing|running) ", "", P["action"]) == mod.lower() or P["action"].startswith("running ")
    summary = (cfg["titleTpl"].replace("{system}", cfg["system"]).replace("{market}", cfg["market"]).replace("{module}", mod)
               .replace("{case}", _s(c["id"]) + (" (rerun)" if c.get("parent") else "")).replace("{cases}", "case").replace("{n}", "1").replace("{cause}", cause["text"]))
    summary = re.sub(r"\s+", " ", summary).strip()
    tpl = cfg["descTpl"].replace(" when {action}", "") if redundant else cfg["descTpl"]
    opening = (tpl.replace("{env}", run.get("env") or "").replace("{system}", cfg["system"]).replace("{market}", cfg["market"]).replace("{module}", mod)
               .replace("{case}", _s(c["id"])).replace("{problem}", P["problem"]).replace("{action}", P["action"]))
    opening = re.sub(r"^\s*-\s*", "", re.sub(r"\s+", " ", opening)).strip()
    chk = "I checked the test data: " + (CHECK_EN.get(c["dataCheck"]) or E.DATA_CHECK.get(c["dataCheck"], "")) + (" (" + c["dataNote"] + ")" if c.get("dataNote") else "") + "." if c.get("dataCheck") else ""
    environment = "\n".join(["Environment: " + (run.get("env") or "-"), "Device: " + (c.get("device") or run.get("device") or "-"), "Run: " + (run.get("name") or "-"),
                             "Test plan: " + (run.get("plan") or "-"), "Executed at: " + (c.get("start") or run.get("at") or "-") + " (UTC+8)"])
    sh = shot_list(c.get("shots"), c.get("screenshot")) + ([] if c.get("parent") else shot_list(c.get("shots2"), (c.get("r2") or {}).get("screenshot")))
    return {"summary": summary, "issueType": cfg["issueTypeEnv"] if c["final"] == "ENVIRONMENT" else cfg["issueType"], "priority": pr["v"], "system": cfg["system"],
            "components": cfg["components"], "labels": cfg["labels"], "assignee": "", "environment": environment,
            "desc": "\n".join(x for x in [opening, chk] if x) + "\n\n" + "\n".join(run_lines(c, case_of)),
            "data": "\n".join(k + ": " + v for k, v in test_data(c).items()),
            "_priorityWhy": pr["why"], "_causeSure": cause["sure"], "_attach": list(dict.fromkeys(sh))}


def apply_script(d, c, run, cfg, case_of, all_=False):
    """只覆盖仍是“脚本”来源的字段，人工改过的保留。"""
    sf = script_fields(d, c, run, cfg, case_of)
    for k in FIELD_NAMES:
        if all_ or d["src"].get(k, "脚本") == "脚本":
            d["f"][k] = sf.get(k, "")
            d["src"][k] = "脚本"
    d["meta"] = {"priorityWhy": sf.get("_priorityWhy"), "causeSure": sf.get("_causeSure"), "attach": sf.get("_attach") or []}


def new_draft(c, run, cfg, case_of) -> dict:
    d = {"id": "D" + base36(int(time.time() * 1000)) + uuid.uuid4().hex[:3], "v": 2, "run": c["run"], "cat": c["final"], "sig": c.get("sig"),
         "uids": [c["uid"]], "status": "draft", "mode": "create", "target": "", "f": {}, "src": {}, "created": now(), "history": []}
    apply_script(d, c, run, cfg, case_of, True)
    return d


def base36(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
    return s or "0"


def wiki(d, cfg) -> str:
    f = d["f"]
    if f.get("desc") is None:
        return "\n\n".join(f[k] for k in ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8") if f.get(k))
    data = (f.get("data") or "").strip()
    return ("{noformat}\n" + f["environment"] + "\n{noformat}\n\n" if cfg["envMode"] == "description" else "") + f["desc"] + \
        ("\n\n*Test data:*\n" + "\n".join("* " + l.strip() for l in data.split("\n") if l.strip()) if data else "")


# ============================================================ 检查
def dup_of(d, drafts, case_of):
    if d["mode"] == "create":
        hit = next((x for x in drafts if x is not d and x["status"] == "submitted" and x.get("issueKey") and x.get("sig") == d.get("sig") and x["cat"] == d["cat"]), None)
        if hit:
            return {"key": hit["issueKey"], "text": "可能重复：之前提交的 " + hit["issueKey"] + " 是同一原因。可以改为“追加评论到已有单”"}
    same = [x for x in drafts if x is not d and x["status"] not in ("discarded", "submitted") and x.get("sig") == d.get("sig") and x["cat"] == d["cat"]]
    if same:
        return {"key": "", "text": "同一原因还有 " + str(len(same)) + " 张草稿（" + "、".join(_s((case_of(x["uids"][0]) or {}).get("id")) for x in same[:5]) + "），提交前确认是否需要分别提单"}
    return None


def validate(d, c, drafts, case_of) -> dict:
    errs, warns, f = [], [], d["f"]
    if not c:
        errs.append("找不到这张单对应的用例（批次可能已删除）")
    if not f.get("summary", "").strip():
        errs.append("标题为空")
    if re.search(r"\{(system|market|module|case|cases|cause|n)\}", f.get("summary", "")):
        errs.append("标题里还有未替换的占位符")
    if len(f.get("summary", "")) > 255:
        errs.append("标题超过 255 个字符（" + str(len(f["summary"])) + "）")
    if "[cause TBD]" in f.get("summary", ""):
        errs.append("标题中的原因还是“[cause TBD]”（待确认），请写明原因")
    if re.search(r"\{(env|system|module|problem|action|case)\}", f.get("desc") or ""):
        errs.append("描述里还有未替换的占位符")
    if d["mode"] == "comment" and not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", d.get("target", "").strip()):
        errs.append("追加评论需要填写正确的单号，例如 ROTQA-5339")
    txt = "\n".join(_s(f.get(k)) for k in ("summary", "environment", "desc", "data"))
    if mask(txt) != txt:
        errs.append("内容中有疑似个人信息（证件号、手机号、邮箱、卡号）")
    if c and not c.get("override") and c["auto"]["status"] == "suspected" and not d.get("ack"):
        warns.append({"k": "sus", "t": "这个用例的分类还是“待复核”（" + c["auto"]["brief"] + "）"})
    meta = d.get("meta") or {}
    if meta and not meta.get("causeSure") and d["src"].get("summary") == "脚本":
        warns.append({"t": "标题中的原因由异常类型推出，不一定是真正原因，请对照证据修改"})
    if c and not meta.get("attach"):
        warns.append({"t": "没有截图。可以在用例详情里粘贴截图，再点“按最新分诊刷新”"})
    dup = dup_of(d, drafts, case_of)
    if dup:
        warns.append({"t": dup["text"]})
    if not f.get("assignee"):
        warns.append({"t": "没有填写 Assignee（经办人），提交后需在 Jira 里指派"})
    return {"errs": errs, "warns": warns, "ok": not errs and not any(w.get("k") == "sus" for w in warns)}


# ============================================================ 导出、提交
def labels_of(d) -> list[str]:
    lst = [x for x in re.split(r"[,，\s]+", d["f"].get("labels") or "") if x] + ["triage-" + d["id"]]
    return [re.sub(r"\s+", "-", x) for x in dict.fromkeys(lst)]


def comps(d) -> list[str]:
    return [x.strip() for x in re.split(r"[,，]", d["f"].get("components") or "") if x.strip()]


def payload(d, cfg, cases, run) -> dict:
    mk = mask if cfg["maskOnExport"] else (lambda s: s)
    f = d["f"]
    fields = {"project": {"key": cfg["project"]}, "issuetype": {"name": f["issueType"]}, "summary": mk(f["summary"]), "priority": {"name": f["priority"]},
              "labels": labels_of(d), "components": [{"name": n} for n in comps(d)], "description": mk(wiki(d, cfg))}
    if cfg["envMode"] == "field":
        fields["environment"] = mk(f["environment"])
    if cfg.get("systemField"):
        fields[cfg["systemField"]] = {"value": f["system"]}
    if f.get("assignee"):
        fields["assignee"] = {"accountId": f["assignee"]} if cfg["deploy"] == "cloud" else {"name": f["assignee"]}
    c = cases[0] if cases else {}
    pool = (c.get("shots") or []) + (c.get("shots2") or [])
    return {"draftId": d["id"], "mode": d["mode"], "target": d.get("target") if d["mode"] == "comment" else None, "idempotencyLabel": "triage-" + d["id"],
            "fields": fields if d["mode"] == "create" else None,
            "comment": mk("h4. Automated regression " + _s(run.get("name")) + ": occurred again in " + _s(c.get("id")) + "\n\n" + wiki(d, cfg)) if d["mode"] == "comment" else None,
            "attachments": [{"fileName": n, "file": next((s.get("file") for s in pool if _base(s["name"]) == n), None)} for n in (d.get("meta") or {}).get("attach") or []],
            "cases": [{"id": x["id"], "name": x.get("name"), "category": x["final"], "rule": "人工" if x.get("override") else x["auto"]["rule"], "attempt": 2 if x.get("parent") else 1} for x in cases],
            "reviewer": d.get("reviewer"), "reviewedAt": d.get("reviewedAt")}


def to_csv(rows) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    return "﻿" + buf.getvalue()


def jira_csv(lst, cfg) -> str:
    mk = mask if cfg["maskOnExport"] else (lambda s: s)
    max_l = max([1] + [len(labels_of(d)) for d in lst])
    max_c = max([1] + [len(comps(d)) for d in lst])
    env = cfg["envMode"] == "field"
    head = ["Summary", "Issue Type", "Priority"] + ["Component/s"] * max_c + ["Labels"] * max_l + (["Environment"] if env else []) + ["System", "Assignee", "Description", "Draft ID"]
    rows = [head]
    for d in lst:
        L, C, f = labels_of(d), comps(d), d["f"]
        rows.append([mk(f["summary"]), f["issueType"], f["priority"]] + [C[i] if i < len(C) else "" for i in range(max_c)] + [L[i] if i < len(L) else "" for i in range(max_l)] +
                    ([mk(f["environment"])] if env else []) + [f["system"], f["assignee"], mk(wiki(d, cfg)), d["id"]])
    return to_csv(rows)


class Jira:
    """最小的 Jira REST 客户端（只用 Python 自带的库）。Cloud 用邮箱 + API Token，Data Center 用个人访问令牌（PAT）。"""

    def __init__(self, cfg):
        self.base = (os.environ.get("JIRA_BASE_URL") or cfg.get("baseUrl") or "").rstrip("/")
        tok = os.environ.get("JIRA_API_TOKEN", "")
        if not self.base or not tok:
            raise RuntimeError("没有配置 Jira 账号：请在本机环境变量里设置 JIRA_BASE_URL、JIRA_API_TOKEN" + ("、JIRA_EMAIL" if cfg["deploy"] == "cloud" else "") + "，然后重新打开测试分析助手")
        if cfg["deploy"] == "cloud":
            em = os.environ.get("JIRA_EMAIL", "")
            if not em:
                raise RuntimeError("Jira Cloud 需要环境变量 JIRA_EMAIL")
            self.auth = "Basic " + base64.b64encode((em + ":" + tok).encode()).decode()
        else:
            self.auth = "Bearer " + tok

    def req(self, method, path, body=None, raw=None, ctype=None, extra=None):
        h = {"Authorization": self.auth, "Accept": "application/json", **(extra or {})}
        data = raw
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        elif ctype:
            h["Content-Type"] = ctype
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                t = resp.read().decode("utf-8", "replace")
                return json.loads(t) if t.strip() else {}
        except urllib.error.HTTPError as e:
            t = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(t)
                msg = "；".join(j.get("errorMessages") or []) + "；".join(k + ": " + v for k, v in (j.get("errors") or {}).items())
            except ValueError:
                msg = t[:300]
            raise RuntimeError("Jira 返回 " + str(e.code) + "：" + (msg or e.reason))
        except urllib.error.URLError as e:
            raise RuntimeError("连不上 Jira（" + str(e.reason) + "）")

    def search(self, jql, fields="summary,status", n=5):
        q = urllib.parse.urlencode({"jql": jql, "fields": fields, "maxResults": n})
        return self.req("GET", "/rest/api/2/search?" + q).get("issues") or []

    def attach(self, key, path: Path, name: str):
        b = uuid.uuid4().hex
        ct = mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = (("--" + b + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"" + name.replace('"', "") + "\"\r\nContent-Type: " + ct + "\r\n\r\n").encode("utf-8")
                + path.read_bytes() + ("\r\n--" + b + "--\r\n").encode())
        return self.req("POST", "/rest/api/2/issue/" + key + "/attachments", raw=body, ctype="multipart/form-data; boundary=" + b, extra={"X-Atlassian-Token": "no-check"})


def _jql_str(s):
    return '"' + re.sub(r'["\\]', " ", _s(s))[:80] + '"'


def submit(items: list[dict], cfg: dict, dry_run: bool, file_of) -> list[dict]:
    """items 是 payload()；file_of(文件名) → 截图的本机路径。预检只查重，不写入。"""
    j = Jira(cfg)
    out = []
    for p in items:
        r = {"draftId": p["draftId"]}
        try:
            done = j.search("labels = " + _jql_str(p["idempotencyLabel"]), n=1)
            if done:
                r.update(key=done[0]["key"], message="之前已经提交过（按草稿标签找到），没有重复建单")
                out.append(r)
                continue
            if p["mode"] == "create":
                cid = p["cases"][0]["id"] if p["cases"] else ""
                dup = j.search("project = " + _jql_str(cfg["project"]) + " AND statusCategory != Done AND summary ~ " + _jql_str(cid), n=3) if cid else []
                if dup:
                    r.update(duplicateOf=dup[0]["key"], duplicateSummary=dup[0]["fields"].get("summary", ""))
            else:
                j.req("GET", "/rest/api/2/issue/" + p["target"] + "?fields=summary")
            if dry_run:
                r["message"] = "可以提交" if not r.get("duplicateOf") else "有未关闭的单标题里有同一个用例编号"
                out.append(r)
                continue
            if p["mode"] == "create":
                key = j.req("POST", "/rest/api/2/issue", {"fields": p["fields"]})["key"]
            else:
                key = p["target"]
                j.req("POST", "/rest/api/2/issue/" + key + "/comment", {"body": p["comment"]})
            r["key"], bad = key, 0
            for a in p["attachments"]:
                f = file_of(a.get("file")) if a.get("file") else None
                if not f or not f.exists():
                    bad += 1
                    continue
                try:
                    j.attach(key, f, a["fileName"])
                except RuntimeError:
                    bad += 1
            r["attachmentsFailed"] = bad
            r["message"] = ("已建单 " if p["mode"] == "create" else "已追加评论到 ") + key + ("，" + str(bad) + " 个截图没有上传，请手动上传" if bad else "")
        except RuntimeError as e:
            r["error"] = str(e)
        out.append(r)
    return out


def send_rerun(url: str, run_name: str, ids: list[str]) -> str:
    r = urllib.request.Request(url, data=json.dumps({"run": run_name, "cases": ids}).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return "重跑接口返回 " + str(resp.status)
    except urllib.error.HTTPError as e:
        raise RuntimeError("重跑接口返回 " + str(e.code))
    except urllib.error.URLError as e:
        raise RuntimeError("连不上重跑接口（" + str(e.reason) + "）")
