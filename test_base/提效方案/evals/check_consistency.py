"""检查 skill 的分析结果和“测试分析助手”页面是否完全一致。

标准答案 evals/consistency/expected.json 是页面（engine.js）对同一份日志算出来的结果：
40 个失败用例的分类、规则编号、确认状态、重跑建议、一句话结论、标记，以及 12 个人工记录场景
（截图观察、截图识别文字、重跑结果、数据核查、人工改判）。

用法（在 skill 目录下）：
    python evals/check_consistency.py
全部一致时输出“一致”并返回 0；有差异时逐条列出并返回 1。
修改 engine.js 或 scripts/ta_engine.py 之后都要运行一次。
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
    """与页面导出标准答案时的解析方式相同。"""
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
            errors.append(f"{label} {k}：skill = {got.get(k)!r}，页面 = {want.get(k)!r}")


def main() -> int:
    expected = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    rules = T.load_rules()
    rows = load_rows(HERE / "las_hk_20261030_raw.txt")
    mapping = {"id": "CaseId", "name": "Name", "result": "Result", "error": "Log"}
    mk = lambda: T.to_cases(copy.deepcopy(rows), mapping, rules, "R1", 0)
    errors = []

    if len(rules) != 31:
        errors.append(f"config/rules.json 有 {len(rules)} 项规则，页面默认是 31 项；请从页面重新导出规则")

    base = mk()
    T.classify_all(base, rules)
    got = {c["id"]: pick(c) for c in base if c.get("failed")}
    want_ids = [w["id"] for w in expected["base"]]
    if sorted(got) != sorted(want_ids):
        errors.append(f"失败用例不同：skill {len(got)} 个，页面 {len(want_ids)} 个；只在 skill：{sorted(set(got) - set(want_ids))}；只在页面：{sorted(set(want_ids) - set(got))}")
    for w in expected["base"]:
        if w["id"] in got:
            diff(w["id"], got[w["id"]], w, errors)

    for i, s in enumerate(expected["scenarios"], 1):
        cs = mk()
        target = next(c for c in cs if c["id"] == s["id"])
        target.update(copy.deepcopy(s["patch"]))
        T.classify_all(cs, rules)
        diff(f"场景{i}（{s['id']} {json.dumps(s['patch'], ensure_ascii=False)}）", pick(target), s["expect"], errors)

    n = len(expected["base"]) + len(expected["scenarios"])
    if errors:
        print(f"不一致：{len(errors)} 处（共检查 {n} 项）")
        for e in errors:
            print(" -", e)
        return 1
    print(f"一致：{len(expected['base'])} 个失败用例 + {len(expected['scenarios'])} 个人工记录场景，与页面结果完全相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
