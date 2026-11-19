"""ai-dev-kit 桌面宠物：一个会动的 Q 版小机器人（也可以换成小猫），陪你看任务进度。

它会做什么
- 读取 ~/.ai-dev-kit/status.json（总调度代理在每个阶段写入），换表情和动作：
    分析需求 → 头顶冒“…”在思考；出方案 → 思考
    等你确认 / 有问题问你 / 等你决定修哪些 / 等你提交 → 跳起来、冒气泡提醒你
    改代码 → 专心敲键盘、齿轮在转；跑验证 → 进度条；评审 → 戴眼镜拿放大镜
    完成 → 星星眼、撒花；卡住了 → 冒汗
- 读取守卫日志：守卫拦住一次危险操作时，举起盾牌告诉你拦住了什么。
- Copilot 在调用工具时，天线（小猫是铃铛）会闪一下；很久没动静会打瞌睡。
- 眼睛会跟着鼠标看。

怎么操作
- 平时不用操作它：在 Copilot 里说需求，它自己跟着进度变；项目也自动跟随 Copilot 所在的目录
- 单击：告诉你现在进行到哪、你该做什么；拖动：移动位置
- 右键：看进度、一键验证、记住一件事；其他工具在“更多工具”，造型大小等在“设置”
- 菜单来自 registry.json（pin 为 true 的放第一层），每次打开都重新读取，新增按钮不用改代码。

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
INK = "#2f3a56"
PAPER = "#fbf8f2"
FONT = "Microsoft YaHei UI" if IS_WINDOWS else "PingFang SC"
FPS_MS = 40

STAGE_TEXT = {
    "idle": "空闲中", "analyzing": "在分析你的需求", "asking": "有问题想问你", "planning": "在写方案",
    "waiting": "方案好了，等你回复“确认”", "working": "在改代码", "checking": "在跑验证",
    "reviewing": "在评审", "fixing": "评审完了，修哪些听你的", "committing": "可以提交啦，命令在会话里",
    "done": "完成啦！", "error": "卡住了，需要你看一下",
}
ATTENTION = {"asking", "waiting", "fixing", "committing"}
RULE_TEXT = {
    "protected-file": "读写密钥文件", "git-write": "git 写操作", "package-install": "安装依赖",
    "locked-file": "改锁定文件", "protected-area": "改同事的模块", "out-of-scope": "越界修改",
    "shell-write": "用命令写文件", "shell-redirect": "用重定向写文件", "ruff-format": "ruff format",
    "dangerous-delete": "递归删除", "forbidden-marker": "加屏蔽标记", "invisible-char": "写入隐形字符",
    "fullwidth-space": "写入全角空格", "custom-deny": "自定义禁止的命令",
}
# 每种状态的样子：眼睛、嘴巴、灯的颜色、动作、肚子屏幕上的图标
LOOKS: dict[str, dict[str, str]] = {
    "idle":       {"eyes": "open",  "mouth": "smile", "light": "#7dd3fc", "anim": "bob",    "icon": "♥"},
    "analyzing":  {"eyes": "up",    "mouth": "flat",  "light": "#60a5fa", "anim": "think",  "icon": "…"},
    "planning":   {"eyes": "up",    "mouth": "flat",  "light": "#60a5fa", "anim": "think",  "icon": "✎"},
    "asking":     {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "waiting":    {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "fixing":     {"eyes": "wide",  "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "?"},
    "committing": {"eyes": "happy", "mouth": "smile", "light": "#fb923c", "anim": "hop",    "icon": "✓"},
    "working":    {"eyes": "focus", "mouth": "flat",  "light": "#4ade80", "anim": "work",   "icon": "⚙"},
    "tool":       {"eyes": "focus", "mouth": "flat",  "light": "#4ade80", "anim": "work",   "icon": "⚙"},
    "checking":   {"eyes": "focus", "mouth": "flat",  "light": "#a78bfa", "anim": "check",  "icon": "✓"},
    "reviewing":  {"eyes": "open",  "mouth": "flat",  "light": "#a78bfa", "anim": "review", "icon": "⌕"},
    "done":       {"eyes": "star",  "mouth": "open",  "light": "#facc15", "anim": "party",  "icon": "★"},
    "error":      {"eyes": "sad",   "mouth": "frown", "light": "#f87171", "anim": "sweat",  "icon": "!"},
    "blocked":    {"eyes": "wide",  "mouth": "o",     "light": "#ef4444", "anim": "shield", "icon": "!"},
    "sleep":      {"eyes": "sleep", "mouth": "smile", "light": "#94a3b8", "anim": "sleep",  "icon": "z"},
}


def load_state() -> dict[str, Any]:
    state = kitlib.load_json(STATE_PATH, {}) or {}
    defaults = {"skin": "robot", "scale": 1.0, "topmost": True, "quiet": False, "project": "", "profile": ""}
    for k, v in defaults.items():
        state.setdefault(k, v)
    return state


def rrect(c: Any, x1: float, y1: float, x2: float, y2: float, r: float, **kw: Any) -> int:
    """圆角矩形（用平滑多边形画）。"""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class Pet:
    def __init__(self, root: Any) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.state = load_state()
        self.cfg = kitlib.load_config()
        self.s = float(self.state["scale"])
        self.t0 = time.time()
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.status: dict[str, Any] = {"stage": "idle"}
        self.status_mtime = 0.0
        self.last_activity = time.time()
        self.last_tool_ping = 0.0
        self.blocked_until = 0.0
        self.blocked_text = ""
        self.tool_running = ""
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.bubble_sticky = False
        self.blink_at = time.time() + 2
        self.particles: list[dict[str, Any]] = []
        self.prev_stage = "idle"
        self.guard_log_pos: dict[str, int] = {}
        self.press: tuple[int, int, int, int] | None = None
        self.moved = False
        self.output_win: Any = None

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

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", lambda _e: self._show_status_now())
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<Button-2>", self.show_menu)  # 部分系统的右键

        self._init_guard_positions()
        if not self.state.get("tour_done"):
            self.tour = [
                "嗨～我是你的开发小助手",
                "你不用操作我：在 Copilot 里直接说需求就行",
                "需要你出手时我会跳起来提醒你",
                "点我一下，我告诉你现在该做什么；右键有更多工具",
            ]
            self.root.after(800, self._next_tip)
        else:
            self.tour = []
            self.say("我在这儿～点我看进度", 4)
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

    def apply_scale(self, s: float, keep_position: bool = True) -> None:
        self.s = s
        self.W, self.H = int(240 * s), int(270 * s)
        x = int(self.state.get("x", self.root.winfo_screenwidth() - self.W - 40))
        y = int(self.state.get("y", self.root.winfo_screenheight() - self.H - 80))
        if keep_position:
            x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def save_state(self) -> None:
        try:
            self.state.update({"x": self.root.winfo_x(), "y": self.root.winfo_y(), "scale": self.s})
            kitlib.save_json(STATE_PATH, self.state)
        except Exception:
            pass

    def say(self, text: str, seconds: float = 5, sticky: bool = False) -> None:
        self.bubble_text = text
        self.bubble_sticky = sticky
        self.bubble_until = time.time() + seconds

    def project(self) -> dict[str, Any] | None:
        """自动跟随 Copilot 当前所在的项目（会话开始和每个阶段都会记录）；不在项目里时返回 None。"""
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
        """每 0.8 秒：读进度、读守卫日志、处理后台工具结果。"""
        try:
            self._poll_status()
            self._poll_guard()
            self._poll_events()
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
        stage = self.status.get("stage", "idle")
        if self.status.get("session") and self.status.get("updated") != getattr(self, "_session_seen", None):
            self._session_seen = self.status.get("updated")
            self.prev_stage = stage
            if self.status.get("project"):
                self.say(f"开新会话啦，项目：{self.status['project']}\n说需求就行，我会跟着进度", 5)
            else:
                self.say("开新会话啦（不在项目里，普通对话）", 4)
            return
        if stage != self.prev_stage:
            self.prev_stage = stage
            if self.state.get("quiet") and stage not in ATTENTION | {"error", "done"}:
                return
            text = STAGE_TEXT.get(stage, stage)
            if self.status.get("msg"):
                text += "\n" + str(self.status["msg"])
            if stage in ATTENTION or stage == "error":
                self.say(text, 3600, sticky=True)
                self.root.bell()
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
            if rec.get("decision") == "deny":
                rule = str(rec.get("rule") or "")
                self.blocked_text = RULE_TEXT.get(rule, rule or "危险操作")
                self.blocked_until = time.time() + 4
                self.say(f"拦住了一次：{self.blocked_text}", 5)

    def _poll_events(self) -> None:
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return
            if ev[0] == "tool_done":
                _, label, cmd, code, out, secs = ev
                self.tool_running = ""
                self.show_output(f"{label}（退出码 {code}，{secs:.1f} 秒）",
                                 "$ " + " ".join(cmd) + "\n\n" + out)
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
                "life": random.uniform(1.2, 2.2), "ch": random.choice("♥★✦♪"),
                "color": random.choice(["#f472b6", "#facc15", "#60a5fa", "#4ade80", "#fb923c"]),
            })

    def draw(self) -> None:
        c, s = self.canvas, self.s
        c.delete("all")
        t = time.time() - self.t0
        stage = self.effective_stage()
        look = LOOKS.get(stage, LOOKS["idle"])
        anim = look["anim"]

        # 身体上下浮动 / 跳跃
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
        cx, ground = self.W / 2, self.H - 16 * s

        def P(x: float, y: float, lift: bool = True) -> tuple[float, float]:
            return cx + x * s, ground + (y + (dy if lift else 0)) * s

        # 眨眼与眼睛朝向
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

        # 影子（跳起来时变小）
        shrink = 1 + hop / 40
        x1, y1 = P(-34 * shrink, -4, lift=False)
        x2, y2 = P(34 * shrink, 4, lift=False)
        c.create_oval(x1, y1, x2, y2, fill="#d9d2c5", outline="")

        light = look["light"]
        if now - self.last_tool_ping < 0.6 and stage not in ("blocked",):
            light = "#ffffff"
        if self.state["skin"] == "cat":
            self.draw_cat(P, t, anim, eyes, look, light, look_dx, look_dy)
        else:
            self.draw_robot(P, t, anim, eyes, look, light, look_dx, look_dy)
        self.draw_effects(P, t, anim, light)
        self.draw_particles(P)
        self.draw_bubble()

    def draw_eyes(self, P: Callable[..., tuple[float, float]], centers: list[tuple[float, float]], kind: str,
                  r: float, color: str, dx: float, dy: float, highlight: bool) -> None:
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
                continue
            elif kind == "happy":
                c.create_arc(x - rs, y - rs * 0.6, x + rs, y + rs * 1.4, start=20, extent=140, style="arc",
                             outline=color, width=max(2, int(3 * s)))
                continue
            elif kind == "star":
                c.create_text(x, y, text="★", fill="#facc15", font=(FONT, -int(20 * s), "bold"))
                continue
            elif kind == "sad":
                c.create_oval(x - rs, y - rs, x + rs, y + rs * 1.1, fill=color, outline="")
                side = -1 if ex < 0 else 1
                c.create_line(x - rs * 1.3, y - rs * (1.3 if side > 0 else 0.6), x + rs * 1.3,
                              y - rs * (0.6 if side > 0 else 1.3), fill=color, width=max(2, int(2.5 * s)))
                continue
            if highlight:
                c.create_oval(x + rs * 0.15, y - rs * 0.75, x + rs * 0.6, y - rs * 0.3, fill="#ffffff", outline="")

    def draw_mouth(self, P: Callable[..., tuple[float, float]], mx: float, my: float, kind: str, color: str,
                   cat: bool = False) -> None:
        c, s = self.canvas, self.s
        x, y = P(mx, my)
        w = max(2, int(2.5 * s))
        if kind == "smile" and cat:
            for off in (-4, 4):
                c.create_arc(x + (off - 4) * s, y - 4 * s, x + (off + 4) * s, y + 4 * s, start=180, extent=180,
                             style="arc", outline=color, width=w)
        elif kind == "smile":
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
        # 脚
        for fx in (-22, 6):
            a, b = P(fx, -14)
            d, e = P(fx + 16, -2)
            c.create_oval(a, b, d, e, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        # 手臂
        swing = math.sin(t * (14 if anim in ("work",) else 2)) * (8 if anim == "work" else 2)
        if anim == "party":
            swing = -14 + math.sin(t * 10) * 4
        for side in (-1, 1):
            sx, sy = P(28 * side, -48)
            hx, hy = P(42 * side, -30 + (swing if side < 0 else -swing))
            c.create_line(sx, sy, hx, hy, fill=INK, width=max(3, int(5 * s)), capstyle="round")
            c.create_oval(hx - 5 * s, hy - 5 * s, hx + 5 * s, hy + 5 * s, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        # 身体和肚子屏幕
        rrect(c, *P(-28, -62), *P(28, -10), 14 * s, fill="#e0e7ff", outline=INK, width=lw)
        rrect(c, *P(-17, -52), *P(17, -22), 7 * s, fill="#1f2a44", outline="")
        icon = self._belly_text(look)
        bx, by = P(0, -37)
        c.create_text(bx, by, text=icon, fill=light, font=(FONT, -int(13 * s), "bold"))
        # 脖子、头、耳朵
        rrect(c, *P(-8, -68), *P(8, -58), 3 * s, fill="#94a3b8", outline=INK, width=max(1, int(2 * s)))
        for ex1, ex2 in ((-54, -46), (46, 54)):
            rrect(c, *P(ex1, -106), *P(ex2, -84), 4 * s, fill="#c7d2fe", outline=INK, width=max(1, int(2 * s)))
        rrect(c, *P(-46, -130), *P(46, -64), 22 * s, fill="#ffffff", outline=INK, width=lw)
        rrect(c, *P(-36, -120), *P(36, -76), 16 * s, fill="#1f2a44", outline="")
        # 脸颊
        for side in (-1, 1):
            a, b = P(29 * side - 5, -74)
            d, e = P(29 * side + 5, -68)
            c.create_oval(a, b, d, e, fill="#fecdd3", outline="")
        self.draw_eyes(P, [(-15, -100), (15, -100)], eyes, 7, "#7df9ff", ldx, ldy, highlight=False)
        self.draw_mouth(P, 0, -85, look["mouth"], "#7df9ff")
        if anim == "review":
            self._glasses(P, [(-15, -100), (15, -100)])
        # 天线
        a, b = P(0, -130)
        d, e = P(0, -144)
        c.create_line(a, b, d, e, fill=INK, width=lw)
        pulse = 1 + 0.25 * math.sin(t * (8 if anim == "hop" else 3))
        bx, by = P(0, -148)
        r = 5.5 * s * pulse
        if anim in ("hop", "shield"):
            c.create_oval(bx - r * 2, by - r * 2, bx + r * 2, by + r * 2, outline=light, width=max(1, int(2 * s)))
        c.create_oval(bx - r, by - r, bx + r, by + r, fill=light, outline=INK, width=max(1, int(2 * s)))

    def draw_cat(self, P: Callable[..., tuple[float, float]], t: float, anim: str, eyes: str,
                 look: dict[str, str], light: str, ldx: float, ldy: float) -> None:
        c, s = self.canvas, self.s
        lw = max(2, int(3 * s))
        fur, cream, pink = "#ffcf94", "#fff4e0", "#ffb4c6"
        # 尾巴（左右摇）
        wag = math.sin(t * (6 if anim in ("hop", "party") else 2)) * 10
        pts = [*P(22, -16), *P(48, -26 + wag / 2), *P(56 + wag / 2, -52), *P(46 + wag, -78)]
        c.create_line(*pts, fill=INK, width=max(6, int(11 * s)), smooth=True, capstyle="round")
        c.create_line(*pts, fill=fur, width=max(4, int(6 * s)), smooth=True, capstyle="round")
        # 身体、肚子、脚
        c.create_oval(*P(-30, -62), *P(30, -4), fill=fur, outline=INK, width=lw)
        c.create_oval(*P(-17, -46), *P(17, -8), fill=cream, outline="")
        bx, by = P(0, -27)
        c.create_text(bx, by, text=self._belly_text(look), fill=INK, font=(FONT, -int(12 * s), "bold"))
        for fx in (-21, 7):
            c.create_oval(*P(fx, -12), *P(fx + 14, -1), fill=cream, outline=INK, width=max(1, int(2 * s)))
        # 前爪（工作时上下动）
        swing = math.sin(t * 14) * 5 if anim == "work" else 0
        if anim == "party":
            swing = -10
        for side in (-1, 1):
            yy = -40 + (swing if side < 0 else -swing)
            c.create_oval(*P(26 * side - 7, yy - 6), *P(26 * side + 7, yy + 6), fill=cream, outline=INK,
                          width=max(1, int(2 * s)))
        # 耳朵（先画，头会盖住底部）
        for side in (-1, 1):
            outer = [*P(-42 * side, -102), *P(-36 * side, -142), *P(-12 * side, -118)]
            inner = [*P(-36 * side, -108), *P(-33 * side, -132), *P(-19 * side, -117)]
            c.create_polygon(outer, fill=fur, outline=INK, width=lw)
            c.create_polygon(inner, fill=pink, outline="")
        # 头
        c.create_oval(*P(-48, -126), *P(48, -54), fill=fur, outline=INK, width=lw)
        for i, xx in enumerate((-8, 0, 8)):
            c.create_line(*P(xx, -124), *P(xx * 0.8, -114 + (2 if i == 1 else 0)), fill="#e08a3c",
                          width=max(2, int(3 * s)), capstyle="round")
        # 项圈和铃铛（铃铛颜色就是状态灯）
        rrect(c, *P(-24, -60), *P(24, -53), 3 * s, fill="#ef4444", outline=INK, width=max(1, int(2 * s)))
        pulse = 1 + 0.2 * math.sin(t * (8 if anim == "hop" else 3))
        bx, by = P(0, -50)
        r = 5 * s * pulse
        c.create_oval(bx - r, by - r, bx + r, by + r, fill=light, outline=INK, width=max(1, int(2 * s)))
        # 脸
        for side in (-1, 1):
            c.create_oval(*P(33 * side - 6, -80), *P(33 * side + 6, -72), fill=pink, outline="")
            for k, yy in enumerate((-78, -72)):
                c.create_line(*P(24 * side, yy), *P(50 * side, yy - 4 + k * 6), fill=INK, width=max(1, int(1.5 * s)))
        self.draw_eyes(P, [(-18, -92), (18, -92)], eyes, 7, INK, ldx, ldy, highlight=True)
        c.create_polygon(*P(-3.5, -81), *P(3.5, -81), *P(0, -77), fill="#f472b6", outline="")
        self.draw_mouth(P, 0, -73, look["mouth"], INK, cat=True)
        if anim == "review":
            self._glasses(P, [(-18, -92), (18, -92)])

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

    def draw_bubble(self) -> None:
        # 提醒类气泡一直显示，直到你点它，或者任务进入下一个阶段
        if self.bubble_sticky and self.status.get("stage") not in ATTENTION | {"error"}:
            self.bubble_sticky = False
            self.bubble_until = min(self.bubble_until, time.time() + 2)
        if not self.bubble_text or (not self.bubble_sticky and time.time() > self.bubble_until):
            self.bubble_text = ""
            return
        c, s = self.canvas, self.s
        x = self.W / 2
        tid = c.create_text(x, 10 * s, text=self.bubble_text, anchor="n", width=self.W - 34 * s,
                            fill=INK, font=(FONT, -int(12.5 * s)), justify="center")
        x1, y1, x2, y2 = c.bbox(tid)
        pad = 8 * s
        bx1, by1, bx2, by2 = x1 - pad, y1 - pad * 0.7, x2 + pad, y2 + pad * 0.7
        rrect(c, bx1, by1, bx2, by2, 12 * s, fill="#ffffff", outline=INK, width=max(2, int(2 * s)), tags="bubble")
        c.create_polygon(x - 7 * s, by2 - 1, x + 7 * s, by2 - 1, x + 2 * s, by2 + 10 * s, fill="#ffffff",
                         outline="", tags="bubble")
        c.create_line(x - 7 * s, by2, x + 2 * s, by2 + 10 * s, x + 7 * s, by2, fill=INK, width=max(2, int(2 * s)), tags="bubble")
        c.tag_raise(tid)

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
        self.root.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")

    def on_release(self, _e: Any) -> None:
        if self.moved:
            self.save_state()
        else:
            self.toggle_status_bubble()
        self.press = None

    # 每个阶段：一句话告诉你“现在该做什么”
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

    def toggle_status_bubble(self) -> None:
        """单击宠物：显示现在的进度，以及你现在要做什么。再点一次收起。"""
        if self.bubble_text:
            self.bubble_text = ""
            self.bubble_sticky = False
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
        lines.append("→ " + self.NEXT_STEP.get(stage, ""))
        proj = self.project()
        lines.append(f"（{proj.get('name') if proj else '不在项目里'}）")
        self.say("\n".join(lines), 10)

    # ------------------------------------------------------------ 菜单

    def show_menu(self, e: Any) -> None:
        """右键菜单：最常用的放第一层，其余收进“更多工具”和“设置”。"""
        tk = self.tk
        self.cfg = kitlib.load_config()
        registry = kitlib.load_json(kitlib.REGISTRY_PATH, {"groups": [], "actions": []}) or {}
        groups = registry.get("groups", [])
        actions = [a for a in registry.get("actions", []) if not a.get("hidden")]
        proj = self.project()
        m = tk.Menu(self.root, tearoff=0, font=(FONT, 10))
        m.add_command(label="◎  现在进行到哪了？", command=self.toggle_status_bubble)
        for a in [a for a in actions if a.get("pin")]:
            m.add_command(label=f"{a.get('icon', '')}  {a.get('label', a.get('id'))}",
                          command=lambda act=a: self.run_action(act))
        m.add_separator()
        more = tk.Menu(m, tearoff=0, font=(FONT, 10))
        for g in groups:
            items = [a for a in actions if a.get("group") == g.get("id") and not a.get("pin")]
            if not items:
                continue
            sub = tk.Menu(more, tearoff=0, font=(FONT, 10))
            for a in items:
                sub.add_command(label=f"{a.get('icon', '')}  {a.get('label', a.get('id'))}",
                                command=lambda act=a: self.run_action(act))
            more.add_cascade(label=g.get("label", g.get("id")), menu=sub)
        more.add_separator()
        more.add_command(label="✎  先给需求打个分（不花额度）", command=self.new_request_dialog)
        m.add_cascade(label="更多工具", menu=more)

        settings = tk.Menu(m, tearoff=0, font=(FONT, 10))
        settings.add_command(label=f"当前项目：{proj.get('name') if proj else '不在项目里'}（自动跟随 Copilot）",
                             state="disabled")
        prof_menu = tk.Menu(settings, tearoff=0, font=(FONT, 10))
        fv = tk.StringVar(value=self.state.get("profile", ""))
        for name, prof in (self.cfg.get("profiles") or {}).items():
            prof_menu.add_radiobutton(label=prof.get("label", name), value=name, variable=fv,
                                      command=lambda v=name: self.set_state("profile", v, f"生成的提示词按“{v}”版本"))
        settings.add_cascade(label="提示词版本（完整 / 省 token）", menu=prof_menu)
        sv = tk.StringVar(value=self.state["skin"])
        settings.add_radiobutton(label="造型：小机器人", value="robot", variable=sv,
                                 command=lambda: self.set_state("skin", "robot", "我是小机器人～"))
        settings.add_radiobutton(label="造型：小猫", value="cat", variable=sv,
                                 command=lambda: self.set_state("skin", "cat", "喵～"))
        size_menu = tk.Menu(settings, tearoff=0, font=(FONT, 10))
        for label, sc in (("小", 0.75), ("中", 1.0), ("大", 1.3)):
            size_menu.add_command(label=label, command=lambda v=sc: (self.apply_scale(v), self.save_state()))
        settings.add_cascade(label="大小", menu=size_menu)
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

    def _show_status_now(self) -> None:
        self.bubble_text = ""
        self.toggle_status_bubble()

    def replay_tour(self) -> None:
        self.state["tour_done"] = False
        self.tour = [
            "你不用操作我：在 Copilot 里直接说需求就行",
            "需要你出手时我会跳起来提醒你",
            "点我一下，我告诉你现在该做什么",
            "右键：看进度、一键验证、记住一件事，其他都在“更多工具”里",
        ]
        self._next_tip()

    def set_state(self, key: str, value: Any, message: str) -> None:
        self.state[key] = value
        self.save_state()
        self.say(message, 3)

    def toggle_topmost(self) -> None:
        self.state["topmost"] = not self.state["topmost"]
        self.root.attributes("-topmost", bool(self.state["topmost"]))
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
            # 没登记的项目用 "."：工具在项目目录里运行，会按目录自动识别
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
                handler = {"new_request": self.new_request_dialog, "status": self.toggle_status_bubble,
                           "memory_add": self.memory_dialog}.get(action.get("builtin", ""))
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

    # ------------------------------------------------------------ 窗口

    def _window(self, title: str, w: int = 520, h: int = 420) -> Any:
        win = self.tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PAPER)
        win.attributes("-topmost", True)
        x = max(0, self.root.winfo_x() - w - 10)
        y = max(0, self.root.winfo_y() + self.H - h)
        win.geometry(f"{w}x{h}+{x}+{y}")
        return win

    def _button(self, parent: Any, text: str, cmd: Callable[[], None], primary: bool = False) -> Any:
        tk = self.tk
        b = tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2", font=(FONT, 10, "bold"),
                      bg="#c2410c" if primary else "#e8e1d3", fg="#ffffff" if primary else INK,
                      activebackground="#9a3412" if primary else "#d9cfbd", padx=12, pady=4, bd=0)
        return b

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
            win = self.output_win = self._window(title, 600, 460)
        bar = tk.Frame(win, bg=PAPER)
        bar.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(bar, text=title, bg=PAPER, fg=INK, font=(FONT, 11, "bold")).pack(side="left")
        box = tk.Text(win, wrap="word", font=("Consolas" if IS_WINDOWS else "Menlo", 10), relief="flat",
                      bg="#fffdf8", fg=INK, padx=10, pady=8, highlightthickness=1, highlightbackground="#d9cfbd")
        box.insert("1.0", text)
        box.pack(fill="both", expand=True, padx=10)
        foot = tk.Frame(win, bg=PAPER)
        foot.pack(fill="x", padx=10, pady=8)
        self._button(foot, "复制全部", lambda: (self.copy(box.get("1.0", "end-1c")), self.say("已复制", 2)), True).pack(side="right")
        self._button(foot, "关闭", win.destroy).pack(side="right", padx=6)

    def ask_text(self, action: dict[str, Any], on_ok: Callable[[str], None]) -> None:
        tk = self.tk
        win = self._window(action.get("label", ""), 460, 260)
        tk.Label(win, text=action.get("description", "") or "请输入内容", bg=PAPER, fg=INK, font=(FONT, 10),
                 wraplength=420, justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        box = tk.Text(win, height=6, wrap="word", font=(FONT, 10), relief="flat", bg="#ffffff", fg=INK,
                      highlightthickness=1, highlightbackground="#d9cfbd")
        box.pack(fill="both", expand=True, padx=12)
        box.focus_set()

        def ok() -> None:
            text = box.get("1.0", "end-1c").strip()
            if not text:
                return
            win.destroy()
            on_ok(text)

        foot = tk.Frame(win, bg=PAPER)
        foot.pack(fill="x", padx=12, pady=10)
        self._button(foot, "确定", ok, True).pack(side="right")
        self._button(foot, "取消", win.destroy).pack(side="right", padx=6)

    def new_request_dialog(self) -> None:
        """说需求：先在本地体检打分（不花额度），再复制给 Copilot 的开工指令。"""
        tk = self.tk
        import prompt_lint

        self.bubble_text = ""
        win = self._window("说需求", 560, 520)
        tk.Label(win, text="用大白话说就行，比如：重复上传同一个文件时不要生成第二份数据", bg=PAPER, fg="#6b7280",
                 font=(FONT, 10)).pack(anchor="w", padx=12, pady=(12, 4))
        box = tk.Text(win, height=6, wrap="word", font=(FONT, 11), relief="flat", bg="#ffffff", fg=INK,
                      highlightthickness=1, highlightbackground="#d9cfbd", padx=8, pady=6)
        box.pack(fill="x", padx=12)
        box.focus_set()
        result = tk.Text(win, height=12, wrap="word", font=(FONT, 10), relief="flat", bg=PAPER, fg=INK, bd=0)
        result.pack(fill="both", expand=True, padx=12, pady=8)
        result.tag_configure("h", font=(FONT, 12, "bold"))
        result.tag_configure("ok", foreground="#15803d")
        result.tag_configure("miss", foreground="#b45309")

        def check() -> None:
            text = box.get("1.0", "end-1c").strip()
            result.configure(state="normal")
            result.delete("1.0", "end")
            if not text:
                return
            rep = prompt_lint.analyze(text)
            result.insert("end", f"需求清晰度：{rep['score']} / 100（{rep['level']}）\n", "h")
            for d in rep["dimensions"]:
                if d["ok"]:
                    result.insert("end", f"✓ {d['label']}  ", "ok")
            result.insert("end", "\n")
            for d in rep["dimensions"]:
                if not d["ok"]:
                    result.insert("end", f"• {d['label']}：{d['question']}\n", "miss")
            if rep["vague"]:
                result.insert("end", f"含糊的说法：{'、'.join(rep['vague'])}\n", "miss")
            if rep["task_count"] > 1:
                result.insert("end", f"看起来有 {rep['task_count']} 件事，AI 会在方案里拆成几步。\n")
            result.insert("end", "\n不用全部补齐：缺的部分 AI 会先查代码，查不到的再问你。")
            result.configure(state="disabled")
            score = rep["score"]
            self.say("说得很清楚！" if score >= 75 else "还可以再具体一点点～" if score >= 50 else "有点笼统，AI 会追问你", 4)

        def start() -> None:
            text = box.get("1.0", "end-1c").strip()
            if not text:
                return
            proj_info = self.project()
            proj = proj_info.get("name") if proj_info else ""
            kickoff = f"请按 /kit-autopilot 流程处理下面的需求" + (f"（项目：{proj}）" if proj else "") + f"：\n{text}"
            self.copy(kickoff)
            win.destroy()
            self.say("开工指令已复制！去 Copilot 里粘贴，方案出来我会提醒你", 7)
            self.burst(5)

        foot = tk.Frame(win, bg=PAPER)
        foot.pack(fill="x", padx=12, pady=(0, 12))
        self._button(foot, "复制开工指令", start, True).pack(side="right")
        self._button(foot, "体检一下", check).pack(side="right", padx=6)
        self._button(foot, "关闭", win.destroy).pack(side="left")

    def memory_dialog(self) -> None:
        tk = self.tk
        import mem

        project = self.project()
        win = self._window("记住一件事", 520, 470)
        frm = tk.Frame(win, bg=PAPER)
        frm.pack(fill="both", expand=True, padx=12, pady=10)
        fields: dict[str, Any] = {}

        def label(text: str) -> None:
            tk.Label(frm, text=text, bg=PAPER, fg=INK, font=(FONT, 10)).pack(anchor="w", pady=(6, 1))

        type_var = tk.StringVar(value="lesson")
        label("类型")
        row = tk.Frame(frm, bg=PAPER)
        row.pack(anchor="w")
        for k, v in mem.TYPES.items():
            tk.Radiobutton(row, text=v, value=k, variable=type_var, bg=PAPER, fg=INK, font=(FONT, 10),
                           selectcolor="#ffffff", activebackground=PAPER).pack(side="left")
        for key, text in (("subject", "一句话主题"), ("cite", "出处（文件:行号#锚点；口述写 user:日期 说明）")):
            label(text)
            fields[key] = tk.Entry(frm, font=(FONT, 10), relief="flat", highlightthickness=1, highlightbackground="#d9cfbd")
            fields[key].pack(fill="x")
            if key == "subject":
                label("事实（不要写密码、密钥、连接串）")
                fact = tk.Text(frm, height=4, wrap="word", font=(FONT, 10), relief="flat", highlightthickness=1,
                               highlightbackground="#d9cfbd")
                fact.pack(fill="x")
        global_var = tk.BooleanVar(value=project is None)
        tk.Checkbutton(frm, text="所有项目都适用（全局）", variable=global_var, bg=PAPER, fg=INK, font=(FONT, 10),
                       activebackground=PAPER, selectcolor="#ffffff").pack(anchor="w", pady=6)

        def save() -> None:
            subject = fields["subject"].get().strip()
            fact_text = fact.get("1.0", "end-1c").strip()
            if not subject or not fact_text:
                self.say("主题和事实都要写哦", 3)
                return
            cmd = [kitlib.python_exe(self.cfg), str(KIT_ROOT / "tools" / "mem.py"), "add", "--type", type_var.get(),
                   "--subject", subject, "--fact", fact_text]
            if project and not global_var.get():
                cmd += ["--project", project["name"]]
            cite = fields["cite"].get().strip() or f"user:{kitlib.today()} 用户口述"
            cmd += ["--cite", cite]
            win.destroy()
            self.run_tool("保存记忆", cmd)

        foot = tk.Frame(win, bg=PAPER)
        foot.pack(fill="x", padx=12, pady=10)
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

            mb.showerror("桌面宠物启动失败", f"{detail[-800:]}\n\n完整信息：{log}")
        except Exception:
            print(detail, file=sys.stderr)


if __name__ == "__main__":
    main()
