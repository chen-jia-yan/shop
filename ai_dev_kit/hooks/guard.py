"""preToolUse 守卫钩子：在 Copilot 调用工具之前检查，违规就直接拒绝。

为什么要它：写在提示词里的"绝对禁止"，模型不一定遵守（GitHub 官方文档原话：
指令不能保证每条都被遵守）；钩子运行的是代码，可以真正拦下来。

Copilot CLI 会把一个 JSON 通过标准输入传进来（camelCase 格式）：
    {"toolName": "powershell", "toolArgs": {...}, "cwd": "...", ...}
本脚本向标准输出写恰好一个 JSON 对象：
    {"permissionDecision": "deny", "permissionDecisionReason": "..."}
    或 {} 表示不干预，交给 Copilot 正常的权限流程。

注意（来自官方文档）：
- 本脚本崩溃或非 0 退出会被当成"拒绝"（fail-closed），所以内部异常一律捕获；
  捕获后怎么处理由 kit.config.json 的 guard.on_error 决定（默认 allow，避免把会话锁死）。
- 超时（默认 5 秒）会被当成"放行"，所以这里只做纯文本判断，不调用外部命令。

本地自测：python guard.py --selftest
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kitlib  # 必须在上一行把 tools 目录加进 sys.path 之后再导入

# ---------------------------------------------------------------- 默认规则
# 可以在 kit.config.json 的 "guard" 段覆盖或追加，见 docs/03-钩子与拦截规则.md

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
GIT_CONDITIONAL = {"branch", "stash", "remote", "config", "tag", "worktree", "submodule"}

SHELL_TOOLS = {"bash", "powershell", "shell", "execute", "run_in_terminal", "terminal"}
READ_TOOLS = {"view", "read", "read_file", "cat", "open"}
WRITE_TOOLS = {"edit", "create", "write", "str_replace_editor", "apply_patch", "str_replace",
               "insert", "write_file", "multi_edit"}

PATH_KEYS = re.compile(r"(?i)^(path|file|file_?path|filename|target|uri|absolute_?path)$")
CONTENT_KEYS = re.compile(r"(?i)(new_?str|file_?text|content|text|new_?string|new_?content|input|patch|code|insert_?text)")
COMMAND_KEYS = re.compile(r"(?i)^(command|cmd|script|commands)$")

REDIRECT = re.compile(r"(?<![0-9&>])>{1,2}(?!&)\s*(?!\$null\b|null\b|nul\b)[^\s|&;]")
WRITE_CMDLETS = re.compile(
    r"(?i)\b(out-file|set-content|add-content|tee-object|tee)\b|\[(system\.)?io\.file\]::(write|append)"
)
PKG_INSTALL = re.compile(
    r"(?i)\b(pip3?|python\s+-m\s+pip)\s+(install|uninstall)\b|\buv\s+(add|remove|sync|lock)\b|"
    r"\buv\s+pip\s+(install|uninstall|sync)\b|\b(npm|pnpm|yarn)\s+(i|install|add|remove|uninstall)\b|"
    r"\bpoetry\s+(add|remove|install|lock)\b|\bconda\s+(install|remove)\b"
)
DANGEROUS_DELETE = re.compile(
    r"(?i)\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r|\bremove-item\b[^|;]*-recurse|"
    r"\b(rd|rmdir)\s+/s\b|\bdel\s+/s\b|\bformat\s+[a-z]:"
)
RUFF_FORMAT = re.compile(r"(?i)\bruff\s+format\b")
READ_ALLOWED_CMDS = re.compile(r"(?i)^\s*test-path\b")

PY_FORBIDDEN_MARKERS = [
    (re.compile(r"#\s*type:\s*ignore(?!\[import-untyped\])"), "新增了 `# type: ignore`（只允许照抄已有的 `# type: ignore[import-untyped]`）"),
    (re.compile(r"#\s*noqa\b"), "新增了 `# noqa`"),
    (re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b|\bpytest\.(skip|xfail)\("), "新增了跳过或预期失败的测试标记"),
    (re.compile(r"\bcast\(\s*Any\s*,"), "新增了 `cast(Any, ...)`"),
]
INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


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
    """按 ; && || | 和换行拆成多段，逐段判断。"""
    parts = re.split(r"\|\||&&|;|\r?\n|\|", command)
    return [p.strip() for p in parts if p.strip()]


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
        if t.startswith("--") or t.startswith("-"):
            i += 1
            continue
        return t.lower(), [x.lower() for x in tokens[i + 1:]]
    return "", []


def _git_verdict(sub: str, rest: list[str]) -> str | None:
    """返回拒绝原因；只读命令返回 None。"""
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


# ---------------------------------------------------------------- 主判断


class Guard:
    def __init__(self, cfg: dict[str, Any]):
        g = cfg.get("guard", {}) or {}
        self.cfg = cfg
        self.enabled = g.get("enabled", True)
        self.protected = list(g.get("protected_files", DEFAULT_PROTECTED_FILES)) + list(g.get("extra_protected_files", []))
        self.protected_allow = list(g.get("protected_allow", DEFAULT_PROTECTED_ALLOW))
        self.locked = list(g.get("locked_files", DEFAULT_LOCKED_FILES))
        self.block_git_write = g.get("block_git_write", True)
        self.block_file_write_cmds = g.get("block_shell_file_write", True)
        self.block_pkg = g.get("block_package_install", True)
        self.block_delete = g.get("block_dangerous_delete", True)
        self.block_ruff_format = g.get("block_ruff_format", True)
        self.check_python_markers = g.get("check_python_markers", True)
        self.enforce_scope = g.get("enforce_scope", True)
        self.extra_deny = [re.compile(p) for p in g.get("extra_deny_command_patterns", [])]

    # -- 文件类

    def _is_protected(self, path: str) -> bool:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if kitlib.match_any(name, self.protected_allow):
            return False
        return kitlib.match_any(name, self.protected) or kitlib.match_any(path, self.protected)

    def check_read(self, paths: list[str]) -> str | None:
        for p in paths:
            if self._is_protected(p):
                return f"[protected-file] 禁止读取可能含密钥的文件：{p}。需要里面的配置项名字时，请让用户告诉你，不要打开文件。"
        return None

    def check_write(self, paths: list[str], contents: list[str], cwd: str) -> str | None:
        project = kitlib.find_project(self.cfg, cwd)
        for p in paths:
            if self._is_protected(p):
                return f"[protected-file] 禁止修改可能含密钥的文件：{p}"
            abs_p = p if os.path.isabs(p) else os.path.join(cwd, p)
            scope_root, scope = kitlib.find_scope(os.path.dirname(abs_p) or cwd)
            rel = kitlib.rel_posix(abs_p, scope_root) if scope_root else p.replace("\\", "/")
            scope_allows = bool(scope) and kitlib.match_any(rel, list(scope.get("files", [])) + list(scope.get("globs", [])))
            if kitlib.match_any(rel, self.locked) and not (scope_allows and scope.get("allow_locked")):
                return f"[locked-file] 禁止修改依赖和锁定文件：{rel}。新增或升级依赖必须由用户决定。"
            if project:
                proj_rel = kitlib.rel_posix(abs_p, project.get("path", cwd))
                protected_areas = list(project.get("protected", []))
                area_allow = list(project.get("protected_allow", []))
                if (protected_areas and kitlib.match_any(proj_rel, protected_areas)
                        and not kitlib.match_any(proj_rel, area_allow) and not scope_allows):
                    return (f"[protected-area] {proj_rel} 属于受保护区域（{', '.join(protected_areas)}），"
                            "通常是同事负责的模块。确需修改，请先停下来说明原因，由用户把它加进本次修改范围。")
            if self.enforce_scope and scope and scope.get("files") is not None and not scope_allows:
                allowed = list(scope.get("files", [])) + list(scope.get("globs", []))
                preview = "、".join(allowed[:8]) + ("……" if len(allowed) > 8 else "")
                return (f"[out-of-scope] {rel} 不在本次允许修改的文件名单里。允许的文件：{preview or '（空）'}。"
                        "如确需修改，请停下来说明原因，由用户运行 scope.py add 加进名单。")
        kit_root = kitlib.norm(kitlib.KIT_ROOT)
        project_py = [
            p for p in paths
            if p.lower().endswith((".py", ".pyi"))
            and not kitlib.norm(p if os.path.isabs(p) else os.path.join(cwd, p)).startswith(kit_root)
        ]
        if self.check_python_markers and project_py:  # 工具包自身的文件不受这条限制
            for text in contents:
                for pattern, reason in PY_FORBIDDEN_MARKERS:
                    if pattern.search(text):
                        return f"[forbidden-marker] {reason}。请从根本上修复问题，而不是屏蔽检查。"
        for text in contents:
            m = INVISIBLE.search(text)
            if m:
                return f"[invisible-char] 写入内容里含隐形字符 U+{ord(m.group(0)):04X}，请删除后重试。"
            if any(p.lower().endswith((".py", ".pyi")) for p in paths) and "\u3000" in text:
                return "[fullwidth-space] Python 代码里含全角空格 U+3000，请改成普通空格。"
        return None

    # -- 命令类

    def check_command(self, command: str) -> str | None:
        for pattern in self.extra_deny:
            if pattern.search(command):
                return f"[custom-deny] 命令命中自定义禁止规则：{pattern.pattern}"
        for seg in _split_shell(command):
            if READ_ALLOWED_CMDS.search(seg):
                continue
            for token in re.findall(r"[^\s'\"=<>|;,()]+", seg):
                cleaned = token.strip("'\"`")
                if cleaned and self._is_protected(cleaned):
                    return f"[protected-file] 命令涉及可能含密钥的文件：{cleaned}。请不要读取或打印它。"
            if self.block_git_write:
                parsed = _git_subcommand(seg)
                if parsed is not None:
                    reason = _git_verdict(*parsed)
                    if reason:
                        return (f"[git-write] {reason}。本工具包规定 git 写操作一律由用户执行；"
                                "你可以把要执行的命令写在报告里，交给用户。")
            if self.block_pkg and PKG_INSTALL.search(seg):
                return "[package-install] 禁止安装、卸载或同步依赖包。缺依赖时请在报告里说明，由用户决定。"
            if self.block_delete and DANGEROUS_DELETE.search(seg):
                return "[dangerous-delete] 禁止递归删除命令。"
            if self.block_ruff_format and RUFF_FORMAT.search(seg):
                return "[ruff-format] 禁止对已有文件运行 ruff format（会产生大量无关改动）。只用 ruff check。"
            if self.block_file_write_cmds:
                if WRITE_CMDLETS.search(seg):
                    return ("[shell-write] 禁止用 Out-File / Set-Content / Add-Content / Tee 写文件"
                            "（Windows PowerShell 5 默认写成 UTF-16）。请用编辑工具修改文件。")
                if REDIRECT.search(seg):
                    return ("[shell-redirect] 禁止用 > 或 >> 把输出写进文件（会产生 UTF-16 文件）。"
                            "需要看输出就直接显示，需要改文件请用编辑工具。")
        return None

    # -- 入口

    def decide(self, payload: dict[str, Any]) -> tuple[str, str, str]:
        """返回 (decision, reason, rule)。decision 为 allow / deny / none。"""
        if not self.enabled:
            return "none", "", ""
        tool = str(payload.get("toolName") or payload.get("tool_name") or "").lower()
        args = payload.get("toolArgs", payload.get("tool_input", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {"input": args}
        cwd = str(payload.get("cwd") or os.getcwd())
        strings = _collect(args)
        paths = [v for k, v in strings if PATH_KEYS.match(k)]
        commands = [v for k, v in strings if COMMAND_KEYS.match(k)]
        contents = [v for k, v in strings if CONTENT_KEYS.search(k) and not PATH_KEYS.match(k)]
        for text in contents:
            if "*** " in text or text.startswith(("--- ", "diff --git")):
                paths.extend(_paths_from_patch(text))

        reason: str | None = None
        if tool in SHELL_TOOLS or commands:
            for cmd in commands or [v for _, v in strings]:
                reason = self.check_command(cmd)
                if reason:
                    break
        if not reason and tool in READ_TOOLS:
            reason = self.check_read(paths)
        if not reason and (tool in WRITE_TOOLS or (paths and contents and tool not in READ_TOOLS)):
            reason = self.check_write(paths, contents, cwd)
        if not reason and tool in {"grep", "rg", "glob"}:
            reason = self.check_read(paths)
        if reason:
            rule = reason[1:reason.index("]")] if reason.startswith("[") and "]" in reason else "deny"
            return "deny", reason, rule
        return "none", "", ""


def handle(raw: str) -> dict[str, Any]:
    cfg = kitlib.load_config()
    on_error = (cfg.get("guard", {}) or {}).get("on_error", "allow")
    try:
        payload = json.loads(raw) if raw.strip() else {}
        decision, reason, rule = Guard(cfg).decide(payload)
        kitlib.log_event("guard", {
            "tool": payload.get("toolName") or payload.get("tool_name"),
            "decision": decision, "rule": rule,
            "args": kitlib.redact(json.dumps(payload.get("toolArgs", payload.get("tool_input", "")), ensure_ascii=False), 300),
            "cwd": payload.get("cwd"),
        })
        if decision == "deny":
            return {"permissionDecision": "deny", "permissionDecisionReason": "ai-dev-kit 守卫：" + reason}
        return {}
    except Exception as exc:  # 钩子崩溃会被当成拒绝，所以必须兜住
        kitlib.log_event("guard", {"decision": "error", "error": repr(exc)[:300]})
        if on_error == "deny":
            return {"permissionDecision": "deny",
                    "permissionDecisionReason": f"ai-dev-kit 守卫内部出错（{exc!r}），按配置拒绝。运行 kit_doctor.py 排查。"}
        return {}


# ---------------------------------------------------------------- 自测

SELFTEST_CASES: list[tuple[str, dict[str, Any], str]] = [
    ("读取 .env", {"toolName": "view", "toolArgs": {"path": "C:/repo/.env"}}, "deny"),
    ("读取 .env.example", {"toolName": "view", "toolArgs": {"path": ".env.example"}}, "deny"),
    ("读取普通文件", {"toolName": "view", "toolArgs": {"path": "src/app.py"}}, "none"),
    ("命令打印 .env", {"toolName": "powershell", "toolArgs": {"command": "Get-Content .env"}}, "deny"),
    ("Test-Path .env 放行", {"toolName": "powershell", "toolArgs": {"command": "Test-Path .env"}}, "none"),
    ("git status 放行", {"toolName": "powershell", "toolArgs": {"command": "git status"}}, "none"),
    ("git -C 路径 diff 放行", {"toolName": "powershell", "toolArgs": {"command": "git -C C:/x --no-pager diff --stat"}}, "none"),
    ("git commit 拒绝", {"toolName": "powershell", "toolArgs": {"command": "git add . ; git commit -m x"}}, "deny"),
    ("git checkout 拒绝", {"toolName": "bash", "toolArgs": {"command": "git checkout -- src/a.py"}}, "deny"),
    ("git stash list 放行", {"toolName": "powershell", "toolArgs": {"command": "git stash list"}}, "none"),
    ("git branch --show-current 放行", {"toolName": "powershell", "toolArgs": {"command": "git branch --show-current"}}, "none"),
    ("git branch 新建 拒绝", {"toolName": "powershell", "toolArgs": {"command": "git branch feature/x"}}, "deny"),
    ("Out-File 拒绝", {"toolName": "powershell", "toolArgs": {"command": "uv run pytest | Out-File r.txt"}}, "deny"),
    ("重定向 拒绝", {"toolName": "powershell", "toolArgs": {"command": "uv run pytest > r.txt"}}, "deny"),
    ("2>&1 放行", {"toolName": "powershell", "toolArgs": {"command": "uv run pytest -q 2>&1 | Select-Object -Last 15"}}, "none"),
    ("pip install 拒绝", {"toolName": "powershell", "toolArgs": {"command": "uv pip install requests"}}, "deny"),
    ("uv sync 拒绝", {"toolName": "powershell", "toolArgs": {"command": "uv sync"}}, "deny"),
    ("ruff format 拒绝", {"toolName": "powershell", "toolArgs": {"command": "uv run ruff format ."}}, "deny"),
    ("ruff check 放行", {"toolName": "powershell", "toolArgs": {"command": "uv run ruff check ."}}, "none"),
    ("递归删除 拒绝", {"toolName": "powershell", "toolArgs": {"command": "Remove-Item -Recurse -Force build"}}, "deny"),
    ("改 pyproject 拒绝", {"toolName": "edit", "toolArgs": {"path": "pyproject.toml", "new_str": "x"}}, "deny"),
    ("写 type: ignore 拒绝", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "x = 1  # type: ignore"}}, "deny"),
    ("照抄 import-untyped 放行", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "import x  # type: ignore[import-untyped]"}}, "none"),
    ("写 noqa 拒绝", {"toolName": "create", "toolArgs": {"path": "src/b.py", "file_text": "import os  # noqa"}}, "deny"),
    ("写 skip 拒绝", {"toolName": "edit", "toolArgs": {"path": "tests/test_a.py", "new_str": "@pytest.mark.skip\ndef test_x(): ..."}}, "deny"),
    ("写零宽字符 拒绝", {"toolName": "edit", "toolArgs": {"path": "src/a.py", "new_str": "x\u200b = 1"}}, "deny"),
    ("Markdown 里写 noqa 放行", {"toolName": "edit", "toolArgs": {"path": "docs/a.md", "new_str": "不要写 # noqa"}}, "none"),
]


def selftest() -> int:
    kitlib.setup_console()
    import tempfile

    guard = Guard({"guard": {}, "projects": []})
    sandbox = tempfile.mkdtemp(prefix="kit-guard-")  # 空目录，不受真实修改范围影响
    failed = 0
    for title, payload, expected in SELFTEST_CASES:
        payload = dict(payload)
        payload["cwd"] = sandbox
        decision, reason, _ = guard.decide(payload)
        ok = decision == expected
        failed += 0 if ok else 1
        mark = "通过" if ok else "失败"
        print(f"[{mark}] {title}：期望 {expected}，实际 {decision}{'（' + reason + '）' if reason and not ok else ''}")
    print(f"守卫自测：{len(SELFTEST_CASES) - failed}/{len(SELFTEST_CASES)} 通过。")
    return 1 if failed else 0


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
