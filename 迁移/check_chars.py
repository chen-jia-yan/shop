"""只读扫描：找出代码里的隐形字符、特殊空格和"长得像英文字母"的字符。不修改任何文件。

用法（在 tap-ai-backend 目录下运行）：
    uv run python C:/Users/234393/Desktop/check_chars.py src tests sql .env.example
"""

import io
import sys
import tokenize
import unicodedata
from pathlib import Path

# 这些字符肉眼看不见，或者看起来像普通空格；出现在代码里几乎都是错误
INVISIBLE = {
    "\u00a0": "不换行空格(NBSP)",
    "\u00ad": "软连字符",
    "\u200b": "零宽空格",
    "\u200c": "零宽非连接符",
    "\u200d": "零宽连接符",
    "\u200e": "左到右标记",
    "\u200f": "右到左标记",
    "\u2028": "行分隔符",
    "\u2029": "段分隔符",
    "\u202a": "方向控制符",
    "\u202b": "方向控制符",
    "\u202c": "方向控制符",
    "\u202d": "方向控制符",
    "\u202e": "方向控制符",
    "\u2060": "单词连接符",
    "\u2066": "方向控制符",
    "\u2067": "方向控制符",
    "\u2068": "方向控制符",
    "\u2069": "方向控制符",
    "\u3000": "全角空格",
    "\ufeff": "BOM",
}
SUFFIXES = {".py", ".sql", ".md", ".toml", ".txt", ".example", ".json", ".yaml", ".yml"}
SKIP_DIRS = {"__pycache__", ".venv", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path}: 不是 UTF-8 编码 ({exc})"]

    out: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            if ch in INVISIBLE:
                out.append(f"{path}:{no}:{col}: {INVISIBLE[ch]} U+{ord(ch):04X}")
        indent = line[: len(line) - len(line.lstrip())]
        if "\t" in indent:
            out.append(f"{path}:{no}: 缩进里有 Tab")

    if path.suffix != ".py":
        return out

    # 代码里的名字（类名、函数名、变量名）只允许英文字符；中文只能出现在注释和字符串里
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.NAME and not tok.string.isascii():
                bad = ", ".join(
                    f"U+{ord(c):04X} {unicodedata.name(c, '?')}"
                    for c in tok.string
                    if not c.isascii()
                )
                out.append(
                    f"{path}:{tok.start[0]}:{tok.start[1] + 1}: "
                    f"名字里有非英文字符 {ascii(tok.string)} -> {bad}"
                )
            elif tok.type == tokenize.ERRORTOKEN and not tok.string.isspace():
                out.append(
                    f"{path}:{tok.start[0]}:{tok.start[1] + 1}: 无法识别的字符 {ascii(tok.string)}"
                )
    except (tokenize.TokenError, SyntaxError) as exc:
        out.append(f"{path}: Python 无法解析 ({exc})")
    return out


def iter_files(args: list[str]):
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in SUFFIXES and not SKIP_DIRS & set(f.parts):
                    yield f
        elif p.is_file():
            yield p
        else:
            print(f"找不到: {arg}")


def main() -> int:
    args = sys.argv[1:] or ["src", "tests"]
    files = 0
    problems = 0
    for f in iter_files(args):
        files += 1
        for msg in scan_file(f):
            print(msg)
            problems += 1
    print(f"扫描了 {files} 个文件，发现 {problems} 处问题")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
