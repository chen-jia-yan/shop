"""任务进度状态：总调度代理在每个阶段写一行状态，桌面宠物读取它来换表情和气泡。

状态文件：~/.ai-dev-kit/status.json（只记录阶段和一句话说明，不记录代码和密钥）

阶段（stage）：
    idle       空闲
    analyzing  分析需求、查代码
    asking     有问题要问你
    planning   正在出方案
    waiting    方案已给出，等你回复“确认”
    working    正在改代码
    checking   正在跑验证
    reviewing  正在评审
    fixing     等你决定修哪些 / 正在修
    committing 等你执行提交命令
    done       全部完成
    error      卡住了，需要你看一下

用法：
    python tools/kit_status.py set --stage planning --task "重复上传幂等" --steps "改服务层|改接口|补测试"
    python tools/kit_status.py set --stage working --msg "改 library_kb.py" --step 1   # 总步数从 --steps 推出来
    python tools/kit_status.py show
    python tools/kit_status.py clear
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import kitlib

STATUS_PATH = kitlib.DATA_DIR / "status.json"
STAGES = {
    "idle": "空闲", "analyzing": "分析需求", "asking": "有问题问你", "planning": "出方案",
    "waiting": "等你确认", "working": "改代码", "checking": "跑验证", "reviewing": "评审",
    "fixing": "处理评审意见", "committing": "等你提交", "done": "完成", "error": "卡住了",
}
STALE_SECONDS = 2 * 3600  # 两小时没有更新就当成空闲


def read_status() -> dict[str, Any]:
    data = kitlib.load_json(STATUS_PATH, {}) or {}
    if not data or data.get("stage") not in STAGES:
        return {"stage": "idle", "msg": "", "updated": 0}
    if time.time() - float(data.get("updated", 0)) > STALE_SECONDS and data.get("stage") != "idle":
        data = dict(data, stage="idle", msg="（上次的任务已经很久没有更新）")
    return data


def write_status(stage: str, msg: str = "", **extra: Any) -> dict[str, Any]:
    if stage not in STAGES:
        raise SystemExit(f"不认识的阶段：{stage}，可选：{', '.join(STAGES)}")
    data = {"stage": stage, "label": STAGES[stage], "msg": kitlib.redact(msg, 200), "updated": time.time()}
    # 记下 Copilot 正在哪个项目工作，桌面宠物据此自动跟随；不在项目里运行时（例如从宠物菜单重置）保留上一次的
    previous = kitlib.load_json(STATUS_PATH, {}) or {}
    try:
        cwd = os.getcwd()
        proj = kitlib.get_project(kitlib.load_config(), cwd)
    except OSError:
        cwd, proj = "", None
    if proj:
        data["cwd"], data["project"] = str(proj.get("path") or cwd), str(proj.get("name", ""))
    elif previous.get("cwd"):
        data["cwd"], data["project"] = previous["cwd"], previous.get("project", "")
    steps = extra.pop("steps", None)
    if isinstance(steps, str) and steps.strip():
        data["steps"] = [s.strip() for s in steps.split("|") if s.strip()][:12]
    elif stage != "idle" and previous.get("steps") and (not extra.get("task") or extra.get("task") == previous.get("task")):
        data["steps"] = previous["steps"]
    if data.get("steps") and not extra.get("total"):
        extra["total"] = len(data["steps"])
    if stage == "done" and extra.get("total"):
        extra["step"] = extra["total"]
    elif extra.get("step") is None and previous.get("step") and data.get("steps") and stage != "idle":
        extra["step"] = previous["step"]
    if not extra.get("task") and previous.get("task") and stage != "idle":
        extra["task"] = previous["task"]
    for key, value in extra.items():
        if value not in (None, ""):
            data[key] = kitlib.redact(str(value), 120) if isinstance(value, str) else value
    kitlib.save_json(STATUS_PATH, data)
    return data


def remember_session(cwd: str, cfg: dict[str, Any]) -> None:
    """会话开始时调用：记录当前项目，并把进度重置成空闲（上一个会话的进度已经没意义了）。"""
    proj = kitlib.get_project(cfg, cwd)
    data = {"stage": "idle", "label": STAGES["idle"], "msg": "", "updated": time.time(),
            "cwd": str(proj.get("path") or cwd) if proj else "", "project": str(proj.get("name", "")) if proj else "",
            "session": True}
    kitlib.save_json(STATUS_PATH, data)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="任务进度状态")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("set")
    p.add_argument("--stage", required=True, choices=list(STAGES))
    p.add_argument("--msg", default="")
    p.add_argument("--task", default="")
    p.add_argument("--step", type=int)
    p.add_argument("--total", type=int)
    p.add_argument("--steps", default="", help="用 | 分隔的步骤名，例如 \"改服务层|改接口|补测试\"")
    sub.add_parser("show")
    sub.add_parser("clear")
    args = parser.parse_args(argv)
    if args.cmd == "set":
        data = write_status(args.stage, args.msg, task=args.task, step=args.step, total=args.total, steps=args.steps)
        print(f"状态已更新：{data['label']} {data['msg']}")
    elif args.cmd == "show":
        data = read_status()
        print(f"{STAGES[data['stage']]}  {data.get('msg', '')}")
    else:
        write_status("idle")
        print("状态已清空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
