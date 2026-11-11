"""第 3 步：按 references/taxonomy.md 的规则对失败用例分类。

用法：
    python scripts/classify_rules.py --failures triage_runs/<run_id>/failures.json \
        --rerun triage_runs/<run_id>/rerun.json --rules config/rules.yaml \
        --data-checks triage_runs/<run_id>/data_checks.yaml \
        --config config/config.yaml --out triage_runs/<run_id>/classified.json

输出：
- classified.json：每个用例的分类、规则编号、状态（confirmed / suspected）、证据编号、原因。
- data_checks.todo.yaml（与 out 同目录）：需要人工去数据库核查的数据清单。

本脚本只做确定性判断，不调用任何模型。同样的输入永远得到同样的输出。
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from common import (CATEGORIES, OWNERS, add_evidence, find_evidence, intercepting_element,
                    load_config, match_any, normalize_signature, now_iso, parse_time, read_json,
                    read_yaml, setup_logging, short_exception_name, write_json, write_yaml)
from log_parser import analyze_log, short_type

log = setup_logging()

DESK_PATTERN_RE = re.compile(r"SetCursorPos|active desktop|DESKTOP_UNAVAILABLE", re.I)
BACKEND_PATTERN_RE = re.compile(r"transport-level|forcibly closed|network-related|Timeout expired", re.I)

UI_BLOCKED_EXC = {"ElementClickInterceptedException", "ElementNotInteractableException",
                  "NoSuchElementException", "TimeoutException"}
DATA_KEYS = ("agent_code", "product_code", "policy_no", "proposal_no", "plan_code")
BAD_DATA_RESULTS = {"missing", "used", "invalid_state"}
ALERT_TEXT_RES = [
    re.compile(r"Alert Text:\s*(.+?)(?:\n|$)", re.I),
    re.compile(r"\{Alert text\s*:\s*(.+?)\}", re.I),
]


# ---------------------------------------------------------------- 辅助

def verdict(category, status, rule_id, reason, evidence_ids, needs_human_reason=None):
    return {
        "category": category,
        "category_cn": CATEGORIES[category],
        "status": status,
        "rule_id": rule_id,
        "owner": OWNERS[category],
        "reason": reason,
        "evidence_ids": [e for e in evidence_ids if e],
        "needs_human_reason": needs_human_reason,
    }


def alert_text_of(case: dict) -> str | None:
    pe = case.get("popup_evidence") or {}
    if pe.get("alert_text"):
        return pe["alert_text"]
    if short_exception_name(case.get("error_type")) == "UnexpectedAlertPresentException":
        for rx in ALERT_TEXT_RES:
            m = rx.search(case.get("error_message") or "")
            if m:
                return m.group(1).strip()
    return None


def ev_id(case: dict, kind: str, content: str | None = None) -> str | None:
    for e in find_evidence(case, kind):
        if content is None or e.get("content") == content:
            return e["id"]
    return None


def data_keys(case: dict) -> list[str]:
    td = case.get("test_data") or {}
    keys = [f"{k}={td[k]}" for k in DATA_KEYS if td.get(k)]
    return keys or [f"case={case['case_id']}"]


def history_flaky(case: dict, window: int) -> bool:
    hist = [h.get("status") for h in (case.get("history") or [])][-window:]
    if len(hist) < 3:
        return False
    rate = sum(1 for s in hist if s == "passed") / len(hist)
    return 0.1 <= rate <= 0.9


def last_frame_in(stack: str | None, paths: list[str]) -> bool:
    frames = re.findall(r'File "([^"]+)"', stack or "")
    if not frames:
        return False
    last = frames[-1].replace("\\", "/")
    return any(p.replace("\\", "/") in last for p in paths)


# ---------------------------------------------------------------- Python 日志（异常链）

def attach_log(case: dict, rules: dict) -> dict | None:
    """解析用例日志，把拆出来的各部分作为独立证据编号。结果缓存在 case["_log"]。"""
    if "_log" in case:
        return case["_log"]
    text = "\n".join(filter(None, [case.get("error_message"), case.get("stack_trace"), case.get("log_text")]))
    L = analyze_log(text, rules.get("log", {}))
    case["_log"] = L
    if not L:
        return None
    ids = {}
    if L["step_log"]:
        ids["step"] = add_evidence(case, "step_log", L["step_log"])
    if L["popup_text"] is not None or L["sys_msgs"]:
        ids["sys"] = add_evidence(case, "system_message",
                                  "\n".join(L["sys_msgs"]) or "（弹窗出现了，但脚本没有读到文字）")
    if L["root"]:
        r = L["root"]
        ids["root"] = add_evidence(case, "root_exception", f"{r['type']}: {r['msg']}".strip(": "))
        if not case.get("error_type"):
            case["error_type"] = r["type"]
    if L["path"]:
        ids["loc"] = add_evidence(case, "failure_location", " → ".join(L["path"]))
    if L["windows"]:
        ids["win"] = add_evidence(case, "open_windows", "\n".join(L["windows"]))
    if L["handler_error"]:
        ids["handler"] = add_evidence(case, "handler_error", L["handler_error"])
    L["ev"] = ids
    return L


def log_signature(case: dict) -> str:
    L = case.get("_log")
    if L and L.get("root"):
        r = L["root"]
        at = L["root_at"]["func"] if L.get("root_at") else (L["path"][-1].split("（")[0] if L.get("path") else "")
        return f"{short_type(r['type'])}|{normalize_signature(r['msg'].splitlines()[0] if r['msg'] else '')}|{at}"
    return f"{short_exception_name(case.get('error_type'))}|{normalize_signature(case.get('error_message'))}"


# ---------------------------------------------------------------- 批量失败检测（ENV3）

def mass_failure_signatures(cases: list, cfg: dict) -> dict[str, dict]:
    ecfg = cfg.get("classify", {}).get("environment", {})
    min_cases = int(ecfg.get("mass_failure_min_cases", 5))
    ratio = float(ecfg.get("mass_failure_ratio", 0.3))
    window = float(ecfg.get("mass_failure_window_minutes", 15))
    by_sig = defaultdict(list)
    for c in cases:
        pe = c.get("popup_evidence") or {}
        if c.get("business_error_text") or pe.get("dialogs") or pe.get("alert_text"):
            continue  # 有业务报错或弹框的，不属于“整体环境故障”
        by_sig[log_signature(c)].append(c)
    result = {}
    for sig, group in by_sig.items():
        if len(group) < min_cases or len(group) / max(1, len(cases)) < ratio:
            continue
        # 执行顺序上连续（需要 execution_index：用例在本次运行中的执行序号，含通过的用例）
        idx = sorted(c["execution_index"] for c in group if c.get("execution_index") is not None)
        contiguous = len(idx) == len(group) and idx[-1] - idx[0] + 1 == len(idx)
        times = sorted(t for t in (parse_time(c.get("started_at")) for c in group) if t)
        if contiguous:
            note = f"{len(group)} 个用例报错特征相同，且在执行顺序上连续（第 {idx[0]}–{idx[-1]} 个）"
        elif len(times) == len(group):
            span = (times[-1] - times[0]).total_seconds() / 60
            if span > window:
                continue
            note = f"{len(group)} 个用例报错特征相同，时间范围 {times[0]:%H:%M}–{times[-1]:%H:%M}"
        else:
            note = f"{len(group)} 个用例报错特征相同（缺少执行时间和执行序号，未校验是否集中发生）"
        result[sig] = {"note": note, "case_ids": [c["case_id"] for c in group]}
    return result


def run_level_flags(out_cases: list, total_cases: int | None) -> None:
    """断崖：从某个用例开始连续因环境失败直到运行结束。标出断崖起点前紧挨着的失败用例（环境中断边界）。

    需要 execution_index 和本次运行的用例总数（failures.json 的 total_cases）；缺少时跳过。
    """
    if not total_cases:
        return
    by_idx = {c["execution_index"]: c for c in out_cases if c.get("execution_index") is not None}
    k = total_cases
    while k in by_idx and by_idx[k]["category"] == "ENVIRONMENT" and by_idx[k]["status"] == "confirmed":
        k -= 1
    tail = total_cases - k
    if tail < 5:
        return
    start = by_idx[k + 1]
    for i in range(k + 1, total_cases + 1):
        by_idx[i]["reason"] += (f"；从第 {k + 1} 个用例（{start['case_id']}）起连续 {tail} 个用例都因环境原因失败直到运行结束，"
                                "环境在这之前中断后没有恢复")
    prev = by_idx.get(k)
    if prev and prev["category"] != "ENVIRONMENT":
        prev["flags"]["env_boundary"] = True
        prev["reason"] += f"；紧挨着环境中断起点（第 {k + 1} 个用例起全部因环境失败），先重跑再判断"
        if prev["status"] == "confirmed":
            prev["status"] = "suspected"


# ---------------------------------------------------------------- 单个用例分类

def classify(case, rerun, rules, checks, cfg, mass):
    exc = short_exception_name(case.get("error_type")) or ""
    msg = case.get("error_message") or ""
    pe = case.get("popup_evidence") or {}
    dialogs = [d for d in (pe.get("dialogs") or []) if d.get("text")]
    alert = alert_text_of(case)
    biz_text = case.get("business_error_text")
    noise, biz = rules.get("noise_popups", []), rules.get("business_errors", [])
    env_rules = rules.get("environment", {})
    script = rules.get("script", {})
    err_ev = ev_id(case, "error_message")
    L = case.get("_log")
    lev = (L or {}).get("ev", {})
    root_txt = f"{L['root']['type']}: {L['root']['msg']}" if L and L.get("root") else ""
    where = f"，位置 {L['root_at']['func']} 第{L['root_at']['line']}行" if L and L.get("root_at") else ""
    types = [short_type(t) for t in (L or {}).get("types", [])] or [exc]

    def any_exc(names):
        return any(t in (names or []) for t in types)

    # 重跑证据
    rr = (rerun.get("results") or {}).get(case["case_id"])
    rerun_ev = None
    if rr:
        summary = "；".join(f"第{a['attempt']}次 {a['status']}（{a['started_at']}）" for a in rr["attempts"])
        rerun_ev = add_evidence(case, "rerun", f"重跑结果：{summary}")
    passed_on_rerun = bool(rr and rr.get("passed_on_rerun"))

    # ENV1 / ENV2 / ENV-DESK
    if exc in env_rules.get("exception_types", []):
        return verdict("ENVIRONMENT", "confirmed", "ENV1", f"异常类型 {exc}", [err_ev, lev.get("root"), rerun_ev])
    env_text = L["main_text"] if L else msg
    hit = match_any(" ".join(filter(None, [env_text, biz_text] + [d["text"] for d in dialogs])),
                    env_rules.get("patterns", []))
    if hit:
        if DESK_PATTERN_RE.search(hit):
            v = verdict("ENVIRONMENT", "confirmed", "ENV-DESK",
                        f"报错匹配“{hit}”：执行机没有可交互的桌面（远程桌面最小化、断开或锁屏时会这样），无法移动鼠标和输入",
                        [lev.get("step"), lev.get("root"), err_ev, rerun_ev])
            v["group_key"] = "env:desktop"
            return v
        v = verdict("ENVIRONMENT", "confirmed", "ENV2", f"报错匹配环境故障特征：{hit}" +
                    ("（被测系统与数据库/后台服务的连接中断）" if BACKEND_PATTERN_RE.search(hit) else ""),
                    [lev.get("sys"), lev.get("root"), err_ev, ev_id(case, "business_error_text"), rerun_ev])
        if BACKEND_PATTERN_RE.search(hit):
            v["group_key"] = "env:backend-connection"
        return v

    # ENV3
    sig = log_signature(case)
    if sig in mass:
        mid = add_evidence(case, "mass_failure", mass[sig]["note"], case_ids=mass[sig]["case_ids"])
        return verdict("ENVIRONMENT", "suspected", "ENV3", mass[sig]["note"], [err_ev, lev.get("root"), mid, rerun_ev])

    # R1
    if passed_on_rerun:
        v = verdict("RERUN_PASS", "confirmed", "R1", "自动重跑通过", [rerun_ev])
        if biz_text or any(match_any(d["text"], biz) for d in dialogs):
            v["flags_extra"] = {"rerun_pass_with_business_error": True}
            v["reason"] += "；但原始失败中出现了业务报错，请人工确认是否需要跟进"
        return v

    # 系统提示（桌面端 pop-up error / Validation Error）：按文字含义分类
    if L and (L["popup_text"] is not None or L["sys_msgs"]):
        sysm = rules.get("system_messages", {})
        text = "\n".join(L["sys_msgs"])
        sid = lev.get("sys")
        if L["popup_text"] == "" and not text:
            return verdict("NEEDS_HUMAN", "suspected", "SYS-EMPTY",
                           "提交后出现了弹窗，但脚本没有读到弹窗文字；只能看截图确认", [sid, err_ev], "unknown_popup")
        h = match_any(text, sysm.get("lock", []))
        if h:
            v = verdict("TEST_DATA", "confirmed", "DATA-LOCK",
                        f"系统提示数据被占用：{text[:120]}；下一步查占用来源（前面失败用例未关窗口？其他批次？）", [sid, err_ev])
            v["group_key"] = "data:lock"
            return v
        if match_any(text, sysm.get("config", [])):
            return verdict("NEEDS_HUMAN", "suspected", "SYS-CFG",
                           f"系统提示缺少配置：{text[:120]}；需确认该配置在测试环境是否应存在", [sid, err_ev], "system_config")
        if match_any(text, sysm.get("crash", [])):
            return verdict("PRODUCT_DEFECT", "suspected", "SYS-CRASH", f"被测程序弹出未处理异常对话框：{text[:120]}", [sid, err_ev])
        if match_any(text, biz) and not biz_text:
            biz_text = text

    # POP1：原生对话框
    if alert:
        aid = ev_id(case, "alert_text") or add_evidence(case, "alert_text", alert)
        if match_any(alert, noise):
            return verdict("POPUP_INTERFERENCE", "confirmed", "POP1",
                           f"原生对话框，文字在干扰清单中：{alert[:80]}", [aid, err_ev])
        if match_any(alert, biz):
            biz_text = biz_text or alert
        else:
            return verdict("NEEDS_HUMAN", "suspected", "POP1-unknown",
                           f"出现不在清单中的原生对话框：{alert[:80]}", [aid, err_ev], "unknown_popup")

    # 业务报错（BIZ1/2/3）
    biz_sources = []
    if biz_text and not match_any(biz_text, noise):
        biz_sources.append(("business_error_text", biz_text))
    for d in dialogs:
        if match_any(d["text"], biz) and not match_any(d["text"], noise):
            biz_sources.append(("popup_text", d["text"]))
    if biz_sources:
        kind, text = biz_sources[0]
        bid = ev_id(case, kind, text) or ev_id(case, "alert_text") or add_evidence(case, kind, text)
        keys = data_keys(case)
        results = {k: checks.get(k) for k in keys}
        check_ids = []
        for k, chk in results.items():
            if chk and chk.get("result"):
                check_ids.append(add_evidence(
                    case, "data_check",
                    f"{k}：{chk['result']}（{chk.get('checked_by')}，{chk.get('checked_at')}，"
                    f"{chk.get('method')}）{chk.get('note') or ''}".strip()))
        bad = [k for k, chk in results.items() if chk and chk.get("result") in BAD_DATA_RESULTS]
        unchecked = [k for k, chk in results.items() if not (chk and chk.get("result"))]
        if bad:
            return verdict("TEST_DATA", "confirmed", "BIZ1",
                           f"业务报错“{text[:80]}”，数据核查结果：" +
                           "，".join(f"{k}={results[k]['result']}" for k in bad),
                           [bid, *check_ids, rerun_ev])
        if not unchecked:
            return verdict("PRODUCT_DEFECT", "confirmed", "BIZ2",
                           f"业务报错“{text[:80]}”，相关数据核查均正常", [bid, *check_ids, rerun_ev])
        v = verdict("NEEDS_HUMAN", "suspected", "BIZ3",
                    f"业务报错“{text[:80]}”，待核查数据：{', '.join(unchecked)}",
                    [bid, *check_ids, rerun_ev], "pending_data_check")
        v["pending_checks"] = unchecked
        return v

    # POP2：网页弹框（干扰）
    if dialogs and exc in UI_BLOCKED_EXC:
        for d in dialogs:
            if match_any(d["text"], noise):
                did = ev_id(case, "popup_text", d["text"])
                return verdict("POPUP_INTERFERENCE", "confirmed", "POP2",
                               f"失败时页面有干扰弹框：{d['text'][:80]}", [did, err_ev])
        did = ev_id(case, "popup_text", dialogs[0]["text"])
        return verdict("NEEDS_HUMAN", "suspected", "POP2-unknown",
                       f"失败时页面有未知弹框：{dialogs[0]['text'][:80]}", [did, err_ev], "unknown_popup")

    # POP3：点击被遮挡，遮挡元素像弹框
    if exc == "ElementClickInterceptedException":
        blocker = intercepting_element(msg)
        if blocker and match_any(blocker, rules.get("popup", {}).get("overlay_keywords", [])):
            bid = add_evidence(case, "intercepting_element", blocker)
            return verdict("POPUP_INTERFERENCE", "suspected", "POP3",
                           f"点击被遮挡，遮挡元素疑似弹框：{blocker[:120]}", [bid, err_ev])

    # POP4：网页内没找到弹框，但有整屏截图
    if pe.get("popup_type") == "not_in_page" and case.get("fullscreen_screenshot") and exc in UI_BLOCKED_EXC:
        fid = ev_id(case, "fullscreen_screenshot")
        return verdict("POPUP_INTERFERENCE", "suspected", "POP4",
                       "网页内没有弹框，疑似浏览器或系统弹窗，请查看整屏截图", [fid, err_ev])

    # 掩盖型报错与桌面端控件异常（pywinauto）。排在 SCR3 之前：AttributeError/TypeError 不一定是脚本问题
    if L and L.get("root"):
        desk = rules.get("desktop", {})
        ids = [lev.get("root"), lev.get("loc"), lev.get("step"), *[e["id"] for e in find_evidence(case, "screenshot")]]
        verify = ""
        if L["success_marks"]:
            verify = f"；步骤日志显示业务操作已成功（“{L['success_marks'][0]}”），失败在之后的结果校验阶段"

        def tag(v):
            if verify:
                v["phase"] = "verify"
            return v

        if match_any(root_txt, desk.get("masked_patterns", [])):
            return tag(verdict("NEEDS_HUMAN", "suspected", "MASK1",
                               f"掩盖型报错 {root_txt[:120]}{where}：前一步查找没找到东西、返回了 False/None，"
                               "报错本身不是原因；需看报错行的查找函数和截图" + verify, ids, "masked_failure"))
        if any_exc(desk.get("ambiguous")):
            return tag(verdict("SCRIPT_ISSUE", "confirmed", "DSK-AMB",
                               f"定位条件匹配到多个控件（{root_txt[:120]}）{where}；同时检查前面用例是否留下窗口" + verify, ids))
        if match_any(root_txt, desk.get("option_missing", [])):
            return tag(verdict("SCRIPT_ISSUE", "suspected", "DSK-OPT",
                               f"下拉框没有脚本要选的选项（{root_txt[:120]}）{where}；需确认实际选项名称" + verify, ids))
        if match_any(root_txt, desk.get("datetime", [])):
            return tag(verdict("SCRIPT_ISSUE", "suspected", "DSK-DTP",
                               f"日期控件设置失败{where}；需确认要设置的日期值和控件允许范围（超出范围属测试数据问题）", ids))
        if any_exc(desk.get("not_enabled")):
            return tag(verdict("NEEDS_HUMAN", "suspected", "DSK-DIS",
                               f"控件处于不可用（灰色）状态（ElementNotEnabled）{where}；原因需看截图或控件状态" + verify,
                               ids, "control_state"))
        if any_exc(desk.get("not_visible")):
            return tag(verdict("SCRIPT_ISSUE", "suspected", "DSK-VIS",
                               f"控件存在但不可见（ElementNotVisible）{where}；需看截图确认页签/区域/窗口状态" + verify, ids))
        if any_exc(desk.get("not_found")) or match_any(root_txt, desk.get("not_found", [])):
            win = f"“{L['expect_window']}”" if L.get("expect_window") else ""
            return tag(verdict("NEEDS_HUMAN", "suspected", "DSK-NF",
                               f"找不到窗口或控件{win}{where}；需看截图，并检查报错列出的窗口里有无前面用例的残留" + verify,
                               ids + [lev.get("win")], "insufficient_evidence"))
        if short_type(L["root"]["type"]) == "Exception" and not match_any(L["root"]["msg"], biz):
            return verdict("NEEDS_HUMAN", "suspected", "GEN1",
                           f"只有笼统的报错“{L['root']['msg'][:100]}”{where}；真实原因需看步骤日志最后几行和截图",
                           ids, "generic_error")

    # SCR2 / SCR3
    if exc in script.get("invalid_selector_exceptions", []):
        return verdict("SCRIPT_ISSUE", "confirmed", "SCR2", "定位表达式无效（InvalidSelectorException）", [err_ev])
    if exc in script.get("python_errors", []):
        paths = cfg.get("classify", {}).get("test_code_paths", [])
        if last_frame_in(case.get("stack_trace"), paths):
            return verdict("SCRIPT_ISSUE", "confirmed", "SCR3",
                           f"测试代码中的 Python 错误：{exc}", [err_ev])
        return verdict("NEEDS_HUMAN", "suspected", "SCR3-outside",
                       f"Python 错误 {exc}，但堆栈不在测试代码目录中", [err_ev], "no_rule_matched")

    # SCR1
    if exc in script.get("locator_exceptions", []):
        note = "找不到元素或等待超时，页面上没有弹框和业务报错"
        if not case.get("popup_evidence"):
            note += "（注意：缺少弹窗证据，无法完全排除弹窗）"
        shots = [e["id"] for e in find_evidence(case, "screenshot")]
        return verdict("SCRIPT_ISSUE", "suspected", "SCR1",
                       note + "；需查看截图确认页面是否正常", [err_ev, *shots, rerun_ev])

    # AST1 / AST2
    if exc in rules.get("assertion", {}).get("exception_types", []):
        if match_any(msg, rules["assertion"].get("expected_actual_patterns", [])):
            return verdict("PRODUCT_DEFECT", "suspected", "AST1",
                           "断言失败，期望值与实际值不一致；需确认期望值是否仍符合当前需求", [err_ev, rerun_ev])
        return verdict("NEEDS_HUMAN", "suspected", "AST2", "断言失败，但没有期望值和实际值",
                       [err_ev], "insufficient_evidence")

    # 兜底
    if not msg and not case.get("screenshots"):
        return verdict("NEEDS_HUMAN", "suspected", "NONE", "没有报错信息，也没有截图",
                       [rerun_ev], "insufficient_evidence")
    return verdict("NEEDS_HUMAN", "suspected", "NONE", f"没有规则命中（异常类型：{exc or '未知'}）",
                   [err_ev, rerun_ev], "no_rule_matched")


# ---------------------------------------------------------------- 主流程

def load_checks(path: str | None) -> dict:
    items = read_yaml(path, default=[]) if path else []
    return {str(i["key"]).strip(): i for i in items if i.get("key")}


def popup_summary(cases: list) -> list:
    counter, pages = Counter(), defaultdict(set)
    for c in cases:
        pe = c.get("popup_evidence") or {}
        texts = [alert_text_of(c)] + [d.get("text") for d in pe.get("dialogs") or []]
        for t in filter(None, texts):
            key = t.strip()[:150]
            counter[key] += 1
            if c.get("page_url"):
                pages[key].add(urlparse(c["page_url"]).path or c["page_url"])
    return [{"text": t, "count": n, "pages": sorted(pages[t])} for t, n in counter.most_common()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--failures", required=True)
    ap.add_argument("--rerun")
    ap.add_argument("--rules", default="config/rules.yaml")
    ap.add_argument("--data-checks")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = read_json(args.failures)
    rerun = read_json(args.rerun) if args.rerun and Path(args.rerun).exists() else {"results": {}, "skipped": True}
    rules = read_yaml(args.rules, default={})
    cfg = load_config(args.config)
    checks = load_checks(args.data_checks)
    window = int(cfg.get("classify", {}).get("history_flaky_window", 10))

    cases = data["cases"]
    for case in cases:
        attach_log(case, rules)  # 先拆日志：后面的批量检测和逐个分类都基于异常链第一段
    mass = mass_failure_signatures(cases, cfg)
    todo = {}
    out_cases = []
    for case in cases:
        v = classify(case, rerun, rules, checks, cfg, mass)
        L = case.pop("_log", None)
        flags = {"historically_flaky": history_flaky(case, window),
                 "rerun_pass_with_business_error": False,
                 "passed_on_rerun": bool((rerun.get("results") or {}).get(case["case_id"], {}).get("passed_on_rerun")),
                 "screenshot_failed": bool(L and L.get("screenshot_failed")),
                 "env_boundary": False}
        flags.update(v.pop("flags_extra", {}))
        if L:
            v["log_summary"] = {"test_function": L["test_fn"], "failure_path": L["path"], "screen": L["screen"],
                                "success_marks": L["success_marks"], "open_windows": L["windows"]}
            if L.get("screenshot_failed"):
                v["reason"] += "；失败处理时截图失败（screen grab failed），报告里的截图不是这个用例失败时的画面"
        for k in v.get("pending_checks", []):
            item = todo.setdefault(k, {"key": k, "result": None, "checked_by": None, "checked_at": None,
                                       "method": None, "note": None, "cases": []})
            item["cases"].append(case["case_id"])
        out_cases.append({**case, **v, "flags": flags, "ai_review": None})
    run_level_flags(out_cases, data.get("total_cases"))

    by_cat = Counter(c["category"] for c in out_cases)
    by_status = Counter(c["status"] for c in out_cases)
    result = {
        "run_id": data["run_id"],
        "generated_at": now_iso(),
        "environment": data.get("environment", {}),
        "rerun_skipped": bool(rerun.get("skipped")),
        "cases": out_cases,
        "summary": {
            "total_failed": len(out_cases),
            "by_category": {k: by_cat.get(k, 0) for k in CATEGORIES},
            "by_status": dict(by_status),
            "needs_human_reasons": dict(Counter(c["needs_human_reason"] for c in out_cases
                                                if c["needs_human_reason"])),
            "popups": popup_summary(cases),
        },
    }
    write_json(args.out, result)

    todo_path = Path(args.out).with_name("data_checks.todo.yaml")
    if todo:
        write_yaml(todo_path, list(todo.values()))
        log.info("有 %d 项数据需要核查，清单：%s", len(todo), todo_path)
    elif todo_path.exists():
        todo_path.unlink()

    log.info("分类完成：%s", "，".join(f"{CATEGORIES[k]} {n}" for k, n in result["summary"]["by_category"].items() if n))
    log.info("confirmed %d / suspected %d", by_status.get("confirmed", 0), by_status.get("suspected", 0))


if __name__ == "__main__":
    main()
