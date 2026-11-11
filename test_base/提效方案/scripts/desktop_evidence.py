"""失败时采集 Windows 桌面端证据（接入测试框架用，不由 skill 自动运行）。

为什么需要：只有日志和一张截图时，很多失败只能判为“待复核”。在失败那一刻、**关闭弹窗之前**
把窗口清单、对话框文字、控件状态保存下来，大部分结论可以由“猜截图”变成“读事实”。
详见 references/evidence-and-screenshots.md 第 5 节。

接入方法（以 BeautifulReport 的 save_img / 用例基类为例）：

    from desktop_evidence import desktop_available, collect_evidence

    class LasTestBase(unittest.TestCase):
        def setUp(self):
            # 桌面不可用时在用例一开始就以明确的原因失败，而不是做到一半报 SetCursorPos。
            # 报错文字 DESKTOP_UNAVAILABLE 已加入 config/rules.yaml 的环境规则。
            # 要真正“停止本次运行”，需要在运行器或平台里判断：连续 N 个用例出现 DESKTOP_UNAVAILABLE 就终止并报警
            # （unittest 的 failfast 会在任何失败时停止，范围太大，不建议直接用）。
            if not desktop_available():
                raise RuntimeError("DESKTOP_UNAVAILABLE: 执行机没有可交互的桌面（远程桌面可能被最小化、断开或锁屏）")

        # 在失败处理的最开始调用（handle_popups 关闭弹窗之前）
        def on_failure(self, target=None, value=None):
            collect_evidence(out_dir="evidence", case_id=self.id(), target=target, value=value)

输出：evidence/<case_id>.json（以及同名 .png 截图）。把 JSON 作为报告附件或 SDK 接口的一个字段带出来，
skill 会把它作为 A 级证据使用。

依赖：pywinauto、pywin32、Pillow（项目已在使用）。所有采集都放在 try 里：采集失败不影响用例本身的结果。
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime


def desktop_available() -> bool:
    """尝试把鼠标移到当前位置。没有可交互桌面时，Windows 会拒绝 SetCursorPos（与本次报错同一个调用）。"""
    try:
        import win32api
        x, y = win32api.GetCursorPos()
        win32api.SetCursorPos((x, y))
        return True
    except Exception:
        return False


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _control_info(ctrl) -> dict:
    info = {
        "class": _safe(ctrl.class_name, ""),
        "type": _safe(ctrl.friendly_class_name, ""),
        "text": _safe(ctrl.window_text, ""),
        "visible": _safe(ctrl.is_visible),
        "enabled": _safe(ctrl.is_enabled),
    }
    if info["type"] in ("CheckBox", "RadioButton"):
        info["checked"] = _safe(ctrl.get_check_state)  # 0 未勾选 / 1 已勾选 / 2 不确定
    if info["type"] == "ComboBox":
        info["items"] = _safe(ctrl.texts, [])[:50]
    return info


def collect_evidence(out_dir: str, case_id: str, target: str | None = None, value: str | None = None,
                     backend: str = "win32", max_controls: int = 300) -> str | None:
    """采集当前桌面状态，返回 JSON 文件路径；采集失败返回 None。

    target：脚本当时要找/操作的控件或窗口名称；value：要输入的值或要设置的日期。
    """
    try:
        from pywinauto import Desktop
    except Exception:
        return None
    os.makedirs(out_dir, exist_ok=True)
    safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in case_id)
    data = {
        "case_id": case_id,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "desktop_available": desktop_available(),
        "target": target,
        "value": value,
        "foreground_window": None,
        "windows": [],
        "dialogs": [],
        "foreground_controls": [],
        "screenshot": None,
    }
    fg = None
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        data["foreground_window"] = {"title": win32gui.GetWindowText(hwnd), "class": win32gui.GetClassName(hwnd)}
        fg = hwnd
    except Exception:
        pass

    desk = Desktop(backend=backend)
    for w in _safe(desk.windows, []) or []:
        if not _safe(w.is_visible, False):
            continue
        item = {"title": _safe(w.window_text, ""), "class": _safe(w.class_name, ""),
                "enabled": _safe(w.is_enabled), "pid": _safe(w.process_id), "handle": _safe(lambda: w.handle)}
        data["windows"].append(item)
        # 标准对话框（类名 #32770）：读取里面全部文字，解决“弹窗文字为空”的问题
        if item["class"] == "#32770":
            texts = [t for t in (_safe(lambda c=c: c.window_text(), "") for c in (_safe(w.children, []) or [])) if t]
            data["dialogs"].append({"title": item["title"], "texts": texts})
        if fg and item["handle"] == fg:
            for c in (_safe(w.descendants, []) or [])[:max_controls]:
                data["foreground_controls"].append(_control_info(c))

    try:
        from PIL import ImageGrab
        png = os.path.join(out_dir, safe_id + ".png")
        ImageGrab.grab().save(png)
        data["screenshot"] = png
    except Exception as e:  # 截图失败本身也是证据（桌面可能不可用）
        data["screenshot_error"] = f"{type(e).__name__}: {e}"

    path = os.path.join(out_dir, safe_id + ".json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None
