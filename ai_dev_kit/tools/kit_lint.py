"""工具包自检（lint）：改了技能、代理、模板、清单之后运行，确认格式都对、引用都存在。

检查：
- 技能：SKILL.md 有 name / description；name 与目录名一致且是小写加连字符；description 不超过 1024 字，
  写清"做什么、什么时候用"；正文不超过 500 行（官方建议，太长模型反而抓不住重点）；正文里提到的
  references/ scripts/ 文件都存在
- 代理：*.agent.md 有 name / description；tools 只用官方工具组；文件名就是代理 ID
- 风格卡片：必需的段落齐全；来源文件和核对日期存在，核对日期超过 120 天给提醒
- registry.json：每个按钮引用的模板、代理、工具都存在
- 模板：只用已知占位符
- 记忆、评估用例、JSON 文件能正常解析
- 所有文件编码正常

用法：python tools/kit_lint.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import check_chars
import kitlib

ROOT = kitlib.KIT_ROOT
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOOL_GROUPS = {"read", "edit", "search", "execute", "grep", "glob", "web", "todo", "agent", "shell", "*",
               "view", "create", "bash", "powershell", "task", "ask_user", "web_fetch"}
KNOWN_PLACEHOLDERS = {"rules", "task", "project_block", "project_name", "files", "verify_cmd", "style_hint",
                      "output_block", "ref", "kit", "python"}
CARD_SECTIONS = ["## 何时使用", "## 必须", "## 禁止", "## 精简样例", "## 反例", "## 检查项", "## 来源"]

errors: list[str] = []
warnings: list[str] = []


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = kitlib.read_text(path)
    if not text.startswith("---"):
        return {}, text
    head, _, body = text[3:].partition("\n---")
    meta: dict[str, str] = {}
    key = ""
    for line in head.splitlines():
        if re.match(r"^[A-Za-z][\w-]*\s*:", line):
            key, _, value = line.partition(":")
            key = key.strip()
            meta[key] = value.strip()
        elif key and line.startswith((" ", "\t")):
            meta[key] = (meta[key] + " " + line.strip()).strip()
    return meta, body.lstrip("-\n")


def lint_skills() -> int:
    count = 0
    for base in (ROOT / "skills", ROOT / "style-packs"):
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")):
            count += 1
            skill = d / "SKILL.md"
            if not skill.is_file():
                errors.append(f"{d}：缺少 SKILL.md")
                continue
            meta, body = frontmatter(skill)
            name = meta.get("name", "")
            desc = meta.get("description", "").strip(">|").strip()
            if not name:
                errors.append(f"{skill}：缺少 name")
            elif name != d.name:
                errors.append(f"{skill}：name（{name}）必须与目录名（{d.name}）一致")
            elif not NAME_RE.match(name):
                errors.append(f"{skill}：name 只能用小写字母、数字和连字符")
            if not desc:
                errors.append(f"{skill}：缺少 description")
            elif len(desc) > 1024:
                errors.append(f"{skill}：description 超过 1024 字")
            elif not re.search(r"(用于|适用|当|Use when|Use this)", desc):
                warnings.append(f"{skill}：description 最好写明“什么时候用”，模型靠它决定是否加载")
            lines = body.count("\n") + 1
            if lines > 500:
                warnings.append(f"{skill}：正文 {lines} 行，超过建议的 500 行，细节请移到 references/")
            for ref in set(re.findall(r"`?((?:references|scripts|assets|patterns)/[\w./-]+)`?", body)):
                if not (d / ref).exists():
                    errors.append(f"{skill}：提到的 {ref} 不存在")
            if "allowed-tools" in meta and re.search(r"\b(shell|bash|powershell)\b", meta["allowed-tools"]):
                errors.append(f"{skill}：allowed-tools 预先放行了 shell，官方明确提醒不要这样做")
    return count


def lint_agents() -> int:
    count = 0
    for path in sorted((ROOT / "agents").glob("*.agent.md")):
        count += 1
        meta, body = frontmatter(path)
        agent_id = path.name[: -len(".agent.md")]
        if not NAME_RE.match(agent_id):
            errors.append(f"{path}：文件名（代理 ID）只能用小写字母、数字和连字符")
        if not meta.get("description"):
            errors.append(f"{path}：缺少 description")
        tools = meta.get("tools", "")
        if tools:
            names = [t.strip().strip("\"'") for t in tools.strip("[]").split(",") if t.strip()]
            unknown = [t for t in names if t not in TOOL_GROUPS and "/" not in t]
            if unknown:
                warnings.append(f"{path}：tools 里有不认识的名字 {unknown}（如果是 MCP 工具请写成 服务名/工具名）")
        if len(body.strip()) < 80:
            warnings.append(f"{path}：正文太短，代理的职责和边界要写清楚")
    return count


def lint_cards() -> int:
    count = 0
    for card in sorted(ROOT.glob("style-packs/*/patterns/*.md")):
        count += 1
        text = kitlib.read_text(card)
        for sec in CARD_SECTIONS:
            if sec not in text:
                errors.append(f"{card}：缺少段落 {sec}")
        m = re.search(r"核对日期[:：]\s*(\d{4}-\d{2}-\d{2})", text)
        if not m:
            warnings.append(f"{card}：没有写核对日期")
        else:
            age = (time.time() - time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))) / 86400
            if age > 120:
                warnings.append(f"{card}：已经 {int(age)} 天没核对，代码可能变了，请用 kit-extract-pattern 重新核对")
    return count


def lint_registry() -> int:
    data = kitlib.load_json(kitlib.REGISTRY_PATH)
    if data is None:
        errors.append("registry.json 不存在")
        return 0
    templates = {p.stem for p in (ROOT / "templates").glob("*.md")}
    agents = {p.name[: -len(".agent.md")] for p in (ROOT / "agents").glob("*.agent.md")}
    ids: set[str] = set()
    actions = data.get("actions", [])
    for a in actions:
        aid = a.get("id", "")
        if not aid or aid in ids:
            errors.append(f"registry.json：按钮 id 为空或重复：{aid!r}")
        ids.add(aid)
        if a.get("template") and a["template"] not in templates:
            errors.append(f"registry.json：{aid} 引用的模板 {a['template']} 不存在")
        if a.get("agent") and a["agent"] not in agents:
            errors.append(f"registry.json：{aid} 引用的代理 {a['agent']} 不存在")
        if a.get("kind") == "run_tool":
            script = a.get("command", [""])[1] if len(a.get("command", [])) > 1 else ""
            script_path = Path(kitlib.expand(script, {"kit": str(ROOT)}))
            if script and script.endswith(".py") and not script_path.is_file():
                errors.append(f"registry.json：{aid} 的脚本不存在：{script}")
        if a.get("kind") not in {"launch_agent", "prompt_only", "run_tool", "open_path", "builtin"}:
            errors.append(f"registry.json：{aid} 的 kind 不认识：{a.get('kind')}")
    return len(actions)


def lint_templates() -> int:
    count = 0
    for t in sorted((ROOT / "templates").glob("*.md")):
        count += 1
        for ph in set(re.findall(r"\{\{(\w[\w-]*)\}\}", kitlib.read_text(t))):
            if ph not in KNOWN_PLACEHOLDERS:
                errors.append(f"{t}：未知占位符 {{{{{ph}}}}}")
    return count


def lint_json_and_data() -> int:
    count = 0
    for path in list(ROOT.glob("*.json")) + list(ROOT.glob("evals/cases/*.json")) + list(ROOT.glob(".github/plugin/*.json")):
        count += 1
        try:
            json.loads(kitlib.read_text(path))
        except ValueError as exc:
            errors.append(f"{path}：JSON 格式错误：{exc}")
    import mem

    for m in mem.load_all(include_archive=True):
        count += 1
        if not m.meta.get("subject") or m.meta.get("type") not in mem.TYPES:
            errors.append(f"{m.path}：记忆缺少 subject 或 type 不对")
    return count


def lint_encoding() -> int:
    files = check_chars.iter_files([str(ROOT)], set(check_chars.DEFAULT_EXTS))
    for f in files:
        for issue in check_chars.check_file(f):
            if issue.severity == "error":
                errors.append(f"{issue.path}:{issue.line} {issue.message}")
    return len(files)


def main() -> int:
    kitlib.setup_console()
    counts = {
        "技能": lint_skills(),
        "代理": lint_agents(),
        "风格卡片": lint_cards(),
        "按钮": lint_registry(),
        "模板": lint_templates(),
        "数据文件": lint_json_and_data(),
        "编码检查文件": lint_encoding(),
    }
    print("检查范围：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    for e in errors:
        print(f"[错误] {e}")
    for w in warnings:
        print(f"[提醒] {w}")
    print(f"结果：错误 {len(errors)} 个，提醒 {len(warnings)} 个。")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
