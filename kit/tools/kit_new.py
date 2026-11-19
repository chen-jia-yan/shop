"""脚手架：一条命令新增技能、代理、风格卡片、评估用例、桌面宠物按钮或项目，格式自动正确。

这是“动态增量”的入口：以后想加新能力，不用改桌面宠物代码，也不用记格式。

用法：
    python tools/kit_new.py skill  kit-api-doc  "根据接口代码生成接口文档。用于新增或修改接口之后。" [--button 写接口文档]
    python tools/kit_new.py agent  kit-sql-reviewer "只读审查 SQL 和迁移脚本。" --tools read,grep,glob
    python tools/kit_new.py card   style-tap-backend 09-redis-cache "Redis 缓存"
    python tools/kit_new.py pack   style-my-frontend "某前端项目的代码风格包"
    python tools/kit_new.py case   guard-xxx --type guard
    python tools/kit_new.py button my-tool "我的工具" --tool "{kit}/tools/my_tool.py" [--group tools]
    python tools/kit_new.py project my-service "C:/code/my-service" [--style-pack style-tap-backend]
每次新增后会自动运行 kit_lint 检查格式；技能和代理需要重新运行 install.py 才会装进 Copilot。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

import kitlib

ROOT = kitlib.KIT_ROOT
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise SystemExit(f"名字只能用小写字母、数字和连字符：{name}")


def _registry() -> dict:
    return kitlib.load_json(kitlib.REGISTRY_PATH, {"version": 1, "groups": [], "actions": []})


def _add_action(action: dict) -> None:
    data = _registry()
    if any(a.get("id") == action["id"] for a in data.get("actions", [])):
        print(f"registry.json 里已经有按钮 {action['id']}，未重复添加。")
        return
    data.setdefault("actions", []).append(action)
    kitlib.save_json(kitlib.REGISTRY_PATH, data)
    print(f"已在 registry.json 新增按钮：{action['label']}")


def new_skill(args: argparse.Namespace) -> None:
    _check_name(args.name)
    d = ROOT / "skills" / args.name
    if d.exists():
        raise SystemExit(f"已存在：{d}")
    kitlib.write_text(d / "SKILL.md", f"""---
name: {args.name}
description: {args.description}
---

# {args.title or args.name}

## 什么时候用
- （写清触发条件：用户说了什么、遇到什么情况时加载这个技能）

## 步骤
1. （第一步，写成可执行的动作）
2. （第二步）
3. （验证：怎样确认做对了）

## 输出格式
- （要交付什么，最后附核对表）

## 不要做
- （常见错误做法）
""")
    print(f"已创建技能：{d / 'SKILL.md'}")
    if args.button:
        _add_action({"id": args.name, "label": args.button, "group": args.group or "workflow", "icon": "✦",
                     "kind": "prompt_only", "prompt": f"加载技能 /{args.name}，完成下面的任务：\n{{task}}",
                     "description": args.description})


def new_agent(args: argparse.Namespace) -> None:
    _check_name(args.name)
    path = ROOT / "agents" / f"{args.name}.agent.md"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    tools = ", ".join(f'"{t.strip()}"' for t in args.tools.split(",") if t.strip())
    kitlib.write_text(path, f"""---
name: {args.name}
description: {args.description}
tools: [{tools}]
strict-tools-list: true
include-custom-instructions: true
---

你是{args.title or args.name}。

## 职责
- （这个角色负责什么）

## 边界
- 只使用上面列出的工具组；需要别的权限时停下来说明。
- 不读取 .env 等可能含密钥的文件；不执行 git 写操作。

## 工作方式
1. （先做什么）
2. （再做什么）

## 输出
- 结论 + 证据（文件:行号 或命令原始输出）+ 核对表。
""")
    print(f"已创建代理：{path}")
    if args.button:
        _add_action({"id": args.name, "label": args.button, "group": args.group or "workflow", "icon": "◆",
                     "kind": "launch_agent", "agent": args.name, "template": args.template or "implement",
                     "description": args.description})


def new_card(args: argparse.Namespace) -> None:
    pack = ROOT / "style-packs" / args.pack
    if not (pack / "SKILL.md").is_file():
        raise SystemExit(f"风格包不存在：{pack}（先用 pack 子命令创建）")
    path = pack / "patterns" / f"{args.card}.md"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    template = kitlib.read_text(ROOT / "style-packs" / "_template" / "patterns" / "card-template.md")
    kitlib.write_text(path, template.replace("卡片标题", args.title).replace("YYYY-MM-DD", kitlib.today()))
    print(f"已创建卡片：{path}\n记得在 {pack / 'SKILL.md'} 的卡片目录里加上这一行。")


def new_pack(args: argparse.Namespace) -> None:
    _check_name(args.name)
    if not args.name.startswith("style-"):
        raise SystemExit("风格包名字请以 style- 开头，例如 style-my-service")
    pack = ROOT / "style-packs" / args.name
    if pack.exists():
        raise SystemExit(f"已存在：{pack}")
    template = kitlib.read_text(ROOT / "style-packs" / "_template" / "SKILL.md")
    kitlib.write_text(pack / "SKILL.md", template.replace("style-template", args.name).replace("某项目", args.description))
    (pack / "patterns").mkdir(parents=True, exist_ok=True)
    print(f"已创建风格包：{pack}\n下一步：用技能 /kit-extract-pattern 从项目代码里提炼卡片，或运行 kit_new.py card。")


def new_case(args: argparse.Namespace) -> None:
    path = ROOT / "evals" / "cases" / f"{args.name}.json"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    skeletons = {
        "guard": {"payload": {"toolName": "powershell", "toolArgs": {"command": "（命令）"}}, "expect": "deny"},
        "prompt": {"text": "（含糊的需求草稿）", "expect_missing": ["done", "verify"]},
        "static": {"check": "chars", "before": {}, "after": {"src/a.py": "（改动后的内容）"}, "expect": "fail"},
        "output": {"check_name": "tests", "exit_code": 0, "output": "（测试命令的原始输出）", "expect": "fail"},
        "agent": {"agent": "kit-reviewer", "prompt": "（给评审员的输入）", "expect_all": ["（必须出现的关键词正则）"], "expect_none": []},
    }
    case = {"id": args.name, "type": args.type, "title": "（一句话说明这条用例防的是什么）",
            "incident": "（来自哪次事故）", **skeletons[args.type]}
    kitlib.save_json(path, case)
    print(f"已创建用例：{path}，填好内容后运行 python tools/run_evals.py")


def new_button(args: argparse.Namespace) -> None:
    _check_name(args.name)
    action: dict = {"id": args.name, "label": args.label, "group": args.group or "tools", "icon": "▸",
                    "description": args.description or args.label}
    if args.tool:
        action.update({"kind": "run_tool", "command": ["{python}", args.tool] + (args.args or [])})
    elif args.agent:
        action.update({"kind": "launch_agent", "agent": args.agent, "template": args.template or "implement"})
    else:
        action.update({"kind": "prompt_only", "template": args.template or "implement"})
    _add_action(action)


def new_project(args: argparse.Namespace) -> None:
    cfg = kitlib.load_json(kitlib.CONFIG_PATH)
    if cfg is None:
        raise SystemExit("还没有 kit.config.json，先运行 install.py")
    if kitlib.get_project(cfg, args.name):
        raise SystemExit(f"项目 {args.name} 已存在")
    cfg.setdefault("projects", []).append({
        "name": args.name, "path": args.path, "style_pack": args.style_pack or "",
        "python_cmd": ["uv", "run", "python"],
        "checks": {"tests": ["uv", "run", "pytest", "-q"], "lint": ["uv", "run", "ruff", "check", "."],
                   "chars": ["{python}", "{kit}/tools/check_chars.py", "src", "tests"]},
        "source_dirs": ["src"], "test_dirs": ["tests"], "protected": [], "notes": [],
        "isolated_import_modules": [],
    })
    kitlib.save_json(kitlib.CONFIG_PATH, cfg)
    print(f"已登记项目 {args.name}。请打开 kit.config.json 按实际情况修改测试命令和受保护目录。")


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="ai-dev-kit 脚手架")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("skill"); p.add_argument("name"); p.add_argument("description")
    p.add_argument("--title"); p.add_argument("--button"); p.add_argument("--group")
    p = sub.add_parser("agent"); p.add_argument("name"); p.add_argument("description")
    p.add_argument("--tools", default="read,grep,glob"); p.add_argument("--title"); p.add_argument("--button")
    p.add_argument("--group"); p.add_argument("--template")
    p = sub.add_parser("card"); p.add_argument("pack"); p.add_argument("card"); p.add_argument("title")
    p = sub.add_parser("pack"); p.add_argument("name"); p.add_argument("description")
    p = sub.add_parser("case"); p.add_argument("name"); p.add_argument("--type", choices=["guard", "prompt", "static", "output", "agent"], default="guard")
    p = sub.add_parser("button"); p.add_argument("name"); p.add_argument("label"); p.add_argument("--tool")
    p.add_argument("--args", nargs="*"); p.add_argument("--agent"); p.add_argument("--template"); p.add_argument("--group")
    p.add_argument("--description")
    p = sub.add_parser("project"); p.add_argument("name"); p.add_argument("path"); p.add_argument("--style-pack")
    args = parser.parse_args(argv)
    {"skill": new_skill, "agent": new_agent, "card": new_card, "pack": new_pack, "case": new_case,
     "button": new_button, "project": new_project}[args.cmd](args)
    if args.cmd != "project":
        print("\n运行格式检查：")
        subprocess.run([sys.executable, str(ROOT / "tools" / "kit_lint.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
