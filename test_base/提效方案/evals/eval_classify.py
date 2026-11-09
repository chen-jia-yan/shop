"""检验分类规则的准确率：把 classify_rules.py 的结果与人工标注对比。

用法：
    python evals/eval_classify.py --classified triage_runs/<run_id>/classified.json \
        --labels evals/labeled_cases.csv [--min-accuracy 0.8] [--max-critical-miss 0.05]

labeled_cases.csv 格式（UTF-8，第一行为表头）：
    case_id,human_category,note
    Case7,PRODUCT_DEFECT,已查数据库 agent 40100 正常

human_category 可以填英文代码或中文名（见 references/taxonomy.md）。

输出：
- 总体准确率（只统计规则给出 confirmed 的用例，以及全部用例两个口径）
- 混淆矩阵
- 关键漏判率：人工判定为 PRODUCT_DEFECT，但规则分到了其他非“需人工判断”类别的比例
- 每条规则的准确率，便于找出需要修改的规则
达不到 --min-accuracy 或超过 --max-critical-miss 时以退出码 1 结束，可接入 CI。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import CATEGORIES, read_json  # noqa: E402

CN_TO_CODE = {v: k for k, v in CATEGORIES.items()}


def load_labels(path: str) -> dict[str, str]:
    labels = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = (row.get("human_category") or "").strip()
            code = raw if raw in CATEGORIES else CN_TO_CODE.get(raw)
            if not code:
                print(f"[警告] {row.get('case_id')} 的标注 {raw!r} 不是有效类别，已忽略")
                continue
            labels[row["case_id"].strip()] = code
    return labels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classified", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--min-accuracy", type=float, default=0.8)
    ap.add_argument("--max-critical-miss", type=float, default=0.05)
    args = ap.parse_args()

    cases = {c["case_id"]: c for c in read_json(args.classified)["cases"]}
    labels = load_labels(args.labels)
    common_ids = [cid for cid in labels if cid in cases]
    if not common_ids:
        print("没有可对比的用例（case_id 对不上）")
        sys.exit(1)

    confusion = defaultdict(Counter)
    per_rule = defaultdict(lambda: [0, 0])
    correct_all = correct_conf = n_conf = 0
    defects = critical_miss = 0
    wrong = []
    for cid in common_ids:
        pred, truth = cases[cid]["category"], labels[cid]
        rule, status = cases[cid]["rule_id"], cases[cid]["status"]
        confusion[truth][pred] += 1
        per_rule[rule][1] += 1
        if pred == truth:
            correct_all += 1
            per_rule[rule][0] += 1
        else:
            wrong.append((cid, truth, pred, rule, status))
        if status == "confirmed":
            n_conf += 1
            correct_conf += pred == truth
        if truth == "PRODUCT_DEFECT":
            defects += 1
            if pred not in ("PRODUCT_DEFECT", "NEEDS_HUMAN"):
                critical_miss += 1

    n = len(common_ids)
    acc_all = correct_all / n
    acc_conf = correct_conf / n_conf if n_conf else 0.0
    miss_rate = critical_miss / defects if defects else 0.0
    human_rate = sum(1 for cid in common_ids if cases[cid]["category"] == "NEEDS_HUMAN") / n

    print(f"对比用例：{n}（标注 {len(labels)}，分类结果 {len(cases)}）")
    print(f"全部用例准确率：{acc_all:.1%}")
    print(f"confirmed 用例准确率：{acc_conf:.1%}（{n_conf} 个）")
    print(f"需人工判断比例：{human_rate:.1%}")
    print(f"关键漏判率（真实缺陷被分到其他类）：{miss_rate:.1%}（{critical_miss}/{defects}）")

    cats = list(CATEGORIES)
    print("\n混淆矩阵（行 = 人工标注，列 = 规则分类）")
    print("".ljust(20) + "".join(c[:10].ljust(11) for c in cats))
    for t in cats:
        if confusion[t]:
            print(t.ljust(20) + "".join(str(confusion[t][p]).ljust(11) for p in cats))

    print("\n各规则准确率")
    for rule, (ok, total) in sorted(per_rule.items(), key=lambda x: x[1][0] / x[1][1]):
        print(f"  {rule:<14} {ok}/{total}  {ok / total:.0%}")

    if wrong:
        print("\n分错的用例")
        for cid, truth, pred, rule, status in wrong:
            print(f"  {cid}: 人工 {truth} / 规则 {pred}（{rule}, {status}）")

    failed = acc_conf < args.min_accuracy or miss_rate > args.max_critical_miss
    if failed:
        print(f"\n未达标：confirmed 准确率需 >= {args.min_accuracy:.0%}，关键漏判率需 <= {args.max_critical_miss:.0%}")
        sys.exit(1)
    print("\n达标")


if __name__ == "__main__":
    main()
