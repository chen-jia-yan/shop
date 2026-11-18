"""ai-dev-kit 桌面挂件：一个置顶的小窗口，按钮全部来自 registry.json。

设计要点
- 按钮不写死：读取 registry.json，每 3 秒检查一次文件是否变化，变了就自动重建按钮（新增技能/工具只要改 registry.json 或用 kit_new.py button）。
- 四种按钮：
    launch_agent  生成提示词 → 复制到剪贴板 → 在项目目录新开窗口启动 Copilot（带 --agent，或提示你用 /agent 选择）
    prompt_only   只生成并复制提示词
    run_tool      在后台线程运行工具包脚本，结果显示在输出框（不卡界面）
    open_path     打开文件或目录
  另有内置表单：锁定修改范围（scope_set）、新增记忆（memory_add）。
- 两种版本：顶部“版本”下拉框选择 quota（公司 bat，1.0.75）或 latest（PATH 里的 copilot），
  启动时设置环境变量 AI_DEV_KIT_PROFILE，钩子据此切换“完整 / 省 token”模式。
- 窗口位置、透明度、置顶、上次选择的项目都记在 ~/.ai-dev-kit/widget_state.json。

运行：双击 widget/start_widget.bat，或 pythonw widget/dev_widget.pyw
"""

from __future__ import annotations

import os
import queue
import shlex
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT / "tools"))
sys.path.insert(0, str(KIT_ROOT / "hooks"))

import kitlib

STATE_PATH = kitlib.DATA_DIR / "widget_state.json"
OUTPUT_FILE = kitlib.DATA_DIR / "widget" / "output.md"
LAUNCH_DIR = kitlib.DATA_DIR / "launch"
IS_WINDOWS = os.name == "nt"

COLORS = {
    "bg": "#f7f7f9", "panel": "#ffffff", "header": "#2f3a56", "header_fg": "#ffffff",
    "accent": "#3b6fd8", "muted": "#6b7280", "ok": "#15803d", "warn": "#b45309", "err": "#b91c1c",
    "border": "#d9dce3",
}
FONT = ("Microsoft YaHei UI", 9) if IS_WINDOWS else ("PingFang SC", 12)
FONT_BOLD = (FONT[0], FONT[1], "bold")
MONO = ("Consolas", 9) if IS_WINDOWS else ("Menlo", 11)


def load_state() -> dict[str, Any]:
    state = kitlib.load_json(STATE_PATH, {}) or {}
    state.setdefault("opacity", 0.97)
    state.setdefault("topmost", True)
    state.setdefault("frameless", False)
    state.setdefault("launch_mode", "window")  # window：新窗口启动 Copilot；copy：只复制
    state.setdefault("collapsed", False)
    return state


class Tooltip:
    """鼠标停留时显示按钮说明。"""

    def __init__(self, widget: Any, text_fn: Callable[[], str]) -> None:
        self.widget = widget
        self.text_fn = text_fn
        self.tip: Any = None
        self.job: Any = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: Any = None) -> None:
        self._cancel()
        self.job = self.widget.after(600, self._show)

    def _cancel(self) -> None:
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self) -> None:
        import tkinter as tk

        text = self.text_fn()
        if not text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=text, justify="left", wraplength=300, bg="#fffbe6", fg="#333",
                 relief="solid", borderwidth=1, font=FONT, padx=6, pady=4).pack()

    def _hide(self, _event: Any = None) -> None:
        self._cancel()
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class KitWidget:
    def __init__(self, root: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.state = load_state()
        self.cfg: dict[str, Any] = {}
        self.registry: dict[str, Any] = {}
        self.mtimes: dict[str, float] = {}
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.busy = False
        self.reload_data()

        root.title("AI 开发助手")
        root.configure(bg=COLORS["bg"])
        root.attributes("-topmost", bool(self.state["topmost"]))
        try:
            root.attributes("-alpha", float(self.state["opacity"]))
        except tk.TclError:
            pass
        if self.state["frameless"]:
            root.overrideredirect(True)
        elif IS_WINDOWS:
            try:
                root.attributes("-toolwindow", True)  # 细标题栏、不占任务栏，输入法和焦点最稳定
            except tk.TclError:
                pass
        if "x" in self.state and "y" in self.state:
            root.geometry(f"+{int(self.state['x'])}+{int(self.state['y'])}")

        style = ttk.Style(root)
        try:
            style.theme_use("vista" if IS_WINDOWS else "clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=FONT, padding=(6, 3))
        style.configure("TLabel", font=FONT, background=COLORS["bg"])
        style.configure("TCheckbutton", font=FONT, background=COLORS["bg"])
        style.configure("TRadiobutton", font=FONT, background=COLORS["bg"])
        style.configure("TNotebook.Tab", font=FONT, padding=(8, 3))
        style.configure("TFrame", background=COLORS["bg"])

        self._build_header()
        self.body = ttk.Frame(root, padding=(8, 6, 8, 8))
        self._build_selectors()
        self._build_task()
        self.notebook = ttk.Notebook(self.body)
        self.notebook.pack(fill="x", pady=(6, 4))
        self._build_tabs()
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._save_state())
        self._build_output()
        self.status = tk.Label(self.body, text="就绪", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT)
        self.status.pack(fill="x", pady=(4, 0))
        if not self.state.get("collapsed"):
            self.body.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.bind("<Configure>", self._remember_position, add="+")
        root.after(150, self._poll_events)
        root.after(3000, self._watch_files)
        if self.cfg.get("_from_example"):
            self.set_status("还没有 kit.config.json：请先运行 tools/install.py，再打开配置文件修改项目路径。", "warn")

    # ------------------------------------------------------------ 数据

    def reload_data(self) -> None:
        self.cfg = kitlib.load_config()
        self.registry = kitlib.load_json(kitlib.REGISTRY_PATH, {"groups": [], "actions": []}) or {}
        for path in (kitlib.REGISTRY_PATH, kitlib.CONFIG_PATH):
            try:
                self.mtimes[str(path)] = path.stat().st_mtime
            except OSError:
                self.mtimes[str(path)] = 0.0

    def projects(self) -> list[str]:
        return [p.get("name", "") for p in self.cfg.get("projects", []) if p.get("name")]

    def profiles(self) -> list[str]:
        return list((self.cfg.get("profiles") or {}).keys())

    def current_project(self) -> dict[str, Any] | None:
        name = self.project_var.get().strip()
        return kitlib.get_project(self.cfg, name) if name else None

    def current_profile(self) -> dict[str, Any]:
        return kitlib.get_profile(self.cfg, self.profile_var.get().strip() or None)

    def task_text(self) -> str:
        return self.task.get("1.0", "end-1c").strip()

    # ------------------------------------------------------------ 界面

    def _build_header(self) -> None:
        tk = self.tk
        bar = tk.Frame(self.root, bg=COLORS["header"])
        bar.pack(fill="x")
        title = tk.Label(bar, text="  AI 开发助手", bg=COLORS["header"], fg=COLORS["header_fg"], font=FONT_BOLD)
        title.pack(side="left", pady=4)
        self.mode_label = tk.Label(bar, text="", bg=COLORS["header"], fg="#c7d2fe", font=FONT)
        self.mode_label.pack(side="left", padx=6)
        for text, cmd, tip in (("×", self.quit, "关闭"), ("—", self.toggle_collapse, "折叠 / 展开"),
                               ("⟳", self.manual_reload, "重新加载按钮和配置")):
            b = tk.Label(bar, text=text, bg=COLORS["header"], fg=COLORS["header_fg"], font=FONT_BOLD,
                         padx=8, cursor="hand2")
            b.pack(side="right")
            b.bind("<Button-1>", lambda _e, c=cmd: c())
            Tooltip(b, lambda t=tip: t)
        for w in (bar, title, self.mode_label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<Button-3>", self._header_menu)
            w.bind("<Double-Button-1>", lambda _e: self.toggle_collapse())

    def _build_selectors(self) -> None:
        ttk = self.ttk
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Label(row, text="项目").pack(side="left")
        self.project_var = self.tk.StringVar(value=self.state.get("project") or (self.projects()[:1] or [""])[0])
        self.project_box = ttk.Combobox(row, textvariable=self.project_var, values=self.projects(), width=18, state="readonly")
        self.project_box.pack(side="left", padx=(4, 10))
        ttk.Label(row, text="版本").pack(side="left")
        default_profile = self.state.get("profile") or self.cfg.get("default_profile") or (self.profiles()[:1] or [""])[0]
        self.profile_var = self.tk.StringVar(value=default_profile)
        self.profile_box = ttk.Combobox(row, textvariable=self.profile_var, values=self.profiles(), width=8, state="readonly")
        self.profile_box.pack(side="left", padx=(4, 0))
        self.project_box.bind("<<ComboboxSelected>>", lambda _e: self._on_selection())
        self.profile_box.bind("<<ComboboxSelected>>", lambda _e: self._on_selection())
        self._update_mode_label()

    def _build_task(self) -> None:
        tk, ttk = self.tk, self.ttk
        ttk.Label(self.body, text="任务 / 需求 / 报错（按钮会使用这里的文字）").pack(anchor="w", pady=(6, 2))
        frame = tk.Frame(self.body, bg=COLORS["border"], padx=1, pady=1)
        frame.pack(fill="x")
        self.task = tk.Text(frame, height=5, width=46, wrap="word", font=FONT, relief="flat", undo=True)
        self.task.pack(fill="x")
        if self.state.get("task"):
            self.task.insert("1.0", self.state["task"])

    def _build_tabs(self) -> None:
        ttk = self.ttk
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)
        actions = self.registry.get("actions", [])
        groups = self.registry.get("groups", []) or [{"id": "default", "label": "全部"}]
        known = {g["id"] for g in groups}
        for g in groups:
            frame = ttk.Frame(self.notebook, padding=4)
            items = [a for a in actions if a.get("group") == g["id"] or (g is groups[0] and a.get("group") not in known)]
            for i, action in enumerate(items):
                label = f"{action.get('icon', '')} {action.get('label', action.get('id'))}".strip()
                btn = ttk.Button(frame, text=label, command=lambda a=action: self.run_action(a))
                btn.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
                Tooltip(btn, lambda a=action: a.get("description", ""))
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=1)
            self.notebook.add(frame, text=g.get("label", g["id"]))
        self.notebook.add(self._build_settings(), text="设置")
        last = self.state.get("tab", 0)
        if isinstance(last, int) and 0 <= last < len(self.notebook.tabs()):
            self.notebook.select(last)

    def _build_settings(self) -> Any:
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(self.notebook, padding=6)
        ttk.Label(frame, text="透明度").grid(row=0, column=0, sticky="w")
        self.opacity_var = tk.DoubleVar(value=float(self.state["opacity"]))
        ttk.Scale(frame, from_=0.5, to=1.0, variable=self.opacity_var, command=lambda _v: self._apply_opacity()).grid(
            row=0, column=1, sticky="ew", padx=4)
        self.topmost_var = tk.BooleanVar(value=bool(self.state["topmost"]))
        ttk.Checkbutton(frame, text="总在最前", variable=self.topmost_var, command=self._apply_topmost).grid(
            row=1, column=0, columnspan=2, sticky="w")
        self.frameless_var = tk.BooleanVar(value=bool(self.state["frameless"]))
        ttk.Checkbutton(frame, text="无边框（重启挂件生效；如果无法输入中文请关闭）", variable=self.frameless_var,
                        command=self._save_state).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="代理按钮").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.launch_var = tk.StringVar(value=self.state["launch_mode"])
        ttk.Radiobutton(frame, text="复制提示词并新开 Copilot 窗口", value="window", variable=self.launch_var,
                        command=self._save_state).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(frame, text="只复制提示词（我自己粘到已开的会话）", value="copy", variable=self.launch_var,
                        command=self._save_state).grid(row=5, column=0, columnspan=2, sticky="w")
        bar = ttk.Frame(frame)
        bar.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(bar, text="打开数据目录", command=lambda: self.open_path(str(kitlib.DATA_DIR))).pack(side="left")
        ttk.Button(bar, text="打开挂件日志", command=lambda: self.open_path(str(kitlib.DATA_DIR / "logs"))).pack(side="left", padx=4)
        frame.columnconfigure(1, weight=1)
        return frame

    def _build_output(self) -> None:
        tk, ttk = self.tk, self.ttk
        head = ttk.Frame(self.body)
        head.pack(fill="x", pady=(4, 2))
        ttk.Label(head, text="输出（生成的提示词、工具结果）").pack(side="left")
        ttk.Button(head, text="清空", width=5, command=lambda: self.set_output("")).pack(side="right")
        ttk.Button(head, text="复制", width=5, command=lambda: self.copy(self.output_text(), "已复制输出框内容")).pack(side="right", padx=2)
        frame = tk.Frame(self.body, bg=COLORS["border"], padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.output = tk.Text(frame, height=14, width=46, wrap="word", font=MONO, relief="flat")
        scroll = ttk.Scrollbar(frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------ 小工具

    def set_status(self, text: str, level: str = "info") -> None:
        color = {"info": COLORS["muted"], "ok": COLORS["ok"], "warn": COLORS["warn"], "err": COLORS["err"]}[level]
        self.status.configure(text=text, fg=color)

    def set_output(self, text: str) -> None:
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.see("1.0")

    def output_text(self) -> str:
        return self.output.get("1.0", "end-1c")

    def copy(self, text: str, message: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.set_status(message, "ok")

    def open_path(self, path: str) -> None:
        if not Path(path).exists():
            self.set_status(f"不存在：{path}", "err")
            return
        if IS_WINDOWS:
            os.startfile(path)  # 用系统默认程序打开
        else:
            subprocess.Popen(["open", path])

    def _update_mode_label(self) -> None:
        prof = self.current_profile()
        mode = "省 token" if prof.get("token_mode") == "lean" else "完整"
        self.mode_label.configure(text=f"[{prof.get('_name', '')} · {mode}]")

    def _on_selection(self) -> None:
        self._update_mode_label()
        self._save_state()

    def _apply_opacity(self) -> None:
        try:
            self.root.attributes("-alpha", float(self.opacity_var.get()))
        except self.tk.TclError:
            pass
        self._save_state()

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", bool(self.topmost_var.get()))
        self._save_state()

    def toggle_collapse(self) -> None:
        if self.body.winfo_ismapped():
            self.body.pack_forget()
            self.state["collapsed"] = True
        else:
            self.body.pack(fill="both", expand=True)
            self.state["collapsed"] = False
        self._save_state()

    def manual_reload(self) -> None:
        self.reload_data()
        self._refresh_after_reload()
        self.set_status("已重新加载按钮和配置", "ok")

    def _refresh_after_reload(self) -> None:
        self.project_box.configure(values=self.projects())
        self.profile_box.configure(values=self.profiles())
        if self.project_var.get() not in self.projects():
            self.project_var.set((self.projects()[:1] or [""])[0])
        if self.profile_var.get() not in self.profiles():
            self.profile_var.set(self.cfg.get("default_profile") or (self.profiles()[:1] or [""])[0])
        self._build_tabs()
        self._update_mode_label()

    def _header_menu(self, event: Any) -> None:
        menu = self.tk.Menu(self.root, tearoff=0)
        menu.add_command(label="重新加载", command=self.manual_reload)
        menu.add_command(label="打开工具包目录", command=lambda: self.open_path(str(KIT_ROOT)))
        menu.add_command(label="打开配置文件", command=lambda: self.open_path(str(kitlib.CONFIG_PATH)))
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _drag_start(self, event: Any) -> None:
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event: Any) -> None:
        dx, dy = getattr(self, "_drag", (0, 0))
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _remember_position(self, event: Any) -> None:
        if event.widget is self.root:
            self.state["x"], self.state["y"] = self.root.winfo_x(), self.root.winfo_y()

    def _save_state(self) -> None:
        try:
            self.state.update({
                "project": self.project_var.get(), "profile": self.profile_var.get(),
                "opacity": round(float(self.opacity_var.get()), 2), "topmost": bool(self.topmost_var.get()),
                "frameless": bool(self.frameless_var.get()), "launch_mode": self.launch_var.get(),
                "tab": self.notebook.index(self.notebook.select()) if self.notebook.tabs() else 0,
                "task": self.task_text()[:4000],
                "x": self.root.winfo_x(), "y": self.root.winfo_y(),
            })
            kitlib.save_json(STATE_PATH, self.state)
        except Exception:
            kitlib.log_event("widget_error", {"where": "save_state", "error": traceback.format_exc(limit=2)})

    def quit(self) -> None:
        self._save_state()
        self.root.destroy()

    # ------------------------------------------------------------ 后台

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "tool_done":
                    _, action, cmd, code, out, seconds = event
                    self.busy = False
                    self._on_tool_done(action, cmd, code, out, seconds)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _watch_files(self) -> None:
        changed = False
        for path in (kitlib.REGISTRY_PATH, kitlib.CONFIG_PATH):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            if mtime != self.mtimes.get(str(path)):
                changed = True
        if changed:
            try:
                self.reload_data()
                self._refresh_after_reload()
                self.set_status("检测到按钮或配置有变化，已自动更新", "ok")
            except Exception as exc:
                self.set_status(f"按钮配置读取失败：{exc}（请运行 kit_lint 检查 registry.json）", "err")
        self.root.after(3000, self._watch_files)

    # ------------------------------------------------------------ 按钮动作

    def context(self) -> dict[str, str]:
        project = self.current_project()
        prof = self.current_profile()
        ctx = kitlib.base_ctx(self.cfg, project)
        task = self.task_text()
        ctx.update({
            "project_name": project.get("name", "") if project else "",
            "task": task,
            "task_line": task.splitlines()[0][:80] if task else "",
            "lean_flag": "--lean" if prof.get("token_mode") == "lean" else "",
            "output_file": str(OUTPUT_FILE),
            "profile": prof.get("_name", ""),
        })
        ctx.setdefault("project", "")
        return ctx

    def expand_command(self, cmd: list[str], ctx: dict[str, str]) -> list[str]:
        """展开占位符；值为空的参数去掉，紧挨着的 --选项 也一起去掉（例如没选项目时的 --project）。"""
        out: list[str] = []
        for part in cmd:
            value = kitlib.expand(part, ctx)
            if value == "" and part.strip():
                if out and out[-1].startswith("--"):
                    out.pop()
                continue
            out.append(value)
        return out

    def run_action(self, action: dict[str, Any]) -> None:
        if action.get("requires_project") and not self.current_project():
            self.set_status("这个按钮需要先在上方选择项目（项目在 kit.config.json 里登记）", "warn")
            return
        if action.get("requires_task") and not self.task_text():
            self.set_status("请先在任务框里写下需求、报错或主题", "warn")
            self.task.focus_set()
            return
        self._save_state()
        kind = action.get("kind")
        try:
            if kind == "run_tool":
                self.run_tool(action)
            elif kind == "prompt_only":
                text = self.build_prompt(action)
                if text:
                    self.set_output(text)
                    self.copy(text, f"已生成并复制：{action.get('label')}")
            elif kind == "launch_agent":
                self.launch_agent(action)
            elif kind == "open_path":
                self.open_path(kitlib.expand(action.get("path", ""), self.context()))
            elif kind == "builtin":
                {"scope_set": self.scope_dialog, "memory_add": self.memory_dialog}.get(
                    action.get("builtin", ""), lambda: self.set_status(f"未知的内置功能：{action.get('builtin')}", "err"))()
            else:
                self.set_status(f"不认识的按钮类型：{kind}", "err")
        except Exception as exc:
            kitlib.log_event("widget_error", {"action": action.get("id"), "error": traceback.format_exc(limit=4)})
            self.set_status(f"出错了：{exc}（详细信息在数据目录 logs 里）", "err")

    def build_prompt(self, action: dict[str, Any]) -> str:
        import prompt_builder

        ctx = self.context()
        if action.get("template"):
            try:
                return prompt_builder.build(action["template"], ctx["task"], ctx["project_name"] or None,
                                            ctx["profile"] or None)
            except SystemExit as exc:
                self.set_status(str(exc), "err")
                return ""
        return kitlib.expand(action.get("prompt", ""), ctx)

    def run_tool(self, action: dict[str, Any], extra: list[str] | None = None) -> None:
        ctx = self.context()
        kitlib.write_text(OUTPUT_FILE, self.output_text())
        cmd = self.expand_command(list(action.get("command", [])), ctx) + list(extra or [])
        self._spawn(action, cmd, ctx)

    def _spawn(self, action: dict[str, Any], cmd: list[str], ctx: dict[str, str] | None = None) -> None:
        if self.busy:
            self.set_status("上一个工具还在运行，请稍等", "warn")
            return
        ctx = ctx or self.context()
        cwd = ctx.get("project") or str(KIT_ROOT)
        if not Path(cwd).is_dir():
            cwd = str(KIT_ROOT)
        env = {"AI_DEV_KIT_PROFILE": ctx["profile"]}
        self.busy = True
        self.set_status(f"正在运行：{action.get('label')} …", "info")
        timeout = int(action.get("timeout", 1800))

        def worker() -> None:
            started = time.time()
            code, out = kitlib.run(cmd, cwd=cwd, timeout=timeout, env_extra=env)
            self.events.put(("tool_done", action, cmd, code, out, time.time() - started))

        threading.Thread(target=worker, daemon=True).start()

    def _on_tool_done(self, action: dict[str, Any], cmd: list[str], code: int, out: str, seconds: float) -> None:
        shown = " ".join(shlex.quote(c) if " " in c else c for c in cmd)
        self.set_output(f"$ {shown}\n（退出码 {code}，用时 {seconds:.1f} 秒）\n\n{out}")
        if code == 0:
            self.set_status(f"完成：{action.get('label')}", "ok")
        elif action.get("id") == "mm-add" and code == 3:
            if self.tk.messagebox.askyesno("发现相近的记忆", "已有内容相近的记忆（见输出框）。仍然保存为新的一条吗？"):
                self._spawn(action, cmd + ["--force"])
                return
            self.set_status("没有保存：可以用 supersede 更新旧记忆", "warn")
        else:
            self.set_status(f"{action.get('label')} 返回 {code}，请看输出框", "err")

    def launch_agent(self, action: dict[str, Any]) -> None:
        text = self.build_prompt(action)
        if not text:
            return
        self.set_output(text)
        self.copy(text, "已复制提示词")
        agent = action.get("agent", "")
        if self.launch_var.get() == "copy":
            self.set_status(f"已复制提示词。在 Copilot 里用 /agent 选择 {agent}（或直接说“用 {agent} 代理”），然后粘贴。", "ok")
            return
        prof = self.current_profile()
        launcher = prof.get("launcher", "")
        if not launcher:
            self.set_status("当前版本没有配置 launcher（kit.config.json → profiles）", "err")
            return
        project = self.current_project()
        cwd = (project or {}).get("path") or str(Path.home())
        args: list[str] = []
        if prof.get("agent_flag", prof.get("launcher_type") != "bat"):
            args += ["--agent", agent]
        args += [kitlib.expand(a, {"agent": agent}) for a in prof.get("launch_extra_args", [])]
        ok, message = self._open_console(launcher, prof.get("launcher_type", "exe"), args, cwd, prof["_name"])
        if not ok:
            self.set_status(message, "err")
            return
        if "--agent" in args:
            self.set_status(f"已打开 Copilot（代理 {agent}）。提示词已复制，窗口里粘贴即可（右键或 Ctrl+V）。", "ok")
        else:
            self.set_status(f"已打开 Copilot。先输入 /agent 选择 {agent}，再粘贴提示词。", "ok")

    def _open_console(self, launcher: str, launcher_type: str, args: list[str], cwd: str, profile: str) -> tuple[bool, str]:
        """写一个临时 .cmd 再用新控制台运行，避免 cmd 对带空格路径和引号的特殊处理。"""
        if not IS_WINDOWS:
            return False, "新开控制台只支持 Windows；已复制提示词，请手动启动 Copilot。"
        LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
        script = LAUNCH_DIR / f"launch-{profile}.cmd"
        quoted = " ".join(f'"{a}"' if (" " in a or not a) else a for a in args)
        exe = launcher if launcher_type == "bat" else kitlib.resolve_exe(launcher)
        # npm 安装的 copilot 实际是 copilot.cmd，和 bat 一样需要 call，否则窗口会在它结束后直接关闭
        call = "call " if exe.lower().endswith((".bat", ".cmd")) else ""
        lines = [
            "@echo off",
            "chcp 65001 >nul",
            f"set AI_DEV_KIT_PROFILE={profile}",
            f'cd /d "{cwd}"',
            f"title Copilot - {profile}",
            f'{call}"{exe}" {quoted}'.rstrip(),
        ]
        with open(script, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        try:
            subprocess.Popen(["cmd", "/k", str(script)], cwd=cwd,
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except OSError as exc:
            return False, f"无法打开新窗口：{exc}"
        return True, ""

    # ------------------------------------------------------------ 内置表单

    def _dialog(self, title: str) -> Any:
        win = self.tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=COLORS["bg"])
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.geometry(f"+{self.root.winfo_x() + 30}+{self.root.winfo_y() + 60}")
        return win

    def scope_dialog(self) -> None:
        tk, ttk = self.tk, self.ttk
        project = self.current_project() or {}
        _root, data = kitlib.find_scope(project.get("path", ""))
        data = data or {}
        win = self._dialog(f"锁定修改范围 - {project.get('name')}")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="步骤名称（例如：K2a 图谱 scope 过滤）").pack(anchor="w")
        task_var = tk.StringVar(value=data.get("task") or self.task_text().splitlines()[0][:60] if self.task_text() else data.get("task", ""))
        ttk.Entry(frm, textvariable=task_var, width=56).pack(fill="x", pady=(0, 6))
        ttk.Label(frm, text="允许修改的文件，每行一个（相对项目根目录；可以用通配，例如 tests/unit/test_kb_*.py）").pack(anchor="w")
        files = tk.Text(frm, height=10, width=56, font=MONO)
        files.pack(fill="both", expand=True)
        files.insert("1.0", "\n".join(list(data.get("files", [])) + list(data.get("globs", []))))
        locked_var = tk.BooleanVar(value=bool(data.get("allow_locked")))
        ttk.Checkbutton(frm, text="本步骤允许修改 pyproject.toml / uv.lock（一般不要勾）", variable=locked_var).pack(anchor="w", pady=4)

        def submit() -> None:
            entries = [ln.strip() for ln in files.get("1.0", "end-1c").splitlines() if ln.strip()]
            plain = [e for e in entries if not any(ch in e for ch in "*?[")]
            globs = [e for e in entries if any(ch in e for ch in "*?[")]
            extra = ["--task", task_var.get().strip() or "未命名步骤"]
            if plain:
                extra += ["--files"] + plain
            if globs:
                extra += ["--globs"] + globs
            if locked_var.get():
                extra.append("--allow-locked")
            win.destroy()
            self.run_tool({"id": "scope-set", "label": "锁定修改范围",
                           "command": ["{python}", "{kit}/tools/scope.py", "set", "--project", "{project_name}"]}, extra)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(6, 0))
        ttk.Button(bar, text="保存", command=submit).pack(side="right")
        ttk.Button(bar, text="取消", command=win.destroy).pack(side="right", padx=4)

    def memory_dialog(self) -> None:
        tk, ttk = self.tk, self.ttk
        import mem

        project = self.current_project()
        win = self._dialog("新增一条记忆")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        type_labels = [f"{k}（{v}）" for k, v in mem.TYPES.items()]
        fields: dict[str, Any] = {}

        def row(label: str, widget: Any) -> None:
            ttk.Label(frm, text=label).pack(anchor="w", pady=(4, 0))
            widget.pack(fill="x")

        scope_var = tk.StringVar(value=f"当前项目：{project.get('name')}" if project else "全局")
        scope_box = ttk.Combobox(frm, textvariable=scope_var, state="readonly",
                                 values=([f"当前项目：{project.get('name')}"] if project else []) + ["全局"])
        row("适用范围", scope_box)
        type_var = tk.StringVar(value=type_labels[0])
        row("类型", ttk.Combobox(frm, textvariable=type_var, values=type_labels, state="readonly"))
        for key, label in (("subject", "主题（一句话，≤60 字）"), ("why", "为什么重要（可选）"),
                           ("how", "以后遇到时怎么做（可选）"), ("cite", "引用（路径:行号#锚点文字；口述写 user:日期 说明；多个用 ; 分隔）"),
                           ("tags", "标签（逗号分隔，可选）")):
            fields[key] = tk.StringVar()
            row(label, ttk.Entry(frm, textvariable=fields[key], width=60))
            if key == "subject":
                ttk.Label(frm, text="事实（≤400 字；不要写密码、密钥、连接串）").pack(anchor="w", pady=(4, 0))
                fact = tk.Text(frm, height=4, width=60, font=FONT, wrap="word")
                fact.pack(fill="x")
        prio_var = tk.StringVar(value="normal")
        row("优先级", ttk.Combobox(frm, textvariable=prio_var, values=["high", "normal", "low"], state="readonly"))

        def submit() -> None:
            subject = fields["subject"].get().strip()
            fact_text = fact.get("1.0", "end-1c").strip()
            if not subject or not fact_text:
                self.tk.messagebox.showwarning("缺少内容", "主题和事实都要填写", parent=win)
                return
            extra = ["--type", type_var.get().split("（")[0], "--subject", subject, "--fact", fact_text,
                     "--priority", prio_var.get()]
            if scope_var.get().startswith("当前项目") and project:
                extra += ["--project", project["name"]]
            for key in ("why", "how", "tags"):
                if fields[key].get().strip():
                    extra += [f"--{key}", fields[key].get().strip()]
            for cite in [c.strip() for c in fields["cite"].get().split(";") if c.strip()]:
                extra += ["--cite", cite]
            win.destroy()
            self.run_tool({"id": "mm-add", "label": "新增记忆",
                           "command": ["{python}", "{kit}/tools/mem.py", "add"]}, extra)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="保存", command=submit).pack(side="right")
        ttk.Button(bar, text="取消", command=win.destroy).pack(side="right", padx=4)


def main() -> None:
    try:
        import tkinter as tk
        import tkinter.messagebox  # 预先导入，表单里会用到

        root = tk.Tk()
        KitWidget(root)
        root.mainloop()
    except Exception:
        detail = traceback.format_exc()
        log = kitlib.DATA_DIR / "logs" / "widget_crash.log"
        kitlib.write_text(log, detail)
        try:
            import tkinter.messagebox as mb

            mb.showerror("AI 开发助手启动失败", f"{detail[-800:]}\n\n完整信息：{log}")
        except Exception:
            print(detail, file=sys.stderr)


if __name__ == "__main__":
    main()
