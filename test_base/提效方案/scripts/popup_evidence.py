"""接入测试框架：用例失败时自动收集弹窗证据、截图、整屏截图和环境信息。

这是唯一需要放进测试代码仓库的文件。接入后，load_results.py 就能读到弹窗证据，
弹窗类失败才能被准确分类。

接入方法（pytest + Selenium）：
1. 把本文件复制到测试仓库根目录（与 conftest.py 同级）。
2. 在 conftest.py 中加一行：
       pytest_plugins = ["popup_evidence"]
3. 确认提供 WebDriver 的 fixture 名称。默认是 driver；如果不同，设置环境变量：
       set TRIAGE_DRIVER_FIXTURE=browser
4. （可选）设置页面错误提示区域的 CSS 选择器，用于抓取业务报错文字：
       set TRIAGE_ERROR_SELECTORS=.error-message,.alert-danger,[role=alert]
5. 建议在创建浏览器时加上：
       options.set_capability("unhandledPromptBehavior", "ignore")
   这样原生对话框出现时不会被自动关掉，脚本能记录弹窗文字。

输出：
- evidence/<用例>.json：弹窗类型、弹窗文字、页面弹框、网址、标题、业务报错、浏览器版本
- evidence/<用例>_fail.png：Selenium 截图（网页内容）
- evidence/<用例>_fullscreen.png：整屏截图（可以看到浏览器和系统弹窗；需要 Pillow，且测试机有桌面会话）
- 使用 JUnit XML 时，这些路径写入 <properties>；使用 Allure 时，作为附件挂到用例上。

本插件只读取信息，不会改变用例结果。收集过程出错时只记录警告，不影响测试执行。
"""
from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path

import pytest

EVIDENCE_DIR = Path(os.environ.get("TRIAGE_EVIDENCE_DIR", "evidence")).resolve()
DRIVER_FIXTURE = os.environ.get("TRIAGE_DRIVER_FIXTURE", "driver")
ERROR_SELECTORS = os.environ.get(
    "TRIAGE_ERROR_SELECTORS",
    ".error,.error-message,.alert-danger,.validation-summary-errors,.field-validation-error,[role=alert]")

FIND_DIALOGS_JS = r"""
const sel = '[role=dialog],[role=alertdialog],.modal,.modal-dialog,.popup,.dialog,.ui-dialog,'
          + '.el-dialog,.el-message-box,.ant-modal,.cdk-overlay-pane,.swal2-popup,.toast';
const out = [];
const seen = new Set();
document.querySelectorAll(sel).forEach(el => {
  const r = el.getBoundingClientRect(), s = getComputedStyle(el);
  if (r.width < 2 || r.height < 2 || s.display === 'none' || s.visibility === 'hidden'
      || parseFloat(s.opacity) === 0) return;
  const text = (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 500);
  if (!text || seen.has(text)) return;
  seen.add(text);
  out.push({tag: el.tagName.toLowerCase(), cls: el.getAttribute('class'), id: el.id || null, text: text});
});
return out;
"""

FIND_ERRORS_JS = r"""
const out = [];
document.querySelectorAll(arguments[0]).forEach(el => {
  const r = el.getBoundingClientRect();
  const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
  if (r.width > 0 && r.height > 0 && t) out.push(t.slice(0, 300));
});
return Array.from(new Set(out)).slice(0, 5);
"""


def _safe_name(nodeid: str) -> str:
    return re.sub(r"[^\w.-]+", "_", nodeid)[-120:]


def _alert_text(driver, exc) -> tuple[str | None, bool]:
    """返回 (原生对话框文字, 是否在收集后关闭了对话框)。"""
    from selenium.common.exceptions import NoAlertPresentException, UnexpectedAlertPresentException
    text = getattr(exc, "alert_text", None) if isinstance(exc, UnexpectedAlertPresentException) else None
    try:
        alert = driver.switch_to.alert
        text = text or alert.text
        alert.dismiss()  # 记录文字后关闭，否则后续截图和清理都会失败
        return text, True
    except NoAlertPresentException:
        return text, False
    except Exception:  # noqa: BLE001
        return text, False


def _fullscreen(path: Path) -> str | None:
    try:
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=True).save(path)
        return str(path)
    except Exception as exc:  # noqa: BLE001  无桌面会话、无 Pillow 等情况
        warnings.warn(f"整屏截图失败：{exc}")
        return None


def collect(driver, exc, nodeid: str) -> dict:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    name = _safe_name(nodeid)
    ev = {"nodeid": nodeid, "collected_at": datetime.now().isoformat(timespec="seconds"),
          "exception": type(exc).__name__ if exc else None,
          "message": (str(exc) if exc else "")[:1500]}

    # 整屏截图要最先做：此时浏览器和系统弹窗还在
    ev["fullscreen_screenshot"] = _fullscreen(EVIDENCE_DIR / f"{name}_fullscreen.png")

    alert_text, dismissed = _alert_text(driver, exc)
    ev["alert_text"] = alert_text
    ev["alert_dismissed_after_capture"] = dismissed

    try:
        ev["dialogs"] = driver.execute_script(FIND_DIALOGS_JS) or []
    except Exception as e:  # noqa: BLE001
        ev["dialogs"], ev["dialogs_error"] = [], str(e)[:300]
    try:
        errors = driver.execute_script(FIND_ERRORS_JS, ERROR_SELECTORS) or []
        ev["business_error_text"] = " | ".join(errors) if errors else None
    except Exception:  # noqa: BLE001
        ev["business_error_text"] = None
    try:
        ev["url"], ev["title"] = driver.current_url, driver.title
    except Exception:  # noqa: BLE001
        ev["url"] = ev["title"] = None
    try:
        shot = EVIDENCE_DIR / f"{name}_fail.png"
        driver.get_screenshot_as_file(str(shot))
        ev["screenshot"] = str(shot)
    except Exception as e:  # noqa: BLE001
        ev["screenshot"], ev["screenshot_error"] = None, str(e)[:300]
    try:
        caps = driver.capabilities
        ev["browser"] = {
            "browser": caps.get("browserName"),
            "browser_version": caps.get("browserVersion"),
            "driver_version": (caps.get("msedge") or caps.get("chrome") or {}).get(
                "msedgedriverVersion" if caps.get("msedge") else "chromedriverVersion", "").split(" ")[0] or None,
            "os": caps.get("platformName"),
        }
    except Exception:  # noqa: BLE001
        ev["browser"] = {}

    if alert_text:
        ev["popup_type"] = "js_alert"
    elif ev["dialogs"]:
        ev["popup_type"] = "html_modal"
    else:
        ev["popup_type"] = "not_in_page"

    path = EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    ev["_path"] = str(path)
    return ev


def _attach(item, ev: dict) -> None:
    item.user_properties.append(("evidence", ev["_path"]))
    if ev.get("screenshot"):
        item.user_properties.append(("screenshot", ev["screenshot"]))
    if ev.get("fullscreen_screenshot"):
        item.user_properties.append(("fullscreen_screenshot", ev["fullscreen_screenshot"]))
    if ev.get("url"):
        item.user_properties.append(("page_url", ev["url"]))
    if ev.get("business_error_text"):
        item.user_properties.append(("business_error_text", ev["business_error_text"]))
    try:
        import allure
        allure.attach.file(ev["_path"], name="evidence", attachment_type=allure.attachment_type.JSON)
        if ev.get("screenshot"):
            allure.attach.file(ev["screenshot"], name="failure screenshot",
                               attachment_type=allure.attachment_type.PNG)
        if ev.get("fullscreen_screenshot"):
            allure.attach.file(ev["fullscreen_screenshot"], name="fullscreen screenshot",
                               attachment_type=allure.attachment_type.PNG)
    except ImportError:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    driver = item.funcargs.get(DRIVER_FIXTURE)
    if driver is None:
        return
    try:
        ev = collect(driver, call.excinfo.value if call.excinfo else None, item.nodeid)
        _attach(item, ev)
    except Exception as exc:  # noqa: BLE001  证据收集失败不能影响测试
        warnings.warn(f"弹窗证据收集失败（{item.nodeid}）：{exc}")
