"""ai-dev-kit 桌面机器人：一个小机器人 + 头顶的对话泡泡 + 一块随时能打开的数据面板。

机器人（小尺寸，只占一小块地方）
- 读取 ~/.ai-dev-kit/status.json（总调度在每个阶段写入），换表情和动作：
    分析 / 出方案 → 思考；改代码 → 敲键盘、齿轮转；跑验证 → 进度条；评审 → 戴眼镜拿放大镜
    完成 → 星星眼、撒花；卡住了 → 冒汗；守卫拦下危险操作 → 举盾牌
- 很久没动静会打瞌睡；眼睛跟着鼠标看。

对话泡泡（单独的小窗口，不用时不占地方）
- 执行中：每换一个阶段弹一个小泡泡，几秒后自己消失
- 该你了（等你确认方案、Copilot 弹了确认框、要不要删数据、一轮做完了）：橙色提醒泡泡，
  带一键复制的回复，事情处理完自己收起；点一下泡泡也能收起

数据面板（单独的窗口，什么时候都能看，任务结束后也能看）
- 打开 / 关闭：双击机器人、点机器人右下角的小图标、或右键 → 打开数据面板
- 顶上一排按钮切换：总览（时长、Token、上一轮、守卫）/ 时间 / 能力 / 工具 / Token / 最近几轮
- 默认背景透明，只显示动态进度条和小标签；右键面板可以换深色背景、调透明度
- 拖标题栏移动，拖右下角小三角或右边、下边的边框调大小，内容跟着放大；大小和位置都会记住
- 数据都来自本机真实记录（~/.ai-dev-kit/metrics/），没有示例数据；没用过时显示“还没有数据”

操作
- 单击机器人：现在进行到哪、你该做什么；双击：数据面板；拖动：移动（泡泡和面板跟着走）
- 右键机器人：常用工具、模式切换、设置（菜单来自 registry.json，新增按钮不用改代码）
- 任务只在 Copilot 终端里说，机器人不需要输入任何东西

运行：双击 widget/start_widget.bat，或 pythonw widget/dev_widget.pyw
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
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

STATE_PATH = kitlib.DATA_DIR / "pet_state.json"
STATUS_PATH = kitlib.DATA_DIR / "status.json"
OUTPUT_FILE = kitlib.DATA_DIR / "widget" / "output.md"
IS_WINDOWS = os.name == "nt"
KEY = "#fe01fd"  # 透明色：窗口里这个颜色的地方会变成透明（只在 Windows 上生效）
FONT = "Microsoft YaHei UI" if IS_WINDOWS else "PingFang SC"
MONO = "Consolas" if IS_WINDOWS else "Menlo"
FPS_MS = 40

# 机器人配色
INK = "#2f3a56"
PAPER = "#fbf8f2"
# 面板配色（深色科技风）
BG = "#0b1220"
CARD = "#111b2e"
CARD2 = "#16223a"
LINE = "#1e2a44"
GRID = "#0f1a2d"
TEXT = "#e2e8f0"
DIM = "#7b8bab"
FAINT = "#4a5a7a"
ACCENT = "#22d3ee"
ACCENT2 = "#818cf8"
WARN = "#fb923c"
OK = "#34d399"
BAD = "#f87171"
PALETTE = ["#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa"]
ROTATE_SECONDS = 6.0

STAGE_TEXT = {
    "idle": "空闲中", "analyzing": "在分析你的需求", "asking": "有问题想问你", "planning": "在写方案",
    "waiting": "方案好了，等你回复“确认”", "working": "在改代码", "checking": "在跑验证",
    "reviewing": "在评审", "fixing": "评审完了，修哪些听你的", "committing": "可以提交啦，命令在会话里",
    "done": "完成啦！", "error": "卡住了，需要你看一下",
}
STAGE_SHORT = {
    "idle": "空闲", "analyzing": "分析", "asking": "提问", "planning": "方案", "waiting": "等确认",
    "working": "改代码", "checking": "验证", "reviewing": "评审", "fixing": "选修复", "committing": "等提交",
    "done": "完成", "error": "卡住",
}
ATTENTION = {"asking", "waiting", "fixing", "committing"}
RULE_TEXT = {
    "protected-file": "读写密钥文件", "git-write": "git 写操作", "git-add-all": "git add .",
    "package-install": "改依赖", "locked-file": "改锁定文件", "locked-area": "改锁定区域",
    "shared-baseline": "改共享模块前没记基线", "out-of-scope": "越界修改", "shell-write": "用命令写文件",
    "ruff-format": "ruff format", "forbidden-marker": "加屏蔽标记", "invisible-char": "写入隐形字符",
    "fullwidth-space": "写入全角空格", "custom-deny": "自定义禁止的命令", "need-kit-run": "没用删除保护跑测试",
    "delete-rejected": "你拒绝过的删除", "nodelete-tamper": "改删除保护开关", "dangerous-delete": "删 .git 或整个目录",
}
QUIET_RULES = {"delete-needs-consent", "delete-needs-flag"}  # 这两种由提醒卡处理，不举盾牌
LOOKS: dict[str, dict[str, str]] = {
    "idle":       {"eyes": "open",  "mouth": "smile", "light": "#7dd3fc", "anim": "bob",    "icon": "♥"},
    "analyzing":  {"eyes": "up",    "mouth": "flat",  "light": "#60a5fa", "anim": "think",  "icon": "…"},
    "planning":   {"eyes": "up",    "mouth": "flat",  "light": "#60a5fa", "anim": "think",  "icon": "✎"},
    "asking":     {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "waiting":    {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "fixing":     {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "committing": {"eyes": "happy", "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "✓"},
    "attention":  {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "!"},
    "working":    {"eyes": "focus", "mouth": "flat",  "light": "#4ade80", "anim": "work",   "icon": "⚙"},
    "tool":       {"eyes": "focus", "mouth": "flat",  "light": "#4ade80", "anim": "work",   "icon": "⚙"},
    "checking":   {"eyes": "focus", "mouth": "flat",  "light": "#a78bfa", "anim": "check",  "icon": "✓"},
    "reviewing":  {"eyes": "open",  "mouth": "flat",  "light": "#a78bfa", "anim": "review", "icon": "⌕"},
    "done":       {"eyes": "star",  "mouth": "open",  "light": "#facc15", "anim": "party",  "icon": "★"},
    "error":      {"eyes": "sad",   "mouth": "frown", "light": "#f87171", "anim": "sweat",  "icon": "!"},
    "blocked":    {"eyes": "wide",  "mouth": "o",     "light": "#ef4444", "anim": "shield", "icon": "!"},
    "sleep":      {"eyes": "sleep", "mouth": "smile", "light": "#94a3b8", "anim": "sleep",  "icon": "z"},
}
NEXT_STEP = {
    "idle": "在 Copilot 里直接说需求就行，我会自己跟上进度",
    "analyzing": "不用管，它在查代码。有问题会来问你",
    "planning": "不用管，方案马上好",
    "asking": "去 Copilot 窗口回答它的问题（选一个选项就行）",
    "waiting": "去 Copilot 窗口看方案：没问题就回复“确认”，想改就直接说",
    "working": "不用管，它在改代码",
    "checking": "不用管，在跑测试",
    "reviewing": "不用管，在评审",
    "fixing": "去 Copilot 窗口选要修哪些问题",
    "committing": "去 Copilot 窗口复制提交命令，在终端里执行",
    "done": "完成啦！可以开始下一个需求",
    "error": "去 Copilot 窗口看看卡在哪了",
}


def load_state() -> dict[str, Any]:
    state = kitlib.load_json(STATE_PATH, {}) or {}
    defaults = {"robot_scale": 0.75, "topmost": True, "quiet": False, "profile": "", "span": "today",
                "panel_open": bool(state.get("hud", True)), "panel_bg": "clear"}
    for k, v in defaults.items():
        state.setdefault(k, v)
    state.pop("skin", None)  # 旧版本的小猫造型已经去掉
    for old in ("hud", "scale"):  # 2.0 的面板和机器人在一个窗口里；2.1 起分开，大小分别记
        state.pop(old, None)
    return state


def rrect(c: Any, x1: float, y1: float, x2: float, y2: float, r: float, **kw: Any) -> int:
    """圆角矩形（用平滑多边形画）。"""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def mix(c1: str, c2: str, f: float) -> str:
    """两种颜色按比例混合（0 = c1，1 = c2），用来做呼吸灯和渐变。"""
    f = max(0.0, min(1.0, f))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * f):02x}" for x, y in zip(a, b))


def text_px(text: str, size: float) -> float:
    """粗略估算文字宽度：中文约 1 个字号宽，英文和数字约 0.58 个字号宽。"""
    return sum(size if ord(ch) > 0x2e80 else size * 0.58 for ch in text)


def fit(text: str, max_px: float, size: float) -> str:
    """按宽度截断，超出时末尾加省略号。"""
    if text_px(text, size) <= max_px:
        return text
    out = ""
    for ch in text:
        if text_px(out + ch + "…", size) > max_px:
            break
        out += ch
    return out + "…"


# ================================================================= 对话泡泡


class Bubble:
    """机器人头顶的对话泡泡：单独的小窗口，不用时不占任何地方。

    - 普通泡泡（在改代码、跑完了）几秒后自己消失
    - 提醒泡泡（该你了）橙色边框，一直显示到事情处理完，或者你点一下收起
    - 可以带按钮：一键复制回复、看风险评估、打开数据面板
    """

    def __init__(self, pet: "Pet") -> None:
        tk = pet.tk
        self.pet = pet
        self.win = tk.Toplevel(pet.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        bg = KEY if IS_WINDOWS else PAPER
        if IS_WINDOWS:
            self.win.attributes("-transparentcolor", KEY)
        self.win.configure(bg=bg)
        self.c = tk.Canvas(self.win, highlightthickness=0, bd=0, bg=bg, cursor="hand2")
        self.c.pack(fill="both", expand=True)
        self.c.bind("<ButtonRelease-1>", self.on_click)
        self.win.withdraw()
        self.msg: dict[str, Any] = {}
        self.until = 0.0
        self.hits: list[tuple[float, float, float, float, Callable[[], None]]] = []
        self.anchor: tuple[int, int, int, int] | None = None

    @property
    def key(self) -> str:
        return str(self.msg.get("key", ""))

    @property
    def attention(self) -> bool:
        return bool(self.msg.get("attention"))

    def show(self, text: str, seconds: float = 5, attention: bool = False, title: str = "",
             buttons: list[tuple[str, Callable[[], None]]] | None = None, key: str = "", color: str = "") -> None:
        self.msg = {"text": text, "title": title, "attention": attention, "buttons": list(buttons or []),
                    "key": key, "color": color or ("#ea580c" if attention else INK)}
        self.until = time.time() + seconds
        self.anchor = None
        self.tick()

    def visible(self) -> bool:
        return bool(self.msg)

    def hide(self) -> None:
        self.msg = {}
        self.anchor = None
        self.win.withdraw()

    def tick(self) -> None:
        """每一帧调用：到时间就收起；机器人被拖动了就跟着走。"""
        if not self.msg:
            return
        if time.time() > self.until:
            self.hide()
            return
        root = self.pet.root
        anchor = (root.winfo_x(), root.winfo_y(), self.pet.W, self.pet.Hpx)
        if anchor != self.anchor:
            self.anchor = anchor
            self.render(*anchor)
            self.win.deiconify()
            self.win.lift()

    def on_click(self, e: Any) -> None:
        for x1, y1, x2, y2, cb in self.hits:
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                cb()
                return
        if self.key:
            self.pet.dismissed.add(self.key)  # 你收起的提醒不会再弹出来
        self.hide()

    def render(self, px: int, py: int, pw: int, ph: int) -> None:
        c = self.c
        c.delete("all")
        self.hits = []
        m = self.msg
        s = max(1.0, self.pet.s * 1.2)
        pad, tail, bw = 11 * s, 12 * s, 2
        maxw = 250 * s
        color = m["color"]
        y = 0.0
        if m["title"]:
            tid = c.create_text(0, y, text=m["title"], anchor="nw", width=maxw, fill=color, tags="fg",
                                font=(FONT, -int(12.5 * s), "bold"))
            y = c.bbox(tid)[3] + 4 * s
        tid = c.create_text(0, y, text=m["text"], anchor="nw", width=maxw, fill=INK, tags="fg",
                            font=(FONT, -int(12 * s)), justify="left")
        x1, _, x2, y2 = c.bbox("fg")
        content_w, content_h = x2 - x1, y2
        row: list[tuple[str, Callable[[], None], float]] = []
        bx = 0.0
        for label, cb in m["buttons"]:
            w = text_px(label, 11 * s) + 18 * s
            row.append((label, cb, bx))
            bx += w + 6 * s
        if row:
            content_w = max(content_w, bx - 6 * s)
            content_h += 8 * s + 20 * s
        w = int(content_w + pad * 2 + bw * 2)
        h = int(content_h + pad * 2 + bw * 2)
        sw = self.pet.root.winfo_screenwidth()
        bx_win = int(min(max(4, px + pw // 2 - w // 2), sw - w - 4))
        above = py - h - tail > 0
        by_win = int(py - h - tail + 6 * s) if above else int(py + ph - 4 * s)
        top = 0 if above else tail
        fill = "#fff7ed" if m["attention"] else "#ffffff"
        rrect(c, bw, top + bw, w - bw, top + h - bw, 12 * s, fill=fill, outline=color, width=bw)
        tx = min(max(16 * s, px + pw / 2 - bx_win), w - 16 * s)
        if above:
            yb = top + h - bw
            c.create_polygon(tx - 8 * s, yb - 1, tx + 8 * s, yb - 1, tx + 2 * s, yb + tail, fill=fill, outline="")
            c.create_line(tx - 8 * s, yb, tx + 2 * s, yb + tail, tx + 8 * s, yb, fill=color, width=bw)
        else:
            yt = tail + bw
            c.create_polygon(tx - 8 * s, yt + 1, tx + 8 * s, yt + 1, tx + 2 * s, 0, fill=fill, outline="")
            c.create_line(tx - 8 * s, yt, tx + 2 * s, 0, tx + 8 * s, yt, fill=color, width=bw)
        ox, oy = pad + bw, top + pad + bw
        c.move("fg", ox, oy)
        c.tag_raise("fg")
        by = oy + y2 + 8 * s
        for i, (label, cb, rx) in enumerate(row):
            bw_btn = text_px(label, 11 * s) + 18 * s
            primary = i == 0
            rrect(c, ox + rx, by, ox + rx + bw_btn, by + 20 * s, 9 * s, fill=color if primary else "#ffffff",
                  outline=color)
            c.create_text(ox + rx + bw_btn / 2, by + 10 * s, text=label, fill="#ffffff" if primary else color,
                          font=(FONT, -int(11 * s), "bold"))
            self.hits.append((ox + rx, by, ox + rx + bw_btn, by + 20 * s, cb))
        self.win.geometry(f"{w}x{h + int(tail)}+{bx_win}+{by_win}")
        c.configure(width=w, height=h + int(tail))


# ================================================================= 数据面板


TABS = [("overview", "总览"), ("time", "时间"), ("caps", "能力"), ("tools", "工具"), ("tokens", "Token"),
        ("turns", "最近几轮")]
THEMES = {
    # clear：背景透明，只留进度条和带底色的小标签；dark：深色卡片
    "clear": {"bg": KEY if IS_WINDOWS else BG, "chip": CARD, "ink": TEXT, "sub": DIM, "track": CARD2, "edge": "#334155"},
    "dark": {"bg": BG, "chip": CARD, "ink": TEXT, "sub": DIM, "track": CARD2, "edge": LINE},
}


class Panel:
    """数据面板：单独的窗口，什么时候想看都能打开（任务结束后也能看）。

    - 打开 / 关闭：双击机器人、点机器人右下角的小图标、或右键 → 数据面板
    - 顶上一排按钮切换内容：总览 / 时间 / 能力 / 工具 / Token / 最近几轮
    - 拖标题栏移动；拖右下角小三角或右边、下边的边框调大小，内容跟着放大缩小；大小和位置都会记住
    - 默认背景透明，只显示进度条；右键面板可以换成深色背景、调整体透明度
    """

    MIN_W, MIN_H = 300, 190
    DEFAULT_W, DEFAULT_H = 440, 290

    def __init__(self, pet: "Pet") -> None:
        tk = pet.tk
        self.pet = pet
        self.win = tk.Toplevel(pet.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", bool(pet.state.get("topmost", True)))
        self.c = tk.Canvas(self.win, highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)
        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<B1-Motion>", self.on_drag)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        self.c.bind("<Button-3>", self.show_menu)
        self.c.bind("<Button-2>", self.show_menu)
        self.c.bind("<Motion>", self.on_motion)
        self.c.bind("<Leave>", lambda _e: setattr(self, "hover", False))
        st = pet.state
        self.w = max(self.MIN_W, int(st.get("panel_w", self.DEFAULT_W)))
        self.h = max(self.MIN_H, int(st.get("panel_h", self.DEFAULT_H)))
        self.dx: int | None = st.get("panel_dx")
        self.dy: int | None = st.get("panel_dy")
        self.tab = str(st.get("panel_tab", "overview"))
        self.tab_switched = time.time()
        self.summary: dict[str, Any] = {}
        self.channels: dict[str, dict[str, Any]] = {}
        self.loaded_at = 0.0
        self.load_error = ""
        self.mode_label = ""
        self.anim: dict[str, float] = {}
        self.hits: list[tuple[float, float, float, float, Any]] = []
        self.press: tuple[Any, int, int, int, int, int, int] | None = None
        self.hover = False
        self.anchor: tuple[int, int] | None = None
        self.win.withdraw()
        self.apply_theme()

    # -------------------------------------------------- 窗口

    @property
    def is_open(self) -> bool:
        return bool(self.pet.state.get("panel_open", True))

    def theme(self) -> dict[str, str]:
        return THEMES.get(str(self.pet.state.get("panel_bg", "clear")), THEMES["clear"])

    @property
    def clear(self) -> bool:
        return self.pet.state.get("panel_bg", "clear") == "clear"

    def apply_theme(self) -> None:
        th = self.theme()
        if IS_WINDOWS:
            self.win.attributes("-transparentcolor", KEY if self.clear else "")
        self.win.configure(bg=th["bg"])
        self.c.configure(bg=th["bg"])
        try:
            self.win.attributes("-alpha", float(self.pet.state.get("panel_alpha", 1.0)))
        except Exception:
            pass

    def show(self) -> None:
        self.pet.state["panel_open"] = True
        self.loaded_at = 0
        self.anim.clear()
        self.anchor = None
        self.place()
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.pet.state["panel_open"] = False
        self.save()
        self.win.withdraw()

    def place(self) -> None:
        """面板跟着机器人：默认放在机器人左边、底边对齐；你拖过之后记住相对位置。"""
        root = self.pet.root
        rx, ry = root.winfo_x(), root.winfo_y()
        self.anchor = (rx, ry)
        dx, dy = self.dx, self.dy
        if dx is None or dy is None:
            dx = -(self.w + 8) if rx - self.w - 8 >= 0 else self.pet.W + 8
            dy = self.pet.Hpx - self.h
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, min(rx + int(dx), sw - self.w))
        y = max(0, min(ry + int(dy), sh - self.h))
        self.win.geometry(f"{self.w}x{self.h}+{x}+{y}")

    def save(self) -> None:
        self.pet.state.update({"panel_w": self.w, "panel_h": self.h, "panel_dx": self.dx, "panel_dy": self.dy,
                               "panel_tab": self.tab})
        self.pet.save_state()

    def set_bg(self, mode: str) -> None:
        self.pet.state["panel_bg"] = mode
        self.apply_theme()
        self.pet.save_state()

    def set_alpha(self, value: float) -> None:
        self.pet.state["panel_alpha"] = value
        self.apply_theme()
        self.pet.save_state()

    def reset(self) -> None:
        self.w, self.h, self.dx, self.dy = self.DEFAULT_W, self.DEFAULT_H, None, None
        self.place()
        self.save()

    def set_tab(self, key: str) -> None:
        self.tab = key
        self.tab_switched = time.time()
        self.anim.clear()
        self.save()

    def toggle_span(self) -> None:
        self.pet.set_span("week" if self.pet.state.get("span", "today") == "today" else "today")

    def show_menu(self, e: Any) -> None:
        tk = self.pet.tk
        m = self.pet._menu(self.win)
        bv = tk.StringVar(value=str(self.pet.state.get("panel_bg", "clear")))
        m.add_radiobutton(label="背景：透明（只看进度条）", value="clear", variable=bv, command=lambda: self.set_bg("clear"))
        m.add_radiobutton(label="背景：深色", value="dark", variable=bv, command=lambda: self.set_bg("dark"))
        alpha = self.pet._menu(m)
        for label, a in (("不透明", 1.0), ("90%", 0.9), ("75%", 0.75), ("60%", 0.6)):
            alpha.add_command(label=label, command=lambda v=a: self.set_alpha(v))
        m.add_cascade(label="整体透明度", menu=alpha)
        rv = tk.BooleanVar(value=bool(self.pet.state.get("panel_rotate", False)))
        m.add_checkbutton(label=f"自动轮播（每 {int(ROTATE_SECONDS)} 秒换一页）", variable=rv,
                          command=lambda: self.pet.set_state("panel_rotate", not self.pet.state.get("panel_rotate"), "好的"))
        m.add_separator()
        m.add_command(label="恢复默认大小和位置", command=self.reset)
        m.add_command(label="关闭面板", command=self.pet.toggle_panel)
        m.tk_popup(e.x_root, e.y_root)

    # -------------------------------------------------- 鼠标：拖标题栏移动，拖边框 / 右下角调大小

    def _hit(self, x: float, y: float) -> Any:
        for x1, y1, x2, y2, name in reversed(self.hits):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        edge = 8
        right, bottom = x >= self.w - edge, y >= self.h - edge
        if right and bottom:
            return "resize"
        if right:
            return "resize-x"
        if bottom:
            return "resize-y"
        return "move" if not self.clear else ""

    def on_motion(self, e: Any) -> None:
        self.hover = True
        name = self._hit(e.x, e.y)
        cursor = {"resize": "size_nw_se" if IS_WINDOWS else "bottom_right_corner", "resize-x": "sb_h_double_arrow",
                  "resize-y": "sb_v_double_arrow", "move": "fleur"}.get(name if isinstance(name, str) else "", "hand2")
        try:
            self.c.configure(cursor=cursor)
        except Exception:
            self.c.configure(cursor="")

    def on_press(self, e: Any) -> None:
        self.press = (self._hit(e.x, e.y), e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y(), self.w, self.h)

    def on_drag(self, e: Any) -> None:
        if not self.press:
            return
        name, x0, y0, wx, wy, ww, wh = self.press
        dx, dy = e.x_root - x0, e.y_root - y0
        if name == "move":
            self.win.geometry(f"+{wx + dx}+{wy + dy}")
        elif isinstance(name, str) and name.startswith("resize"):
            if name in ("resize", "resize-x"):
                self.w = max(self.MIN_W, ww + dx)
            if name in ("resize", "resize-y"):
                self.h = max(self.MIN_H, wh + dy)
            self.win.geometry(f"{self.w}x{self.h}+{wx}+{wy}")

    def on_release(self, e: Any) -> None:
        if not self.press:
            return
        name, x0, y0 = self.press[:3]
        moved = abs(e.x_root - x0) + abs(e.y_root - y0) > 3
        self.press = None
        if moved and isinstance(name, str) and (name == "move" or name.startswith("resize")):
            root = self.pet.root
            self.dx, self.dy = self.win.winfo_x() - root.winfo_x(), self.win.winfo_y() - root.winfo_y()
            self.save()
        elif not moved and callable(name):
            name()

    # -------------------------------------------------- 数据

    def refresh(self) -> None:
        if time.time() - self.loaded_at < 2.0:
            return
        self.loaded_at = time.time()
        try:
            import kit_metrics

            self.summary = kit_metrics.summary(self.pet.state.get("span", "today"))
            self.channels = {ch["key"]: ch for ch in kit_metrics.channels(self.summary, top=6)}
            self.load_error = ""
        except Exception as exc:  # 统计坏了不影响机器人
            self.summary, self.channels = {}, {}
            self.load_error = repr(exc)[:80]
        cwd = str(self.pet.status.get("cwd") or "")
        try:
            info = kitlib.current_mode(self.pet.cfg, cwd) if cwd and os.path.isdir(cwd) else None
            override = kitlib.read_mode_override()
            if info:
                self.mode_label = info["label"] + ("·手动" if info["source"] == "manual" else "")
            elif override:
                self.mode_label = kitlib.MODES.get(str(override.get("mode")), "") + "·手动"
            else:
                self.mode_label = "自动"
        except Exception:
            self.mode_label = ""

    # -------------------------------------------------- 绘制

    def tick(self, t: float) -> None:
        if not self.is_open:
            return
        root = self.pet.root
        if self.press is None and self.anchor != (root.winfo_x(), root.winfo_y()):
            self.place()  # 机器人被拖动了，面板跟着走
        self.draw(t)

    def _ease(self, key: str, target: float) -> float:
        cur = self.anim.get(key, 0.0)
        cur += (target - cur) * 0.16
        if abs(target - cur) < 0.002:
            cur = target
        self.anim[key] = cur
        return cur

    def chip(self, x: float, y: float, text: str, u: float, anchor: str = "w", bold: bool = False,
             color: str = "", fill: str = "", size: float = 11.0, cb: Any = None) -> tuple[float, float, float, float]:
        """带底色的小标签：透明背景下文字也清楚，不会有毛边。返回标签的外框。"""
        th = self.theme()
        c = self.c
        tid = c.create_text(x, y, text=text, anchor=anchor, fill=color or th["ink"],
                            font=(FONT, -int(size * u), "bold" if bold else "normal"))
        x1, y1, x2, y2 = c.bbox(tid)
        box = (x1 - 6 * u, y1 - 2.5 * u, x2 + 6 * u, y2 + 2.5 * u)
        rrect(c, *box, 7 * u, fill=fill or th["chip"], outline=th["edge"] if self.clear else "", width=1)
        c.tag_raise(tid)
        if cb is not None:
            self.hits.append((*box, cb))
        return box

    def bar(self, x1: float, y: float, x2: float, u: float, frac: float, color: str, key: str, t: float,
            segments: list[tuple[float, str]] | None = None, live: bool = False) -> None:
        """动态进度条：从当前长度缓慢长到目标长度；live=True 时有一道亮光扫过。"""
        c = self.c
        hh = 10 * u
        rrect(c, x1, y - hh / 2, x2, y + hh / 2, hh / 2, fill=self.theme()["track"], outline="")
        f = self._ease(key, max(0.0, min(1.0, frac)))
        if f <= 0.003:
            return
        end = max(x1 + hh, x1 + (x2 - x1) * f)
        if segments:
            pos = x1
            for share, col in segments:
                nxt = min(end, pos + (end - x1) * share)
                if nxt - pos >= 1:
                    rrect(c, pos, y - hh / 2, nxt, y + hh / 2, hh / 2, fill=col, outline="")
                pos = nxt
        else:
            rrect(c, x1, y - hh / 2, end, y + hh / 2, hh / 2, fill=mix(color, BG, 0.25), outline="")
            rrect(c, x1, y - hh / 2, x1 + (end - x1) * 0.6, y + hh / 2, hh / 2, fill=color, outline="")
        if live:
            sx = x1 + ((t * 0.45) % 1.0) * (end - x1)
            c.create_rectangle(max(x1, sx - 8 * u), y - hh / 2 + 2, min(end, sx + 8 * u), y + hh / 2 - 2,
                               fill="#ffffff", outline="")

    def draw(self, t: float) -> None:
        self.refresh()
        c, th = self.c, self.theme()
        c.delete("all")
        self.hits = []
        W, H = self.w, self.h
        u = max(0.85, min(2.2, min(W / self.DEFAULT_W, H / self.DEFAULT_H)))
        # 细边框：透明背景时也能看出面板范围，并且可以拖边框调大小
        rrect(c, 1, 1, W - 1, H - 1, 12 * u, fill="" if self.clear else th["bg"], outline=th["edge"],
              width=2 if self.clear else 1)
        # 标题栏（拖它移动）
        head = 26 * u
        rrect(c, 4, 4, W - 4, 4 + head, 10 * u, fill=th["chip"], outline="")
        self.hits.append((4, 4, W - 4, 4 + head, "move"))
        mid = 4 + head / 2
        live = mix(OK, "#0b3b2e", (math.sin(t * 3) + 1) / 4)
        c.create_oval(12 * u, mid - 3.5 * u, 19 * u, mid + 3.5 * u, fill=live, outline="")
        c.create_text(25 * u, mid, text="AI·DEV 数据", anchor="w", fill=TEXT, font=(MONO, -int(11.5 * u), "bold"))
        x = 112 * u
        if self.mode_label:
            box = self.chip(x, mid, self.mode_label, u, color=ACCENT2, fill=CARD2, size=10)
            x = box[2] + 6 * u
        span = "今天" if self.pet.state.get("span", "today") == "today" else "近7天"
        self.chip(x, mid, span + " ▾", u, fill=CARD2, size=10, cb=self.toggle_span)
        c.create_text(W - 16 * u, mid, text="✕", fill=DIM, font=(FONT, -int(12 * u), "bold"))
        self.hits.append((W - 28 * u, 4, W - 4, 4 + head, self.pet.toggle_panel))
        # 切换按钮
        y = 4 + head + 16 * u
        x = 10 * u
        if self.pet.state.get("panel_rotate") and not self.hover and time.time() - self.tab_switched > ROTATE_SECONDS:
            keys = [k for k, _ in TABS]
            self.set_tab(keys[(keys.index(self.tab) + 1) % len(keys)] if self.tab in keys else keys[0])
        for key, label in TABS:
            on = key == self.tab
            box = self.chip(x, y, label, u, bold=on, color=BG if on else TEXT, fill=ACCENT if on else th["chip"], size=10.5,
                            cb=lambda k=key: self.set_tab(k))
            x = box[2] + 5 * u
        top, bottom = y + 16 * u, H - 14 * u
        if self.load_error:
            self.chip(12 * u, (top + bottom) / 2, "统计暂时读不到：" + self.load_error, u, color=FAINT, size=10)
        elif self.tab == "overview":
            self._overview(top, bottom, W, u, t)
        else:
            self._ranking(self.channels.get(self.tab, {}), top, bottom, W, u)
        # 右下角小三角：拖它调大小
        g = 16 * u
        c.create_polygon(W - 3, H - g, W - 3, H - 3, W - g, H - 3, fill=ACCENT if self.hover else th["edge"], outline="")
        self.hits.append((W - g - 4, H - g - 4, W, H, "resize"))

    def _overview(self, top: float, bottom: float, W: float, u: float, t: float) -> None:
        import kit_metrics

        d = self.summary or {}
        running = self.pet.effective_stage() in ("working", "tool", "checking", "reviewing", "analyzing", "planning")
        rows = 4
        gap = (bottom - top) / rows
        ys = [top + gap * (i + 0.5) for i in range(rows)]
        lx, bx1, bx2, vx = 12 * u, 78 * u, W - 150 * u, W - 12 * u
        # 1. 时长：AI 干活 + 等你，一条两色进度条
        ai, wait = float(d.get("ai_sec") or 0), float(d.get("wait_sec") or 0)
        total = ai + wait
        self.chip(lx, ys[0], "时长", u, bold=True)
        segs = [(ai / total, ACCENT), (wait / total, WARN)] if total else None
        self.bar(bx1, ys[0], bx2, u, 1.0 if total else 0.0, ACCENT, "ov-time", t, segs, live=running)
        self.chip(vx, ys[0], (f"AI {kit_metrics.fmt_sec(ai)} · 等你 {kit_metrics.fmt_sec(wait)}" if total else "还没有数据"),
                  u, anchor="e", size=10)
        # 2. Token：用量 / 每日参考额度
        tok = float(d.get("token_total") or 0)
        budget = float((self.pet.cfg.get("metrics", {}) or {}).get("token_budget_day", 1_000_000))
        if self.pet.state.get("span") == "week":
            budget *= 7
        frac = tok / budget if budget else 0.0
        color = BAD if frac > 0.9 else WARN if frac > 0.6 else ACCENT2
        est = "（估算）" if d.get("token_estimated") else "（部分估算）" if d.get("token_mixed") else ""
        self.chip(lx, ys[1], "Token", u, bold=True)
        self.bar(bx1, ys[1], bx2, u, frac, color, "ov-tok", t, live=running)
        self.chip(vx, ys[1], (f"{kit_metrics.fmt_tok(tok)} / {kit_metrics.fmt_tok(budget)}{est}" if tok else "还没有数据"),
                  u, anchor="e", size=10)
        # 3. 上一轮：耗时和 token（任务结束后也一直留着）
        last = kit_metrics.last_turn(d)
        longest = max([float(r.get("sec") or 0) for r in d.get("recent", [])] + [1.0])
        self.chip(lx, ys[2], "上一轮", u, bold=True)
        self.bar(bx1, ys[2], bx2, u, float(last.get("sec") or 0) / longest, OK, "ov-last", t)
        self.chip(vx, ys[2], (f"{kit_metrics.fmt_sec(float(last.get('sec') or 0))} · "
                              f"{kit_metrics.fmt_tok(float(last.get('tokens') or 0))}" if last else "还没有数据"),
                  u, anchor="e", size=10)
        # 4. 守卫和对话轮数
        g = d.get("guard", {}) or {}
        self.chip(lx, ys[3], "守卫", u, bold=True)
        x = bx1
        for label, n, col in (("拦下", int(g.get("deny", 0)), BAD), ("问你", int(g.get("ask", 0)), WARN),
                              ("禁删拦截", int(d.get("nodelete_blocks", 0)), ACCENT2)):
            box = self.chip(x, ys[3], f"{label} {n}", u, color=BG if n else DIM, fill=col if n else self.theme()["chip"],
                            size=10)
            x = box[2] + 6 * u
        self.chip(vx, ys[3], f"对话 {d.get('turns', 0)} 轮", u, anchor="e", size=10)

    def _ranking(self, ch: dict[str, Any], top: float, bottom: float, W: float, u: float) -> None:
        import kit_metrics

        items = list(ch.get("items") or [])
        if ch.get("title"):
            self.chip(12 * u, top + 4 * u, ch["title"], u, bold=True, size=10.5)
        if not items:
            hint = {"time": "用一轮对话后，这里显示时间花在哪个项目、等了你多久",
                    "caps": "用到技能或代理后，这里显示排行",
                    "tools": "模型调用工具后，这里显示调用次数排行",
                    "tokens": "一轮对话结束后，这里显示 token 去向",
                    "turns": "一轮对话结束后，这里显示每轮花了多久"}.get(str(ch.get("key")), "还没有数据")
            self.chip(12 * u, (top + bottom) / 2 + 8 * u, "还没有数据：" + hint, u, color=FAINT, size=10)
            return
        start = top + 20 * u
        row_h = min(28 * u, (bottom - start) / max(5, len(items)))
        label_w = max(80 * u, (W - 24 * u) * 0.32)
        bx1, bx2 = 12 * u + label_w + 8 * u, W - 90 * u
        vmax = max(v for _, v in items) or 1.0
        for i, (label, value) in enumerate(items):
            key = f"{ch['key']}:{label}"
            pos = self.anim.setdefault("y:" + key, float(i))
            pos += (i - pos) * 0.2
            self.anim["y:" + key] = pos
            ry = start + (pos + 0.5) * row_h
            color = PALETTE[i % len(PALETTE)]
            self.chip(12 * u, ry, fit(f"{i + 1}. {label}", label_w - 12 * u, 10 * u), u, size=10,
                      color=TEXT if i < 3 else DIM)
            self.bar(bx1, ry, bx2, u, value / vmax, color, key, 0.0)
            unit = ch.get("unit")
            shown = (kit_metrics.fmt_sec(value) if unit == "sec" else kit_metrics.fmt_tok(value) if unit == "tok"
                     else f"{int(value)} 次")
            self.chip(W - 12 * u, ry, shown, u, anchor="e", size=10)


# ================================================================= 机器人


class Pet:
    ROBOT_W = 150  # 只放机器人；泡泡和数据面板是单独的窗口
    H = 200

    def __init__(self, root: Any) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.state = load_state()
        self.cfg = kitlib.load_config()
        self.s = float(self.state["robot_scale"])
        self.t0 = time.time()
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.status: dict[str, Any] = {"stage": "idle"}
        self.status_mtime = 0.0
        self.last_activity = time.time()
        self.last_tool_ping = 0.0
        self.blocked_until = 0.0
        self.blocked_text = ""
        self.tool_running = ""
        self.blink_at = time.time() + 2
        self.particles: list[dict[str, Any]] = []
        self.prev_stage = "idle"
        self.guard_log_pos: dict[str, int] = {}
        self.press: tuple[int, int, int, int] | None = None
        self.moved = False
        self.click_job: Any = None
        self.output_win: Any = None
        self.alert: dict[str, Any] = {}
        self.alert_key = ""
        self.alert_checked = 0.0
        self.dismissed: set[str] = set()
        self.ask_info: dict[str, Any] = {}  # 守卫刚弹了确认框（Copilot 在等你选）
        self.W = int(self.ROBOT_W * self.s)
        self.Hpx = int(self.H * self.s)

        if not self.state.get("profile"):
            self.state["profile"] = self.cfg.get("default_profile", "")

        root.overrideredirect(True)
        root.attributes("-topmost", bool(self.state["topmost"]))
        bg = KEY if IS_WINDOWS else PAPER
        if IS_WINDOWS:
            root.attributes("-transparentcolor", KEY)
        root.configure(bg=bg)
        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg=bg, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.apply_scale(self.s, keep_position=False)
        self.bubble = Bubble(self)
        self.panel = Panel(self)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<Button-2>", self.show_menu)

        self._init_guard_positions()
        if not self.state.get("tour_done"):
            self.tour = [
                "嗨～我是你的开发小助手，平时你只管在 Copilot 终端里干活",
                "轮到你的时候，我会在头顶弹泡泡提醒你，泡泡上有一键复制的回复",
                "双击我（或点我右下角的小图标）打开数据面板，随时都能看",
                "面板可以拖动、拖右下角调大小；右键面板换背景，右键我有工具和设置",
            ]
            self.root.after(800, self._next_tip)
        else:
            self.tour = []
            self.say("我在这儿～点我看进度，双击看数据", 4)
        if self.panel.is_open:
            root.after(300, self.panel.show)
        root.after(FPS_MS, self.tick)
        root.after(300, self.poll)

    def _next_tip(self) -> None:
        if not self.tour:
            self.state["tour_done"] = True
            self.save_state()
            return
        self.say(self.tour.pop(0), 4)
        self.root.after(4200, self._next_tip)

    # ------------------------------------------------------------ 窗口与状态

    @property
    def robot_w(self) -> float:
        return self.ROBOT_W * self.s

    def apply_scale(self, s: float, keep_position: bool = True) -> None:
        self.s = s
        self.W = int(self.ROBOT_W * s)
        self.Hpx = int(self.H * s)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = int(self.state.get("x", sw - self.W - 40))
        y = int(self.state.get("y", sh - self.Hpx - 80))
        if keep_position:
            x, y = self.root.winfo_x(), self.root.winfo_y()
        x = max(0, min(x, sw - self.W))
        y = max(0, min(y, sh - self.Hpx))
        self.root.geometry(f"{self.W}x{self.Hpx}+{x}+{y}")

    def save_state(self) -> None:
        try:
            self.state.update({"x": self.root.winfo_x(), "y": self.root.winfo_y(), "robot_scale": self.s})
            kitlib.save_json(STATE_PATH, self.state)
        except Exception:
            pass

    def say(self, text: str, seconds: float = 5, sticky: bool = False) -> None:
        """弹一个普通泡泡；有“该你了”的提醒正在显示时不盖住它。"""
        if self.bubble.attention and not sticky and self.bubble.key:
            return
        self.bubble.show(text, seconds=3600 if sticky else seconds, attention=sticky)

    def toggle_panel(self) -> None:
        if self.panel.is_open:
            self.panel.hide()
        else:
            self.panel.show()
        self.save_state()

    def wants_attention(self) -> bool:
        return bool(self.alert) and self.alert.get("color") != ACCENT

    def _refresh_alert(self) -> None:
        """轮到你的事情，按重要程度只取一件，用提醒泡泡弹出来（不占面板的位置）。"""
        alert: dict[str, Any] = {}
        try:
            import kit_metrics

            note_ts = float((kit_metrics.read_alert(max_age=600) or {}).get("ts", 0))
        except Exception:
            note_ts = 0.0
        if self.ask_info and note_ts > float(self.ask_info.get("ts", 0)):
            self.ask_info = {}  # 之后又有新的提醒（例如这一轮做完了），确认框那件事已经过去
        try:
            pending = kitlib.pending_deletes()
        except Exception:
            pending = []
        stage = str(self.status.get("stage", "idle"))
        if self.ask_info and time.time() - float(self.ask_info.get("ts", 0)) < 600:
            info = self.ask_info
            alert = {"key": "ask:" + str(info.get("ts")), "title": "该你了：Copilot 在等你确认",
                     "body": str(info.get("reason") or "") + "\n去 Copilot 窗口选“同意”或“不同意”（不要选“不再询问”）。"
                     "不同意时可以顺手写一句原因，它会照着调整、接着做。",
                     "color": BAD if info.get("rule") == "data-delete" else WARN, "buttons": [], "sticky": True}
        elif pending:
            req = pending[-1]
            risk = str(req.get("risk", ""))
            level = next((ln.split("：", 1)[1] for ln in risk.splitlines() if ln.startswith("风险：")), "")
            alert = {"key": "del:" + str(req.get("digest")), "title": "该你了：要不要删除数据",
                     "body": f"风险 {level or '未评估'} · " + str(req.get("command", ""))[:120],
                     "color": BAD if level == "高" else WARN, "sticky": True,
                     "buttons": [("复制“同意”", lambda: self._copy_reply("同意，可以删")),
                                 ("复制“不要删”", lambda: self._copy_reply("不要删")),
                                 ("看风险评估", lambda r=risk: self.show_output("删除前的风险评估", r))]}
        elif stage in ATTENTION:
            msg = str(self.status.get("msg") or "")
            buttons: list[tuple[str, Callable[[], None]]] = []
            if stage == "waiting":
                buttons = [("复制“确认”", lambda: self._copy_reply("确认"))]
            elif stage == "committing":
                buttons = [("复制“已提交”", lambda: self._copy_reply("已提交，继续下一步"))]
            alert = {"key": f"stage:{stage}:{self.status.get('updated')}", "title": "该你了：" + STAGE_TEXT[stage],
                     "body": msg or NEXT_STEP.get(stage, ""), "color": WARN, "buttons": buttons, "sticky": True}
        else:
            try:
                import kit_metrics

                note = kit_metrics.read_alert(max_age=600)
            except Exception:
                note = {}
            if note:
                kind = str(note.get("kind", ""))
                title = {"permission_prompt": "该你了：需要你确认一个操作",
                         "elicitation_dialog": "该你了：有问题需要你回答"}.get(kind, "这一轮做完了")
                done = kind == "turn_done"
                alert = {"key": f"note:{note.get('ts')}", "title": title,
                         "body": str(note.get("msg") or "去 Copilot 窗口看看"), "color": ACCENT if done else WARN,
                         "sticky": not done, "buttons": [("看数据", self.panel.show)] if done else []}
        old_key = self.alert_key
        self.alert = alert
        self.alert_key = str(alert.get("key", ""))
        if self.alert_key and self.alert_key != old_key and self.alert_key not in self.dismissed:
            if not self.state.get("quiet") or alert["color"] != ACCENT:
                try:
                    self.root.bell()
                except Exception:
                    pass
            if not (self.state.get("quiet") and alert["color"] == ACCENT):
                self.bubble.show(str(alert.get("body", "")), seconds=3600 if alert.get("sticky") else 8,
                                 attention=bool(alert.get("sticky")), title=str(alert.get("title", "")),
                                 buttons=alert.get("buttons"), key=self.alert_key, color=alert["color"]
                                 if alert["color"] != ACCENT else "")
        elif old_key and self.alert_key != old_key and self.bubble.key == old_key:
            self.bubble.hide()  # 事情处理完了，提醒泡泡自己收起

    def _copy_reply(self, text: str) -> None:
        self.copy(text)
        self.bubble.hide()
        self.say(f"已复制“{text}”，去 Copilot 里粘贴发送", 4)

    def project(self) -> dict[str, Any] | None:
        """自动跟随 Copilot 当前所在的项目；不在项目里时返回 None。"""
        cwd = self.status.get("cwd")
        if not cwd:
            return None
        return kitlib.get_project(self.cfg, str(cwd)) if os.path.isdir(str(cwd)) else None

    def profile(self) -> dict[str, Any]:
        return kitlib.get_profile(self.cfg, self.state.get("profile") or None)

    def effective_stage(self) -> str:
        now = time.time()
        if now < self.blocked_until:
            return "blocked"
        if self.tool_running:
            return "tool"
        stage = self.status.get("stage", "idle")
        if self.wants_attention() and stage not in ATTENTION:
            return "attention"
        if stage == "done" and now - float(self.status.get("updated", 0)) > 90:
            stage = "idle"
        if stage == "idle" and now - self.last_activity > 15 * 60:
            return "sleep"
        return stage

    def _init_guard_positions(self) -> None:
        path = self._guard_log()
        try:
            self.guard_log_pos[str(path)] = path.stat().st_size
        except OSError:
            self.guard_log_pos[str(path)] = 0

    def _guard_log(self) -> Path:
        return kitlib.DATA_DIR / "logs" / f"guard-{time.strftime('%Y%m%d')}.jsonl"

    def poll(self) -> None:
        """每 0.8 秒：读进度、读守卫日志、处理后台工具结果；每 1.6 秒看一次有没有轮到你的事。"""
        try:
            self._poll_status()
            self._poll_guard()
            self._poll_events()
            if time.time() - self.alert_checked > 1.6:
                self.alert_checked = time.time()
                self._refresh_alert()
        except Exception:
            kitlib.log_event("pet_error", {"where": "poll", "error": traceback.format_exc(limit=2)})
        self.root.after(800, self.poll)

    def _poll_status(self) -> None:
        try:
            mtime = STATUS_PATH.stat().st_mtime
        except OSError:
            return
        if mtime == self.status_mtime:
            return
        self.status_mtime = mtime
        import kit_status

        self.status = kit_status.read_status()
        self.last_activity = time.time()
        self.panel.loaded_at = 0
        self.alert_checked = 0
        stage = self.status.get("stage", "idle")
        if self.status.get("session") and self.status.get("updated") != getattr(self, "_session_seen", None):
            self._session_seen = self.status.get("updated")
            self.prev_stage = stage
            if self.status.get("project"):
                self.say(f"开新会话啦，项目：{self.status['project']}", 4)
            else:
                self.say("开新会话啦", 3)
            return
        if stage != self.prev_stage:
            self.prev_stage = stage
            if self.state.get("quiet") and stage not in ATTENTION | {"error", "done"}:
                return
            text = STAGE_TEXT.get(stage, stage)
            if self.status.get("msg"):
                text += "\n" + str(self.status["msg"])
            if stage in ATTENTION:
                self.alert_checked = 0  # “该你了”由提醒泡泡负责（带一键复制的按钮）
            elif stage == "error":
                self.say(text, 3600, sticky=True)
            elif stage == "done":
                self.say(text, 8)
                self.burst(18)
            elif stage != "idle":
                self.say(text, 4)

    def _poll_guard(self) -> None:
        path = self._guard_log()
        key = str(path)
        try:
            size = path.stat().st_size
        except OSError:
            return
        pos = self.guard_log_pos.get(key, 0)
        if size <= pos:
            self.guard_log_pos[key] = size
            return
        with open(path, "rb") as f:
            f.seek(pos)
            chunk = f.read(size - pos)
        self.guard_log_pos[key] = size
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            self.last_activity = time.time()
            self.last_tool_ping = time.time()
            rule = str(rec.get("rule") or "")
            decision = str(rec.get("decision") or "")
            if decision == "ask":
                # 守卫在 Copilot 里弹了确认框：机器人弹泡泡提醒你去选
                reason = str(rec.get("reason") or "").splitlines()
                self.ask_info = {"ts": time.time(), "rule": rule, "reason": reason[0] if reason else ""}
            else:
                self.ask_info = {}  # 又有新的工具调用了，说明确认框已经处理完
            if decision == "deny" and rule not in QUIET_RULES:
                self.blocked_text = RULE_TEXT.get(rule, rule or "危险操作")
                self.blocked_until = time.time() + 4
                self.say(f"拦住了一次：{self.blocked_text}（AI 会跳过这一步接着做）", 5)
        self.alert_checked = 0  # 马上刷新提醒

    def _poll_events(self) -> None:
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return
            if ev[0] == "tool_done":
                _, label, cmd, code, out, secs = ev
                self.tool_running = ""
                self.show_output(f"{label}（退出码 {code}，{secs:.1f} 秒）", "$ " + " ".join(cmd) + "\n\n" + out)
                if code == 0:
                    self.say(f"{label}：完成 ✓", 4)
                    self.burst(6)
                else:
                    self.say(f"{label}：返回 {code}，结果在窗口里", 6)

    # ------------------------------------------------------------ 动画

    def tick(self) -> None:
        try:
            self.draw()
        except Exception:
            kitlib.log_event("pet_error", {"where": "draw", "error": traceback.format_exc(limit=3)})
        self.root.after(FPS_MS, self.tick)

    def burst(self, n: int) -> None:
        for _ in range(n):
            self.particles.append({
                "x": random.uniform(-40, 40), "y": random.uniform(-150, -90),
                "vx": random.uniform(-1.2, 1.2), "vy": random.uniform(-2.6, -1.0),
                "life": random.uniform(1.2, 2.2), "ch": random.choice("★✦♪♥"),
                "color": random.choice(PALETTE),
            })

    def draw(self) -> None:
        c, s = self.canvas, self.s
        c.delete("all")
        t = time.time() - self.t0
        stage = self.effective_stage()
        look = LOOKS.get(stage, LOOKS["idle"])
        anim = look["anim"]

        bob = math.sin(t * 2.2) * 2.5
        hop = 0.0
        if anim == "hop":
            phase = (t * 1.6) % 1.0
            hop = -abs(math.sin(phase * math.pi)) * 14 if phase < 0.5 else 0
        elif anim == "party":
            hop = -abs(math.sin(t * 6)) * 6
        elif anim == "sleep":
            bob = math.sin(t * 1.0) * 1.5
        dy = bob + hop
        cx, ground = self.robot_w / 2, self.Hpx - 16 * s

        def P(x: float, y: float, lift: bool = True) -> tuple[float, float]:
            return cx + x * s, ground + (y + (dy if lift else 0)) * s

        now = time.time()
        if now > self.blink_at + 0.14:
            self.blink_at = now + random.uniform(2.5, 6.0)
        eyes = look["eyes"]
        if self.blink_at <= now <= self.blink_at + 0.14 and eyes in ("open", "wide", "up", "focus"):
            eyes = "blink"
        px, py = self.root.winfo_pointerxy()
        hx, hy = self.root.winfo_rootx() + cx, self.root.winfo_rooty() + ground - 95 * s
        dist = math.hypot(px - hx, py - hy) or 1.0
        look_dx, look_dy = (px - hx) / dist * min(3.0, dist / 40), (py - hy) / dist * min(2.5, dist / 40)
        if eyes == "up":
            look_dx, look_dy = 2.5, -2.5

        shrink = 1 + hop / 40
        x1, y1 = P(-34 * shrink, -4, lift=False)
        x2, y2 = P(34 * shrink, 4, lift=False)
        c.create_oval(x1, y1, x2, y2, fill="#cfd6e4" if IS_WINDOWS else "#d9d2c5", outline="")

        light = look["light"]
        if now - self.last_tool_ping < 0.6 and stage != "blocked":
            light = "#ffffff"
        self.draw_robot(P, t, anim, eyes, look, light, look_dx, look_dy)
        self.draw_effects(P, t, anim, light)
        self.draw_particles(P)
        self.draw_panel_button(t)
        if self.bubble.attention and not self.bubble.key and self.status.get("stage") != "error":
            self.bubble.until = min(self.bubble.until, time.time() + 2)  # “卡住了”解决后泡泡自己收起
        self.bubble.tick()
        self.panel.tick(t)

    def panel_button_box(self) -> tuple[float, float, float, float]:
        s = self.s
        return (self.W - 26 * s, self.Hpx - 24 * s, self.W - 4 * s, self.Hpx - 4 * s)

    def draw_panel_button(self, t: float) -> None:
        """机器人右下角的小图标（三根小柱子）：点它打开 / 关闭数据面板。"""
        c, s = self.canvas, self.s
        x1, y1, x2, y2 = self.panel_button_box()
        on = self.panel.is_open
        rrect(c, x1, y1, x2, y2, 6 * s, fill=ACCENT if on else CARD, outline=INK, width=max(1, int(1.5 * s)))
        for i, hgt in enumerate((0.45, 0.8, 0.6)):
            bx = x1 + (5 + i * 5) * s
            top = y2 - 4 * s - (y2 - y1 - 8 * s) * (hgt if on else hgt * (0.8 + 0.2 * math.sin(t * 3 + i)))
            c.create_rectangle(bx, top, bx + 3 * s, y2 - 4 * s, fill=BG if on else ACCENT, outline="")

    def draw_eyes(self, P: Callable[..., tuple[float, float]], centers: list[tuple[float, float]], kind: str,
                  r: float, color: str, dx: float, dy: float) -> None:
        c, s = self.canvas, self.s
        for ex, ey in centers:
            x, y = P(ex + dx, ey + dy)
            rs = r * s
            if kind in ("open", "up"):
                c.create_oval(x - rs, y - rs * 1.15, x + rs, y + rs * 1.15, fill=color, outline="")
            elif kind == "wide":
                rs *= 1.25
                c.create_oval(x - rs, y - rs * 1.2, x + rs, y + rs * 1.2, fill=color, outline="")
            elif kind == "focus":
                c.create_oval(x - rs, y - rs * 0.45, x + rs, y + rs * 0.45, fill=color, outline="")
            elif kind in ("blink", "sleep"):
                c.create_line(x - rs, y, x + rs, y, fill=color, width=max(2, int(3 * s)), capstyle="round")
            elif kind == "happy":
                c.create_arc(x - rs, y - rs * 0.6, x + rs, y + rs * 1.4, start=20, extent=140, style="arc",
                             outline=color, width=max(2, int(3 * s)))
            elif kind == "star":
                c.create_text(x, y, text="★", fill="#facc15", font=(FONT, -int(20 * s), "bold"))
            elif kind == "sad":
                c.create_oval(x - rs, y - rs, x + rs, y + rs * 1.1, fill=color, outline="")
                side = -1 if ex < 0 else 1
                c.create_line(x - rs * 1.3, y - rs * (1.3 if side > 0 else 0.6), x + rs * 1.3,
                              y - rs * (0.6 if side > 0 else 1.3), fill=color, width=max(2, int(2.5 * s)))

    def draw_mouth(self, P: Callable[..., tuple[float, float]], mx: float, my: float, kind: str, color: str) -> None:
        c, s = self.canvas, self.s
        x, y = P(mx, my)
        w = max(2, int(2.5 * s))
        if kind == "smile":
            c.create_arc(x - 7 * s, y - 6 * s, x + 7 * s, y + 4 * s, start=200, extent=140, style="arc", outline=color, width=w)
        elif kind == "flat":
            c.create_line(x - 5 * s, y, x + 5 * s, y, fill=color, width=w, capstyle="round")
        elif kind == "open":
            c.create_arc(x - 7 * s, y - 6 * s, x + 7 * s, y + 6 * s, start=180, extent=180, style="chord",
                         fill="#f472b6", outline=color, width=w)
        elif kind == "o":
            c.create_oval(x - 3.5 * s, y - 3.5 * s, x + 3.5 * s, y + 3.5 * s, outline=color, width=w)
        elif kind == "frown":
            c.create_arc(x - 7 * s, y - 1 * s, x + 7 * s, y + 9 * s, start=20, extent=140, style="arc", outline=color, width=w)

    def draw_robot(self, P: Callable[..., tuple[float, float]], t: float, anim: str, eyes: str,
                   look: dict[str, str], light: str, ldx: float, ldy: float) -> None:
        c, s = self.canvas, self.s
        lw = max(2, int(3 * s))
        for fx in (-22, 6):
            a, b = P(fx, -14)
            d, e = P(fx + 16, -2)
            c.create_oval(a, b, d, e, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        swing = math.sin(t * (14 if anim == "work" else 2)) * (8 if anim == "work" else 2)
        if anim == "party":
            swing = -14 + math.sin(t * 10) * 4
        for side in (-1, 1):
            sx, sy = P(28 * side, -48)
            hx, hy = P(42 * side, -30 + (swing if side < 0 else -swing))
            c.create_line(sx, sy, hx, hy, fill=INK, width=max(3, int(5 * s)), capstyle="round")
            c.create_oval(hx - 5 * s, hy - 5 * s, hx + 5 * s, hy + 5 * s, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        rrect(c, *P(-28, -62), *P(28, -10), 14 * s, fill="#e0e7ff", outline=INK, width=lw)
        rrect(c, *P(-17, -52), *P(17, -22), 7 * s, fill="#1f2a44", outline="")
        bx, by = P(0, -37)
        c.create_text(bx, by, text=self._belly_text(look), fill=light, font=(FONT, -int(13 * s), "bold"))
        rrect(c, *P(-8, -68), *P(8, -58), 3 * s, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        for ex1, ex2 in ((-54, -46), (46, 54)):
            rrect(c, *P(ex1, -106), *P(ex2, -84), 4 * s, fill="#c7d2fe", outline=INK, width=max(1, int(2 * s)))
        rrect(c, *P(-46, -130), *P(46, -64), 22 * s, fill="#ffffff", outline=INK, width=lw)
        rrect(c, *P(-36, -120), *P(36, -76), 16 * s, fill="#1f2a44", outline="")
        for side in (-1, 1):
            a, b = P(29 * side - 5, -74)
            d, e = P(29 * side + 5, -68)
            c.create_oval(a, b, d, e, fill="#fecdd3", outline="")
        self.draw_eyes(P, [(-15, -100), (15, -100)], eyes, 7, "#7df9ff", ldx, ldy)
        self.draw_mouth(P, 0, -85, look["mouth"], "#7df9ff")
        if anim == "review":
            self._glasses(P, [(-15, -100), (15, -100)])
        a, b = P(0, -130)
        d, e = P(0, -144)
        c.create_line(a, b, d, e, fill=INK, width=lw)
        pulse = 1 + 0.25 * math.sin(t * (8 if anim == "hop" else 3))
        bx, by = P(0, -148)
        r = 5.5 * s * pulse
        if anim in ("hop", "shield"):
            c.create_oval(bx - r * 2, by - r * 2, bx + r * 2, by + r * 2, outline=light, width=max(1, int(2 * s)))
        c.create_oval(bx - r, by - r, bx + r, by + r, fill=light, outline=INK, width=max(1, int(2 * s)))

    def _belly_text(self, look: dict[str, str]) -> str:
        step, total = self.status.get("step"), self.status.get("total")
        if step and total and self.effective_stage() in ("working", "checking", "reviewing", "fixing"):
            return f"{step}/{total}"
        return look["icon"]

    def _glasses(self, P: Callable[..., tuple[float, float]], centers: list[tuple[float, float]]) -> None:
        c, s = self.canvas, self.s
        pts = []
        for ex, ey in centers:
            x, y = P(ex, ey)
            r = 11 * s
            c.create_oval(x - r, y - r, x + r, y + r, outline="#facc15", width=max(2, int(2.5 * s)))
            pts.append((x, y))
        c.create_line(pts[0][0] + 11 * s, pts[0][1], pts[1][0] - 11 * s, pts[1][1], fill="#facc15", width=max(2, int(2.5 * s)))

    def draw_effects(self, P: Callable[..., tuple[float, float]], t: float, anim: str, light: str) -> None:
        c, s = self.canvas, self.s
        if anim == "think":
            for i, (x, y, r) in enumerate(((34, -138, 3), (44, -150, 4.5), (57, -162, 6))):
                on = int(t * 3) % 3 >= i
                a, b = P(x, y)
                rr = r * s * (1.0 if on else 0.6)
                c.create_oval(a - rr, b - rr, a + rr, b + rr, fill="#ffffff" if on else "#e5e7eb", outline=INK,
                              width=max(1, int(1.5 * s)))
        elif anim == "work":
            gx, gy = P(52, -30)
            ang = t * 3
            teeth = []
            for k in range(16):
                rad = (12 if k % 2 == 0 else 8.5) * s
                a = ang + k * math.pi / 8
                teeth += [gx + math.cos(a) * rad, gy + math.sin(a) * rad]
            c.create_polygon(teeth, fill="#cbd5e1", outline=INK, width=max(1, int(2 * s)))
            c.create_oval(gx - 3.5 * s, gy - 3.5 * s, gx + 3.5 * s, gy + 3.5 * s, fill=INK, outline="")
        elif anim == "check":
            x1, y1 = P(-30, 7, lift=False)
            x2, y2 = P(30, 12, lift=False)
            rrect(c, x1, y1, x2, y2, 2.5 * s, fill="#e5e7eb", outline=INK, width=max(1, int(1.5 * s)))
            frac = (t * 0.5) % 1.0
            if frac > 0.04:
                rrect(c, x1 + 1, y1 + 1, x1 + (x2 - x1) * frac, y2 - 1, 2 * s, fill="#a78bfa", outline="")
        elif anim == "review":
            mx, my = P(48, -34)
            r = 9 * s
            c.create_line(mx + r * 0.7, my + r * 0.7, mx + r * 1.8, my + r * 1.8, fill=INK, width=max(3, int(4 * s)), capstyle="round")
            c.create_oval(mx - r, my - r, mx + r, my + r, fill="#e0f2fe", outline=INK, width=max(2, int(3 * s)))
        elif anim == "sweat":
            drop = (t * 0.8) % 1.0
            x, y = P(42, -124 + drop * 18)
            c.create_polygon(x, y - 7 * s, x - 5 * s, y + 2 * s, x, y + 6 * s, x + 5 * s, y + 2 * s, smooth=True,
                             fill="#93c5fd", outline="#3b82f6", width=max(1, int(1.5 * s)))
        elif anim == "shield":
            x, y = P(-52, -48)
            w = 14 * s
            c.create_polygon(x - w, y - w, x + w, y - w, x + w, y + w * 0.3, x, y + w * 1.3, x - w, y + w * 0.3,
                             fill="#ef4444", outline=INK, width=max(2, int(2.5 * s)))
            c.create_text(x, y, text="✋", fill="#ffffff", font=(FONT, -int(13 * s), "bold"))
        elif anim == "sleep":
            for i in range(3):
                phase = (t * 0.35 + i / 3) % 1.0
                x, y = P(36 + phase * 26, -136 - phase * 34)
                c.create_text(x, y, text="z", fill="#64748b", font=(FONT, -int((10 + phase * 8) * s), "bold"))
        elif anim == "party" and random.random() < 0.15:
            self.burst(1)

    def draw_particles(self, P: Callable[..., tuple[float, float]]) -> None:
        dt = FPS_MS / 1000
        alive = []
        for p in self.particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.05
            x, y = P(p["x"], p["y"])
            self.canvas.create_text(x, y, text=p["ch"], fill=p["color"], font=(FONT, -int(14 * self.s), "bold"))
            alive.append(p)
        self.particles = alive[-60:]

    # ------------------------------------------------------------ 鼠标

    def on_press(self, e: Any) -> None:
        self.press = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.moved = False
        self.last_activity = time.time()

    def on_drag(self, e: Any) -> None:
        if not self.press:
            return
        x0, y0, wx, wy = self.press
        if abs(e.x_root - x0) + abs(e.y_root - y0) > 4:
            self.moved = True
        self.root.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")  # 泡泡和面板会跟着走

    def on_release(self, e: Any) -> None:
        self.press = None
        if self.moved:
            self.save_state()
            return
        x1, y1, x2, y2 = self.panel_button_box()
        if x1 <= e.x <= x2 and y1 <= e.y <= y2:
            self.toggle_panel()
            return
        if self.click_job is None:  # 等一下，看是不是双击
            self.click_job = self.root.after(260, self._single_click)

    def _single_click(self) -> None:
        self.click_job = None
        self.toggle_status_bubble()

    def on_double(self, _e: Any) -> None:
        """双击机器人：打开 / 关闭数据面板。"""
        if self.click_job is not None:
            self.root.after_cancel(self.click_job)
            self.click_job = None
        self.toggle_panel()

    def toggle_status_bubble(self) -> None:
        """单击机器人：显示现在的进度，以及你现在要做什么。再点一次收起。"""
        if self.bubble.visible() and not self.bubble.key:
            self.bubble.hide()
            return
        if self.bubble.key and self.alert and self.bubble.key == self.alert_key:
            self.dismissed.add(self.alert_key)
            self.bubble.hide()
            return
        if self.alert and self.alert_key in self.dismissed:
            self.dismissed.discard(self.alert_key)  # 你收起过的提醒：点机器人再看一次
            self.alert_key = ""
            self._refresh_alert()
            return
        st = self.status
        stage = st.get("stage", "idle")
        lines = [f"【{STAGE_TEXT.get(stage, stage)}】"]
        if st.get("task"):
            lines.append(f"任务：{st['task']}")
        if st.get("step") and st.get("total"):
            lines.append(f"第 {st['step']}/{st['total']} 步")
        if st.get("msg") and stage != "idle":
            lines.append(str(st["msg"]))
        lines.append("→ " + NEXT_STEP.get(stage, ""))
        self.bubble.show("\n".join(lines), seconds=10, buttons=[("看数据", self.panel.show)])

    # ------------------------------------------------------------ 菜单

    def _menu(self, parent: Any) -> Any:
        return self.tk.Menu(parent, tearoff=0, font=(FONT, 10), bg=CARD, fg=TEXT, activebackground=ACCENT,
                            activeforeground=BG, bd=0)

    def show_menu(self, e: Any) -> None:
        tk = self.tk
        self.cfg = kitlib.load_config()
        registry = kitlib.load_json(kitlib.REGISTRY_PATH, {"groups": [], "actions": []}) or {}
        groups = registry.get("groups", [])
        actions = [a for a in registry.get("actions", []) if not a.get("hidden")]
        proj = self.project()
        m = self._menu(self.root)
        m.add_command(label="◎  现在进行到哪了？", command=self.toggle_status_bubble)
        m.add_command(label=("▣  关闭数据面板" if self.panel.is_open else "▣  打开数据面板（双击我也可以）"), command=self.toggle_panel)
        for a in [a for a in actions if a.get("pin")]:
            m.add_command(label=f"{a.get('icon', '')}  {a.get('label', a.get('id'))}",
                          command=lambda act=a: self.run_action(act))
        m.add_separator()
        more = self._menu(m)
        for g in groups:
            items = [a for a in actions if a.get("group") == g.get("id") and not a.get("pin")]
            if not items:
                continue
            sub = self._menu(more)
            for a in items:
                sub.add_command(label=f"{a.get('icon', '')}  {a.get('label', a.get('id'))}",
                                command=lambda act=a: self.run_action(act))
            more.add_cascade(label=g.get("label", g.get("id")), menu=sub)
        m.add_cascade(label="更多工具", menu=more)

        mode_menu = self._menu(m)
        current = kitlib.read_mode_override().get("mode", "auto")
        mv = tk.StringVar(value=str(current))
        mode_menu.add_radiobutton(label="自动（项目里 = 项目开发，其他 = 工作台）", value="auto", variable=mv,
                                  command=lambda: self.set_mode("auto"))
        for key, label in kitlib.MODES.items():
            mode_menu.add_radiobutton(label=label, value=key, variable=mv, command=lambda k=key: self.set_mode(k))
        m.add_cascade(label="模式", menu=mode_menu)

        settings = self._menu(m)
        settings.add_command(label=f"当前项目：{proj.get('name') if proj else '不在项目里'}（自动跟随 Copilot）", state="disabled")
        bg_menu = self._menu(settings)
        bv = tk.StringVar(value=str(self.state.get("panel_bg", "clear")))
        bg_menu.add_radiobutton(label="透明（只看进度条）", value="clear", variable=bv, command=lambda: self.panel.set_bg("clear"))
        bg_menu.add_radiobutton(label="深色", value="dark", variable=bv, command=lambda: self.panel.set_bg("dark"))
        bg_menu.add_separator()
        bg_menu.add_command(label="恢复默认大小和位置", command=self.panel.reset)
        settings.add_cascade(label="数据面板背景", menu=bg_menu)
        spv = tk.StringVar(value=self.state.get("span", "today"))
        span_menu = self._menu(settings)
        span_menu.add_radiobutton(label="今天", value="today", variable=spv, command=lambda: self.set_span("today"))
        span_menu.add_radiobutton(label="最近 7 天", value="week", variable=spv, command=lambda: self.set_span("week"))
        settings.add_cascade(label="统计范围", menu=span_menu)
        prof_menu = self._menu(settings)
        fv = tk.StringVar(value=self.state.get("profile", ""))
        for name, prof in (self.cfg.get("profiles") or {}).items():
            prof_menu.add_radiobutton(label=prof.get("label", name), value=name, variable=fv,
                                      command=lambda v=name: self.set_state("profile", v, f"生成的提示词按“{v}”版本"))
        settings.add_cascade(label="提示词版本（完整 / 省 token）", menu=prof_menu)
        size_menu = self._menu(settings)
        for label, sc in (("小（默认）", 0.75), ("中", 0.95), ("大", 1.2)):
            size_menu.add_command(label=label, command=lambda v=sc: (self.apply_scale(v), self.save_state()))
        settings.add_cascade(label="机器人大小（面板大小直接拖右下角）", menu=size_menu)
        tv = tk.BooleanVar(value=bool(self.state["topmost"]))
        settings.add_checkbutton(label="总在最前", variable=tv, command=self.toggle_topmost)
        qv = tk.BooleanVar(value=bool(self.state["quiet"]))
        settings.add_checkbutton(label="安静模式（只在需要你处理时提醒）", variable=qv,
                                 command=lambda: self.set_state("quiet", not self.state["quiet"], "好的"))
        settings.add_separator()
        settings.add_command(label="再看一遍使用提示", command=self.replay_tour)
        settings.add_command(label="打开工具包目录", command=lambda: self.open_path(str(KIT_ROOT)))
        m.add_cascade(label="设置", menu=settings)
        m.add_separator()
        m.add_command(label="退出", command=self.quit)
        m.tk_popup(e.x_root, e.y_root)

    def set_mode(self, mode: str) -> None:
        kitlib.set_mode(None if mode == "auto" else mode, "")
        self.panel.loaded_at = 0
        self.alert_checked = 0
        label = "自动判断" if mode == "auto" else kitlib.MODES[mode]
        self.say(f"模式：{label}" + ("（12 小时后恢复自动）" if mode != "auto" else "") + "\n新开的会话生效", 4)

    def set_span(self, span: str) -> None:
        self.state["span"] = span
        self.save_state()
        self.panel.loaded_at = 0
        self.alert_checked = 0
        self.panel.anim.clear()


    def replay_tour(self) -> None:
        self.state["tour_done"] = False
        self.tour = [
            "轮到你的时候，我会在头顶弹泡泡，泡泡上有一键复制的回复",
            "双击我打开数据面板：顶上的按钮切换内容，任务结束后也能看",
            "面板拖标题栏移动、拖右下角调大小；右键面板换背景",
            "右键我：工具、模式切换、设置",
        ]
        self._next_tip()

    def set_state(self, key: str, value: Any, message: str) -> None:
        self.state[key] = value
        self.save_state()
        self.say(message, 3)

    def toggle_topmost(self) -> None:
        self.state["topmost"] = not self.state["topmost"]
        self.root.attributes("-topmost", bool(self.state["topmost"]))
        self.panel.win.attributes("-topmost", bool(self.state["topmost"]))
        self.save_state()

    def quit(self) -> None:
        self.save_state()
        self.root.destroy()

    def open_path(self, path: str) -> None:
        if not Path(path).exists():
            self.say(f"找不到：{path}", 4)
            return
        if IS_WINDOWS:
            os.startfile(path)  # 用系统默认程序打开
        else:
            subprocess.Popen(["open", path])

    def copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    # ------------------------------------------------------------ 按钮动作（来自 registry.json）

    def context(self, task: str = "") -> dict[str, str]:
        project = self.project()
        prof = self.profile()
        ctx = kitlib.base_ctx(self.cfg, project)
        ctx.update({
            "project_name": ("." if project.get("_auto") else project.get("name", "")) if project else "",
            "task": task, "task_line": task.splitlines()[0][:80] if task else "",
            "lean_flag": "--lean" if prof.get("token_mode") == "lean" else "",
            "output_file": str(OUTPUT_FILE), "profile": prof.get("_name", ""),
        })
        ctx.setdefault("project", "")
        return ctx

    @staticmethod
    def expand_command(cmd: list[str], ctx: dict[str, str]) -> list[str]:
        """展开占位符；值为空的参数去掉，紧挨着的 --选项 也一起去掉。"""
        out: list[str] = []
        for part in cmd:
            value = kitlib.expand(part, ctx)
            if value == "" and part.strip():
                if out and out[-1].startswith("--"):
                    out.pop()
                continue
            out.append(value)
        return out

    def run_action(self, action: dict[str, Any], task: str | None = None) -> None:
        self.last_activity = time.time()
        if action.get("requires_project") and not self.project():
            self.say("这个功能要在项目里用：先在项目目录里打开 Copilot 开个会话，我就知道是哪个项目了", 6)
            return
        if action.get("requires_task") and task is None:
            self.ask_text(action, lambda text: self.run_action(action, text))
            return
        kind = action.get("kind")
        try:
            if kind == "run_tool":
                self.run_tool(action.get("label", ""), self.expand_command(list(action.get("command", [])), self.context(task or "")))
            elif kind in ("prompt_only", "launch_agent"):
                text = self.build_prompt(action, task or "")
                if not text:
                    return
                self.copy(text)
                self.show_output(action.get("label", "提示词"), text)
                if kind == "launch_agent":
                    self.say(f"提示词已复制。在 Copilot 里先输入 /agent 选 {action.get('agent')}，再粘贴", 7)
                else:
                    self.say("提示词已复制，去 Copilot 里粘贴吧", 4)
            elif kind == "open_path":
                self.open_path(kitlib.expand(action.get("path", ""), self.context()))
            elif kind == "builtin":
                handler = {"new_request": lambda: self.say("直接在 Copilot 终端里说需求就行，轮到你时我会弹泡泡提醒", 5),
                           "status": self.toggle_status_bubble,
                           "memory_add": self.memory_dialog, "toggle_hud": self.toggle_panel}.get(action.get("builtin", ""))
                handler() if handler else self.say(f"不认识的内置功能：{action.get('builtin')}", 4)
            else:
                self.say(f"不认识的按钮类型：{kind}", 4)
        except Exception as exc:
            kitlib.log_event("pet_error", {"action": action.get("id"), "error": traceback.format_exc(limit=4)})
            self.say(f"出错了：{exc}", 6)

    def build_prompt(self, action: dict[str, Any], task: str) -> str:
        import prompt_builder

        ctx = self.context(task)
        if action.get("template"):
            try:
                return prompt_builder.build(action["template"], task, ctx.get("project") or None, ctx["profile"] or None)
            except SystemExit as exc:
                self.say(str(exc), 6)
                return ""
        return kitlib.expand(action.get("prompt", ""), ctx)

    def run_tool(self, label: str, cmd: list[str]) -> None:
        if self.tool_running:
            self.say(f"我还在忙“{self.tool_running}”，等我一下", 4)
            return
        ctx = self.context()
        cwd = ctx.get("project") or str(KIT_ROOT)
        if not Path(cwd).is_dir():
            cwd = str(KIT_ROOT)
        self.tool_running = label
        self.say(f"正在{label}…", 3)

        def worker() -> None:
            started = time.time()
            code, out = kitlib.run(cmd, cwd=cwd, timeout=1800, env_extra={"AI_DEV_KIT_PROFILE": ctx["profile"]})
            self.events.put(("tool_done", label, cmd, code, out, time.time() - started))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ 窗口（深色主题）

    def _window(self, title: str, w: int = 520, h: int = 420) -> Any:
        win = self.tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        x = max(0, self.root.winfo_x() - w - 10)
        y = max(0, self.root.winfo_y() + self.Hpx - h)
        win.geometry(f"{w}x{h}+{x}+{y}")
        return win

    def _button(self, parent: Any, text: str, cmd: Callable[[], None], primary: bool = False) -> Any:
        tk = self.tk
        return tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2", font=(FONT, 10, "bold"),
                         bg=ACCENT if primary else CARD2, fg=BG if primary else TEXT,
                         activebackground="#06b6d4" if primary else LINE, activeforeground=BG if primary else TEXT,
                         padx=14, pady=5, bd=0)

    def _textbox(self, parent: Any, height: int, mono: bool = False) -> Any:
        tk = self.tk
        return tk.Text(parent, height=height, wrap="word", font=(MONO if mono else FONT, 10 if mono else 11), relief="flat",
                       bg="#0f172a", fg=TEXT, insertbackground=ACCENT, selectbackground="#1e3a5f", padx=10, pady=8,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)

    def show_output(self, title: str, text: str) -> None:
        tk = self.tk
        if self.output_win is not None and self.output_win.winfo_exists():
            win = self.output_win
            for child in win.winfo_children():
                child.destroy()
            win.title(title)
            win.deiconify()
            win.lift()
        else:
            win = self.output_win = self._window(title, 620, 480)
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(bar, text=title, bg=BG, fg=TEXT, font=(FONT, 11, "bold")).pack(side="left")
        box = self._textbox(win, 18, mono=True)
        box.insert("1.0", text)
        box.pack(fill="both", expand=True, padx=12)
        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=12, pady=10)
        self._button(foot, "复制全部", lambda: (self.copy(box.get("1.0", "end-1c")), self.say("已复制", 2)), True).pack(side="right")
        self._button(foot, "关闭", win.destroy).pack(side="right", padx=6)

    def ask_text(self, action: dict[str, Any], on_ok: Callable[[str], None]) -> None:
        tk = self.tk
        win = self._window(action.get("label", ""), 480, 280)
        tk.Label(win, text=action.get("description", "") or "请输入内容", bg=BG, fg=DIM, font=(FONT, 10),
                 wraplength=440, justify="left").pack(anchor="w", padx=14, pady=(14, 6))
        box = self._textbox(win, 6)
        box.pack(fill="both", expand=True, padx=14)
        box.focus_set()

        def ok() -> None:
            text = box.get("1.0", "end-1c").strip()
            if not text:
                return
            win.destroy()
            on_ok(text)

        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=14, pady=12)
        self._button(foot, "确定", ok, True).pack(side="right")
        self._button(foot, "取消", win.destroy).pack(side="right", padx=6)

    def memory_dialog(self) -> None:
        tk = self.tk
        import mem

        project = self.project()
        win = self._window("记住一件事", 540, 500)
        frm = tk.Frame(win, bg=BG)
        frm.pack(fill="both", expand=True, padx=14, pady=10)
        fields: dict[str, Any] = {}

        def label(text: str) -> None:
            tk.Label(frm, text=text, bg=BG, fg=DIM, font=(FONT, 10)).pack(anchor="w", pady=(8, 2))

        def entry() -> Any:
            return tk.Entry(frm, font=(FONT, 10), relief="flat", bg="#0f172a", fg=TEXT, insertbackground=ACCENT,
                            highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)

        type_var = tk.StringVar(value="lesson")
        label("类型")
        row = tk.Frame(frm, bg=BG)
        row.pack(anchor="w")
        for k, v in mem.TYPES.items():
            tk.Radiobutton(row, text=v, value=k, variable=type_var, bg=BG, fg=TEXT, font=(FONT, 10), selectcolor=CARD2,
                           activebackground=BG, activeforeground=ACCENT).pack(side="left")
        label("一句话主题")
        fields["subject"] = entry()
        fields["subject"].pack(fill="x")
        label("事实（不要写密码、密钥、连接串）")
        fact = self._textbox(frm, 4)
        fact.pack(fill="x")
        label("出处（文件:行号#锚点；口述写 user:日期 说明）")
        fields["cite"] = entry()
        fields["cite"].pack(fill="x")
        global_var = tk.BooleanVar(value=project is None)
        tk.Checkbutton(frm, text="所有项目都适用（全局）", variable=global_var, bg=BG, fg=TEXT, font=(FONT, 10),
                       activebackground=BG, selectcolor=CARD2).pack(anchor="w", pady=8)

        def save() -> None:
            subject = fields["subject"].get().strip()
            fact_text = fact.get("1.0", "end-1c").strip()
            if not subject or not fact_text:
                self.say("主题和事实都要写哦", 3)
                return
            cmd = [kitlib.python_exe(self.cfg), str(KIT_ROOT / "tools" / "mem.py"), "add", "--type", type_var.get(),
                   "--subject", subject, "--fact", fact_text]
            if project and not global_var.get() and not project.get("_auto"):
                cmd += ["--project", project["name"]]
            cite = fields["cite"].get().strip() or f"user:{kitlib.today()} 用户口述"
            cmd += ["--cite", cite]
            win.destroy()
            self.run_tool("保存记忆", cmd)

        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=14, pady=12)
        self._button(foot, "保存", save, True).pack(side="right")
        self._button(foot, "取消", win.destroy).pack(side="right", padx=6)


def main() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        Pet(root)
        root.mainloop()
    except Exception:
        detail = traceback.format_exc()
        log = kitlib.DATA_DIR / "logs" / "widget_crash.log"
        kitlib.write_text(log, detail)
        try:
            import tkinter.messagebox as mb

            mb.showerror("桌面机器人启动失败", f"{detail[-800:]}\n\n完整信息：{log}")
        except Exception:
            print(detail, file=sys.stderr)


if __name__ == "__main__":
    main()
