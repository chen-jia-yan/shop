"""禁删运行器：在“禁删保护”下运行一条命令（跑测试、跑项目脚本时用）。

用法：
    python kit_run.py -- uv run pytest tests/unit -q
    python kit_run.py -- python scripts/import_jp.py --dry-run
    python kit_run.py --check                # 检查保护能不能在当前目录的 Python 环境里生效
    python kit_run.py --allow-delete -- python scripts/cleanup_test_kb.py
                                             # 用户同意删除后才用：删除照常执行，每一次都记日志

做的事：把工具包的 runtime 目录放到 PYTHONPATH 最前面，并设置 AI_DEV_KIT_NODELETE=1。
被启动的 Python 进程会自动加载 runtime/sitecustomize.py：neo4j、SQLAlchemy、MySQL 驱动、
requests / httpx、Azure 搜索等客户端的删除操作会被拦下并报 KitDeleteBlocked（见 runtime/kit_nodelete.py），
避免测试或脚本在没人知道的情况下删掉数据。确实需要删除时：先评估风险告诉用户，用户同意后加 --allow-delete
重新运行（守卫会核对用户是否真的同意过这一条命令）。
写入、查询不受影响。输出原样显示，退出码原样返回。

守卫要求 Copilot 跑测试和项目脚本时都通过本脚本；你自己在命令行运行时不受任何影响。
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys

import kitlib

CHECK_CODE = (
    "import sys, os\n"
    "m = sys.modules.get('kit_nodelete')\n"
    "print('KIT_NODELETE_ACTIVE' if (m and m.is_active()) else 'KIT_NODELETE_INACTIVE')\n"
)


def split_command(parts: list[str]) -> list[str]:
    """`-- uv run pytest` 这样的多段参数原样使用；只给了一整段带空格的字符串时再拆开。"""
    if len(parts) == 1 and " " in parts[0].strip():
        return shlex.split(parts[0], posix=not kitlib.IS_WINDOWS)
    return parts


def run(parts: list[str], cwd: str | None = None, allow_delete: bool = False) -> int:
    cmd = split_command(parts)
    if not cmd:
        print("用法：python kit_run.py -- <命令>")
        return 2
    env = kitlib.nodelete_env(allow_delete=allow_delete)
    env.setdefault("PYTHONUTF8", "1")
    real = [kitlib.resolve_exe(cmd[0])] + cmd[1:]
    kitlib.log_event("kit_run", {"cmd": kitlib.redact(" ".join(cmd), 200), "cwd": cwd or os.getcwd(), "allow_delete": allow_delete})
    if allow_delete:
        print("ai-dev-kit：本次运行允许删除数据（用户已同意），每一次删除都会记到日志 nodelete-*.jsonl。")
    try:
        return subprocess.call(real, cwd=cwd, env=env, shell=False)
    except FileNotFoundError:
        print(f"找不到命令：{cmd[0]}")
        return 127
    except KeyboardInterrupt:
        return 130


def check(cwd: str | None = None) -> int:
    """用当前目录项目的 Python（登记的 python_cmd 或自动识别的）确认保护会生效。"""
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, cwd or ".")
    py = kitlib.expand_cmd(list((project or {}).get("python_cmd") or ["{python}"]), kitlib.base_ctx(cfg, project))
    code, out = kitlib.run(py + ["-c", CHECK_CODE], cwd=cwd or (project or {}).get("path"), timeout=180, nodelete=True)
    active = "KIT_NODELETE_ACTIVE" in out
    print(f"Python：{' '.join(py)}")
    print("禁删保护：" + ("已生效" if active else "没有生效"))
    if not active:
        print("输出：" + out.strip()[-400:])
        print("可能原因：该环境会清空 PYTHONPATH，或者项目里已有同名 sitecustomize。把这段输出发给我。")
    return 0 if active else 1


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        i = argv.index("--")
        head, tail = argv[:i], argv[i + 1:]
    else:
        head, tail = argv, []
    parser = argparse.ArgumentParser(description="在禁删保护下运行命令")
    parser.add_argument("--check", action="store_true", help="检查保护能否在当前项目环境里生效")
    parser.add_argument("--cwd", help="在这个目录里运行")
    parser.add_argument("--allow-delete", action="store_true", help="用户同意删除后才用：放行删除并逐条记日志")
    args, rest = parser.parse_known_args(head)
    if args.check:
        return check(args.cwd)
    return run(rest + tail, args.cwd, args.allow_delete)


if __name__ == "__main__":
    sys.exit(main())
