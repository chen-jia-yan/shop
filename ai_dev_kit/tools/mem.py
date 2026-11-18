"""记忆系统：把"踩过的坑、做过的决定、团队约定"变成可验证、可检索、可淘汰的记录。

设计依据（详见 docs/05-记忆系统.md）：
- 存成人能读、能改、能进版本库的 Markdown 文件，一条一个文件，多人协作不冲突；
- 每条记忆带"引用"（文件:行号#锚点文字），使用前当场核对引用是否还成立，
  这是 GitHub Copilot Memory 公开的做法（存的时候带出处，用的时候即时验证）；
- 会话开始只注入少量高优先级、已验证的记忆，其余按需检索，控制 token；
- 有"取代""过期""归档"机制，旧知识不会一直堆在那里误导模型。

用法：
    python mem.py add --project tap-ai-backend --type lesson --subject "..." --fact "..." \
        --why "..." --how "..." --cite "src/a.py:12#关键字" --tags "导入,循环"
    python mem.py search "循环导入" [--project P]
    python mem.py list [--project P] [--status active]
    python mem.py verify [--project P] [--write]
    python mem.py show ID
    python mem.py supersede OLD_ID --by NEW_ID
    python mem.py archive ID
    python mem.py prune [--days 30] [--write]
    python mem.py stats
    python mem.py digest --project P        # 预览会话开始时会注入的内容
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import kitlib

MEMORY_DIR = kitlib.KIT_ROOT / "memory"
ARCHIVE_DIR = MEMORY_DIR / "_archive"
GLOBAL = "_global"
TYPES = {
    "lesson": "教训",
    "decision": "决定",
    "convention": "约定",
    "fact": "事实",
    "preference": "偏好",
}
PRIORITY_WEIGHT = {"high": 3.0, "normal": 1.5, "low": 0.5}
SUBJECT_MAX = 60
FACT_MAX = 400


@dataclass
class Memory:
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or self.path.stem)

    @property
    def project(self) -> str:
        return str(self.meta.get("project") or GLOBAL)

    @property
    def status(self) -> str:
        return str(self.meta.get("status") or "active")

    @property
    def citations(self) -> list[str]:
        cites = self.meta.get("citations") or []
        return cites if isinstance(cites, list) else [str(cites)]

    @property
    def fact(self) -> str:
        m = re.search(r"(?m)^事实[:：]\s*(.+)$", self.body)
        if m:
            return m.group(1).strip()
        first = next((ln.strip() for ln in self.body.splitlines() if ln.strip()), "")
        return first


# ---------------------------------------------------------------- 读写


def parse(path: Path) -> Memory:
    text = kitlib.read_text(path)
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        header = parts[0][3:]
        body = parts[1].lstrip("-").lstrip("\n") if len(parts) > 1 else ""
        current_list: str | None = None
        for line in header.splitlines():
            if not line.strip():
                continue
            if line.lstrip().startswith("- ") and current_list:
                meta.setdefault(current_list, []).append(line.lstrip()[2:].strip())
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value == "":
                    current_list = key
                    meta[key] = []
                else:
                    current_list = None
                    meta[key] = value
    return Memory(path, meta, body.strip())


def render(mem: Memory) -> str:
    order = ["id", "type", "project", "subject", "tags", "status", "priority", "created",
             "verified", "expires", "supersedes", "superseded_by", "source"]
    lines = ["---"]
    for key in order:
        if key in mem.meta and mem.meta[key] not in (None, ""):
            lines.append(f"{key}: {mem.meta[key]}")
    for key, value in mem.meta.items():
        if key not in order and key != "citations" and not isinstance(value, list):
            lines.append(f"{key}: {value}")
    lines.append("citations:")
    for cite in mem.citations:
        lines.append(f"  - {cite}")
    lines.append("---")
    lines.append(mem.body.strip())
    return "\n".join(lines) + "\n"


def save(mem: Memory) -> None:
    kitlib.write_text(mem.path, render(mem))


def load_all(project: str | None = None, include_archive: bool = False) -> list[Memory]:
    items: list[Memory] = []
    if not MEMORY_DIR.is_dir():
        return items
    for path in sorted(MEMORY_DIR.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        if not include_archive and ARCHIVE_DIR in path.parents:
            continue
        try:
            m = parse(path)
        except Exception:
            continue
        if project and m.project not in {project, GLOBAL}:
            continue
        items.append(m)
    return items


def find(mem_id: str) -> Memory | None:
    for m in load_all(include_archive=True):
        if m.id == mem_id:
            return m
    return None


# ---------------------------------------------------------------- 引用核对

CITE_RE = re.compile(r"^(?P<path>.+?)(?::(?P<line>\d+))?(?:#(?P<anchor>.+))?$")


def project_root(project: str) -> Path:
    if project == GLOBAL:
        return kitlib.KIT_ROOT
    proj = kitlib.get_project(kitlib.load_config(), project)
    if proj and proj.get("path"):
        return Path(proj["path"])
    return kitlib.KIT_ROOT


def check_citation(cite: str, root: Path) -> tuple[str, str]:
    """返回 (状态, 说明)。状态：ok / moved / stale / missing / user（来自用户口述，无法核对）。"""
    cite = cite.strip()
    if cite.startswith(("user:", "用户:", "用户：")):
        return "user", "来自用户说明"
    m = CITE_RE.match(cite)
    if not m:
        return "stale", "引用格式不对"
    path = root / m.group("path").strip()
    if not path.is_file():
        return "missing", f"文件不存在：{m.group('path')}"
    anchor = (m.group("anchor") or "").strip()
    if not anchor:
        return "ok", "文件存在"
    try:
        lines = kitlib.read_text(path).splitlines()
    except OSError as exc:
        return "stale", f"读不了文件：{exc}"
    line_no = int(m.group("line") or 0)
    if line_no:
        lo, hi = max(0, line_no - 21), min(len(lines), line_no + 20)
        if any(anchor in ln for ln in lines[lo:hi]):
            return "ok", "锚点仍在原位置附近"
    for idx, ln in enumerate(lines, start=1):
        if anchor in ln:
            return "moved", f"锚点移到了第 {idx} 行"
    return "stale", f"找不到锚点文字：{anchor}"


def verify_memory(mem: Memory) -> tuple[str, list[str]]:
    """一条记忆的总体状态：任何一个引用失效，就是 stale。"""
    root = project_root(mem.project)
    notes: list[str] = []
    overall = "ok"
    for cite in mem.citations:
        status, note = check_citation(cite, root)
        notes.append(f"{cite} → {status}（{note}）")
        if status in {"stale", "missing"}:
            overall = "stale"
    if not mem.citations:
        overall = "uncited"
    return overall, notes


# ---------------------------------------------------------------- 检索


def tokens(text: str) -> list[str]:
    """英文按词，中文按相邻两字切分（离线也能做像样的中文检索）。"""
    text = text.lower()
    words = re.findall(r"[a-z0-9_.\-]{2,}", text)
    cjk = re.findall("[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for run in cjk:
        if len(run) == 1:
            grams.append(run)
        grams.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words + grams


def score(mem: Memory, query_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0
    fields = {
        "subject": (str(mem.meta.get("subject", "")), 3.0),
        "tags": (str(mem.meta.get("tags", "")), 2.0),
        "body": (mem.body, 1.0),
    }
    total = 0.0
    for text, weight in fields.values():
        bag = tokens(text)
        if not bag:
            continue
        for qt in set(query_tokens):
            hits = bag.count(qt)
            if hits:
                total += weight * (1 + math.log(hits))
    total *= PRIORITY_WEIGHT.get(str(mem.meta.get("priority", "normal")), 1.0) / 1.5
    return total


def search(query: str, project: str | None = None, limit: int = 8) -> list[tuple[float, Memory]]:
    qt = tokens(query)
    ranked = [(score(m, qt), m) for m in load_all(project) if m.status == "active"]
    ranked = [r for r in ranked if r[0] > 0]
    ranked.sort(key=lambda r: (-r[0], r[1].id))
    return ranked[:limit]


def _short_cite(cites: list[str]) -> str:
    if not cites:
        return ""
    first = cites[0].split("#", 1)[0]
    return f"（见 {first}{' 等' if len(cites) > 1 else ''}）"


def digest(project: str | None, project_path: str | None = None,
           max_chars: int = 1200, max_items: int = 8) -> str:
    """会话开始时注入的摘要：只要 active、引用核对通过的条目，按优先级和核对日期排序。"""
    candidates = [m for m in load_all(project) if m.status == "active"]
    if project is None:
        candidates = [m for m in candidates if m.project == GLOBAL]
    # 先按核对日期从新到旧，再按优先级从高到低（排序是稳定的，所以优先级相同时新的在前）
    candidates.sort(key=lambda m: str(m.meta.get("verified", "")), reverse=True)
    candidates.sort(key=lambda m: -PRIORITY_WEIGHT.get(str(m.meta.get("priority", "normal")), 1.0))
    lines: list[str] = []
    used = 0
    for m in candidates:
        if len(lines) >= max_items:
            break
        state, _ = verify_memory(m)
        if state == "stale":
            continue
        label = TYPES.get(str(m.meta.get("type", "")), "记忆")
        line = f"- [{label}] {m.meta.get('subject', m.id)}：{m.fact}{_short_cite(m.citations)}"
        if len(line) > 220:
            line = line[:217] + "…"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


# ---------------------------------------------------------------- 命令

_SECRET_HINT = re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token)\s*[=:]\s*\S+|[a-z]+://[^:\s]+:[^@\s]+@|\bsk-[A-Za-z0-9]{16,}")


def _slug(text: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if ascii_part:
        return ascii_part[:40]
    return "m" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def cmd_add(args: argparse.Namespace) -> int:
    project = args.project or GLOBAL
    if args.type not in TYPES:
        print(f"类型只能是：{', '.join(TYPES)}")
        return 2
    subject = args.subject.strip()
    fact = args.fact.strip()
    if not subject or not fact:
        print("subject 和 fact 都不能为空。")
        return 2
    if len(subject) > SUBJECT_MAX:
        print(f"subject 太长（{len(subject)} 字），请控制在 {SUBJECT_MAX} 字内：一句话说清是什么。")
        return 2
    if len(fact) > FACT_MAX:
        print(f"fact 太长（{len(fact)} 字），请控制在 {FACT_MAX} 字内；细节放进 --why / --how。")
        return 2
    joined = " ".join([subject, fact, args.why or "", args.how or ""] + list(args.cite or []))
    if _SECRET_HINT.search(joined):
        print("拒绝保存：内容里像是有密码、密钥或带口令的连接串。记忆里绝对不能存密钥。")
        return 2
    if not args.cite and args.type in {"lesson", "convention", "fact"}:
        print("提醒：这条记忆没有引用。没有引用就无法自动核对，建议加 --cite \"路径:行号#锚点文字\"；"
              "如果来自用户口述，用 --cite \"user:日期 用户说明\"。")
    similar = search(subject + " " + fact, project=project if project != GLOBAL else None, limit=3)
    if similar and similar[0][0] >= 6:
        print("发现内容相近的已有记忆，请确认不是重复（如果是更新，用 supersede 取代旧条目）：")
        for s, m in similar:
            print(f"  {m.id}（相似度 {s:.1f}）：{m.meta.get('subject')}")
        if not args.force:
            print("加 --force 仍然保存。")
            return 3
    mem_id = f"{kitlib.today()}-{_slug(args.id or subject)}"
    target = MEMORY_DIR / project / f"{mem_id}.md"
    n = 2
    while target.exists():
        target = MEMORY_DIR / project / f"{mem_id}-{n}.md"
        n += 1
    body_lines = [f"事实：{fact}"]
    if args.why:
        body_lines.append(f"原因：{args.why.strip()}")
    if args.how:
        body_lines.append(f"怎么用：{args.how.strip()}")
    mem = Memory(target, {
        "id": target.stem, "type": args.type, "project": project, "subject": subject,
        "tags": args.tags or "", "status": "active", "priority": args.priority,
        "created": kitlib.today(), "verified": kitlib.today(), "source": args.source or "",
        "citations": list(args.cite or []),
    }, "\n".join(body_lines))
    state, notes = verify_memory(mem)
    if state == "stale":
        print("引用核对失败，未保存：")
        for note in notes:
            print("  " + note)
        return 4
    save(mem)
    print(f"已保存：{target}")
    for note in notes:
        print("  " + note)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    items = load_all(args.project, include_archive=args.all)
    if args.status:
        items = [m for m in items if m.status == args.status]
    for m in items:
        print(f"{m.id} [{m.project}/{m.meta.get('type')}/{m.status}/{m.meta.get('priority', 'normal')}] {m.meta.get('subject')}")
    print(f"共 {len(items)} 条。")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    results = search(args.query, args.project, args.limit)
    if not results:
        print("没有找到相关记忆。")
        return 0
    for s, m in results:
        print(f"{m.id}（{s:.1f}）[{TYPES.get(str(m.meta.get('type')), '')}] {m.meta.get('subject')}")
        print(f"    {m.fact}")
        if m.citations:
            print(f"    引用：{'；'.join(m.citations)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    m = find(args.id)
    if not m:
        print("找不到这条记忆。")
        return 1
    print(render(m))
    state, notes = verify_memory(m)
    print(f"核对结果：{state}")
    for note in notes:
        print("  " + note)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    items = [m for m in load_all(args.project) if m.status in {"active", "stale"}]
    counts: dict[str, int] = {}
    for m in items:
        state, notes = verify_memory(m)
        counts[state] = counts.get(state, 0) + 1
        if state != "ok":
            print(f"{m.id} → {state}")
            for note in notes:
                print("    " + note)
        if args.write:
            if state == "stale" and m.status == "active":
                m.meta["status"] = "stale"
                save(m)
            elif state in {"ok", "uncited"}:
                m.meta["verified"] = kitlib.today()
                if m.status == "stale":
                    m.meta["status"] = "active"
                save(m)
    summary = "，".join(f"{k} {v} 条" for k, v in sorted(counts.items()))
    print(f"核对 {len(items)} 条：{summary or '无'}。" + ("" if args.write else "（加 --write 才会更新状态）"))
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    old, new = find(args.old), find(args.by)
    if not old or not new:
        print("找不到对应的记忆。")
        return 1
    old.meta["status"] = "superseded"
    old.meta["superseded_by"] = new.id
    new.meta["supersedes"] = old.id
    save(old)
    save(new)
    print(f"{old.id} 已被 {new.id} 取代。")
    return 0


def _archive(m: Memory) -> Path:
    target = ARCHIVE_DIR / m.project / m.path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    m.meta["archived"] = kitlib.today()
    save(m)
    shutil.move(str(m.path), str(target))
    return target


def cmd_archive(args: argparse.Namespace) -> int:
    m = find(args.id)
    if not m:
        print("找不到这条记忆。")
        return 1
    print(f"已归档到：{_archive(m)}")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    cutoff = time.time() - args.days * 86400
    picked: list[Memory] = []
    for m in load_all():
        expires = str(m.meta.get("expires", ""))
        expired = bool(expires) and expires < kitlib.today()
        old_stale = m.status in {"stale", "superseded"} and m.path.stat().st_mtime < cutoff
        if expired or old_stale:
            picked.append(m)
    for m in picked:
        print(f"{'归档' if args.write else '将归档'}：{m.id}（{m.status}）")
        if args.write:
            _archive(m)
    print(f"共 {len(picked)} 条。" + ("" if args.write else "（加 --write 才会执行）"))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    items = load_all(include_archive=True)
    by: dict[tuple[str, str], int] = {}
    for m in items:
        by[(m.project, m.status)] = by.get((m.project, m.status), 0) + 1
    for (proj, status), n in sorted(by.items()):
        print(f"{proj:<24} {status:<11} {n}")
    print(f"总计 {len(items)} 条。")
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    proj = kitlib.get_project(kitlib.load_config(), args.project) if args.project else None
    text = digest(args.project, proj.get("path") if proj else None, args.max_chars, args.max_items)
    print(text or "（没有可注入的记忆）")
    print(f"\n——共 {len(text)} 字")
    return 0


def main(argv: list[str] | None = None) -> int:
    kitlib.setup_console()
    parser = argparse.ArgumentParser(description="ai-dev-kit 记忆系统")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="新增一条记忆")
    p.add_argument("--project", help="项目名；不填表示全局")
    p.add_argument("--type", required=True, choices=sorted(TYPES))
    p.add_argument("--subject", required=True, help="一句话主题（≤60 字）")
    p.add_argument("--fact", required=True, help="事实本身（≤400 字）")
    p.add_argument("--why", help="为什么重要")
    p.add_argument("--how", help="以后遇到时怎么做")
    p.add_argument("--cite", action="append", help="引用：路径:行号#锚点文字，可多次")
    p.add_argument("--tags", default="")
    p.add_argument("--priority", default="normal", choices=["high", "normal", "low"])
    p.add_argument("--source", help="来源，如：修1b 事故、用户 11-02 确认")
    p.add_argument("--id", help="自定义英文短名")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list")
    p.add_argument("--project")
    p.add_argument("--status")
    p.add_argument("--all", action="store_true", help="包含已归档")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("verify")
    p.add_argument("--project")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("supersede")
    p.add_argument("old")
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_supersede)

    p = sub.add_parser("archive")
    p.add_argument("id")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("prune")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("digest")
    p.add_argument("--project")
    p.add_argument("--max-chars", type=int, default=1200)
    p.add_argument("--max-items", type=int, default=8)
    p.set_defaults(func=cmd_digest)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
