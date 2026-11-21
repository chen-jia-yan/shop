"""ai-dev-kit 公共函数库。

所有脚本（钩子、工具、桌面宠物）都从这里读取配置、定位目录、运行命令。
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


def get_project(cfg: dict[str, Any], name: str | None) -> dict[str, Any] | None:
    """按名字找项目。名字也可以是 "."（当前目录）、"auto" 或一个目录路径：
    先找登记过的项目，没登记但在 git 仓库里就自动识别，都不是就返回 None（非项目工作）。"""
    for proj in cfg.get("projects", []):
        if name and proj.get("name") == name:
            return proj
    if not name or name in (".", "auto"):
        target: str = os.getcwd()
    elif os.path.isdir(name):
        target = name
    else:
        return None
    return find_project(cfg, target) or detect_project(target)


def find_git_root(start: Path | str) -> Path | None:
    cur = Path(start).resolve()
    for folder in [cur] + list(cur.parents):
        if (folder / ".git").exists():
            return folder
    return None


def detect_project(start: Path | str) -> dict[str, Any] | None:
    """没登记的目录：在 git 仓库里就按常见约定自动识别测试命令和目录；不在仓库里返回 None。"""
    root = find_git_root(start)
    if root is None or root == Path.home().resolve():
        return None
    def has(rel: str) -> bool:
        return (root / rel).exists()

    source_dirs = ["src"] if has("src") else ["."]
    test_dirs = [d for d in ("tests", "test") if has(d)][:1]
    checks: dict[str, list[str]] = {}
    is_python = has("pyproject.toml") or has("setup.py") or any(root.glob("requirements*.txt"))
    runner: list[str] = []
    if is_python:
        runner = ["uv", "run"] if has("uv.lock") else ["poetry", "run"] if has("poetry.lock") else []
        pytest = runner + ["pytest"] if runner else ["{python}", "-m", "pytest"]
        if test_dirs:
            checks["tests"] = pytest + [test_dirs[0], "-q"]
            checks["collect"] = pytest + [test_dirs[0], "--collect-only", "-q"]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if has("pyproject.toml") else ""
        if "ruff" in pyproject or has("ruff.toml") or has(".ruff.toml"):
            checks["lint"] = (runner or ["{python}", "-m"]) + ["ruff", "check"] + source_dirs + test_dirs
    checks["chars"] = ["{python}", "{kit}/tools/check_chars.py"] + source_dirs + test_dirs
    return {
        "name": root.name, "path": str(root), "_auto": True, "style_pack": "",
        "python_cmd": (runner + ["python"]) if runner else ["{python}"],
        "checks": checks, "source_dirs": source_dirs, "test_dirs": test_dirs,
        "protected": [], "notes": [], "isolated_import_modules": [],
    }


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
    nodelete: bool = False,
) -> tuple[int, str]:
    """运行命令并返回 (退出码, 合并后的输出)。不经过 shell，避免引号和注入问题。
    nodelete=True 时子进程启用禁删保护（跑测试、跑项目脚本时用）。"""
    if not cmd:
        return 2, "命令为空"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    if nodelete:
        env = nodelete_env(env)
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


# ---------------------------------------------------------------- 禁删保护（运行时）

RUNTIME_DIR = KIT_ROOT / "runtime"


def nodelete_env(base: dict[str, str] | None = None, allow_delete: bool = False) -> dict[str, str]:
    """给子进程用的环境变量：启用禁删保护（见 runtime/kit_nodelete.py）。
    allow_delete=True 只在用户同意删除之后使用：删除照常执行，但每一次都记日志。"""
    env = dict(base if base is not None else os.environ)
    old = env.get("PYTHONPATH", "")
    parts = [str(RUNTIME_DIR)] + [p for p in old.split(os.pathsep) if p and p != str(RUNTIME_DIR)]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["AI_DEV_KIT_NODELETE"] = "1"
    env["AI_DEV_KIT_HOME"] = str(DATA_DIR)
    if allow_delete:
        env["AI_DEV_KIT_ALLOW_DELETE"] = "1"
    else:
        env.pop("AI_DEV_KIT_ALLOW_DELETE", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


# ---------------------------------------------------------------- 删除数据：先评估，等用户同意
#
# 流程：
#   1. 模型要运行删除数据的命令 → 守卫拦下，附上风险评估，并记一条“待同意”；
#   2. 模型把风险告诉用户，停下来等回复；
#   3. 用户回复“同意 / 可以删 / 确认删除”等 → 提交消息的钩子把这一会话里待同意的删除标记为“已同意”；
#      回复“不要 / 取消”等 → 作废；
#   4. 模型重新运行同一条命令 → 守卫放行一次（用掉就作废），并写审计日志。
# 同意只认用户在对话里亲口回复，模型自己改命令、改环境变量都绕不过去。

DELETE_REQ_PATH = DATA_DIR / "delete_requests.json"
DELETE_REQ_TTL = 30 * 60
CONSENT_YES = re.compile(r"(同意|确认删除|确定删除|可以删|删吧|删掉吧|允许删除|批准|^\s*(好|好的|可以|确认|确定|行|ok|yes|y)\s*[。.!！]*\s*$)", re.I)
CONSENT_NO = re.compile(r"(不.{0,2}同意|没同意|不要删|别删|不能删|先别删|取消|不行|不可以|算了|^\s*(no|n)\s*$)", re.I)
CONSENT_WAIT = re.compile(r"(等一下|等等|先不|先查|先看|先统计|先数|多少条|哪个库|哪个环境|\?|？)")


def command_digest(command: str) -> str:
    """命令的指纹（忽略多余空白）。用户同意的是“这一条命令”，换了命令要重新问。"""
    return hashlib.sha1(" ".join(command.split()).encode("utf-8", errors="replace")).hexdigest()[:16]


def delete_core(command: str) -> str:
    """去掉 kit_run.py 包装和 --allow-delete，只留真正要执行的命令。
    这样“被拦下的原命令”和“同意后加了 --allow-delete 的重试命令”算同一条。"""
    text = command.strip()
    at = text.lower().replace("\\", "/").find("kit_run.py")
    if at >= 0:
        sep = text.find(" -- ", at)
        if sep >= 0:
            text = text[sep + 4:]
    return " ".join(text.split())


def _delete_reqs() -> dict[str, Any]:
    data = load_json(DELETE_REQ_PATH, {}) or {}
    now = time.time()
    for sid in list(data):
        data[sid] = [r for r in data[sid] if now - float(r.get("ts", 0)) < DELETE_REQ_TTL]
        if not data[sid]:
            data.pop(sid)
    return data


def pending_deletes() -> list[dict[str, Any]]:
    """所有会话里还在等用户同意的删除（桌面机器人用来亮“等你决定”）。"""
    out: list[dict[str, Any]] = []
    for sid, items in _delete_reqs().items():
        for r in items:
            if r.get("status") == "pending":
                out.append(dict(r, session=sid))
    return sorted(out, key=lambda r: float(r.get("ts", 0)))


def delete_request(session: str, command: str, risk: str) -> None:
    data = _delete_reqs()
    digest = command_digest(command)
    items = [r for r in data.get(session, []) if r.get("digest") != digest]
    items.append({"digest": digest, "status": "pending", "ts": time.time(), "risk": risk[:600],
                  "command": redact(command, 200)})
    data[session] = items[-10:]
    save_json(DELETE_REQ_PATH, data)


def delete_consent(session: str, prompt: str) -> str:
    """用户发来新消息时调用：根据回复把待同意的删除标为同意或作废。返回 approved / rejected / ""。"""
    data = _delete_reqs()
    pending = [r for r in data.get(session, []) if r.get("status") == "pending"]
    if not pending:
        return ""
    text = prompt.strip()
    if CONSENT_NO.search(text):
        status = "rejected"
    elif CONSENT_WAIT.search(text):
        return ""  # 用户还有疑问（先查数量、问是哪个库……），继续等
    elif CONSENT_YES.search(text):
        status = "approved"
    else:
        return ""  # 用户在说别的，继续等
    for r in pending:
        r["status"] = status
        r["ts"] = time.time()
    save_json(DELETE_REQ_PATH, data)
    log_event("delete_consent", {"session": session[:12], "status": status, "count": len(pending),
                                 "commands": [r.get("command", "") for r in pending]})
    return status


def delete_status(session: str, command: str, consume: bool = False) -> str:
    """这条删除命令的状态：approved / pending / rejected / ""。consume=True 时同意用一次就作废。"""
    data = _delete_reqs()
    digest = command_digest(command)
    for r in data.get(session, []):
        if r.get("digest") == digest:
            status = str(r.get("status", ""))
            if consume and status == "approved":
                data[session].remove(r)
                save_json(DELETE_REQ_PATH, data)
            return status
    return ""


# ---------------------------------------------------------------- 三种模式

MODES = {"chat": "随手问", "workbench": "工作台", "project": "项目开发"}
MODE_PATH = DATA_DIR / "mode.json"
MODE_TTL = 12 * 3600


def location_kind(cfg: dict[str, Any], cwd: Path | str) -> tuple[str, dict[str, Any] | None]:
    """按目录判断位置：project（登记过的项目）/ repo（没登记的 git 仓库）/ other（其他目录）。"""
    proj = find_project(cfg, cwd)
    if proj:
        return "project", proj
    det = detect_project(cwd)
    if det:
        return "repo", det
    return "other", None


def read_mode_override() -> dict[str, Any]:
    data = load_json(MODE_PATH, {}) or {}
    if data.get("mode") not in MODES or time.time() - float(data.get("set_at", 0)) > MODE_TTL:
        return {}
    return data


def current_mode(cfg: dict[str, Any], cwd: Path | str) -> dict[str, Any]:
    """当前模式。没手动指定时：登记过的项目 = 项目开发，其余 = 工作台（随手问由模型按意图判断）。"""
    kind, proj = location_kind(cfg, cwd)
    auto = "project" if kind == "project" else "workbench"
    override = read_mode_override()
    root = override.get("root", "")
    if override and (not root or norm(cwd) == norm(root) or norm(cwd).startswith(norm(root).rstrip("\\/") + os.sep)):
        mode, source = str(override["mode"]), "manual"
    else:
        mode, source = auto, "auto"
    return {"mode": mode, "label": MODES[mode], "source": source, "kind": kind, "project": proj}


def set_mode(mode: str | None, root: str = "") -> None:
    if not mode or mode == "auto":
        if MODE_PATH.exists():
            MODE_PATH.unlink()
        return
    if mode not in MODES:
        raise ValueError(f"不认识的模式：{mode}，可选：{', '.join(MODES)}、auto")
    save_json(MODE_PATH, {"mode": mode, "root": root, "set_at": time.time()})


# ---------------------------------------------------------------- “问一次”的记录

APPROVALS_PATH = DATA_DIR / "approvals.json"


def args_digest(args: Any) -> str:
    try:
        raw = json.dumps(args, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        raw = str(args)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _approvals() -> dict[str, Any]:
    return load_json(APPROVALS_PATH, {}) or {}


def approval_ok(session: str, kind: str) -> bool:
    """本会话里同一类操作已经被用户放行过一次。"""
    if not session or not kind:
        return False
    return kind in (_approvals().get(session, {}) or {}).get("kinds", {})


def approval_pending(session: str, kind: str, digest: str) -> None:
    if not session or not kind:
        return
    data = _approvals()
    entry = data.setdefault(session, {"kinds": {}, "pending": [], "ts": time.time()})
    entry["pending"] = [p for p in entry.get("pending", []) if time.time() - p.get("ts", 0) < 900][-20:]
    entry["pending"].append({"kind": kind, "digest": digest, "ts": time.time()})
    entry["ts"] = time.time()
    if len(data) > 20:
        for old in sorted(data, key=lambda k: data[k].get("ts", 0))[: len(data) - 20]:
            data.pop(old, None)
    save_json(APPROVALS_PATH, data)


def approval_confirm(session: str, digest: str) -> str:
    """工具真的执行了（postToolUse），说明用户在确认框里点了允许：记下这一类，本会话不再问。"""
    data = _approvals()
    entry = data.get(session)
    if not entry:
        return ""
    for p in list(entry.get("pending", [])):
        if p.get("digest") == digest:
            entry["pending"].remove(p)
            kind = str(p.get("kind", ""))
            if kind and not kind.endswith("!"):  # 以 ! 结尾的类别每次都问
                entry.setdefault("kinds", {})[kind] = time.time()
            save_json(APPROVALS_PATH, data)
            return kind
    return ""


# ---------------------------------------------------------------- 共享模块（和同事一起开发的代码）


def shared_areas(project: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """返回 (共享区域, 例外)。旧配置里的 protected 当作共享区域处理：可以改，但要保持兼容。"""
    if not project:
        return [], []
    areas = list(project.get("shared", [])) or list(project.get("protected", []))
    allow = list(project.get("shared_allow", [])) or list(project.get("protected_allow", []))
    return areas, allow


def shared_state_path(project: dict[str, Any]) -> Path:
    return Path(project.get("path", ".")) / SCOPE_DIRNAME / "shared.json"


def read_shared_state(project: dict[str, Any]) -> dict[str, Any]:
    return load_json(shared_state_path(project), {}) or {}


def setup_console() -> None:
    """让 Windows 终端正确显示中文。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
