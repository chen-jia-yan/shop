"""全量体检：一次查出缺的包、命令、配置和版本问题，合并成一条安装命令，不再一个一个试。

为什么需要：缺包时模型常常“装一个 → 跑 → 又缺一个 → 再装”，来回好几轮，既慢又费 token。
这个脚本按代码里的 import 一次性对照项目的虚拟环境，把所有缺的东西列全。

查什么：
    1. Python 包：扫描源码和测试的 import，在项目自己的环境（python_cmd，例如 uv run python）里逐个检查能不能导入；
       已经写在 pyproject 里但没装上的 → 建议同步环境（uv sync），不改 pyproject；
       没写在 pyproject 里的 → 列出来，由你决定装到哪里（装到环境不改 pyproject，还是加进依赖）。
    2. 命令行工具：验收命令里用到的 uv / ruff / pytest / git 等是否在 PATH 里。
    3. 配置项：代码里用 os.environ["X"] 强制读取、当前环境变量里又没有的名字（只列名字，不读 .env，不显示任何值）。
    4. 版本：项目环境的 Python 版本是否满足 requires-python。
    5. 本地安装包：项目目录附近有没有对应的 .whl 文件。

只读，不安装任何东西。用法：
    python kit_env.py scan                 # 当前目录（登记过的项目或 git 仓库）
    python kit_env.py scan --project tap-ai-backend
    python kit_env.py scan --json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import kitlib

IMPORT_TO_PACKAGE = {
    "yaml": "PyYAML", "cv2": "opencv-python", "PIL": "Pillow", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "docx": "python-docx", "pptx": "python-pptx", "fitz": "PyMuPDF", "jwt": "PyJWT",
    "Crypto": "pycryptodome", "magic": "python-magic", "dateutil": "python-dateutil", "MySQLdb": "mysqlclient",
    "pymysql": "PyMySQL", "attr": "attrs", "google": "google-api-core", "jose": "python-jose", "multipart": "python-multipart",
    "socks": "PySocks", "win32api": "pywin32", "win32com": "pywin32", "pythoncom": "pywin32", "OpenSSL": "pyOpenSSL",
    "serial": "pyserial", "usb": "pyusb", "Levenshtein": "python-Levenshtein", "lxml": "lxml", "pydantic_settings": "pydantic-settings",
    "azure": "azure-core", "openpyxl": "openpyxl", "xlrd": "xlrd", "tiktoken": "tiktoken",
}
CHECK_CODE = (
    "import importlib.util, json, sys\n"
    "names = json.loads(sys.argv[1])\n"
    "missing = []\n"
    "for n in names:\n"
    "    try:\n"
    "        ok = importlib.util.find_spec(n) is not None\n"
    "    except Exception:\n"
    "        ok = False\n"
    "    if not ok:\n"
    "        missing.append(n)\n"
    "print('KITENV' + json.dumps({'missing': missing, 'python': list(sys.version_info[:3]), 'exe': sys.executable}))\n"
)
ENV_REQUIRED = re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]\s*\]")
REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", "build", "dist"}


def _py_files(root: Path, dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs or ["."]:
        base = (root / d).resolve()
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if not any(part in SKIP_DIRS for part in p.parts):
                out.append(p)
    return out[:5000]


def local_modules(root: Path, dirs: list[str]) -> set[str]:
    names: set[str] = set()
    for d in set((dirs or []) + ["."]):
        base = root / d
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if p.is_dir() and ((p / "__init__.py").exists() or any(p.glob("*.py"))):
                names.add(p.name)
            elif p.suffix == ".py":
                names.add(p.stem)
    return names


def collect_imports(files: list[Path]) -> tuple[dict[str, list[str]], list[str]]:
    """返回 {顶层模块: [用到它的文件]}，以及强制读取的环境变量名。"""
    found: dict[str, list[str]] = {}
    env_names: list[str] = []
    for f in files:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                found.setdefault(m, [])
                if len(found[m]) < 3:
                    found[m].append(f.name)
        env_names.extend(ENV_REQUIRED.findall(src))
    return found, sorted(set(env_names))


def declared_packages(root: Path) -> tuple[set[str], str]:
    """pyproject 里声明的依赖名（小写、统一连字符）和 requires-python。"""
    path = root / "pyproject.toml"
    if not path.is_file():
        return set(), ""
    text = path.read_text(encoding="utf-8", errors="replace")
    names: set[str] = set()
    requires = ""
    try:
        import tomllib

        data = tomllib.loads(text)
        proj = data.get("project", {}) or {}
        requires = str(proj.get("requires-python", ""))
        deps = list(proj.get("dependencies", []) or [])
        for group in (proj.get("optional-dependencies", {}) or {}).values():
            deps.extend(group)
        for group in (data.get("dependency-groups", {}) or {}).values():
            deps.extend(d for d in group if isinstance(d, str))
        for d in deps:
            m = REQ_NAME.match(str(d))
            if m:
                names.add(m.group(1).lower().replace("_", "-"))
    except (ImportError, ValueError):
        for m in re.finditer(r"^\s*\"([A-Za-z0-9][A-Za-z0-9._\-]*)", text, re.M):
            names.add(m.group(1).lower().replace("_", "-"))
        rp = re.search(r"requires-python\s*=\s*\"([^\"]+)\"", text)
        requires = rp.group(1) if rp else ""
    return names, requires


def _version_ok(version: list[int], spec: str) -> bool:
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.match(r"(>=|<=|==|>|<|~=|!=)\s*([\d.]+)", part)
        if not m:
            continue
        op, raw = m.groups()
        want = [int(x) for x in raw.split(".")]
        have = version[: len(want)]
        checks = {">=": have >= want, "<=": have <= want, "==": have == want, ">": have > want, "<": have < want,
                  "!=": have != want, "~=": have >= want}
        if not checks[op]:
            return False
    return True


def scan(project: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(project["path"])
    dirs = list(project.get("source_dirs", [])) + list(project.get("test_dirs", []))
    files = _py_files(root, dirs)
    imports, env_names = collect_imports(files)
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names) | {"__future__"}
    local = local_modules(root, list(project.get("source_dirs", [])) + list(project.get("test_dirs", [])))
    candidates = sorted(m for m in imports if m not in stdlib and m not in local and m.isidentifier())
    ctx = kitlib.base_ctx(cfg, project)
    py_cmd = kitlib.expand_cmd(list(project.get("python_cmd") or ["{python}"]), ctx)
    result: dict[str, Any] = {"project": project.get("name"), "path": str(root), "python_cmd": py_cmd,
                              "files": len(files), "missing": [], "commands": [], "config": [], "version": "", "wheels": [],
                              "error": ""}
    code, out = kitlib.run(py_cmd + ["-c", CHECK_CODE, json.dumps(candidates)], cwd=root, timeout=300, nodelete=True)
    line = next((ln for ln in out.splitlines() if ln.startswith("KITENV")), "")
    if not line:
        result["error"] = f"没能在项目环境里运行检查（退出码 {code}）：{kitlib.redact(out, 300)}"
        info: dict[str, Any] = {"missing": [], "python": []}
    else:
        info = json.loads(line[len("KITENV"):])
    declared, requires = declared_packages(root)
    for mod in info.get("missing", []):
        pkg = IMPORT_TO_PACKAGE.get(mod, mod)
        key = pkg.lower().replace("_", "-")
        result["missing"].append({"module": mod, "package": pkg, "declared": key in declared or mod.lower() in declared,
                                  "used_in": imports.get(mod, [])})
    if info.get("python") and requires and not _version_ok(list(info["python"]), requires):
        result["version"] = f"项目环境是 Python {'.'.join(map(str, info['python']))}，pyproject 要求 {requires}"
    seen: set[str] = set()
    for cmd in list((project.get("checks", {}) or {}).values()) + [project.get("python_cmd") or []]:
        if not cmd:
            continue
        head = kitlib.expand(str(cmd[0]), ctx)
        if head in seen or "{" in head:
            continue
        seen.add(head)
        if not (Path(head).exists() or shutil.which(head)):
            result["commands"].append(head)
    result["config"] = [n for n in env_names if n not in os.environ][:30]
    names = {m["package"].lower().replace("-", "_") for m in result["missing"]}
    for folder in {root, root.parent, root / "wheels", root.parent / "wheels"}:
        if folder.is_dir():
            for whl in folder.glob("*.whl"):
                if whl.name.split("-")[0].lower() in names:
                    result["wheels"].append(str(whl))
    result["plan"] = plan(result, project)
    return result


def plan(result: dict[str, Any], project: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    uses_uv = (project.get("python_cmd") or [""])[0] == "uv"
    root = result["path"]
    if any(c in ("uv",) for c in result["commands"]):
        steps.append("先装 uv：pip install uv（或按公司要求的方式安装），装完重开终端")
    declared = [m for m in result["missing"] if m["declared"]]
    extra = [m for m in result["missing"] if not m["declared"]]
    if declared:
        steps.append(f"pyproject 里已经声明、但环境里没装上（{'、'.join(m['package'] for m in declared)}）："
                     + (f"cd \"{root}\" 后运行 uv sync" if uses_uv else "在项目环境里重新安装依赖"))
    if result["wheels"]:
        steps.append("这些包有本地安装文件，优先用它们：" + "；".join(f"uv pip install \"{w}\"" if uses_uv else f"pip install \"{w}\""
                                                     for w in result["wheels"]))
    if extra:
        pkgs = " ".join(m["package"] for m in extra)
        steps.append(f"pyproject 里没有声明的包（{'、'.join(m['package'] for m in extra)}）："
                     + (f"只装到环境不改 pyproject：uv pip install {pkgs}" if uses_uv else f"pip install {pkgs}")
                     + "；要长期使用就由你决定是否加进依赖（uv add 会改 pyproject 和 uv.lock）")
    other_cmds = [c for c in result["commands"] if c != "uv"]
    if other_cmds:
        steps.append("缺少命令：" + "、".join(other_cmds) + "（装好后确认在 PATH 里）")
    if result["config"]:
        steps.append("代码里强制读取、但当前环境变量里没有的配置名：" + "、".join(result["config"])
                     + "。如果项目从 .env 读取，请你自己确认 .env 里有这些名字（不要把值发给 AI）")
    if result["version"]:
        steps.append("Python 版本不符合：" + result["version"])
    return steps


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="全量体检：缺包、缺命令、缺配置一次查全")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, args.project)
    if not project:
        print("当前目录不是登记过的项目，也不在 git 仓库里。到项目目录里运行，或者加 --project 名字。")
        return 2
    result = scan(project, cfg)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["plan"] else 1
    print(f"项目：{result['project']}（扫描了 {result['files']} 个 .py 文件；环境：{' '.join(result['python_cmd'])}）")
    if result["error"]:
        print("! " + result["error"])
    if not result["plan"]:
        print("没发现缺的包、命令或配置。")
        return 0
    if result["missing"]:
        print("\n缺的 Python 包：")
        for m in result["missing"]:
            tag = "pyproject 已声明" if m["declared"] else "pyproject 未声明"
            print(f"  - {m['module']} → 包名 {m['package']}（{tag}；用在 {'、'.join(m['used_in'])}）")
    print("\n建议一次做完（装包前先确认）：")
    for i, step in enumerate(result["plan"], 1):
        print(f"  {i}. {step}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
