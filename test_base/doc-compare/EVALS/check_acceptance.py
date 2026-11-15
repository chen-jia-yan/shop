"""验收：用以前人工确认过的差异做标准答案，检查新对比一条不漏。

用法：
    python evals/check_acceptance.py --result <batch 结果文件夹（含 summary.json）> --golden evals/golden.csv

golden.csv（UTF-8，可以用 Excel 另存为“CSV UTF-8”）：
    case,old,new,note
    Case5,UXP3 587.85,UXP3 600.00,保费变化
    Case7,,新增条款 ABC,新文件多出一段
  old / new 填差异里的一段原文（不用整行），只有一边的差异另一边留空。

结果：
  - 漏掉的：标准答案里有、对比结果的“真实差异 / 不确定”里没有。必须为 0 才能替换现有做法。
  - 多出的：对比结果里有、标准答案里没有的真实差异，请同事A 逐条看：是以前漏掉的真差异，还是需要加过滤规则。
全部找到时返回 0，否则返回 1。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from pathlib import Path


def norm(s: str) -> str:
    return "".join(unicodedata.normalize("NFKC", s or "").split()).replace(",", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--golden", required=True)
    args = ap.parse_args()
    root = Path(args.result)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    results = {}
    for r in summary["cases"]:
        if r.get("dir"):
            results[r["case"]] = json.loads((root / r["dir"] / "result.json").read_text(encoding="utf-8"))

    golden = list(csv.DictReader(Path(args.golden).open(encoding="utf-8-sig")))
    missing, hit = [], {}
    for g in golden:
        res = results.get(g["case"])
        if res is None:
            missing.append((g, "这个 Case 没有对比结果"))
            continue
        go, gn = norm(g.get("old")), norm(g.get("new"))
        found = [it for it in res["items"] if it["status"] in ("real", "unsure")
                 and (not go or go in norm("".join(it["old"]))) and (not gn or gn in norm("".join(it["new"])))]
        if found:
            for it in found:
                hit[(g["case"], it["id"])] = True
        else:
            near = [it["id"] for it in res["items"] if it["status"] in ("ignored", "layout")
                    and (not go or go in norm("".join(it["old"]))) and (not gn or gn in norm("".join(it["new"])))]
            missing.append((g, f"被归为已忽略或位置变化：{', '.join(near)}" if near else "对比结果里找不到"))

    extra = [(c, it) for c, res in results.items() for it in res["items"] if it["status"] == "real" and (c, it["id"]) not in hit]
    print(f"标准答案 {len(golden)} 条：找到 {len(golden) - len(missing)} 条，漏掉 {len(missing)} 条")
    for g, why in missing:
        print(f"  漏掉 {g['case']}：{g.get('old') or '（无）'} → {g.get('new') or '（无）'}（{why}）")
    print(f"标准答案以外的真实差异 {len(extra)} 条（请逐条确认）：")
    for c, it in extra[:200]:
        print(f"  {c} {it['id']}：{' / '.join(it['old']) or '（无）'} → {' / '.join(it['new']) or '（无）'}")
    if len(extra) > 200:
        print(f"  ……还有 {len(extra) - 200} 条，见各 Case 的 ignore.html")
    print("验收通过：一条不漏" if not missing else "验收未通过：有漏掉的差异，不能替换现有做法")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
