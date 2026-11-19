"""按模板生成任务提示词（R3 格式），供桌面宠物和命令行使用。

模板在 templates/*.md，占位符写成 {{名字}}：
    {{rules}}          通用规则（固定内容，永远放在最前面）
    {{task}}           你填的任务描述
    {{project_block}}  项目、工作目录、风格包
    {{project_name}}   项目名
    {{files}}          本次允许修改的文件（读 scope.json，没有就用参数）
    {{verify_cmd}}     一键验收命令
    {{style_hint}}     风格包提示
    {{output_block}}   按模式（完整 / 省 token）给出的输出要求
    {{ref}}            评审对比的基准（默认 HEAD）
    {{kit}} {{python}} 工具包目录、Python 路径

省 token 的排列方式：固定不变的内容（通用规则、模板骨架）放前面，
每次都变的内容（任务描述）放后面。模型服务端的提示词缓存按“前缀”命中，
开头越稳定，命中越多（OpenAI 的提示词缓存要求前 1024 个 token 完全相同）。

用法：
    python prompt_builder.py --action implement --project tap-ai-backend --task "..." [--files a.py b.py] [--copy]
    python prompt_builder.py --list
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import kitlib

TEMPLATE_DIR = kitlib.KIT_ROOT / "templates"
PLACEHOLDER = re.compile(r"\{\{(\w[\w-]*)\}\}")


def list_actions() -> list[str]:
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.md") if not p.stem.startswith("_"))


def _files_block(project: dict[str, Any] | None, files: list[str] | None) -> str:
    if files:
        return "\n".join(f"- {f}" for f in files)
    if project:
        _, scope = kitlib.find_scope(project.get("path", "."))
        if scope:
            items = list(scope.get("files", [])) + list(scope.get("globs", []))
            if items:
                return "\n".join(f"- {f}" for f in items)
    return "- 【待补充：列出允许修改的文件；先做“计划”这一步可以得到名单】"


def build(action: str, task: str, project_name: str | None = None, profile_name: str | None = None,
          files: list[str] | None = None, ref: str = "HEAD") -> str:
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, project_name) if project_name else None
    profile = kitlib.get_profile(cfg, profile_name)
    path = TEMPLATE_DIR / f"{action}.md"
    if not path.is_file():
        raise SystemExit(f"没有这个模板：{action}（可用：{', '.join(list_actions())}）")
    template = kitlib.read_text(path)
    rules = kitlib.read_text(TEMPLATE_DIR / "_rules.md").strip()
    lean = profile.get("token_mode") == "lean"

    project_block = ""
    style_hint = ""
    verify_cmd = "项目的测试命令"
    if project:
        project_block = f"【工作目录】{project.get('path')}"
        if project.get("git_root") and project.get("git_root") != project.get("path"):
            project_block += f"\n【git 仓库根】{project.get('git_root')}（提交、看状态在这个目录）"
        if project.get("protected"):
            project_block += "\n【受保护区域，不要修改】" + "、".join(project["protected"])
        if project.get("style_pack"):
            style_hint = f"写代码和评审都以风格包 /{project['style_pack']} 为准：先加载它，按相关卡片的“必须 / 禁止 / 检查项”执行。"
        verify_cmd = f"\"{kitlib.python_exe(cfg)}\" \"{kitlib.KIT_ROOT / 'tools' / 'run_checks.py'}\" " + ("" if project.get("_auto") else f" --project {project.get('name')}")
    output_block = ("【输出要求：省 token】只给结论、改动摘要、命令输出里的失败行和汇总行、核对表；不要复述代码，不要重复贴相同的输出。"
                    if lean else "【输出要求】命令都贴原始输出；没把握的地方明确写出来。")

    values = {
        "rules": rules,
        "task": task.strip() or "【待补充：任务描述】",
        "project_block": project_block,
        "project_name": project.get("name", "") if project else "",
        "files": _files_block(project, files),
        "verify_cmd": verify_cmd,
        "style_hint": style_hint,
        "output_block": output_block,
        "ref": ref,
        "kit": str(kitlib.KIT_ROOT),
        "python": kitlib.python_exe(cfg),
    }
    text = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def copy_to_clipboard(text: str) -> bool:
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="按模板生成 R3 提示词")
    parser.add_argument("--action", help="模板名，如 plan / implement / review")
    parser.add_argument("--project")
    parser.add_argument("--profile")
    parser.add_argument("--task", default="")
    parser.add_argument("--task-file")
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--copy", action="store_true", help="复制到剪贴板")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list or not args.action:
        print("可用模板：" + "、".join(list_actions()))
        return 0
    task = kitlib.read_text(args.task_file) if args.task_file else args.task
    text = build(args.action, task, args.project, args.profile, args.files, args.ref)
    print(text)
    if args.copy:
        print("（已复制到剪贴板）" if copy_to_clipboard(text) else "（复制失败：请手动复制上面的内容）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
