"""查看或切换模式：随手问 / 工作台 / 项目开发。

平时不用管：登记过的项目里自动是“项目开发”，其他地方是“工作台”；问问题、查资料时
模型会按“随手问”回答。想临时换一种时用这个脚本（桌面机器人的面板上也能点）。

用法：
    python kit_mode.py                 # 显示当前目录的模式
    python kit_mode.py set workbench   # 切到工作台（chat / workbench / project），12 小时后自动恢复
    python kit_mode.py set project --here   # 只对当前目录（及其子目录）生效
    python kit_mode.py auto            # 恢复自动判断

各模式的区别（守卫的红线在任何模式下都不变）：
    随手问   直接回答；要改文件时先问
    工作台   在当前目录里放手做；超过 3 个文件或有风险时先给简短方案；完成后说明怎么验证
    项目开发 完整流程：方案 → 确认 → 锁定范围 → 执行 → 验证 → 评审 → 提交命令
"""

from __future__ import annotations

import argparse
import os
import sys

import kitlib

DESCRIPTIONS = {
    "chat": "直接回答；要改文件时先问你",
    "workbench": "在当前目录里放手做；改动大或有风险时先给简短方案；完成后说明怎么验证",
    "project": "完整流程：方案 → 你确认 → 锁定范围 → 执行 → 验证 → 评审 → 提交命令",
}


def describe(cwd: str) -> str:
    cfg = kitlib.load_config()
    info = kitlib.current_mode(cfg, cwd)
    where = {"project": "登记过的项目", "repo": "没登记的 git 仓库", "other": "普通目录"}[info["kind"]]
    proj = info.get("project") or {}
    lines = [f"当前模式：{info['label']}（{'手动指定' if info['source'] == 'manual' else '自动判断'}）",
             f"位置：{where}" + (f"，项目 {proj.get('name')}" if proj else ""),
             f"含义：{DESCRIPTIONS[info['mode']]}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="查看或切换模式")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("set")
    p.add_argument("mode", choices=list(kitlib.MODES))
    p.add_argument("--here", action="store_true", help="只对当前目录生效")
    sub.add_parser("auto")
    sub.add_parser("show")
    args = parser.parse_args(argv)
    cwd = os.getcwd()
    if args.cmd == "set":
        kitlib.set_mode(args.mode, cwd if args.here else "")
        print(f"已切换为：{kitlib.MODES[args.mode]}（12 小时后自动恢复为自动判断）")
    elif args.cmd == "auto":
        kitlib.set_mode(None)
        print("已恢复自动判断。")
    print(describe(cwd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
