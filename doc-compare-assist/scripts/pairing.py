"""选文件：扫描 baseline、新文件两个文件夹，按文件名里的 Case 编号配对，生成可以在 Excel 里勾选的 pairs.csv。"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from common import safe_name

COLS = ["选中", "Case", "baseline", "新文件", "备注"]


def list_pdfs(folder, recursive=False) -> list[Path]:
    d = Path(folder)
    if not d.is_dir():
        raise SystemExit(f"文件夹不存在：{d}")
    it = d.rglob("*") if recursive else d.iterdir()
    return sorted(p for p in it if p.is_file() and p.suffix.lower() == ".pdf")


def key_of(path: Path, key_regex: str) -> str:
    m = re.search(key_regex, path.stem, re.I) if key_regex else None
    if m:
        return re.sub(r"\s+", "", m.group(1) if m.groups() else m.group(0))
    return path.stem


def make_pairs(baseline_dir, new_dir, cfg: dict) -> list[dict]:
    pc = cfg["pairing"]
    a, b = defaultdict(list), defaultdict(list)
    for p in list_pdfs(baseline_dir, pc.get("recursive")):
        a[key_of(p, pc["key_regex"])].append(p)
    for p in list_pdfs(new_dir, pc.get("recursive")):
        b[key_of(p, pc["key_regex"])].append(p)
    pairs = []
    for k in sorted(set(a) | set(b), key=_natural):
        ra, rb = a.get(k, []), b.get(k, [])
        note, sel = "", True
        if not ra:
            note, sel = "baseline 里没有对应文件", False
        elif not rb:
            note, sel = "新文件里没有对应文件", False
        elif len(ra) > 1 or len(rb) > 1:
            note, sel = f"同一个编号有多个文件（baseline {len(ra)} 个、新文件 {len(rb)} 个），请在 csv 里改成一对一", False
        pairs.append({
            "key": k, "dir": safe_name(k), "selected": sel, "note": note,
            "baseline": str(ra[0]) if ra else "", "new": str(rb[0]) if rb else "",
            "baseline_all": [str(x) for x in ra], "new_all": [str(x) for x in rb],
            "files": {}, "status": "待对比", "error": "",
        })
    return pairs


def _natural(s: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def write_csv(path, pairs) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for p in pairs:
            base = p["baseline"] or " | ".join(p["baseline_all"])
            new = p["new"] or " | ".join(p["new_all"])
            w.writerow(["Y" if p["selected"] else "N", p["key"], base, new, p["note"]])


def apply_csv(path, pairs) -> list[dict]:
    """读回用户改过的 pairs.csv：选中列 Y/N；baseline、新文件两列可以改成别的路径；也可以新增行。"""
    by_key = {p["key"]: p for p in pairs}
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = (row.get("Case") or "").strip()
            if not k:
                continue
            p = by_key.get(k) or {"key": k, "dir": safe_name(k), "files": {}, "status": "待对比", "error": "",
                                  "baseline_all": [], "new_all": []}
            p["selected"] = (row.get("选中") or "").strip().upper() in ("Y", "YES", "1", "是", "√", "✓")
            p["baseline"] = (row.get("baseline") or "").strip()
            p["new"] = (row.get("新文件") or "").strip()
            p["note"] = (row.get("备注") or "").strip()
            if p["selected"]:
                for side in ("baseline", "new"):
                    if not p[side] or "|" in p[side] or not Path(p[side]).is_file():
                        p["selected"] = False
                        p["note"] = f"{'baseline' if side == 'baseline' else '新文件'}路径无效：{p[side] or '空'}"
            out.append(p)
    return out
