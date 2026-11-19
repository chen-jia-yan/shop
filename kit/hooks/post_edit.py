"""postToolUse 钩子：每次 Copilot 改完或新建文件后，立刻检查这个文件。

检查内容：
1. 编码和隐形字符（复用 tools/check_chars.py）：UTF-16、BOM、零宽字符、全角空格、Tab 缩进等；
2. Python 文件能不能编译（语法错误马上发现，不用等到跑测试）。

发现问题时，通过 additionalContext 把问题追加到工具结果里，模型在同一轮就能看到并修正。
没问题时输出 {}，不增加任何 token。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_chars  # 必须在上一行把 tools 目录加进 sys.path 之后再导入
import kitlib

WRITE_TOOLS = {"edit", "create", "write", "str_replace_editor", "apply_patch", "str_replace",
               "insert", "write_file", "multi_edit"}
PATH_KEYS = re.compile(r"(?i)^(path|file|file_?path|filename|target|absolute_?path)$")


def _paths(args: Any) -> list[str]:
    found: list[str] = []

    def walk(obj: Any, key: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, str(k))
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif isinstance(obj, str):
            if PATH_KEYS.match(key):
                found.append(obj)
            elif "*** " in obj:
                found.extend(re.findall(r"(?m)^\*\*\*\s+(?:Add|Update)\s+File:\s*(.+?)\s*$", obj))

    walk(args)
    return found


def _compile_check(path: Path) -> str | None:
    try:
        source = path.read_bytes()
        compile(source, str(path), "exec", dont_inherit=True)
    except SyntaxError as exc:
        return f"{path.name} 第 {exc.lineno} 行语法错误：{exc.msg}"
    except (OSError, ValueError):
        return None
    return None


def handle(raw: str) -> dict[str, Any]:
    payload = json.loads(raw) if raw.strip() else {}
    tool = str(payload.get("toolName") or payload.get("tool_name") or "").lower()
    if tool not in WRITE_TOOLS:
        return {}
    args = payload.get("toolArgs", payload.get("tool_input", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            args = {}
    cwd = str(payload.get("cwd") or os.getcwd())
    problems: list[str] = []
    for p in _paths(args):
        fp = Path(p if os.path.isabs(p) else os.path.join(cwd, p))
        if not fp.is_file():
            continue
        for issue in check_chars.check_file(fp):
            if issue.severity == "error" or issue.rule in {"bom", "mixed-eol"}:
                problems.append(f"{fp.name}:{issue.line} {issue.message}")
        if fp.suffix.lower() == ".py":
            err = _compile_check(fp)
            if err:
                problems.append(err)
    if not problems:
        return {}
    kitlib.log_event("post_edit", {"tool": tool, "problems": problems[:20]})
    shown = problems[:15]
    more = f"\n……另有 {len(problems) - 15} 处" if len(problems) > 15 else ""
    return {"additionalContext": "ai-dev-kit 改后检查发现问题，请先修正再继续：\n- " + "\n- ".join(shown) + more}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        result = handle(raw)
    except Exception as exc:  # postToolUse 出错只记录，不打断会话
        kitlib.log_event("post_edit", {"error": repr(exc)[:300]})
        result = {}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
