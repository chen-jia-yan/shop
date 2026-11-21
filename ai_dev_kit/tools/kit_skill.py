"""技能试用台：写给别人用的技能，先在本机校验、挂上、试用，确认没问题再打包交付。

为什么需要：Copilot 只加载固定位置的技能（~/.copilot/skills/<名字>/SKILL.md、仓库里的 .github/skills/ 等），
你放在别的目录里的技能不会自动出现，会话里就会报“不是内嵌 skill / 找不到”。格式不对（名字和目录不一致、
description 太长、开头不是 ---、带 BOM）也会被静默跳过。这个脚本把这些坑一次查完。

用法：
    python kit_skill.py check  D:/my-skills/api-doc      # 只校验，不改任何东西（也可以检查 *.agent.md）
    python kit_skill.py add    D:/my-skills/api-doc      # 校验通过后复制到 ~/.copilot/skills/，并登记进能力目录
    python kit_skill.py try    api-doc                   # 本地试用：看“用户会这样说”里的话能不能匹配到它、和谁冲突
    python kit_skill.py pack   D:/my-skills/api-doc      # 校验后打成 zip，附带安装说明，发给别人
    python kit_skill.py list                             # 本机所有技能和代理（标出哪些是你自己的）
    python kit_skill.py remove api-doc                   # 只移除用 add 挂上的技能（先备份）
add 之后在会话里输入 /skills reload（或重启 Copilot），再输入 /skills list 确认能看到。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import kit_catalog
import kitlib

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINKS_PATH = kitlib.DATA_DIR / "user_skills.json"
LINK_RE = re.compile(r"\]\(((?!https?:|#|mailto:)[^)\s]+)\)")
SHELL_TOOLS = re.compile(r"(?i)\b(shell|bash|powershell|execute)\b")
SECRET_HINT = re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{8,}")
NEGATIVE_HEAD = re.compile(r"(?m)^##\s*(不适用|不要用|这些情况别用)\s*$")
SKIP_PARTS = {"__pycache__", ".git", ".venv", "node_modules"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def show(self, title: str) -> None:
        print(f"== {title} ==")
        for m in self.errors:
            print(f"  ✗ {m}")
        for m in self.warnings:
            print(f"  ! {m}")
        for m in self.notes:
            print(f"  · {m}")
        if not self.errors:
            print("  ✓ 没有会导致加载失败的问题" + ("（有提醒，建议处理）" if self.warnings else ""))

    @property
    def ok(self) -> bool:
        return not self.errors


def _skill_file(target: Path) -> Path:
    if target.is_file():
        return target
    return target / "SKILL.md"


def check(target: Path) -> tuple[Report, dict[str, str], str]:
    rep = Report()
    path = _skill_file(target)
    is_agent = path.name.endswith(".agent.md")
    if not path.is_file():
        rep.err(f"找不到 {path}。技能目录里必须有一个名字正好是 SKILL.md 的文件（大写）。")
        return rep, {}, ""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        rep.err("文件开头有 BOM。另存为“UTF-8（无 BOM）”，否则开头的 --- 识别不了。")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        rep.err("文件是 UTF-16 编码（PowerShell 的 > 重定向会这样）。改存为 UTF-8。")
        return rep, {}, ""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        rep.err("不是 UTF-8 编码。")
        return rep, {}, ""
    if "\r\n" in text:
        rep.note("用的是 Windows 换行（CRLF），一般没问题。")
    if not text.lstrip("\ufeff").startswith("---"):
        rep.err("第一行必须是 ---（YAML 头）。")
    meta, body = kit_catalog.frontmatter(text.lstrip("\ufeff"))
    name = meta.get("name", "")
    desc = meta.get("description", "")
    expected = path.name.replace(".agent.md", "") if is_agent else path.parent.name
    if not name:
        rep.err("YAML 头里缺 name。")
    elif not NAME_RE.match(name) or len(name) > 64:
        rep.err(f"name “{name}” 只能用小写字母、数字和连字符，最长 64 个字符。")
    elif name != expected:
        rep.err(f"name “{name}” 和{'文件名' if is_agent else '目录名'} “{expected}” 不一致，Copilot 会按目录名找，找不到就报不存在。")
    if not desc:
        rep.err("YAML 头里缺 description。模型完全靠它判断什么时候用这个技能。")
    else:
        if len(desc) > 1024:
            rep.err(f"description 有 {len(desc)} 个字符，超过 1024 会加载失败。")
        if len(desc) < 30:
            rep.warn("description 太短。写清楚“做什么 + 什么时候用（用户会怎么说）”，模型才会主动用它。")
        if not re.search(r"(用于|当|什么时候|时候|如果|when|use )", desc, re.I):
            rep.warn("description 里没写“什么时候用”。加一句“用于……的时候 / 用户说……时”。")
        if ":" in desc and not re.search(r"^description:\s*[\"']", text, re.M):
            rep.warn("description 里有英文冒号且没加引号，部分 YAML 解析器会出错。整段用双引号括起来，或者换成中文冒号。")
    tools = meta.get("allowed-tools", "") or meta.get("tools", "")
    if not is_agent and tools and SHELL_TOOLS.search(tools):
        rep.warn("allowed-tools 里预先放行了 shell：别人装上后这个技能可以不经确认执行任何命令。建议去掉，让用户逐次确认。")
    if not kit_catalog.triggers_of(body):
        rep.warn("正文里没有“## 用户会这样说”小节。加 3~8 句用户的原话，自动匹配会准很多。")
    if re.search(r"(?m)^\s*-\s*（改成", body):
        rep.warn("“## 用户会这样说”里还有脚手架留下的占位句（括号开头），换成用户真实会说的话。")
    if not NEGATIVE_HEAD.search(body):
        rep.note("可以再加一个“## 不适用”小节，写 2~3 句容易误触发的说法，减少乱用。")
    lines = body.count("\n")
    if lines > 500:
        rep.warn(f"正文有 {lines} 行。超过 500 行建议把细节拆到 references/ 里，正文只留步骤，省 token。")
    base = path.parent
    for link in LINK_RE.findall(body):
        rel = link.split("#", 1)[0]
        if rel and not (base / rel).exists():
            rep.err(f"正文引用的文件不存在：{rel}")
    if SECRET_HINT.search(text):
        rep.err("文件里像是写了密码或密钥。交付前一定要删掉。")
    if not is_agent:
        for p in base.rglob("*"):
            if any(part in SKIP_PARTS for part in p.parts):
                continue
            if p.is_file() and p.name.lower().startswith(".env"):
                rep.err(f"技能目录里有 {p.name}，不能带着交付。")
            if p.is_file() and p.suffix == ".py":
                src = p.read_text(encoding="utf-8", errors="replace")
                try:
                    compile(src, str(p), "exec", dont_inherit=True)
                except SyntaxError as exc:
                    rep.err(f"{p.relative_to(base)} 第 {exc.lineno} 行语法错误：{exc.msg}")
    return rep, meta, body


def _links() -> dict[str, Any]:
    return kitlib.load_json(LINKS_PATH, {}) or {}


def add(target: Path, force: bool) -> int:
    rep, meta, _ = check(target)
    rep.show(f"校验 {target}")
    if not rep.ok:
        print("\n先把上面的 ✗ 改掉再挂。")
        return 1
    name = meta["name"]
    src = _skill_file(target)
    home = kitlib.copilot_home()
    manifest = kitlib.load_json(kitlib.DATA_DIR / "installed.json", {}) or {}
    links = _links()
    if src.name.endswith(".agent.md"):
        dst = home / "agents" / src.name
        if name + ".agent.md" in manifest.get("agents", []):
            print(f"{name} 和工具包自带的代理重名，换个名字。")
            return 1
        if dst.exists() and name not in links and not force:
            print(f"{dst} 已存在且不是用本工具挂的。确认要覆盖就加 --force（会先备份）。")
            return 1
        _backup(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        dst = home / "skills" / name
        if name in manifest.get("skills", []):
            print(f"{name} 和工具包自带的技能重名，换个名字。")
            return 1
        if dst.exists() and name not in links and not force:
            print(f"{dst} 已存在且不是用本工具挂的。确认要覆盖就加 --force（会先备份）。")
            return 1
        _backup(dst)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src.parent, dst, ignore=shutil.ignore_patterns("__pycache__", ".git", ".env*", ".venv"))
    links[name] = {"source": str(target.resolve()), "installed": str(dst), "kind": "agent" if dst.suffix == ".md" else "skill",
                   "ts": kitlib.now()}
    kitlib.save_json(LINKS_PATH, links)
    kit_catalog.build()
    print(f"\n已挂到 {dst}，并登记进能力目录。")
    print("下一步：在 Copilot 会话里输入 /skills reload（代理要重启 Copilot），再用 /skills list 确认能看到；")
    print(f"然后运行 python \"{Path(__file__).resolve()}\" try {name} 看自动匹配效果。")
    print("源目录改了以后再运行一次 add 就会同步过去。")
    return 0


def _backup(path: Path) -> None:
    if not path.exists():
        return
    target = kitlib.DATA_DIR / "backups" / time.strftime("%Y%m%d-%H%M%S") / "user-skills" / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, target, dirs_exist_ok=True)
    else:
        shutil.copy2(path, target)


def _negatives(body: str) -> list[str]:
    m = NEGATIVE_HEAD.search(body)
    if not m:
        return []
    out: list[str] = []
    for line in body[m.end():].splitlines():
        s = line.strip()
        if s.startswith("#"):
            break
        if s.startswith(("-", "*")):
            out.append(s.lstrip("-* ").strip().strip("“”\"'"))
    return out


def try_skill(name_or_dir: str) -> int:
    items = kit_catalog.build()
    target = Path(name_or_dir)
    if target.exists():
        rep, meta, body = check(target)
        rep.show(f"校验 {target}")
        name = meta.get("name", "")
        if name and not any(i["name"] == name for i in items):
            entry = {"name": name, "kind": "skill", "source": "trial", "desc": meta.get("description", "")[:240],
                     "triggers": kit_catalog.triggers_of(body), "writes": False, "path": str(target)}
            items = items + [entry]
    else:
        name = name_or_dir
        found = [i for i in items if i["name"] == name]
        if not found:
            print(f"能力目录里没有 {name}。先 add，或者直接传技能目录路径。")
            return 1
        body = kit_catalog.frontmatter(kitlib.read_text(found[0]["path"]))[1]
    me = next((i for i in items if i["name"] == name), None)
    if not me:
        return 1
    should = me.get("triggers", [])
    shouldnt = _negatives(body)
    print(f"\n== 自动匹配试用：{name} ==")
    if not should:
        print("  没有“## 用户会这样说”，没法试。先补上 3~8 句用户原话。")
        return 1
    hit = 0
    for phrase in should:
        result = kit_catalog.match(phrase, items, top=3)
        top_name = result[0][1]["name"] if result else "（没匹配到）"
        ok = bool(result) and top_name == name
        hit += ok
        others = "、".join(r[1]["name"] for r in result if r[1]["name"] != name)
        print(f"  {'✓' if ok else '✗'} “{phrase}” → {top_name}" + (f"（也像：{others}）" if others else ""))
    wrong = 0
    for phrase in shouldnt:
        result = kit_catalog.match(phrase, items, top=1)
        bad = bool(result) and result[0][1]["name"] == name
        wrong += bad
        print(f"  {'✗' if bad else '✓'} 不该触发：“{phrase}” → {result[0][1]['name'] if result else '（没匹配到）'}")
    print(f"\n  应触发 {hit}/{len(should)}，误触发 {wrong}/{len(shouldnt)}。")
    if hit < len(should):
        print("  没命中的句子：把里面的关键词写进 description，或者换成更像用户原话的说法。")
    if wrong:
        print("  误触发：在 description 里写清“不用于……”，并收窄“用户会这样说”。")
    print("\n本地匹配只是第一层。要看模型实际会不会用，在 Copilot 里用上面任意一句话提问，"
          "看它开头有没有说“我用 " + name + " …”；交付前至少真实试一次。")
    return 0 if hit == len(should) and not wrong else 1


def pack(target: Path, out: Path | None) -> int:
    rep, meta, _ = check(target)
    rep.show(f"校验 {target}")
    if not rep.ok:
        print("\n有 ✗ 的问题，不打包。")
        return 1
    name = meta["name"]
    src = _skill_file(target)
    out = out or (Path.cwd() / f"{name}-{time.strftime('%Y%m%d')}.zip")
    readme = (f"# {name}\n\n{meta.get('description', '')}\n\n## 安装\n"
              f"1. 解压后把 {name}/ 整个目录放到 %USERPROFILE%\\.copilot\\skills\\ 下面（目录名必须是 {name}）。\n"
              "2. 在 Copilot 会话里输入 /skills reload，或者重启 Copilot。\n"
              f"3. 输入 /skills list，能看到 {name} 就装好了。\n"
              "如果装了 ai-dev-kit，也可以直接运行 python tools/kit_skill.py add <解压后的目录>。\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if src.name.endswith(".agent.md"):
            zf.write(src, src.name)
            readme = readme.replace(f"把 {name}/ 整个目录放到 %USERPROFILE%\\.copilot\\skills\\ 下面（目录名必须是 {name}）",
                                    f"把 {src.name} 放到 %USERPROFILE%\\.copilot\\agents\\ 下面").replace("/skills reload，或者重启 Copilot", "重启 Copilot")
        else:
            for p in sorted(src.parent.rglob("*")):
                if p.is_dir() or any(part in SKIP_PARTS for part in p.parts) or p.name.lower().startswith(".env"):
                    continue
                zf.write(p, f"{name}/{p.relative_to(src.parent).as_posix()}")
        zf.writestr("安装说明.md", readme)
    print(f"\n已打包：{out}")
    print("交付前建议：先 add 到本机、try 一次、在 Copilot 里真实用一次。")
    return 0


def list_all() -> int:
    items = kit_catalog.build()
    links = _links()
    if not items:
        print("还没有任何技能或代理。")
    for i in items:
        tag = "工具包" if i["source"] == "kit" else "试用台挂的" if i["name"] in links else "你自己的"
        kind = "代理" if i["kind"] == "agent" else "技能"
        risk = "会改文件" if i.get("writes") else "只读"
        say = "" if i.get("triggers") else "（缺“用户会这样说”）"
        print(f"[{tag}] {kind} {i['name']}  {risk}{say}\n    {i['desc'][:90]}")
    return 0


def remove(name: str) -> int:
    links = _links()
    entry = links.get(name)
    if not entry:
        print(f"{name} 不是用 kit_skill.py add 挂上的，不动它。需要的话手动处理：{kitlib.copilot_home()}")
        return 1
    dst = Path(entry["installed"])
    _backup(dst)
    if dst.is_dir():
        shutil.rmtree(dst)
    elif dst.exists():
        dst.unlink()
    links.pop(name, None)
    kitlib.save_json(LINKS_PATH, links)
    kit_catalog.build()
    print(f"已移除 {dst}（备份在 {kitlib.DATA_DIR / 'backups'}）。源目录 {entry.get('source')} 没动。")
    return 0


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="技能试用台")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("target")
    p = sub.add_parser("add")
    p.add_argument("target")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("try")
    p.add_argument("target")
    p = sub.add_parser("pack")
    p.add_argument("target")
    p.add_argument("--out")
    sub.add_parser("list")
    p = sub.add_parser("remove")
    p.add_argument("name")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        rep, _, _ = check(Path(args.target))
        rep.show(f"校验 {args.target}")
        return 0 if rep.ok else 1
    if args.cmd == "add":
        return add(Path(args.target), args.force)
    if args.cmd == "try":
        return try_skill(args.target)
    if args.cmd == "pack":
        return pack(Path(args.target), Path(args.out) if args.out else None)
    if args.cmd == "list":
        return list_all()
    return remove(args.name)


if __name__ == "__main__":
    sys.exit(main())
