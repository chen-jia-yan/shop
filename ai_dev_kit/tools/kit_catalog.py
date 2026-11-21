"""能力目录：把所有技能和代理（工具包自带的 + 你自己写的）整理成一张表，并做本地匹配。

为什么需要：模型只在“你说的话”和“能力的描述”对得上时才会想到用它。目录把每个能力的
“做什么”和“用户一般怎么说”放在一起，会话开头注入一份精简版；你每发一条消息，钩子先在
本地匹配一次（不花额度），匹配上就附一行“可能适用：xxx”，由模型说明打算用它、再问你。

能力文件里的约定（SKILL.md 或 *.agent.md 正文里）：
    ## 用户会这样说
    - 帮我排查一下为什么报错
    - 测试突然挂了
    风险：只读          （可选：只读 / 会改文件；代理按 tools 自动判断）

来源：
    工具包的 skills/、style-packs/、agents/
    ~/.copilot/skills、~/.agents/skills、~/.copilot/agents 里你自己装的
    用 kit_skill.py add 挂进来的目录

用法：
    python kit_catalog.py build          # 重新生成 ~/.ai-dev-kit/catalog.json
    python kit_catalog.py show           # 看会话开头注入的精简目录
    python kit_catalog.py match "测试一直报 ModuleNotFoundError"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import kitlib

CATALOG_PATH = kitlib.DATA_DIR / "catalog.json"
EXTRA_DIRS_PATH = kitlib.DATA_DIR / "skill_dirs.json"
TRIGGER_HEAD = re.compile(r"(?m)^##\s*用户会这样说\s*$")
RISK_LINE = re.compile(r"(?m)^风险[:：]\s*(只读|会改文件)")
WRITE_TOOLS = {"edit", "execute", "shell", "bash", "powershell", "write", "*"}
QUESTION = re.compile(r"^(什么|为什么|怎么|如何|是不是|能不能|可不可以|有没有|哪|谁|多少)|[?？]\s*$")


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    meta: dict[str, str] = {}
    for line in parts[0][3:].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    body = parts[1].lstrip("-").lstrip("\n") if len(parts) > 1 else ""
    return meta, body


def triggers_of(body: str, limit: int = 8) -> list[str]:
    m = TRIGGER_HEAD.search(body)
    if not m:
        return []
    out: list[str] = []
    for line in body[m.end():].splitlines():
        s = line.strip()
        if s.startswith("#"):
            break
        if s.startswith(("-", "*")) and not s.lstrip("-* ").startswith("（改成"):  # 跳过脚手架占位句
            out.append(s.lstrip("-* ").strip().strip("“”\"'"))
        if len(out) >= limit:
            break
    return [t for t in out if t]


def _entry(path: Path, kind: str, source: str) -> dict[str, Any] | None:
    try:
        meta, body = frontmatter(kitlib.read_text(path))
    except OSError:
        return None
    name = meta.get("name") or (path.parent.name if kind == "skill" else path.name.replace(".agent.md", ""))
    desc = meta.get("description", "")
    if not name or not desc:
        return None
    risk_m = RISK_LINE.search(body)
    if kind == "agent":
        tools = {t.strip().strip("\"'[] ").lower() for t in meta.get("tools", "*").split(",")}
        writes = bool(tools & WRITE_TOOLS) or not meta.get("tools")
    else:
        writes = bool(risk_m and risk_m.group(1) == "会改文件")
    if risk_m:
        writes = risk_m.group(1) == "会改文件"
    return {"name": name, "kind": kind, "source": source, "desc": desc[:240], "triggers": triggers_of(body),
            "writes": writes, "path": str(path)}


def extra_dirs() -> list[str]:
    registered = kitlib.load_json(EXTRA_DIRS_PATH, []) or []
    configured = (kitlib.load_config().get("capabilities", {}) or {}).get("extra_skill_dirs", []) or []
    return [d for d in list(registered) + list(configured) if isinstance(d, str) and d]


def _skill_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    if (base / "SKILL.md").is_file():  # 直接指向单个技能目录
        return [base / "SKILL.md"]
    return sorted(p / "SKILL.md" for p in base.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
                  and (p / "SKILL.md").is_file())


def build() -> list[dict[str, Any]]:
    manifest = kitlib.load_json(kitlib.DATA_DIR / "installed.json", {}) or {}
    kit_skills = set(manifest.get("skills", []))
    kit_agents = set(manifest.get("agents", []))
    items: dict[str, dict[str, Any]] = {}

    def add(entry: dict[str, Any] | None) -> None:
        if entry and entry["name"] not in items:
            items[entry["name"]] = entry

    for base in (kitlib.KIT_ROOT / "skills", kitlib.KIT_ROOT / "style-packs"):
        for f in _skill_files(base):
            add(_entry(f, "skill", "kit"))
    for f in sorted((kitlib.KIT_ROOT / "agents").glob("*.agent.md")):
        add(_entry(f, "agent", "kit"))
    home = kitlib.copilot_home()
    for base in [home / "skills", Path.home() / ".agents" / "skills"] + [Path(d) for d in extra_dirs()]:
        for f in _skill_files(base):
            if f.parent.name in kit_skills and base == home / "skills":
                continue
            add(_entry(f, "skill", "user"))
    for f in sorted((home / "agents").glob("*.agent.md")) if (home / "agents").is_dir() else []:
        if f.name not in kit_agents:
            add(_entry(f, "agent", "user"))
    result = sorted(items.values(), key=lambda e: (e["source"] != "user", e["kind"], e["name"]))
    kitlib.save_json(CATALOG_PATH, {"built": kitlib.now(), "items": result})
    return result


def load(rebuild_if_missing: bool = True) -> list[dict[str, Any]]:
    data = kitlib.load_json(CATALOG_PATH, {}) or {}
    if not data.get("items") and rebuild_if_missing:
        return build()
    return list(data.get("items", []))


# ---------------------------------------------------------------- 本地匹配


def grams(text: str) -> set[str]:
    """中文按两个字一组，英文按单词，用来粗略比较两句话像不像。"""
    text = text.lower()
    out: set[str] = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", text))
    for run in re.findall("[\\u4e00-\\u9fff]+", text):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def match(prompt: str, items: list[dict[str, Any]] | None = None, top: int = 2) -> list[tuple[float, dict[str, Any]]]:
    items = items if items is not None else load()
    pg = grams(prompt)
    if not pg:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        if prompt and f"/{item['name']}" in prompt:
            scored.append((2.0, item))
            continue
        best = 0.0
        for trig in item.get("triggers", []):
            tg = grams(trig)
            if tg:
                best = max(best, len(pg & tg) / len(tg))
        dg = grams(item.get("desc", ""))
        desc_score = len(pg & dg) / max(8, len(pg)) if dg else 0.0
        score = max(best, desc_score * 0.8)
        if score >= 0.45:
            scored.append((round(score, 2), item))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]


def is_question(prompt: str) -> bool:
    return bool(QUESTION.search(prompt.strip()))


def digest(items: list[dict[str, Any]] | None = None, max_chars: int = 1400) -> str:
    """会话开头注入的精简目录：每个能力一行，做什么 + 一句典型说法。"""
    items = items if items is not None else load()
    lines: list[str] = []
    for item in items:
        say = f"｜例：{item['triggers'][0]}" if item.get("triggers") else ""
        mark = "（你写的）" if item["source"] == "user" else ""
        kind = "代理" if item["kind"] == "agent" else "技能"
        lines.append(f"- {kind} {item['name']}{mark}：{item['desc'][:60]}{say}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars] + "\n……（完整目录：kit_catalog.py show）"


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="能力目录")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("show")
    p = sub.add_parser("match")
    p.add_argument("text")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        items = build()
        print(f"能力目录已生成：{CATALOG_PATH}（{len(items)} 个；其中你自己的 {sum(i['source'] == 'user' for i in items)} 个）")
        missing = [i["name"] for i in items if not i.get("triggers")]
        if missing:
            print("这些能力还没写“用户会这样说”，自动匹配会弱一些：" + "、".join(missing))
    elif args.cmd == "show":
        print(digest(build(), max_chars=100_000))
    else:
        found = match(args.text, build())
        if not found:
            print("没有匹配到。")
        for score, item in found:
            print(f"{score:.2f}  {item['kind']} {item['name']}：{item['desc'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
