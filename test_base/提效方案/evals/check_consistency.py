"""基准样本：一份真实的 LAS 回归日志（40 个失败用例）+ 12 个人工记录场景，检查判断逻辑有没有被改坏。

标准答案 evals/consistency/expected.json 记录了每个失败用例的分类、规则编号、确认状态、重跑建议、一句话结论、标记，
以及截图观察、截图识别文字、重跑结果、数据核查、人工改判这些场景的结果。
这里固定使用默认规则（config/rules.default.json），不受团队改规则、自定义规则的影响：它检查的是 ta_engine.py 的代码。

用法（在 skill 目录下）：
    python evals/check_consistency.py            全部相同输出“一致”，返回 0；有差异逐条列出，返回 1
    python evals/check_consistency.py --update   确认差异是有意的改进后，用当前结果更新标准答案
ta.py check 会自动运行本检查。
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ta_engine as T  # noqa: E402

HERE = Path(__file__).resolve().parent / "consistency"
FIELDS = ("cat", "rule", "status", "plan", "brief", "flags")


def load_rows(path: Path):
    raw = path.read_text(encoding="utf-8-sig")
    rows = []
    for p in re.split(r"\n(?=\d{1,2}\.\s*\n)", raw)[1:]:
        no = int(re.match(r"^(\d+)\.", p).group(1))
        body = re.sub(r"^\d+\.\s*\n", "", p, count=1)
        body = re.sub(r"\n(?=[_\\])", "", body)
        body = re.sub(r"\s*\n\s*", " ", body).strip()
        rows.append({"CaseId": "No." + str(no), "Name": "", "Result": "Failed" if re.search(r"Traceback|Exception:", body) else "Passed", "Log": body})
    return rows


def pick(c):
    return {"id": c["id"], "cat": c["final"], "rule": c["auto"]["rule"], "status": c["auto"]["status"],
            "plan": c["plan"]["b"], "brief": c["auto"]["brief"], "flags": c["auto"]["flags"]}


def diff(label, got, want, errors):
    for k in FIELDS:
        if got.get(k) != want.get(k):
            errors.append(f"{label} {k}：现在 = {got.get(k)!r}，标准答案 = {want.get(k)!r}")


def run(update=False) -> tuple[int, list[str]]:
    expected = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    rules = T.default_rules()
    rows = load_rows(HERE / "las_hk_20261030_raw.txt")
    mapping = {"id": "CaseId", "name": "Name", "result": "Result", "error": "Log"}
    mk = lambda: T.to_cases(copy.deepcopy(rows), mapping, rules, "R1", 0)
    errors = []

    base = mk()
    T.classify_all(base, rules)
    got = {c["id"]: pick(c) for c in base if c.get("failed")}
    want_ids = [w["id"] for w in expected["base"]]
    if sorted(got) != sorted(want_ids):
        errors.append(f"失败用例不同：现在 {len(got)} 个，标准答案 {len(want_ids)} 个")
    for w in expected["base"]:
        if w["id"] in got:
            diff(w["id"], got[w["id"]], w, errors)

    new_sc = []
    for i, s in enumerate(expected["scenarios"], 1):
        cs = mk()
        target = next(c for c in cs if c["id"] == s["id"])
        target.update(copy.deepcopy(s["patch"]))
        T.classify_all(cs, rules)
        p = pick(target)
        diff(f"场景{i}（{s['id']} {json.dumps(s['patch'], ensure_ascii=False)}）", p, s["expect"], errors)
        new_sc.append(dict(s, expect=p))

    if update:
        expected["base"] = [got[i] for i in sorted(got, key=lambda x: int(x.split(".")[1]))]
        expected["scenarios"] = new_sc
        (HERE / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(expected["base"]) + len(expected["scenarios"]), errors


def main() -> int:
    upd = "--update" in sys.argv
    n, errors = run(upd)
    if upd:
        print(f"已用当前结果更新标准答案（{len(errors)} 处变化）")
        return 0
    if errors:
        print(f"不一致：{len(errors)} 处（共检查 {n} 项）")
        for e in errors:
            print(" -", e)
        return 1
    print(f"一致：{n} 项与标准答案相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
