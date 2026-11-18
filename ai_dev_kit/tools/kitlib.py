"""ai-dev-kit 公共函数库。

所有脚本（钩子、工具、挂件）都从这里读取配置、定位目录、运行命令。
只使用 Python 标准库，保证在离线、不能装包的电脑上也能运行。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

KIT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("AI_DEV_KIT_HOME") or (Path.home() / ".ai-dev-kit"))
CONFIG_PATH = KIT_ROOT / "kit.config.json"
EXAMPLE_CONFIG_PATH = KIT_ROOT / "kit.config.example.json"
REGISTRY_PATH = KIT_ROOT / "registry.json"
SCOPE_DIRNAME = ".ai-dev-kit"
SCOPE_FILENAME = "scope.json"

IS_WINDOWS = os.name == "nt"


# ---------------------------------------------------------------- 路径与配置


def copilot_home() -> Path:
    """Copilot CLI 的配置目录。设置了 COPILOT_HOME 时以它为准。"""
    env = os.environ.get("COPILOT_HOME")
    return Path(env) if env else Path.home() / ".copilot"


def load_json(path: Path | str, default: Any = None) -> Any:
    """读取 JSON。文件不存在返回 default；带 BOM 的 UTF-8 也能读。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path: Path | str, data: Any) -> None:
    """原子写入 JSON：先写临时文件再替换，UTF-8 无 BOM，换行统一为 LF。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def write_text(path: Path | str, text: str) -> None:
    """写文本文件：UTF-8 无 BOM，LF 换行，自动建目录。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_text(path: Path | str) -> str:
    """读文本：优先 UTF-8（容忍 BOM），失败再试 GBK，最后用替换字符兜底。"""
    raw = Path(path).read_bytes()
    return decode_bytes(raw)


def decode_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_config() -> dict[str, Any]:
    """读取 kit.config.json；还没创建时退回示例配置，并做标记。"""
    cfg = load_json(CONFIG_PATH)
    if cfg is None:
        cfg = load_json(EXAMPLE_CONFIG_PATH, {}) or {}
        cfg["_from_example"] = True
    return cfg


def python_exe(cfg: dict[str, Any] | None = None) -> str:
    """配置里写的 Python；没写就用当前解释器。"""
    cfg = cfg if cfg is not None else load_config()
    configured = (cfg.get("python") or "").strip()
    return configured or sys.executable


def norm(path: Path | str) -> str:
    """统一大小写和分隔符，用于比较 Windows 路径。"""
    return os.path.normcase(os.path.abspath(str(path)))


def find_project(cfg: dict[str, Any], cwd: Path | str) -> dict[str, Any] | None:
    """按当前目录匹配 kit.config.json 里登记的项目（取最长匹配）。"""
    current = norm(cwd)
    best: dict[str, Any] | None = None
    best_len = -1
    for proj in cfg.get("projects", []):
        root = norm(proj.get("path", ""))
        if not proj.get("path"):
            continue
        if current == root or current.startswith(root.rstrip("\\/") + os.sep):
            if len(root) > best_len:
                best, best_len = proj, len(root)
    return best


def get_project(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    for proj in cfg.get("projects", []):
        if proj.get("name") == name:
            return proj
    return None


def get_profile(cfg: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    profiles = cfg.get("profiles", {})
    key = name or cfg.get("default_profile") or next(iter(profiles), "")
    prof = dict(profiles.get(key, {}))
    prof["_name"] = key
    return prof


def expand(value: str, ctx: dict[str, str]) -> str:
    """替换 {python} {kit} {project} 这类占位符。"""
    out = value
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", val)
    return out


def expand_cmd(cmd: list[str], ctx: dict[str, str]) -> list[str]:
    return [expand(part, ctx) for part in cmd]


def base_ctx(cfg: dict[str, Any], project: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = {"python": python_exe(cfg), "kit": str(KIT_ROOT)}
    if project:
        ctx["project"] = str(project.get("path", ""))
        ctx["git_root"] = str(project.get("git_root") or project.get("path", ""))
    return ctx


# ---------------------------------------------------------------- 运行命令


def resolve_exe(name: str) -> str:
    """在 PATH 里找可执行文件（含 Windows 的 .cmd/.bat/.exe）。找不到原样返回。"""
    if os.path.sep in name or (IS_WINDOWS and "/" in name):
        return name
    found = shutil.which(name)
    return found or name


def run(
    cmd: list[str],
    cwd: Path | str | None = None,
    timeout: int = 900,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str]:
    """运行命令并返回 (退出码, 合并后的输出)。不经过 shell，避免引号和注入问题。"""
    if not cmd:
        return 2, "命令为空"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    real = [resolve_exe(cmd[0])] + list(cmd[1:])
    try:
        proc = subprocess.run(
            real,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            timeout=timeout,
            env=env,
            shell=False,
        )
    except FileNotFoundError as exc:
        return 127, f"找不到命令：{cmd[0]}（{exc}）"
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（{timeout} 秒）：{' '.join(cmd)}"
    except OSError as exc:
        return 126, f"命令无法启动：{cmd[0]}（{exc}）"
    text = decode_bytes(proc.stdout or b"")
    err = decode_bytes(proc.stderr or b"")
    if err.strip():
        text = text + ("\n" if text and not text.endswith("\n") else "") + err
    return proc.returncode, text


def git(args: list[str], cwd: Path | str) -> tuple[int, str]:
    """只读 git 调用的统一入口（本工具包从不执行 git 写操作）。"""
    return run(["git", "--no-pager"] + args, cwd=cwd, timeout=120)


# ---------------------------------------------------------------- 指纹（哈希缓存）


def tree_fingerprint(root: Path | str, extra: str = "") -> str:
    """工作区指纹：HEAD + 未提交改动的文件内容哈希。

    内容没变，指纹就不变，验收结果可以直接复用，不必重跑测试、
    也不必把几千行测试输出再塞进模型上下文。
    """
    root = Path(root)
    h = hashlib.sha256()
    h.update(extra.encode("utf-8"))
    code, head = git(["rev-parse", "HEAD"], root)
    h.update(head.strip().encode("utf-8") if code == 0 else b"no-git")
    code, status = git(["status", "--porcelain", "--untracked-files=all"], root)
    if code != 0:
        status = ""
    for line in sorted(status.splitlines()):
        h.update(line.encode("utf-8", errors="replace"))
        rel = line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        target = root / rel
        if target.is_file():
            try:
                if target.stat().st_size <= 5_000_000:
                    h.update(hashlib.sha256(target.read_bytes()).digest())
            except OSError:
                pass
    return h.hexdigest()[:24]


def cache_get(namespace: str, key: str) -> Any:
    data = load_json(DATA_DIR / "cache" / f"{namespace}.json", {}) or {}
    return data.get(key)


def cache_put(namespace: str, key: str, value: Any, keep: int = 50) -> None:
    path = DATA_DIR / "cache" / f"{namespace}.json"
    data = load_json(path, {}) or {}
    data[key] = value
    if len(data) > keep:
        for old in sorted(data, key=lambda k: str(data[k].get("ts", "")))[: len(data) - keep]:
            data.pop(old, None)
    save_json(path, data)


# ---------------------------------------------------------------- 修改范围（scope）


def find_scope(start: Path | str) -> tuple[Path | None, dict[str, Any] | None]:
    """从 start 往上找 .ai-dev-kit/scope.json，返回 (仓库根, 范围数据)。"""
    cur = Path(start).resolve()
    for folder in [cur] + list(cur.parents):
        candidate = folder / SCOPE_DIRNAME / SCOPE_FILENAME
        if candidate.is_file():
            return folder, load_json(candidate, {})
    return None, None


def rel_posix(path: Path | str, root: Path | str) -> str:
    """把绝对路径变成相对仓库根的 POSIX 路径；不在根下面就返回绝对路径。"""
    p = os.path.realpath(str(path))
    r = os.path.realpath(str(root))
    try:
        rel = os.path.relpath(p, r)
    except ValueError:
        return p.replace("\\", "/")
    if rel.startswith(".."):
        return p.replace("\\", "/")
    return rel.replace("\\", "/")


def match_any(rel: str, patterns: list[str]) -> bool:
    """大小写不敏感的通配匹配。* 可以跨目录，所以 src/** 和 src/* 都能匹配子目录。"""
    target = rel.replace("\\", "/").lower()
    name = target.rsplit("/", 1)[-1]
    for pat in patterns:
        pat_l = pat.replace("\\", "/").lower().strip()
        if not pat_l:
            continue
        if fnmatch.fnmatchcase(target, pat_l) or fnmatch.fnmatchcase(name, pat_l):
            return True
        if pat_l.endswith("/**") and target.startswith(pat_l[:-3].rstrip("/") + "/"):
            return True
    return False


# ---------------------------------------------------------------- 脱敏与日志

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey)(\s*[=:]\s*)([^\s'\";,]+)"), r"\1\2***"),
    (re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)"), r"\1***\3"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "sk-***"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "***"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "***"),
]


def redact(text: str, limit: int = 400) -> str:
    """去掉密码、密钥、连接串里的口令，再截断，用于日志和展示。"""
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    if len(out) > limit:
        out = out[:limit] + f"…（已截断，共 {len(text)} 字）"
    return out


def log_event(kind: str, record: dict[str, Any]) -> None:
    """追加一行 JSON 日志到 ~/.ai-dev-kit/logs/<kind>-日期.jsonl。写日志失败不影响主流程。"""
    try:
        day = time.strftime("%Y%m%d")
        path = DATA_DIR / "logs" / f"{kind}-{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(record)
        record.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # 日志不能影响钩子和工具的主逻辑
        pass


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def setup_console() -> None:
    """让 Windows 终端正确显示中文。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
