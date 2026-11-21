"""项目管理：看看有哪些项目、把当前目录登记成项目、删除项目。

大多数时候不需要登记：在任何 git 仓库里打开 Copilot，工具包都会按目录自动识别（测试命令、源码目录）。
需要登记的情况：要设置受保护目录、注意事项、风格包，或者自动识别的测试命令不对。

用法：
    python tools/kit_project.py                 # 看当前目录被识别成什么项目
    python tools/kit_project.py list            # 列出登记过的项目
    python tools/kit_project.py add             # 把当前目录登记成项目（自动识别的设置会写进 kit.config.json）
    python tools/kit_project.py add C:/code/xxx --name xxx --style-pack style-tap-backend
    python tools/kit_project.py remove xxx      # 删除登记（不会删除任何代码）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import kitlib


def describe(proj: dict[str, Any]) -> str:
    lines = [f"项目：{proj.get('name')}{'（未登记，自动识别）' if proj.get('_auto') else '（已登记）'}",
             f"  目录：{proj.get('path')}"]
    if proj.get("git_root") and proj.get("git_root") != proj.get("path"):
        lines.append(f"  git 仓库根：{proj['git_root']}")
    for key, cmd in (proj.get("checks") or {}).items():
        lines.append(f"  {key}：{' '.join(cmd)}")
    if proj.get("style_pack"):
        lines.append(f"  风格包：{proj['style_pack']}")
    if proj.get("protected"):
        lines.append(f"  受保护区域：{'、'.join(proj['protected'])}")
    for note in proj.get("notes", []):
        lines.append(f"  注意：{note}")
    return "\n".join(lines)


def load_user_config() -> dict[str, Any]:
    cfg = kitlib.load_json(kitlib.CONFIG_PATH)
    if cfg is None:
        raise SystemExit("还没有 kit.config.json，请先运行 python tools/install.py")
    return cfg


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="项目管理")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list")
    p = sub.add_parser("show")
    p.add_argument("path", nargs="?", default=".")
    p = sub.add_parser("add")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--name")
    p.add_argument("--style-pack", default="")
    p = sub.add_parser("remove")
    p.add_argument("name")
    args = parser.parse_args(argv)

    if args.cmd in (None, "show"):
        path = os.path.abspath(getattr(args, "path", "."))
        proj = kitlib.get_project(kitlib.load_config(), path)
        if not proj:
            print(f"{path} 不在任何项目里（不是 git 仓库，也没有登记）。在这里使用 Copilot 时按普通对话处理。")
            return 0
        print(describe(proj))
        if proj.get("_auto"):
            print("\n需要设置受保护目录、注意事项或修改测试命令时，运行：python tools/kit_project.py add")
        return 0

    if args.cmd == "list":
        cfg = kitlib.load_config()
        projects = cfg.get("projects", [])
        if not projects:
            print("还没有登记任何项目。不登记也能用：在 git 仓库里打开 Copilot 会自动识别。")
        for proj in projects:
            exists = "" if Path(proj.get("path", "")).is_dir() else "（目录不存在！）"
            print(f"- {proj.get('name')}：{proj.get('path')}{exists}")
        return 0

    cfg = load_user_config()
    if args.cmd == "add":
        path = os.path.abspath(args.path)
        if kitlib.find_project(cfg, path):
            print(f"已经登记过：\n{describe(kitlib.find_project(cfg, path) or {})}")
            return 0
        detected = kitlib.detect_project(path)
        if detected is None:
            if not os.path.isdir(path):
                raise SystemExit(f"目录不存在：{path}")
            detected = {"name": Path(path).name, "path": path, "checks": {}, "source_dirs": ["."], "test_dirs": [],
                        "protected": [], "notes": [], "isolated_import_modules": []}
        detected.pop("_auto", None)
        if Path(path).resolve() != Path(detected["path"]).resolve():
            detected["git_root"] = detected["path"]  # 项目在仓库的子目录里（例如 fwd-tap-common/fwd-tap-ingest）
            detected["path"] = path
            detected["name"] = Path(path).name
        if args.name:
            detected["name"] = args.name
        if args.style_pack:
            detected["style_pack"] = args.style_pack
        if any(p.get("name") == detected["name"] for p in cfg.get("projects", [])):
            raise SystemExit(f"项目名 {detected['name']} 已被占用，请用 --name 换一个")
        cfg.setdefault("projects", []).append(detected)
        kitlib.save_json(kitlib.CONFIG_PATH, cfg)
        print("已登记：\n" + describe(detected))
        print(f"\n需要加受保护目录、注意事项时，打开 {kitlib.CONFIG_PATH} 找到这个项目修改。")
        return 0

    if args.cmd == "remove":
        before = len(cfg.get("projects", []))
        cfg["projects"] = [p for p in cfg.get("projects", []) if p.get("name") != args.name]
        if len(cfg["projects"]) == before:
            print(f"没有找到项目：{args.name}")
            return 1
        kitlib.save_json(kitlib.CONFIG_PATH, cfg)
        print(f"已删除登记：{args.name}（代码和记忆都没有动）")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
