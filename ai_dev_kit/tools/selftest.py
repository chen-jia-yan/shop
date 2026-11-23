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


@case("守卫：内置拦截 / 确认 / 放行用例全部符合预期（项目和工作台两种位置）")
def _t_guard() -> None:
    import guard

    bad = []
    for title, payload, expected, where in guard.SELFTEST_CASES:
        sandbox = tempfile.mkdtemp()
        projects = [{"name": "selftest", "path": sandbox}] if where == "project" else []
        g = guard.Guard({"guard": {}, "projects": projects}, forced_mode="project" if where == "project" else "workbench")
        p = dict(payload)
        p["cwd"] = sandbox
        v = g.decide(p)
        if v.decision != expected:
            bad.append(f"{title}: 期望 {expected} 实际 {v.decision}（{v.rule}）")
    expect(not bad, "；".join(bad))


@case("守卫：删除数据流程（旧版本退路：拦下 → 用户同意 → 放行一次 → 再来要重新问；拒绝后一直拦）")
def _t_delete_flow() -> None:
    import contextlib
    import io

    import guard

    with contextlib.redirect_stdout(io.StringIO()) as out:
        failed_steps = guard._selftest_delete_flow()
    expect(failed_steps == 0, out.getvalue()[-800:])


@case("守卫：当场确认（删数据弹确认框、测试自动套禁删保护、范围外文件当场问）")
def _t_ask_flow() -> None:
    import contextlib
    import io

    import guard

    with contextlib.redirect_stdout(io.StringIO()) as out:
        failed_steps = guard._selftest_ask_flow()
    expect(failed_steps == 0, out.getvalue()[-800:])


@case("删除同意的识别：同意 / 继续等 / 拒绝")
def _t_consent() -> None:
    kitlib.delete_request("s-consent", "cypher-shell \"MATCH (n:T) DETACH DELETE n\"", "风险：低")
    expect(kitlib.delete_consent("s-consent", "这个是哪个库？") == "", "用户提问不应当算同意")
    expect(kitlib.delete_consent("s-consent", "先查一下有多少条") == "", "用户要先查数量不应当算同意")
    expect(kitlib.delete_consent("s-consent", "同意") == "approved", "“同意”应当算同意")
    kitlib.delete_request("s-consent2", "curl -X DELETE http://x/1", "风险：中")
    expect(kitlib.delete_consent("s-consent2", "不同意，先别删") == "rejected", "“不同意”应当算拒绝")
    expect(kitlib.delete_core("python \"C:/kit/tools/kit_run.py\" --allow-delete -- uv run pytest -q")
           == "uv run pytest -q", "去掉 kit_run 包装后的命令不对")


@case("删除风险评估：整图删除为高风险，带条件的本地删除为低风险")
def _t_assess() -> None:
    import kit_rules

    high = kit_rules.assess("cypher-shell \"MATCH (n) DETACH DELETE n\"")
    expect(high.level == "高", f"整图删除应当是高风险，实际 {high.level}")
    low = kit_rules.assess("mysql -h localhost -e \"DELETE FROM tmp_docs WHERE run_id='t1'\"")
    expect(low.level == "低", f"本地带条件删除应当是低风险，实际 {low.level}")
    no_where = kit_rules.assess("mysql -e \"DELETE FROM documents\"")
    expect(no_where.level == "高", "没有 WHERE 的 DELETE 应当是高风险")
    expect("只读查询" in high.render(), "风险评估里应当建议先做只读计数")


@case("守卫：共享模块没记基线时拦下，记了基线后放行，例外文件直接放行")
def _t_shared_area() -> None:
    import guard

    root = Path(tempfile.mkdtemp())
    proj = {"name": "p", "path": str(root), "shared": ["src/qa/**"], "shared_allow": ["src/qa/browse.py"]}
    g = guard.Guard({"guard": {}, "projects": [proj]}, forced_mode="project")
    edit = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "qa" / "x.py"), "new_str": "y = 2"}, "cwd": str(root)}
    allow = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "qa" / "browse.py"), "new_str": "y = 2"}, "cwd": str(root)}
    expect(g.decide(dict(edit)).rule == "shared-baseline", "没记基线时应当拦下")
    expect(g.decide(dict(allow)).decision == "none", "例外文件应当直接放行")
    kitlib.save_json(kitlib.shared_state_path(proj), {"baseline": {"passed": 3, "failed": 0}})
    expect(g.decide(dict(edit)).decision == "none", "记了基线后应当放行")


@case("守卫：修改范围（scope）外的文件当场问用户，范围内放行")
def _t_scope_guard() -> None:
    import guard

    root = Path(tempfile.mkdtemp())
    kitlib.save_json(root / ".ai-dev-kit" / "scope.json", {"files": ["src/a.py"], "globs": ["tests/*"]})
    g = guard.Guard({"guard": {}, "projects": []}, forced_mode="workbench")
    inside = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "a.py"), "new_str": "x = 1"}, "cwd": str(root)}
    glob_ok = {"toolName": "edit", "toolArgs": {"path": str(root / "tests" / "test_a.py"), "new_str": "x = 1"}, "cwd": str(root)}
    outside = {"toolName": "edit", "toolArgs": {"path": str(root / "src" / "b.py"), "new_str": "x = 1"}, "cwd": str(root)}
    expect(g.decide(inside).decision == "none", "范围内文件被误拒")
    expect(g.decide(glob_ok).decision == "none", "通配范围内文件被误拒")
    expect(g.decide(outside).decision == "ask", "范围外文件应当当场问用户")


@case("一次做完：同一文件改 3 次、同一测试跑 3 次、分 2 次装包时各提醒一次")
def _t_batch_hint() -> None:
    import kit_events

    sid = "s-batch"
    kit_events.batch_reset(sid)
    edit = {"sessionId": sid, "toolName": "edit", "toolArgs": {"path": "src/settings.py", "new_str": "x"}}
    hints = [kit_events.batch_hint(dict(edit)) for _ in range(4)]
    expect(not hints[0] and not hints[1] and "settings.py" in hints[2] and not hints[3], f"改同一文件的提醒不对：{hints}")
    run = {"sessionId": sid, "toolName": "powershell", "toolArgs": {"command": "python kit_run.py -- uv run pytest tests -q -k a"}}
    runs = [kit_events.batch_hint(dict(run)) for _ in range(3)]
    expect(not runs[0] and not runs[1] and "跑了 3 次" in runs[2], f"重复跑测试的提醒不对：{runs}")
    pip = {"sessionId": sid, "toolName": "powershell", "toolArgs": {"command": "pip install a"}}
    pips = [kit_events.batch_hint(dict(pip)) for _ in range(2)]
    expect(not pips[0] and "kit_env.py" in pips[1], f"分次装包的提醒不对：{pips}")


@case("计量：一轮对话的时长、真实 token / 估算 token、工具和能力排行（数据写在临时目录）")
def _t_metrics() -> None:
    import json as _json

    import kit_metrics

    tr = Path(tempfile.mkdtemp()) / "events.jsonl"
    kitlib.write_text(tr, _json.dumps({"type": "assistant.usage", "data": {"inputTokens": 1200, "outputTokens": 300}}) + "\n")
    base = {"sessionId": "s-m", "cwd": tempfile.mkdtemp()}
    kit_metrics.record("session_start", dict(base, timestamp=1_000_000_000_000))
    kit_metrics.record("prompt", dict(base, timestamp=1_000_000_010_000, prompt="帮我修一下 /kit-debug-bug"))
    kit_metrics.record("tool", dict(base, timestamp=1_000_000_020_000, toolName="skill", toolArgs={"skill": "kit-debug-bug"},
                                     toolResult={"textResultForLlm": "ok"}))
    info = kit_metrics.record("stop", dict(base, timestamp=1_000_000_070_000, transcriptPath=str(tr)))
    expect(abs(info["sec"] - 60) < 1 and info["tokens"] == 1500 and not info["est"], f"一轮的统计不对：{info}")
    kit_metrics.record("prompt", dict(base, timestamp=1_000_000_100_000, prompt="再看看"))
    info2 = kit_metrics.record("stop", dict(base, timestamp=1_000_000_110_000, transcriptPath=str(tr)))
    expect(info2["est"], "transcript 没有新的 token 字段时应当标成估算")
    day = kit_metrics.load_day(kit_metrics._day(1_000_000_000))
    expect(day["turns"] == 2 and day["caps"].get("kit-debug-bug", 0) >= 1, f"日统计不对：{day}")
    titles = [ch["title"] for ch in kit_metrics.channels(day)]
    expect(len(titles) == 5, f"榜单应当有 5 个：{titles}")


@case("计量：没用过时是空的（不放任何示例数据）")
def _t_metrics_empty() -> None:
    import kit_metrics

    data = kit_metrics.load_day("19990101")
    expect(data["turns"] == 0 and not data["tools"] and not data["recent"], "空的一天不应当有任何数据")


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


@case("项目：没登记的 git 仓库能自动识别测试命令；不是仓库的目录当作非项目")
def _t_detect_project() -> None:
    root = Path(tempfile.mkdtemp(prefix="kit-proj-")) / "my-service"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    kitlib.write_text(root / "pyproject.toml", "[tool.ruff]\nline-length = 120\n")
    kitlib.write_text(root / "uv.lock", "")
    proj = kitlib.get_project({"projects": []}, str(root / "src"))
    expect(proj is not None and proj.get("_auto") is True, "没有识别出项目")
    expect(proj["name"] == "my-service", f"项目名不对：{proj['name']}")
    expect(proj["checks"].get("tests") == ["uv", "run", "pytest", "tests", "-q"], f"测试命令不对：{proj['checks']}")
    expect("lint" in proj["checks"], "有 ruff 配置时应当识别出 lint 命令")
    plain = Path(tempfile.mkdtemp(prefix="kit-noproj-"))
    expect(kitlib.get_project({"projects": []}, str(plain)) is None, "普通目录不应当被当成项目")
    registered = {"projects": [{"name": "reg", "path": str(root)}]}
    expect(kitlib.get_project(registered, str(root / "tests"))["name"] == "reg", "登记过的项目应当优先于自动识别")
    expect(kitlib.get_project(registered, "reg")["name"] == "reg", "按名字找登记过的项目失败")


@case("进度状态：写入、读取、分步、过期自动回到空闲、拒绝未知阶段")
def _t_status() -> None:
    import kit_status

    kit_status.write_status("planning", "", task="测试", steps="改服务层|改接口|补测试")
    kit_status.write_status("waiting", "方案好了", step=1)
    data = kit_status.read_status()
    expect(data["stage"] == "waiting" and data["step"] == 1 and data["total"] == 3, f"读回的状态不对：{data}")
    stale = dict(data, updated=0)
    kitlib.save_json(kit_status.STATUS_PATH, stale)
    expect(kit_status.read_status()["stage"] == "idle", "很久没更新的状态应当当作空闲")
    try:
        kit_status.write_status("unknown")
        raise AssertionError("未知阶段应当报错")
    except SystemExit:
        pass


@case("桌面机器人菜单：registry.json 每个按钮都能被识别")
def _t_registry_for_pet() -> None:
    data = kitlib.load_json(kitlib.REGISTRY_PATH, {}) or {}
    groups = {g["id"] for g in data.get("groups", [])}
    kinds = {"run_tool", "prompt_only", "launch_agent", "open_path", "builtin"}
    builtins = {"new_request", "status", "memory_add", "toggle_hud"}
    bad = [a.get("id") for a in data.get("actions", [])
           if a.get("group") not in groups or a.get("kind") not in kinds
           or (a.get("kind") == "builtin" and a.get("builtin") not in builtins)]
    expect(not bad, f"这些按钮在菜单里不会正常显示或无法执行：{bad}")


@case("自动流程：总调度代理和 kit-autopilot 技能都在，个人规则里写了默认流程")
def _t_autopilot() -> None:
    expect((kitlib.KIT_ROOT / "agents" / "kit-orchestrator.agent.md").is_file(), "缺少总调度代理")
    expect((kitlib.KIT_ROOT / "skills" / "kit-autopilot" / "SKILL.md").is_file(), "缺少 kit-autopilot 技能")
    personal = kitlib.read_text(kitlib.KIT_ROOT / "instructions" / "personal.md")
    expect("/kit-autopilot" in personal and "确认" in personal, "个人规则里没有写默认流程")


@case("技能试用台：格式正确的技能通过；名字和目录不一致、带 BOM、引用不存在的文件都能查出来")
def _t_skill_check() -> None:
    import kit_skill

    base = Path(tempfile.mkdtemp())
    good = base / "my-merge-excel"
    kitlib.write_text(good / "SKILL.md", "---\nname: my-merge-excel\ndescription: 把多个 Excel 合并成一个。用于用户说“合并这些表格”的时候。\n---\n\n"
                      "# 合并表格\n\n## 用户会这样说\n- 合并这些表格\n- 把几个 Excel 拼起来\n\n## 不适用\n- 导入数据库\n\n## 步骤\n1. 读取\n")
    rep, meta, _ = kit_skill.check(good)
    expect(rep.ok, f"格式正确的技能被判为有问题：{rep.errors}")
    bad = base / "wrong-dir"
    (bad).mkdir()
    (bad / "SKILL.md").write_bytes(b"\xef\xbb\xbf---\nname: other-name\ndescription: x\n---\n\n# x\n\n[ref](references/missing.md)\n")
    rep2, _, _ = kit_skill.check(bad)
    text = "；".join(rep2.errors)
    expect("BOM" in text and "不一致" in text and "不存在" in text, f"没有查出全部问题：{text}")


@case("能力目录：用户的原话能匹配到对应技能，无关的话不乱匹配")
def _t_catalog() -> None:
    import kit_catalog

    items = kit_catalog.build()
    names = {i["name"] for i in items}
    expect({"kit-debug-bug", "kit-data-safety", "kit-env-fix", "kit-skill-lab"} <= names, f"能力目录缺少技能：{names}")
    hit = kit_catalog.match("为什么报错", items)
    expect(hit and hit[0][1]["name"] == "kit-debug-bug", f"“为什么报错”没匹配到排障：{hit}")
    hit2 = kit_catalog.match("测试报了 KitDeleteBlocked", items)
    expect(hit2 and hit2[0][1]["name"] == "kit-data-safety", f"删除被拦没匹配到数据安全：{hit2}")
    expect(not kit_catalog.match("今天天气不错", items), "无关的话不应当匹配到能力")
    expect("kit-debug-bug" in kit_catalog.digest(items), "会话目录里应当有技能")


@case("配置升级：旧版的受保护目录和注意事项自动换成 2.0 的说法，可以反复运行")
def _t_migrate() -> None:
    import install

    cfg = {"projects": [{"name": "p", "protected": ["src/qa/**"], "protected_allow": ["src/qa/b.py"],
                         "notes": ["同事的问答知识插件 src/qa/ 不要改", "共享 Neo4j：hk 的数据不删不改"]}],
           "session_context": {"max_chars": 1800}}
    changes = install.migrate_config(cfg)
    p = cfg["projects"][0]
    expect(p.get("shared") == ["src/qa/**"] and "protected" not in p, f"受保护目录没有换成共享模块：{p}")
    expect(not any("不要改" in n or "不删不改" in n for n in p["notes"]), f"旧的注意事项还在：{p['notes']}")
    expect(any("同意" in n for n in p["notes"]), "新的删除说明没有写进注意事项")
    expect("nodelete" in cfg and cfg["session_context"]["max_chars"] == 3600 and changes, "新配置段没有加上")
    expect(install.migrate_config(cfg) == [], "第二次运行不应当再改")


@case("会话注入：写明模式、删除要先问、一次做完、能力目录")
def _t_session_context() -> None:
    import session_start

    text = session_start.build_context(tempfile.mkdtemp(), {"projects": []})
    for word in ("模式：", "等用户回复同意", "一次做完", "kit_env.py", "可以用的技能和代理"):
        expect(word in text, f"会话注入里缺少：{word}")


@case("全量体检：从代码的 import 里找出第三方包，排除标准库和本项目自己的模块")
def _t_env_imports() -> None:
    import kit_env

    root = Path(tempfile.mkdtemp())
    kitlib.write_text(root / "src" / "app" / "__init__.py", "")
    kitlib.write_text(root / "src" / "app" / "main.py", "import os\nimport yaml\nfrom app import util\nfrom docx import Document\n"
                      "TOKEN = os.environ['APP_TOKEN']\n")
    files = kit_env._py_files(root, ["src"])
    imports, env_names = kit_env.collect_imports(files)
    local = kit_env.local_modules(root, ["src"])
    third = sorted(m for m in imports if m not in set(sys.stdlib_module_names) and m not in local) \
        if hasattr(sys, "stdlib_module_names") else ["docx", "yaml"]
    expect(third == ["docx", "yaml"], f"第三方包识别不对：{third}")
    expect(env_names == ["APP_TOKEN"], f"强制读取的配置名不对：{env_names}")
    expect(kit_env.IMPORT_TO_PACKAGE["yaml"] == "PyYAML", "包名映射不对")


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
