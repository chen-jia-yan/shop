"""体检：检查工具包在这台电脑上是否装好、能用，每一项都给出修复办法。只读，不改任何东西。

用法：python tools/kit_doctor.py [--quick]   （--quick 跳过运行 copilot --version 和删除保护检查）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

import kitlib

OK, WARN, FAIL = "通过", "提醒", "失败"
results: list[tuple[str, str, str, str]] = []  # (状态, 项目, 说明, 修复办法)


def add(status: str, item: str, detail: str, fix: str = "") -> None:
    results.append((status, item, detail, fix))


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 9):
        add(OK, "Python", f"{v.major}.{v.minor}.{v.micro}  {sys.executable}")
    else:
        add(FAIL, "Python", f"版本 {v.major}.{v.minor} 太旧", "需要 Python 3.9 以上")
    cfg = kitlib.load_config()
    configured = cfg.get("python", "")
    if configured and not Path(configured).exists():
        add(FAIL, "配置里的 Python", f"找不到 {configured}", "修改 kit.config.json 的 python 字段")


def check_tkinter() -> None:
    try:
        import tkinter

        add(OK, "tkinter（桌面机器人需要）", f"Tk {tkinter.TkVersion}")
    except Exception as exc:
        add(WARN, "tkinter（桌面机器人需要）", f"无法导入：{exc}", "桌面机器人用不了，其他功能不受影响；重新安装 Python 时勾选 tcl/tk")


def check_git() -> None:
    code, out = kitlib.run(["git", "--version"], timeout=20)
    add(OK if code == 0 else FAIL, "git", out.strip() if code == 0 else "找不到 git", "" if code == 0 else "安装 git 或把它加进 PATH")


def check_copilot(cfg: dict) -> None:
    for name, prof in (cfg.get("profiles") or {}).items():
        launcher = prof.get("launcher", "")
        label = f"Copilot（{prof.get('label', name)}）"
        if not launcher:
            add(WARN, label, "没有配置 launcher", "在 kit.config.json 的 profiles 里填写启动命令或 bat 路径")
            continue
        if prof.get("launcher_type") == "bat":
            exists = Path(launcher).is_file()
            add(OK if exists else FAIL, label, f"启动脚本 {'存在' if exists else '不存在'}：{launcher}（不自动运行，避免弹出会话）",
                "" if exists else "修改 profiles 里的 launcher 路径")
            continue
        code, out = kitlib.run([launcher, "--version"], timeout=30)
        if code == 0:
            add(OK, label, out.strip().splitlines()[0] if out.strip() else "可运行")
        else:
            add(FAIL, label, f"运行 {launcher} --version 失败：{out.strip()[:120]}", "确认 copilot 在 PATH 里，或填写完整路径")


def check_install() -> None:
    home = kitlib.copilot_home()
    manifest = kitlib.load_json(kitlib.DATA_DIR / "installed.json")
    if not manifest:
        add(FAIL, "安装状态", "还没有安装", "运行 python tools/install.py")
        return
    if Path(manifest.get("kit_root", "")).resolve() != kitlib.KIT_ROOT.resolve():
        add(WARN, "安装状态", f"安装时的工具包目录是 {manifest.get('kit_root')}，与当前目录不同", "在当前目录重新运行 install.py")
    missing_skills = [s for s in manifest.get("skills", []) if not (home / "skills" / s / "SKILL.md").is_file()]
    add(OK if not missing_skills else FAIL, "技能", f"已安装 {len(manifest.get('skills', []))} 个"
        + (f"，缺少：{', '.join(missing_skills)}" if missing_skills else ""), "" if not missing_skills else "重新运行 install.py")
    missing_agents = [a for a in manifest.get("agents", []) if not (home / "agents" / a).is_file()]
    add(OK if not missing_agents else FAIL, "自定义代理", f"已安装 {len(manifest.get('agents', []))} 个"
        + (f"，缺少：{', '.join(missing_agents)}" if missing_agents else ""), "" if not missing_agents else "重新运行 install.py")
    instr = home / "copilot-instructions.md"
    has_block = instr.is_file() and "ai-dev-kit:begin" in kitlib.read_text(instr)
    add(OK if has_block else FAIL, "个人指令", str(instr) if has_block else "没有找到工具包指令段", "" if has_block else "重新运行 install.py")
    for name, required in (("ai-dev-kit.json", True), ("ai-dev-kit-extra.json", False)):
        hook_file = home / "hooks" / name
        if not manifest.get("hooks"):
            if required:
                add(WARN, "钩子配置", "安装时选择了不注册钩子：硬拦截没有生效", "需要时运行 python tools/install.py（不加 --no-hooks）")
            continue
        label = "钩子配置（核心）" if required else "钩子配置（扩展：计时、该你了、消息提示）"
        try:
            data = json.loads(kitlib.read_text(hook_file))
            events = sorted(data.get("hooks", {}).keys())
            scripts = [a for evs in data["hooks"].values() for e in evs for a in e.get("args", [])[:1]]
            bad = [s for s in scripts if not Path(s).is_file()]
            add(OK if not bad else FAIL, label, f"{hook_file.name}：{', '.join(events)}" + (f"；脚本不存在：{bad}" if bad else ""),
                "" if not bad else "重新运行 install.py")
        except (OSError, ValueError, KeyError) as exc:
            add(FAIL if required else WARN, label, f"读取失败：{exc}", "重新运行 install.py")


def check_catalog() -> None:
    import kit_catalog

    items = kit_catalog.build()
    mine = [i["name"] for i in items if i["source"] == "user"]
    missing = [i["name"] for i in items if not i.get("triggers")]
    add(OK, "能力目录", f"{len(items)} 个技能和代理（你自己的 {len(mine)} 个）")
    if missing:
        add(WARN, "能力目录：自动匹配", f"这些没写“用户会这样说”，自动匹配会弱一些：{'、'.join(missing[:8])}",
            "在 SKILL.md 里加“## 用户会这样说”小节，或用 kit_skill.py try 看效果")


def check_nodelete(cfg: dict) -> None:
    runtime = kitlib.KIT_ROOT / "runtime"
    if not (runtime / "sitecustomize.py").is_file() or not (runtime / "kit_nodelete.py").is_file():
        add(FAIL, "删除保护", f"{runtime} 里缺少文件", "重新解压工具包")
        return
    for proj in cfg.get("projects", []):
        if not Path(proj.get("path", "")).is_dir():
            continue
        code, out = kitlib.run([sys.executable, str(kitlib.KIT_ROOT / "tools" / "kit_run.py"), "--check", "--cwd", proj["path"]],
                               timeout=240)
        active = "已生效" in out
        add(OK if active else WARN, f"删除保护（{proj.get('name')}）", "已生效" if active else kitlib.redact(out.strip()[-160:], 160),
            "" if active else "把 kit_run.py --check 的输出发给维护者；在此之前测试里的删除只有守卫一道防线")


def check_guard() -> None:
    script = kitlib.KIT_ROOT / "hooks" / "guard.py"
    code, out = kitlib.run([sys.executable, str(script), "--selftest"], timeout=60)
    last = out.strip().splitlines()[-1] if out.strip() else ""
    add(OK if code == 0 else FAIL, "守卫自测", last or out[:200], "" if code == 0 else "把输出发给维护者；必要时先用 --no-hooks 重新安装")
    payload = json.dumps({"toolName": "view", "toolArgs": {"path": ".env"}, "cwd": str(Path.home())})
    try:
        import os
        import tempfile

        env = dict(os.environ, AI_DEV_KIT_HOME=tempfile.mkdtemp(prefix="kit-doctor-"))  # 模拟调用不写进你的日志和统计
        proc = subprocess.run([sys.executable, str(script)], input=payload.encode("utf-8"), env=env,
                              capture_output=True, timeout=10)
        reply = proc.stdout.decode("utf-8", errors="replace")
        ok = proc.returncode == 0 and '"deny"' in reply
        add(OK if ok else FAIL, "钩子通信（模拟 Copilot 调用）", reply[:120] or proc.stderr.decode("utf-8", "replace")[:120],
            "" if ok else "守卫没有按预期输出 JSON，检查 Python 路径和脚本")
    except subprocess.TimeoutExpired:
        add(FAIL, "钩子通信（模拟 Copilot 调用）", "超时", "钩子超时会被 Copilot 当成放行，需要排查")


def check_projects(cfg: dict) -> None:
    home = kitlib.copilot_home()
    for proj in cfg.get("projects", []):
        name = proj.get("name", "?")
        path = Path(proj.get("path", ""))
        if not path.is_dir():
            add(FAIL, f"项目 {name}", f"目录不存在：{path}", "修改 kit.config.json")
            continue
        notes = []
        pack = proj.get("style_pack")
        if pack and not (home / "skills" / pack / "SKILL.md").is_file():
            notes.append(f"风格包 {pack} 未安装")
        for key, cmd in (proj.get("checks") or {}).items():
            exe = kitlib.expand(cmd[0], kitlib.base_ctx(cfg, proj)) if cmd else ""
            if exe and kitlib.resolve_exe(exe) == exe and not Path(exe).exists():
                notes.append(f"{key} 命令找不到：{exe}")
        add(OK if not notes else WARN, f"项目 {name}", str(path) + ("；" + "；".join(notes) if notes else ""),
            "" if not notes else "检查 kit.config.json 中该项目的 style_pack 和 checks")


def check_kit_files() -> None:
    import check_chars

    files = check_chars.iter_files([str(kitlib.KIT_ROOT)], set(check_chars.DEFAULT_EXTS))
    errors = [i for f in files for i in check_chars.check_file(f) if i.severity == "error"]
    add(OK if not errors else FAIL, "工具包文件编码", f"{len(files)} 个文件，问题 {len(errors)} 处",
        "" if not errors else "运行 python tools/check_chars.py . 查看")


def check_data_dir() -> None:
    try:
        probe = kitlib.DATA_DIR / "logs" / ".probe"
        kitlib.write_text(probe, "ok")
        probe.unlink()
        add(OK, "数据目录", str(kitlib.DATA_DIR))
    except OSError as exc:
        add(FAIL, "数据目录", f"无法写入 {kitlib.DATA_DIR}：{exc}", "设置环境变量 AI_DEV_KIT_HOME 指向可写目录")


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="ai-dev-kit 体检")
    parser.add_argument("--quick", action="store_true", help="跳过运行 copilot --version 和删除保护检查")
    args = parser.parse_args(argv)
    cfg = kitlib.load_config()
    if cfg.get("_from_example"):
        add(WARN, "配置文件", "还没有 kit.config.json，正在使用示例配置", "运行 install.py 会自动创建，然后按实际情况修改")
    steps: list[Callable[[], None]] = [check_python, check_tkinter, check_git, check_data_dir, check_install,
                                       check_guard, check_catalog, check_kit_files, lambda: check_projects(cfg)]
    if not args.quick:
        steps.insert(3, lambda: check_copilot(cfg))
        steps.append(lambda: check_nodelete(cfg))
    for step in steps:
        try:
            step()
        except Exception as exc:
            add(FAIL, getattr(step, "__name__", "检查"), f"检查本身出错：{exc!r}")
    width = max(len(r[1]) for r in results) + 2
    for status, item, detail, fix in results:
        print(f"[{status}] {item.ljust(width)}{detail}")
        if fix and status != OK:
            print(f"       {''.ljust(width)}→ {fix}")
    fails = sum(1 for r in results if r[0] == FAIL)
    warns = sum(1 for r in results if r[0] == WARN)
    print(f"\n体检完成：失败 {fails} 项，提醒 {warns} 项。")
    print("手动确认几件事（脚本没法替你看）：\n"
          "  1. 启动 Copilot 时没有出现“! Invalid hook configuration”。如果扩展钩子文件被提示无效，说明这个版本不支持新事件，\n"
          "     核心功能不受影响；面板里的计时和“该你了”会少一些。\n"
          "  2. 在 Copilot 会话里输入 /skills list，能看到 kit- 开头的技能；输入 /agent，能看到 kit- 开头的代理。\n"
          "  3. 在会话里让 Copilot “读取 .env 文件”，应该看到 ai-dev-kit 守卫的拒绝提示。\n"
          "  4. 让 Copilot 运行一条删除语句（例如对测试库），应该先看到风险评估，你回复“同意”后才执行。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
