---
name: policy-diff-summary
description: 保单附表（Policy Schedule）回归对比结果汇总。把多个 different_after_ignore.html 里的差异过滤噪音（位置变化、日期、姓名、空格断行）、按变化内容跨用例归并成 Difference，固定产出 差异汇总.html + 交付文档.docx + 交付文档.xlsx。用户说“整理/汇总对比结果”“出交付文档”“看下这批 difference”时使用。
metadata:
  version: "3.0.0"
---

# 保单附表差异汇总

同事跑完对比脚本后，每个用例有一份 `…(different_after_ignore).html`。本技能把它们一次读完，去掉噪音，把**同一处变化**合并成一个 Difference（自动列出 Sample case），在新版 PDF 里截图，写好交付文档。

**每次都必须得到这三份文件，缺一份就是没完成：**

| 产物 | 给谁 |
|---|---|
| `差异汇总.html` | 自己核对：Difference 列表、已过滤、文件、交付文档预览。双击打开，不需要联网 |
| `交付文档.docx` | 发给开发：Difference N + Sample case + 新版 PDF 截图 + 说明 |
| `交付文档.xlsx` | 与 Word 内容一致 |

位置固定：`<对比结果文件夹>\差异汇总\<运行名>\`。中间数据都在旁边隐藏的 `.diffsum\` 里，不用管。

## 第 0 步：准备工具（每次开始都做，一条命令）

把本文件末尾的代码写到 `~/.diffsum/diffsum.py`（用下面这条命令，把路径换成本文件的实际路径）：

```bash
python -c "import pathlib,sys;t=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8');s=t.split('# ==== DIFFSUM_TOOL_BEGIN ====')[-1].split('# ==== DIFFSUM_TOOL_END ====',1)[0];p=pathlib.Path.home()/'.diffsum'/'diffsum.py';p.parent.mkdir(exist_ok=True);p.write_text(s,encoding='utf-8');print(p)" "<本 SKILL.md 的路径>"
```

直接进入第 1 步。`start` 提示缺少 Python 库时，征得用户同意后运行 `pip install pymupdf python-docx openpyxl pillow`，再重新运行 `start`。（`selftest` 是给技能维护人用的，正常使用不要跑。）

下面的命令都写成 `diffsum <命令>`，实际是 `python ~/.diffsum/diffsum.py <命令>`（Mac / Linux 上 `python` 不存在时用 `python3`，第 0 步同理）。

## 第 1 步：汇总（不用用户复制路径）

| 用户怎么说 | 运行 |
|---|---|
| 没说用哪些文件 | `diffsum start`（第一次会弹出选文件夹窗口，选一次就记住；以后自动用最新一次运行） |
| “用最近 3 次” | `diffsum start --latest 3` |
| “换个文件夹” | `diffsum start --pick` |
| “我自己选文件” | `diffsum start --pick-files`（弹窗多选） |
| 拖进来一个文件夹或文件（终端里出现路径） | `diffsum start --files "<路径>" ["<路径2>" …]` |

输出里会写这次用了哪次运行、还有哪些可选，**把这一行告诉用户**，方便他说“换成上一次”。

输出说“没找到 Case N 的新版 PDF”时，运行 `diffsum start --pick-pdf`（弹窗选新版 PDF 所在文件夹，记住后不再问），其他参数保持不变。

## 第 2 步：AI 补标题、说明，复查过滤

读 `.diffsum\for_ai.json`（start 输出的最后一行有路径），在同一个 `.diffsum` 文件夹里写一个 `ai.json`：

```json
{"by": "AI", "changes": {
  "title": {"D1": "Provision is different", "D2": "Annual premium amount is different"},
  "desc":  {"D1": "Provision version changed from V042024H to V112026H in Extended Benefit. Please confirm it is expected."},
  "merge": [["D4", "D7"]],
  "restore_no": [12]
}}
```

- **title**：每个 Difference 都要有，英文短句，和同事现有写法一致（“X is different / X is missing in new version / X is added”）。
- **desc**：一两句，写清旧值 → 新值、在哪一段、请开发确认什么。只写 old/new 和 examples 里看得到的内容，不推测原因。
- **merge**：同一字段、同一性质，只是每个用例的值不同（例如各用例保费都变了），合并成一个。拿不准就不合并。
- **restore_no**：看 `filtered_to_review`。日期过滤把金额一起吞掉、或把产品名/条款名当成姓名的，把它的 `no` 写进来。
- 不要排除（exclude）任何 Difference。放不放进交付由用户决定。

然后运行 `diffsum edit ai.json`。

## 第 3 步：确认产物，交给用户

运行 `diffsum check`，看到 `✓ 产物齐全` 后，把三个路径原样告诉用户，再用两三句话说明：一共几个 Difference、哪几个需要手动补截图、过滤了多少处（页面“已过滤”可查）。

`check` 没通过就按提示处理，再重新运行 `start` 或 `edit`，直到通过。不能跳过，也不能用别的文件代替。

## 用户在终端里要改

用户看完页面后可能会说下面这些话。照着在 `.diffsum` 文件夹里写一个 JSON，运行 `diffsum edit <文件>`，再运行 `diffsum check`：

| 用户说 | changes 里写 |
|---|---|
| “D3 不要” | `"exclude": ["D3"]` |
| “D3 加回来” | `"include": ["D3"]` |
| “D2 标题改成 …”“说明改成 …” | `"title": {"D2": "…"}` / `"desc": {"D2": "…"}`，并且 `"by": "人工"` |
| “D1 截图用 Case 11” | `"rep": {"D1": 11}` |
| “已过滤第 12 条放回来” | `"restore_no": [12]` |
| “D4 和 D7 是一个问题” | `"merge": [["D4", "D7"]]` |
| “这种变化以后都过滤掉” | `"ignore": ["D5"]` |

## 规则

1. **只有三份产物。** 不另外生成 md、txt、截图文件夹或其他文档，也不要手工改这三份文件。所有修改都通过 `diffsum edit` 完成，否则下次重新生成时会丢失。
2. **过滤只靠工具。** 日期、姓名、位置变化由工具判断，AI 只能通过 `restore_no` 把误过滤的放回来，不能自己删差异。
3. **不编造。** 标题和说明只依据 for_ai.json 里的内容。
4. **截图失败不跳过。** 文档里会写“需手动截图”，告诉用户是哪几个。
5. **用户的修改优先。** 用户改过的标题或说明，AI 不覆盖（for_ai.json 里 `title_src` 为“人工”的，不要再写 title）。
6. **出问题先诊断。** 结果和预期不符时，运行 `diffsum diag`。它只输出统计数字，不含保单内容。
7. **设置在哪。** `diffsum where` 列出设置、修改记录、姓名名单（`names.txt`，一行一个，补充工具认不出的姓名）的位置。

## 工具代码

```python
# ==== DIFFSUM_TOOL_BEGIN ====
# -*- coding: utf-8 -*-
"""保单附表差异汇总：读取多个 different_after_ignore.html，过滤噪音，按变化内容归并成 Difference，
固定产出 差异汇总.html + 交付文档.docx + 交付文档.xlsx。只在本机运行，不联网。"""
import base64, datetime as _dt, difflib, hashlib, html, json, os, re, sys, tempfile, zipfile
from html.parser import HTMLParser
from pathlib import Path

VERSION = "3.0.0"
HOME = Path.home() / ".diffsum"
CFG_F, MEM_F, NAMES_F = HOME / "config.json", HOME / "memory.json", HOME / "names.txt"
OUT_DIR_NAME = "差异汇总"
PRODUCTS = ("差异汇总.html", "交付文档.docx", "交付文档.xlsx")
HTML_PAT = re.compile(r"after[_ ]?ignore.*\.html?$", re.I)


class UserError(Exception):
    pass


def out(*a):
    print(*a, flush=True)


def now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def cfg():
    c = read_json(CFG_F, {})
    c.setdefault("root", "")          # 对比结果的上层文件夹，例如 C:\PolicySchedule_Compare\Different
    c.setdefault("pdf_dirs", [])      # 新版 PDF 所在文件夹（可多个）
    c.setdefault("mask_policy_no", False)
    return c


def save_cfg(c):
    write_json(CFG_F, c)


def h8(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ 选文件
def pick_dir(title):
    """弹出系统的选文件夹窗口；没有图形界面时返回空。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        p = filedialog.askdirectory(title=title, mustexist=True)
        r.destroy()
        return p or ""
    except Exception:
        return ""


def pick_files(title):
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        ps = filedialog.askopenfilenames(title=title, filetypes=[("对比结果", "*.html *.htm"), ("全部", "*.*")])
        r.destroy()
        return list(ps or [])
    except Exception:
        return []


def find_html(folder):
    folder = Path(folder)
    if folder.is_file():
        return [folder] if HTML_PAT.search(folder.name) else []
    res = []
    for p in folder.rglob("*"):
        if OUT_DIR_NAME in p.parts or ".diffsum" in p.parts:
            continue
        if p.is_file() and HTML_PAT.search(p.name):
            res.append(p)
    return sorted(res)


def run_folders(root):
    """root 下含有对比结果的子文件夹，按修改时间从新到旧。"""
    root = Path(root)
    seen = {}
    for f in find_html(root):
        rel = f.relative_to(root).parts
        top = root / rel[0] if len(rel) > 1 else root
        seen.setdefault(top, []).append(f)
    return sorted(seen.items(), key=lambda kv: max(x.stat().st_mtime for x in kv[1]), reverse=True)


def choose_inputs(a, c):
    """决定这次要汇总哪些文件。返回 (文件列表, 说明, 产物目录)。"""
    if a.files:
        fs = []
        for x in a.files:
            fs += find_html(x)
        if not fs:
            raise UserError("给的路径里没有 *after_ignore*.html 文件：" + "；".join(a.files))
        base = Path(a.files[0])
        base = base if base.is_dir() else base.parent
        return fs, "指定的 " + str(len(a.files)) + " 个路径", base / OUT_DIR_NAME
    if a.pick_files:
        fs = [Path(x) for x in pick_files("选择要汇总的对比结果（可多选）")]
        if not fs:
            raise UserError("没有选文件（或电脑上不能弹出选择窗口，请把文件夹拖进终端，或用 --files 路径）")
        return fs, "手动选的 " + str(len(fs)) + " 个文件", fs[0].parent / OUT_DIR_NAME
    if a.pick or not c["root"] or not Path(c["root"]).exists():
        p = pick_dir("选择对比结果所在的文件夹（例如 PolicySchedule_Compare\\Different）")
        if not p:
            raise UserError("还没有设置对比结果所在的文件夹。请把文件夹拖进终端，或运行 start --files <路径>")
        c["root"] = p
        save_cfg(c)
    runs = run_folders(c["root"])
    if not runs:
        raise UserError("文件夹里没有找到 *after_ignore*.html：" + c["root"] + "（换文件夹用 start --pick）")
    n = max(1, a.latest or 1)
    use = runs[:n]
    fs = sorted(f for _, x in use for f in x)
    names = [p.name for p, _ in use]
    others = ["  " + p.name + "（" + str(len(x)) + " 个文件）" for p, x in runs[n:n + 5]]
    note = "最新 " + str(n) + " 次运行：" + "、".join(names) + (("\n其他可选：\n" + "\n".join(others)) if others else "")
    outdir = Path(c["root"]) / OUT_DIR_NAME / (names[0] if n == 1 else names[0] + "_等" + str(n) + "次")
    return fs, note, outdir


# ------------------------------------------------------------------ 读取对比页（Python difflib.HtmlDiff 格式）
class _DiffHTML(HTMLParser):
    """把并排对比表读成行：[(左行号, 左片段, 右行号, 右片段)]，片段是 [(文字, 标记)]，标记为 add/chg/sub/None。"""
    MARKS = {"diff_add": "add", "diff_chg": "chg", "diff_sub": "sub"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.tables = [], 0
        self.in_t = self.skip_t = False
        self.tr = None
        self.td = None
        self.marks = []

    def handle_starttag(self, tag, at):
        a = dict(at)
        if tag == "table":
            self.in_t = True
            self.skip_t = "summary" in a or "diff" not in (a.get("class") or "").split()
            self.tables += 0 if self.skip_t else 1
        elif not self.in_t or self.skip_t:
            return
        elif tag == "tr":
            self.tr = []
        elif tag == "td" and self.tr is not None:
            self.td = {"cls": a.get("class") or "", "segs": []}
            self.marks = []
        elif tag == "span" and self.td is not None:
            self.marks.append(self.MARKS.get((a.get("class") or "").strip()))
        elif tag == "br" and self.td is not None:
            self.td["segs"].append(("\n", self.marks[-1] if self.marks else None))

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_t = self.skip_t = False
        elif not self.in_t or self.skip_t:
            return
        elif tag == "span" and self.marks:
            self.marks.pop()
        elif tag == "td" and self.td is not None and self.tr is not None:
            self.tr.append(self.td)
            self.td = None
        elif tag == "tr" and self.tr is not None:
            self._row(self.tr)
            self.tr = None

    def handle_data(self, d):
        if self.td is not None and d:
            m = next((x for x in reversed(self.marks) if x), None)
            self.td["segs"].append((d.replace("\xa0", " "), m))

    def _row(self, tds):
        heads = [i for i, t in enumerate(tds) if "diff_header" in t["cls"]]
        if len(heads) < 2:
            return
        side = []
        for i in heads[:2]:
            no = "".join(s for s, _ in tds[i]["segs"]).strip()
            txt = tds[i + 1]["segs"] if i + 1 < len(tds) else []
            side.append((no, txt))
        (ln, lt), (rn, rt) = side
        # 换行续接（行号显示为 >）：接到上一行
        if self.rows and (ln == ">" or rn == ">"):
            p = self.rows[-1]
            if ln == ">":
                p[1].extend([(" ", None)] + lt)
            if rn == ">":
                p[3].extend([(" ", None)] + rt)
            return
        self.rows.append([int(ln) if ln.isdigit() else None, list(lt), int(rn) if rn.isdigit() else None, list(rt)])


def parse_diff_html(path):
    raw = Path(path).read_bytes()
    txt = None
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    p = _DiffHTML()
    p.feed(txt)
    p.close()
    if not p.tables:
        raise UserError("不是 difflib 对比页（没有找到 class=diff 的表格）：" + Path(path).name)
    return p.rows


def seg_text(segs):
    return "".join(s for s, _ in segs)


def seg_marked(segs):
    return any(m for _, m in segs)


CASE_PAT = re.compile(r"case[ _-]?(\d+)", re.I)


def case_of(path):
    m = CASE_PAT.search(Path(path).name)
    return int(m.group(1)) if m else None


def pdf_stem(path):
    """对比页文件名去掉 after_ignore 之类的后缀，得到对应 PDF 的文件名。"""
    s = Path(path).stem
    s = re.sub(r"[ _\-]*\(?\s*diff(erent|erence)?[ _]*after[ _]*ignore\s*\)?$", "", s, flags=re.I)
    s = re.sub(r"[ _\-]*\(?\s*after[ _]*ignore\s*\)?$", "", s, flags=re.I)
    return s.strip(" _-")


# ------------------------------------------------------------------ 噪音识别（只替换那一个词，不删整行）
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_Y, _M, _D = r"(?:19|20)\d{2}", r"(?:0?[1-9]|1[0-2])", r"(?:0?[1-9]|[12]\d|3[01])"
_S = r"(?:[./\-]|\s{1,3})"
_L, _R = r"(?<![\d,.])", r"(?![\d,]|\.\d)"          # 左右不能紧挨数字、逗号、小数点：金额不会被当成日期
DATE_RES = [re.compile(x, re.I) for x in (
    _L + _Y + _S + _M + _S + _D + _R,                        # 2026 11 06 / 2026-11-06 / 2026/11/06
    _L + _D + _S + _M + _S + _Y + _R,                        # 06/11/2026 / 06 11 2026
    _L + _D + r"[\s\-]{0,2}" + _MON + r"\.?[\s\-,]{1,3}" + _Y + _R,   # 06 Nov 2026 / 06-Nov-2026
    r"(?<![A-Za-z])" + _MON + r"\.?\s{1,2}" + _D + r",?\s{1,2}" + _Y + _R,  # November 6, 2026
    _Y + r"\s*年\s*" + _M + r"\s*月\s*" + _D + r"\s*日",       # 2026年11月6日
    r"(?<!\d)(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-3])[0-5]\d[0-5]\d(?!\d)",  # 20261020195841
    r"(?<![\d:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?![\d:])",  # 19:58:41（打印时间）
)]
NAME_LABEL = re.compile(
    r"(?:Name\s+of\s+(?:the\s+)?(?:Life\s+)?(?:Insured|Policy\s*Owner|Policyholder|Assured|Beneficiary|Proposer)|Life\s+Insured|Insured(?:\s+Person)?|"
    r"Policy\s*Owner|Policyholder|Proposer|Applicant|Assured|Beneficiary|Payor|Payer|(?<![A-Za-z]\s)(?<![A-Za-z])Name|Dear\s+(?:Mr|Mrs|Ms|Miss|Dr)\.?)"
    r"\s*[:：]?\s{0,3}([A-Z][A-Za-z'’.\-]*(?:,?\s[A-Z][A-Za-z'’.\-]*){1,5})")
NAME_LABEL_ZH = re.compile(r"(?:姓名|被保人|受保人|投保人|保单持有人|保單持有人|持有人)\s*[:：]?\s*([一-鿿]{2,4})")
NAME_STOP = {"age", "sex", "male", "female", "plan", "policy", "benefit", "date", "no", "number", "not", "applicable", "same", "as", "above",
             "insured", "owner", "schedule", "hkd", "usd", "rmb", "mop", "the", "of", "and", "issue", "effective", "premium", "currency", "class",
             "occupation", "relationship", "self", "spouse", "child", "smoker", "non", "standard", "address", "id", "hkid", "passport", "tel", "phone"}
POLNO = re.compile(r"(?:Policy|Certificate|Contract)\s*(?:No\.?|Number|#)\s*[:：]?\s*([A-Z0-9][A-Z0-9\-]{5,})|保[单單]號?[号碼码]+\s*[:：]?\s*([A-Z0-9][A-Z0-9\-]{5,})", re.I)
PH = {"dt": "⟨日期⟩", "nm": "⟨姓名⟩", "pn": "⟨保单号⟩"}
WHY = {"mv": "位置变化", "dt": "仅日期不同", "nm": "仅姓名不同", "pn": "仅保单号不同", "ws": "仅空格/断行不同", "rule": "按过滤规则"}


def global_names():
    try:
        return [x.strip() for x in NAMES_F.read_text(encoding="utf-8-sig").splitlines() if x.strip() and not x.startswith("#")]
    except OSError:
        return []


def names_in(texts):
    """只认标签后面的名字（同一份文件内）。"""
    found = set()
    for t in texts:
        for m in NAME_LABEL.finditer(t):
            toks = re.split(r",?\s", m.group(1).strip())
            keep = []
            for k in toks:
                if k.lower().strip(".") in NAME_STOP:
                    break
                keep.append(k)
            if 2 <= len(keep) <= 5 and not any(ch.isdigit() for ch in "".join(keep)):
                found.add(" ".join(keep))
        for m in NAME_LABEL_ZH.finditer(t):
            found.add(m.group(1))
    return found


def polnos_in(texts):
    return {g for t in texts for m in POLNO.finditer(t) for g in m.groups() if g}


def mask(text, names, polnos):
    """返回 (替换后的文字, 用到的替换种类)。"""
    kinds = set()
    s = text
    for n in sorted(names, key=len, reverse=True):
        pat = r"(?<![A-Za-z])" + r",?\s+".join(re.escape(p) for p in n.split()) + r"(?![A-Za-z])"
        s, k = re.subn(pat, PH["nm"], s, flags=re.I)
        if k:
            kinds.add("nm")
    for p in polnos:
        s, k = re.subn(r"(?<![A-Za-z0-9])" + re.escape(p) + r"(?![A-Za-z0-9])", PH["pn"], s)
        if k:
            kinds.add("pn")
    for r in DATE_RES:
        s, k = r.subn(PH["dt"], s)
        if k:
            kinds.add("dt")
    return s, kinds


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def nows(s):
    return re.sub(r"\s+", "", s)


def word_diff(a, b):
    """词级对比，返回 (旧 html, 新 html)，变化部分用 <del>/<ins>。"""
    ta, tb = re.split(r"(\s+)", a), re.split(r"(\s+)", b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    oa, ob = [], []
    e = lambda xs: html.escape("".join(xs))
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            oa.append(e(ta[i1:i2]))
            ob.append(e(tb[j1:j2]))
        else:
            if i2 > i1:
                oa.append("<del>" + e(ta[i1:i2]) + "</del>")
            if j2 > j1:
                ob.append("<ins>" + e(tb[j1:j2]) + "</ins>")
    ph = lambda s: re.sub("⟨(日期|姓名|保单号)⟩", r'<span class="mask">\1</span>', s)
    return ph("".join(oa)), ph("".join(ob))


# ------------------------------------------------------------------ 单个文件：找出真变化
def analyze_file(path, run, mem, c):
    rows = parse_diff_html(path)
    case = case_of(path)
    allt = [seg_text(r[1]) for r in rows] + [seg_text(r[3]) for r in rows]
    names = names_in(allt) | set(global_names())
    polnos = polnos_in(allt) if c.get("mask_policy_no") else set()
    restore, ignore = set(mem.get("restore", [])), set(mem.get("ignore", []))
    items, prev_r = [], ""   # 每处候选变化；prev_r 是新版的上一行，用来给“新版缺少的内容”定位
    for i, (ln, lt, rn, rt) in enumerate(rows):
        lx, rx = seg_text(lt), seg_text(rt)
        if rx.strip() and not seg_marked(rt):
            prev_r = rx
        lm, rm = seg_marked(lt), seg_marked(rt)
        if not (lm or rm):
            continue
        kind = "chg" if lx.strip() and rx.strip() else "del" if lx.strip() else "add" if rx.strip() else None
        if kind:
            items.append({"i": i, "kind": kind, "l": ln, "r": rn, "old": lx if kind != "add" else "", "new": rx if kind != "del" else "", "ctx": prev_r})
    done = {}
    # 1) 连续几行合起来只差空格/断行
    blk = []
    for it in items + [None]:
        if blk and (it is None or it["i"] != blk[-1]["i"] + 1):
            if len(blk) > 1 and nows("".join(x["old"] for x in blk)) == nows("".join(x["new"] for x in blk)):
                for x in blk:
                    done[x["i"]] = ("ws", "第 " + str(blk[0]["i"] + 1) + "–" + str(blk[-1]["i"] + 1) + " 行合起来内容相同，只是断行不同")
            blk = []
        if it is not None:
            blk.append(it)
    # 2) 位置变化：旧版删掉的内容在新版另一处出现（忽略空格、断行、日期姓名）
    mk = lambda s: nows(mask(s, names, polnos)[0])
    dels = [x for x in items if x["kind"] == "del" and x["i"] not in done]
    adds = [x for x in items if x["kind"] == "add" and x["i"] not in done]
    pool_new = "".join(mk(x["new"]) for x in adds)
    pool_old = "".join(mk(x["old"]) for x in dels)
    for x, pool, side in [(x, pool_new, "old") for x in dels] + [(x, pool_old, "new") for x in adds]:
        k = mk(x[side])
        if len(k) >= 6 and k in pool:
            where = "旧版第 " + str(x["l"]) + " 行" if side == "old" else "新版第 " + str(x["r"]) + " 行"
            done[x["i"]] = ("mv", where + "的内容在" + ("新版" if side == "old" else "旧版") + "另一处出现")
    # 3) 逐行：只差日期/姓名/保单号/空格
    found, filtered = {}, []
    for x in items:
        mo, ko = mask(x["old"], names, polnos)
        mn, kn = mask(x["new"], names, polnos)
        key = x["kind"] + "|" + norm(mo) + "→" + norm(mn)
        fid = h8(key)
        why = done.get(x["i"])
        if not why and x["kind"] == "chg":
            if nows(x["old"]) == nows(x["new"]):
                why = ("ws", "只差空格")
            elif norm(mo) == norm(mn):
                ks = (ko | kn)
                k1 = "dt" if ks == {"dt"} else "nm" if ks == {"nm"} else "pn" if ks == {"pn"} else "dt" if "dt" in ks else "nm"
                why = (k1, "替换" + "、".join(WHY[k][1:3] for k in sorted(ks)) + "后内容相同")
        if not why and fid in ignore:
            why = ("rule", "之前标为“以后也过滤”")
        if why and fid in restore:
            why = None
        rec = {"case": case, "file": Path(path).name, "run": run, "l": x["l"], "r": x["r"], "old": x["old"].strip(), "new": x["new"].strip(), "ctx": x["ctx"].strip(), "fid": fid}
        if why:
            filtered.append(dict(rec, why=why[0], detail=why[1]))
            continue
        if key in found:
            found[key]["count"] += 1
            continue
        ho, hn = word_diff(norm(mo), norm(mn))
        found[key] = dict(rec, key=key, kind=x["kind"], mold=norm(mo), mnew=norm(mn), hold=ho, hnew=hn, count=1)
    stat = {"file": Path(path).name, "path": str(path), "case": case, "run": run, "pdf_stem": pdf_stem(path),
            "raw": len(items), "kept": sum(v["count"] for v in found.values()), "names": len(names)}
    return list(found.values()), filtered, stat


# ------------------------------------------------------------------ 所有文件：按变化内容归并成 Difference
def analyze_all(files, root, mem, c):
    groups, filtered, stats, errors = {}, [], [], []
    for f in files:
        f = Path(f)
        try:
            rel = f.relative_to(root)
            run = rel.parts[0] if len(rel.parts) > 1 else Path(root).name
        except (ValueError, TypeError):
            run = f.parent.name
        try:
            found, filt, st = analyze_file(f, run, mem, c)
        except UserError as e:
            errors.append(str(e))
            continue
        except Exception as e:  # 单个文件坏了不影响其他文件
            errors.append(f.name + "：读取失败（" + type(e).__name__ + ": " + str(e)[:120] + "）")
            continue
        stats.append(st)
        filtered += filt
        for x in found:
            g = groups.setdefault(x["key"], {"id": h8(x["key"]), "key": x["key"], "kind": x["kind"], "mold": x["mold"], "mnew": x["mnew"],
                                             "hold": x["hold"], "hnew": x["hnew"], "occ": []})
            g["occ"].append({k: x[k] for k in ("case", "file", "run", "l", "r", "old", "new", "ctx", "count")})
    diffs = []
    for g in groups.values():
        cs = sorted({o["case"] for o in g["occ"] if o["case"] is not None})
        g["cases"] = cs
        g["hits"] = sum(o["count"] for o in g["occ"])
        diffs.append(g)
    diffs.sort(key=lambda g: (-len(g["occ"]), g["cases"][0] if g["cases"] else 10 ** 9, g["key"]))
    return diffs, filtered, stats, errors


# ------------------------------------------------------------------ 新版 PDF：找文件、定位、截图
SKIP_PDF_DIR = re.compile(r"^(bak|backup|baseline|old|旧版|基线)$", re.I)


def pdf_index(roots):
    idx = {}
    for r in roots:
        r = Path(r)
        if not r.exists():
            continue
        for p in r.rglob("*.pdf"):
            if OUT_DIR_NAME in p.parts or any(SKIP_PDF_DIR.match(x) for x in p.relative_to(r).parts[:-1]):
                continue
            idx.setdefault(p.stem.lower(), p)
    return idx


def find_pdf(stat, idx):
    s = (stat["pdf_stem"] or "").lower()
    if s in idx:
        return idx[s]
    cand = [k for k in idx if s and (k.startswith(s) or s.startswith(k))]
    if not cand and stat["case"] is not None:
        cand = [k for k in idx if CASE_PAT.match(k) and int(CASE_PAT.match(k).group(1)) == stat["case"]]
    if not cand:
        return None
    return idx[max(cand, key=lambda k: difflib.SequenceMatcher(None, k, s).ratio())]


def _needles(occ, kind):
    """在 PDF 里搜索用的文字，从最完整到最短。"""
    t = norm(occ["new"] if kind != "del" else occ.get("ctx") or "")
    out_ = []
    if t:
        out_.append(t)
        if len(t) > 60:
            out_ += [t[:60], t[-60:]]
        ws = t.split(" ")
        if len(ws) > 4:
            out_ += [" ".join(ws[:4]), " ".join(ws[-4:])]
    return [x for x in dict.fromkeys(out_) if len(x) >= 3]


def shoot(pdf, occ, kind, png):
    """在新版 PDF 里找到这处变化，截一段整页宽的图，红框标出位置。"""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf))
    try:
        for nd in _needles(occ, kind):
            for pno in range(doc.page_count):
                page = doc[pno]
                hits = page.search_for(nd)
                if not hits:
                    continue
                r = fitz.Rect(hits[0])
                for h in hits[1:]:
                    if abs(h.y0 - r.y1) < 30:
                        r |= h
                pr = page.rect
                box = fitz.Rect(r.x0 - 3, r.y0 - 2, r.x1 + 3, r.y1 + 2)
                if kind == "del":   # 新版缺少的内容：在前一行下方画框，表示“这里少了”
                    box = fitz.Rect(pr.x0 + 30, r.y1 + 1, pr.x1 - 30, r.y1 + 14)
                page.draw_rect(box, color=(0.89, 0.29, 0.28), width=1.6)
                clip = fitz.Rect(pr.x0 + 14, max(pr.y0, box.y0 - 80), pr.x1 - 14, min(pr.y1, box.y1 + 80))
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
                samp = pix.samples
                if pix.width < 60 or sum(1 for b in samp[::97] if b < 200) < 10:
                    continue   # 空白图：换下一个位置
                Path(png).parent.mkdir(parents=True, exist_ok=True)
                pix.save(str(png))
                return {"ok": True, "page": pno + 1, "how": "按文字“" + nd[:30] + "”定位"}
        return {"ok": False, "why": "新版 PDF 里没找到这段文字（可能被拆成多段或是图片），请手动截图"}
    finally:
        doc.close()


def make_shots(diffs, stats, c, outdir, roots, log):
    """每个 Difference 用代表用例截一张图；失败就记原因，不跳过。"""
    idx = pdf_index(roots)
    by_file = {s["file"]: s for s in stats}
    sd = outdir / ".diffsum" / "shots"
    try:
        import fitz  # noqa: F401
        has = True
    except ImportError:
        has = False
    for g in diffs:
        rep = next((o for o in g["occ"] if o["case"] == g.get("rep")), g["occ"][0])
        g["rep"] = rep["case"]
        g["shot"] = None
        if not has:
            g["shot_err"] = "没有安装 PyMuPDF，不能截图（pip install pymupdf）"
            continue
        pdf = find_pdf(by_file.get(rep["file"], {"pdf_stem": "", "case": rep["case"]}), idx)
        if not pdf:
            g["shot_err"] = "没找到 Case " + str(rep["case"]) + " 的新版 PDF（用 start --pick-pdf 选新版 PDF 所在文件夹）"
            continue
        try:
            png = sd / (g["id"] + ".png")
            r = shoot(pdf, rep, g["kind"], png)
        except Exception as e:
            r = {"ok": False, "why": "截图出错：" + type(e).__name__ + " " + str(e)[:100]}
        if r["ok"]:
            g.update(shot=str(png), shot_page=r["page"], shot_pdf=pdf.name, shot_err=None)
        else:
            g.update(shot_err=r["why"], shot_pdf=pdf.name)
    n = sum(1 for g in diffs if g.get("shot"))
    log("截图：" + str(n) + " / " + str(len(diffs)) + " 个 Difference 成功" + ("" if n == len(diffs) else "，其余在页面和文档里标为“需手动截图”"))


# ------------------------------------------------------------------ 修改记录（标题、说明、是否放进交付…）按变化内容记住，下次同样的变化自动带上
def load_mem():
    m = read_json(MEM_F, {})
    for k, d in (("diff", {}), ("ignore", []), ("restore", []), ("merge", [])):
        m.setdefault(k, d)
    return m


def auto_title(g):
    cut = lambda s, n=48: (s[:n] + "…") if len(s) > n else s
    if g["kind"] == "add":
        return "Added in new version: " + cut(g["mnew"])
    if g["kind"] == "del":
        return "Missing in new version: " + cut(g["mold"])
    return "“" + cut(g["mold"], 30) + "” → “" + cut(g["mnew"], 30) + "”"


def apply_mem(diffs, mem):
    by = {g["id"]: g for g in diffs}
    for grp in mem.get("merge", []):           # AI / 人工合并的几个 Difference
        gs = [by[i] for i in grp if i in by]
        if len(gs) < 2:
            continue
        t = gs[0]
        for g in gs[1:]:
            t["occ"] += g["occ"]
            t.setdefault("merged", []).append({"id": g["id"], "mold": g["mold"], "mnew": g["mnew"]})
            diffs.remove(g)
            by.pop(g["id"])
        t["cases"] = sorted({o["case"] for o in t["occ"] if o["case"] is not None})
        t["hits"] = sum(o["count"] for o in t["occ"])
    for g in diffs:
        e = mem["diff"].get(g["id"], {})
        g["title"] = e.get("title") or auto_title(g)
        g["title_src"] = e.get("title_src") or ("" if e.get("title") else "自动")
        g["desc"] = e.get("desc") or ""
        g["include"] = not e.get("exclude")
        if e.get("rep") in g["cases"]:
            g["rep"] = e["rep"]
    diffs.sort(key=lambda g: (-len(g["occ"]), g["cases"][0] if g["cases"] else 10 ** 9, g["key"]))
    n = 0
    for g in diffs:
        if g["include"]:
            n += 1
            g["no"] = n
        else:
            g["no"] = None
    return diffs


def cases_txt(g):
    return ",".join(str(x) for x in g["cases"]) or "、".join(sorted({o["file"] for o in g["occ"]}))


# ------------------------------------------------------------------ 交付文档：Word
def write_docx(path, data, bid):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    inc = [g for g in data["diffs"] if g["include"]]
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    d.core_properties.title = "Policy Schedule Comparison Result"
    d.core_properties.comments = "diffsum:" + bid
    d.add_heading("Policy Schedule Regression — Comparison Result", level=1)
    t = d.add_table(rows=0, cols=4)
    t.style = "Table Grid"
    for a, b, c2, e in (("Run", data["runs"], "Generated", data["at"]), ("Files compared", str(len(data["stats"])), "Differences", str(len(inc)))):
        cs = t.add_row().cells
        cs[0].text, cs[1].text, cs[2].text, cs[3].text = a, b, c2, e
    if inc:
        d.add_paragraph()
        s = d.add_table(rows=1, cols=3)
        s.style = "Table Grid"
        s.rows[0].cells[0].text, s.rows[0].cells[1].text, s.rows[0].cells[2].text = "#", "Difference", "Cases"
        for g in inc:
            cs = s.add_row().cells
            cs[0].text, cs[1].text, cs[2].text = str(g["no"]), g["title"], str(len(g["cases"]) or len(g["occ"]))
    else:
        d.add_paragraph("No difference to report: all differences were filtered as noise or excluded.")
    for g in inc:
        h = d.add_heading("Difference " + str(g["no"]) + ": " + g["title"], level=2)
        d.add_paragraph("Sample case : " + cases_txt(g))
        if g.get("shot") and Path(g["shot"]).exists():
            d.add_picture(g["shot"], width=Cm(16))
        else:
            p = d.add_paragraph()
            r = p.add_run("［需手动截图：" + (g.get("shot_err") or "没有截图") + "］")
            r.font.color.rgb = RGBColor(0xC4, 0x30, 0x2B)
        if g["desc"]:
            d.add_paragraph(g["desc"])
    d.save(str(path))


# ------------------------------------------------------------------ 交付文档：Excel（内容与 Word 一致）
def write_xlsx(path, data, bid):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    inc = [g for g in data["diffs"] if g["include"]]
    wb = Workbook()
    ws = wb.active
    ws.title = "Differences"
    wb.properties.keywords = "diffsum:" + bid
    ws.append(["No.", "Difference", "Sample case", "Cases", "Description", "Screenshot", "Location"])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="DDE7F5")
    for k, w in zip("ABCDEFG", (6, 40, 30, 8, 50, 62, 26)):
        ws.column_dimensions[k].width = w
    try:
        from openpyxl.drawing.image import Image as XImg
        import PIL  # noqa: F401  openpyxl 插图需要 Pillow
    except ImportError:
        XImg = None
    if not inc:
        ws.append(["", "No difference to report"])
    for i, g in enumerate(inc, start=2):
        loc = (g.get("shot_pdf") or "") + (" p." + str(g["shot_page"]) if g.get("shot_page") else "")
        ws.append([g["no"], g["title"], cases_txt(g), len(g["cases"]) or len(g["occ"]), g["desc"], "", loc])
        for c in ws[i]:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if g.get("shot") and Path(g["shot"]).exists() and XImg:
            im = XImg(g["shot"])
            sc = min(1.0, 430 / max(1, im.width))
            im.width, im.height = int(im.width * sc), int(im.height * sc)
            ws.add_image(im, "F" + str(i))
            ws.row_dimensions[i].height = im.height * 0.75 + 6
        else:
            ws.cell(i, 6).value = "［需手动截图：" + (g.get("shot_err") or ("没有安装 Pillow，Excel 不能插图，见 Word" if g.get("shot") else "没有截图")) + "］"
            ws.row_dimensions[i].height = 48
    wb.save(str(path))


# ------------------------------------------------------------------ 产出并校验：三份产物每次都写，缺一份就报错
def build(data, outdir, log):
    outdir.mkdir(parents=True, exist_ok=True)
    bid = h8(now() + str(len(data["diffs"])) + str(os.getpid()) + str(_dt.datetime.now().timestamp()))
    data["bid"] = bid
    write_json(outdir / ".diffsum" / "data.json", data)
    writers = {"差异汇总.html": lambda p: p.write_text(render_html(data, bid), encoding="utf-8"),
               "交付文档.docx": lambda p: write_docx(p, data, bid),
               "交付文档.xlsx": lambda p: write_xlsx(p, data, bid)}
    for name in PRODUCTS:
        final = outdir / name
        tmp = outdir / ".diffsum" / ("tmp_" + h8(name) + Path(name).suffix)
        try:
            writers[name](tmp)
        except ImportError as e:
            raise UserError("缺少 Python 库，" + name + " 没生成：" + str(e) + "\n请运行：pip install pymupdf python-docx openpyxl pillow")
        try:
            os.replace(tmp, final)
        except PermissionError:
            raise UserError(name + " 正在被打开（Word / Excel / 浏览器占用），请关闭后重新运行")
    write_json(outdir / ".diffsum" / "manifest.json", {"bid": bid, "at": now(), "version": VERSION, "n_diff": sum(1 for g in data["diffs"] if g["include"])})
    return verify(outdir, log)


def verify(outdir, log=out):
    """检查三份产物都在、是这次生成的、能打开。返回 True/False 并打印结果。"""
    man = read_json(outdir / ".diffsum" / "manifest.json", {})
    bid, bad = man.get("bid"), []
    for name in PRODUCTS:
        p = outdir / name
        if not p.exists() or p.stat().st_size == 0:
            bad.append(name + "：不存在")
            continue
        try:
            if name.endswith(".html"):
                ok = ("diffsum-build:" + str(bid)) in p.read_text(encoding="utf-8", errors="ignore")
            else:
                with zipfile.ZipFile(p) as z:
                    ok = ("diffsum:" + str(bid)) in z.read("docProps/core.xml").decode("utf-8", "ignore")
        except (zipfile.BadZipFile, KeyError, OSError):
            ok = False
        if not ok:
            bad.append(name + "：不是这次生成的或文件损坏")
    log("")
    if bad or not bid:
        log("✗ 产物不完整：" + "；".join(bad or ["还没有生成过"]))
        return False
    log("✓ 产物齐全（" + str(man.get("n_diff")) + " 个 Difference，生成于 " + man.get("at", "") + "）")
    for name in PRODUCTS:
        log("  " + str(outdir / name))
    return True


# ------------------------------------------------------------------ 差异汇总.html（单个文件，双击打开；截图嵌在页面里）
def _b64(p):
    try:
        return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
    except OSError:
        return ""


def render_html(data, bid):
    slim = {"bid": bid, "at": data["at"], "runs": data["runs"], "root": data.get("root", ""), "version": VERSION,
            "stats": data["stats"], "errors": data["errors"], "filtered": data["filtered"],
            "diffs": [dict({k: g.get(k) for k in ("id", "no", "kind", "title", "title_src", "desc", "include", "cases", "hits", "hold", "hnew",
                                               "mold", "mnew", "rep", "shot_err", "shot_page", "shot_pdf", "merged")},
                           occ=g["occ"][:300], img=_b64(g["shot"]) if g.get("shot") else "") for g in data["diffs"]]}
    js = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__BID__", bid).replace("__DATA__", js)


PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<!-- diffsum-build:__BID__ -->
<title>保单附表差异汇总</title>
<style>
:root{--bg:#f4f6f9;--line:#e3e8ef;--line2:#eef1f5;--ink:#1d2533;--ink2:#4c5667;--mu:#8b94a3;--acc:#2a6fd6;--accb:#eaf2fd;--bad:#c4302b;
--mono:"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;--sans:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:12.5px/1.55 var(--sans)}
header{display:flex;align-items:center;gap:12px;padding:10px 18px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
header h1{font-size:15px;margin:0;font-weight:600}.sp{flex:1}.hint{color:var(--mu)}
.btn{font:inherit;border:1px solid var(--line);background:#fff;border-radius:4px;padding:4px 10px;color:var(--ink2);cursor:pointer}
.btn:hover{border-color:var(--acc);color:var(--acc)}.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}.btn.sm{padding:1px 8px;font-size:11.5px}
.btn[disabled]{opacity:.5;cursor:default}
.stats{display:flex;margin:12px 18px;background:#fff;border:1px solid var(--line);border-radius:6px;flex-wrap:wrap}
.st{padding:8px 16px;border-right:1px solid var(--line2)}.st:last-child{border-right:0}
.st b{display:block;font-size:18px;font-family:var(--mono);font-weight:600}.st span{color:var(--mu)}.st .sub{font-size:11px;color:var(--mu)}
.warn{margin:0 18px 10px;background:#fdf6ec;border:1px solid #faecd8;color:#8a5a00;border-radius:4px;padding:6px 10px}
.tabs{display:flex;gap:2px;margin:0 18px;border-bottom:1px solid var(--line)}
.tab{padding:7px 14px;cursor:pointer;color:var(--ink2);border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.on{color:var(--acc);border-color:var(--acc);font-weight:600}.tab i{font-style:normal;font-family:var(--mono);background:var(--line2);border-radius:8px;padding:0 6px;margin-left:4px;font-size:11px}
.view{margin:12px 18px 60px}.hide{display:none!important}
.main{display:grid;grid-template-columns:minmax(0,430px) minmax(0,1fr);gap:12px}
.panel{background:#fff;border:1px solid var(--line);border-radius:6px;min-width:0}
.ph{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line2)}
.chips{display:flex;gap:6px;padding:8px 12px;border-bottom:1px solid var(--line2);flex-wrap:wrap;align-items:center}
.chip{border:1px solid var(--line);border-radius:12px;padding:1px 9px;cursor:pointer;color:var(--ink2);background:#fff;font-size:11.5px}
.chip.on{background:var(--accb);border-color:#b9d3f6;color:var(--acc)}
.list{max-height:calc(100vh - 260px);overflow:auto}
.ty{padding:8px 12px;border-bottom:1px solid var(--line2);cursor:pointer;border-left:3px solid transparent}
.ty:hover{background:#f8fafd}.ty.on{background:var(--accb);border-left-color:var(--acc)}.ty.off{opacity:.55}
.ty-h{display:flex;align-items:center;gap:6px}.ty-h .no{font-family:var(--mono);color:var(--mu);font-size:11px;width:30px;flex:none}
.ty-h .t{font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ty-h .n{font-family:var(--mono);font-size:11px;color:var(--ink2);flex:none}
.ty .ex,.ty .cs{margin:2px 0 0 52px;font-size:11px;color:var(--mu);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ty .ex{font-family:var(--mono);color:var(--ink2)}
.tag{font-size:10px;border:1px solid var(--line);border-radius:3px;padding:0 4px;color:var(--mu);flex:none}.tag.ai{color:#6b4fd0;border-color:#d9cff7;background:#f6f3ff}
.tag.ed{color:#b26a00;border-color:#f2d9a8;background:#fff8ea}.tag.er{color:var(--bad);border-color:#f1c4c2;background:#fdf2f1}
.det{padding:12px 14px}.det input.ti{font:600 14px var(--sans);border:1px solid transparent;border-radius:4px;padding:3px 6px;width:100%;color:var(--ink)}
.det input.ti:hover,.det input.ti:focus,.det textarea:focus{border-color:var(--line);outline:0}
.det textarea{width:100%;font:inherit;border:1px solid var(--line);border-radius:4px;padding:5px 8px;resize:vertical}
.row{display:flex;gap:12px;align-items:center;margin:6px 0 10px;flex-wrap:wrap}
.sec{margin-top:12px}.sec h4{margin:0 0 6px;font-size:12px;color:var(--ink2);font-weight:600}
.cmp{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border:1px solid var(--line);border-radius:4px;overflow:hidden}
.cmp>div{padding:6px 10px;font-family:var(--mono);font-size:12px;white-space:pre-wrap;word-break:break-word}
.cmp .hd{background:#f6f8fb;color:var(--mu);font-family:var(--sans);font-size:11px;padding:3px 10px;border-bottom:1px solid var(--line2)}.cmp .o{border-right:1px solid var(--line2)}
del{background:#f8c9c9;text-decoration:none;color:#b4232a;border-radius:2px}ins{background:#bfe6c9;text-decoration:none;color:#1e7b3c;border-radius:2px}
.mask{font-family:var(--sans);font-size:10.5px;background:#eef1f5;color:var(--mu);border:1px dashed #cdd4de;border-radius:3px;padding:0 4px}
.cases{display:flex;flex-wrap:wrap;gap:4px}.cc{font-family:var(--mono);font-size:11.5px;border:1px solid var(--line);border-radius:3px;padding:1px 7px;cursor:pointer;background:#fff}
.cc.on{background:var(--ink);color:#fff;border-color:var(--ink)}.cc.rep::after{content:" ★";color:#e3a21a}
.shot{border:1px solid var(--line);border-radius:4px;overflow:hidden}.shot img{display:block;max-width:100%}
.shot .cap{padding:3px 8px;background:#f6f8fb;font-size:11px;color:var(--mu);border-bottom:1px solid var(--line2)}
.noshot{padding:16px;color:var(--bad);background:#fdf2f1}
table.t{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)}
table.t th,table.t td{border-bottom:1px solid var(--line2);padding:5px 8px;text-align:left;vertical-align:top}
table.t th{background:#f6f8fb;color:var(--ink2);font-weight:500;position:sticky;top:44px}table.t td.m{font-family:var(--mono);font-size:11.5px;word-break:break-word}
tr.rs td{background:#f1f8f3}
.why{font-size:11px;border-radius:3px;padding:0 6px;white-space:nowrap;background:#eef1f5;color:var(--ink2)}
.why.mv{background:#eaf2fd;color:var(--acc)}.why.dt{background:#fff4d6;color:#8a5a00}.why.nm{background:#f3eefe;color:#6b4fd0}
.a4{width:min(794px,100%);margin:0 auto;background:#fff;border:1px solid var(--line);box-shadow:0 6px 24px -14px #0003;padding:48px 60px;font:13px/1.6 Calibri,"Segoe UI","Microsoft YaHei",sans-serif;color:#222}
.a4 h2{font-size:19px;margin:0 0 12px}.a4 table{border-collapse:collapse;width:100%;margin-bottom:14px;font-size:12px}
.a4 td,.a4 th{border:1px solid #c9ced6;padding:3px 8px;text-align:left}.a4 th{background:#f1f3f6}
.a4 h3{font-size:15px;color:#1f3864;margin:22px 0 2px}.a4 img{max-width:100%;border:1px solid #c9ced6}
.dlg{position:fixed;inset:0;background:#0006;display:grid;place-items:center;z-index:9}.dlg>div{background:#fff;border-radius:8px;padding:16px;width:min(680px,92vw)}
.dlg textarea{width:100%;height:240px;font:12px var(--mono)}
@media(max-width:1000px){.main{grid-template-columns:minmax(0,1fr)}}
@media print{header,.stats,.tabs,.warn,#v-list,#v-filt,#v-files{display:none!important}#v-doc{display:block!important}.a4{border:0;box-shadow:none;padding:0}}
</style></head><body>
<header><h1>保单附表差异汇总</h1><span class="hint" id="meta"></span><span class="sp"></span></header>
<div class="stats" id="stats"></div><div id="warns"></div>
<div class="tabs" id="tabs"></div>
<div class="view" id="v-list"><div class="main"><div class="panel"><div class="chips" id="lf"></div><div class="list" id="list"></div></div><div class="panel det" id="det"></div></div></div>
<div class="view hide" id="v-filt"></div>
<div class="view hide" id="v-files"></div>
<div class="view hide" id="v-doc"></div>
<script>
const D=__DATA__;
const $=s=>document.querySelector(s),esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const WHY={mv:"位置变化",dt:"仅日期",nm:"仅姓名",pn:"仅保单号",ws:"空格/断行",rule:"过滤规则"};
const INC=D.diffs.filter(g=>g.include);
let tab="list",cur=(INC[0]||D.diffs[0]||{}).id,curCase=null,ff="all",fpage=1;
const G=id=>D.diffs.find(g=>g.id===id);
const cases=g=>g.cases.length?g.cases.join(","):[...new Set(g.occ.map(o=>o.file))].join("、");
function head(){
  const cnt={};D.filtered.forEach(f=>cnt[f.why]=(cnt[f.why]||0)+1);
  $("#meta").textContent=D.runs+" · 生成于 "+D.at;
  $("#stats").innerHTML=`<div class="st"><b>${D.stats.length}</b><span>对比文件</span><div class="sub">${new Set(D.stats.map(s=>s.case)).size} 个用例</div></div>
   <div class="st"><b>${D.stats.reduce((a,s)=>a+s.raw,0)}</b><span>原始差异处</span></div>
   <div class="st"><b>${D.filtered.length}</b><span>再过滤</span><div class="sub">${Object.entries(cnt).map(([k,v])=>WHY[k]+" "+v).join(" · ")||"无"}</div></div>
   <div class="st"><b>${INC.length}</b><span>Difference</span><div class="sub">已写进交付文档</div></div>`;
  const w=[];if(D.errors.length)w.push("有 "+D.errors.length+" 个文件没读出来，见“文件”页");
  const ns=INC.filter(g=>!g.img).length;if(ns)w.push(ns+" 个 Difference 没能自动截图，交付文档里标了“需手动截图”");
  $("#warns").innerHTML=w.map(x=>`<div class="warn">${esc(x)}</div>`).join("");
  $("#tabs").innerHTML=[["list","Difference 列表",INC.length],["filt","已过滤",D.filtered.length],["files","文件",D.stats.length],["doc","交付文档预览",""]].map(([k,n,c])=>`<div class="tab ${k===tab?"on":""}" data-t="${k}">${n}${c!==""?`<i>${c}</i>`:""}</div>`).join("");
  document.querySelectorAll(".tab").forEach(e=>e.onclick=()=>{tab=e.dataset.t;render()});
}
function list(){
  const out=D.diffs.length-INC.length;
  $("#lf").innerHTML=`<span class="hint">按涉及用例数排序${out?" · 另有 "+out+" 个按你的要求没放进交付":""}</span>`;
  $("#list").innerHTML=D.diffs.map(g=>`<div class="ty ${g.id===cur?"on":""} ${g.include?"":"off"}" data-id="${g.id}"><div class="ty-h"><span class="no">${g.no?"D"+g.no:"—"}</span><span class="t">${esc(g.title)}</span>${g.img?"":'<span class="tag er">无截图</span>'}<span class="n">${g.cases.length||g.occ.length} 个用例</span></div>
   <div class="ex">${esc(g.mold||"（无）")} → ${esc(g.mnew||"（无）")}</div><div class="cs">Case ${esc(cases(g))}</div></div>`).join("")||'<div class="hint" style="padding:16px">没有</div>';
  document.querySelectorAll(".ty").forEach(e=>e.onclick=()=>{cur=e.dataset.id;curCase=null;render()});
}
function det(){
  const g=G(cur);if(!g){$("#det").innerHTML='<div class="hint" style="padding:20px">没有需要交付的差异：所有变化都被过滤了，或者对比结果里没有差异。可在“已过滤”页检查。</div>';return}
  const c=curCase!=null?curCase:g.rep,o=g.occ.find(x=>x.case===c)||g.occ[0];
  $("#det").innerHTML=`<div class="hint" style="font-family:var(--mono)">${g.no?"Difference "+g.no:"没放进交付"} · ${g.hits} 处 · ${g.cases.length||g.occ.length} 个用例</div>
  <div style="font-size:14px;font-weight:600;margin:2px 0 8px">${esc(g.title)}</div>
  <div class="sec"><h4>变化内容</h4><div class="cmp"><div class="hd o">旧版（基线）</div><div class="hd">新版</div><div class="o">${g.hold||'<span class="hint">（旧版没有）</span>'}</div><div>${g.hnew||'<span class="hint">（新版没有这段）</span>'}</div></div>
   ${g.merged?`<div class="hint" style="margin-top:4px">已合并 ${g.merged.length} 个相似的变化：${g.merged.map(m=>esc(m.mold+" → "+m.mnew)).join("；")}</div>`:""}</div>
  ${g.desc?`<div class="sec"><h4>说明</h4><div>${esc(g.desc)}</div></div>`:""}
  <div class="sec"><h4>Sample case <span class="hint" style="font-weight:400">点一个看它的原文；★ 是交付用的截图</span></h4><div class="cases">${g.occ.map(x=>x.case).filter((x,i,a)=>a.indexOf(x)===i).map(x=>`<span class="cc ${x===c?"on":""} ${x===g.rep?"rep":""}" data-c="${x}">${x==null?"?":x}</span>`).join("")}</div></div>
  <div class="sec"><h4>Case ${esc(o.case)} 的原文 <span class="hint" style="font-weight:400">${esc(o.file)} · 旧第 ${o.l||"-"} 行 / 新第 ${o.r||"-"} 行${o.count>1?" · 本文件出现 "+o.count+" 次":""}</span></h4>
   <div class="cmp"><div class="o">${esc(o.old)||'<span class="hint">（无）</span>'}</div><div>${esc(o.new)||'<span class="hint">（无）</span>'}</div></div></div>
  <div class="sec"><h4>交付截图（新版 PDF）</h4>${g.img?`<div class="shot"><div class="cap">Case ${esc(g.rep)} · ${esc(g.shot_pdf||"")} · 第 ${g.shot_page} 页</div><img src="${g.img}" alt="Case ${esc(g.rep)} 新版 PDF 截图"></div>`:`<div class="shot noshot">需手动截图：${esc(g.shot_err||"没有截图")}</div>`}</div>`;
  document.querySelectorAll(".cc").forEach(b=>b.onclick=()=>{curCase=b.dataset.c==="null"?null:+b.dataset.c;det()});
}
function filt(){
  const cnt={};D.filtered.forEach(f=>cnt[f.why]=(cnt[f.why]||0)+1);
  const L=D.filtered.filter(f=>ff==="all"||f.why===ff),P=200,show=L.slice(0,fpage*P);
  $("#v-filt").innerHTML=`<div class="chips" style="background:#fff;border:1px solid var(--line);border-bottom:0;border-radius:6px 6px 0 0">${[["all","全部 "+D.filtered.length]].concat(Object.entries(cnt).map(([k,v])=>[k,WHY[k]+" "+v])).map(([k,n])=>`<span class="chip ${ff===k?"on":""}" data-f="${k}">${n}</span>`).join("")}
   <span class="sp"></span><span class="hint">过滤错了，在终端里告诉 AI 第几条要放回来</span></div>
  <table class="t"><thead><tr><th style="width:44px">#</th><th style="width:90px">原因</th><th style="width:56px">用例</th><th>旧版</th><th>新版</th><th style="width:240px">判断依据</th></tr></thead><tbody>
  ${show.map(f=>`<tr><td class="m">${D.filtered.indexOf(f)+1}</td><td><span class="why ${f.why}">${WHY[f.why]||f.why}</span></td><td class="m">${esc(f.case)}</td><td class="m">${esc(f.old)}</td><td class="m">${esc(f.new)}</td><td class="hint">${esc(f.detail)}<br>${esc(f.file)} · 行 ${f.l||"-"}/${f.r||"-"}</td></tr>`).join("")}
  ${L.length>show.length?`<tr><td colspan="6"><button class="btn" id="more">再显示 ${Math.min(P,L.length-show.length)} 条（共 ${L.length}）</button></td></tr>`:""}${!L.length?'<tr><td colspan="6" class="hint">没有</td></tr>':""}</tbody></table>`;
  document.querySelectorAll("#v-filt .chip").forEach(e=>e.onclick=()=>{ff=e.dataset.f;fpage=1;filt()});
  if($("#more"))$("#more").onclick=()=>{fpage++;filt()};
}
function files(){
  $("#v-files").innerHTML=(D.errors.length?`<div class="warn" style="margin:0 0 10px">${D.errors.map(esc).join("<br>")}</div>`:"")+
  `<table class="t"><thead><tr><th>文件</th><th>用例</th><th>运行</th><th>原始差异</th><th>剩余变化</th><th>认出的姓名</th></tr></thead><tbody>${D.stats.map(s=>`<tr><td class="m">${esc(s.file)}</td><td class="m">${esc(s.case)}</td><td class="m">${esc(s.run)}</td><td class="m">${s.raw}</td><td class="m">${s.kept}</td><td class="m">${s.names}</td></tr>`).join("")}</tbody></table>`;
}
function doc(){
  $("#v-doc").innerHTML=`<div class="a4">
   <h2>Policy Schedule Regression — Comparison Result</h2>
   <table><tr><th>Run</th><td>${esc(D.runs)}</td><th>Generated</th><td>${esc(D.at)}</td></tr><tr><th>Files compared</th><td>${D.stats.length}</td><th>Differences</th><td>${INC.length}</td></tr></table>
   ${INC.length?`<table><tr><th>#</th><th>Difference</th><th>Cases</th></tr>${INC.map(g=>`<tr><td>${g.no}</td><td>${esc(g.title)}</td><td>${g.cases.length||g.occ.length}</td></tr>`).join("")}</table>`:"<p>No difference to report.</p>"}
   ${INC.map(g=>`<h3>Difference ${g.no}: ${esc(g.title)}</h3><div>Sample case : ${esc(cases(g))}</div>${g.img?`<img src="${g.img}" alt="">`:`<p style="color:#c4302b">［需手动截图：${esc(g.shot_err||"")}］</p>`}${g.desc?`<p>${esc(g.desc)}</p>`:""}`).join("")}</div>`;
}
function render(){head();["list","filt","files","doc"].forEach(k=>$("#v-"+k).classList.toggle("hide",k!==tab));if(tab==="list"){list();det()}if(tab==="filt")filt();if(tab==="files")files();if(tab==="doc")doc()}
render();
</script></body></html>"""


# ------------------------------------------------------------------ 流程：读取 → 过滤归并 → 截图 → 产出三份文件
def pipeline(files, root, outdir, note, log=out):
    c, mem = cfg(), load_mem()
    log("读取 " + str(len(files)) + " 个对比文件…")
    diffs, filtered, stats, errors = analyze_all(files, root, mem, c)
    if not stats:
        raise UserError("一个对比文件都没读出来：" + "；".join(errors[:3]))
    apply_mem(diffs, mem)
    parents = []
    for f in files:
        for p in (Path(f).parent, Path(f).parent.parent):
            if p not in parents:
                parents.append(p)
    make_shots(diffs, stats, c, outdir, [Path(x) for x in c["pdf_dirs"]] + parents[:6], log)
    runs = sorted({s["run"] for s in stats})
    data = {"at": now(), "runs": "、".join(runs[:3]) + ("等 " + str(len(runs)) + " 次运行" if len(runs) > 3 else ""), "note": note,
            "root": str(root or ""), "inputs": [str(f) for f in files], "outdir": str(outdir),
            "diffs": diffs, "filtered": filtered, "stats": stats, "errors": errors}
    ok = build(data, outdir, log)
    c = cfg()
    c["last_out"] = str(outdir)
    save_cfg(c)
    for_ai(data, outdir, log)
    return ok


def for_ai(data, outdir, log):
    """给 AI 的摘要：每个 Difference 的内容、例子，和需要复查的过滤。"""
    amt = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+\.\d{2}\b")
    sus = [f for f in data["filtered"] if (f["why"] == "dt" and (amt.search(f["old"]) or amt.search(f["new"]))) or f["why"] in ("nm", "rule")]
    js = {"outdir": str(outdir), "products": [str(outdir / p) for p in PRODUCTS],
          "differences": [{"no": g["no"], "id": g["id"], "include": g["include"], "title": g["title"], "title_src": g["title_src"], "desc": g["desc"],
                           "kind": {"chg": "内容改变", "add": "新版新增", "del": "新版缺少"}[g["kind"]], "cases": g["cases"], "hits": g["hits"],
                           "old": g["mold"], "new": g["mnew"], "examples": [{"case": o["case"], "old": o["old"], "new": o["new"]} for o in g["occ"][:3]],
                           "screenshot": "ok" if g.get("shot") else g.get("shot_err")} for g in data["diffs"]],
          "filtered_count": {k: sum(1 for f in data["filtered"] if f["why"] == k) for k in WHY},
          "filtered_to_review": [{"no": data["filtered"].index(f) + 1, "why": WHY[f["why"]], "case": f["case"], "old": f["old"], "new": f["new"]} for f in sus[:40]],
          "errors": data["errors"]}
    p = outdir / ".diffsum" / "for_ai.json"
    write_json(p, js)
    log("")
    log("共 " + str(len(data["diffs"])) + " 个 Difference（放进交付 " + str(sum(1 for g in data["diffs"] if g["include"])) + " 个），再过滤 " + str(len(data["filtered"])) + " 处；"
        + str(sum(1 for g in data["diffs"] if g["title_src"] == "自动")) + " 个还是自动标题")
    log("给 AI 的摘要：" + str(p))


def cmd_start(a):
    c = cfg()
    if a.pick_pdf:
        p = pick_dir("选择新版 PDF 所在的文件夹")
        if not p:
            raise UserError("没有选文件夹")
        c["pdf_dirs"] = [p] + [x for x in c["pdf_dirs"] if x != p][:4]
        save_cfg(c)
        out("已记住新版 PDF 文件夹：" + p)
    files, note, outdir = choose_inputs(a, c)
    out("这次汇总：" + note)
    root = cfg()["root"] if not (a.files or a.pick_files) else None
    ok = pipeline(files, root, Path(a.out) if a.out else outdir, note)
    sys.exit(0 if ok else 1)


def _resolve(ids, data):
    by_no = {"D" + str(g["no"]): g["id"] for g in data["diffs"] if g.get("no")}
    by_id = {g["id"] for g in data["diffs"]}
    res = []
    for x in ids:
        x = str(x).strip()
        k = by_no.get(x.upper(), x)
        if k not in by_id:
            raise UserError("没有这个 Difference：" + x + "（用 for_ai.json 里的 id，或 D1、D2 这样的编号）")
        res.append(k)
    return res


def cmd_edit(a):
    c = cfg()
    outdir = Path(a.out or c.get("last_out") or "")
    data = read_json(outdir / ".diffsum" / "data.json", None)
    if not data:
        raise UserError("还没有汇总过，先运行 start")
    raw = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8-sig")
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise UserError("没有读到修改内容（要一段 JSON）")
    js = json.loads(m.group(0))
    ch, by = js.get("changes", js), js.get("by", "人工")
    mem = load_mem()
    ent = lambda i: mem["diff"].setdefault(i, {})
    n = 0
    for i in _resolve(ch.get("exclude", []), data):
        ent(i)["exclude"] = True
        n += 1
    for i in _resolve(ch.get("include", []), data):
        ent(i).pop("exclude", None)
        n += 1
    for k, v in (ch.get("title") or {}).items():
        e = ent(_resolve([k], data)[0])
        if by == "AI" and e.get("title_src") == "人工":
            out("  跳过 " + k + "：标题是用户改的，AI 不覆盖")
            continue
        e.update(title=str(v).strip(), title_src=by, at=now())
        n += 1
    for k, v in (ch.get("desc") or {}).items():
        e = ent(_resolve([k], data)[0])
        if by == "AI" and e.get("desc_src") == "人工":
            continue
        e.update(desc=str(v).strip(), desc_src=by)
        n += 1
    for k, v in (ch.get("rep") or {}).items():
        ent(_resolve([k], data)[0])["rep"] = int(v)
        n += 1
    fl = data["filtered"]
    for k in ch.get("restore_no", []):   # 页面“已过滤”里的序号
        if not 1 <= int(k) <= len(fl):
            raise UserError("已过滤里没有第 " + str(k) + " 条（共 " + str(len(fl)) + " 条）")
        ch.setdefault("restore", []).append(fl[int(k) - 1]["fid"])
    for f in ch.get("restore", []):
        if f not in mem["restore"]:
            mem["restore"].append(f)
        mem["ignore"] = [x for x in mem["ignore"] if x != f]
        n += 1
    for i in _resolve(ch.get("ignore", []), data):
        if i not in mem["ignore"]:
            mem["ignore"].append(i)
        ent(i)["exclude"] = True
        n += 1
    for grp in ch.get("merge", []):
        ids = _resolve(grp, data)
        if len(ids) >= 2:
            mem["merge"] = [g for g in mem["merge"] if not set(g) & set(ids)] + [ids]
            n += 1
    for i in _resolve(ch.get("unmerge", []), data):
        mem["merge"] = [g for g in mem["merge"] if i not in g]
        n += 1
    write_json(MEM_F, mem)
    out("已记录 " + str(n) + " 项修改，重新生成…")
    ok = pipeline([Path(x) for x in data["inputs"]], data.get("root") or None, outdir, data.get("note", ""))
    sys.exit(0 if ok else 1)


def cmd_check(a):
    c = cfg()
    p = a.out or c.get("last_out")
    if not p:
        out("✗ 还没有生成过产物，先运行 start")
        sys.exit(1)
    sys.exit(0 if verify(Path(p)) else 1)


def cmd_diag(a):
    """只输出统计数字，不输出任何保单内容，可以放心发给别人看。"""
    data = read_json(Path(a.out or cfg().get("last_out") or "") / ".diffsum" / "data.json", None)
    if not data:
        raise UserError("还没有汇总过，先运行 start")
    out("diffsum " + VERSION + " · Python " + sys.version.split()[0])
    for mod in ("fitz", "docx", "openpyxl", "PIL", "tkinter"):
        try:
            __import__(mod)
            out("  " + mod + "：有")
        except ImportError:
            out("  " + mod + "：没有")
    out("文件 " + str(len(data["stats"])) + " 个，读不出 " + str(len(data["errors"])) + " 个")
    out("原始差异 " + str(sum(s["raw"] for s in data["stats"])) + " 处，剩余 " + str(sum(s["kept"] for s in data["stats"])) + " 处")
    out("再过滤：" + "，".join(WHY[k] + " " + str(sum(1 for f in data["filtered"] if f["why"] == k)) for k in WHY))
    out("Difference " + str(len(data["diffs"])) + " 个：新增 " + str(sum(1 for g in data["diffs"] if g["kind"] == "add")) + "，缺少 " +
        str(sum(1 for g in data["diffs"] if g["kind"] == "del")) + "，改变 " + str(sum(1 for g in data["diffs"] if g["kind"] == "chg")))
    out("截图成功 " + str(sum(1 for g in data["diffs"] if g.get("shot"))) + " 个；失败原因：" +
        "；".join(sorted({(g.get("shot_err") or "")[:40] for g in data["diffs"] if not g.get("shot")})))
    out("每个文件（原始 / 剩余 / 认出姓名数）：")
    for s in data["stats"][:200]:
        out("  case " + str(s["case"]) + " · " + str(s["raw"]) + " / " + str(s["kept"]) + " / " + str(s["names"]))
    for e in data["errors"]:
        out("  读不出：" + re.sub(r"[^\s：（）]+\.html?", "<文件>", e)[:160])


# ------------------------------------------------------------------ 自检：造一批模拟对比文件，验证过滤、归并和三份产物
def cmd_selftest(a):
    global HOME, CFG_F, MEM_F, NAMES_F
    tmp = Path(tempfile.mkdtemp(prefix="diffsum_test_"))
    HOME = tmp / "home"
    CFG_F, MEM_F, NAMES_F = HOME / "config.json", HOME / "memory.json", HOME / "names.txt"
    fill = ["Clause " + str(i) + ": the benefit described in this section is payable as stated." for i in range(1, 9)]
    prov_o, prov_n = "Extended Benefit - LBE VHIS-FPC V042024H", "Extended Benefit - LBE VHIS-FPC V112026H"
    note = "Important Notes to Policy Owner please read carefully before signing"
    C = {
        1: (["POLICY SCHEDULE", "Policy Owner: CHAN TAI MAN", "Issue Date  2026 11 06", note] + fill[:2] + [prov_o] + fill[2:4] + [prov_o] + fill[4:6] + [prov_o] +
            ["Hospital  Cash   Benefit"] + fill[6:7] + ["Premium Due 06/11/2026 HKD 1,250.00"] + fill[7:] +
            ["This policy is issued subject to the terms and conditions of the", "policy contract.", "End of schedule"],
            ["POLICY SCHEDULE", "Policy Owner: WONG SIU MING", "Issue Date  2026 11 20"] + fill[:2] + [prov_n] + fill[2:4] + [prov_n] + fill[4:6] + [prov_n] +
            ["Hospital Cash Benefit"] + fill[6:7] + ["Premium Due 20/11/2026 HKD 1,250.00"] + fill[7:] +
            ["This policy is issued subject to the terms and", "conditions of the policy contract.", "End of schedule", note]),
        2: (["POLICY SCHEDULE", "Plan Name: VHIS Flexi Plan"] + fill[:3] + [prov_o] + fill[3:6] + ["Premium Due 06/11/2026 HKD 1,250.00"] + fill[6:],
            ["POLICY SCHEDULE", "Plan Name: VHIS Flexi Plus"] + fill[:3] + [prov_n] + fill[3:6] + ["Premium Due 20/11/2026 HKD 1,350.00"] + fill[6:]),
        3: (["POLICY SCHEDULE", "Dear Mr CHAN TAI MAN,"] + fill[:4] + ["Hospital Cash Rider (HCR2)"] + fill[4:],
            ["POLICY SCHEDULE", "Dear Mr LEE KA HO,"] + fill[:4] + fill[4:]),
    }
    run = tmp / "Different" / "2026-11-25_101010" / "report"
    run.mkdir(parents=True)
    for n, (o, w) in C.items():
        h = difflib.HtmlDiff(wrapcolumn=58).make_file(o, w, "old", "new")
        (run / ("Case" + str(n) + "_PolSchedule-82600_1613391" + str(n) + "_20261125101010(different_after_ignore).html")).write_text(h, encoding="utf-8")
    res = []
    ok = lambda name, cond, detail="": res.append((bool(cond), name, detail))
    files = find_html(tmp / "Different")
    ok("找到 3 个对比文件", len(files) == 3, len(files))
    diffs, filt, stats, errs = analyze_all(files, tmp / "Different", load_mem(), cfg())
    ok("没有读取错误", not errs, errs)
    W = lambda case, why: [f for f in filt if f["case"] == case and f["why"] == why]
    ok("条款变化归成一个 Difference，Sample case 1,2", any(g["cases"] == [1, 2] and "V112026H" in g["mnew"] for g in diffs), [(g["cases"], g["mnew"][:40]) for g in diffs])
    pv = next((g for g in diffs if "V112026H" in g["mnew"]), None)
    ok("同一文件重复 3 次只算一处，合计 4 处", pv and pv["hits"] == 4 and len(pv["occ"]) == 2, pv and pv["hits"])
    ok("只差日期的行被过滤（2 处）", len(W(1, "dt")) == 2, [f["old"] for f in W(1, "dt")])
    ok("Policy Owner 后的姓名被过滤", any("Policy Owner" in f["old"] for f in W(1, "nm")), [f["old"] for f in filt if f["case"] == 1])
    ok("Dear Mr 后的姓名被过滤", any("Dear" in f["old"] for f in W(3, "nm")))
    ok("挪了位置的段落被过滤", any("Important Notes" in (f["old"] + f["new"]) for f in W(1, "mv")))
    ok("只差空格 / 断行被过滤", len(W(1, "ws")) >= 2, [f["old"] for f in W(1, "ws")])
    pm = [g for g in diffs if "1,350.00" in g["mnew"]]
    ok("日期旁边的金额变化保留，日期被替换", pm and "⟨日期⟩" in pm[0]["mold"] and "1,250.00" in pm[0]["mold"], pm and pm[0]["mold"])
    ok("产品名变化不当作姓名", any("Flexi Plus" in g["mnew"] for g in diffs))
    ok("新版缺少的附加险保留", any(g["kind"] == "del" and "HCR2" in g["mold"] for g in diffs))
    ok("没有多余的 Difference（应为 4 个）", len(diffs) == 4, [g["mold"][:30] + " → " + g["mnew"][:30] for g in diffs])
    # 修改记录：标题、排除、过滤规则，重新生成后带上
    write_json(MEM_F, {"diff": {pv["id"]: {"title": "Provision is different", "title_src": "AI"}}, "ignore": [], "restore": [W(1, "dt")[0]["fid"]], "merge": []})
    d2, f2, s2, _ = analyze_all(files, tmp / "Different", load_mem(), cfg())
    apply_mem(d2, load_mem())
    ok("AI 标题按变化内容带上", any(g["title"] == "Provision is different" for g in d2))
    ok("恢复的过滤回到 Difference", len(d2) == 5 and len(f2) == len(filt) - 1, (len(d2), len(f2)))
    # 三份产物
    outdir = tmp / "Different" / OUT_DIR_NAME / "test"
    try:
        okp = pipeline(files, tmp / "Different", outdir, "自检", log=lambda *x: None)
        ok("三份产物都生成并通过校验", okp)
        page = (outdir / "差异汇总.html").read_text(encoding="utf-8")
        ok("页面里有全部 Difference", page.count('"id":') >= 5 and "Provision is different" in page)
        with zipfile.ZipFile(outdir / "交付文档.docx") as z:
            ok("没有截图时 Word 里写“需手动截图”", "需手动截图" in z.read("word/document.xml").decode("utf-8"))
    except UserError as e:
        ok("三份产物都生成（缺少库）", False, str(e))
    for good, name, detail in res:
        out(("✓ " if good else "✗ ") + name + ("" if good else "   ← " + str(detail)[:300]))
    bad = sum(1 for r in res if not r[0])
    out("\n" + ("全部通过" if not bad else str(bad) + " 项没通过") + "（" + str(len(res)) + " 项）· 测试文件在 " + str(tmp))
    sys.exit(1 if bad else 0)


def main():
    import argparse
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="diffsum", description="保单附表差异汇总 " + VERSION)
    sp = ap.add_subparsers(dest="cmd")
    p = sp.add_parser("start", help="汇总对比结果，产出 差异汇总.html + 交付文档.docx + 交付文档.xlsx")
    p.add_argument("--files", nargs="+", help="文件夹或文件（可多个），不给就用上次的文件夹里最新的一次运行")
    p.add_argument("--latest", type=int, default=1, help="用最新几次运行（默认 1）")
    p.add_argument("--pick", action="store_true", help="弹窗重新选对比结果所在的文件夹")
    p.add_argument("--pick-files", action="store_true", help="弹窗多选对比文件")
    p.add_argument("--pick-pdf", action="store_true", help="弹窗选新版 PDF 所在的文件夹")
    p.add_argument("--out", help="产物放在哪（默认 <文件夹>\\差异汇总\\<运行名>）")
    p = sp.add_parser("edit", help="应用修改（页面复制来的 JSON，或 AI 写的标题/说明/合并），然后重新生成")
    p.add_argument("file", nargs="?", default="-", help="JSON 文件，- 表示从输入读取")
    p.add_argument("--out")
    for name in ("check", "diag"):
        sp.add_parser(name).add_argument("--out")
    sp.add_parser("selftest")
    sp.add_parser("where")
    a = ap.parse_args()
    if a.cmd == "where":
        out("设置：" + str(CFG_F) + "\n修改记录：" + str(MEM_F) + "\n姓名名单：" + str(NAMES_F) + "\n上次产物：" + str(cfg().get("last_out", "")))
        return
    fn = {"start": cmd_start, "edit": cmd_edit, "check": cmd_check, "diag": cmd_diag, "selftest": cmd_selftest}.get(a.cmd)
    if not fn:
        ap.print_help()
        return
    try:
        fn(a)
    except UserError as e:
        out("✗ " + str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
# ==== DIFFSUM_TOOL_END ====
```
