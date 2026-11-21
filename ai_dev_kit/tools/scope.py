"""本次修改范围（scope）：把"允许修改的文件名单"变成守卫钩子能强制执行的文件。

写入位置：<项目>/.ai-dev-kit/scope.json，并自动把 .ai-dev-kit/ 加进 .git/info/exclude
（只影响本机，不会被提交）。守卫钩子发现编辑的文件不在名单里，就直接拒绝。

用法：
    python scope.py set --project tap-ai-backend --task "修2：K2a 收尾" \
        --files tests/conftest.py src/tap_ai/application/library_kg.py --globs "tests/unit/test_library_kg*"
    python scope.py add --project tap-ai-backend --files src/tap_ai/api/dto.py
    python scope.py show --project tap-ai-backend
    python scope.py clear --project tap-ai-backend
    python scope.py from-prompt --project tap-ai-backend prompt.txt   # 从提示词的【允许修改的文件】段落读取
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import kitlib


def project_root(name: str) -> tuple[Path, Path]:
    """返回 (git 仓库根, 项目根)。两者可能不同，例如 fwd-tap-ingest 在 fwd-tap-common 仓库里。"""
    proj = kitlib.get_project(kitlib.load_config(), name)
    if not proj:
        raise SystemExit(f"找不到项目：{name}（当前目录不在 git 仓库里，也没有在 kit.config.json 登记）")
    return Path(proj.get("git_root") or proj["path"]), Path(proj["path"])


def scope_path(root: Path) -> Path:
    return root / kitlib.SCOPE_DIRNAME / kitlib.SCOPE_FILENAME


def ensure_excluded(git_root: Path) -> None:
    exclude = git_root / ".git" / "info" / "exclude"
    if not exclude.parent.is_dir():
        return
    text = kitlib.read_text(exclude) if exclude.exists() else ""
    if ".ai-dev-kit/" not in text.split():
        kitlib.write_text(exclude, text.rstrip("\n") + ("\n" if text else "") + ".ai-dev-kit/\n")


def _norm_list(items: list[str] | None, base: Path, root: Path) -> list[str]:
    out: list[str] = []
    for item in items or []:
        item = item.strip().strip("`").strip()
        if not item:
            continue
        p = Path(item)
        if p.is_absolute():
            out.append(kitlib.rel_posix(p, root))
        else:
            out.append(kitlib.rel_posix(base / p, root))
    return sorted(set(out))


def load(root: Path) -> dict[str, Any]:
    return kitlib.load_json(scope_path(root), {}) or {}


def cmd_set(args: argparse.Namespace, add: bool = False) -> int:
    git_root, proj_root = project_root(args.project)
    root = proj_root
    data = load(root) if add else {}
    files = set(data.get("files", [])) | set(_norm_list(args.files, proj_root, root))
    globs = set(data.get("globs", [])) | set(args.globs or [])
    data.update({
        "task": args.task or data.get("task", ""),
        "files": sorted(files),
        "globs": sorted(globs),
        "allow_locked": bool(getattr(args, "allow_locked", False) or data.get("allow_locked", False)),
        "updated": kitlib.now(),
    })
    kitlib.save_json(scope_path(root), data)
    ensure_excluded(git_root)
    print(f"已{'追加' if add else '设置'}修改范围：{scope_path(root)}")
    return cmd_show(args)


def cmd_show(args: argparse.Namespace) -> int:
    _, root = project_root(args.project)
    data = load(root)
    if not data:
        print("当前没有设置修改范围（守卫不限制修改哪些文件，只做通用拦截）。")
        return 0
    print(f"任务：{data.get('task', '')}")
    print("允许修改的文件：")
    for f in data.get("files", []):
        exists = (root / f).exists()
        print(f"  - {f}{'' if exists else '（新文件）'}")
    for g in data.get("globs", []):
        print(f"  - {g}（通配）")
    if data.get("allow_locked"):
        print("  ! 允许修改依赖和锁定文件")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    _, root = project_root(args.project)
    path = scope_path(root)
    if path.exists():
        path.unlink()
        print("已清除修改范围。")
    else:
        print("本来就没有设置修改范围。")
    return 0


SECTION = re.compile(r"【本次允许修改的文件】(.*?)(?=【|\Z)", re.S)
PATH_IN_LINE = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]+|[\w./\\-]+/\*+[\w.*]*")


def cmd_from_prompt(args: argparse.Namespace) -> int:
    text = kitlib.read_text(args.prompt_file)
    m = SECTION.search(text)
    if not m:
        print("提示词里没有找到【本次允许修改的文件】段落。")
        return 1
    files: list[str] = []
    globs: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("-*0123456789.、 ").strip()
        if not line or line.startswith("其他文件"):
            continue
        for token in PATH_IN_LINE.findall(line):
            (globs if "*" in token else files).append(token.replace("\\", "/"))
    if not files and not globs:
        print("段落里没有识别出文件路径。")
        return 1
    args.files, args.globs = files, globs
    task = re.search(r"【任务\s*([^】]*)】", text)
    args.task = args.task or (task.group(1).strip() if task else "")
    return cmd_set(args)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="本次修改范围")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("set", "add"):
        p = sub.add_parser(name)
        p.add_argument("--project", default=".")
        p.add_argument("--task")
        p.add_argument("--files", nargs="*")
        p.add_argument("--globs", nargs="*")
        p.add_argument("--allow-locked", action="store_true", help="允许修改 pyproject.toml / uv.lock 等")
    for name in ("show", "clear"):
        p = sub.add_parser(name)
        p.add_argument("--project", default=".")
    p = sub.add_parser("from-prompt")
    p.add_argument("--project", default=".")
    p.add_argument("--task")
    p.add_argument("--allow-locked", action="store_true")
    p.add_argument("prompt_file")
    args = parser.parse_args(argv)
    if args.cmd == "set":
        return cmd_set(args)
    if args.cmd == "add":
        return cmd_set(args, add=True)
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "clear":
        return cmd_clear(args)
    return cmd_from_prompt(args)


if __name__ == "__main__":
    sys.exit(main())
