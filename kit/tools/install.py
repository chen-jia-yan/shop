"""安装 / 更新 / 卸载 ai-dev-kit（可以反复运行，结果一样）。

做的事：
1. 没有 kit.config.json 时，从示例复制一份，并自动填好当前 Python 路径；
2. 把 skills/ 和 style-packs/ 里的技能同步到 ~/.copilot/skills/（个人技能，所有项目可用）；
3. 把 agents/ 里的自定义代理同步到 ~/.copilot/agents/；
4. 把 instructions/personal.md 合并进 ~/.copilot/copilot-instructions.md（只替换标记之间的内容，你自己写的部分不动）；
5. 写入 ~/.copilot/hooks/ai-dev-kit.json，注册三个钩子：会话开始注入上下文、调用工具前拦截、改完文件检查；
6. 记录安装清单到 ~/.ai-dev-kit/installed.json，卸载和更新时只动自己装的东西；
7. 被覆盖的文件先备份到 ~/.ai-dev-kit/backups/时间戳/。

用法（在工具包根目录）：
    python tools/install.py               # 安装或更新
    python tools/install.py --dry-run     # 只显示将要做什么
    python tools/install.py --no-hooks    # 不注册钩子
    python tools/install.py --hook-style powershell   # 旧版 Copilot 不支持 exec 时用
    python tools/install.py --uninstall   # 卸载
装完重启 Copilot（或在会话里输入 /skills reload），再运行 python tools/kit_doctor.py 检查。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import kitlib

BEGIN = "<!-- ai-dev-kit:begin（这段由 ai-dev-kit 安装脚本维护，请不要手动修改） -->"
END = "<!-- ai-dev-kit:end -->"
HOOK_FILE = "ai-dev-kit.json"
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".yaml", ".yml"}


class Installer:
    def __init__(self, dry: bool):
        self.dry = dry
        self.home = kitlib.copilot_home()
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup_dir = kitlib.DATA_DIR / "backups" / self.stamp
        self.manifest_path = kitlib.DATA_DIR / "installed.json"
        self.manifest: dict[str, Any] = kitlib.load_json(self.manifest_path, {}) or {}
        self.actions: list[str] = []

    def say(self, msg: str) -> None:
        self.actions.append(msg)
        print(("[预演] " if self.dry else "") + msg)

    def backup(self, path: Path) -> None:
        if not path.exists() or self.dry:
            return
        target = self.backup_dir / path.relative_to(self.home) if self.home in path.parents else self.backup_dir / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)

    # -------------------------------------------------- 配置

    def ensure_config(self) -> dict[str, Any]:
        if kitlib.CONFIG_PATH.exists():
            cfg = kitlib.load_config()
            self.say(f"使用已有配置：{kitlib.CONFIG_PATH}")
        else:
            cfg = kitlib.load_json(kitlib.EXAMPLE_CONFIG_PATH, {}) or {}
            cfg["python"] = sys.executable
            self.say(f"创建配置 {kitlib.CONFIG_PATH}（Python 填为 {sys.executable}），请按实际情况修改项目路径和启动脚本。")
            if not self.dry:
                kitlib.save_json(kitlib.CONFIG_PATH, cfg)
        for proj in cfg.get("projects", []):
            if proj.get("path") and not Path(proj["path"]).is_dir():
                print(f"  ! 项目 {proj.get('name')} 的目录不存在：{proj['path']}（不影响安装，记得改 kit.config.json）")
        return cfg

    # -------------------------------------------------- 渲染与同步

    def render(self, text: str, cfg: dict[str, Any]) -> str:
        kit = str(kitlib.KIT_ROOT).replace("\\", "/")
        return text.replace("{{KIT_ROOT}}", kit).replace("{{PYTHON}}", kitlib.python_exe(cfg).replace("\\", "/"))

    def copy_tree(self, src: Path, dst: Path, cfg: dict[str, Any]) -> None:
        if self.dry:
            return
        if dst.exists():
            shutil.rmtree(dst)
        for path in src.rglob("*"):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() in TEXT_SUFFIXES:
                kitlib.write_text(target, self.render(kitlib.read_text(path), cfg))
            else:
                shutil.copy2(path, target)

    def sync_skills(self, cfg: dict[str, Any]) -> list[str]:
        sources: list[Path] = []
        for base in (kitlib.KIT_ROOT / "skills", kitlib.KIT_ROOT / "style-packs"):
            if base.is_dir():
                sources.extend(p for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith("_")
                               and (p / "SKILL.md").is_file())
        installed: list[str] = []
        skills_home = self.home / "skills"
        previous = set(self.manifest.get("skills", []))
        for src in sources:
            dst = skills_home / src.name
            if dst.exists() and src.name not in previous:
                self.say(f"备份同名的已有技能：{dst}")
                self.backup(dst)
            self.copy_tree(src, dst, cfg)
            installed.append(src.name)
        for stale in sorted(previous - set(installed)):
            target = skills_home / stale
            if target.exists():
                self.say(f"移除已不存在的旧技能：{stale}")
                if not self.dry:
                    shutil.rmtree(target)
        self.say(f"同步技能 {len(installed)} 个到 {skills_home}：{', '.join(installed)}")
        return installed

    def sync_agents(self, cfg: dict[str, Any]) -> list[str]:
        agents_home = self.home / "agents"
        previous = set(self.manifest.get("agents", []))
        installed: list[str] = []
        for src in sorted((kitlib.KIT_ROOT / "agents").glob("*.agent.md")):
            dst = agents_home / src.name
            if dst.exists() and src.name not in previous:
                self.backup(dst)
            if not self.dry:
                kitlib.write_text(dst, self.render(kitlib.read_text(src), cfg))
            installed.append(src.name)
        for stale in sorted(previous - set(installed)):
            target = agents_home / stale
            if target.exists():
                self.say(f"移除已不存在的旧代理：{stale}")
                if not self.dry:
                    target.unlink()
        self.say(f"同步自定义代理 {len(installed)} 个到 {agents_home}：{', '.join(a.replace('.agent.md', '') for a in installed)}")
        return installed

    def merge_instructions(self, cfg: dict[str, Any], remove: bool = False) -> None:
        target = self.home / "copilot-instructions.md"
        current = kitlib.read_text(target) if target.exists() else ""
        if BEGIN in current and END in current:
            head, rest = current.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            outside = (head.rstrip() + "\n\n" + tail.lstrip()).strip()
        else:
            outside = current.strip()
        if remove:
            new = outside + ("\n" if outside else "")
            self.say(f"从 {target} 移除工具包指令段")
        else:
            block = self.render(kitlib.read_text(kitlib.KIT_ROOT / "instructions" / "personal.md"), cfg).strip()
            new = (outside + "\n\n" if outside else "") + BEGIN + "\n" + block + "\n" + END + "\n"
            self.say(f"合并个人指令到 {target}（你原有的内容保留在标记段之外）")
        if new != current and not self.dry:
            self.backup(target)
            kitlib.write_text(target, new)

    def write_hooks(self, cfg: dict[str, Any], style: str) -> None:
        target = self.home / "hooks" / HOOK_FILE
        py = kitlib.python_exe(cfg)
        hooks_dir = kitlib.KIT_ROOT / "hooks"

        def entry(script: str, timeout: int, matcher: str | None = None) -> dict[str, Any]:
            path = str(hooks_dir / script)
            if style == "powershell":
                item: dict[str, Any] = {"type": "command", "powershell": f"& '{py}' '{path}'", "timeoutSec": timeout}
            else:
                item = {"type": "command", "exec": py, "args": [path], "timeoutSec": timeout}
            if matcher:
                item["matcher"] = matcher
            return item

        data = {
            "version": 1,
            "hooks": {
                "sessionStart": [entry("session_start.py", 10)],
                "preToolUse": [entry("guard.py", 5)],
                "postToolUse": [entry("post_edit.py", 10, "edit|create|apply_patch|str_replace_editor|write|str_replace|insert")],
            },
        }
        self.say(f"写入钩子配置 {target}（方式：{style}）")
        if not self.dry:
            self.backup(target)
            kitlib.save_json(target, data)

    def remove_hooks(self) -> None:
        target = self.home / "hooks" / HOOK_FILE
        if target.exists():
            self.say(f"删除钩子配置 {target}")
            if not self.dry:
                self.backup(target)
                target.unlink()

    def save_manifest(self, skills: list[str], agents: list[str], hooks: bool) -> None:
        data = {"kit_root": str(kitlib.KIT_ROOT), "copilot_home": str(self.home), "skills": skills,
                "agents": agents, "hooks": hooks, "installed_at": kitlib.now(),
                "kit_version": (kitlib.load_json(kitlib.KIT_ROOT / "plugin.json", {}) or {}).get("version", "")}
        if not self.dry:
            kitlib.save_json(self.manifest_path, data)

    # -------------------------------------------------- 卸载

    def uninstall(self) -> None:
        for name in self.manifest.get("skills", []):
            target = self.home / "skills" / name
            if target.exists():
                self.say(f"删除技能 {name}")
                if not self.dry:
                    shutil.rmtree(target)
        for name in self.manifest.get("agents", []):
            target = self.home / "agents" / name
            if target.exists():
                self.say(f"删除代理 {name}")
                if not self.dry:
                    target.unlink()
        self.merge_instructions({}, remove=True)
        self.remove_hooks()
        if self.manifest_path.exists() and not self.dry:
            self.manifest_path.unlink()
        self.say("卸载完成。工具包目录、记忆和日志都保留着，需要的话手动删除。")


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="安装 / 更新 / 卸载 ai-dev-kit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-hooks", action="store_true")
    parser.add_argument("--hook-style", choices=["exec", "powershell"], default="exec")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    if sys.version_info < (3, 9):
        print("需要 Python 3.9 以上。")
        return 2
    inst = Installer(args.dry_run)
    print(f"工具包目录：{kitlib.KIT_ROOT}\nCopilot 配置目录：{inst.home}\n")
    if args.uninstall:
        inst.uninstall()
        return 0
    if not inst.home.exists():
        print(f"提醒：{inst.home} 不存在。如果你从没启动过 Copilot CLI，先启动一次再安装；"
              "如果你用 COPILOT_HOME 指定了别的目录，请先设置好这个环境变量。")
        if not args.dry_run:
            inst.home.mkdir(parents=True, exist_ok=True)
    cfg = inst.ensure_config()
    skills = inst.sync_skills(cfg)
    agents = inst.sync_agents(cfg)
    inst.merge_instructions(cfg)
    if args.no_hooks:
        inst.remove_hooks()
    else:
        inst.write_hooks(cfg, args.hook_style)
    inst.save_manifest(skills, agents, not args.no_hooks)
    if not args.dry_run:
        (kitlib.DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    print("\n下一步：")
    print("  1. 按实际情况检查 kit.config.json（项目路径、启动脚本、受保护目录）")
    print("  2. 重启 Copilot CLI；在会话里输入 /skills list 和 /agent，应能看到 kit- 开头的技能和代理")
    print("  3. 运行 python tools/kit_doctor.py 做一次完整体检")
    print("  4. 运行 python tools/selftest.py 确认工具包自身没有问题")
    print("  5. 双击 widget/start_widget.bat 打开桌面宠物")
    if inst.dry:
        print("\n以上为预演，没有改动任何文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
