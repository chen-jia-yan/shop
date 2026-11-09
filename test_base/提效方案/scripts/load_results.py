"""第 1 步：读取一次回归的失败用例，统一成 failures.json。

用法：
    python scripts/load_results.py --input <结果目录或文件> --format allure|junit|normalized \
        --run-id <run_id> --config config/config.yaml --out triage_runs/<run_id>/failures.json

说明：
- allure：读取 allure-results 目录中的 *-result.json，只取 status 为 failed / broken 的用例。
- junit：读取一个 XML 文件或目录下全部 *.xml，<failure> 和 <error> 视为失败。
- normalized：读取已经符合 data-contract.md 第 2 节格式的 JSON（cases 列表）。
- 所有文本在写出前都会脱敏。
- 截图等路径会转换为绝对路径，并检查文件是否存在。
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from common import (TZ_HK, add_evidence, fail, load_config, mask_pii, now_iso, read_json,
                    setup_logging, short_exception_name, split_test_data, write_json)

log = setup_logging()

LABEL_KEYS = {"case_id", "market", "module", "system", "suite"}
SCREENSHOT_EXT = {".png", ".jpg", ".jpeg"}
EXCEPTION_RE = re.compile(r"([A-Za-z_][\w.]*(?:Exception|Error))\s*:")


def empty_case() -> dict:
    return {
        "case_id": None, "case_name": None, "nodeid": None,
        "system": None, "market": None, "module": None,
        "status": "failed", "started_at": None, "duration_sec": None,
        "failed_step": None, "case_steps": [],
        "error_type": None, "error_message": None, "stack_trace": None,
        "business_error_text": None, "page_url": None,
        "screenshots": [], "fullscreen_screenshot": None,
        "popup_evidence": None, "test_data": {}, "history": [], "evidence": [],
    }


def ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=TZ_HK).isoformat(timespec="seconds")


def guess_error_type(message: str | None, trace: str | None) -> str | None:
    """从报错信息或堆栈里找出异常类名。先看堆栈最后一行，再看信息开头。"""
    for text in ((trace or "").strip().splitlines()[-1:] + [(message or "")]):
        m = EXCEPTION_RE.search(text)
        if m:
            return short_exception_name(m.group(1))
    return None


def load_evidence_file(path: Path) -> dict | None:
    """读取 popup_evidence.py 写出的证据 JSON。"""
    try:
        return read_json(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("证据文件无法读取：%s（%s）", path, exc)
        return None


def apply_popup_file(case: dict, ev: dict, base: Path) -> None:
    case["popup_evidence"] = {
        "popup_type": ev.get("popup_type"),
        "alert_text": ev.get("alert_text"),
        "dialogs": ev.get("dialogs") or [],
    }
    case["page_url"] = case["page_url"] or ev.get("url")
    case["business_error_text"] = case["business_error_text"] or ev.get("business_error_text")
    # 证据文件里的截图只作为后备：测试报告本身已带截图时不再重复添加
    if ev.get("fullscreen_screenshot"):
        case["_ev_fullscreen"] = str((base / ev["fullscreen_screenshot"]).resolve())
    if ev.get("screenshot"):
        case["_ev_screenshot"] = str((base / ev["screenshot"]).resolve())
    if ev.get("browser"):
        case.setdefault("_env", {}).update(ev["browser"])


# ---------------------------------------------------------------- Allure

def first_failed_step(steps: list) -> str | None:
    for step in steps or []:
        inner = first_failed_step(step.get("steps"))
        if inner:
            return inner
        if step.get("status") in ("failed", "broken"):
            return step.get("name")
    return None


def all_attachments(node: dict) -> list:
    items = list(node.get("attachments") or [])
    for step in node.get("steps") or []:
        items.extend(all_attachments(step))
    return items


def load_allure(input_dir: Path) -> tuple[list, dict]:
    if not input_dir.is_dir():
        fail(f"Allure 结果目录不存在：{input_dir}")
    files = sorted(input_dir.glob("*-result.json"))
    if not files:
        fail(f"目录中没有 *-result.json：{input_dir}")

    env = {}
    props = input_dir / "environment.properties"
    if props.exists():
        for line in props.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    cases = []
    for f in files:
        r = read_json(f)
        if r.get("status") not in ("failed", "broken"):
            continue
        c = empty_case()
        labels = {l.get("name"): l.get("value") for l in r.get("labels", [])}
        c["case_name"] = r.get("name")
        c["nodeid"] = r.get("fullName")
        c["case_id"] = labels.get("case_id") or r.get("testCaseId") or r.get("name")
        for k in ("market", "module", "system"):
            c[k] = labels.get(k)
        c["status"] = r["status"]
        c["started_at"] = ms_to_iso(r.get("start"))
        if r.get("start") and r.get("stop"):
            c["duration_sec"] = round((r["stop"] - r["start"]) / 1000, 1)
        details = r.get("statusDetails") or {}
        c["error_message"] = details.get("message")
        c["stack_trace"] = details.get("trace")
        c["error_type"] = guess_error_type(c["error_message"], c["stack_trace"])
        c["failed_step"] = first_failed_step(r.get("steps"))
        c["case_steps"] = [s.get("name") for s in r.get("steps") or [] if s.get("name")]
        c["test_data"] = {p.get("name"): p.get("value") for p in r.get("parameters", [])}
        for att in all_attachments(r):
            src = input_dir / att.get("source", "")
            name = (att.get("name") or "").lower()
            if not src.exists():
                continue
            if src.suffix.lower() in SCREENSHOT_EXT:
                if "fullscreen" in name or "full screen" in name:
                    c["fullscreen_screenshot"] = str(src.resolve())
                else:
                    c["screenshots"].append(str(src.resolve()))
            elif src.suffix.lower() == ".json" and "evidence" in name:
                ev = load_evidence_file(src)
                if ev:
                    apply_popup_file(c, ev, input_dir)
        cases.append(c)
    return cases, env


# ---------------------------------------------------------------- JUnit

def load_junit(path: Path) -> tuple[list, dict]:
    files = [path] if path.is_file() else sorted(path.glob("**/*.xml"))
    if not files:
        fail(f"找不到 JUnit XML：{path}")
    cases = []
    for f in files:
        base = f.parent
        root = ET.parse(f).getroot()
        for tc in root.iter("testcase"):
            bad = tc.find("failure")
            if bad is None:
                bad = tc.find("error")
            if bad is None:
                continue
            c = empty_case()
            props = {p.get("name"): p.get("value") for p in tc.iter("property")}
            classname, name = tc.get("classname", ""), tc.get("name", "")
            c["case_name"] = name
            c["nodeid"] = props.get("nodeid") or (
                f"{classname.replace('.', '/')}.py::{name}" if classname else name)
            c["case_id"] = props.get("case_id") or name
            for k in ("market", "module", "system"):
                c[k] = props.get(k)
            c["status"] = "failed" if bad.tag == "failure" else "broken"
            c["started_at"] = props.get("started_at") or tc.get("timestamp")
            c["duration_sec"] = float(tc.get("time")) if tc.get("time") else None
            c["error_message"] = bad.get("message")
            c["stack_trace"] = bad.text
            c["error_type"] = short_exception_name(bad.get("type")) or guess_error_type(
                bad.get("message"), bad.text)
            c["failed_step"] = props.get("failed_step")
            c["page_url"] = props.get("page_url")
            c["business_error_text"] = props.get("business_error_text")
            if props.get("case_steps"):
                c["case_steps"] = [s.strip() for s in props["case_steps"].split("||") if s.strip()]
            for k, v in props.items():
                if k == "screenshot" or k.startswith("screenshot_"):
                    p = (base / v).resolve()
                    if p.exists():
                        c["screenshots"].append(str(p))
                elif k == "fullscreen_screenshot":
                    p = (base / v).resolve()
                    if p.exists():
                        c["fullscreen_screenshot"] = str(p)
                elif k == "evidence":
                    ev = load_evidence_file(base / v)
                    if ev:
                        apply_popup_file(c, ev, base)
                elif k not in LABEL_KEYS | {"nodeid", "started_at", "failed_step", "page_url",
                                             "business_error_text", "case_steps"}:
                    c["test_data"][k] = v
            cases.append(c)
    return cases, {}


# ---------------------------------------------------------------- normalized

def load_normalized(path: Path) -> tuple[list, dict]:
    data = read_json(path)
    cases = []
    for raw in data.get("cases", []):
        c = empty_case()
        c.update({k: v for k, v in raw.items() if k in c})
        cases.append(c)
    return cases, data.get("environment", {})


# ---------------------------------------------------------------- 统一处理

def finalize(cases: list, env: dict, cfg: dict) -> dict:
    environment = {
        "env_name": env.get("env_name") or env.get("Environment") or env.get("env"),
        "browser": env.get("browser") or env.get("Browser"),
        "browser_version": env.get("browser_version") or env.get("Browser.Version"),
        "driver_version": env.get("driver_version"),
        "os": env.get("os") or env.get("OS"),
        "build": env.get("build") or env.get("Build"),
    }
    seen_ids = set()
    for c in cases:
        # 浏览器信息若由证据文件提供，用来补全环境信息
        for k, v in (c.pop("_env", None) or {}).items():
            environment[k] = environment.get(k) or v

        if c["case_id"] in seen_ids:  # 参数化用例可能同名，加上序号区分
            c["case_id"] = f"{c['case_id']}#{len(seen_ids)}"
        seen_ids.add(c["case_id"])

        kept, secrets = split_test_data(c["test_data"], cfg)
        c["test_data"] = kept
        for key in ("error_message", "stack_trace", "business_error_text", "case_name", "failed_step"):
            c[key] = mask_pii(c[key], secrets)
        c["case_steps"] = [mask_pii(s, secrets) for s in c["case_steps"]]
        if c["popup_evidence"]:
            pe = c["popup_evidence"]
            pe["alert_text"] = mask_pii(pe.get("alert_text"), secrets)
            for d in pe.get("dialogs") or []:
                d["text"] = mask_pii(d.get("text"), secrets)

        ev_shot, ev_full = c.pop("_ev_screenshot", None), c.pop("_ev_fullscreen", None)
        if not c["screenshots"] and ev_shot:
            c["screenshots"].append(ev_shot)
        if not c["fullscreen_screenshot"] and ev_full:
            c["fullscreen_screenshot"] = ev_full
        if c["fullscreen_screenshot"] and not Path(c["fullscreen_screenshot"]).exists():
            c["fullscreen_screenshot"] = None
        c["screenshots"] = [p for p in dict.fromkeys(c["screenshots"]) if Path(p).exists()]

        # 生成证据编号
        c["evidence"] = []
        if c["error_type"] or c["error_message"]:
            add_evidence(c, "error_message",
                         f"{c['error_type'] or ''}: {(c['error_message'] or '')[:1500]}".strip(": "))
        for p in c["screenshots"]:
            add_evidence(c, "screenshot", path=p)
        if c["fullscreen_screenshot"]:
            add_evidence(c, "fullscreen_screenshot", path=c["fullscreen_screenshot"])
        pe = c["popup_evidence"] or {}
        if pe.get("alert_text"):
            add_evidence(c, "alert_text", pe["alert_text"])
        for d in pe.get("dialogs") or []:
            if d.get("text"):
                add_evidence(c, "popup_text", d["text"], html_class=d.get("cls"), html_id=d.get("id"))
        if c["business_error_text"]:
            add_evidence(c, "business_error_text", c["business_error_text"])
        if c["page_url"]:
            add_evidence(c, "page_url", c["page_url"])
    return {"environment": environment, "cases": cases}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--format", required=True, choices=["allure", "junit", "normalized"])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = load_config(args.config)
    src = Path(args.input)
    loader = {"allure": load_allure, "junit": load_junit, "normalized": load_normalized}[args.format]
    cases, env = loader(src)
    data = finalize(cases, env, cfg)
    data.update({"run_id": args.run_id, "source_format": args.format,
                 "source_path": str(src.resolve()), "loaded_at": now_iso()})
    write_json(args.out, data)

    n = len(data["cases"])
    no_shot = sum(1 for c in data["cases"] if not c["screenshots"])
    no_popup = sum(1 for c in data["cases"] if not c["popup_evidence"])
    no_label = sum(1 for c in data["cases"] if not (c["market"] and c["module"]))
    log.info("读取失败用例 %d 个，写入 %s", n, args.out)
    log.info("缺少截图：%d；缺少弹窗证据：%d；缺少市场/模块标签：%d", no_shot, no_popup, no_label)
    if n and no_popup / n > 0.5:
        log.warning("超过一半用例没有弹窗证据，建议先在测试框架中接入 scripts/popup_evidence.py")


if __name__ == "__main__":
    main()
