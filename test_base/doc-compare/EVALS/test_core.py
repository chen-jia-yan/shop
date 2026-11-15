"""文档对比核心的测试：不需要 PDF，用截图里的真实写法和容易出错的情况。

运行（在 skill 目录下）：python evals/test_core.py    全部通过时输出“全部通过”。
改过 filters.py 或 dc_core.py 之后都要运行一次。合并同事A 的过滤后，把他遇到过的写法也加进来。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dc_core import compare, normalize  # noqa: E402
from filters import Filter, name_regex  # noqa: E402
from pdf_io import mark_header_footer  # noqa: E402

passed = 0


def lines(texts, src="text", page=1):
    return [{"t": t, "n": normalize(t, {}), "no": k, "page": page, "bbox": None, "src": src, "sec": ""} for k, t in enumerate(texts, 1)]


def run(a, b, cfg=None, names=None, src="text"):
    A, B = lines(a, src), lines(b, src)
    flt = Filter(cfg or {}, [l["n"] for l in A], [l["n"] for l in B], names)
    return compare(A, B, cfg or {}, flt)


def by(res, status):
    return [x for x in res["items"] if x["status"] == status]


def check(title, cond, detail=""):
    global passed
    if not cond:
        raise SystemExit(f"不通过：{title}\n  {detail}")
    passed += 1
    print("通过：", title)


S = lambda r: {k: r["stats"][k] for k in ("real", "unsure", "ignored", "layout")}

# ---------- 1. 截图 Case5：日期都推后 14 天、被保人姓名变了；baseline 1 个名字，新文件 3 个 ----------
TEST_NAMES = {n: "测试数据" for n in ["NICHOLSPUN", "ELIZABETHACP", "GARCIAYRW", "KATHRYNOOS"]}
a5 = ["保單資料", "2026 11 06", "繳費期", "2026 11 06", "x", "2026 11 06", "被保人姓名 梁柏翰",
      "UXP3 587.85 2046 11 06", "條款", "梁柏翰", "END"]
b5 = ["保單資料", "2026 11 20", "繳費期", "2026 11 20", "x", "2026 11 20", "被保人姓名 朱彥廷",
      "UXP3 587.85 2046 11 20", "條款", "NICHOLSPUN", "ELIZABETHACP", "朱彥廷", "END"]
r = run(a5, b5, names=TEST_NAMES)
check("Case5：没有真实差异、没有不确定", r["stats"]["real"] == 0 and r["stats"]["unsure"] == 0, S(r))
check("Case5：日期整体推后 14 天（含 2046 年那行）", r["date_shift"] == 14, r["date_shifts"])
check("Case5：被保人姓名从标签自动收集", "梁柏翰" in r["names"] and "朱彥廷" in r["names"], r["names"])
check("Case5：全部进附录（4 个日期 + 2 个人名 + 多出的人名行）", r["stats"]["ignored"] == 7, S(r))
check("Case5：人名个数不同的那段写明原因", any("个数不同" in x["reason"] for x in by(r, "ignored")), [x["reason"] for x in by(r, "ignored")])

# ---------- 2. 截图 Case7：同样的情况 ----------
a7 = ["2026 11 06", "被保人姓名 楊宜庭", "HCY6 906.12 2051 11 06", "條款", "楊宜庭", "END"]
b7 = ["2026 11 20", "被保人姓名 楊傑克", "HCY6 906.12 2051 11 20", "條款", "GARCIAYRW", "KATHRYNOOS", "楊傑克", "END"]
r = run(a7, b7, names=TEST_NAMES)
check("Case7：没有真实差异，5 处忽略", S(r) == {"real": 0, "unsure": 0, "ignored": 5, "layout": 0}, S(r))
r = run(a7, b7, {"name_count_change": "unsure"}, TEST_NAMES)
check("Case7：配置 name_count_change = unsure 时，人名个数不同交给人看", S(r)["unsure"] == 1 and S(r)["real"] == 0, S(r))

# ---------- 3. 没有测试数据名单：NICHOLSPUN 不认识 → 报差异，并提示疑似人名 ----------
r = run(a5, b5)
real = by(r, "real")
check("没有名单：报 1 处真实差异并标疑似人名", len(real) == 1 and "疑似人名" in real[0]["flags"] and "NICHOLSPUN" in real[0]["reason"], real)

# ---------- 4. 金额不会被当成日期；金额变了一定报出来 ----------
flt = Filter({}, [], [])
key, dates, _ = flt.template("UXP3 587.85 2046 11 06")
check("587.85 不被当成日期", key == "UXP3 587.85 ‹日期›" and len(dates) == 1, key)
r = run(["UXP3 587.85 2046 11 06"], ["UXP3 600.00 2046 11 20"])
check("金额 587.85 → 600.00 报为真实差异", S(r)["real"] == 1 and "600.00" in by(r, "real")[0]["new"][0], r["items"])

# ---------- 5. 日期平移天数 ----------
r = run(["生效日 2026 11 06", "繳費日 2026 12 06", "到期日 2046 11 06"], ["生效日 2026 11 20", "繳費日 2026 12 20", "到期日 2046 11 21"])
check("到期日推后 15 天、其他推后 14 天 → 到期日报差异", S(r)["real"] == 1 and S(r)["ignored"] == 2 and "15" in by(r, "real")[0]["reason"], r["items"])
r = run(["生效日 2026 11 06", "到期日 2046 11 06"], ["生效日 2026 11 20", "到期日 2046 11 21"])
check("只有两个日期且天数不同 → 不确定", S(r)["unsure"] == 2 and S(r)["ignored"] == 0, S(r))
r = run(["生效日 2026 11 06", "列印日期 2026 11 03"], ["生效日 2026 11 20", "列印日期 2026 11 15"], {"date_any_shift_labels": ["列印日期"]})
check("列印日期按配置不要求统一平移", S(r)["ignored"] == 2 and S(r)["real"] == 0, r["items"])

# ---------- 6. 不是日期的写法 ----------
r = run(["日期 2026 02 30"], ["日期 2026 02 28"])
check("2026 02 30 不是日期 → 报差异", S(r)["real"] == 1, S(r))
r = run(["587.2026 11 20"], ["587.2026 11 21"])
check("紧挨小数点的 2026 11 20 不是日期 → 报差异", S(r)["real"] == 1, S(r))
r = run(["生效日 2026-11-06"], ["生效日 2026 11 06"])
check("日期写法变了、日期相同 → 不确定（可能改了打印格式）", S(r)["unsure"] == 1, r["items"])

# ---------- 7. 位置错位 ----------
r = run(["A", "本保單的保障範圍包括", "意外及疾病", "Z"], ["A", "本保單的保障範圍包括意外", "及疾病", "Z"])
check("换行位置不同、内容相同 → 位置变化，不算差异", S(r) == {"real": 0, "unsure": 0, "ignored": 0, "layout": 1}, S(r))
r = run(["A", "Plan Premium 587.85", "Z"], ["A", "Premium Plan 587.85", "Z"])
check("表格列读取顺序不同 → 位置变化", S(r)["layout"] == 1 and S(r)["real"] == 0, S(r))
r = run(["標題", "條款甲 內容一", "條款乙 內容二", "結尾"], ["標題", "條款乙 內容二", "條款甲 內容一", "結尾"])
check("两段互换位置 → 位置变化，不算差异", S(r)["layout"] == 1 and S(r)["real"] == 0, S(r))
r = run(["標題", "保費 906.50", "生效日 2026 11 06"], ["標題", "新增說明", "保費 906.50", "生效日 2026 11 20"])
check("前面多一行：只报这一行，后面照常配对", S(r)["real"] == 1 and by(r, "real")[0]["new"] == ["新增說明"] and S(r)["ignored"] == 1, r["items"])
r = run(["保額 1,000,000.00"], ["保額 1000000.00"])
check("千分位写法不同 → 相同", not r["items"], r["items"])

# ---------- 8. 扫描页：识别得到的文字，变化一律交给人看 ----------
r = run(["Signature 2026 11 06"], ["Signature 2026 11 20"], src="ocr")
check("扫描页上的日期变化 → 不确定", S(r)["unsure"] == 1 and "扫描页" in r["items"][0]["flags"], r["items"])

# ---------- 9. 人名匹配 ----------
nre = name_regex({"LEE": "", "WONG": ""})
check("LEE 不匹配 FLEET", nre.sub("‹人名›", "FLEET LEE") == "FLEET ‹人名›")
r = run(["FLEET LEE"], ["FLEET WONG"], {"names": ["LEE", "WONG"]})
check("FLEET LEE → FLEET WONG 只差人名 → 忽略", S(r)["ignored"] == 1, r["items"])

# ---------- 10. 负责人 ----------
r = run(["UXP3 587.85"], ["UXP3 600.00"], {"owners": [{"name": "產品組", "match": ["UXP3"]}]})
check("按关键字分给负责人", by(r, "real")[0]["owner"] == "產品組", r["items"])

# ---------- 11. 页眉页脚 ----------
L = []
for p in range(1, 6):
    L.append({"t": f"保單附表 第 {p} 頁", "n": f"保單附表 第 {p} 頁", "page": p, "bbox": [50, 20, 300, 30], "src": "text"})
    L.append({"t": f"正文 {p}", "n": f"正文 {p}", "page": p, "bbox": [50, 300, 300, 310], "src": "text"})
mark_header_footer(L, [{"page": p, "h": 800, "text": True} for p in range(1, 6)], {"header_band": 0.08, "header_min_ratio": 0.5})
check("每页的页眉（页码不同）去掉，正文保留", all(l.get("hf") for l in L[0::2]) and not any(l.get("hf") for l in L[1::2]), L)

print(f"全部通过（{passed} 项）")
