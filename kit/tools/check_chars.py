"""编码与隐形字符检查（只读）。

能发现：UTF-16 文件、带 BOM 的 UTF-8、无法按 UTF-8 解码的文件、
零宽字符、不间断空格、全角空格、Python 文件里的 Tab 缩进、
Python 里的非 ASCII 标识符、同一文件混用 CRLF 和 LF。

用法：
    python check_chars.py src tests sql
    python check_chars.py --json src
退出码：0 = 没有问题；1 = 发现问题；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_EXTS = {
    ".py", ".pyi", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".sql",
    ".ini", ".cfg", ".ps1", ".bat", ".cmd", ".sh", ".html", ".css", ".js", ".ts",
    ".csv", ".xml", ".example",
}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache",
             ".ruff_cache", ".pytest_cache", "dist", "build", ".idea", ".ai-dev-kit"}
# 这些文件里可能有密钥，检查工具也不打开
SECRET_NAMES = {".env"}

ZERO_WIDTH = {
    "\u200b": "零宽空格 U+200B",
    "\u200c": "零宽非连接符 U+200C",
    "\u200d": "零宽连接符 U+200D",
    "\u2060": "词连接符 U+2060",
    "\ufeff": "文件中间的 BOM U+FEFF",
    "\u00ad": "软连字符 U+00AD",
}
NBSP = "\u00a0"
FULLWIDTH_SPACE = "\u3000"


@dataclass
class Issue:
    path: str
    line: int
    rule: str
    message: str
    severity: str = "error"  # error / warning


def _is_secret_file(path: Path) -> bool:
    name = path.name.lower()
    return name in SECRET_NAMES or (name.startswith(".env.") and name != ".env.example")


def check_bytes(path: str, raw: bytes, is_python: bool) -> list[Issue]:
    issues: list[Issue] = []
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        issues.append(Issue(path, 1, "utf16", "文件是 UTF-16 编码，应转成 UTF-8（无 BOM）"))
        return issues
    if b"\x00" in raw[:4096]:
        issues.append(Issue(path, 1, "nul", "文件里有 NUL 字节，可能是 UTF-16 或二进制文件"))
        return issues
    body = raw
    if raw.startswith(b"\xef\xbb\xbf"):
        issues.append(Issue(path, 1, "bom", "文件开头有 UTF-8 BOM，应去掉", "warning"))
        body = raw[3:]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = body[: exc.start].count(b"\n") + 1
        issues.append(Issue(path, line, "not-utf8", f"不是合法 UTF-8（第 {exc.start} 字节附近），可能是 GBK 编码"))
        return issues

    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf and lf:
        issues.append(Issue(path, 1, "mixed-eol", f"混用换行符：CRLF {crlf} 处，LF {lf} 处", "warning"))

    for lineno, line in enumerate(text.splitlines(), start=1):
        for ch, label in ZERO_WIDTH.items():
            if ch in line:
                issues.append(Issue(path, lineno, "zero-width", f"含隐形字符：{label}"))
        if NBSP in line:
            sev = "error" if is_python else "warning"
            issues.append(Issue(path, lineno, "nbsp", "含不间断空格 U+00A0（看起来像空格，实际不是）", sev))
        if FULLWIDTH_SPACE in line:
            stripped = line.lstrip(" \t")
            sev = "error" if (is_python and (line.startswith(FULLWIDTH_SPACE) or not stripped.startswith("#"))) else "warning"
            issues.append(Issue(path, lineno, "fullwidth-space", "含全角空格 U+3000", sev))
        if is_python and line.startswith("\t"):
            issues.append(Issue(path, lineno, "tab-indent", "Python 用了 Tab 缩进，应改为 4 个空格"))

    if is_python:
        issues.extend(_check_python_identifiers(path, text))
    return issues


def _check_python_identifiers(path: str, text: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for tok in tokens:
            if tok.type == tokenize.NAME and not tok.string.isascii():
                issues.append(Issue(path, tok.start[0], "non-ascii-name",
                                    f"标识符含非 ASCII 字符：{tok.string!r}"))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        issues.append(Issue(path, 1, "tokenize", f"无法解析（可能有语法错误）：{exc}", "warning"))
    return issues


def check_file(path: Path | str) -> list[Issue]:
    """检查单个文件。钩子在每次改完文件后调用它。"""
    p = Path(path)
    if _is_secret_file(p):
        return []
    try:
        raw = p.read_bytes()
    except OSError as exc:
        return [Issue(str(p), 1, "unreadable", f"无法读取：{exc}", "warning")]
    return check_bytes(str(p), raw, p.suffix.lower() in {".py", ".pyi"})


def iter_files(targets: list[str], exts: set[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        p = Path(target)
        if p.is_file():
            files.append(p)
            continue
        if not p.is_dir():
            continue
        for root, dirs, names in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                fp = Path(root) / name
                if fp.suffix.lower() in exts or name.lower() in {".env.example"}:
                    files.append(fp)
    return sorted(set(files))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="编码与隐形字符检查（只读）")
    parser.add_argument("targets", nargs="*", default=["."], help="要检查的文件或目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--errors-only", action="store_true", help="只显示 error 级别")
    parser.add_argument("--ext", action="append", default=[], help="额外检查的扩展名，如 .vue")
    args = parser.parse_args(argv)

    exts = set(DEFAULT_EXTS) | {e if e.startswith(".") else "." + e for e in args.ext}
    files = iter_files(args.targets, exts)
    all_issues: list[Issue] = []
    for fp in files:
        all_issues.extend(check_file(fp))
    if args.errors_only:
        all_issues = [i for i in all_issues if i.severity == "error"]

    errors = sum(1 for i in all_issues if i.severity == "error")
    warnings = len(all_issues) - errors
    if args.json:
        print(json.dumps({"files": len(files), "errors": errors, "warnings": warnings,
                          "issues": [asdict(i) for i in all_issues]}, ensure_ascii=False, indent=2))
    else:
        for i in all_issues:
            tag = "错误" if i.severity == "error" else "提醒"
            print(f"{i.path}:{i.line}: [{tag}:{i.rule}] {i.message}")
        print(f"扫描 {len(files)} 个文件：错误 {errors} 个，提醒 {warnings} 个。")
        if not files:
            print("注意：没有扫描到任何文件，请检查路径是否正确。")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
