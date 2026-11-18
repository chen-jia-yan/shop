"""静态检查库：把本项目踩过的坑写成可以自动跑的检查（只读，不改任何文件）。

每个检查对应一类真实事故（见 evals/cases 和 docs/09-事故与防线.md）：
    chars              编码、隐形字符、UTF-16（.env.example 变成 UTF-16、终端乱码）
    nested_orm_class   ORM 类被缩进成嵌套类（models.py 5 个类缩进进 TokenUsage）
    removed_names      顶层类或函数被删掉或悄悄改名（LibraryChunkDraft → ChunkDraft）
    isolated_imports   每个模块单独导入，发现循环导入（kg_schema ↔ sinks）
    env_in_tests       测试读取真实 .env
    getattr_settings   新代码用 getattr(settings, "x", 默认值) 绕开配置校验
    forbidden_markers  新代码里出现 type: ignore / noqa / skip / xfail / cast(Any
    tautological_asserts 测试拿同一个东西和自己比较（永远相等的无效测试）
    test_collection    测试收集阶段报错，或者一个测试都没收集到（"0 tests ran"）
    scope_diff         改动的文件超出本次允许修改的名单
    submodule_dirty    子模块（gitlink）有未提交改动，提交时容易被一起带进去

用法：
    python checks.py --project tap-ai-backend
    python checks.py --project tap-ai-backend --only chars,isolated_imports
    python checks.py --list
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import check_chars
import kitlib


@dataclass
class Result:
    name: str
    ok: bool
    summary: str
    findings: list[str] = field(default_factory=list)
    severity: str = "error"  # error：必须处理；warning：需要人看一眼
    skipped: bool = False


@dataclass
class Ctx:
    project: dict[str, Any]
    root: Path
    git_root: Path
    ref: str
    cfg: dict[str, Any]

    def py_cmd(self) -> list[str]:
        cmd = self.project.get("python_cmd") or ["{python}"]
        return kitlib.expand_cmd(list(cmd), kitlib.base_ctx(self.cfg, self.project))


# ---------------------------------------------------------------- 公共帮助函数


def changed_files(ctx: Ctx, suffix: str = "") -> list[Path]:
    """相对 ref 有改动的文件 + 未跟踪的新文件（只看项目目录内）。"""
    files: set[str] = set()
    code, out = kitlib.git(["diff", "--name-only", ctx.ref, "--", "."], ctx.root)
    if code == 0:
        files.update(x.strip() for x in out.splitlines() if x.strip())
    code, out = kitlib.git(["ls-files", "--others", "--exclude-standard", "--", "."], ctx.root)
    if code == 0:
        files.update(x.strip() for x in out.splitlines() if x.strip())
    result: list[Path] = []
    for rel in sorted(files):
        p = (ctx.git_root / rel) if not (ctx.root / rel).exists() else (ctx.root / rel)
        if p.is_file() and (not suffix or p.suffix == suffix):
            result.append(p)
    return result


def added_lines(ctx: Ctx, suffix: str = ".py") -> list[tuple[str, int, str]]:
    """新增的代码行 (文件, 行号, 内容)。只检查新代码，不追究历史代码。"""
    out_lines: list[tuple[str, int, str]] = []
    code, diff = kitlib.git(["diff", "-U0", ctx.ref, "--", "."], ctx.root)
    if code == 0:
        current, line_no = "", 0
        for line in diff.splitlines():
            if line.startswith("+++ "):
                path = line[4:].strip()
                current = path[2:] if path.startswith("b/") else path
                continue
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                line_no = int(m.group(1))
                continue
            if line.startswith("+") and not line.startswith("+++"):
                if current.endswith(suffix):
                    out_lines.append((current, line_no, line[1:]))
                line_no += 1
    code, out = kitlib.git(["ls-files", "--others", "--exclude-standard", "--", "."], ctx.root)
    if code == 0:
        for rel in out.splitlines():
            rel = rel.strip()
            p = ctx.root / rel
            if rel.endswith(suffix) and p.is_file():
                for i, text in enumerate(kitlib.read_text(p).splitlines(), start=1):
                    out_lines.append((rel, i, text))
    return out_lines


def py_files(ctx: Ctx, dirs: list[str]) -> list[Path]:
    found: list[Path] = []
    for d in dirs:
        base = ctx.root / d
        if base.is_dir():
            found.extend(p for p in base.rglob("*.py") if ".venv" not in p.parts)
    return sorted(found)


def parse_py(path: Path) -> ast.AST | None:
    try:
        return ast.parse(kitlib.read_text(path), filename=str(path))
    except SyntaxError:
        return None


# ---------------------------------------------------------------- 各项检查


def check_chars_(ctx: Ctx) -> Result:
    dirs = ctx.project.get("source_dirs", ["src", "tests"])
    files = check_chars.iter_files([str(ctx.root / d) for d in dirs], set(check_chars.DEFAULT_EXTS))
    issues = [i for f in files for i in check_chars.check_file(f) if i.severity == "error"]
    findings = [f"{kitlib.rel_posix(i.path, ctx.root)}:{i.line} {i.message}" for i in issues[:50]]
    return Result("chars", not issues, f"扫描 {len(files)} 个文件，编码问题 {len(issues)} 处", findings)


def check_nested_orm(ctx: Ctx) -> Result:
    findings: list[str] = []
    for path in py_files(ctx, ctx.project.get("source_dirs", ["src"])):
        tree = parse_py(path)
        if tree is None:
            continue
        for outer in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for inner in outer.body:
                if not isinstance(inner, ast.ClassDef):
                    continue
                bases = [ast.unparse(b) for b in inner.bases]
                has_table = any(
                    isinstance(st, (ast.Assign, ast.AnnAssign))
                    and "__tablename__" in ast.unparse(st)
                    for st in inner.body
                )
                if has_table or any(re.search(r"(Base|Model|DeclarativeBase)$", b) for b in bases):
                    findings.append(f"{kitlib.rel_posix(path, ctx.root)}:{inner.lineno} "
                                    f"ORM 类 {inner.name} 嵌套在 {outer.name} 里面（多半是缩进错了）")
    return Result("nested_orm_class", not findings, f"发现 {len(findings)} 个嵌套的 ORM 类", findings)


def _top_names(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}


def check_removed_names(ctx: Ctx) -> Result:
    findings: list[str] = []
    for path in changed_files(ctx, ".py"):
        rel_git = kitlib.rel_posix(path, ctx.git_root)
        code, old_src = kitlib.git(["show", f"{ctx.ref}:{rel_git}"], ctx.git_root)
        if code != 0:
            continue  # 新文件
        old, new = _top_names(old_src), _top_names(kitlib.read_text(path))
        removed, added = sorted(old - new), sorted(new - old)
        if removed:
            hint = f"；同时新增了 {', '.join(added)}，可能是改名" if added else ""
            findings.append(f"{kitlib.rel_posix(path, ctx.root)} 删除了顶层名字：{', '.join(removed)}{hint}")
    return Result("removed_names", not findings,
                  f"{len(findings)} 个文件删除或改名了顶层类/函数（相对 {ctx.ref}）", findings, "warning")


def check_isolated_imports(ctx: Ctx) -> Result:
    modules = list(ctx.project.get("isolated_import_modules", []))
    if not modules:
        return Result("isolated_imports", True, "未配置 isolated_import_modules，跳过", skipped=True)
    findings: list[str] = []
    for mod in modules:
        cmd = ctx.py_cmd() + ["-c", f"import {mod}"]
        code, out = kitlib.run(cmd, cwd=ctx.root, timeout=180)
        if code != 0:
            last = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or ["（无输出）"]
            findings.append(f"单独导入 {mod} 失败：{last[0][:200]}")
    return Result("isolated_imports", not findings, f"单独导入 {len(modules)} 个模块，失败 {len(findings)} 个", findings)


ENV_PATTERNS = [
    (re.compile(r"\bload_dotenv\s*\("), "调用了 load_dotenv()"),
    (re.compile(r"""env_file\s*=\s*["']\.env["']"""), "env_file 指向真实 .env"),
    (re.compile(r"""open\(\s*["'][^"']*\.env["']"""), "直接打开 .env"),
    (re.compile(r"\bdotenv_values\s*\("), "读取 dotenv_values()"),
]


def check_env_in_tests(ctx: Ctx) -> Result:
    findings: list[str] = []
    for path in py_files(ctx, ctx.project.get("test_dirs", ["tests"])):
        for i, line in enumerate(kitlib.read_text(path).splitlines(), start=1):
            for pattern, label in ENV_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{kitlib.rel_posix(path, ctx.root)}:{i} 测试里{label}")
    return Result("env_in_tests", not findings, f"测试读取真实环境文件 {len(findings)} 处", findings)


GETATTR_SETTINGS = re.compile(r"""getattr\(\s*\w*settings\w*\s*,\s*["']""")


def check_getattr_settings(ctx: Ctx) -> Result:
    findings = [f"{f}:{n} {t.strip()[:120]}" for f, n, t in added_lines(ctx) if GETATTR_SETTINGS.search(t)]
    return Result("getattr_settings", not findings,
                  f"新代码里 getattr(settings, ...) {len(findings)} 处（应直接访问 settings.字段）", findings)


MARKERS = [
    (re.compile(r"#\s*type:\s*ignore(?!\[import-untyped\])"), "type: ignore"),
    (re.compile(r"#\s*noqa\b"), "noqa"),
    (re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b|\bpytest\.(skip|xfail)\("), "skip/xfail"),
    (re.compile(r"\bcast\(\s*Any\s*,"), "cast(Any, ...)"),
]


def check_forbidden_markers(ctx: Ctx) -> Result:
    findings: list[str] = []
    for f, n, t in added_lines(ctx):
        for pattern, label in MARKERS:
            if pattern.search(t):
                findings.append(f"{f}:{n} 新增 {label}：{t.strip()[:120]}")
    return Result("forbidden_markers", not findings, f"新代码里屏蔽检查的标记 {len(findings)} 处", findings)


def check_tautological(ctx: Ctx) -> Result:
    findings: list[str] = []
    for path in py_files(ctx, ctx.project.get("test_dirs", ["tests"])):
        tree = parse_py(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
                cmp = node.test
                if len(cmp.ops) == 1 and isinstance(cmp.ops[0], (ast.Eq, ast.Is)):
                    if ast.dump(cmp.left) == ast.dump(cmp.comparators[0]):
                        findings.append(f"{kitlib.rel_posix(path, ctx.root)}:{node.lineno} "
                                        f"断言两边完全相同：{ast.unparse(cmp)[:100]}")
    return Result("tautological_asserts", not findings, f"永远成立的断言 {len(findings)} 处", findings, "warning")


def check_test_collection(ctx: Ctx) -> Result:
    cmd = ctx.project.get("checks", {}).get("collect")
    cmd = kitlib.expand_cmd(cmd, kitlib.base_ctx(ctx.cfg, ctx.project)) if cmd else ctx.py_cmd() + ["-m", "pytest", "--collect-only", "-q"]
    code, out = kitlib.run(cmd, cwd=ctx.root, timeout=300)
    collected = re.search(r"(\d+)\s+tests?\s+collected", out) or re.search(r"(\d+)\s+tests?\b", out.strip().splitlines()[-1] if out.strip() else "")
    errors = re.search(r"(\d+)\s+errors?", out)
    n = int(collected.group(1)) if collected else 0
    findings: list[str] = []
    if errors and int(errors.group(1)) > 0:
        findings.extend(ln.strip() for ln in out.splitlines() if ln.startswith("ERROR"))
        findings.insert(0, f"收集阶段有 {errors.group(1)} 个错误：这些测试一个都没真正运行")
    if n == 0:
        findings.append("一个测试都没收集到（检查工作目录、测试路径、依赖是否缺失）")
    if code not in (0, 5) and not findings:
        findings.append(f"pytest 退出码 {code}：{out.strip().splitlines()[-1] if out.strip() else ''}")
    return Result("test_collection", not findings, f"收集到 {n} 个测试", findings[:30])


def check_scope_diff(ctx: Ctx) -> Result:
    scope_root, scope = kitlib.find_scope(ctx.root)
    if not scope:
        return Result("scope_diff", True, "没有设置本次修改范围（scope.json），跳过", skipped=True)
    allowed = list(scope.get("files", [])) + list(scope.get("globs", []))
    findings: list[str] = []
    for path in changed_files(ctx):
        rel = kitlib.rel_posix(path, scope_root or ctx.root)
        if rel.startswith(".ai-dev-kit/"):
            continue
        if not kitlib.match_any(rel, allowed):
            findings.append(f"{rel} 不在允许修改名单里")
    return Result("scope_diff", not findings, f"超出修改范围的文件 {len(findings)} 个", findings)


def check_submodule_dirty(ctx: Ctx) -> Result:
    code, ls = kitlib.git(["ls-files", "-s"], ctx.git_root)
    if code != 0:
        return Result("submodule_dirty", True, "不是 git 仓库，跳过", skipped=True)
    gitlinks = {line.split("\t", 1)[1] for line in ls.splitlines() if line.startswith("160000") and "\t" in line}
    if not gitlinks:
        return Result("submodule_dirty", True, "没有子模块")
    code, status = kitlib.git(["status", "--porcelain"], ctx.git_root)
    findings = [f"子模块 {line[3:].strip()} 有改动（{line[:2].strip()}）：提交时只点名添加自己的文件，不要 git add ."
                for line in status.splitlines() if line[3:].strip() in gitlinks]
    return Result("submodule_dirty", not findings, f"有改动的子模块 {len(findings)} 个", findings, "warning")


CHECKS: dict[str, Callable[[Ctx], Result]] = {
    "chars": check_chars_,
    "nested_orm_class": check_nested_orm,
    "removed_names": check_removed_names,
    "isolated_imports": check_isolated_imports,
    "env_in_tests": check_env_in_tests,
    "getattr_settings": check_getattr_settings,
    "forbidden_markers": check_forbidden_markers,
    "tautological_asserts": check_tautological,
    "test_collection": check_test_collection,
    "scope_diff": check_scope_diff,
    "submodule_dirty": check_submodule_dirty,
}
FAST_CHECKS = ["chars", "nested_orm_class", "removed_names", "env_in_tests", "getattr_settings",
               "forbidden_markers", "tautological_asserts", "scope_diff", "submodule_dirty"]


def make_ctx(project_name: str, ref: str = "HEAD") -> Ctx:
    cfg = kitlib.load_config()
    project = kitlib.get_project(cfg, project_name)
    if not project:
        raise SystemExit(f"kit.config.json 里没有登记项目：{project_name}")
    root = Path(project["path"])
    git_root = Path(project.get("git_root") or project["path"])
    return Ctx(project, root, git_root, ref, cfg)


def run_checks(ctx: Ctx, names: list[str]) -> list[Result]:
    results: list[Result] = []
    for name in names:
        fn = CHECKS.get(name)
        if fn is None:
            results.append(Result(name, False, "没有这个检查项"))
            continue
        try:
            results.append(fn(ctx))
        except Exception as exc:  # 单个检查出错不影响其他检查
            results.append(Result(name, False, f"检查本身出错：{exc!r}"))
    return results


def format_results(results: list[Result]) -> str:
    lines = []
    for r in results:
        mark = "跳过" if r.skipped else ("通过" if r.ok else ("失败" if r.severity == "error" else "提醒"))
        lines.append(f"[{mark}] {r.name}：{r.summary}")
        for f in r.findings[:20]:
            lines.append(f"    - {f}")
        if len(r.findings) > 20:
            lines.append(f"    ……另有 {len(r.findings) - 20} 条")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="ai-dev-kit 静态检查（只读）")
    parser.add_argument("--project", help="kit.config.json 里的项目名")
    parser.add_argument("--only", help="逗号分隔的检查项")
    parser.add_argument("--ref", default="HEAD", help="对比的基准提交，默认 HEAD")
    parser.add_argument("--all", action="store_true", help="包括较慢的检查（导入、测试收集）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        for name in CHECKS:
            print(f"{name}{'' if name in FAST_CHECKS else '（较慢）'}")
        return 0
    if not args.project:
        parser.error("需要 --project")
    ctx = make_ctx(args.project, args.ref)
    names = args.only.split(",") if args.only else (list(CHECKS) if args.all else FAST_CHECKS)
    results = run_checks(ctx, [n.strip() for n in names if n.strip()])
    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print(format_results(results))
    failed = [r for r in results if not r.ok and not r.skipped and r.severity == "error"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
