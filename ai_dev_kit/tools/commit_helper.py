"""安全提交助手：只生成命令，不执行任何 git 写操作。

做的事：
1. 列出工作区所有改动，按"在本次修改范围内 / 超出范围 / 子模块 / 可能含密钥"分类；
2. 只为范围内的文件生成逐个点名的 git add 命令（绝不生成 git add . 或 git add -A）；
3. 生成提交前核对命令（git diff --cached --stat），以及建议的提交说明；
4. 发现子模块有改动、改动了锁定文件、出现 .env 等文件时给出醒目提醒。

用法：
    python commit_helper.py --project tap-ai-backend [--message "fix: ..."]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import kitlib

SENSITIVE = [".env", ".env.*", "*.pem", "*.key", "providers.json", "secrets.*", "credentials.*"]
LOCKED = ["pyproject.toml", "uv.lock", "poetry.lock", "*.lock", "requirements*.txt"]


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="安全提交助手（只生成命令）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--message", default="", help="提交说明")
    args = parser.parse_args(argv)

    cfg = kitlib.load_config()
    proj = kitlib.get_project(cfg, args.project)
    if not proj:
        print(f"kit.config.json 里没有登记项目：{args.project}")
        return 2
    proj_root = Path(proj["path"])
    git_root = Path(proj.get("git_root") or proj["path"])

    code, branch = kitlib.git(["branch", "--show-current"], git_root)
    branch = branch.strip()
    code, status = kitlib.git(["status", "--porcelain", "--untracked-files=all"], git_root)
    if code != 0:
        print("读取 git status 失败：\n" + status)
        return 2
    code, ls = kitlib.git(["ls-files", "-s"], git_root)
    gitlinks = {ln.split("\t", 1)[1] for ln in ls.splitlines() if ln.startswith("160000") and "\t" in ln}

    scope_root, scope = kitlib.find_scope(proj_root)
    allowed = (list(scope.get("files", [])) + list(scope.get("globs", []))) if scope else None

    in_scope: list[str] = []
    out_scope: list[str] = []
    submodules: list[str] = []
    sensitive: list[str] = []
    locked: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        flag, rel = line[:2], line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        if rel in gitlinks:
            submodules.append(f"{rel}（{flag.strip()}）")
            continue
        if rel.startswith(".ai-dev-kit/") or "/.ai-dev-kit/" in rel:
            continue
        name = rel.rsplit("/", 1)[-1]
        if kitlib.match_any(name, SENSITIVE):
            sensitive.append(rel)
            continue
        if kitlib.match_any(rel, LOCKED):
            locked.append(rel)
        rel_scope = kitlib.rel_posix(git_root / rel, scope_root) if scope_root else rel
        if allowed is None or kitlib.match_any(rel_scope, allowed):
            in_scope.append(rel)
        else:
            out_scope.append(rel)

    print(f"仓库：{git_root}　当前分支：{branch or '（未知）'}")
    if branch in {"develop", "master", "main"}:
        print(f"!! 当前在 {branch} 分支上。规则要求不要直接在这个分支上提交，请先切到功能分支。")
    if scope is None:
        print("提醒：没有设置本次修改范围，下面把所有改动都列为可提交，请逐个确认。")
    if sensitive:
        print("!! 发现可能含密钥的文件，绝对不要提交：")
        for f in sensitive:
            print(f"   - {f}")
    if submodules:
        print("!! 子模块有改动（与本次任务无关，不要添加）：")
        for f in submodules:
            print(f"   - {f}")
    if locked:
        print("!! 改动了依赖或锁定文件，确认是你本人决定的：")
        for f in locked:
            print(f"   - {f}")
    if out_scope:
        print("!! 以下文件超出本次修改范围，默认不添加。先弄清楚是谁、为什么改的：")
        for f in out_scope:
            print(f"   - {f}")
    if not in_scope:
        print("没有可以提交的文件。")
        return 0

    print("\n请在 PowerShell 里逐行执行（由你本人执行，工具包不会替你执行）：")
    print(f"Set-Location '{git_root}'")
    for f in in_scope:
        print(f"git add -- '{f}'")
    print("git --no-pager diff --cached --stat")
    print("\n核对上面的 --stat：只能出现下面这些文件，数量应为 "
          f"{len(in_scope)} 个；有多出来的就先 git restore --staged <文件> 撤出暂存区。")
    for f in in_scope:
        print(f"   · {f}")
    message = args.message or (scope.get("task", "") if scope else "")
    if message:
        safe = message.replace("'", "''")
        print(f"\n确认无误后提交：\ngit commit -m '{safe}'")
    else:
        print("\n确认无误后提交：git commit -m '<类型>: <说明>'（例如 fix: 修复 kg_schema 循环导入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
