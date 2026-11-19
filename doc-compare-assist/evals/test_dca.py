"""测试：读差异、字段名、变化部分、配对、读回 pairs.csv。只用 Python 自带的库，不需要 PDF。

运行：python evals/test_dca.py   应输出“全部通过”。改过 scripts/ 里的读取逻辑后运行一次。
"""
import difflib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_parse  # noqa: E402
import pairing  # noqa: E402
from common import DEFAULTS, deep_merge  # noqa: E402

CFG = deep_merge(DEFAULTS, {})
fails = []
try:
    sys.stdout.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  → {detail}"))
    if not cond:
        fails.append(name)


A = ["保單資料", "Policy Date : 06 Nov 2026", "Premium : 587.85", "Plan : BZ600", "Same line", "到期日 2046 11 06"]
B = ["保單資料", "Policy Date : 06 Nov 2026", "Premium : 600.00", "Plan : BZ600", "Same line", "到期日 2046 11 20", "New line added"]

print("difflib.HtmlDiff 整页（make_file）")
html = difflib.HtmlDiff().make_file(A, B, "page0", "page0")
items = diff_parse.finish(diff_parse.parse_htmldiff(html), CFG)
check("读出 3 条变化（改 2 条、新增 1 条）", len(items) == 3, [(i["old"], i["new"]) for i in items])
prem = next((i for i in items if "587.85" in i["old"]), None)
check("保费那一行原值、新值照抄", prem and prem["old"] == "Premium : 587.85" and prem["new"] == "Premium : 600.00", prem)
check("字段名取冒号前面", prem and prem["field"] == "Premium", prem and prem["field"])
check("变化写成 587.85 → 600.00", prem and prem["change"] == "587.85 → 600.00", prem and prem["change"])
check("只框变化的词", prem and prem["tok_old"] == ["587.85"] and prem["tok_new"] == ["600.00"], prem and (prem["tok_old"], prem["tok_new"]))
check("行号", prem and prem["line_old"] == 3 and prem["line_new"] == 3, prem and (prem["line_old"], prem["line_new"]))
check("表头 page0 当成第 1 页", prem and prem["page_old"] == 1, prem and prem["page_old"])
add = next((i for i in items if i["new"] == "New line added"), None)
check("新增行：类型是新增、原值为空", add and add["kind"] == "新增" and add["old"] == "", add)
check("图例表里的 Added/Changed 不当成差异", not any("Added" in i["new"] and "New" not in i["new"] for i in items))

print("difflib.HtmlDiff 只显示变化附近（make_table context=True）和折行")
long_a = ["x"] * 20 + ["Benefit : " + "A" * 30 + " 100"] + ["y"] * 20
long_b = ["x"] * 20 + ["Benefit : " + "A" * 30 + " 200"] + ["y"] * 20
tbl = difflib.HtmlDiff(wrapcolumn=20).make_table(long_a, long_b, context=True, numlines=2)
it2 = diff_parse.finish(diff_parse.parse_htmldiff(tbl), CFG)
check("折行拼回一行", len(it2) == 1 and it2[0]["old"].endswith("100") and it2[0]["new"].endswith("200"), [(i["old"], i["new"]) for i in it2])
check("折行后行号不变", it2 and it2[0]["line_old"] == 21, it2 and it2[0]["line_old"])

print("只差空格")
sp = diff_parse.finish([{"old": "Sum Assured :  1,000", "new": "Sum Assured : 1,000"}], CFG)
check("标成只差空格", sp[0]["space_only"] is True)

print("字段名")
check("10:30 这种时间不当字段名", diff_parse.field_of("10:30 AM", "11:30 AM") == "")
check("全角冒号", diff_parse.field_of("保單生效日 ：2026年11月06日", "保單生效日 ：2026年11月20日") == "保單生效日")

print("一行旧、一行新的文字格式")
li = diff_parse.parse_lines(["- Premium : 587.85", "+ Premium : 600.00", "- 删掉的行", "+ 新加的行", "+ 又一行"],
                            CFG["difference"]["old_line"], CFG["difference"]["new_line"])
check("配成 3 条", len(li) == 3, li)
check("第 3 条是只有新值", li[2]["old"] == "" and li[2]["new"] == "又一行", li[2])
txt = diff_parse.text_lines("<html><body><p>- a</p><p>+ b</p><br>+ c</body></html>", True)
check("html 转成按行文字", txt == ["- a", "+ b", "+ c"], txt)

print("配对和 pairs.csv")
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "base").mkdir()
    (d / "new").mkdir()
    for n in ("Case7_PolSchedule-BZ600_72624_20261106.pdf", "Case12_PolSchedule_1.pdf", "Case3_x.pdf"):
        (d / "base" / n).write_bytes(b"%PDF-1.4")
    for n in ("Case7_PolSchedule-BZ600_72624_20261120.pdf", "Case12_PolSchedule_2.pdf"):
        (d / "new" / n).write_bytes(b"%PDF-1.4")
    pairs = pairing.make_pairs(d / "base", d / "new", CFG)
    keys = [p["key"] for p in pairs]
    check("按 Case 编号配对、自然排序", keys == ["Case3", "Case7", "Case12"], keys)
    check("Case7 日期不同也能配上", pairs[1]["selected"] and pairs[1]["new"].endswith("20261120.pdf"))
    check("缺新文件的不选中并写明原因", not pairs[0]["selected"] and "新文件" in pairs[0]["note"], pairs[0])
    pairing.write_csv(d / "pairs.csv", pairs)
    text = (d / "pairs.csv").read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    text = [l.replace("Y,Case12", "N,Case12", 1) if l.startswith("Y,Case12") else l for l in text]
    (d / "pairs.csv").write_text("\n".join(text), encoding="utf-8-sig")
    back = pairing.apply_csv(d / "pairs.csv", pairs)
    sel = [p["key"] for p in back if p["selected"]]
    check("读回 csv：只选中 Case7", sel == ["Case7"], sel)

print()
if fails:
    print(f"有 {len(fails)} 项没通过：" + "、".join(fails))
    sys.exit(1)
print("全部通过")
