"""ai-dev-kit 桌面机器人：左边是会动的小机器人，右边是一块科技感的数据面板（HUD）。

机器人
- 读取 ~/.ai-dev-kit/status.json（总调度在每个阶段写入），换表情和动作：
    分析 / 出方案 → 思考；改代码 → 敲键盘、齿轮转；跑验证 → 进度条；评审 → 戴眼镜拿放大镜
    完成 → 星星眼、撒花；卡住了 → 冒汗；守卫拦下危险操作 → 举盾牌
- 该你了（等你确认、等你回答、等你决定是否删除数据、一轮做完）→ 跳起来，面板亮提醒卡。
- 很久没动静会打瞌睡；眼睛跟着鼠标看。

右侧面板（数据都来自本机真实记录，没有示例数据；没用过时显示“还没有数据”）
- 顶部：当前模式（随手问 / 工作台 / 项目开发）、统计范围（今天 / 近 7 天）、时间
- 数据条：AI 干活时长、等你的时长、token（拿不到真实值时标“估算”）、对话轮数
- 任务进度：分段进度条，每段是方案里的一步，当前步在闪
- 排行榜：时间都去哪了 / 用到的技能和代理 / 工具调用 / token 去向，每 6 秒自动轮播，条形图会动态重排
- 提醒卡：轮到你时停止轮播，显示要你做什么，并给出一键复制的回复（例如“确认”“同意”）

操作
- 单击机器人：现在进行到哪、你该做什么；拖动：移动位置
- 单击面板上的小圆点：切换排行榜；单击“今天 / 近7天”：切换统计范围
- 右键：常用工具、模式切换、面板显示 / 收起、设置（菜单来自 registry.json，新增按钮不用改代码）

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
    "delete-rejected": "你拒绝过的删除", "nodelete-tamper": "改删除保护开关",
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
    defaults = {"scale": 1.0, "topmost": True, "quiet": False, "profile": "", "hud": True, "span": "today"}
    for k, v in defaults.items():
        state.setdefault(k, v)
    state.pop("skin", None)  # 旧版本的小猫造型已经去掉
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


# ================================================================= 右侧面板


class Hud:
    """右侧数据面板：只读本机真实数据，没有数据时显示空状态。"""

    def __init__(self, pet: "Pet") -> None:
        self.pet = pet
        self.summary: dict[str, Any] = {}
        self.channels: list[dict[str, Any]] = []
        self.loaded_at = 0.0
        self.ch_index = 0
        self.ch_switched = time.time()
        self.bars: dict[str, dict[str, float]] = {}
        self.hits: list[tuple[float, float, float, float, Callable[[], None]]] = []
        self.hover = False
        self.alert: dict[str, Any] = {}
        self.alert_key = ""
        self.mode_label = ""
        self.load_error = ""

    # -------------------------------------------------- 数据

    def refresh(self) -> None:
        if time.time() - self.loaded_at < 2.0:
            return
        self.loaded_at = time.time()
        try:
            import kit_metrics

            self.summary = kit_metrics.summary(self.pet.state.get("span", "today"))
            self.channels = kit_metrics.channels(self.summary, top=5)
            self.load_error = ""
        except Exception as exc:  # 统计坏了不影响机器人
            self.summary, self.channels = {}, []
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
        self._refresh_alert()

    def _refresh_alert(self) -> None:
        """轮到你的事情，按重要程度只取一件。"""
        alert: dict[str, Any] = {}
        try:
            pending = kitlib.pending_deletes()
        except Exception:
            pending = []
        stage = str(self.pet.status.get("stage", "idle"))
        if pending:
            req = pending[-1]
            risk = str(req.get("risk", ""))
            level = next((ln.split("：", 1)[1] for ln in risk.splitlines() if ln.startswith("风险：")), "")
            alert = {"key": "del:" + str(req.get("digest")), "title": "等你决定：要删除数据",
                     "body": f"风险 {level or '未评估'} · " + str(req.get("command", "")),
                     "color": BAD if level == "高" else WARN,
                     "buttons": [("复制“同意”", "同意，可以删"), ("复制“不要删”", "不要删")],
                     "detail": risk}
        elif stage in ATTENTION:
            msg = str(self.pet.status.get("msg") or "")
            buttons: list[tuple[str, str]] = []
            if stage == "waiting":
                buttons = [("复制“确认”", "确认")]
            elif stage == "committing":
                buttons = [("复制“已提交”", "已提交，继续下一步")]
            alert = {"key": f"stage:{stage}:{self.pet.status.get('updated')}", "title": "该你了：" + STAGE_TEXT[stage],
                     "body": msg or NEXT_STEP.get(stage, ""), "color": WARN, "buttons": buttons}
        else:
            try:
                import kit_metrics

                note = kit_metrics.read_alert()
            except Exception:
                note = {}
            if note:
                kind = str(note.get("kind", ""))
                title = {"permission_prompt": "该你了：需要你确认一个操作",
                         "elicitation_dialog": "该你了：有问题需要你回答"}.get(kind, "该你了：这一轮做完了")
                alert = {"key": f"note:{note.get('ts')}", "title": title,
                         "body": str(note.get("msg") or "去 Copilot 窗口看看"), "color": WARN if kind != "turn_done" else ACCENT,
                         "buttons": []}
        if alert and alert["key"] != self.alert_key:
            self.alert_key = alert["key"]
            if not self.pet.state.get("quiet") or alert["color"] != ACCENT:
                try:
                    self.pet.root.bell()
                except Exception:
                    pass
        if not alert:
            self.alert_key = ""
        self.alert = alert

    def wants_attention(self) -> bool:
        return bool(self.alert) and self.alert.get("color") != ACCENT

    # -------------------------------------------------- 交互

    def click(self, x: float, y: float) -> bool:
        for x1, y1, x2, y2, cb in reversed(self.hits):
            if x1 <= x <= x2 and y1 <= y <= y2:
                cb()
                return True
        if self.channels and not self.alert:
            self.next_channel()
            return True
        return False

    def next_channel(self, step: int = 1) -> None:
        if not self.channels:
            return
        self.ch_index = (self.ch_index + step) % len(self.channels)
        self.ch_switched = time.time()
        self.bars = {}

    def set_channel(self, i: int) -> None:
        self.ch_index = i
        self.ch_switched = time.time()
        self.bars = {}

    def toggle_span(self) -> None:
        span = "week" if self.pet.state.get("span", "today") == "today" else "today"
        self.pet.state["span"] = span
        self.pet.save_state()
        self.loaded_at = 0
        self.bars = {}
        self.refresh()

    # -------------------------------------------------- 绘制

    def draw(self, c: Any, x0: float, y0: float, w: float, h: float, t: float) -> None:
        s = self.pet.s
        self.refresh()
        self.hits = []
        x1, y1, x2, y2 = x0, y0, x0 + w, y0 + h
        # 外框：呼吸的描边；轮到你时变成橙色
        glow = (math.sin(t * 2.4) + 1) / 2
        edge = mix(LINE, self.alert.get("color", ACCENT) if self.wants_attention() else ACCENT, 0.25 + 0.35 * glow)
        rrect(c, x1, y1, x2, y2, 16 * s, fill=BG, outline=edge, width=max(1, int(1.5 * s)))
        # 背景网格 + 慢慢往下扫的扫描线
        gy = y1 + 10 * s
        while gy < y2 - 8 * s:
            c.create_line(x1 + 10 * s, gy, x2 - 10 * s, gy, fill=GRID)
            gy += 12 * s
        scan = y1 + 12 * s + ((t * 18 * s) % (h - 24 * s))
        c.create_line(x1 + 12 * s, scan, x2 - 12 * s, scan, fill=mix(GRID, ACCENT, 0.18))

        pad = 12 * s
        cx1, cx2 = x1 + pad, x2 - pad
        y = y1 + pad
        y = self._header(c, cx1, cx2, y, t)
        y = self._stats(c, cx1, cx2, y + 6 * s)
        y = self._progress(c, cx1, cx2, y + 8 * s, t)
        remain = y2 - pad - (y + 8 * s)
        if self.alert:
            self._alert_card(c, cx1, cx2, y + 8 * s, remain, t)
        else:
            self._channel(c, cx1, cx2, y + 8 * s, remain, t)

    def _header(self, c: Any, x1: float, x2: float, y: float, t: float) -> float:
        s = self.pet.s
        live = mix(OK, "#0b3b2e", (math.sin(t * 3) + 1) / 4)
        c.create_oval(x1, y + 4 * s, x1 + 7 * s, y + 11 * s, fill=live, outline="")
        c.create_text(x1 + 12 * s, y + 7.5 * s, text="AI·DEV HUD", anchor="w", fill=TEXT, font=(MONO, -int(11 * s), "bold"))
        mx = x1 + 92 * s
        if self.mode_label:
            label = self.mode_label
            tw = text_px(label, 10 * s) + 14 * s
            rrect(c, mx, y, mx + tw, y + 15 * s, 7 * s, fill=CARD2, outline=mix(CARD2, ACCENT2, 0.6))
            c.create_text(mx + tw / 2, y + 7.5 * s, text=label, fill=ACCENT2, font=(FONT, -int(10 * s)))
        clock = time.strftime("%H:%M")
        c.create_text(x2, y + 7.5 * s, text=clock, anchor="e", fill=DIM, font=(MONO, -int(10.5 * s)))
        span = "今天" if self.pet.state.get("span", "today") == "today" else "近7天"
        sw = text_px(span, 10 * s) + 14 * s
        sx2 = x2 - 40 * s
        rrect(c, sx2 - sw, y, sx2, y + 15 * s, 7 * s, fill=CARD2, outline=LINE)
        c.create_text(sx2 - sw / 2, y + 7.5 * s, text=span, fill=TEXT, font=(FONT, -int(10 * s)))
        self.hits.append((sx2 - sw, y, sx2, y + 15 * s, self.toggle_span))
        return y + 15 * s

    def _stats(self, c: Any, x1: float, x2: float, y: float) -> float:
        import kit_metrics

        s = self.pet.s
        d = self.summary or {}
        est = d.get("token_estimated") or d.get("token_mixed")
        tiles = [
            ("AI 干活", kit_metrics.fmt_sec(d.get("ai_sec", 0)) if d.get("ai_sec") else "—", ACCENT),
            ("等你", kit_metrics.fmt_sec(d.get("wait_sec", 0)) if d.get("wait_sec") else "—", WARN),
            ("Token" + ("·估算" if est else ""), kit_metrics.fmt_tok(d.get("token_total", 0)) if d.get("token_total") else "—", ACCENT2),
            ("对话", f"{d.get('turns', 0)} 轮" if d.get("turns") else "—", OK),
        ]
        gap = 6 * s
        tw = (x2 - x1 - gap * 3) / 4
        th = 38 * s
        for i, (label, value, color) in enumerate(tiles):
            tx = x1 + i * (tw + gap)
            rrect(c, tx, y, tx + tw, y + th, 8 * s, fill=CARD, outline=LINE)
            c.create_rectangle(tx + 6 * s, y + 1, tx + 22 * s, y + 3 * s, fill=color, outline="")
            c.create_text(tx + 7 * s, y + 12 * s, text=fit(label, tw - 10 * s, 9 * s), anchor="w", fill=DIM,
                          font=(FONT, -int(9 * s)))
            c.create_text(tx + 7 * s, y + 27 * s, text=fit(value, tw - 10 * s, 12 * s), anchor="w",
                          fill=TEXT if value != "—" else FAINT, font=(MONO, -int(12 * s), "bold"))
        return y + th

    def _progress(self, c: Any, x1: float, x2: float, y: float, t: float) -> float:
        s = self.pet.s
        st = self.pet.status
        stage = str(st.get("stage", "idle"))
        task = str(st.get("task") or "")
        steps = list(st.get("steps") or [])
        total = int(st.get("total") or len(steps) or 0)
        step = int(st.get("step") or 0)
        h = 40 * s
        rrect(c, x1, y, x2, y + h, 8 * s, fill=CARD, outline=LINE)
        if not task and stage == "idle":
            c.create_text(x1 + 10 * s, y + 13 * s, text="任务进度", anchor="w", fill=DIM, font=(FONT, -int(9.5 * s)))
            c.create_text(x1 + 10 * s, y + 28 * s, text="暂无进行中的任务 · 在 Copilot 里说需求即可", anchor="w",
                          fill=FAINT, font=(FONT, -int(10 * s)))
            return y + h
        head = fit(task or STAGE_TEXT.get(stage, stage), x2 - x1 - 80 * s, 10.5 * s)
        c.create_text(x1 + 10 * s, y + 11 * s, text=head, anchor="w", fill=TEXT, font=(FONT, -int(10.5 * s), "bold"))
        tag = STAGE_SHORT.get(stage, stage)
        color = WARN if stage in ATTENTION else BAD if stage == "error" else OK if stage == "done" else ACCENT
        c.create_text(x2 - 10 * s, y + 11 * s, text=tag, anchor="e", fill=color, font=(FONT, -int(10 * s), "bold"))
        bx1, bx2, by = x1 + 10 * s, x2 - 10 * s, y + 23 * s
        if total > 0:
            done = total if stage == "done" else max(0, step - 1)
            gap = 3 * s
            seg = (bx2 - bx1 - gap * (total - 1)) / total
            for i in range(total):
                sx = bx1 + i * (seg + gap)
                if i < done:
                    fill = OK
                elif i == done and stage != "done":
                    fill = mix(CARD2, color, 0.45 + 0.45 * (math.sin(t * 4) + 1) / 2)
                else:
                    fill = CARD2
                rrect(c, sx, by, sx + seg, by + 6 * s, 3 * s, fill=fill, outline="")
            name = steps[min(max(step, 1), len(steps)) - 1] if steps and step else ""
            sub = f"第 {min(max(step, 1), total)}/{total} 步" + (f" · {name}" if name else "")
            if stage == "done":
                sub = f"全部 {total} 步完成"
        else:
            # 没有分步信息：用一条流动的光带表示正在进行
            rrect(c, bx1, by, bx2, by + 6 * s, 3 * s, fill=CARD2, outline="")
            pos = (t * 0.45) % 1.0
            gx = bx1 + (bx2 - bx1) * pos
            rrect(c, max(bx1, gx - 30 * s), by, min(bx2, gx + 30 * s), by + 6 * s, 3 * s, fill=color, outline="")
            sub = str(st.get("msg") or STAGE_TEXT.get(stage, ""))
        c.create_text(bx1, y + 35 * s, text=fit(sub, bx2 - bx1, 9 * s), anchor="w", fill=DIM, font=(FONT, -int(9 * s)))
        return y + h

    def _channel(self, c: Any, x1: float, x2: float, y: float, h: float, t: float) -> None:
        import kit_metrics

        s = self.pet.s
        rrect(c, x1, y, x2, y + h, 8 * s, fill=CARD, outline=LINE)
        if not self.channels:
            c.create_text((x1 + x2) / 2, y + h / 2, text="统计暂时读不到" + (f"\n{self.load_error}" if self.load_error else ""),
                          fill=FAINT, font=(FONT, -int(10 * s)), justify="center")
            return
        nonempty = [i for i, ch in enumerate(self.channels) if ch["items"]]
        if (not self.hover and time.time() - self.ch_switched > ROTATE_SECONDS and nonempty):
            following = [i for i in nonempty if i > self.ch_index] or nonempty
            self.set_channel(following[0])
        self.ch_index %= len(self.channels)
        ch = self.channels[self.ch_index]
        c.create_text(x1 + 10 * s, y + 11 * s, text=ch["title"], anchor="w", fill=TEXT, font=(FONT, -int(10.5 * s), "bold"))
        # 页码小圆点（可点击切换）
        for i in range(len(self.channels)):
            dx = x2 - 10 * s - (len(self.channels) - 1 - i) * 11 * s
            r = 3 * s if i == self.ch_index else 2.2 * s
            fill = ACCENT if i == self.ch_index else (FAINT if self.channels[i]["items"] else LINE)
            c.create_oval(dx - r, y + 11 * s - r, dx + r, y + 11 * s + r, fill=fill, outline="")
            self.hits.append((dx - 5 * s, y + 4 * s, dx + 5 * s, y + 18 * s, lambda k=i: self.set_channel(k)))
        # 轮播倒计时细线
        if nonempty and not self.hover:
            frac = min(1.0, (time.time() - self.ch_switched) / ROTATE_SECONDS)
            c.create_line(x1 + 10 * s, y + 21 * s, x1 + 10 * s + (x2 - x1 - 20 * s) * frac, y + 21 * s, fill=mix(CARD, ACCENT, 0.5))
        items = ch["items"]
        if not items:
            hint = {"time": "用一轮对话后，这里显示时间花在哪个项目、等了你多久",
                    "caps": "用到技能或代理后，这里显示排行",
                    "tools": "模型调用工具后，这里显示调用次数排行",
                    "tokens": "一轮对话结束后，这里显示 token 去向"}.get(ch["key"], "还没有数据")
            c.create_text((x1 + x2) / 2, y + (h + 22 * s) / 2, text="还没有数据\n" + hint, fill=FAINT,
                          font=(FONT, -int(9.5 * s)), justify="center", width=x2 - x1 - 30 * s)
            return
        top = y + 28 * s
        row_h = min(22 * s, (h - 34 * s) / max(5, len(items)))
        rank_w, value_w = 18 * s, 58 * s
        bar_x1 = x1 + 10 * s + rank_w
        bar_x2 = x2 - 10 * s - value_w
        vmax = max(v for _, v in items) or 1.0
        for i, (label, value) in enumerate(items):
            key = f"{ch['key']}:{label}"
            anim = self.bars.setdefault(key, {"w": 0.0, "y": float(i)})
            anim["w"] += (value / vmax - anim["w"]) * 0.16
            anim["y"] += (i - anim["y"]) * 0.2
            ry = top + anim["y"] * row_h
            color = PALETTE[i % len(PALETTE)]
            # 名次
            if i < 3:
                c.create_oval(x1 + 10 * s, ry + row_h / 2 - 7 * s, x1 + 24 * s, ry + row_h / 2 + 7 * s,
                              fill=mix(CARD, color, 0.35), outline="")
            c.create_text(x1 + 17 * s, ry + row_h / 2, text=str(i + 1), fill=TEXT if i < 3 else DIM,
                          font=(MONO, -int(9.5 * s), "bold"))
            # 条形：底槽 + 渐变色条 + 末端高光
            bh = row_h * 0.64
            by1, by2 = ry + (row_h - bh) / 2, ry + (row_h + bh) / 2
            rrect(c, bar_x1, by1, bar_x2, by2, bh / 2, fill=CARD2, outline="")
            bw = max(bh, (bar_x2 - bar_x1) * anim["w"])
            rrect(c, bar_x1, by1, bar_x1 + bw, by2, bh / 2, fill=mix(color, BG, 0.25), outline="")
            rrect(c, bar_x1, by1, bar_x1 + bw * 0.55, by2, bh / 2, fill=color, outline="")
            c.create_oval(bar_x1 + bw - bh * 0.8, by1 + 1, bar_x1 + bw - 1, by2 - 1, fill=mix(color, "#ffffff", 0.45), outline="")
            inside = text_px(label, 9.5 * s) + 12 * s < bw
            if inside:
                c.create_text(bar_x1 + 7 * s, ry + row_h / 2, text=label, anchor="w", fill=BG, font=(FONT, -int(9.5 * s), "bold"))
            else:
                c.create_text(bar_x1 + bw + 5 * s, ry + row_h / 2, text=fit(label, bar_x2 - bar_x1 - bw - 6 * s, 9.5 * s),
                              anchor="w", fill=TEXT, font=(FONT, -int(9.5 * s)))
            unit = ch["unit"]
            shown = (kit_metrics.fmt_sec(value) if unit == "sec" else kit_metrics.fmt_tok(value) if unit == "tok"
                     else f"{int(value)} 次")
            c.create_text(x2 - 10 * s, ry + row_h / 2, text=shown, anchor="e", fill=TEXT, font=(MONO, -int(9.5 * s)))

    def _alert_card(self, c: Any, x1: float, x2: float, y: float, h: float, t: float) -> None:
        s = self.pet.s
        a = self.alert
        color = a.get("color", WARN)
        pulse = (math.sin(t * 5) + 1) / 2
        rrect(c, x1, y, x2, y + h, 8 * s, fill=mix(CARD, color, 0.08), outline=mix(LINE, color, 0.5 + 0.5 * pulse),
              width=max(1, int(2 * s)))
        c.create_rectangle(x1 + 1, y + 8 * s, x1 + 4 * s, y + h - 8 * s, fill=color, outline="")
        c.create_text(x1 + 12 * s, y + 13 * s, text=fit(a.get("title", ""), x2 - x1 - 24 * s, 11 * s), anchor="w",
                      fill=color, font=(FONT, -int(11 * s), "bold"))
        body = str(a.get("body", ""))
        body = body if len(body) <= 96 else body[:96] + "…"
        c.create_text(x1 + 12 * s, y + 26 * s, text=body, anchor="nw", fill=TEXT, width=x2 - x1 - 24 * s,
                      font=(FONT, -int(9.5 * s)))
        buttons = list(a.get("buttons", []))
        if a.get("detail"):
            buttons.append(("看风险评估", ""))
        bx = x1 + 12 * s
        by = y + h - 24 * s
        for label, reply in buttons:
            bw = text_px(label, 9.5 * s) + 18 * s
            primary = reply and reply == buttons[0][1]
            rrect(c, bx, by, bx + bw, by + 17 * s, 8 * s, fill=color if primary else CARD2,
                  outline=color if not primary else "")
            c.create_text(bx + bw / 2, by + 8.5 * s, text=label, fill=BG if primary else TEXT, font=(FONT, -int(9.5 * s), "bold"))
            if reply:
                cb = (lambda r=reply: (self.pet.copy(r), self.pet.say(f"已复制“{r}”，去 Copilot 里粘贴发送", 4)))
            else:
                cb = (lambda d=a.get("detail", ""): self.pet.show_output("删除前的风险评估", d))
            self.hits.append((bx, by, bx + bw, by + 17 * s, cb))
            bx += bw + 6 * s


# ================================================================= 机器人


class Pet:
    ROBOT_W = 230
    PANEL_W = 350
    H = 290

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
        self.hud = Hud(self)

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
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<Button-2>", self.show_menu)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda _e: setattr(self.hud, "hover", False))

        self._init_guard_positions()
        if not self.state.get("tour_done"):
            self.tour = [
                "嗨～我是你的开发小助手",
                "右边是今天的数据：时间、token、用到的能力",
                "轮到你的时候我会跳起来，面板上有一键复制的回复",
                "点我看进度，右键有工具和模式切换",
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

    @property
    def robot_w(self) -> float:
        return self.ROBOT_W * self.s

    def apply_scale(self, s: float, keep_position: bool = True) -> None:
        self.s = s
        self.W = int((self.ROBOT_W + (self.PANEL_W if self.state.get("hud", True) else 0)) * s)
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
            self.state.update({"x": self.root.winfo_x(), "y": self.root.winfo_y(), "scale": self.s})
            kitlib.save_json(STATE_PATH, self.state)
        except Exception:
            pass

    def say(self, text: str, seconds: float = 5, sticky: bool = False) -> None:
        self.bubble_text = text
        self.bubble_sticky = sticky
        self.bubble_until = time.time() + seconds

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
        if self.hud.wants_attention() and stage not in ATTENTION:
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
        self.hud.loaded_at = 0
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
            if stage in ATTENTION or stage == "error":
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
            if rec.get("decision") == "deny" and rule not in QUIET_RULES:
                self.blocked_text = RULE_TEXT.get(rule, rule or "危险操作")
                self.blocked_until = time.time() + 4
                self.say(f"拦住了一次：{self.blocked_text}", 5)
            elif rule == "delete-needs-consent":
                self.hud.loaded_at = 0  # 马上刷新提醒卡

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
        if self.state.get("hud", True):
            self.hud.draw(c, self.robot_w + 2 * s, 10 * s, self.PANEL_W * s - 8 * s, self.Hpx - 20 * s, t)
        self.draw_bubble()

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

    def draw_bubble(self) -> None:
        if self.bubble_sticky and self.status.get("stage") not in ATTENTION | {"error"}:
            self.bubble_sticky = False
            self.bubble_until = min(self.bubble_until, time.time() + 2)
        if not self.bubble_text or (not self.bubble_sticky and time.time() > self.bubble_until):
            self.bubble_text = ""
            return
        c, s = self.canvas, self.s
        x = self.robot_w / 2
        tid = c.create_text(x, 10 * s, text=self.bubble_text, anchor="n", width=self.robot_w - 30 * s,
                            fill=INK, font=(FONT, -int(12 * s)), justify="center")
        x1, y1, x2, y2 = c.bbox(tid)
        pad = 8 * s
        bx1, by1, bx2, by2 = x1 - pad, y1 - pad * 0.7, x2 + pad, y2 + pad * 0.7
        rrect(c, bx1, by1, bx2, by2, 12 * s, fill="#ffffff", outline=INK, width=max(2, int(2 * s)))
        c.create_polygon(x - 7 * s, by2 - 1, x + 7 * s, by2 - 1, x + 2 * s, by2 + 10 * s, fill="#ffffff", outline="")
        c.create_line(x - 7 * s, by2, x + 2 * s, by2 + 10 * s, x + 7 * s, by2, fill=INK, width=max(2, int(2 * s)))
        c.tag_raise(tid)

    # ------------------------------------------------------------ 鼠标

    def on_motion(self, e: Any) -> None:
        self.hud.hover = bool(self.state.get("hud", True)) and e.x > self.robot_w

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

    def on_release(self, e: Any) -> None:
        if self.moved:
            self.save_state()
        elif self.state.get("hud", True) and e.x > self.robot_w:
            self.hud.click(e.x, e.y)
        else:
            self.toggle_status_bubble()
        self.press = None

    def toggle_status_bubble(self) -> None:
        """单击机器人：显示现在的进度，以及你现在要做什么。再点一次收起。"""
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
        if self.hud.alert:
            lines.append("→ " + str(self.hud.alert.get("title", "")))
        else:
            lines.append("→ " + NEXT_STEP.get(stage, ""))
        self.say("\n".join(lines), 10)

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
        m.add_command(label="✎  说需求（先体检，不花额度）", command=self.new_request_dialog)
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
        hv = tk.BooleanVar(value=bool(self.state.get("hud", True)))
        settings.add_checkbutton(label="显示右侧数据面板", variable=hv, command=self.toggle_hud)
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
        for label, sc in (("小", 0.8), ("中", 1.0), ("大", 1.25)):
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

    def set_mode(self, mode: str) -> None:
        kitlib.set_mode(None if mode == "auto" else mode, "")
        self.hud.loaded_at = 0
        label = "自动判断" if mode == "auto" else kitlib.MODES[mode]
        self.say(f"模式：{label}" + ("（12 小时后恢复自动）" if mode != "auto" else "") + "\n新开的会话生效", 4)

    def set_span(self, span: str) -> None:
        self.state["span"] = span
        self.save_state()
        self.hud.loaded_at = 0
        self.hud.bars = {}

    def toggle_hud(self) -> None:
        self.state["hud"] = not self.state.get("hud", True)
        self.apply_scale(self.s)
        self.save_state()

    def replay_tour(self) -> None:
        self.state["tour_done"] = False
        self.tour = [
            "右边是今天的数据：时间、token、用到的能力",
            "排行榜每 6 秒换一个，点小圆点也能切换",
            "轮到你的时候我会跳起来，面板上有一键复制的回复",
            "右键：工具、模式切换、面板设置",
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
                           "memory_add": self.memory_dialog, "toggle_hud": self.toggle_hud}.get(action.get("builtin", ""))
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

    def new_request_dialog(self) -> None:
        """说需求：边写边体检（本地打分，不花额度），写好后复制开工指令。"""
        tk = self.tk
        import prompt_lint

        self.bubble_text = ""
        win = self._window("说需求", 580, 560)
        tk.Label(win, text="用大白话说就行，比如：重复上传同一个文件时不要生成第二份数据", bg=BG, fg=DIM,
                 font=(FONT, 10)).pack(anchor="w", padx=14, pady=(14, 6))
        box = self._textbox(win, 6)
        box.pack(fill="x", padx=14)
        box.focus_set()
        meter = tk.Canvas(win, height=34, bg=BG, highlightthickness=0)
        meter.pack(fill="x", padx=14, pady=(10, 0))
        result = tk.Text(win, height=12, wrap="word", font=(FONT, 10), relief="flat", bg=BG, fg=TEXT, bd=0,
                         padx=2, pady=4)
        result.pack(fill="both", expand=True, padx=14, pady=6)
        result.tag_configure("ok", foreground=OK)
        result.tag_configure("miss", foreground=WARN)
        result.tag_configure("dim", foreground=DIM)
        pending: list[str] = []

        def draw_meter(score: int, level: str) -> None:
            meter.delete("all")
            w = max(200, meter.winfo_width())
            color = OK if score >= 75 else WARN if score >= 50 else BAD
            meter.create_text(0, 9, text="需求清晰度", anchor="w", fill=DIM, font=(FONT, 9))
            meter.create_text(w, 9, text=f"{score} / 100 · {level}", anchor="e", fill=color, font=(MONO, 10, "bold"))
            rrect(meter, 0, 20, w, 30, 5, fill=CARD2, outline="")
            if score:
                rrect(meter, 0, 20, max(10, w * score / 100), 30, 5, fill=color, outline="")

        def check() -> None:
            pending.clear()
            text = box.get("1.0", "end-1c").strip()
            result.configure(state="normal")
            result.delete("1.0", "end")
            if not text:
                draw_meter(0, "还没写")
                result.configure(state="disabled")
                return
            rep = prompt_lint.analyze(text)
            draw_meter(int(rep["score"]), str(rep["level"]))
            for d in rep["dimensions"]:
                if d["ok"]:
                    result.insert("end", f"✓ {d['label']}  ", "ok")
            result.insert("end", "\n\n")
            for d in rep["dimensions"]:
                if not d["ok"]:
                    result.insert("end", f"• {d['label']}：{d['question']}\n", "miss")
            if rep["vague"]:
                result.insert("end", f"• 含糊的说法：{'、'.join(rep['vague'])}\n", "miss")
            if rep["task_count"] > 1:
                result.insert("end", f"• 看起来有 {rep['task_count']} 件事，AI 会在方案里拆开。\n", "dim")
            result.insert("end", "\n不用全部补齐：缺的部分 AI 会先查代码，查不到的一次问你。", "dim")
            result.configure(state="disabled")

        def on_key(_e: Any = None) -> None:
            token = str(time.time())
            pending.append(token)
            win.after(350, lambda: check() if pending and pending[-1] == token else None)

        box.bind("<KeyRelease>", on_key)
        win.after(100, lambda: draw_meter(0, "还没写"))

        def start() -> None:
            text = box.get("1.0", "end-1c").strip()
            if not text:
                return
            proj_info = self.project()
            proj = proj_info.get("name") if proj_info else ""
            kickoff = ("请按 /kit-autopilot 流程处理下面的需求" + (f"（项目：{proj}）" if proj else "")
                       + "，同类改动一次列全再改，问题一次问完：\n" + text) if proj else text
            self.copy(kickoff)
            win.destroy()
            self.say("已复制！去 Copilot 里粘贴，轮到你时我会提醒", 6)
            self.burst(5)

        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=14, pady=(0, 14))
        self._button(foot, "复制给 Copilot", start, True).pack(side="right")
        self._button(foot, "关闭", win.destroy).pack(side="left")

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
