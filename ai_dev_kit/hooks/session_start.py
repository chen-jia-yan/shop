"""sessionStart 钩子：会话开始时，把“现在是什么模式 + 当前项目要点 + 能用的能力 + 已验证的记忆”注入上下文。

这样每次新开会话都不用再手动交代：在哪个项目、用哪种节奏做事、哪些地方是共享模块、
有哪些技能和代理可以用、上次踩过什么坑。

控制 token 的做法：
- 只注入一份精简摘要（默认最多 3600 字），详细内容留在技能、参考资料和记忆文件里，按需再读；
- 内容不含时间戳等每次都变的东西，方便模型服务端的前缀缓存命中；
- 记忆只注入“引用位置仍然有效”的条目；
- 能力目录每个能力只占一行（做什么 + 一句典型说法）。
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

TOOLS = kitlib.KIT_ROOT / "tools"

RED_LINES = [
    "不读、不打印 .env 和 .env.example；不在回答里出现密钥、密码、数据库地址",
    "数据可以写；删除数据要先评估风险告诉用户，再直接运行，守卫会当场请用户确认，不能乱删；删缓存、构建目录等中间产物不用问；测试和脚本在 kit_run.py 下运行（守卫会自动套上）",
    "不用 git add .；不在 develop / master 上直接改",
    "共享模块可以改，但先记录测试基线、保持接口兼容，改完对比基线",
    "不伪造验证结果：没运行就说没运行，0 个测试算失败",
]

DELETE_RULES = (
    "要删除数据时：先说清楚 ① 要删什么（语句或接口）② 范围（先做只读计数，告诉用户会删多少条）③ 能不能恢复 "
    "④ 删之前建议做什么（备份、软删除、换测试库）。说完直接运行删除命令，守卫会当场弹确认框，用户同意就接着做，不用停下来等；"
    "如果守卫拦下并说明要等用户在对话里回复“同意”（旧做法），就照它说的等用户回复后再执行同一条命令；"
    "测试和脚本里确实要删时用 kit_run.py --allow-delete 重跑（同样会弹确认框）。用户不同意就跳过这一步继续别的，不要换写法绕过。"
)

BATCH_RULES = (
    "一次做完：动手前先把同一类的事情列全，再一次做完，不要做一点、跑一次、再做一点。包括："
    "缺的包和命令（先 kit_env.py scan 查全，合成一条命令）；要加或改的配置项、参数（列成清单一次改完）；"
    "要改的调用点、同类写法（先用一次搜索找全，再批量改）；测试和检查的失败（一次看全所有失败，分类后一起修，最后再跑一次）；"
    "要问用户的问题（合并成一次提问）。只有后一步确实取决于前一步的结果时才分步，并说明原因。"
    "缺的是配置项时只说名字，不读取或打印它的值。"
)

MODE_RULES = {
    "chat": "随手问：直接回答，给出处；不主动改文件，要改先问。",
    "workbench": ("工作台：在当前目录里放手做。改动不超过 3 个文件且没有风险时直接做，做完说明改了什么、怎么验证；"
                  "更大或有风险（删改大量内容、装包、碰共享数据）时先给 3~5 行方案再动手。"),
    "project": ("项目开发：开发类需求按 /kit-autopilot 走（需求卡 → 方案 → 用户回复“确认” → 锁定范围 → 执行 → 验证 → 评审 → 给提交命令）；"
                "问问题、查代码这类不改文件的请求直接回答，不走流程。"),
}

CAPABILITY_RULES = (
    "用能力的规矩：用户不需要知道有哪些技能和代理，由你判断。只读的（查、解释、评审、出方案）判断合适就直接用，"
    "并在开头说一句“我用 X 来…”；会改文件或运行命令的，先说“我打算用 X，因为…，可以吗？”，用户同意再用。"
    "用户消息末尾如果附了“[ai-dev-kit 提示] 可能适用：…”，那只是本地关键词匹配的参考，不合适就忽略。"
)


def _tool(name: str) -> str:
    return f"python \"{TOOLS / name}\""


def _project_lines(project: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if project.get("_auto"):
        checks = project.get("checks", {})
        lines.append(f"项目：{project.get('name')}（{project.get('path')}，未登记，已按目录自动识别）")
        lines.append("自动识别的验收命令：" + ("、".join(f"{k}={' '.join(v)}" for k, v in checks.items() if k != "collect") or "无"))
        lines.append(f"一键验证（在项目目录里运行）：{_tool('run_checks.py')}")
        lines.append(f"要长期在这里开发、或需要设置共享模块，可以建议登记：{_tool('kit_project.py')} add")
        return lines
    lines.append(f"项目：{project.get('name')}（{project.get('path')}）")
    if project.get("style_pack"):
        lines.append(f"风格包：写代码或评审前先加载技能 /{project['style_pack']}。")
    checks = project.get("checks", {})
    if checks:
        lines.append(f"验收命令已登记（{'、'.join(checks.keys())}），运行：{_tool('run_checks.py')} --project {project.get('name')}")
    shared, shared_allow = kitlib.shared_areas(project)
    if shared:
        state = kitlib.read_shared_state(project)
        base = state.get("baseline") or {}
        status = (f"已记录基线（通过 {base.get('passed', 0)}，失败 {base.get('failed', 0)}）" if base
                  else f"还没有基线，改之前先运行：{_tool('run_checks.py')} --project {project.get('name')} --shared-baseline")
        lines.append("共享模块（可以改，保持接口兼容，不能改坏）：" + "、".join(shared) + f"；{status}")
        if shared_allow:
            lines.append("其中这些文件不需要基线就能改：" + "、".join(shared_allow))
    locked = project.get("locked_areas", [])
    if locked:
        lines.append("锁定区域（一个字都不能改）：" + "、".join(locked))
    for note in project.get("notes", [])[:8]:
        lines.append(f"注意：{note}")
    return lines


def _catalog_lines(cfg: dict[str, Any]) -> list[str]:
    try:
        import kit_catalog

        text = kit_catalog.digest(kit_catalog.load(), max_chars=1400)
    except Exception as exc:  # 目录坏了不影响会话
        kitlib.log_event("session_start", {"where": "catalog", "error": repr(exc)[:200]})
        return []
    if not text:
        return []
    return ["可以用的技能和代理（完整说明在各自的 SKILL.md / .agent.md 里）：", text, CAPABILITY_RULES]


def build_context(cwd: str, cfg: dict[str, Any]) -> str:
    profile = kitlib.get_profile(cfg, os.environ.get("AI_DEV_KIT_PROFILE"))
    info = kitlib.current_mode(cfg, cwd)
    kind = info["kind"]
    project = info.get("project")
    lines: list[str] = ["[ai-dev-kit 会话信息]"]
    source = "用户手动指定" if info["source"] == "manual" else "按位置自动判断"
    lines.append(f"模式：{info['label']}（{source}）。{MODE_RULES[info['mode']]}")
    lines.append("不管哪种模式：用户只是提问、查资料、看代码时，按随手问直接回答。")
    if profile.get("token_mode", "full") == "lean":
        lines.append("输出：省 token。只给结论、改动摘要、命令关键输出行（失败行和汇总行）和核对表；不要复述代码。")
    else:
        lines.append("输出：完整。验证时贴原始关键输出和核对表。")
    lines.append("红线（守卫会直接拦，不要尝试绕过）：" + "；".join(RED_LINES) + "。")

    if project:
        lines.extend(_project_lines(project, cfg))
    elif kind == "other":
        lines.append("当前不在 git 仓库里：写文档、整理资料、写脚本、写技能都可以直接做；用户明确要做项目开发时再走开发流程。")

    nd = cfg.get("nodelete", {}) or {}
    if nd.get("enabled", True):
        lines.append(f"运行测试或脚本：{_tool('kit_run.py')} -- <原命令>（自带禁删保护：没经用户同意的删除会被拦下并报 KitDeleteBlocked，数据不会被删）。")
        lines.append(DELETE_RULES)
    lines.append(BATCH_RULES + f" 体检：{_tool('kit_env.py')} scan")
    lines.append(f"写给别人用的技能：用 {_tool('kit_skill.py')} check / add / try 先校验、挂到本机、试用，再打包交付。")

    scope_root, scope = kitlib.find_scope(cwd)
    if scope:
        files = list(scope.get("files", [])) + list(scope.get("globs", []))
        lines.append(f"本次任务：{scope.get('task', '（未填写）')}")
        lines.append("本次只允许修改：" + ("、".join(files[:20]) if files else "（名单为空：不允许修改任何文件）")
                     + ("……" if len(files) > 20 else ""))

    if (cfg.get("capabilities", {}) or {}).get("auto_suggest", True):
        lines.extend(_catalog_lines(cfg))

    mem_cfg = cfg.get("memory", {}) or {}
    project_name = project.get("name") if project and not project.get("_auto") else None
    project_path = project.get("path") if project else cwd
    digest = mem.digest(project_name, project_path, max_chars=int(mem_cfg.get("digest_max_chars", 1200)),
                        max_items=int(mem_cfg.get("digest_max_items", 8)))
    if digest:
        lines.append("相关记忆（已核对引用仍有效；有疑问时打开引用位置确认）：")
        lines.append(digest)

    text = "\n".join(lines)
    limit = int((cfg.get("session_context", {}) or {}).get("max_chars", 3600))
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
        try:  # 告诉桌面机器人：新会话在哪里开始（失败不影响会话）
            import kit_status

            kit_status.remember_session(cwd, cfg)
        except Exception as exc:
            kitlib.log_event("session_start", {"where": "status", "error": repr(exc)[:200]})
        try:
            import kit_metrics

            kit_metrics.record("session_start", payload, cwd=cwd)
        except Exception as exc:
            kitlib.log_event("session_start", {"where": "metrics", "error": repr(exc)[:200]})
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
