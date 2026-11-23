"""preToolUse 守卫钩子：Copilot 调用工具之前检查一次，按风险给出结果。

2.1 起的原则：**能当场问就当场问，能自动处理就自动处理，尽量不打断任务**。

    红线  deny   直接拦下（读密钥、git add .、项目里的 git 写操作、删整个项目或 .git……）。
                 拒绝理由里会写“跳过这一步继续其余工作”，模型不会因此结束整个任务。
    黄线  ask    Copilot 当场弹确认框，你同意它就接着执行（任务不中断）：
                 删数据（确认框里带风险评估）、删普通文件、改方案外的文件、工作台里的 git 写操作和装包……
                 同一会话里同一类（同一个文件）你同意过一次，就不再问。
    自动  改写   跑测试和项目脚本没经过 kit_run.py 时，自动套上禁删保护再执行（modifiedArgs），不拦；
                 你同意删数据时，自动加上 --allow-delete。
    绿线  allow / {}  删中间产物（缓存、临时文件、本次会话自己新建的文件）直接放行，其余不干预。

旧版本不支持当场确认（ask）或改写命令（modifiedArgs）时的退路：kit.config.json 里
    "guard": {"ask_mode": "deny"}         删数据回到“拦下 → 你在对话里回复同意 → 重新运行”
    "nodelete": {"auto_wrap": false}      跑测试回到“拦下并告诉它改成 kit_run.py”

为什么要它：写在提示词里的“禁止”，模型不一定遵守（GitHub 官方文档原话：指令不能保证
每条都被遵守）；钩子运行的是代码，可以真正拦下来。但规则写得太死会让人寸步难行，
所以只有“不可逆的损失”才是红线，其余能问就问。

位置决定规则松紧（模式见 kitlib.current_mode）：
    project  登记过的项目（tap-ai-backend 等）：完整规则
    repo     没登记的 git 仓库：工作台规则
    other    其他目录：工作台规则

Copilot CLI 通过标准输入传入 JSON（camelCase）：{"toolName", "toolArgs", "cwd", "sessionId", ...}
本脚本向标准输出写恰好一个 JSON 对象：
    {"permissionDecision": "deny" | "ask" | "allow", "permissionDecisionReason": "...", "modifiedArgs": {...}} 或 {}

注意（来自官方文档）：
- 本脚本崩溃或非 0 退出会被当成“拒绝”，所以内部异常一律捕获，按 guard.on_error 处理（默认放行）；
- 超时会被当成“放行”，所以这里只做文本判断，最多读一下要运行的脚本文件，不调用外部命令；
- 自动驾驶（autopilot）模式下 ask 会被当成拒绝。

本地自测：python guard.py --selftest
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kit_rules  # 必须在上一行把 tools 目录加进 sys.path 之后再导入
import kitlib

# ---------------------------------------------------------------- 默认规则
# 可以在 kit.config.json 的 "guard" 段覆盖或追加，见 docs/03-钩子与自定义代理.md

DEFAULT_PROTECTED_FILES = [
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "id_rsa*", "providers.json",
    "secrets.json", "secrets.yaml", "secrets.yml", "credentials.json", "*.secret",
]
DEFAULT_PROTECTED_ALLOW = [".env.template", ".env.sample"]
DEFAULT_LOCKED_FILES = ["pyproject.toml", "uv.lock", "poetry.lock", "requirements*.txt",
                        "package-lock.json", "*.lock"]

GIT_READONLY = {
    "status", "diff", "log", "show", "grep", "ls-files", "blame", "rev-parse",
    "describe", "shortlog", "cat-file", "ls-tree", "reflog", "whatchanged",
    "show-ref", "for-each-ref", "name-rev", "merge-base", "count-objects", "help",
    "version", "--version",
}

SHELL_TOOLS = {"bash", "powershell", "shell", "execute", "run_in_terminal", "terminal"}
READ_TOOLS = {"view", "read", "read_file", "cat", "open"}
WRITE_TOOLS = {"edit", "create", "write", "str_replace_editor", "apply_patch", "str_replace",
               "insert", "write_file", "multi_edit"}

PATH_KEYS = re.compile(r"(?i)^(path|file|file_?path|filename|target|uri|absolute_?path)$")
CONTENT_KEYS = re.compile(r"(?i)(new_?str|file_?text|content|text|new_?string|new_?content|input|patch|code|insert_?text)")
COMMAND_KEYS = re.compile(r"(?i)^(command|cmd|script|commands)$")

REDIRECT = re.compile(r"(?<![0-9&>\-=])>{1,2}(?!&)\s*(?!\$null\b|null\b|nul\b)[^\s|&;=]")
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
WRITE_CMDLETS = re.compile(
    r"(?i)\b(out-file|set-content|add-content|tee-object|tee)\b|\[(system\.)?io\.file\]::(write|append)"
)
LOCKFILE_PKG = re.compile(r"(?i)\buv\s+(add|remove|sync|lock)\b|\bpoetry\s+(add|remove|install|lock|update)\b|"
                          r"\b(npm|pnpm|yarn)\s+(i|install|add|remove|uninstall)\b")
PKG_INSTALL = re.compile(
    r"(?i)\b(pip3?|python\d*(\.\d+)?(\.exe)?\s+-m\s+pip|py\s+-m\s+pip)\s+(install|uninstall|download)\b|"
    r"\buv\s+pip\s+(install|uninstall|sync)\b|\bconda\s+(install|remove)\b|\bwinget\s+install\b|\bchoco\s+install\b"
)
RECURSIVE_DELETE = re.compile(
    r"(?i)\brm\s+-[a-z]*r|\bremove-item\b[^|;]*-recurse|\b(rd|rmdir)\s+/s\b|\bdel\s+/s\b|\bformat\s+[a-z]:|"
    r"\bshutil\.rmtree\b"
)
RUFF_FORMAT = re.compile(r"(?i)\bruff\s+format\b")
READ_ALLOWED_CMDS = re.compile(r"(?i)^\s*test-path\b")

# 删文件：哪些算中间产物（删了不用问）
DEFAULT_SCRATCH_DIRS = ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints",
                        "htmlcov", "*.egg-info", ".tox", ".nox"]
DEFAULT_SCRATCH_LAST = ["build", "dist", "tmp", "temp", ".tmp", "out", "_tmp*", "tmp_*", "tmp-*"]
DEFAULT_SCRATCH_FILES = ["*.pyc", "*.pyo", "*.log", "*.tmp", "*.bak", "*.orig", "*.rej", ".coverage",
                         ".coverage.*", "coverage.xml", "*.prof", "tmp_*", "tmp-*", "_tmp*", "scratch_*"]
FILE_DELETE_HEAD = re.compile(
    r"(?i)^(?:&\s*)?(?:cmd(?:\.exe)?\s+/c\s+|sudo\s+|xargs\s+(?:-\S+\s+)*)?"
    r"(rm|del|erase|rd|rmdir|remove-item|ri|unlink)(?:\.exe)?(?=\s|$)(.*)$"
)
FIND_DELETE = re.compile(r"(?i)^find\s.*(-delete\b|-exec\s+rm\b)")
LISTING_CMDS = re.compile(r"(?i)^(get-childitem|gci|ls|dir|cd|set-location|sl|pushd|popd|where-object|foreach-object|"
                          r"select-object|sort-object|write-host|echo)\b")
PARAM_WITH_VALUE = {"-erroraction", "-ea", "-warningaction", "-wa", "-depth", "-confirm"}
PARAM_TARGET = {"-path", "-literalpath", "-filter", "-include", "-name"}
CONTINUE = "跳过这一步即可：继续做其余能做的部分，最后在报告里写明需要用户做什么，不要因此结束整个任务。"
NODELETE_TAMPER = re.compile(r"(?i)AI_DEV_KIT_(?:NODELETE|ALLOW_DELETE)")
COPILOT_SKILL_CMD = re.compile(r"(?i)\bcopilot\s+(skill|plugin)\s+(list|add|install|info|enable)\b")

PYTEST_RUN = re.compile(r"(?i)(?:^|[\s;&|(\"'/\\])(?:pytest|py\.test)(?:\.exe)?(?=[\s\"']|$)")
PY_RUN = re.compile(r"(?i)(?:^|[\s;&|(\"'/\\])(?:python\d*(?:\.\d+)?|py)(?:\.exe)?[\"']?\s+(?P<rest>.*)$")
RUNNER_RUN = re.compile(r"(?i)\b(?:uv|poetry|pipenv|pdm|hatch|rye)\s+run\s+(?P<rest>.*)$")
NON_CODE_TOOLS = {"ruff", "mypy", "black", "isort", "flake8", "pyright", "pylint", "bandit", "pre-commit"}
PY_FILE = re.compile(r"[\"']?((?:[A-Za-z]:)?[^\s\"'|;&]*\.py)\b")

PY_FORBIDDEN_MARKERS = [
    (re.compile(r"#\s*type:\s*ignore(?!\[import-untyped\])"), "新增了 `# type: ignore`（只允许照抄已有的 `# type: ignore[import-untyped]`）"),
    (re.compile(r"#\s*noqa\b"), "新增了 `# noqa`"),
    (re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b|\bpytest\.(skip|xfail)\("), "新增了跳过或预期失败的测试标记"),
    (re.compile(r"\bcast\(\s*Any\s*,"), "新增了 `cast(Any, ...)`"),
]
INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

SEVERITY = {"none": 0, "allow": 1, "ask": 2, "deny": 3}


@dataclass
class Verdict:
    decision: str = "none"   # none / allow / ask / deny
    reason: str = ""
    rule: str = ""
    kind: str = ""           # ask 时的类别，用于“同类只问一次”；以 ! 结尾表示每次都问
    rewrite: str = ""        # 要替换成的命令（自动套禁删保护、自动加 --allow-delete）；空表示不改

    @staticmethod
    def deny(rule: str, reason: str) -> "Verdict":
        return Verdict("deny", f"[{rule}] {reason}", rule)

    @staticmethod
    def ask(rule: str, reason: str, kind: str = "") -> "Verdict":
        return Verdict("ask", f"[{rule}] {reason}", rule, kind or rule)

    @staticmethod
    def allow(rule: str, reason: str) -> "Verdict":
        return Verdict("allow", f"[{rule}] {reason}", rule)


def worst(verdicts: list[Verdict]) -> Verdict:
    best = next((v for v in verdicts if v.rule), Verdict())  # 都放行时保留带说明的那条（例如 delete-approved）
    for v in verdicts:
        if SEVERITY[v.decision] > SEVERITY[best.decision]:
            best = v
    return best


# ---------------------------------------------------------------- 工具函数


def _collect(obj: Any, key: str = "", out: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    """把 toolArgs 里所有字符串连同它的键名收集出来（参数结构因版本而异，所以不写死）。"""
    out = out if out is not None else []
    if isinstance(obj, str):
        out.append((key, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect(v, str(k), out)
    elif isinstance(obj, list):
        for v in obj:
            _collect(v, key, out)
    return out


def _paths_from_patch(text: str) -> list[str]:
    """apply_patch 的补丁里取出被修改的文件路径。"""
    found = re.findall(r"(?m)^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$", text)
    found += re.findall(r"(?m)^(?:\+\+\+|---)\s+(?:[ab]/)?(\S+)", text)
    return [p for p in found if p not in {"/dev/null"}]


def _split_shell(command: str) -> list[str]:
    """按 ; && || | 和换行拆成多段，逐段判断。引号里的分隔符不算（例如 python -c "import a; a.b()"）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif command.startswith(("&&", "||"), i):
            parts.append("".join(buf))
            buf = []
            i += 1
        elif ch in ";|\n":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _strip_quotes(text: str) -> str:
    """引号里的内容换成占位：判断重定向时不受字符串内容影响（例如 python -c "print(a > b)"）。"""
    return QUOTED.sub("''", text)


def _tokens(text: str) -> list[str]:
    return [t.strip("\"'") for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", text)]


def _short(items: list[str], n: int = 4) -> str:
    return "、".join(items[:n]) + (f" 等 {len(items)} 个" if len(items) > n else "")


def _with_allow_delete(command: str) -> str:
    """给命令里每个 kit_run.py 加上 --allow-delete（用户在确认框里同意删除后才会真正执行）。"""
    return re.sub(r"(kit_run\.py[\"']?)(\s+)(?!--allow-delete)", r"\1 --allow-delete\2", command)


def _git_subcommand(segment: str) -> tuple[str, list[str]] | None:
    tokens = re.findall(r"\"[^\"]*\"|'[^']*'|\S+", segment)
    while tokens and tokens[0] in {"&", "."}:  # PowerShell 的调用写法：& git status
        tokens = tokens[1:]
    if not tokens:
        return None
    head = tokens[0].strip("&").strip("\"'").lower()
    if head.endswith("git.exe"):
        head = "git"
    if head != "git" and not head.endswith("/git") and not head.endswith("\\git"):
        return None
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in {"-C", "-c", "--git-dir", "--work-tree"}:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t.lower(), [x.lower() for x in tokens[i + 1:]]
    return "", []


def _git_write_reason(sub: str, rest: list[str]) -> str | None:
    """返回“这是写操作”的说明；只读命令返回 None。"""
    if sub in GIT_READONLY or sub == "":
        return None
    if sub == "branch":
        writes = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                  "-u", "--set-upstream-to", "--unset-upstream", "--edit-description"}
        if any(r in writes for r in rest):
            return "git branch 带了修改参数"
        names = [r for r in rest if not r.startswith("-")]
        if names and not any(r in {"--list", "-l", "--contains", "--merged", "--no-merged", "--points-at"} for r in rest):
            return "git branch <名字> 会新建分支"
        return None
    if sub == "stash":
        return None if rest[:1] in (["list"], ["show"]) else "git stash 会改动工作区"
    if sub == "remote":
        return None if not rest or rest[:1] in (["-v"], ["show"], ["get-url"]) else "git remote 会修改远程配置"
    if sub == "config":
        return None if any(r in {"--get", "--get-all", "--list", "-l", "--get-regexp"} for r in rest) else "git config 会修改配置"
    if sub == "tag":
        return None if not rest or rest[:1] in (["-l"], ["--list"]) else "git tag 会新建或删除标签"
    if sub == "worktree":
        return None if rest[:1] == ["list"] else "git worktree 会改动工作区"
    if sub == "submodule":
        return None if rest[:1] in (["status"], ["summary"]) else "git submodule 会改动子模块"
    return f"git {sub} 是写操作"


def _is_add_all(sub: str, rest: list[str]) -> bool:
    return sub == "add" and any(r in {".", "-a", "--all", "-u", "--update", ":/", "*"} or r.endswith("/.") for r in rest)


def _under(path: str, root: str) -> bool:
    p, r = kitlib.norm(path), kitlib.norm(root).rstrip("\\/")
    return p == r or p.startswith(r + os.sep)


def _abs(path: str, cwd: str) -> str:
    return path if os.path.isabs(path) else os.path.join(cwd, path)


def _needs_wrapper(seg: str, kit_root: str, cwd: str, only_pytest: bool) -> bool:
    """这一段命令会运行 Python 代码（测试、脚本、python -c / -m），却没有通过 kit_run.py。"""
    low = seg.lower().replace("\\", "/")
    if "kit_run.py" in low:
        return False
    if PYTEST_RUN.search(seg):
        return True
    if only_pytest:
        return False
    m = RUNNER_RUN.search(seg)
    if m:
        first = (m.group("rest").split() or [""])[0].strip("\"'").lower()
        return first not in NON_CODE_TOOLS
    m = PY_RUN.search(seg)
    if not m:
        return False
    rest = m.group("rest").strip()
    tokens = rest.split()
    if not tokens or tokens[0] in {"-V", "--version", "-h", "--help"}:
        return False
    if re.match(r"(?i)-m\s+(pip|venv|ensurepip|site)\b", rest):
        return False
    scripts = PY_FILE.findall(rest)
    if scripts and _under(_abs(scripts[0], cwd), kit_root):
        return False  # 工具包自己的脚本（run_checks.py 等）内部会处理保护
    return bool(re.search(r"(?i)(^|\s)-[a-z]*[cm]\b", rest) or scripts)


SEARCH_HEADS = {"grep", "egrep", "rg", "findstr", "select-string", "sls", "git", "cat", "type", "get-content", "gc",
                "less", "more", "head", "tail", "ls", "dir", "get-childitem", "gci", "where", "where-object", "echo",
                "write-host", "write-output", "sort", "sort-object", "select-object", "measure-object", "wc", "find"}


def _search_only(command: str) -> bool:
    """整条命令只是在搜索、查看文本（例如 grep "DELETE FROM" src），不会执行任何语句。"""
    for seg in _split_shell(command):
        head = seg.split()[0].strip("&\"'").lower() if seg.split() else ""
        head = head.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")
        if head not in SEARCH_HEADS:
            return False
        if head == "git" and not re.match(r"(?i)git\s+(?:--no-pager\s+)?(grep|log|show|diff|blame)\b", seg):
            return False
    return True


def _wrapped(seg: str, cfg: dict[str, Any], shell: str) -> str:
    py = kitlib.python_exe(cfg)
    runner = str(kitlib.KIT_ROOT / "tools" / "kit_run.py")
    if shell == "powershell":
        return f"& \"{py}\" \"{runner}\" -- {seg}"
    return f"\"{py}\" \"{runner}\" -- {seg}"


def _script_findings(seg: str, cwd: str, kit_root: str) -> list[str]:
    """要运行的 .py 脚本里有没有删数据的写法（只读文件，不执行）。"""
    out: list[str] = []
    for f in PY_FILE.findall(seg):
        path = _abs(f, cwd)
        if _under(path, kit_root) or not os.path.isfile(path):
            continue
        try:
            if os.path.getsize(path) > 512_000:
                continue
            text = kitlib.read_text(path)
        except OSError:
            continue
        for item in kit_rules.scan_python(text)[:3]:
            out.append(f"{f} {item.describe()}")
    return out


# ---------------------------------------------------------------- 主判断


class Guard:
    def __init__(self, cfg: dict[str, Any], forced_mode: str | None = None):
        g = cfg.get("guard", {}) or {}
        nd = cfg.get("nodelete", {}) or {}
        self.cfg = cfg
        self.forced_mode = forced_mode
        self.enabled = g.get("enabled", True)
        self.protected = list(g.get("protected_files", DEFAULT_PROTECTED_FILES)) + list(g.get("extra_protected_files", []))
        self.protected_allow = list(g.get("protected_allow", DEFAULT_PROTECTED_ALLOW))
        self.locked = list(g.get("locked_files", DEFAULT_LOCKED_FILES))
        self.check_python_markers = g.get("check_python_markers", True)
        self.enforce_scope = g.get("enforce_scope", True)
        self.extra_deny = [re.compile(p) for p in g.get("extra_deny_command_patterns", [])]
        self.extra_ask = [re.compile(p) for p in g.get("extra_ask_command_patterns", [])]
        self.nodelete = nd.get("enabled", True)
        self.require_wrapper = nd.get("require_wrapper", True)
        self.auto_wrap = nd.get("auto_wrap", True)
        self.ask_mode = str(g.get("ask_mode", "ask")).lower()
        self.check_file_delete = g.get("check_file_delete", True)
        self.scratch_dirs = DEFAULT_SCRATCH_DIRS + list(g.get("extra_scratch_dirs", []))
        self.scratch_last = DEFAULT_SCRATCH_LAST + list(g.get("extra_scratch_dirs", []))
        self.scratch_files = DEFAULT_SCRATCH_FILES + list(g.get("extra_scratch_files", []))
        self.kit_root = str(kitlib.KIT_ROOT)
        self.session = ""
        self.session_files: dict[str, Any] = {"created": [], "edited": []}
        self.shell = "powershell" if kitlib.IS_WINDOWS else "bash"
        self.want_allow_delete = False
        self.modified_args: Any = None

    # -- 文件类

    def _is_protected(self, path: str) -> bool:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if kitlib.match_any(name, self.protected_allow):
            return False
        return kitlib.match_any(name, self.protected) or kitlib.match_any(path, self.protected)

    # -- 删文件：中间产物直接放行，整个项目 / .git 拒绝，其余当场问

    def _delete_kind(self, target: str, cwd: str, loc: dict[str, Any]) -> str:
        """danger / scratch / normal / unknown。"""
        import tempfile

        t = target.strip().strip("\"'").rstrip("\\/") or target.strip()
        low = t.lower().replace("\\", "/")
        if not t or "{}" in t:
            return "unknown"
        if low.startswith(("$env:temp", "$env:tmp", "%temp%", "%tmp%", "/tmp/", "$tmpdir", "${tmpdir}")):
            return "scratch"
        if "$" in t or "%" in t:
            return "unknown"
        if low in {"*", "*.*", ".", "..", "./", ".\\", "/", "~", "./*", "../*"} or re.match(r"^[a-z]:/?\*?$", low):
            return "danger"
        n = kitlib.norm(_abs(t, cwd))
        project = loc.get("project") or {}
        roots = {kitlib.norm(Path.home())}
        for r in (project.get("path"), project.get("git_root"), str(kitlib.find_git_root(cwd) or "")):
            if r:
                roots.add(kitlib.norm(r))
        parts = [x for x in low.split("/") if x not in ("", ".")]
        if n in roots or ".git" in parts:
            return "danger"
        # 系统临时目录里的东西算中间产物（工作目录本身就在临时目录里时不算，例如自测）
        tmp_root = kitlib.norm(tempfile.gettempdir()).rstrip("\\/") + os.sep
        if not kitlib.norm(cwd).startswith(tmp_root) and (
                n.startswith(tmp_root) or "/appdata/local/temp/" in n.replace("\\", "/")):
            return "scratch"
        name = parts[-1] if parts else low
        if any(kitlib.match_any(part, self.scratch_dirs) for part in parts):
            return "scratch"
        if kitlib.match_any(name, self.scratch_last) or kitlib.match_any(name, self.scratch_files):
            return "scratch"
        if n in self.session_files.get("created", []):
            return "scratch"
        return "normal"

    def _delete_targets(self, seg: str, rest: str, segments: list[str]) -> list[str]:
        targets: list[str] = []
        toks = _tokens(rest)
        i = 0
        while i < len(toks):
            tok, low = toks[i], toks[i].lower()
            if low in PARAM_WITH_VALUE:
                i += 2
                continue
            if low in PARAM_TARGET and i + 1 < len(toks):
                targets += [x for x in toks[i + 1].split(",") if x]
                i += 2
                continue
            if tok.startswith("-") or re.match(r"^/[a-zA-Z]$", tok) or tok in {"{}", "+", "\\;"}:
                i += 1
                continue
            targets += [x for x in tok.split(",") if x]
            i += 1
        if not targets:
            # 管道写法：Get-ChildItem -Filter __pycache__ -Recurse | Remove-Item -Recurse
            for other in segments:
                if other is seg or not LISTING_CMDS.match(other):
                    continue
                o = _tokens(other)
                for k, tok in enumerate(o[1:], start=1):
                    prev = o[k - 1].lower()
                    if prev in PARAM_WITH_VALUE:
                        continue
                    if (prev in PARAM_TARGET or not tok.startswith("-")) and tok.lower() not in PARAM_TARGET \
                            and not tok.startswith("$_") and tok not in {"{", "}"}:
                        targets.append(tok)
        return targets

    def check_file_delete_segment(self, seg: str, segments: list[str], cwd: str, loc: dict[str, Any]) -> Verdict | None:
        m = FILE_DELETE_HEAD.match(seg)
        if m:
            rest = m.group(2)
        elif FIND_DELETE.match(seg):
            rest = " ".join(re.findall(r"(?i)-i?name\s+(\"[^\"]*\"|'[^']*'|\S+)", seg))
        elif re.search(r"\bshutil\.rmtree\b|\bos\.(remove|unlink|rmdir)\b", seg):
            rest = " ".join(QUOTED.findall(seg))  # python -c "shutil.rmtree('build')"
        else:
            return None
        targets = self._delete_targets(seg, rest, segments)
        kinds = [(t, self._delete_kind(t, cwd, loc)) for t in targets]
        danger = [t for t, k in kinds if k == "danger"]
        if danger:
            return Verdict.deny("dangerous-delete", f"要删除 {_short(danger)}：这是整个项目、.git、用户目录或盘符根目录。"
                                f"只删具体的文件或缓存目录。{CONTINUE}")
        others = [t for t, k in kinds if k != "scratch"]
        if kinds and not others:
            return Verdict.allow("scratch-delete", f"删除中间产物：{_short(targets)}")
        if not others:
            return Verdict.ask("file-delete", "要删除文件，但命令里看不出具体删哪些。确认删除就继续；不同意可以告诉它保留什么。",
                               "file-delete!")
        key = "|".join(sorted(kitlib.norm(_abs(t, cwd)) for t in others))[:300]
        return Verdict.ask("file-delete", f"要删除 {_short(others)}。确认删除就继续；不同意可以告诉它保留什么。",
                           f"file-delete:{key}")

    def check_read(self, paths: list[str]) -> Verdict:
        for p in paths:
            if self._is_protected(p):
                return Verdict.deny("protected-file", f"禁止读取可能含密钥的文件：{p}。需要里面的配置项名字时，请让用户告诉你配置名和是否已设置，不要打开文件。" + CONTINUE)
        return Verdict()

    def check_write(self, paths: list[str], contents: list[str], cwd: str, loc: dict[str, Any]) -> Verdict:
        kind, project, mode = loc["kind"], loc["project"], loc["mode"]
        out: list[Verdict] = []
        base_root = str((project or {}).get("git_root") or (project or {}).get("path") or cwd)
        for p in paths:
            if self._is_protected(p):
                return Verdict.deny("protected-file", f"禁止修改可能含密钥的文件：{p}。{CONTINUE}")
            abs_p = _abs(p, cwd)
            scope_root, scope = kitlib.find_scope(os.path.dirname(abs_p) or cwd)
            rel = kitlib.rel_posix(abs_p, scope_root) if scope_root else p.replace("\\", "/")
            scope_allows = bool(scope) and kitlib.match_any(rel, list(scope.get("files", [])) + list(scope.get("globs", [])))
            if kitlib.match_any(rel, self.locked) and not (scope_allows and scope.get("allow_locked")):
                if kind == "project":
                    return Verdict.deny("locked-file", f"项目里禁止直接修改依赖和锁定文件：{rel}。需要新增或升级依赖时，"
                                        f"把要改的内容写进报告，由用户决定。{CONTINUE}")
                out.append(Verdict.ask("locked-file", f"要修改依赖文件 {rel}，请用户确认。", "locked-file"))
            if kind == "project" and project:
                proj_rel = kitlib.rel_posix(abs_p, project.get("path", cwd))
                locked_areas = list(project.get("locked_areas", []))
                if locked_areas and kitlib.match_any(proj_rel, locked_areas) and not scope_allows:
                    return Verdict.deny("locked-area", f"{proj_rel} 属于配置里写明不能改的区域（{', '.join(locked_areas)}）。{CONTINUE}")
                areas, allow = kitlib.shared_areas(project)
                if areas and kitlib.match_any(proj_rel, areas) and not kitlib.match_any(proj_rel, allow):
                    state = kitlib.read_shared_state(project)
                    if not state.get("baseline"):
                        cmd = f"\"{kitlib.python_exe(self.cfg)}\" \"{kitlib.KIT_ROOT / 'tools' / 'run_checks.py'}\" --shared-baseline"
                        return Verdict.deny("shared-baseline", f"{proj_rel} 属于共享模块（和同事一起开发，可以改，但不能改坏）。"
                                            f"改之前先记录测试基线：{cmd}。记录后直接接着改，不用问用户；改完一键验证会对比基线，"
                                            "通过数不能变少，并在评审时检查对外接口是否兼容。")
            if self.enforce_scope and scope and scope.get("files") is not None and not scope_allows:
                allowed = list(scope.get("files", [])) + list(scope.get("globs", []))
                preview = "、".join(allowed[:8]) + ("……" if len(allowed) > 8 else "")
                if self.ask_mode == "deny":
                    return Verdict.deny("out-of-scope", f"{rel} 不在本次允许修改的文件名单里（{preview or '空'}）。"
                                        "确需修改时说明原因，用户同意后运行 scope.py add 把它加进名单；其余工作照常继续。")
                out.append(Verdict.ask("out-of-scope", f"要修改 {rel}：不在这次方案列出的文件里（{preview or '空'}）。"
                                       "同意后会自动加进修改范围，同一个文件不会再问。", f"out-of-scope:{rel}"))
                continue
            if not _under(abs_p, base_root) and not _under(abs_p, cwd):
                folder = os.path.dirname(abs_p)
                out.append(Verdict.ask("outside-write", f"要写当前工作目录以外的位置：{abs_p}。请用户确认。",
                                       f"outside-write:{kitlib.norm(folder)}"))
            elif mode == "chat":
                out.append(Verdict.ask("chat-write", "当前是随手问模式，改文件前先问用户。", "chat-write"))
        kit_root = kitlib.norm(self.kit_root)
        code_py = [p for p in paths if p.lower().endswith((".py", ".pyi"))]
        project_py = [p for p in code_py if not kitlib.norm(_abs(p, cwd)).startswith(kit_root)]
        if kind == "project" and self.check_python_markers and project_py:
            for text in contents:
                for pattern, reason in PY_FORBIDDEN_MARKERS:
                    if pattern.search(text):
                        return Verdict.deny("forbidden-marker", f"{reason}。请从根本上修复问题后直接继续，不要屏蔽检查。")
        for text in contents:
            m = INVISIBLE.search(text)
            if m:
                return Verdict.deny("invisible-char", f"写入内容里含隐形字符 U+{ord(m.group(0)):04X}，删掉后重新写入即可。")
            if code_py and "\u3000" in text:
                return Verdict.deny("fullwidth-space", "Python 代码里含全角空格 U+3000，改成普通空格后重新写入即可。")
        return worst(out)

    # -- 删除数据：当场问用户（确认框里带风险评估）

    def _delete_gate(self, command: str, risk: "kit_rules.Risk", python_run: bool) -> Verdict:
        """删数据不是不行，是不能乱删。

        ask_mode=ask（默认）：Copilot 当场弹确认框，里面写着风险评估；你同意它就接着执行，任务不中断。
            测试和脚本会自动加上 --allow-delete，同意后删除才会真的执行。每次都问，不会“问一次管一会话”。
        ask_mode=deny（旧版本不支持当场确认时）：先拦下 → 模型把风险告诉你 → 你在对话里回复同意 → 同一条放行一次。
        """
        if self.ask_mode != "deny":
            if python_run:
                self.want_allow_delete = True
            return Verdict.ask("data-delete", "这一步会删除数据。\n" + risk.render()
                               + "\n同意就执行（测试和脚本会以允许删除的方式运行，每次删除都记日志）；"
                               "不同意可以在确认框里写一句原因或替代做法（比如先导出、改成软删除）。",
                               "data-delete!")
        core = kitlib.delete_core(command)
        status = kitlib.delete_status(self.session, core)
        if status == "approved" and python_run and "--allow-delete" not in command:
            return Verdict.deny("delete-needs-flag", "用户已同意这次删除。测试和脚本要加 --allow-delete 才会真的删，请改成："
                                + _wrapped(core, self.cfg, self.shell).replace(" -- ", " --allow-delete -- ", 1))
        if status == "approved":
            kitlib.delete_status(self.session, core, consume=True)
            kitlib.log_event("delete_allowed", {"session": self.session[:12], "command": kitlib.redact(core, 300),
                                                "risk": risk.level})
            return Verdict("none", "用户已同意这次删除", "delete-approved", "")
        if status == "rejected":
            return Verdict.deny("delete-rejected", "用户已经拒绝了这次删除。不要换个写法再试；"
                                "如果仍然认为需要删除，把原因和替代方案（软删除、导出后再删）写给用户，由用户决定。")
        kitlib.delete_request(self.session, core, risk.render())
        if python_run:
            retry = ("用这条命令重新运行：" + _wrapped(core, self.cfg, self.shell).replace(" -- ", " --allow-delete -- ", 1))
        else:
            retry = "原样重新运行这条命令"
        return Verdict.deny("delete-needs-consent",
                            "这一步会删除数据，已先拦下，什么都没执行。删除可以做，但要用户先同意。\n"
                            f"{risk.render()}\n"
                            "请先把上面的风险评估告诉用户（要删什么、范围多大、能不能恢复、建议先做什么；"
                            "能先做只读计数就先做，把数量一起告诉用户），然后停下来等用户回复。"
                            f"用户明确回复“同意”后，{retry}。用户没同意之前，不要换写法、拆命令或改用别的工具绕过。")


    # -- 命令类

    def check_command(self, command: str, cwd: str, loc: dict[str, Any], shell: str) -> Verdict:
        kind = loc["kind"]
        self.shell = shell
        self.want_allow_delete = False
        out: list[Verdict] = []
        delete_approved: Verdict | None = None
        data_ask = False          # 删数据：已经决定当场问用户
        wraps: list[str] = []     # 要自动套上禁删保护的命令段
        scratch_only = True       # 整条命令是不是只在删中间产物（是才替你放行）
        for pattern in self.extra_deny:
            if pattern.search(command):
                return Verdict.deny("custom-deny", f"命令命中自定义禁止规则：{pattern.pattern}。{CONTINUE}")
        for pattern in self.extra_ask:
            if pattern.search(command):
                out.append(Verdict.ask("custom-ask", f"命令命中需要确认的规则：{pattern.pattern}", "custom-ask!"))
        if self.nodelete:
            if NODELETE_TAMPER.search(command):
                return Verdict.deny("nodelete-tamper", "不要在命令里改禁删保护的环境变量。需要删除数据时直接运行原命令，"
                                    "守卫会当场请用户确认。")
            searching = _search_only(command)
            found = [] if searching else kit_rules.scan_text(command)
            removed = None if searching else kit_rules.scan_remove(command)
            if removed:
                found.append(removed)
            if found:
                runs_python = bool("kit_run.py" in command or PY_RUN.search(command) or PYTEST_RUN.search(command))
                gate = self._delete_gate(command, kit_rules.assess(command, found), python_run=runs_python)
                if gate.decision == "deny":
                    return gate
                if gate.decision == "ask":
                    out.append(gate)
                    data_ask = True
                else:
                    delete_approved = gate
        segments = _split_shell(command)
        for seg in segments:
            if READ_ALLOWED_CMDS.search(seg):
                scratch_only = False
                continue
            for token in re.findall(r"[^\s'\"=<>|;,()]+", seg):
                cleaned = token.strip("'\"`")
                if cleaned and self._is_protected(cleaned):
                    return Verdict.deny("protected-file", f"命令涉及可能含密钥的文件：{cleaned}。请不要读取或打印它；"
                                        f"需要某个配置时只问用户是否已设置。{CONTINUE}")
            if COPILOT_SKILL_CMD.search(seg):
                scratch_only = False
                continue  # 登记、查看技能和插件是安全的
            parsed = _git_subcommand(seg)
            if parsed is not None:
                sub, rest = parsed
                if _is_add_all(sub, rest):
                    return Verdict.deny("git-add-all", "禁止 git add . / -A / --all：仓库里可能有不该提交的改动（例如脏的子模块）。"
                                        f"需要提交时逐个文件写出 git add 命令，放进最后的报告交给用户。{CONTINUE}")
                why = _git_write_reason(sub, rest)
                if why:
                    if kind == "project":
                        return Verdict.deny("git-write", f"{why}。登记过的项目里 git 写操作一律由用户执行；"
                                            f"把要执行的命令写进最后的报告。{CONTINUE}")
                    out.append(Verdict.ask("git-write", f"{why}，请用户确认。", f"git-{sub}"))
            if LOCKFILE_PKG.search(seg):
                if kind == "project":
                    return Verdict.deny("package-install", "项目里禁止用 uv add / sync / lock 等命令改依赖和锁定文件。"
                                        f"缺依赖时先运行 kit_env.py 全量体检，把需要的依赖写进报告交给用户。{CONTINUE}")
                out.append(Verdict.ask("package-install", "要安装或修改依赖，请用户确认（建议先全量体检，合并成一条命令）。",
                                       "package-install"))
            elif PKG_INSTALL.search(seg):
                out.append(Verdict.ask("package-install", "要安装或卸载依赖包，请用户确认（建议先全量体检，合并成一条命令）。",
                                       "package-install"))
            if RUFF_FORMAT.search(seg) and kind == "project":
                return Verdict.deny("ruff-format", f"项目里禁止对已有文件运行 ruff format（会产生大量无关改动）。只用 ruff check。{CONTINUE}")
            if WRITE_CMDLETS.search(seg) or REDIRECT.search(_strip_quotes(seg)):
                if kind == "project":
                    return Verdict.deny("shell-write", "项目里禁止用 > / >> / Out-File / Set-Content 写文件（Windows PowerShell 5 "
                                        f"默认写成 UTF-16）。看输出就直接显示（可以接 | Select-Object -Last 50），改文件用编辑工具。{CONTINUE}")
                out.append(Verdict.ask("shell-write", "要用命令把输出写进文件（PowerShell 5 可能写成 UTF-16），请用户确认。",
                                       "shell-write"))
            file_del = self.check_file_delete_segment(seg, segments, cwd, loc) if self.check_file_delete else None
            if file_del is not None:
                if file_del.decision == "deny":
                    return file_del
                if file_del.decision != "allow":
                    scratch_only = False
                out.append(file_del)
            elif RECURSIVE_DELETE.search(seg):
                scratch_only = False
                out.append(Verdict.ask("recursive-delete", "要递归删除目录或文件，请用户确认。", "recursive-delete!"))
            elif not LISTING_CMDS.match(seg):
                scratch_only = False
            if self.nodelete:
                if self.require_wrapper and _needs_wrapper(seg, self.kit_root, cwd, only_pytest=(kind == "other")):
                    if not self.auto_wrap:
                        return Verdict.deny("need-kit-run", "跑测试和项目脚本要在禁删保护下运行（数据可以写；要删先问用户）。"
                                            f"请改成：{_wrapped(seg, self.cfg, shell)}")
                    wraps.append(seg)
                if delete_approved or data_ask:
                    continue
                bad = [] if (PYTEST_RUN.search(seg) or re.search(r"(?i)\s-m\s", seg)) else _script_findings(seg, cwd, self.kit_root)
                if not bad and re.search(r"(?i)\s-c\s", seg):
                    bad = [f.describe() for f in kit_rules.scan_python(seg)[:3]]
                allow_flag = bool(re.search(r"kit_run\.py['\"]?\s+(?:\S+\s+)*?--allow-delete\b", seg))
                approved_before = (not bad and not allow_flag and self.ask_mode == "deny"
                                   and kitlib.delete_status(self.session, kitlib.delete_core(seg)) == "approved")
                if bad or allow_flag or approved_before:
                    risk = kit_rules.assess(seg + "\n" + "\n".join(bad))
                    if bad:
                        risk.what = bad
                    else:
                        risk.what = ["运行过程中所有被禁删保护拦截的删除调用都会放行（测试或脚本里的清理代码）"]
                    gate = self._delete_gate(seg, risk, python_run=True)
                    if gate.decision == "deny":
                        return gate
                    if gate.decision == "ask":
                        out.append(gate)
                        data_ask = True
                    else:
                        delete_approved = gate
        result = worst(out)
        if result.decision == "allow" and (not scratch_only or not segments):
            result = Verdict()  # 命令里还有别的操作：交给 Copilot 自己的权限流程
        if delete_approved is not None and result.decision == "none":
            result = delete_approved  # 用户同意过的删除：放行，并在日志里记成 delete-approved
        new_command = command
        for seg in wraps:
            new_command = new_command.replace(seg, _wrapped(seg, self.cfg, shell), 1)
        if self.want_allow_delete:
            if "kit_run.py" not in new_command:
                new_command = _wrapped(new_command, self.cfg, shell)
            new_command = _with_allow_delete(new_command)
        if new_command != command:
            result.rewrite = new_command
            if not result.rule:
                result.rule = "auto-kit-run"
        return result

    # -- 入口

    def location(self, cwd: str) -> dict[str, Any]:
        info = kitlib.current_mode(self.cfg, cwd)
        if self.forced_mode:
            info = dict(info, mode=self.forced_mode)
        return info

    def decide(self, payload: dict[str, Any]) -> Verdict:
        if not self.enabled:
            return Verdict()
        tool = str(payload.get("toolName") or payload.get("tool_name") or "").lower()
        args = payload.get("toolArgs", payload.get("tool_input", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {"input": args}
        cwd = str(payload.get("cwd") or os.getcwd())
        self.session = str(payload.get("sessionId") or payload.get("session_id") or "")
        self.session_files = kitlib.session_files(self.session)
        self.modified_args: Any = None
        loc = self.location(cwd)
        strings = _collect(args)
        paths = [v for k, v in strings if PATH_KEYS.match(k)]
        commands = [v for k, v in strings if COMMAND_KEYS.match(k)]
        contents = [v for k, v in strings if CONTENT_KEYS.search(k) and not PATH_KEYS.match(k)]
        for text in contents:
            if "*** " in text or text.startswith(("--- ", "diff --git")):
                paths.extend(_paths_from_patch(text))

        verdicts: list[Verdict] = []
        rewrites: dict[str, str] = {}
        if tool in SHELL_TOOLS or commands:
            shell = "powershell" if tool == "powershell" or kitlib.IS_WINDOWS and tool != "bash" else "bash"
            for cmd in commands or [v for _, v in strings]:
                v = self.check_command(cmd, cwd, loc, shell)
                verdicts.append(v)
                if v.rewrite:
                    rewrites[cmd] = v.rewrite
                if v.decision == "deny":
                    break
        if tool in READ_TOOLS or tool in {"grep", "rg", "glob"}:
            verdicts.append(self.check_read(paths))
        if tool in WRITE_TOOLS or (paths and contents and tool not in READ_TOOLS):
            verdicts.append(self.check_write(paths, contents, cwd, loc))
        result = worst(verdicts)
        if rewrites and result.decision != "deny" and isinstance(args, dict):
            self.modified_args = _replace_strings(args, rewrites)
        return result


def _replace_strings(obj: Any, mapping: dict[str, str]) -> Any:
    """复制一份工具参数，把其中的命令换成改写后的（其余参数原样保留）。"""
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _replace_strings(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_strings(v, mapping) for v in obj]
    return obj


def _new_files(payload: dict[str, Any], cwd: str) -> list[str]:
    """这次调用会新建的文件（调用前还不存在）：记下来，之后删除它们不用再问。"""
    tool = str(payload.get("toolName") or payload.get("tool_name") or "").lower()
    if tool not in WRITE_TOOLS:
        return []
    args = payload.get("toolArgs", payload.get("tool_input", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return []
    return [_abs(v, cwd) for k, v in _collect(args) if PATH_KEYS.match(k) and not os.path.exists(_abs(v, cwd))]


def handle(raw: str) -> dict[str, Any]:
    cfg = kitlib.load_config()
    on_error = (cfg.get("guard", {}) or {}).get("on_error", "allow")
    try:
        payload = json.loads(raw) if raw.strip() else {}
        session = str(payload.get("sessionId") or payload.get("session_id") or "")
        guard = Guard(cfg)
        verdict = guard.decide(payload)
        modified = guard.modified_args
        approved_before = False
        if verdict.decision == "ask" and kitlib.approval_ok(session, verdict.kind):
            approved_before = True
        kitlib.log_event("guard", {
            "tool": payload.get("toolName") or payload.get("tool_name"),
            "decision": "approved-before" if approved_before else verdict.decision, "rule": verdict.rule,
            "reason": kitlib.redact(verdict.reason, 160) if verdict.decision in ("deny", "ask") else "",
            "rewritten": bool(modified),
            "args": kitlib.redact(json.dumps(payload.get("toolArgs", payload.get("tool_input", "")), ensure_ascii=False), 300),
            "cwd": payload.get("cwd"), "session": session[:12],
        })
        if verdict.decision != "deny":
            created = _new_files(payload, str(payload.get("cwd") or os.getcwd()))
            if created:
                kitlib.session_add("created", created, session)
        if verdict.decision in ("deny", "ask") and not approved_before:
            try:  # 计量失败不影响拦截
                import kit_metrics

                kit_metrics.record("guard", {"sessionId": session, "cwd": payload.get("cwd"), "decision": verdict.decision})
            except Exception as exc:
                kitlib.log_event("guard", {"where": "metrics", "error": repr(exc)[:200]})
        out: dict[str, Any] = {}
        if verdict.decision == "deny":
            return {"permissionDecision": "deny", "permissionDecisionReason": "ai-dev-kit 守卫：" + verdict.reason}
        if verdict.decision == "ask" and not approved_before:
            digest = kitlib.args_digest(payload.get("toolArgs", payload.get("tool_input", "")))
            kitlib.approval_pending(session, verdict.kind, digest)
            if modified is not None:  # 用完工具后看到的可能是改写后的参数，两种都记上
                kitlib.approval_pending(session, verdict.kind, kitlib.args_digest(modified))
            out = {"permissionDecision": "ask", "permissionDecisionReason": "ai-dev-kit：" + verdict.reason
                   + "（如果在自动驾驶模式下被自动拒绝：跳过这一步继续其余工作，把这条命令写进报告交给用户。）"}
        elif verdict.decision == "allow":
            out = {"permissionDecision": "allow", "permissionDecisionReason": "ai-dev-kit：" + verdict.reason}
        if modified is not None:
            out["modifiedArgs"] = modified
        return out
    except Exception as exc:  # 钩子崩溃会被当成拒绝，所以必须兜住
        kitlib.log_event("guard", {"decision": "error", "error": repr(exc)[:300]})
        if on_error == "deny":
            return {"permissionDecision": "deny",
                    "permissionDecisionReason": f"ai-dev-kit 守卫内部出错（{exc!r}），按配置拒绝。运行 kit_doctor.py 排查。"}
        return {}


# ---------------------------------------------------------------- 自测
# (标题, 工具调用, 期望, 位置)：位置 project = 临时目录登记成项目；other = 普通目录

SELFTEST_CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("读取 .env", {"toolName": "view", "toolArgs": {"path": "C:/repo/.env"}}, "deny", "other"),
    ("读取 .env.example", {"toolName": "view", "toolArgs": {"path": ".env.example"}}, "deny", "other"),
    ("读取普通文件", {"toolName": "view", "toolArgs": {"path": "src/app.py"}}, "none", "project"),
    ("命令打印 .env", {"toolName": "powershell", "toolArgs": {"command": "Get-Content .env"}}, "deny", "other"),
    ("Test-Path .env 放行", {"toolName": "powershell", "toolArgs": {"command": "Test-Path .env"}}, "none", "other"),
    ("git status 放行", {"toolName": "powershell", "toolArgs": {"command": "git status"}}, "none", "project"),
    ("git -C 路径 diff 放行", {"toolName": "powershell", "toolArgs": {"command": "git -C C:/x --no-pager diff --stat"}}, "none", "project"),
    ("项目里 git commit 拦截", {"toolName": "powershell", "toolArgs": {"command": "git commit -m x"}}, "deny", "project"),
    ("工作台 git commit 先问", {"toolName": "powershell", "toolArgs": {"command": "git commit -m x"}}, "ask", "other"),
    ("任何地方 git add . 拦截", {"toolName": "powershell", "toolArgs": {"command": "git add ."}}, "deny", "other"),
    ("git add 点名 工作台先问", {"toolName": "powershell", "toolArgs": {"command": "git add src/a.py"}}, "ask", "other"),
    ("项目里 git checkout 拦截", {"toolName": "bash", "toolArgs": {"command": "git checkout -- src/a.py"}}, "deny", "project"),
    ("git stash list 放行", {"toolName": "powershell", "toolArgs": {"command": "git stash list"}}, "none", "project"),
    ("项目里 Out-File 拦截", {"toolName": "powershell", "toolArgs": {"command": "Get-ChildItem | Out-File r.txt"}}, "deny", "project"),
    ("工作台 重定向 先问", {"toolName": "powershell", "toolArgs": {"command": "dir > r.txt"}}, "ask", "other"),
    ("项目里 uv add 拦截", {"toolName": "powershell", "toolArgs": {"command": "uv add requests"}}, "deny", "project"),
    ("工作台 pip install 先问", {"toolName": "powershell", "toolArgs": {"command": "python -m pip install requests"}}, "ask", "other"),
    ("项目里 ruff format 拦截", {"toolName": "powershell", "toolArgs": {"command": "uv run ruff format ."}}, "deny", "project"),
    ("ruff check 放行", {"toolName": "powershell", "toolArgs": {"command": "uv run ruff check ."}}, "none", "project"),
    ("删 build 目录（中间产物）放行", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item -Recurse -Force build"}}, "allow", "other"),
    ("删 __pycache__ 放行", {"toolName": "powershell", "toolArgs": {"command": "Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force"}}, "allow", "project"),
    ("删日志和 pyc 放行", {"toolName": "bash", "toolArgs": {"command": "rm -f debug.log src/a.pyc"}}, "allow", "project"),
    ("删源码目录 当场问", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item -Recurse -Force src/legacy"}}, "ask", "project"),
    ("删单个源码文件 当场问", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item src/old.py"}}, "ask", "project"),
    ("删 .git 拦截", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item -Recurse -Force .git"}}, "deny", "project"),
    ("删当前整个目录 拦截", {"toolName": "bash", "toolArgs": {"command": "rm -rf ./"}}, "deny", "other"),
    ("删缓存后接着跑别的 交给 Copilot", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item -Recurse .pytest_cache; git status"}}, "none", "project"),
    ("引号里的箭头不是重定向", {"toolName": "powershell", "toolArgs": {"command": "python C:/kit/tools/kit_run.py -- uv run python -c \"import sys; print('a -> b', len(sys.argv) > 0)\""}}, "none", "project"),
    ("项目里 改 pyproject 拦截", {"toolName": "edit", "toolArgs": {"path": "pyproject.toml", "new_str": "x"}}, "deny", "project"),
    ("项目里 写 type: ignore 拦截", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "x = 1  # type: ignore"}}, "deny", "project"),
    ("工作台 写 type: ignore 放行", {"toolName": "edit", "toolArgs": {"path": "a.py", "new_str": "x = 1  # type: ignore"}}, "none", "other"),
    ("照抄 import-untyped 放行", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "import x  # type: ignore[import-untyped]"}}, "none", "project"),
    ("写零宽字符 拦截", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "x\u200b = 1"}}, "deny", "other"),
    ("Markdown 里写 noqa 放行", {"toolName": "edit", "toolArgs": {"path": "docs/a.md", "new_str": "不要写 # noqa"}}, "none", "project"),
    ("工作台 新建自己的技能 放行", {"toolName": "create", "toolArgs": {"path": "my-skill/SKILL.md", "file_text": "---\nname: my-skill\n---"}}, "none", "other"),
    ("登记技能命令 放行", {"toolName": "powershell", "toolArgs": {"command": "copilot skill add C:/work/my-skill"}}, "none", "other"),
    ("Cypher DETACH DELETE 当场问", {"toolName": "powershell", "toolArgs": {"command": "cypher-shell \"MATCH (n:Doc) DETACH DELETE n\""}}, "ask", "other"),
    ("SQL DELETE FROM 当场问", {"toolName": "powershell", "toolArgs": {"command": "mysql -e \"DELETE FROM documents WHERE id=1\""}}, "ask", "other"),
    ("curl -X DELETE 当场问", {"toolName": "bash", "toolArgs": {"command": "curl -X DELETE http://localhost:8000/api/doc/1"}}, "ask", "other"),
    ("调用删除接口 当场问", {"toolName": "powershell", "toolArgs": {"command": "irm -Method Post http://localhost:8000/tap/ai/library/kb/documents/delete"}}, "ask", "other"),
    ("Cypher MERGE 写入 放行", {"toolName": "powershell", "toolArgs": {"command": "cypher-shell \"MERGE (n:Doc {id: 1})\""}}, "none", "other"),
    ("Cypher REMOVE 当场问", {"toolName": "powershell", "toolArgs": {"command": "cypher-shell \"MATCH (n:Doc) REMOVE n.tmp\""}}, "ask", "other"),
    ("搜索代码里的 DELETE 放行", {"toolName": "powershell", "toolArgs": {"command": "grep -rn \"DELETE FROM\" src"}}, "none", "project"),
    ("项目里 直接跑 pytest 自动套保护（不拦）", {"toolName": "powershell", "toolArgs": {"command": "uv run pytest tests/unit -q"}}, "none", "project"),
    ("项目里 经 kit_run 跑 pytest 放行", {"toolName": "powershell", "toolArgs": {"command": "python C:/kit/tools/kit_run.py -- uv run pytest tests/unit -q 2>&1 | Select-Object -Last 15"}}, "none", "project"),
    ("改禁删环境变量 拦截", {"toolName": "powershell", "toolArgs": {"command": "$env:AI_DEV_KIT_NODELETE='0'; uv run pytest"}}, "deny", "project"),
]


def _selftest_ask_flow() -> int:
    """2.1 默认流程：删数据当场问、自动加 --allow-delete；跑测试自动套保护；越界当场问。"""
    import tempfile

    sandbox = tempfile.mkdtemp(prefix="kit-guard-")
    runner = str(kitlib.KIT_ROOT / "tools" / "kit_run.py")
    guard = Guard({"guard": {}, "projects": [{"name": "selftest", "path": sandbox}]}, forced_mode="project")
    checks: list[tuple[str, bool]] = []
    v = guard.decide({"toolName": "powershell", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"command": "uv run pytest tests/unit -q 2>&1 | Select-Object -Last 15"}})
    new_cmd = str((guard.modified_args or {}).get("command", ""))
    checks.append(("跑 pytest：不拦，自动套上 kit_run.py", v.decision == "none" and "kit_run.py" in new_cmd
                   and new_cmd.endswith("| Select-Object -Last 15") and "--allow-delete" not in new_cmd))
    v = guard.decide({"toolName": "powershell", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"command": f"python \"{runner}\" -- uv run pytest tests/it -q", "description": "x"}})
    checks.append(("已经经过 kit_run.py：不改写", v.decision == "none" and guard.modified_args is None))
    v = guard.decide({"toolName": "powershell", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"command": f"python \"{runner}\" --allow-delete -- uv run pytest tests/it -q"}})
    checks.append(("带 --allow-delete 跑测试：当场问", v.decision == "ask" and v.kind.endswith("!")))
    v = guard.decide({"toolName": "powershell", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"command": "cypher-shell \"MATCH (n:TmpDoc) DETACH DELETE n\""}})
    checks.append(("Cypher 删除：当场问，确认框里有风险评估", v.decision == "ask" and "风险" in v.reason))
    script = Path(sandbox) / "cleanup.py"
    kitlib.write_text(script, "import requests\nrequests.delete('http://x/api/doc/1')\n")
    v = guard.decide({"toolName": "powershell", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"command": f"python {script}"}})
    new_cmd = str((guard.modified_args or {}).get("command", ""))
    checks.append(("会删数据的脚本：当场问，并自动加 --allow-delete", v.decision == "ask"
                   and "kit_run.py" in new_cmd and "--allow-delete" in new_cmd))
    kitlib.save_json(Path(sandbox) / ".ai-dev-kit" / "scope.json", {"files": ["src/a.py"]})
    v = guard.decide({"toolName": "edit", "sessionId": "ask-a", "cwd": sandbox,
                      "toolArgs": {"path": str(Path(sandbox) / "src" / "b.py"), "new_str": "x = 2"}})
    checks.append(("改方案外的文件：当场问（同一个文件只问一次）", v.decision == "ask" and v.kind == "out-of-scope:src/b.py"))
    failed = 0
    for title, ok in checks:
        failed += 0 if ok else 1
        print(f"[{'通过' if ok else '失败'}] 当场确认 · {title}")
    return failed


def _selftest_delete_flow() -> int:
    """旧版本退路（ask_mode=deny）：拦下 → 用户同意 → 同一条放行一次 → 再来要重新问；用户拒绝 → 一直拦。"""
    import tempfile

    sandbox = tempfile.mkdtemp(prefix="kit-guard-")
    guard = Guard({"guard": {"ask_mode": "deny"}, "projects": []}, forced_mode="workbench")
    cypher = {"toolName": "powershell", "sessionId": "selftest-a", "cwd": sandbox,
              "toolArgs": {"command": "cypher-shell \"MATCH (n:TmpDoc {run:'x'}) DETACH DELETE n\""}}
    runner = str(kitlib.KIT_ROOT / "tools" / "kit_run.py")
    script = {"toolName": "powershell", "sessionId": "selftest-b", "cwd": sandbox,
              "toolArgs": {"command": f"python \"{runner}\" --allow-delete -- uv run pytest tests/it -q"}}
    no_flag = {"toolName": "powershell", "sessionId": "selftest-b", "cwd": sandbox,
               "toolArgs": {"command": f"python \"{runner}\" -- uv run pytest tests/it -q"}}
    steps: list[tuple[str, Any, str]] = [
        ("删除命令第一次：拦下并给风险评估", lambda: guard.decide(dict(cypher)), "delete-needs-consent"),
        ("用户说别的话：还在等", lambda: kitlib.delete_consent("selftest-a", "这个库是哪个环境的？") or "waiting", "waiting"),
        ("等待中再试：继续拦", lambda: guard.decide(dict(cypher)), "delete-needs-consent"),
        ("用户回复同意", lambda: kitlib.delete_consent("selftest-a", "同意，删吧"), "approved"),
        ("同一条命令：放行一次", lambda: guard.decide(dict(cypher)), "delete-approved"),
        ("再来一次：要重新问", lambda: guard.decide(dict(cypher)), "delete-needs-consent"),
        ("用户回复不要", lambda: kitlib.delete_consent("selftest-a", "不要删"), "rejected"),
        ("拒绝后再试：拦下", lambda: guard.decide(dict(cypher)), "delete-rejected"),
        ("--allow-delete 跑测试：先拦下", lambda: guard.decide(dict(script)), "delete-needs-consent"),
        ("用户同意", lambda: kitlib.delete_consent("selftest-b", "可以"), "approved"),
        ("同意了但没加 --allow-delete：提示加上", lambda: guard.decide(dict(no_flag)), "delete-needs-flag"),
        ("加上 --allow-delete：放行", lambda: guard.decide(dict(script)), "delete-approved"),
    ]
    failed = 0
    for title, fn, expected in steps:
        got = fn()
        actual = got.rule if isinstance(got, Verdict) else str(got)
        ok = actual == expected
        failed += 0 if ok else 1
        print(f"[{'通过' if ok else '失败'}] 删除流程 · {title}：期望 {expected}，实际 {actual}")
    return failed


def selftest() -> int:
    kitlib.setup_console()
    import tempfile

    # 自测产生的“待同意删除”记录写到临时文件，不留在你的数据目录里
    kitlib.DELETE_REQ_PATH = Path(tempfile.mkdtemp(prefix="kit-guard-")) / "delete_requests.json"
    failed = 0
    for title, payload, expected, where in SELFTEST_CASES:
        sandbox = tempfile.mkdtemp(prefix="kit-guard-")  # 空目录，不受真实修改范围影响
        projects = [{"name": "selftest", "path": sandbox}] if where == "project" else []
        guard = Guard({"guard": {}, "projects": projects}, forced_mode="project" if where == "project" else "workbench")
        payload = dict(payload)
        payload["cwd"] = sandbox
        v = guard.decide(payload)
        ok = v.decision == expected
        failed += 0 if ok else 1
        mark = "通过" if ok else "失败"
        print(f"[{mark}] {title}：期望 {expected}，实际 {v.decision}{'（' + v.reason + '）' if v.reason and not ok else ''}")
    print(f"守卫自测：{len(SELFTEST_CASES) - failed}/{len(SELFTEST_CASES)} 通过。")
    flow_failed = _selftest_delete_flow() + _selftest_ask_flow()
    return 1 if failed or flow_failed else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace") if not sys.stdin.isatty() else ""
    result = handle(raw)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
