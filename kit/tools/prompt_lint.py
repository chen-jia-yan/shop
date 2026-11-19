"""提示词体检（离线、零 token）：检查一段需求描述缺了什么，给出具体追问，再补全成 R3 提示词。

为什么先做本地体检：GitHub 官方的省额度建议里写到，提示词含糊时，代理要自己猜意图、
多读文件、反复返工，最费 token；而写清"目标、相关上下文、完成标准"几乎不增加 token，
却能大幅减少返工次数。所以在发给模型之前先把需求补完整，是成本最低的一步。

检查 8 个维度：目标、位置、背景、约束、完成标准、验证方式、输出要求、示例。
另外识别含糊词（"优化一下""看看""等等"）和"一句话里塞了好几件事"。

用法：
    python prompt_lint.py "帮我优化一下上传接口"
    python prompt_lint.py --file draft.txt --r3 --project tap-ai-backend
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Any

import kitlib


@dataclass
class Dimension:
    key: str
    label: str
    weight: int
    pattern: re.Pattern[str]
    question: str
    example: str


DIMENSIONS = [
    Dimension("goal", "目标", 20,
              re.compile(r"(实现|新增|增加|添加|修复|修改|改成|改为|删除|移除|重构|迁移|编写|写一个|写个|生成|排查|定位|评审|审查|检查|整理|设计|支持|接入|拆分|合并|替换|升级|补充|implement|add|fix|remove|refactor|migrate|write|review)", re.I),
              "这次具体要做成什么？用一句话说出动作和对象。",
              "例：给 /tap/ai/library/kb/documents 新增 delete 接口"),
    Dimension("location", "位置", 15,
              re.compile(r"([\w\-]+/[\w\-./]+|\b[\w\-]+\.(py|ts|js|md|json|toml|sql|yaml|yml)\b|模块|目录|文件|接口|函数|方法|类|路由|表|字段|页面|组件)", re.I),
              "涉及哪些文件、模块或接口？不知道具体文件时，说出模块或接口路径也行。",
              "例：src/tap_ai/api/library_kb.py、application/library_kb.py"),
    Dimension("context", "背景", 10,
              re.compile(r"(因为|背景|现状|目前|现在|之前|原来|报错|错误|异常|问题是|原因|发现|出现|导致|traceback|error)", re.I),
              "现在是什么情况？有报错就贴报错原文，有现象就描述现象。",
              "例：上传 100 个文件有 70 个失败，报错是 MySQL server has gone away"),
    Dimension("constraints", "约束", 12,
              re.compile(r"(不要|禁止|不能|不许|只能|只改|只允许|必须|保持|不改|别动|不得|仅|兼容|不影响)", re.I),
              "有哪些不能做的事？比如不能改哪些文件、不能加依赖、不能改接口格式。",
              "例：不改问答插件；不新增依赖；接口返回格式保持不变"),
    Dimension("done", "完成标准", 15,
              re.compile(r"(验收|完成标准|做到|预期|期望|应该|成功后|结果是|达到|满足|通过|返回.{0,10}(为|是)|算完成)", re.I),
              "怎样才算完成？写出能检查的结果。",
              "例：重复上传同名文件时返回 skipped，document_id 不变"),
    Dimension("verify", "验证方式", 12,
              re.compile(r"(pytest|单元测试|测试|ruff|mypy|运行|执行|命令|curl|调用一次|截图|日志|run_checks)", re.I),
              "用什么方法验证？跑哪些测试或命令？",
              "例：uv run pytest tests/unit/test_library_kb_service.py -q 全部通过"),
    Dimension("output", "输出要求", 8,
              re.compile(r"(报告|格式|核对表|列出|贴出|表格|清单|markdown|返回给我|告诉我|说明)", re.I),
              "做完要给你什么？比如改动摘要、原始输出、核对表。",
              "例：贴出 git diff --stat 和测试最后 15 行，最后给核对表"),
    Dimension("examples", "示例", 8,
              re.compile(r"(例如|比如|样例|示例|如下|参考|照着|类似|```|输入[:：]|输出[:：])", re.I),
              "有没有可以参考的例子、样例数据或已有写法？",
              "例：写法参考 library_kb.py 里的 documents/retry 接口"),
]

VAGUE = ["优化一下", "优化下", "处理一下", "处理下", "看看", "看一下", "完善一下", "完善下", "搞一下", "弄一下",
         "搞定", "等等", "之类", "什么的", "好一点", "更好", "尽量", "差不多", "相关的", "一些", "适当", "合理",
         "大概", "整一下", "调整一下", "改一改", "弄好"]
SPLITTERS = re.compile(r"(然后|还有|另外|以及|同时|再就是|并且|；|;|\n\s*\d+[.、)])")


def analyze(text: str) -> dict[str, Any]:
    text = text.strip()
    dims: list[dict[str, Any]] = []
    score = 0
    for d in DIMENSIONS:
        hit = bool(d.pattern.search(text))
        if d.key == "goal" and len(text) < 12:
            hit = False
        if hit:
            score += d.weight
        dims.append({"key": d.key, "label": d.label, "ok": hit, "question": d.question, "example": d.example})
    vague = [w for w in VAGUE if w in text]
    score -= min(20, 4 * len(vague))
    tasks = len(SPLITTERS.findall(text)) + 1
    score = max(0, min(100, score))
    level = "好" if score >= 75 else ("一般" if score >= 50 else "需要补充")
    advice: list[str] = []
    for d in dims:
        if not d["ok"]:
            advice.append(f"缺少【{d['label']}】：{d['question']}（{d['example']}）")
    if vague:
        advice.append(f"含糊的说法：{'、'.join(vague)}。请换成具体的动作和结果，例如把“优化一下”改成“把接口响应时间从 3 秒降到 1 秒以内”。")
    if tasks >= 3:
        advice.append(f"一段话里大约有 {tasks} 件事。模型容易只做前一两件，建议编号列出，或者拆成几个任务分开做。")
    return {"score": score, "level": level, "dimensions": dims, "vague": vague, "task_count": tasks, "advice": advice}


def build_r3(text: str, answers: dict[str, str] | None = None, project: dict[str, Any] | None = None,
             token_mode: str = "full") -> str:
    """把草稿和补充回答拼成 R3 提示词；仍然缺的信息写成【待补充】，提醒你填。"""
    answers = answers or {}
    report = analyze(text + "\n" + "\n".join(answers.values()))
    missing = {d["key"] for d in report["dimensions"] if not d["ok"]}

    def val(key: str, fallback: str) -> str:
        v = answers.get(key, "").strip()
        if v:
            return v
        return f"【待补充：{fallback}】" if key in missing else "（见任务描述）"

    items = [x.strip() for x in re.split(r"\n\s*\d+[.、)]\s*|；|;", text) if x.strip()]
    numbered = "\n".join(f"{i}. {x}" for i, x in enumerate(items, start=1)) if len(items) > 1 else f"1. {text}"
    proj_line = ""
    if project:
        proj_line = f"\n【工作目录】{project.get('path')}"
        if project.get("style_pack"):
            proj_line += f"\n【风格包】开工前先加载技能 /{project['style_pack']}，按里面的卡片写代码。"
    protected = ""
    if project and project.get("protected"):
        protected = "\n- 不改这些受保护区域：" + "、".join(project["protected"])
    output_rule = ("只输出：改动摘要、命令输出的关键行（失败行和汇总行）、核对表。不要复述代码。"
                   if token_mode == "lean" else "按通用规则贴原始输出，最后给核对表。")
    checklist_rows = "\n".join(f"| {i} | | |" for i in range(1, len(items) + 1 if len(items) > 1 else 2))
    return f"""【任务】{items[0][:60] if items else text[:60]}{proj_line}

【背景】
{val('context', '现在是什么情况、有什么报错')}

【绝对禁止】
- 不读 .env 等可能含密钥的文件；不连接外部服务；不安装任何包
- git 只允许 status / diff / log / show / grep / ls-files
- 不改 pyproject.toml、uv.lock；不对已有文件运行 ruff format{protected}
- {val('constraints', '还有哪些不能做的事')}

【本次允许修改的文件】
{val('location', '涉及哪些文件；名单以外的文件一律不改，需要改就停下来告诉我')}

【要做的 {max(1, len(items))} 件事】
{numbered}

【完成标准】
{val('done', '怎样才算完成')}

【验证】
{val('verify', '跑哪些测试或命令，要求贴原始输出')}

【参考】
{val('examples', '可参考的已有写法或样例')}

【完成报告】
{val('output', output_rule)}

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据（文件:行号 或 命令） |
{checklist_rows}
"""


def format_report(rep: dict[str, Any]) -> str:
    lines = [f"提示词得分：{rep['score']} / 100（{rep['level']}）"]
    for d in rep["dimensions"]:
        lines.append(f"  {'✓' if d['ok'] else '✗'} {d['label']}")
    if rep["advice"]:
        lines.append("建议补充：")
        lines.extend(f"  - {a}" for a in rep["advice"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="提示词体检（离线）")
    parser.add_argument("text", nargs="?", help="需求草稿")
    parser.add_argument("--file", help="从文件读取草稿")
    parser.add_argument("--r3", action="store_true", help="同时输出补全后的 R3 提示词")
    parser.add_argument("--project")
    parser.add_argument("--lean", action="store_true", help="省 token 版输出要求")
    args = parser.parse_args(argv)
    text = kitlib.read_text(args.file) if args.file else (args.text or sys.stdin.read())
    rep = analyze(text)
    print(format_report(rep))
    if args.r3:
        proj = kitlib.get_project(kitlib.load_config(), args.project) if args.project else None
        print("\n" + build_r3(text, project=proj, token_mode="lean" if args.lean else "full"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
