"""sessionStart 钩子：会话开始时，自动把"当前项目的要点 + 本次修改范围 + 已验证的记忆"注入上下文。

这样每次新开会话都不用再手动交代：项目用哪个风格包、测试命令是什么、
哪些目录是同事的、上次踩过什么坑。

控制 token 的做法：
- 只注入一份精简摘要（默认最多 1800 字），详细内容留在技能和记忆文件里，按需再读；
- 内容不含时间戳等每次都变的东西，方便模型服务端的前缀缓存命中；
- 记忆只注入"引用位置仍然有效"的条目（参考 GitHub Copilot Memory 的即时验证做法）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kitlib  # 必须在上一行把 tools 目录加进 sys.path 之后再导入
import mem


def build_context(cwd: str, cfg: dict[str, Any]) -> str:
    profile = kitlib.get_profile(cfg, os.environ.get("AI_DEV_KIT_PROFILE"))
    project = kitlib.find_project(cfg, cwd) or kitlib.detect_project(cwd)
    lines: list[str] = ["[ai-dev-kit 会话信息]"]
    mode = profile.get("token_mode", "full")
    if mode == "lean":
        lines.append("模式：省 token。回答只给结论、改动摘要、命令关键输出行（失败行和汇总行）和核对表；不要复述代码。")
    else:
        lines.append("模式：完整。按 R3 规则贴原始输出和核对表。")
    if project:
        lines.append("流程：开发类需求默认按 /kit-autopilot 执行（先出方案，用户回复“确认”后才改文件；每次修复前先问用户）。")

    if project and project.get("_auto"):
        checks = project.get("checks", {})
        lines.append(f"项目：{project.get('name')}（{project.get('path')}，未登记，已按目录自动识别）")
        lines.append("自动识别的验收命令：" + ("、".join(f"{k}={' '.join(v)}" for k, v in checks.items() if k != "collect") or "无"))
        lines.append(f"一键验证（在项目目录里运行，不用写项目名）：python \"{kitlib.KIT_ROOT / 'tools' / 'run_checks.py'}\"")
        lines.append(f"如果用户要长期在这里开发、或需要设置受保护目录，可以建议登记：python \"{kitlib.KIT_ROOT / 'tools' / 'kit_project.py'}\" add")
    elif project:
        lines.append(f"项目：{project.get('name')}（{project.get('path')}）")
        if project.get("style_pack"):
            lines.append(f"风格包：写代码或评审前先加载技能 /{project['style_pack']}。")
        checks = project.get("checks", {})
        if checks:
            names = "、".join(checks.keys())
            lines.append(f"验收命令已登记（{names}），运行：python \"{kitlib.KIT_ROOT / 'tools' / 'run_checks.py'}\" --project {project.get('name')}")
        if project.get("protected"):
            lines.append("受保护区域（不要修改，除非用户明确授权）：" + "、".join(project["protected"]))
        for note in project.get("notes", [])[:6]:
            lines.append(f"注意：{note}")
    else:
        lines.append("当前不在项目里（不是 git 仓库）：按普通助手回答问题、写文档、查资料，不走开发流程；用户明确要写代码时再按 /kit-autopilot。")

    scope_root, scope = kitlib.find_scope(cwd)
    if scope:
        files = list(scope.get("files", [])) + list(scope.get("globs", []))
        lines.append(f"本次任务：{scope.get('task', '（未填写）')}")
        lines.append("本次只允许修改：" + ("、".join(files[:20]) if files else "（名单为空：不允许修改任何文件）")
                     + ("……" if len(files) > 20 else ""))

    mem_cfg = cfg.get("memory", {}) or {}
    max_chars = int(mem_cfg.get("digest_max_chars", 1200))
    max_items = int(mem_cfg.get("digest_max_items", 8))
    project_name = project.get("name") if project else None
    project_path = project.get("path") if project else cwd
    digest = mem.digest(project_name, project_path, max_chars=max_chars, max_items=max_items)
    if digest:
        lines.append("相关记忆（已核对引用仍有效；用之前若有疑问请打开引用位置确认）：")
        lines.append(digest)

    text = "\n".join(lines)
    limit = int((cfg.get("session_context", {}) or {}).get("max_chars", 1800))
    if len(text) > limit:
        text = text[:limit] + "\n……（摘要已截断）"
    return text


def main() -> int:
    result: dict[str, Any] = {}
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
        cfg = kitlib.load_config()
        cwd = str(payload.get("cwd") or os.getcwd())
        try:  # 告诉桌面宠物：新会话在哪个项目里（失败不影响会话）
            import kit_status

            kit_status.remember_session(cwd, cfg)
        except Exception as exc:
            kitlib.log_event("session_start", {"where": "status", "error": repr(exc)[:200]})
        if (cfg.get("session_context", {}) or {}).get("enabled", True):
            result = {"additionalContext": build_context(cwd, cfg)}
    except Exception as exc:  # 注入失败不影响会话启动
        kitlib.log_event("session_start", {"error": repr(exc)[:300]})
        result = {}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if "--preview" in sys.argv:
        kitlib.setup_console()
        print(build_context(os.getcwd(), kitlib.load_config()))
        sys.exit(0)
    sys.exit(main())
