"""工具包自身的自测：在临时目录里把每个模块跑一遍，确认在这台电脑上工作正常。

不会碰你的项目、Copilot 配置和记忆库（日志、缓存也写到临时目录）。
用法：python tools/selftest.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable

_TMP_HOME = tempfile.mkdtemp(prefix="kit-selftest-home-")
os.environ["AI_DEV_KIT_HOME"] = _TMP_HOME  # 必须在导入 kitlib 之前设置
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import check_chars
import checks
import kitlib
import mem
import prompt_builder
import prompt_lint

passed: list[str] = []
failed: list[tuple[str, str]] = []


def case(name: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    def deco(fn: Callable[[], None]) -> Callable[[], None]:
        try:
            fn()
            passed.append(name)
        except Exception:
            failed.append((name, traceback.format_exc(limit=3)))
        return fn
    return deco


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


@case("check_chars：识别 UTF-16、BOM、零宽字符、Tab 缩进，正常文件不误报")
def _t_chars() -> None:
    d = Path(tempfile.mkdtemp())
    (d / "u16.py").write_bytes("x = 1\n".encode("utf-16"))
    (d / "bom.py").write_bytes(b"\xef\xbb\xbfx = 1\n")
    (d / "zw.py").write_text("x\u200b = 1\n", encoding="utf-8")
    (d / "tab.py").write_text("def f():\n\treturn 1\n", encoding="utf-8")
    (d / "ok.py").write_text("def f():\n    return '中文'\n", encoding="utf-8")
    rules = {p.name: {i.rule for i in check_chars.check_file(p)} for p in d.iterdir()}
    expect("utf16" in rules["u16.py"], f"UTF-16 未识别：{rules['u16.py']}")
    expect("bom" in rules["bom.py"], "BOM 未识别")
    expect("zero-width" in rules["zw.py"], "零宽字符未识别")
    expect("tab-indent" in rules["tab.py"], "Tab 缩进未识别")
    expect(not rules["ok.py"], f"正常文件被误报：{rules['ok.py']}")


@case("守卫：内置 27 条拦截/放行用例全部符合预期")
def _t_guard() -> None:
    import guard

    g = guard.Guard({"guard": {}, "projects": []})
    sandbox = tempfile.mkdtemp()
    bad = []
    for title, payload, expected in guard.SELFTEST_CASES:
        p = dict(payload)
        p["cwd"] = sandbox
        decision, _, _ = g.decide(p)
        if decision != expected:
            bad.append(f"{title}: 期望 {expected} 实际 {decision}")
    expect(not bad, "；".join(bad))


@case("守卫：修改范围（scope）外的文件被拒绝，范围内放行")
def _t_scope_guard() -> None:
    import guard

    root = Path(tempfile.mkdtemp())
    kitlib.save_json(root / ".ai-dev-kit" / "scope.json", {"files": ["src/a.py"], "globs": ["tests/*"]})
    g = guard.Guard({"guard": {}, "projects": []})
    inside = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "a.py"), "new_str": "x = 1"}, "cwd": str(root)}
    glob_ok = {"toolName": "edit", "toolArgs": {"path": str(root / "tests" / "test_a.py"), "new_str": "x = 1"}, "cwd": str(root)}
    outside = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "b.py"), "new_str": "x = 1"}, "cwd": str(root)}
    expect(g.decide(inside)[0] == "none", "范围内文件被误拒")
    expect(g.decide(glob_ok)[0] == "none", "通配范围内文件被误拒")
    expect(g.decide(outside)[0] == "deny", "范围外文件没有被拒绝")


@case("守卫：受保护区域（同事的模块）被拒绝")
def _t_protected_area() -> None:
    import guard

    root = Path(tempfile.mkdtemp())
    cfg = {"guard": {}, "projects": [{"name": "p", "path": str(root), "protected": ["src/qa/**"]}]}
    g = guard.Guard(cfg)
    payload = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "qa" / "x.py"), "new_str": "y = 2"}, "cwd": str(root)}
    expect(g.decide(payload)[0] == "deny", "受保护区域没有被拒绝")


@case("记忆：新增、检索、引用核对（有效 / 锚点移动 / 失效）、拒绝密钥")
def _t_mem() -> None:
    tmp = Path(tempfile.mkdtemp())
    mem.MEMORY_DIR = tmp / "memory"
    mem.ARCHIVE_DIR = mem.MEMORY_DIR / "_archive"
    proj = tmp / "proj"
    kitlib.write_text(proj / "src" / "a.py", "line1\nline2\nVERSION = 'v2'\n")
    orig_root = mem.project_root
    mem.project_root = lambda name: proj if name != mem.GLOBAL else kitlib.KIT_ROOT
    try:
        rc = mem.main(["add", "--project", "p", "--type", "lesson", "--subject", "版本号要同步",
                       "--fact", "VERSION 修改时文档也要改", "--cite", "src/a.py:3#VERSION", "--tags", "版本"])
        expect(rc == 0, f"新增失败 rc={rc}")
        found = mem.search("版本号", project="p")
        expect(found and "版本号" in str(found[0][1].meta.get("subject")), "检索不到刚新增的记忆")
        m = found[0][1]
        expect(mem.verify_memory(m)[0] == "ok", "引用应当有效")
        kitlib.write_text(proj / "src" / "a.py", "\n" * 60 + "VERSION = 'v3'\n")
        status, _ = mem.check_citation("src/a.py:3#VERSION", proj)
        expect(status == "moved", f"锚点移动应识别为 moved，实际 {status}")
        kitlib.write_text(proj / "src" / "a.py", "nothing\n")
        expect(mem.verify_memory(m)[0] == "stale", "引用失效应识别为 stale")
        expect("版本号" not in mem.digest("p", str(proj)), "失效记忆不应出现在会话摘要里")
        rc = mem.main(["add", "--project", "p", "--type", "fact", "--subject", "数据库", "--fact",
                       "连接串 mysql://user:pass123@host/db", "--cite", "user:测试"])
        expect(rc == 2, "含口令的内容应被拒绝保存")
    finally:
        mem.project_root = orig_root


@case("提示词体检：含糊需求得分低并给出追问；具体需求得分高")
def _t_prompt_lint() -> None:
    vague = prompt_lint.analyze("帮我优化一下上传接口")
    good = prompt_lint.analyze(
        "修复 src/tap_ai/api/library_kb.py 的上传接口：目前同名文件重复上传会报错。不要改问答插件。"
        "完成标准：重复上传返回 skipped，document_id 不变。验证：运行 uv run pytest tests/unit/test_library_kb_service.py。"
        "最后贴出测试输出和核对表。例如参考 documents/retry 的写法。")
    expect(vague["score"] < 50, f"含糊需求得分过高：{vague['score']}")
    expect(any("含糊" in a for a in vague["advice"]), "没有指出含糊词")
    expect(good["score"] >= 75, f"具体需求得分过低：{good['score']}")
    r3 = prompt_lint.build_r3("帮我优化一下上传接口")
    expect("【待补充" in r3 and "【核对表】" in r3, "R3 补全结果缺少待补充标记或核对表")


@case("提示词构建：每个模板都能生成，且通用规则在最前面、没有残留占位符")
def _t_builder() -> None:
    for action in prompt_builder.list_actions():
        text = prompt_builder.build(action, "测试任务")
        expect("{{" not in text, f"{action} 有残留占位符")
        if "{{rules}}" in kitlib.read_text(prompt_builder.TEMPLATE_DIR / f"{action}.md"):
            expect(text.startswith("【通用规则】"), f"{action} 的通用规则不在开头（影响缓存命中）")


@case("静态检查：嵌套 ORM 类、永远成立的断言、getattr(settings)")
def _t_checks() -> None:
    root = Path(tempfile.mkdtemp())
    kitlib.write_text(root / "src" / "models.py",
                      "class Base: pass\nclass TokenUsage(Base):\n    __tablename__ = 't'\n"
                      "    class LibraryChunkDraft(Base):\n        __tablename__ = 'd'\n")
    kitlib.write_text(root / "tests" / "test_x.py", "def test_a():\n    x = 1\n    assert x == x\n")
    project = {"name": "t", "path": str(root), "source_dirs": ["src"], "test_dirs": ["tests"]}
    ctx = checks.Ctx(project, root, root, "HEAD", {"projects": [project]})
    res = {r.name: r for r in checks.run_checks(ctx, ["nested_orm_class", "tautological_asserts"])}
    expect(not res["nested_orm_class"].ok, "没识别出嵌套的 ORM 类")
    expect(not res["tautological_asserts"].ok, "没识别出永远成立的断言")
    expect(checks.GETATTR_SETTINGS.search('x = getattr(settings, "library_kb_enabled", False)') is not None,
           "getattr(settings) 规则失效")


@case("指纹缓存：内容不变指纹不变，内容变了指纹改变")
def _t_fingerprint() -> None:
    root = Path(tempfile.mkdtemp())
    code, _ = kitlib.git(["init", "-q"], root)
    if code != 0:
        return  # 没有 git 时跳过
    kitlib.write_text(root / "a.txt", "1")
    f1 = kitlib.tree_fingerprint(root)
    f2 = kitlib.tree_fingerprint(root)
    kitlib.write_text(root / "a.txt", "2")
    f3 = kitlib.tree_fingerprint(root)
    expect(f1 == f2, "内容没变指纹却变了")
    expect(f1 != f3, "内容变了指纹却没变")


@case("工具包文件：编码全部正常")
def _t_kit_encoding() -> None:
    files = check_chars.iter_files([str(kitlib.KIT_ROOT)], set(check_chars.DEFAULT_EXTS))
    bad = [f"{i.path}:{i.line} {i.message}" for f in files for i in check_chars.check_file(f) if i.severity == "error"]
    expect(not bad, "；".join(bad[:5]))


def main() -> int:
    kitlib.setup_console()
    for name in passed:
        print(f"[通过] {name}")
    for name, tb in failed:
        print(f"[失败] {name}\n{tb}")
    print(f"\n自测结果：{len(passed)} 通过，{len(failed)} 失败。（临时目录：{_TMP_HOME}）")
    if failed:
        print("请把上面的失败信息整段发给维护者。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
