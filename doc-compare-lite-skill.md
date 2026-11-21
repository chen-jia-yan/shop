---
name: doc-compare-assist
description: 文档对比复核助手。启动原有的的对比脚本（或读取已生成的） total / ignore 对比结果，回到 baseline 和新版 PDF 里逐条复核（像人工复核一样）：哪些是真实的不同点、哪些是误报、哪些被误过滤或漏掉；整理成一个可以左右对照的核实页面，人确认后一键生成发给开发的 Word 和 Excel（每处差异附新旧 PDF 截图，红框标出不同处，并写明说明）。用户说“复核对比结果”“对比这两份 PDF”“出一份差异文档给开发”时使用。
---

# 文档对比复核助手

用**原有的对比脚本**把 Policy Schedule 这类产品 PDF的新版本和 baseline 做了对比，生成了：

- **total**：全部差异（左 baseline、右新版，Python difflib 生成的 html）
- **ignore**：他过滤掉不重要内容后剩下的差异

你的工作是在他的结果之后做**复核**：回到两份 PDF 里逐条核对，指出哪些是真实的不同点、哪些有问题，最后交给开发一份能直接定位的差异文档。

这个文件里自带一个工具脚本（文件最后），负责读 PDF、读他的 html、截图、生成页面和文档。**你负责判断和沟通。**

## 铁律

1. **只运行、不修改他的对比脚本项目。** 按用户确认过的命令启动它，不改它的代码和配置。
2. **值不能错。** 原值、新值只能来自工具读出的内容，不改写、不补全、不换算；说明里引用数字也要照抄。
3. **不删差异，只标注。** 你认为不重要的标成“已排除”，它们仍在页面附录里，可以改回来。
4. **人确认后才出交付文档。** 交付文档由用户在核实页面里点“生成交付文档”产生。
5. **截图找不到就写“截图待补”，** 不编造位置。

## 第 0 步：释放工具（每次调用都做）

把本文件最后一段代码释放成 `dca_tool.py`。`<本文件路径>` 换成这个 SKILL.md 的实际路径：

```bash
python -c "import pathlib,sys;t=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8');s=t.rsplit('# ==== DCA_TOOL'+'_BEGIN ====',1)[1].split('# ==== DCA_TOOL'+'_END ====')[0];d=pathlib.Path.home()/'.dca';d.mkdir(exist_ok=True);(d/'dca_tool.py').write_text(s,encoding='utf-8');print(d/'dca_tool.py')" "<本文件路径>"
python ~/.dca/dca_tool.py check
```

Windows 的 cmd 里把 `~/.dca` 写成 `%USERPROFILE%\.dca`。缺库时告诉用户运行 `pip install pymupdf python-docx openpyxl pillow`，征得同意再装。下文 `dca` 指 `python ~/.dca/dca_tool.py`。

## 第 1 步：运行他的对比脚本，拿到 total / ignore

调用这个 skill 时，默认要**先替用户把他的对比脚本跑一遍**，再整理。

**① 第一次使用：问清楚怎么启动（以后不用再问）**

运行 `dca setup --show`。如果显示“还没有设置”，就问用户这几件事，可以一次问完：

- 平时怎么启动对比？要在终端里输入的那条命令，例如 `python main.py`，或者 `python run.py --plan TestPlan000015`。如果平时是双击某个 .bat 或 .py，就问那个文件的完整路径。
- 在哪个文件夹里运行？也就是他的项目文件夹。
- 跑完后，total / ignore 会出现在哪个文件夹？
- baseline 和新版 PDF 放在哪里？

然后保存：

```bash
dca setup --command "<启动命令>" --cwd "<项目文件夹>" --results "<结果文件夹>" --pdf "<PDF 文件夹>"
# 新旧 PDF 分在两个文件夹时，把 --pdf 换成：--baseline "<旧版文件夹>" --new "<新版文件夹>"
```

用户不知道怎么启动的话，可以请他打开项目文件夹，你帮他看看：找 README，或者 `main.py`、`run*.py`、`*.bat` 这类入口文件。**找到后先把你推断的命令给他确认，再保存**，不要自己猜着去运行。

**② 运行并等待**

```bash
dca launch                         # 在后台启动他的脚本，命令马上返回
dca launch-status --wait 500       # 等它跑完，最多等 500 秒；还没跑完就再运行一次
```

- 等待期间，每次 `launch-status` 后都简短告诉用户进度，比如“还在运行，已经 12 分钟”。
- **完成**时，会打印这次新生成结果所在的文件夹，接着进入下一步。
- **失败**时，会打印问题和他脚本最后 30 行的输出。把关键报错给用户看，问他怎么处理。不要去改他的项目。
- 他的脚本如果需要在窗口里手动输入、点按钮，就没法自动跑。这种情况请用户手动运行，跑完告诉你结果在哪里，然后直接进入下一步。
- 用户说“已经跑过了，不用再跑”，就跳过这一步。

**③ 配对**

```bash
dca scan --results "<launch-status 打印的结果文件夹>" --pdf "<PDF 文件夹>"
# 新旧 PDF 分在两个文件夹时：--baseline "<旧版文件夹>" --new "<新版文件夹>"
# 只有 PDF、没有他的结果时：只给 --pdf（会直接对比两份 PDF）
```

PDF 位置用 `setup` 里保存的。`scan` 会按 Case 编号把 total、ignore、baseline PDF、新版 PDF 归成一组，并判断哪个是 baseline。把它打印的表格给用户看；**有“请确认”或“没有使用”的，先问清楚**。记下打印的“输出文件夹”，下文写作 `<out>`。

## 第 2 步：读取并复核

```bash
dca extract --out <out>
```

工具做的事，就像人工复核：

1. **读他的结果**：从 ignore（他认为要关注的）和 total（全部）里读出每一条差异的原值、新值、行号。
2. **读两份 PDF**：逐行读出文字、页码和位置。
3. **逐条回 PDF 核对**，每条得到一个复核结论：
   - ignore 里的每一条：在两份 PDF 里找到对应的行，确认两边是否**真的不同**。如果两边其实一样，就是提取或排版造成的**误报**；如果在 PDF 里找不到，或只是位置挪了，就标成**请确认**。
   - total 里有、ignore 里没有的（**被他过滤掉的**）：看是不是只是日期、人名。如果是内容变化，可能是**被误过滤**了，标**请确认**。
   - 两份 PDF 直接对比有、他的 total 里也没有的（**他漏掉的**）：如果是内容变化，标**请确认**。
4. **给建议**：每条给出 真实变化 / 请确认 / 已排除，以及一句复核理由。

打印里如果出现“扫描页（没有文字，未比较）”，要告诉用户这些页没有比较（例如 93 页以后是扫描件），不能说成“没有差异”。

## 第 3 步：你逐条判断，写说明

```bash
dca list --out <out> --verdict confirm                 # 先看拿不准的
dca list --out <out> --verdict real                    # 再看真实变化
dca list --out <out> --origin filtered --limit 200     # 抽查被他过滤掉的，确认没有误伤
```

每条会显示来源、原值、新值、变化的片段和复核理由。判断标准是：**这处变化会不会影响文档内容**。

- **日期**：常写成 `2026 11 20`、`2024 11 20`，而且经常紧跟在金额后面，比如 `587.85 2026 11 20`。只有日期变了才排除；金额也变了，就是真实变化。
- **人名**：中文姓名，或者 `NICHOLSPUN`、`ELIZABETHACP` 这种名和姓连写的大写英文。只是人名变了就排除。拿不准的保持“请确认”。
- **只差空格或折行**：排除。

改 `<out>/.dca/review.json`，每条只改下面这几个键，`sig` 不要动：

- `verdict`：`real`（真实变化）/ `exclude`（排除）/ `confirm`（请确认）
- `field`：字段名，例如 `Annual Premium 年缴保费`。看不出来就留空，不要编。
- `note`：只给 `real` 的条目写，一两句中文：哪里不同、差多少（照抄数值），以及让开发检查什么。不写没根据的推测。

条目很多时，先按相同的变化模式成批判断，再细看剩下的。

## 第 4 步：打开核实页面，等用户确认

```bash
dca shots --out <out>                          # 给真实变化 / 请确认的条目截新旧两张图
dca review --out <out> --title "<文档标题>"      # 后台启动核实页面并打开浏览器，命令马上返回
```

告诉用户：

> 共 N 条：真实变化 X 条、请确认 Y 条、已排除 Z 条（其中误报 A 条、被过滤的日期人名 B 条……）。核实页面已经打开：每条可以点“是真实变化 / 不算”，字段名和说明可以直接改，改动会自动保存。确认没问题后，点左下角“**生成交付文档**”，Word 和 Excel 会直接生成在 `<out>/交付/` 里。

然后停下，等用户。用户回来后运行 `dca status --out <out>`，汇报以下几项：
- 生成了几处差异、涉及几个 Case；
- 截图待补几张；
- 还有几条“请确认”没有处理；
- 文件的位置。

截图待补的，告诉用户在 PDF 里手工截一张替换就行。

## 之后还要改

- 再改结论或说明：运行 `dca review --out <out> --reopen`，在页面里改完后重新点“生成交付文档”。
- 新的一批文件：从第 1 步重新开始，会生成新的输出文件夹。
- 用户只想看看、不改：双击 `<out>/索引.html`，页面是只读的。

## 输出文件夹里有什么

- `索引.html`：核实页面。
- `交付/`：Word 和 Excel。
- `.dca/`：隐藏文件夹，放工具的数据和截图，用户不用管。

## 工具代码（第 0 步释放，不要手动修改）

```python
# ==== DCA_TOOL_BEGIN ====
"""文档对比助手 dca_tool.py（由 SKILL.md 释放出来；要改请改 SKILL.md，下次调用会重新释放）

命令：check / scan / inspect / extract / list / shots / build / run / deliver
"""
import argparse
import datetime
import difflib
import html as _html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

VERSION = "2026.11.21"
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MAX_ROWS = 30000          # 每份 PDF 最多放进全文对照的行数（防止页面过大）
MAX_LINE = 1500           # 单行最多保留的字符数
BIG_HTML = 15 * 1024 * 1024   # 他的 html 超过 15MB 时，索引页里不自动加载


# ------------------------------------------------------------------ 通用

def die(msg):
    print("错误：" + msg)
    sys.exit(2)


def need(mod, pip):
    try:
        return __import__(mod)
    except ImportError:
        die(f"缺少 {pip}，请运行：pip install {pip}")


def norm(s):
    """比较用：全角转半角、去掉所有空白、小写。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def clean(s):
    s = (s or "").replace("\u00a0", " ").replace("\t", " ").replace("\u3000", " ")
    return re.sub(r" {3,}", "  ", s).strip()[:MAX_LINE]


def nat(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(s))]


def jload(p, default=None):
    p = Path(p)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8-sig"))


def jsave(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def read_any(path):
    raw = Path(path).read_bytes()
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
    for enc in ([m.group(1).decode("ascii", "ignore")] if m else []) + ["utf-8-sig", "gb18030", "big5"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def rel(p, start):
    try:
        return os.path.relpath(str(p), str(start)).replace("\\", "/")
    except ValueError:          # 不在同一个盘
        return Path(p).resolve().as_uri()


def W(out):
    """工作数据放在输出文件夹里的隐藏文件夹 .dca，用户只需要看 索引.html 和 交付/。"""
    return Path(out) / ".dca"


def make_work(out):
    w = W(out)
    w.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        try:
            import subprocess
            subprocess.run(["attrib", "+h", str(w)], capture_output=True)
        except Exception:
            pass
    return w


def save_case(out, i, obj):
    """每个 Case 一个数据文件，索引页按需加载；Python 读回时去掉外面的 DCA_CASE( );"""
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (W(out) / f"c{i}.js").write_text("DCA_CASE(" + txt + ");", encoding="utf-8")


def load_case(out, i):
    p = W(out) / f"c{i}.js"
    if not p.is_file():
        return None
    t = p.read_text(encoding="utf-8")
    return json.loads(t[len("DCA_CASE("):t.rindex(");")].replace("<\\/", "</"))


def batch_dir(a):
    d = Path(a.out)
    if not (W(d) / "batch.json").is_file():
        die(f"{d} 不是对比整理的输出文件夹（里面没有 .dca/batch.json），请先运行 scan")
    return d


# ------------------------------------------------------------------ 第 2 步：盘点、配对

CASE_RE = re.compile(r"case\s*[-_ ]?\s*0*(\d+)", re.I)
ROLE_OLD = re.compile(r"(?<![a-z])(baseline|base|old|expected|exp|旧版?|基线)(?![a-z])", re.I)
ROLE_NEW = re.compile(r"(?<![a-z])(new|actual|act|latest|新版?)(?![a-z])", re.I)
DATE_IN_NAME = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")


def case_key(*names):
    for n in names:
        m = CASE_RE.search(str(n or ""))
        if m:
            return f"Case{int(m.group(1))}"
    return None


def doc_key(stem):
    s = re.sub(r"20\d{2}[-_.]?\d{2}[-_.]?\d{2}([-_ T]?\d{4,6})?", " ", stem)
    s = ROLE_OLD.sub(" ", s)
    s = ROLE_NEW.sub(" ", s)
    s = re.sub(r"(?<![a-z])v\d+(\.\d+)*", " ", s, flags=re.I)
    s = re.sub(r"[\s_\-.()（）\[\]]+", "_", s).strip("_").lower()
    return s or stem.lower()


def list_files(d, exts):
    d = Path(d)
    if not d.is_dir():
        die(f"文件夹不存在：{d}")
    out = []
    for p in d.rglob("*"):
        if any(part.startswith("对比整理_") for part in p.relative_to(d).parts):
            continue
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    return sorted(out, key=lambda p: nat(p.name))


def order_two(a, b):
    """两份 PDF 里哪个是 baseline。返回 (baseline, new, 说明)。"""
    for x, y in ((a, b), (b, a)):
        if ROLE_OLD.search(x.stem) and not ROLE_OLD.search(y.stem):
            return x, y, ""
        if ROLE_NEW.search(y.stem) and not ROLE_NEW.search(x.stem):
            return x, y, ""
        if ROLE_OLD.search(x.parent.name) and not ROLE_OLD.search(y.parent.name):
            return x, y, ""
    da, db = DATE_IN_NAME.search(a.stem), DATE_IN_NAME.search(b.stem)
    if da and db and da.group(0) != db.group(0):
        return (a, b, "") if da.group(0) < db.group(0) else (b, a, "")
    x, y = (a, b) if a.stat().st_mtime <= b.stat().st_mtime else (b, a)
    return x, y, "文件名分不出新旧，按修改时间判断（旧的当 baseline），请确认"


def pair_two_dirs(da, db, problems):
    A, B = list_files(da, {".pdf"}), list_files(db, {".pdf"})
    if len(A) == 1 and len(B) == 1:
        return [(A[0], B[0], "")]
    ga, gb = {}, {}
    for p in A:
        ga.setdefault(doc_key(p.stem), []).append(p)
    for p in B:
        gb.setdefault(doc_key(p.stem), []).append(p)
    pairs = []
    for k in sorted(set(ga) | set(gb), key=nat):
        xa, xb = ga.get(k, []), gb.get(k, [])
        if len(xa) == 1 and len(xb) == 1:
            pairs.append((xa[0], xb[0], ""))
        else:
            problems.append(f"{k}：baseline {len(xa)} 个、新版 {len(xb)} 个文件，没法一一对应："
                            + "；".join(p.name for p in xa + xb))
    return pairs


def pair_one_dir(d, problems):
    d = Path(d)
    subs = [x for x in d.iterdir() if x.is_dir() and not x.name.startswith("对比整理_")]
    o = [x for x in subs if ROLE_OLD.search(x.name)]
    n = [x for x in subs if ROLE_NEW.search(x.name)]
    if len(o) == 1 and len(n) == 1:
        return pair_two_dirs(o[0], n[0], problems)
    groups = {}
    for p in list_files(d, {".pdf"}):
        groups.setdefault(doc_key(p.stem), []).append(p)
    pairs = []
    for k in sorted(groups, key=nat):
        g = groups[k]
        if len(g) == 2:
            pairs.append(order_two(*g))
        else:
            problems.append(f"{k}：找到 {len(g)} 个文件，需要正好 2 个（baseline 和新版）："
                            + "；".join(p.name for p in g))
    return pairs


def html_kind(name):
    n = name.lower()
    if "ignore" in n and "info" not in n:
        return "ignore"
    if "total" in n:
        return "total"
    if "diff" in n:
        return "difference"
    return None


def cmd_scan(a):
    problems, pairs = [], []
    if a.baseline and a.new:
        pairs = pair_two_dirs(a.baseline, a.new, problems)
    elif a.pdf:
        pairs = pair_one_dir(a.pdf, problems)
    elif not a.results:
        die("请给出 PDF 位置（--pdf 一个文件夹，或 --baseline 和 --new 两个文件夹），或者对比结果 --results")
    cases, used = [], set()
    for b, n, note in pairs:
        ck = case_key(b.stem, n.stem, b.parent.name, n.parent.name)
        label = ck or doc_key(n.stem)[:40]
        while label in used:
            label += "_2"
        used.add(label)
        cases.append({"label": label, "ck": ck, "dk": doc_key(n.stem), "baseline": str(b.resolve()),
                      "new": str(n.resolve()), "files": {}, "notes": [note] if note else []})
    if a.results:
        loose = []
        for h in list_files(a.results, {".html", ".htm"}):
            kind = html_kind(h.name)
            if not kind:
                continue
            ck = case_key(h.stem, h.parent.name, h.parent.parent.name)
            hit = [c for c in cases if ck and c["ck"] == ck] or \
                  [c for c in cases if c["dk"] and c["dk"] in doc_key(str(h.relative_to(a.results)))]
            if not hit and len(cases) == 1 and not ck:
                hit = cases
            if len(hit) == 1:
                if kind in hit[0]["files"]:
                    hit[0]["notes"].append(f"有多个 {kind} 文件，用的是 {Path(hit[0]['files'][kind]).name}，另一个：{h.name}")
                else:
                    hit[0]["files"][kind] = str(h.resolve())
            else:
                loose.append((ck, kind, h))
        for ck, kind, h in loose:
            if not ck:
                problems.append(f"{h.name}：认不出是哪个 Case，没有使用")
                continue
            c = next((c for c in cases if c["label"] == ck), None)
            if c is None:
                c = {"label": ck, "ck": ck, "dk": "", "baseline": "", "new": "", "files": {},
                     "notes": ["没找到对应的 PDF：只能整理文字，不能截图"]}
                cases.append(c)
            c["files"].setdefault(kind, str(h.resolve()))
    if not cases:
        die("没有找到可以对比的文件。" + ("；".join(problems) if problems else ""))
    cases.sort(key=lambda c: nat(c["label"]))
    base = Path(a.results or a.pdf or a.new)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = Path(a.out) if a.out else base / f"对比整理_{ts}"
    out.mkdir(parents=True, exist_ok=True)
    make_work(out)
    for i, c in enumerate(cases):
        c["file"] = f"c{i}.js"
    jsave(W(out) / "batch.json", {"id": ts, "version": VERSION, "out": str(out.resolve()),
                               "inputs": {"pdf": a.pdf, "baseline": a.baseline, "new": a.new, "results": a.results},
                               "cases": cases, "problems": problems})
    print(f"输出文件夹：{out.resolve()}")
    print(f"共 {len(cases)} 组：")
    print("| Case | baseline | 新版 | 对比结果 | 备注 |")
    print("|---|---|---|---|---|")
    for c in cases:
        fs = "、".join(c["files"]) or "无（将直接对比 PDF）"
        print(f"| {c['label']} | {Path(c['baseline']).name if c['baseline'] else '—'} | "
              f"{Path(c['new']).name if c['new'] else '—'} | {fs} | {'；'.join(c['notes'])} |")
    if problems:
        print("\n有问题、没有使用的：")
        for p in problems:
            print("  - " + p)


# ------------------------------------------------------------------ 第 3 步：提取差异

def pdf_rows(path):
    """PDF → 按行的文字，每行带页码和坐标。同一高度的文字算一行（和常见的 PDF 转文字做法一致）。"""
    fitz = need("fitz", "pymupdf")
    doc = fitz.open(path)
    rows, notext = [], []
    for pno, page in enumerate(doc, 1):
        spans = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    if s["text"].strip():
                        spans.append((s["bbox"], s["text"]))
        if not spans:
            notext.append(pno)
            continue
        spans.sort(key=lambda x: ((x[0][1] + x[0][3]) / 2, x[0][0]))
        lines = []
        for bb, t in spans:
            cy, h = (bb[1] + bb[3]) / 2, bb[3] - bb[1]
            if lines and abs(cy - lines[-1]["cy"]) <= max(2.0, 0.35 * h):
                lines[-1]["sp"].append((bb, t))
            else:
                lines.append({"cy": cy, "sp": [(bb, t)]})
        for L in lines:
            sp = sorted(L["sp"], key=lambda x: x[0][0])
            txt, last = "", None
            for bb, t in sp:
                if last is not None and bb[0] - last > 1.0 and not txt.endswith(" ") and not t.startswith(" "):
                    txt += "  " if bb[0] - last > 12 else " "
                txt += t
                last = bb[2]
            box = [round(min(s[0][0] for s in sp), 1), round(min(s[0][1] for s in sp), 1),
                   round(max(s[0][2] for s in sp), 1), round(max(s[0][3] for s in sp), 1)]
            rows.append({"p": pno, "t": clean(txt), "b": box})
    pages = len(doc)
    doc.close()
    return rows, notext, pages


def ratio(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.ratio() if sm.real_quick_ratio() > 0.45 and sm.quick_ratio() > 0.45 else 0.0


def own_diff(A, B):
    """直接对比两份 PDF 的文字行。返回 (全文对照的对齐表, 变化列表)。"""
    ka, kb = [norm(r["t"]) for r in A], [norm(r["t"]) for r in B]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    align, changes = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            align += [[i1 + k, j1 + k, 0] for k in range(i2 - i1)]
            continue
        # 块里按相似度配对：相似的行算“修改”，配不上的算“删除 / 新增”
        pairs, jstart = [], j1
        for i in range(i1, i2):
            best, bj = 0.45, None
            for j in range(jstart, min(j2, jstart + 40)):
                r = ratio(A[i]["t"], B[j]["t"])
                if r > best:
                    best, bj = r, j
            if bj is not None:
                pairs.append((i, bj))
                jstart = bj + 1
        pi = {i: j for i, j in pairs}
        pj = {j for _, j in pairs}
        j = j1
        for i in range(i1, i2):
            if i in pi:
                while j < pi[i]:
                    if j not in pj:
                        align.append([-1, j, 1])
                        changes.append({"ri": None, "rj": j, "ai": i - 1, "aj": None})
                    j += 1
                align.append([i, pi[i], 1])
                changes.append({"ri": i, "rj": pi[i], "ai": None, "aj": None})
                j = pi[i] + 1
            else:
                align.append([i, -1, 1])
                changes.append({"ri": i, "rj": None, "ai": None, "aj": j - 1})
        while j < j2:
            align.append([-1, j, 1])
            changes.append({"ri": None, "rj": j, "ai": i2 - 1, "aj": None})
            j += 1
    return align, changes


ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S | re.I)
MARK_RE = re.compile(r'<span class="diff_(?:add|chg|sub)">(.*?)</span>', re.S)


def plain(s):
    return _html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\u00a0", " ")


def parse_difflib(text):
    """他的 html（Python difflib.HtmlDiff 左右对照表）→ 有变化的行。不是这种格式时返回 None。"""
    if "diff_header" not in text:
        return None
    rows = []
    for tr in ROW_RE.findall(text):
        tds = TD_RE.findall(tr)
        if len(tds) < 6 or "diff_header" not in tds[1][0]:
            continue
        la, ta, lb, tb = plain(tds[1][1]).strip(), tds[2][1], plain(tds[4][1]).strip(), tds[5][1]
        ma, mb = bool(MARK_RE.search(ta)), bool(MARK_RE.search(tb))
        if rows and (la == ">" or lb == ">"):          # 折行，拼回上一行
            r = rows[-1]
            if la == ">":
                r["old"] += plain(ta)
                r["ma"] = r["ma"] or ma
            if lb == ">":
                r["new"] += plain(tb)
                r["mb"] = r["mb"] or mb
            continue
        rows.append({"la": la, "lb": lb, "old": plain(ta), "new": plain(tb), "ma": ma, "mb": mb})
    out, ctx_a, ctx_b = [], "", ""
    for r in rows:
        if r["ma"] or r["mb"]:
            out.append({"old": clean(r["old"]), "new": clean(r["new"]),
                        "line_old": int(r["la"]) if r["la"].isdigit() else None,
                        "line_new": int(r["lb"]) if r["lb"].isdigit() else None,
                        "ctx_old": ctx_a, "ctx_new": ctx_b})
        if r["old"].strip():
            ctx_a = clean(r["old"])
        if r["new"].strip():
            ctx_b = clean(r["new"])
    return [x for x in out if x["old"] or x["new"]]


def find_row(rows, text, hint=None):
    """他的一行在 PDF 行里的位置：完全一样 → 包含 → 相似度最高（≥0.6）。多处时按前后位置 hint（0~1）选。"""
    t = norm(text)
    if len(t) < 2 or not rows:
        return None
    hits = [i for i, r in enumerate(rows) if norm(r["t"]) == t]
    if not hits and len(t) >= 4:
        hits = [i for i, r in enumerate(rows) if t in norm(r["t"]) or (len(norm(r["t"])) >= 6 and norm(r["t"]) in t)]
    if not hits:
        best, bi = 0.6, None
        for i, r in enumerate(rows):
            x = ratio(text, r["t"])
            if x > best:
                best, bi = x, i
        return bi
    if len(hits) == 1 or hint is None:
        return hits[0]
    return min(hits, key=lambda i: abs(i / max(1, len(rows) - 1) - hint))


# ---- 日期、时间、人名：只用来给出“建议分类”，最后由 AI 和人确认

MON = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
       r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?")
DATE_RES = [re.compile(x) for x in (
    r"(?<![\d.,])\d{4} \d{1,2} \d{1,2}(?!\d)",
    r"(?<![\d.,])\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)",
    r"(?<![\d.,])\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}(?!\d)",
    r"(?<!\d)\d{1,2}(?:st|nd|rd|th)?\s*" + MON + r"\s*,?\s*\d{4}(?!\d)",
    r"\b" + MON + r"\s*\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}(?!\d)",
    r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日",
)]
TIME_RE = re.compile(r"(?<![\d.,:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*(?:AM|PM|am|pm))?(?![\d:])")
NAME_LABELS = ["Name of Insured Person", "Name of Insured", "Name of Policy Owner", "Name of Policy Holder",
               "Policy Owner", "Insured Person", "Life Assured", "Beneficiary", "Adviser", "Advisor",
               "被保人姓名", "被保人性名", "投保人姓名", "受保人的姓名", "保單持有人的姓名", "保單權益人",
               "保單持有人", "受保人", "被保人", "投保人", "受益人", "理財顧問"]
LABEL_RE = re.compile(r"(?:" + "|".join(re.escape(x) for x in sorted(NAME_LABELS, key=len, reverse=True))
                      + r")\s*[:：]\s*(.+?)(?=\s{2,}|$)")
HONOR_RE = re.compile(r"\b(?:MR|MRS|MS|MISS|DR|Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,3}")
FIELD_RE = re.compile(r"^\s*([A-Za-z一-鿿][^:：]{0,58}?)\s*[:：]")


def collect_names(rows, extra):
    names = set(extra)
    for r in rows:
        for m in LABEL_RE.finditer(r["t"]):
            v = m.group(1).strip()
            if 2 <= len(v) <= 60 and not re.search(r"\d{3,}", v):
                names.add(v)
                if " " in v:
                    names.add(v.replace(" ", ""))
        for m in HONOR_RE.finditer(r["t"]):
            names.add(m.group(0))
    return sorted((n for n in names if len(n) >= 2), key=len, reverse=True)


def mask(s, dates=False, times=False, names=()):
    if dates:
        for r in DATE_RES:
            s = r.sub("\x01", s)
    if times:
        s = TIME_RE.sub("\x02", s)
    for n in names:
        s = s.replace(n, "\x03")
    return s


def hint_category(old, new, names):
    """返回 (类别, 建议去向)。类别：content 内容变化 / date 日期 / time 时间 / name 人名 / space 空格。"""
    if old and new:
        if norm(old) == norm(new):
            return "space", "exclude"
        for kw, cat in (({"dates": True}, "date"), ({"times": True}, "time"),
                        ({"dates": True, "times": True}, "date"), ({"names": names}, "name"),
                        ({"dates": True, "times": True, "names": names}, "name")):
            if norm(mask(old, **kw)) == norm(mask(new, **kw)):
                return cat, "exclude"
        return "content", "real"
    t = old or new
    left = norm(mask(t, dates=True, times=True, names=names)).replace("\x01", "").replace("\x02", "").replace("\x03", "")
    if not re.sub(r"[\W_]", "", left):
        return ("name" if "\x03" in mask(t, names=names) else "date"), "exclude"
    if re.fullmatch(r"[A-Z][A-Z .'\-]{3,40}", t.strip()):
        return "name", "confirm"          # 像连写的英文名（如 NICHOLSPUN），交给人确认
    return "content", "real"


def segs(old, new):
    ta, tb = re.findall(r"\S+|\s+", old or ""), re.findall(r"\S+|\s+", new or "")
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    sa, sb, fa, fb = [], [], [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        x, y, ch = "".join(ta[i1:i2]), "".join(tb[j1:j2]), op != "equal"
        if x:
            sa.append([x, 1 if ch and x.strip() else 0])
        if y:
            sb.append([y, 1 if ch and y.strip() else 0])
        if ch:
            if x.strip():
                fa.append(x.strip())
            if y.strip():
                fb.append(y.strip())
    return sa, sb, fa, fb


def field_of(old, new):
    for t in (old, new):
        m = FIELD_RE.match(t or "")
        if m:
            return m.group(1).strip()
    return ""


def _match(x, pool, th=0.8):
    """在另一份结果里找同一处差异：先比完全一样，再比相似度。"""
    k = norm(x["old"]) + "|" + norm(x["new"])
    for y in pool:
        if norm(y["old"]) + "|" + norm(y["new"]) == k:
            return y
    best, bo = th, None
    for y in pool:
        r = ratio(x["old"] + " | " + x["new"], y["old"] + " | " + y["new"])
        if r > best:
            best, bo = r, y
    return bo


def _locate(x, A, B, own, mo, mn):
    """把他结果里的一条差异对到两份 PDF 的具体行上。"""
    best, bo = 0.6, None
    for ch in own:
        ot = A[ch["ri"]]["t"] if ch["ri"] is not None else ""
        nt = B[ch["rj"]]["t"] if ch["rj"] is not None else ""
        r = ratio(x["old"] + " | " + x["new"], ot + " | " + nt)
        if r > best:
            best, bo = r, ch
    if bo:
        pos = dict(bo)
        bo["used"] = True
    else:
        pos = {"ri": find_row(A, x["old"], (x["line_old"] or 0) / mo) if x["old"] else None,
               "rj": find_row(B, x["new"], (x["line_new"] or 0) / mn) if x["new"] else None,
               "ai": find_row(A, x["ctx_old"]) if not x["old"] and x["ctx_old"] else None,
               "aj": find_row(B, x["ctx_new"]) if not x["new"] and x["ctx_new"] else None}
    pos.update(old=x["old"], new=x["new"], line_old=x["line_old"], line_new=x["line_new"])
    return pos


def _pdf_check(it, A, B):
    """回到 PDF 核对这一条：ok 确实不同 / same 两边其实一样 / notfound 没找到 / moved 另一边有同样的行。"""
    if not A and not B:
        return "nopdf"
    ri, rj = it["ri"], it["rj"]
    if (it["old"] and ri is None) or (it["new"] and rj is None):
        return "notfound"
    if ri is not None and rj is not None and norm(A[ri]["t"]) == norm(B[rj]["t"]):
        return "same"
    if ri is not None and rj is None and any(norm(r["t"]) == norm(A[ri]["t"]) for r in B):
        return "moved"
    if rj is not None and ri is None and any(norm(r["t"]) == norm(B[rj]["t"]) for r in A):
        return "moved"
    return "ok"


CAT_ZH = {"content": "内容变化", "date": "日期", "time": "时间", "name": "人名", "space": "空格", "other": "其他"}
VER_ZH = {"real": "真实变化", "exclude": "已排除", "confirm": "请确认"}
ORIGIN_ZH = {"kept": "他的结果", "filtered": "被他过滤掉的", "missed": "他的结果里没有", "pdf": "PDF 直接对比"}


def _judge(origin, status, cat):
    """复核规则：返回 (建议去向, 理由)。AI 会再逐条看，人最后确认。"""
    czh = CAT_ZH.get(cat, cat)
    if status == "same":
        return "exclude", "回到 PDF 核对：这一行两边其实一样，是提取或排版造成的误报"
    if status == "notfound":
        return "confirm", "在 PDF 里没找到这一行（可能是扫描页或文字提取方式不同），请人工看一下"
    if status == "moved":
        return "confirm", "另一份 PDF 里有完全相同的一行，只是位置变了，请确认是否算变化"
    if origin == "filtered":
        if cat == "content":
            return "confirm", "被他的过滤去掉了，但看起来不是日期 / 人名，可能被误过滤"
        return "exclude", f"已被他的过滤去掉（{czh}）"
    if origin == "missed":
        if cat == "content":
            return "confirm", "他的对比结果里没有这一处，PDF 直接对比发现的，请确认"
        return "exclude", f"他的结果里没有，且只是{czh}变化"
    pre = "PDF 核对一致" if status == "ok" else "没有 PDF，未核对"
    if cat == "content":
        return "real", f"{pre}：内容确实不同"
    return "exclude", f"{pre}，但只是{czh}变化"


def cmd_extract(a):
    out = batch_dir(a)
    w = W(out)
    batch = jload(w / "batch.json")
    extra = []
    for p in (out / "names.txt", Path(batch["inputs"].get("pdf") or out) / "names.txt"):
        if p.is_file():
            extra += [x.strip() for x in re.split(r"[\n,\t]", p.read_text(encoding="utf-8-sig")) if len(x.strip()) >= 3]
    review = jload(w / "review.json", {})
    all_items = []
    for ci, c in enumerate(batch["cases"]):
        lab = c["label"]
        A, B, na, nb, pa, pb = [], [], [], [], 0, 0
        if c["baseline"] and Path(c["baseline"]).is_file():
            A, na, pa = pdf_rows(c["baseline"])
        if c["new"] and Path(c["new"]).is_file():
            B, nb, pb = pdf_rows(c["new"])
        align, own = own_diff(A, B) if (A and B) else ([], [])
        notes = [n for n in (c.get("notes") or []) if n]
        kept_key = a.source
        if kept_key == "auto":
            kept_key = next((k for k in ("ignore", "difference", "total") if c["files"].get(k)), "pdf")
        parsed = {}
        for k in ("ignore", "difference", "total"):
            if c["files"].get(k):
                rows = parse_difflib(read_any(c["files"][k]))
                if rows is None:
                    notes.append(f"{k} 页面不是 difflib 左右对照格式，没有使用（可用 inspect 查看）")
                else:
                    parsed[k] = rows
        if kept_key != "pdf" and kept_key not in parsed:
            notes.append(f"没有可用的 {kept_key} 结果，改用 PDF 直接对比")
            kept_key = "pdf"
        raw = []            # (来源, 他的一条差异)
        if kept_key != "pdf":
            raw += [("kept", x) for x in parsed[kept_key]]
            if kept_key != "total" and "total" in parsed:
                if len(parsed[kept_key]) > len(parsed["total"]):
                    notes.append(f"{kept_key} 的条数比 total 还多，请确认哪个才是过滤后的结果（可用 --source 指定）")
                kept = parsed[kept_key]
                raw += [("filtered", x) for x in parsed["total"] if not _match(x, kept)]
        items = []
        if kept_key != "pdf":
            allh = [x for _, x in raw]
            mo = max([x["line_old"] or 0 for x in allh] + [1])
            mn = max([x["line_new"] or 0 for x in allh] + [1])
            for origin, x in raw:
                it = _locate(x, A, B, own, mo, mn)
                it["origin"] = origin
                items.append(it)
            missed = 0
            for ch in own:                       # PDF 直接对比有、他的结果里没有的
                if ch.get("used"):
                    continue
                it = dict(ch)
                it["old"] = A[it["ri"]]["t"] if it["ri"] is not None else ""
                it["new"] = B[it["rj"]]["t"] if it["rj"] is not None else ""
                it.update(line_old=None, line_new=None, origin="missed")
                items.append(it)
                missed += 1
        else:
            for ch in own:
                it = dict(ch)
                it["old"] = A[it["ri"]]["t"] if it["ri"] is not None else ""
                it["new"] = B[it["rj"]]["t"] if it["rj"] is not None else ""
                it.update(line_old=None, line_new=None, origin="pdf")
                items.append(it)
            if not (A and B):
                notes.append("缺少 PDF 或对比结果，这一组没有可整理的内容")
        names = collect_names(A + B, extra)
        keep_items, n = [], 0
        for it in items:
            it.pop("used", None)
            for k2, rows in (("ai", A), ("aj", B)):
                if it.get(k2) is not None and not (0 <= it[k2] < len(rows)):
                    it[k2] = 0 if rows else None
            sa, sb, fa, fb = segs(it["old"], it["new"])
            it.update(seg_old=sa, seg_new=sb, frag_old=fa, frag_new=fb, field=field_of(it["old"], it["new"]),
                      kind="新增" if not it["old"] else "删除" if not it["new"] else "修改")
            it["cat"], _ = hint_category(it["old"], it["new"], names)
            it["check"] = _pdf_check(it, A, B)
            it["hint"], it["why"] = _judge(it["origin"], it["check"], it["cat"])
            if it["origin"] == "missed" and it["hint"] == "exclude" and it["check"] != "ok":
                continue                          # 他没报、我们也认为无关紧要的，不再列出来
            n += 1
            it["id"] = f"{lab}#{n:03d}"
            it["case"] = lab
            it["page_old"] = A[it["ri"]]["p"] if it["ri"] is not None else (A[it["ai"]]["p"] if it.get("ai") is not None else None)
            it["page_new"] = B[it["rj"]]["p"] if it["rj"] is not None else (B[it["aj"]]["p"] if it.get("aj") is not None else None)
            # 指纹：重新提取后编号可能对应到别的差异，指纹不同的旧结论作废
            it["sig"] = norm(it["old"])[:40] + "|" + norm(it["new"])[:40]
            old_r = review.get(it["id"])
            if not old_r or old_r.get("sig") != it["sig"]:
                review[it["id"]] = {"verdict": it["hint"], "cat": it["cat"], "field": it["field"], "note": "", "sig": it["sig"]}
            keep_items.append(it)
        items = keep_items
        trunc = len(A) > MAX_ROWS or len(B) > MAX_ROWS
        if trunc:
            notes.append(f"文字行太多，全文对照只放前 {MAX_ROWS} 行")
        if na or nb:
            notes.append(f"扫描页（没有文字，未比较）：baseline 第 {na[:6]} 页，新版第 {nb[:6]} 页" .replace("[", "").replace("]", ""))
        c["file"] = c.get("file") or f"c{ci}.js"
        save_case(out, ci, {"key": lab, "source": kept_key, "notes": notes, "pages_old": pa, "pages_new": pb,
                            "A": A, "B": B, "align": align, "items": items, "trunc": trunc})
        c["source"], c["notes"] = kept_key, notes
        all_items += items
        cnt = {}
        for it in items:
            cnt[it["hint"]] = cnt.get(it["hint"], 0) + 1
        org = {}
        for it in items:
            org[it["origin"]] = org.get(it["origin"], 0) + 1
        print(f"  {lab:<12} 以 {kept_key} 为准，共 {len(items)} 条（"
              + "、".join(f"{ORIGIN_ZH[k]} {v}" for k, v in org.items()) + "）→ 建议："
              f"真实 {cnt.get('real', 0)}、请确认 {cnt.get('confirm', 0)}、排除 {cnt.get('exclude', 0)}"
              + ("；" + "；".join(notes) if notes else ""))
    ids = {it["id"] for it in all_items}
    jsave(w / "review.json", {k: v for k, v in review.items() if k in ids})
    jsave(w / "batch.json", batch)
    print(f"共 {len(all_items)} 条。下一步：dca list 逐条复核，修改 .dca/review.json 里的 verdict / field / note。")


# ------------------------------------------------------------------ 读数据、逐条列出

def load_items(out):
    batch = jload(W(out) / "batch.json")
    cases = []
    for i, c in enumerate(batch["cases"]):
        w = load_case(out, i)
        if w is None:
            die("还没有提取差异，请先运行 extract")
        cases.append((c, w))
    return batch, cases


def verdicts_of(out):
    return jload(W(out) / "review.json", {}) or {}


def cmd_list(a):
    out = batch_dir(a)
    batch, cases = load_items(out)
    rv = verdicts_of(out)
    shown = 0
    for c, w in cases:
        if a.case and c["label"] != a.case:
            continue
        for it in w["items"]:
            r = rv.get(it["id"], {})
            if a.verdict and r.get("verdict") != a.verdict:
                continue
            if a.cat and r.get("cat", it["cat"]) != a.cat:
                continue
            if a.origin and it.get("origin") != a.origin:
                continue
            shown += 1
            if shown <= a.offset:
                continue
            if shown > a.offset + a.limit:
                print(f"……还有更多，用 --offset {a.offset + a.limit} 继续")
                return
            fo = " / ".join(it["frag_old"])[:80] or "—"
            fn = " / ".join(it["frag_new"])[:80] or "—"
            print(f"{it['id']} [{ORIGIN_ZH.get(it.get('origin'), '')}｜{CAT_ZH.get(r.get('cat', it['cat']), '?')}"
                  f"→{VER_ZH.get(r.get('verdict'), '?')}] p{it['page_old'] or '-'}/{it['page_new'] or '-'} {it['kind']}"
                  f" 字段「{r.get('field', '')}」\n    旧：{it['old'][:160]}\n    新：{it['new'][:160]}\n"
                  f"    变化：{fo} → {fn}\n    复核：{it.get('why', '')}")
    print(f"（共 {shown} 条）")


def cmd_inspect(a):
    t = read_any(a.file)
    print(f"文件：{a.file}（{len(t)} 字符）")
    print("difflib 左右对照格式：" + ("是" if "diff_header" in t else "否"))
    print(f"<table> {len(re.findall(r'<table', t, re.I))} 个，<tr> {len(re.findall(r'<tr', t, re.I))} 个")
    rows = parse_difflib(t)
    if rows is not None:
        print(f"有变化的行：{len(rows)} 条，前 10 条：")
        for x in rows[:10]:
            print(f"  行 {x['line_old']}/{x['line_new']}  旧：{x['old'][:90]!r}  新：{x['new'][:90]!r}")
    else:
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S | re.I)
        lines = [l.strip() for l in plain(re.sub(r"<(br|p|div|tr|li)[^>]*>", "\n", body, flags=re.I)).splitlines() if l.strip()]
        print(f"纯文字 {len(lines)} 行，前 40 行：")
        for l in lines[:40]:
            print("  | " + l[:150])


# ------------------------------------------------------------------ 截图

def shoot_side(fitz, doc, rows, other_rows, it, side, png):
    """截一边的图。返回 (页码, 备注)；页码为 None 表示没截（不会乱框）。"""
    ri, ai = (it["ri"], it.get("ai")) if side == "old" else (it["rj"], it.get("aj"))
    oi = it["rj"] if side == "old" else it["ri"]
    text = it[side]
    dashed = False
    if ri is not None:
        r = rows[ri]
        if text and ratio(text, r["t"]) < 0.6 and norm(text) not in norm(r["t"]):
            return None, "PDF 中定位不确定，截图待补"
        page = doc[r["p"] - 1]
        rect = fitz.Rect(r["b"])
        boxes = []
        for f in (it["frag_old"] if side == "old" else it["frag_new"])[:10]:
            boxes += [h for h in page.search_for(f, clip=rect + (-3, -3, 3, 3))]
        got = norm(page.get_text("text", clip=rect + (-1, -1, 1, 1)))     # 核对：框出来的区域里确实是这一行
        want = norm(r["t"])
        if want[:30] not in got and got not in want:
            return None, "截图区域与文字对不上，截图待补"
        boxes = boxes or [rect]
    elif ai is not None and rows:
        r = rows[ai]
        page = doc[r["p"] - 1]
        h = max(8.0, r["b"][3] - r["b"][1])
        ob = other_rows[oi]["b"] if oi is not None and other_rows else r["b"]
        rect = fitz.Rect(ob[0], r["b"][3] + 1, max(ob[2], ob[0] + 60), r["b"][3] + 1 + h) & page.rect
        boxes, dashed = [rect], True
    else:
        return None, "PDF 中没有对应位置，截图待补"
    clip = fitz.Rect(0, max(0, rect.y0 - 30), page.rect.width, min(page.rect.height, rect.y1 + 30))
    annots = []
    try:
        for b in boxes:
            an = page.add_rect_annot(b + (-2, -2, 2, 2))
            an.set_colors(stroke=(0.88, 0.1, 0.1))
            an.set_border(width=1.6, dashes=[3, 2] if dashed else None)
            an.update()
            annots.append(an)
        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip).save(str(png))
    finally:
        for an in annots:
            page.delete_annot(an)          # 只在内存里画框，原 PDF 不会被保存修改
    try:
        ok = fitz.Pixmap(str(png)).width > 10
    except Exception:
        ok = False
    if not ok:
        return None, "截图文件生成失败"
    return page.number + 1, ("新版缺少这一行，虚线框为应在的位置" if dashed and side == "new" else
                             "baseline 没有这一行，虚线框为对应位置" if dashed else "")


def make_shots(out, batch, cases, rv, only_missing=False):
    """只给“真实变化 / 请确认”的条目截图；已排除的不截，省空间。"""
    fitz = need("fitz", "pymupdf")
    total = bad = 0
    for ci, (c, w) in enumerate(cases):
        todo = [it for it in w["items"] if rv.get(it["id"], {}).get("verdict") in ("real", "confirm")]
        if only_missing:
            todo = [it for it in todo if not (it.get("shot_old") or it.get("shot_new"))]
        if not todo:
            continue
        sd = W(out) / "shots" / f"c{ci}"
        sd.mkdir(parents=True, exist_ok=True)
        for side, key in (("old", "baseline"), ("new", "new")):
            path = c.get(key)
            rows, other = (w["A"], w["B"]) if side == "old" else (w["B"], w["A"])
            if not path or not Path(path).is_file():
                for it in todo:
                    it[f"shot_{side}"], it[f"snote_{side}"] = "", "没有 PDF，不能截图"
                continue
            doc = fitz.open(path)
            try:
                for it in todo:
                    if not it[side] and it.get("a" + ("i" if side == "old" else "j")) is None:
                        it[f"shot_{side}"], it[f"snote_{side}"] = "", ""
                        continue
                    png = sd / f"{it['id'].split('#')[1]}_{side}.png"
                    try:
                        pg, nt = shoot_side(fitz, doc, rows, other, it, side, png)
                    except Exception as e:
                        pg, nt = None, f"截图出错：{type(e).__name__}: {e}"
                    it[f"shot_{side}"] = rel(png, out) if pg else ""
                    it[f"snote_{side}"] = nt
                    if pg:
                        it[f"page_{side}"] = pg
                    total += 1
                    bad += 0 if pg else 1
            finally:
                doc.close()
        save_case(out, ci, w)
    return total, bad


def cmd_shots(a):
    out = batch_dir(a)
    batch, cases = load_items(out)
    total, bad = make_shots(out, batch, cases, verdicts_of(out))
    print(f"截图 {total} 张，其中 {bad} 张没截（截图待补）")


# ------------------------------------------------------------------ 第 6 步：索引页

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#1f2329;--ink2:#545b66;--mute:#8f959e;--line:#dfe2e6;--line2:#eef0f2;--bg:#f3f4f6;--pri:#2f6bff;--pri-l:#e8efff;
--red:#e02d2d;--red-l:#fdecec;--grn:#1f9d55;--grn-l:#e6f6ec;--amb:#b26a00;--amb-l:#fff4dc;--mono:Consolas,"SF Mono",monospace}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{font:13px/1.55 "Microsoft YaHei UI","Microsoft YaHei","PingFang SC",sans-serif;color:var(--ink);background:var(--bg)}
.app{display:grid;grid-template-columns:260px minmax(0,1fr);height:100vh}
aside{background:#fafbfc;border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
.ah{padding:14px}.ah b{font-size:14px}.ah small{display:block;color:var(--mute);font-size:11.5px}
.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px}
.stat div{background:#fff;border:1px solid var(--line2);border-radius:6px;padding:5px 7px;font-size:11px;color:var(--mute)}
.stat b{display:block;font:600 16px var(--mono);color:var(--ink)}
.srch{margin:0 14px 6px;width:calc(100% - 28px);height:30px;border:1px solid var(--line);border-radius:6px;padding:0 9px;font:inherit}
.chk{margin:0 14px 8px;font-size:12px;color:var(--ink2);display:flex;gap:12px}
.list{flex:1;overflow:auto}
.ci{padding:9px 14px;border-top:1px solid var(--line2);cursor:pointer}.ci:hover{background:#f2f5fb}.ci.on{background:var(--pri-l)}
.ci .k{display:flex;align-items:center;gap:6px;font-weight:600}
.ci .n{margin-left:auto;font:11px var(--mono);padding:1px 7px;border-radius:10px;background:var(--red-l);color:var(--red)}.ci .n.z{background:var(--line2);color:var(--mute)}
.ci .f{font-size:11px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.prog{height:4px;background:var(--line2);border-radius:2px;margin-top:5px;overflow:hidden}.prog i{display:block;height:100%;background:var(--grn)}
.side-f{padding:10px 14px;border-top:1px solid var(--line);display:flex;gap:6px;flex-wrap:wrap}
.b{font:inherit;font-size:12px;padding:5px 11px;border-radius:6px;border:1px solid var(--line);background:#fff;cursor:pointer;color:var(--ink)}
.b.p{background:var(--pri);border-color:var(--pri);color:#fff;font-weight:600}
main{min-width:0;display:flex;flex-direction:column;background:#fff}
.mh{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.mh b{font-size:15px}.mh .sub{color:var(--mute);font-size:12px}
.tabs{margin-left:auto;display:flex;gap:2px;background:var(--bg);border-radius:7px;padding:2px}
.tabs span{padding:4px 11px;border-radius:5px;font-size:12px;color:var(--ink2);cursor:pointer}.tabs span.on{background:#fff;color:var(--pri);font-weight:600}
.tabs span.off{display:none}
.body{flex:1;overflow:auto;min-height:0}
.flt{display:flex;gap:6px;padding:10px 18px 0;flex-wrap:wrap;align-items:center}
.flt span{font-size:12px;padding:3px 10px;border-radius:12px;border:1px solid var(--line);color:var(--ink2);cursor:pointer}
.flt span.on{border-color:var(--pri);color:var(--pri);background:var(--pri-l)}
.cnote{margin:10px 18px 0;padding:6px 10px;background:var(--amb-l);color:var(--amb);border-radius:6px;font-size:12px}
.cards{padding:12px 18px 60px}
.card{border:1px solid var(--line);border-radius:8px;margin-bottom:12px;overflow:hidden}.card.ok{border-color:#bfe5cc}
.ch{display:flex;align-items:center;gap:10px;padding:8px 12px;background:#fafbfc;border-bottom:1px solid var(--line2);flex-wrap:wrap}
.ch .id{font:600 12px var(--mono)}.ch .loc{color:var(--mute);font-size:12px}
.fld{border:1px solid transparent;border-radius:4px;padding:1px 4px;font:inherit;font-weight:600;min-width:80px}.fld:hover,.fld:focus{border-color:var(--line)}
.pill{font-size:11px;padding:1px 8px;border-radius:10px}.p-c{background:var(--red-l);color:var(--red)}.p-d{background:var(--line2);color:var(--ink2)}.p-q{background:var(--amb-l);color:var(--amb)}
.vb{margin-left:auto;display:flex;gap:6px}.vb span{font-size:12px;padding:3px 10px;border-radius:6px;border:1px solid var(--line);cursor:pointer;white-space:nowrap;color:var(--ink2);background:#fff}
.vb span.y{background:var(--grn);border-color:var(--grn);color:#fff}.vb span.x{background:var(--ink2);border-color:var(--ink2);color:#fff}
.cb{display:grid;grid-template-columns:1fr 1fr}.cb>div{padding:10px 12px;min-width:0}.cb>div+div{border-left:1px solid var(--line2)}
.lab{font-size:11px;color:var(--mute);margin-bottom:3px}.lab a{color:var(--pri);margin-left:6px}
.val{font:12.5px var(--mono);margin-bottom:8px;word-break:break-all;white-space:pre-wrap}
.val i,.ft i{font-style:normal;background:var(--red-l);color:var(--red);font-weight:700;border-radius:2px}
.shot{max-width:100%;border:1px solid var(--line);border-radius:4px;cursor:zoom-in;display:block}
.miss{font-size:12px;color:var(--amb);padding:8px;border:1px dashed #e8c98a;border-radius:4px;background:var(--amb-l)}
.why{padding:7px 12px;border-top:1px solid var(--line2);font-size:12px;color:var(--ink2);background:#fcfcfd}
.why textarea{width:100%;border:1px solid var(--line);border-radius:5px;font:inherit;font-size:12px;padding:5px 7px;resize:vertical;margin-top:4px;color:var(--ink)}
.appx{border:1px dashed var(--line);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--ink2)}
.appx summary{cursor:pointer;color:var(--ink)}.appx li{margin:4px 0}.appx a{color:var(--pri);cursor:pointer;margin-left:6px}
.ftbar{display:flex;gap:8px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--line2);font-size:12px;color:var(--ink2);flex-wrap:wrap;position:sticky;top:0;background:#fff;z-index:2}
.ft{width:100%;border-collapse:collapse;font:12px/1.5 var(--mono);table-layout:fixed}
.ft td{padding:1px 8px;vertical-align:top;white-space:pre-wrap;word-break:break-all;border-bottom:1px solid #f6f7f8}
.ft td.n{width:52px;color:var(--mute);text-align:right;user-select:none}
.ft tr.c td.t{background:#fff8f0}.ft tr.c td.t.e{background:#f7f7f7}
.ft tr.pg td{background:var(--bg);color:var(--mute);font:11px sans-serif;text-align:center;padding:3px}
.ft tr.gap td{color:var(--mute);text-align:center;font:11px sans-serif;background:#fbfbfc;cursor:pointer}
.ft tr.cur td.t{outline:2px solid var(--pri);outline-offset:-2px}
.more{margin:12px auto 60px;display:block}
iframe{width:100%;height:100%;border:0}
.warn{margin:40px auto;max-width:520px;text-align:center;color:var(--ink2)}
.empty{color:var(--mute);padding:40px;text-align:center}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:9;cursor:zoom-out}
#zoom img{max-width:94vw;max-height:94vh;background:#fff}
#toast{position:fixed;left:50%;bottom:56px;transform:translateX(-50%);background:#1f2329;color:#fff;padding:8px 14px;border-radius:8px;font-size:12.5px;display:none;z-index:10}
.ro{display:none;padding:7px 18px;background:var(--amb-l);color:var(--amb);font-size:12px;border-bottom:1px solid #f0dfb8}
#dlg{position:fixed;inset:0;background:rgba(31,35,41,.35);display:none;align-items:center;justify-content:center;z-index:11}
.dbox{background:#fff;border-radius:12px;padding:20px 22px;width:min(460px,92vw);box-shadow:0 20px 50px -12px rgba(0,0,0,.35)}
.dbox b{font-size:15px}.dbox p{margin:8px 0;color:var(--ink2)}.dbox .path{font:12px var(--mono);word-break:break-all;color:var(--ink);margin:4px 0}
.dl{display:block;font-size:12px;color:var(--ink2);margin-top:10px}.dl input{display:block;width:100%;margin-top:3px;height:30px;border:1px solid var(--line);border-radius:6px;padding:0 8px;font:inherit}
.da{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
.vb span,.side-f .b{user-select:none}
@media print{aside,.tabs,.vb,.flt,.ftbar{display:none}.app{display:block;height:auto}.body{overflow:visible}}
</style></head><body>
<div class="app">
<aside>
 <div class="ah"><b>__TITLE__</b><small id="meta"></small>
  <div class="stat"><div><b id="s1"></b>有差异</div><div><b id="s2"></b>待核实</div><div><b id="s3"></b>真实变化</div></div></div>
 <input class="srch" id="q" type="search" placeholder="搜 Case、字段、值">
 <div class="chk"><label><input type="checkbox" id="onlyDiff" checked> 只看有差异的</label><label><input type="checkbox" id="onlyTodo"> 只看待核实</label></div>
 <div class="list" id="clist"></div>
 <div class="side-f" id="sidef"></div>
</aside>
<main>
 <div class="ro" id="ro">只读查看：要修改核实结论或生成交付文档，请在终端里对 AI 说“继续核实”。</div>
 <div class="mh"><b id="cTitle"></b><span class="sub" id="cSub"></span>
  <div class="tabs" id="tabs"><span data-t="items" class="on">变化整理</span><span data-t="full">全文对照</span><span data-t="ignore">ignore 原页面</span><span data-t="total">total 原页面</span><span data-t="difference">difference 原页面</span></div></div>
 <div class="body" id="body"><div class="empty">加载中…</div></div>
</main></div>
<div id="zoom"><img alt=""></div><div id="toast"></div>
<div id="dlg"><div class="dbox" id="dbox"></div></div>
<script>
const D=__DATA__;
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const SERVER=/^https?:$/.test(location.protocol);
const U=p=>!p?p:(SERVER&&!/^(https?:|\/_f)/.test(p)?"/_f?p="+encodeURIComponent(p):p);
let ST={};
function loadRV(rv){ST={};Object.entries(rv||{}).forEach(([id,r])=>{ST[id]={verdict:r.verdict,note:r.note||""};ST[id+"@f"]={note:r.field||""}})}
loadRV(D.rv);
const CACHE={};let cur=null,tab="items",chip="all",fullPos=0,fullOnly=true,curChange=-1,done=false;
const CAT={content:"内容变化",date:"日期",time:"时间",name:"人名",space:"空格",other:"其他"};
function toast(m){const t=$("#toast");t.textContent=m;t.style.display="block";clearTimeout(t._h);t._h=setTimeout(()=>t.style.display="none",2600)}
function verdict(id,def){return (ST[id]&&ST[id].verdict)||def}
function note(id,def){return ST[id]&&ST[id].note!=null?ST[id].note:def}
async function api(path,body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-DCA":"1"},body:JSON.stringify(body||{})});
 const j=await r.json().catch(()=>({ok:false,error:"服务没有响应"}));if(!r.ok||!j.ok)throw new Error(j.error||("HTTP "+r.status));return j}
const pend={};
function setV(id,k,v){if(!SERVER||done){toast(done?"交付文档已生成，页面已转为只读":"只读查看，不能修改");return false}
 ST[id]=Object.assign(ST[id]||{},{[k]:v});const base=id.replace(/@f$/,""),key=id.endsWith("@f")?"field":k;
 clearTimeout(pend[id+k]);pend[id+k]=setTimeout(()=>api("/api/save",{id:base,key,value:v}).catch(e=>toast("保存失败："+e.message+"（请确认终端里的服务还在运行）")),k==="verdict"?0:400);return true}
function counts(c){let r=0,q=0;c.items.forEach(([id,v])=>{const x=verdict(id,v);if(x==="real")r++;if(x==="confirm")q++});return {r,q,n:c.items.length}}
function stats(){let a=0,q=0,r=0;D.cases.forEach(c=>{const k=counts(c);if(k.n)a++;q+=k.q;r+=k.r});$("#s1").textContent=a;$("#s2").textContent=q;$("#s3").textContent=r}
function list(){const q=$("#q").value.trim().toLowerCase(),od=$("#onlyDiff").checked,ot=$("#onlyTodo").checked;
 $("#clist").innerHTML=D.cases.map((c,i)=>{const k=counts(c);
  if(od&&!k.n)return"";if(ot&&!k.q)return"";if(q&&!(c.label+" "+c.bn+" "+c.nn+" "+(c.search||"")).toLowerCase().includes(q))return"";
  const done=k.n?Math.round((k.n-k.q)/k.n*100):100;
  return `<div class="ci${cur&&cur.i===i?" on":""}" data-i="${i}"><div class="k">${esc(c.label)}<span class="n${k.n?"":" z"}">${k.n?k.r+" / "+k.n:"无差异"}</span></div><div class="f">${esc(c.nn||c.bn)}</div>${k.n?`<div class="prog"><i style="width:${done}%"></i></div>`:""}</div>`}).join("")||'<div class="empty">没有符合的 Case</div>';
 document.querySelectorAll(".ci").forEach(e=>e.onclick=()=>open(+e.dataset.i))}
function open(i){const c=D.cases[i];cur={i,c};list();$("#cTitle").textContent=c.label;$("#cSub").textContent=(c.bn||"—")+" ⇄ "+(c.nn||"—");
 document.querySelectorAll("#tabs span").forEach(t=>{const k=t.dataset.t;t.classList.toggle("off",!(k==="items"||(k==="full"&&c.full)||c.files[k]))});
 if(tab!=="items"&&!(tab==="full"&&c.full)&&!c.files[tab])tab="items";fullPos=0;curChange=-1;
 if(CACHE[c.key])return show();$("#body").innerHTML='<div class="empty">加载中…</div>';
 const s=document.createElement("script");s.src=U(c.data);const bad=()=>{if(!CACHE[c.key]&&cur&&cur.c.key===c.key)$("#body").innerHTML='<div class="empty">数据文件丢失或损坏：'+esc(c.data)+'，请在终端重新整理</div>'};s.onerror=bad;s.onload=bad;document.body.appendChild(s)}
window.DCA_CASE=o=>{CACHE[o.key]=o;if(cur&&cur.c.key===o.key)show()};
function seg(s){return s&&s.length?s.map(([t,ch])=>ch?`<i>${esc(t)}</i>`:esc(t)).join(""):'<span style="color:var(--mute)">（无这一行）</span>'}
function pdfLink(side,p){const f=side==="old"?cur.c.bp:cur.c.np;return f&&p?`<a href="${esc(U(f))}#page=${p}" target="_blank">打开 PDF 第 ${p} 页</a>`:""}
function shotHtml(it,side){const s=it["shot_"+side],n=it["snote_"+side];
 if(s)return `<img class="shot" loading="lazy" src="${esc(U(s))}" alt="">`+(n?`<div class="lab" style="margin-top:4px">${esc(n)}</div>`:"");
 const anc=it[side==="old"?"ai":"aj"];if(!it[side]&&(anc===null||anc===undefined))return"";
 const v=verdict(it.id,it.hint);return `<div class="miss">${esc(n||(v==="exclude"?"已排除的条目不截图":"截图会在生成交付文档时补上"))}</div>`}
const ORG={kept:"他的结果",filtered:"被他过滤掉的",missed:"他的结果里没有",pdf:"PDF 直接对比"};
function card(it){const v=verdict(it.id,it.hint),cls=v==="real"?"p-c":v==="confirm"?"p-q":"p-d";
 const lab=v==="real"?"真实变化":v==="confirm"?"请确认":"已排除",ro=SERVER&&!done?"":" readonly";
 return `<div class="card${v==="real"?" ok":""}" id="c-${esc(it.id)}"><div class="ch"><span class="id">${esc(it.id.split("#")[1])}</span><span class="pill ${cls}">${lab}</span><span class="pill p-d">${CAT[it.cat]||""}</span>${it.origin&&it.origin!=="kept"&&it.origin!=="pdf"?`<span class="pill p-q">${ORG[it.origin]}</span>`:""}
 <input class="fld" value="${esc(note(it.id+"@f",it.field))}" placeholder="字段名" data-f="${esc(it.id)}"${ro}><span class="loc">${it.page_old?"旧 第 "+it.page_old+" 页":""}${it.page_old&&it.page_new?" · ":""}${it.page_new?"新 第 "+it.page_new+" 页":""}</span>
 <div class="vb"><span class="${v==="real"?"y":""}" data-v="real" data-id="${esc(it.id)}">${v==="real"?"✓ ":""}是真实变化</span><span class="${v==="exclude"?"x":""}" data-v="exclude" data-id="${esc(it.id)}">不算</span></div></div>
 <div class="cb"><div><div class="lab">baseline ${pdfLink("old",it.page_old)}</div><div class="val">${seg(it.seg_old)}</div>${shotHtml(it,"old")}</div>
 <div><div class="lab">新版 ${pdfLink("new",it.page_new)}</div><div class="val">${seg(it.seg_new)}</div>${shotHtml(it,"new")}</div></div>
 ${it.why?`<div class="why"><b>复核：</b>${esc(it.why)}</div>`:""}
 <div class="why"><b>说明（会写进交付文档，可以改）：</b><textarea rows="2" data-n="${esc(it.id)}"${ro}>${esc(note(it.id,it.note))}</textarea></div></div>`}
function items(){const o=CACHE[cur.c.key];const all=o.items;const vs=all.map(it=>verdict(it.id,it.hint));
 const n={all:all.length,real:vs.filter(v=>v==="real").length,confirm:vs.filter(v=>v==="confirm").length,exclude:vs.filter(v=>v==="exclude").length};
 let h=`<div class="flt">${[["all","全部"],["real","真实变化"],["confirm","请确认"],["exclude","已排除"]].map(([k,l])=>`<span data-c="${k}" class="${chip===k?"on":""}">${l} ${n[k]}</span>`).join("")}<span style="border:0;color:var(--mute)">来源：${esc(o.source)}</span></div>`;
 if(o.notes&&o.notes.length)h+=`<div class="cnote">${esc(o.notes.join("；"))}</div>`;
 const pick=all.filter((it,i)=>chip==="all"?vs[i]!=="exclude":vs[i]===chip);
 const LIM=150;h+='<div class="cards">'+(pick.length?"":'<div class="empty">这里没有条目</div>')+pick.slice(0,LIM).map(card).join("");
 if(pick.length>LIM)h+=`<div class="empty">条目较多，只显示前 ${LIM} 条；请用上面的分类筛选</div>`;
 if(chip==="all"&&n.exclude){h+=`<details class="appx"><summary><b>已排除 ${n.exclude} 条</b>（日期、人名等，默认不进交付文档）</summary><ul>`+
  all.filter((it,i)=>vs[i]==="exclude").slice(0,500).map(it=>`<li>${esc(it.id.split("#")[1])} [${CAT[it.cat]||""}] ${esc((it.old||"—").slice(0,80))} → ${esc((it.new||"—").slice(0,80))}<a data-v="real" data-id="${esc(it.id)}">改为真实变化</a></li>`).join("")+"</ul></details>"}
 $("#body").innerHTML=h+"</div>";
 document.querySelectorAll(".flt span[data-c]").forEach(e=>e.onclick=()=>{chip=e.dataset.c;items()});
 document.querySelectorAll("[data-v]").forEach(e=>e.onclick=()=>{setV(e.dataset.id,"verdict",e.dataset.v);items();list();stats()});
 document.querySelectorAll("textarea[data-n]").forEach(e=>e.oninput=()=>setV(e.dataset.n,"note",e.value));
 document.querySelectorAll("input[data-f]").forEach(e=>e.oninput=()=>setV(e.dataset.f+"@f","note",e.value));
 document.querySelectorAll("img.shot").forEach(i=>i.onclick=()=>{$("#zoom img").src=i.src;$("#zoom").style.display="flex"})}
function tok(s){return s.match(/\S+|\s+/g)||[]}
function wdiff(a,b){const x=tok(a),y=tok(b);if(x.length*y.length>40000)return [esc(a),esc(b)];
 const m=x.length,n=y.length,L=Array.from({length:m+1},()=>new Uint16Array(n+1));
 for(let i=m-1;i>=0;i--)for(let j=n-1;j>=0;j--)L[i][j]=x[i]===y[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
 let i=0,j=0,A="",B="";while(i<m&&j<n){if(x[i]===y[j]){A+=esc(x[i]);B+=esc(y[j]);i++;j++}else if(L[i+1][j]>=L[i][j+1]){A+=x[i].trim()?`<i>${esc(x[i])}</i>`:esc(x[i]);i++}else{B+=y[j].trim()?`<i>${esc(y[j])}</i>`:esc(y[j]);j++}}
 while(i<m){A+=x[i].trim()?`<i>${esc(x[i])}</i>`:esc(x[i]);i++}while(j<n){B+=y[j].trim()?`<i>${esc(y[j])}</i>`:esc(y[j]);j++}return [A,B]}
function fullRows(){const o=CACHE[cur.c.key],al=o.align;if(!fullOnly)return al.map((r,k)=>k);
 const keep=new Set();al.forEach((r,k)=>{if(r[2])for(let d=-2;d<=2;d++)if(al[k+d])keep.add(k+d)});return [...keep].sort((a,b)=>a-b)}
function full(){const o=CACHE[cur.c.key],al=o.align,A=o.A,B=o.B;const idx=fullRows();const chg=al.map((r,k)=>r[2]?k:-1).filter(k=>k>=0);
 const STEP=400,end=Math.min(idx.length,fullPos+STEP);let h=`<div class="ftbar"><label><input type="checkbox" id="fo" ${fullOnly?"checked":""}> 只看差异（前后各 2 行）</label><span>共 ${chg.length} 处不同</span>
 <span class="b" id="prev">↑ 上一处</span><span class="b" id="next">↓ 下一处</span><span style="color:var(--mute)">左：baseline　右：新版　（PDF 直接对比的结果）</span>${o.trunc?'<span style="color:var(--amb)">行数过多，只显示前一部分</span>':""}</div><table class="ft"><colgroup><col style="width:52px"><col><col style="width:52px"><col></colgroup>`;
 let lastPage=null,prevK=null;for(let x=fullPos;x<end;x++){const k=idx[x],r=al[k];const a=r[0]>=0?A[r[0]]:null,b=r[1]>=0?B[r[1]]:null;
  if(prevK!==null&&k!==prevK+1)h+=`<tr class="gap"><td colspan="4">… 省略 ${k-prevK-1} 行相同内容 …</td></tr>`;prevK=k;
  const pg=(b||a).p;if(pg!==lastPage){h+=`<tr class="pg"><td colspan="4">第 ${a?a.p:"-"} 页 ⇄ 第 ${b?b.p:"-"} 页</td></tr>`;lastPage=pg}
  let ta=a?esc(a.t):"",tb=b?esc(b.t):"";if(r[2]&&a&&b)[ta,tb]=wdiff(a.t,b.t);else if(r[2]){if(a)ta=`<i>${ta}</i>`;if(b)tb=`<i>${tb}</i>`}
  h+=`<tr class="${r[2]?"c":""}" id="r${k}"><td class="n">${a?r[0]+1:""}</td><td class="t${a?"":" e"}">${ta}</td><td class="n">${b?r[1]+1:""}</td><td class="t${b?"":" e"}">${tb}</td></tr>`}
 h+="</table>";if(end<idx.length)h+=`<span class="b more" id="more">再显示 ${Math.min(STEP,idx.length-end)} 行（共 ${idx.length} 行）</span>`;
 $("#body").innerHTML=h;$("#fo").onchange=e=>{fullOnly=e.target.checked;fullPos=0;full()};if($("#more"))$("#more").onclick=()=>{fullPos=end;full()};
 const go=d=>{if(!chg.length)return;curChange=Math.max(0,Math.min(chg.length-1,curChange+d));const k=chg[curChange];const p=idx.indexOf(k);
  if(p<fullPos||p>=end){fullPos=Math.max(0,p-50);full()}const el=document.getElementById("r"+k);if(el){document.querySelectorAll("tr.cur").forEach(x=>x.classList.remove("cur"));el.classList.add("cur");el.scrollIntoView({block:"center"})}};
 $("#prev").onclick=()=>go(-1);$("#next").onclick=()=>go(1)}
function frame(k){const f=cur.c.files[k];if(!f)return;const big=f.size>__BIG__;
 if(big&&!f.force){$("#body").innerHTML=`<div class="warn">这个文件有 ${(f.size/1048576).toFixed(1)} MB，在这里打开可能会很慢。<br><br><span class="b p" id="force">仍在这里打开</span>　<a class="b" href="${esc(U(f.path))}" target="_blank">在新标签页打开</a></div>`;$("#force").onclick=()=>{f.force=1;frame(k)};return}
 $("#body").innerHTML=`<iframe src="${esc(U(f.path))}"></iframe>`}
function show(){document.querySelectorAll("#tabs span").forEach(t=>t.classList.toggle("on",t.dataset.t===tab));
 if(tab==="items")items();else if(tab==="full")full();else frame(tab)}
document.querySelectorAll("#tabs span").forEach(t=>t.onclick=()=>{tab=t.dataset.t;fullPos=0;show()});
$("#q").oninput=list;$("#onlyDiff").onchange=list;$("#onlyTodo").onchange=list;
$("#zoom").onclick=()=>$("#zoom").style.display="none";
function totals(){let r=0,q=0;D.cases.forEach(c=>c.items.forEach(([id,v])=>{const x=verdict(id,v);if(x==="real")r++;if(x==="confirm")q++}));return {r,q}}
function dlg(html){$("#dbox").innerHTML=html;$("#dlg").style.display="flex"}
function closeDlg(){$("#dlg").style.display="none"}
function side(){const s=$("#sidef");
 if(done){s.innerHTML='<span style="font-size:12px;color:var(--grn)">✓ 交付文档已生成</span>';return}
 if(!SERVER){s.innerHTML='<span style="font-size:12px;color:var(--mute)">只读查看</span>';return}
 s.innerHTML='<span class="b p" id="go" style="width:100%;text-align:center">生成交付文档</span>';
 $("#go").onclick=()=>{const t=totals();
  if(!t.r){dlg('<b>还没有“真实变化”的条目</b><p>请先把要交给开发的差异标成“是真实变化”。</p><div class="da"><span class="b" onclick="closeDlg()">好的</span></div>');return}
  dlg(`<b>生成交付文档</b><p>将把 <b>${t.r}</b> 处真实变化（含截图和说明）生成 Word 和 Excel。</p>${t.q?`<p style="color:var(--amb)">还有 ${t.q} 条“请确认”没有处理，不会放进交付文档。</p>`:""}
  <label class="dl">文档标题<input id="m_title" value="${esc(D.meta_doc.title||"")}" placeholder="文档差异说明"></label>
  <label class="dl">对比版本<input id="m_versions" value="${esc(D.meta_doc.versions||"")}" placeholder="例如 baseline 20261106 ⇄ 新版 20261120"></label>
  <label class="dl">核实人<input id="m_reviewer" value="${esc(D.meta_doc.reviewer||"")}"></label>
  <div class="da"><span class="b" onclick="closeDlg()">再看看</span><span class="b p" id="ok">生成</span></div>`);
  $("#ok").onclick=async()=>{const meta={};["title","versions","reviewer"].forEach(k=>meta[k]=$("#m_"+k).value.trim());
   dlg('<b>正在生成…</b><p>截图和文档生成需要一点时间，请不要关闭页面。</p>');
   try{const j=await api("/api/deliver",{meta});done=true;side();if(cur)show();
    dlg(`<b>✓ 交付文档已生成</b><p>${j.items} 处真实变化，${j.cases} 个 Case${j.missing?`；<span style="color:var(--amb)">截图待补 ${j.missing} 张</span>`:""}。</p><p class="path">${esc(j.dir)}</p>${(j.files||[]).map(f=>`<p class="path">· ${esc(f)}</p>`).join("")}<p style="color:var(--mute)">可以关闭这个页面了。之后双击“索引.html”可以只读查看。</p><div class="da"><span class="b p" onclick="closeDlg()">好的</span></div>`)}
   catch(e){dlg(`<b>生成失败</b><p>${esc(e.message)}</p><p style="color:var(--mute)">把这段提示发给终端里的 AI 处理。</p><div class="da"><span class="b" onclick="closeDlg()">关闭</span></div>`)}}}}
async function boot(){$("#ro").style.display=SERVER?"none":"block";
 if(SERVER){try{const r=await fetch("/api/state");const j=await r.json();loadRV(j.review);done=!!j.delivered}catch(e){toast("连不上本机服务，按只读显示")}}
 $("#meta").textContent=D.meta;side();stats();list();const first=D.cases.findIndex(c=>c.items.length);open(first>=0?first:0)}
boot();
</script></body></html>"""


# ------------------------------------------------------------------ 索引页

def build_index(out):
    batch, cases = load_items(out)
    rv = verdicts_of(out)
    summ = []
    for i, (c, w) in enumerate(cases):
        files = {k: {"path": rel(p, out), "size": Path(p).stat().st_size}
                 for k, p in c["files"].items() if Path(p).is_file()}
        its = w["items"]
        summ.append({"key": c["label"], "label": c["label"],
                     "bn": Path(c["baseline"]).name if c["baseline"] else "", "nn": Path(c["new"]).name if c["new"] else "",
                     "bp": rel(c["baseline"], out) if c["baseline"] else "", "np": rel(c["new"], out) if c["new"] else "",
                     "files": files, "data": f".dca/c{i}.js", "full": bool(w["A"] and w["B"]),
                     "items": [[x["id"], rv.get(x["id"], {}).get("verdict", x["hint"])] for x in its],
                     "search": " ".join(sorted({rv.get(x["id"], {}).get("field") or "" for x in its}))[:2000]})
    ids = {x["id"] for _, w in cases for x in w["items"]}
    D = {"id": batch["id"], "meta": f"{len(cases)} 个文档 · {batch['id'][:8]}", "cases": summ,
         "rv": {k: {"verdict": v.get("verdict"), "note": v.get("note", ""), "field": v.get("field", "")}
                for k, v in rv.items() if k in ids},
         "meta_doc": batch.get("meta") or {}}
    page = (PAGE.replace("__TITLE__", _html.escape((batch.get("meta") or {}).get("index_title") or "对比整理"))
            .replace("__BIG__", str(BIG_HTML))
            .replace("__DATA__", json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    (out / "索引.html").write_text(page, encoding="utf-8")
    return out / "索引.html"


def cmd_build(a):
    out = batch_dir(a)
    print(f"索引页：{build_index(out).resolve()}")
# ------------------------------------------------------------------ 第 7 步：交付文档

def _deliver_rows(out, cases, verdicts):
    rows = []
    for c, w in cases:
        for it in w["items"]:
            v = verdicts.get(it["id"], {})
            if v.get("verdict") == "real":
                rows.append((c, it, v))
    rows.sort(key=lambda x: (nat(x[0]["label"]), x[1].get("page_new") or x[1].get("page_old") or 0,
                             x[1]["rj"] if x[1]["rj"] is not None else (x[1]["ri"] or 0)))
    return rows


def _val(it, side):
    t = it[side]
    if not t:
        return "（缺少这一行）"
    f = " ".join(it["frag_" + side])
    return f if f and len(t) > 60 else t


def _where(it, v):
    pn = it.get("page_new") or it.get("page_old")
    return (f"第 {pn} 页" if pn else "") + (f" · {v.get('field')}" if v.get("field") else "")


def write_docx(path, out, rows, meta, lead):
    docx = need("docx", "python-docx")
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def font(run, size=None, bold=None, color=None):
        if size:
            run.font.size = Pt(size)
        if bold is not None:
            run.bold = bold
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        rpr = run._element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rpr.append(rf)
        rf.set(qn("w:eastAsia"), "微软雅黑")
        return run

    def shade(cell, fill):
        tcpr = cell._tc.get_or_add_tcPr()
        s = OxmlElement("w:shd")
        s.set(qn("w:val"), "clear"), s.set(qn("w:color"), "auto"), s.set(qn("w:fill"), fill)
        tcpr.append(s)

    def run_shade(run, fill):
        s = OxmlElement("w:shd")
        s.set(qn("w:val"), "clear"), s.set(qn("w:color"), "auto"), s.set(qn("w:fill"), fill)
        run._element.get_or_add_rPr().append(s)

    def underline_par(p):
        ppr = p._p.get_or_add_pPr()
        b = OxmlElement("w:pBdr")
        bt = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "12"), ("w:space", "1"), ("w:color", "1F2329")):
            bt.set(qn(k), v)
        b.append(bt)
        ppr.append(b)

    def no_split(row):
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))

    def field(p, instr):
        for kind, text in (("begin", None), (None, instr), ("end", None)):
            r = p.add_run()
            font(r, 9, color="999999")
            if kind:
                e = OxmlElement("w:fldChar")
                e.set(qn("w:fldCharType"), kind)
            else:
                e = OxmlElement("w:instrText")
                e.set(qn("xml:space"), "preserve")
                e.text = text
            r._r.append(e)

    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name = "Microsoft YaHei"
    st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(2))
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2)
    title = meta.get("title") or "文档差异说明"
    hp = sec.header.paragraphs[0]
    font(hp.add_run(f"{meta.get('header') or title}\t\t{datetime.date.today():%Y-%m-%d}"), 9, color="999999")
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(fp.add_run("第 "), 9, color="999999"), field(fp, "PAGE"), font(fp.add_run(" 页 / 共 "), 9, color="999999")
    field(fp, "NUMPAGES"), font(fp.add_run(" 页"), 9, color="999999")

    font(d.add_paragraph().add_run(title), 18, True)
    font(d.add_paragraph().add_run(lead), 10.5)
    mrows = [(k, meta.get(f)) for k, f in (("产品 / 文档", "product"), ("对比版本", "versions"),
                                           ("测试环境", "env"), ("核实人", "reviewer"), ("关联单号", "ticket")) if meta.get(f)]
    if mrows:
        t = d.add_table(rows=(len(mrows) + 1) // 2, cols=4)
        t.style = "Table Grid"
        for n, (k, v) in enumerate(mrows):
            ck, cv = t.cell(n // 2, (n % 2) * 2), t.cell(n // 2, (n % 2) * 2 + 1)
            shade(ck, "F4F5F7")
            font(ck.paragraphs[0].add_run(k), 9.5, color="444444")
            font(cv.paragraphs[0].add_run(str(v)), 9.5)

    def h3(text):
        p = d.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.keep_with_next = True
        font(p.add_run(text), 13, True)
        underline_par(p)

    h3("差异一览")
    t = d.add_table(rows=1, cols=6)
    t.style = "Table Grid"
    for i, h in enumerate(("编号", "Case", "页码", "位置 / 字段", "baseline", "新版")):
        shade(t.rows[0].cells[i], "1F2329")
        font(t.rows[0].cells[i].paragraphs[0].add_run(h), 9, True, "FFFFFF")
    for no, (c, it, v) in rows:
        cells = t.add_row().cells
        pn = it.get("page_new") or it.get("page_old") or ""
        for i, (txt, red) in enumerate(((no, False), (c["label"], False), (str(pn), False),
                                        (v.get("field") or "", False), (_val(it, "old")[:80], False), (_val(it, "new")[:80], True))):
            font(cells[i].paragraphs[0].add_run(txt), 9, red or None, "E02D2D" if red else None)

    last = None
    for no, (c, it, v) in rows:
        if c["label"] != last:
            h3(f"{c['label']}　{Path(c['new'] or c['baseline']).stem}")
            last = c["label"]
        p = d.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.keep_with_next = True
        r = font(p.add_run(f" {no} "), 9.5, True, "FFFFFF")
        run_shade(r, "1F2329")
        font(p.add_run("  " + (v.get("field") or it["kind"])), 11, True)
        font(p.add_run("　　" + _where(it, v)), 9.5, color="666666")
        kv = d.add_table(rows=1, cols=4)
        kv.style = "Table Grid"
        for i, (txt, k) in enumerate((("baseline", 1), (it["old"] or "（缺少这一行）", 0), ("新版", 1), (it["new"] or "（缺少这一行）", 0))):
            cell = kv.rows[0].cells[i]
            if k:
                shade(cell, "F4F5F7")
                font(cell.paragraphs[0].add_run(txt), 9.5, color="444444")
            else:
                seg = it["seg_old" if i == 1 else "seg_new"]
                if seg:
                    for s, ch in seg:
                        font(cell.paragraphs[0].add_run(s), 9.5, bool(ch), "E02D2D" if ch else None)
                else:
                    font(cell.paragraphs[0].add_run(txt), 9.5, color="999999")
        for cell, w in zip(kv.rows[0].cells, (Cm(1.8), Cm(6.7), Cm(1.8), Cm(6.7))):
            cell.width = w
        no_split(kv.rows[0])
        pics = d.add_table(rows=2, cols=2)
        for i, side in enumerate(("old", "new")):
            cell = pics.cell(0, i)
            s = it.get("shot_" + side)
            ok = False
            if s and (out / s).is_file():
                try:
                    cell.paragraphs[0].add_run().add_picture(str(out / s), width=Cm(8.1))
                    ok = True
                except Exception:
                    ok = False
            if not ok:
                font(cell.paragraphs[0].add_run(it.get("snote_" + side) or "截图待补"), 9, color="B26A00")
            pg = it.get("page_" + side)
            cap = ("baseline" if side == "old" else "新版") + (f" 第 {pg} 页" if pg else "")
            if ok and it.get("snote_" + side):
                cap += f"（{it['snote_' + side]}）"
            cp = pics.cell(1, i).paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            font(cp.add_run(cap), 8.5, color="666666")
        for row in pics.rows:
            no_split(row)
        if v.get("note"):
            sp = d.add_paragraph()
            sp.paragraph_format.space_before = Pt(4)
            font(sp.add_run("说明："), 10, True)
            font(sp.add_run(v["note"]), 10)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))


def write_xlsx(path, out, rows, cases, verdicts):
    opx = need("openpyxl", "openpyxl")
    need("PIL", "pillow")
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill
    from PIL import Image as PILImage
    wb = opx.Workbook()
    ws = wb.active
    ws.title = "差异说明"
    head = ["编号", "Case", "页码", "位置 / 字段", "baseline", "新版", "说明", "baseline 截图", "新版截图", "处理情况（开发填写）"]
    ws.append(head)
    fill = PatternFill("solid", fgColor="DBE9E1")
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True, color="1F3D2B"), fill
    for col, wdt in zip("ABCDEFGHIJ", (8, 10, 6, 22, 26, 26, 40, 44, 44, 24)):
        ws.column_dimensions[col].width = wdt
    wrap = Alignment(wrap_text=True, vertical="top")
    PX = 300
    for r, (no, (c, it, v)) in enumerate(rows, 2):
        pn = it.get("page_new") or it.get("page_old") or ""
        ws.append([no, c["label"], pn, v.get("field") or "", it["old"] or "（缺少这一行）", it["new"] or "（缺少这一行）",
                   v.get("note") or "", "", "", ""])
        for cell in ws[r]:
            cell.alignment = wrap
        ws.cell(r, 6).font = Font(color="E02D2D", bold=True)
        hmax = 0
        for col, side in ((8, "old"), (9, "new")):
            s = it.get("shot_" + side)
            if s and (out / s).is_file():
                try:
                    with PILImage.open(out / s) as im:
                        w0, h0 = im.size
                    img = XLImage(str(out / s))
                    img.width, img.height = PX, int(h0 * PX / max(1, w0))
                    ws.add_image(img, f"{ws.cell(r, col).column_letter}{r}")
                    hmax = max(hmax, img.height)
                    continue
                except Exception:
                    pass
            ws.cell(r, col).value = it.get("snote_" + side) or "截图待补"
        ws.row_dimensions[r].height = min(409, max(32, hmax * 0.75 + 8))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{max(2, len(rows) + 1)}"
    s2 = wb.create_sheet("汇总")
    s2.append(["Case", "baseline 文件", "新版文件", "真实差异", "已排除（日期 / 人名等）"])
    for cell in s2[1]:
        cell.font, cell.fill = Font(bold=True, color="1F3D2B"), fill
    for c, w in cases:
        vs = [verdicts.get(it["id"], {}).get("verdict") for it in w["items"]]
        s2.append([c["label"], Path(c["baseline"]).name if c["baseline"] else "", Path(c["new"]).name if c["new"] else "",
                   vs.count("real"), vs.count("exclude")])
    for col, wdt in zip("ABCDE", (12, 46, 46, 10, 22)):
        s2.column_dimensions[col].width = wdt
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))




def deliver(out, meta_in=None):
    """生成交付文档（Word + Excel），返回汇总。只放“真实变化”。"""
    batch, cases = load_items(out)
    rv = verdicts_of(out)
    meta = dict(batch.get("meta") or {})
    meta.update({k: v for k, v in (meta_in or {}).items() if v})
    batch["meta"] = meta
    if not any(v.get("verdict") == "real" for v in rv.values()):
        raise RuntimeError("没有标为“真实变化”的条目，交付文档为空")
    make_shots(out, batch, cases, rv, only_missing=True)      # 人工改成“真实变化”但还没截图的，在这里补
    batch, cases = load_items(out)
    real = _deliver_rows(out, cases, rv)
    rows = [(f"D{n:02d}", x) for n, x in enumerate(real, 1)]
    ex = sum(1 for v in rv.values() if v.get("verdict") == "exclude")
    left = sum(1 for v in rv.values() if v.get("verdict") == "confirm")
    k = len({c["label"] for _, (c, _, _) in rows})
    lead = (f"新版生成的文档与 baseline 相比，经测试核实共有 {len(rows)} 处真实差异，涉及 {k} 个 Case。"
            + (f"日期、人名等每次生成都会变化的内容（{ex} 条）已排除，不在本文档内。" if ex else ""))
    fname = re.sub(r'[\\/:*?"<>|]+', "_", meta.get("title") or "文档差异说明")
    dd = out / "交付"
    files = []
    for ext, fn in (("docx", lambda p: write_docx(p, out, rows, meta, lead)),
                    ("xlsx", lambda p: write_xlsx(p, out, rows, cases, rv))):
        p = dd / f"{fname}.{ext}"
        try:
            fn(p)
        except PermissionError:
            p = dd / f"{fname}_{datetime.datetime.now():%H%M%S}.{ext}"     # 旧文件在 Word / Excel 里开着
            fn(p)
        files.append(str(p.resolve()))
    miss = sum(1 for _, (c, it, v) in rows for s in ("old", "new")
               if not it.get("shot_" + s) and (it[s] or it.get("a" + ("i" if s == "old" else "j")) is not None))
    batch["delivered"] = {"at": f"{datetime.datetime.now():%Y-%m-%d %H:%M}", "items": len(rows), "cases": k,
                          "missing": miss, "confirm_left": left, "files": files}
    jsave(W(out) / "batch.json", batch)
    build_index(out)
    return {"ok": True, "dir": str(dd.resolve()), "files": files, "items": len(rows), "cases": k,
            "missing": miss, "confirm_left": left}


def cmd_deliver(a):
    out = batch_dir(a)
    try:
        r = deliver(out, {"title": a.title, "versions": a.versions, "reviewer": a.reviewer})
    except RuntimeError as e:
        die(str(e))
    print(f"交付文档：{r['items']} 处真实差异，{r['cases']} 个 Case；截图待补 {r['missing']} 张；"
          f"还有 {r['confirm_left']} 条“请确认”没处理（未放进交付文档）")
    for f in r["files"]:
        print("  " + f)


# ------------------------------------------------------------------ 核实页面（本机服务）

def _serve(out):
    import threading
    import time
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    batch = jload(W(out) / "batch.json")
    allowed = {str(Path(p).resolve()).lower() for c in batch["cases"]
               for p in [c["baseline"], c["new"]] + list(c["files"].values()) if p}
    root = out.resolve()
    lock = threading.Lock()
    state = {"last": time.time(), "busy": False}
    TYPES = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
             ".png": "image/png", ".pdf": "application/pdf", ".json": "application/json"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            h = (self.headers.get("Host") or "").split(":")[0]
            return h in ("127.0.0.1", "localhost")

        def do_GET(self):
            state["last"] = time.time()
            if not self._host_ok():
                return self._send(403, {"ok": False})
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, (out / "索引.html").read_bytes(), TYPES[".html"])
            if u.path == "/api/state":
                b = jload(W(out) / "batch.json")
                return self._send(200, {"ok": True, "review": verdicts_of(out), "delivered": bool(b.get("delivered"))})
            if u.path == "/_f":
                p = urllib.parse.parse_qs(u.query).get("p", [""])[0]
                f = (root / p).resolve() if not p.startswith("file:") else Path(urllib.parse.unquote(p[7:].lstrip("/")))
                inside = str(f).lower().startswith(str(root).lower())
                if not f.is_file() or not (inside or str(f).lower() in allowed):
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, f.read_bytes(), TYPES.get(f.suffix.lower(), "application/octet-stream"))
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            state["last"] = time.time()
            if not self._host_ok() or self.headers.get("X-DCA") != "1":
                return self._send(403, {"ok": False, "error": "拒绝访问"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except ValueError:
                return self._send(400, {"ok": False, "error": "请求格式不对"})
            if self.path == "/api/save":
                with lock:
                    rv = verdicts_of(out)
                    r = rv.get(body.get("id"))
                    key = body.get("key")
                    if r is None or key not in ("verdict", "note", "field"):
                        return self._send(400, {"ok": False, "error": "没有这一条"})
                    if key == "verdict" and body.get("value") not in ("real", "exclude", "confirm"):
                        return self._send(400, {"ok": False, "error": "结论不对"})
                    r[key] = str(body.get("value") or "")[:2000]
                    if key == "verdict":
                        r["by"] = "人工"
                    jsave(W(out) / "review.json", rv)
                return self._send(200, {"ok": True})
            if self.path == "/api/deliver":
                if state["busy"]:
                    return self._send(409, {"ok": False, "error": "正在生成，请稍候"})
                state["busy"] = True
                try:
                    with lock:
                        res = deliver(out, body.get("meta") or {})
                    print(f"[{datetime.datetime.now():%H:%M}] 交付文档已生成：{res['files']}", flush=True)
                    self._send(200, res)
                    threading.Timer(3.0, srv.shutdown).start()        # 生成完就退出，不留后台进程
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})
                finally:
                    state["busy"] = False
                return
            return self._send(404, {"ok": False})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    jsave(W(out) / "server.json", {"port": port, "pid": os.getpid(), "started": time.time()})

    def idle():
        while True:
            time.sleep(60)
            if time.time() - state["last"] > 4 * 3600 and not state["busy"]:     # 4 小时没人操作就退出
                srv.shutdown()
                return
    threading.Thread(target=idle, daemon=True).start()
    print(f"核实页面服务：http://127.0.0.1:{port}/", flush=True)
    try:
        srv.serve_forever()
    finally:
        try:
            (W(out) / "server.json").unlink()
        except OSError:
            pass


def _alive(out):
    import urllib.request
    s = jload(W(out) / "server.json")
    if not s:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{s['port']}/api/state", timeout=2) as r:
            if r.status == 200:
                return s["port"]
    except Exception:
        pass
    return None


def cmd_serve(a):
    _serve(batch_dir(a))


def cmd_review(a):
    """在后台启动核实页面并打开浏览器，命令本身马上返回（不会卡住终端）。"""
    import subprocess
    import time
    import webbrowser
    out = batch_dir(a)
    batch = jload(W(out) / "batch.json")
    meta = dict(batch.get("meta") or {})
    meta.update({k: v for k, v in (("title", a.title), ("versions", a.versions), ("reviewer", a.reviewer)) if v})
    batch["meta"] = meta
    batch.pop("delivered", None) if a.reopen else None
    jsave(W(out) / "batch.json", batch)
    if not (out / "索引.html").is_file() or a.rebuild:
        build_index(out)
    port = _alive(out)
    if not port:
        log = open(W(out) / "server.log", "a", encoding="utf-8")
        kw = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL, "cwd": str(out)}
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000      # 不弹黑窗口、和终端分离
        else:
            kw["start_new_session"] = True
        exe = sys.executable
        if os.name == "nt" and exe.lower().endswith("python.exe") and Path(exe[:-10] + "pythonw.exe").is_file():
            exe = exe[:-10] + "pythonw.exe"
        try:
            (W(out) / "server.json").unlink()
        except OSError:
            pass
        subprocess.Popen([exe, str(Path(__file__).resolve()), "serve", "--out", str(out)], **kw)
        for _ in range(100):
            time.sleep(0.15)
            port = _alive(out)
            if port:
                break
        if not port:
            die(f"核实页面没有启动成功，请看 {W(out) / 'server.log'}")
    url = f"http://127.0.0.1:{port}/"
    if not a.no_browser:
        webbrowser.open(url)
    print(f"核实页面已打开：{url}")
    print("请在页面里逐条核实，确认后点左下角“生成交付文档”。生成完页面服务会自动退出。")


def cmd_status(a):
    out = batch_dir(a)
    b = jload(W(out) / "batch.json")
    d = b.get("delivered")
    port = _alive(out)
    if d:
        print(f"已生成交付文档（{d['at']}）：{d['items']} 处真实差异，{d['cases']} 个 Case，截图待补 {d['missing']} 张，"
              f"“请确认”未处理 {d['confirm_left']} 条")
        for f in d["files"]:
            print("  " + f)
    else:
        print("还没有生成交付文档。" + (f"核实页面在运行：http://127.0.0.1:{port}/" if port else "核实页面没有运行。"))


# ------------------------------------------------------------------ 第 1 步：启动同事的对比脚本

HOME_DIR = Path.home() / ".dca"
CFG = HOME_DIR / "config.json"
RUN = HOME_DIR / "run.json"
RUN_LOG = HOME_DIR / "run.log"


def cmd_setup(a):
    """记住同事的对比脚本怎么启动（只需要设置一次）。"""
    cfg = jload(CFG, {}) or {}
    for k in ("command", "cwd", "results", "pdf", "baseline", "new"):
        v = getattr(a, k, None)
        if v is not None:
            cfg[k] = v
    if a.show:
        print(json.dumps(cfg, ensure_ascii=False, indent=1) if cfg else "还没有设置")
        return
    if not cfg.get("command"):
        die("请用 --command 给出他平时启动对比的命令，例如：--command \"python main.py\"")
    if cfg.get("cwd") and not Path(cfg["cwd"]).is_dir():
        die(f"--cwd 文件夹不存在：{cfg['cwd']}")
    jsave(CFG, cfg)
    print("已保存启动设置：")
    print(json.dumps(cfg, ensure_ascii=False, indent=1))


def _run_state():
    s = jload(RUN, {}) or {}
    if s.get("state") == "running":
        try:
            if os.name == "nt":
                import subprocess
                r = subprocess.run(["tasklist", "/FI", f"PID eq {s['runner']}"], capture_output=True, text=True)
                alive = str(s["runner"]) in r.stdout
            else:
                os.kill(s["runner"], 0)
                alive = True
        except Exception:
            alive = False
        if not alive:
            s.update(state="failed", error="运行进程意外结束（可能被关闭了），请看日志")
            jsave(RUN, s)
    return s


def _find_results(roots, since):
    """在可能的位置找这次运行新生成的 total / ignore html，返回它们共同的上级文件夹。"""
    hits = []
    for r in roots:
        r = Path(r)
        if not r.is_dir():
            continue
        for p in r.rglob("*.htm*"):
            try:
                if html_kind(p.name) in ("total", "ignore", "difference") and p.stat().st_mtime >= since - 5:
                    hits.append(p)
            except OSError:
                continue
        if hits:
            break
    if not hits:
        return None, 0
    common = Path(os.path.commonpath([str(p.parent) for p in hits]))
    return str(common), len(hits)


def _runner(cmd, cwd, roots, timeout):
    """后台进程：运行他的命令，写日志和状态。"""
    import subprocess
    import time
    t0 = time.time()
    st = {"state": "running", "runner": os.getpid(), "cmd": cmd, "cwd": cwd, "start": t0,
          "start_text": f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}"}
    jsave(RUN, st)
    with open(RUN_LOG, "w", encoding="utf-8", errors="replace") as log:
        try:
            p = subprocess.Popen(cmd, shell=True, cwd=cwd or None, stdout=log, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL)
            st["child"] = p.pid
            jsave(RUN, st)
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            st.update(state="failed", error=f"运行超过 {timeout // 60} 分钟，已停止")
            jsave(RUN, st)
            return
        except Exception as e:
            st.update(state="failed", error=f"启动失败：{type(e).__name__}: {e}")
            jsave(RUN, st)
            return
    st["code"], st["seconds"] = code, round(time.time() - t0)
    res, n = _find_results(roots, t0)
    st["results"], st["result_files"] = res, n
    if code != 0:
        st.update(state="failed", error=f"他的脚本返回了错误码 {code}")
    elif not res:
        st.update(state="failed", error="脚本跑完了，但没找到这次新生成的 total / ignore 文件")
    else:
        st["state"] = "done"
    jsave(RUN, st)


def cmd_launch(a):
    """在后台启动他的对比脚本，命令马上返回；用 launch-status 查看进度。"""
    import subprocess
    cfg = jload(CFG, {}) or {}
    cmd = a.command or cfg.get("command")
    cwd = a.cwd or cfg.get("cwd") or ""
    if not cmd:
        die("还不知道他的对比脚本怎么启动：请先问用户，然后运行 setup --command \"...\" --cwd \"...\"")
    if _run_state().get("state") == "running":
        die("上一次还在运行中，用 launch-status 查看")
    roots = [x for x in (a.results or cfg.get("results"), cwd) if x]
    if not roots:
        die("请用 setup --results 告诉我他的结果一般输出到哪个文件夹")
    if a.runner:
        _runner(cmd, cwd, roots, a.timeout)
        return
    HOME_DIR.mkdir(exist_ok=True)
    jsave(RUN, {"state": "starting"})
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kw["start_new_session"] = True
    args = [sys.executable, str(Path(__file__).resolve()), "launch", "--runner", "--timeout", str(a.timeout),
            "--command", cmd, "--cwd", cwd]
    if a.results or cfg.get("results"):
        args += ["--results", a.results or cfg.get("results")]
    subprocess.Popen(args, **kw)
    print(f"已在后台启动：{cmd}" + (f"（在 {cwd}）" if cwd else ""))
    print("用 launch-status --wait 500 等它跑完（最多等 500 秒，可以重复运行）")


def cmd_launch_status(a):
    import time
    t_end = time.time() + max(0, a.wait)
    while True:
        s = _run_state()
        if s.get("state") not in ("running", "starting") or time.time() >= t_end:
            break
        time.sleep(5)
    state = s.get("state") or "未运行"
    print(f"状态：{ {'running': '运行中', 'starting': '启动中', 'done': '完成', 'failed': '失败'}.get(state, state)}")
    if s.get("start_text"):
        print(f"开始于 {s['start_text']}" + (f"，用时 {s['seconds']} 秒" if s.get("seconds") is not None else ""))
    if s.get("error"):
        print("问题：" + s["error"])
    if s.get("results"):
        print(f"结果文件夹：{s['results']}（新生成 {s['result_files']} 个 total / ignore 文件）")
    if RUN_LOG.is_file() and (state in ("failed",) or a.log):
        lines = RUN_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"--- 他的脚本输出（最后 {min(30, len(lines))} 行）---")
        for l in lines[-30:]:
            print("  " + l[:200])


# ------------------------------------------------------------------ 其他命令

def cmd_check(a):
    ok = True
    for mod, pip in (("fitz", "pymupdf"), ("docx", "python-docx"), ("openpyxl", "openpyxl"), ("PIL", "pillow")):
        try:
            __import__(mod)
            print(f"  ✓ {pip}")
        except ImportError:
            ok = False
            print(f"  ✗ 缺少 {pip}")
    print(f"dca_tool {VERSION}，Python {sys.version.split()[0]}")
    print("环境正常" if ok else "请运行：pip install pymupdf python-docx openpyxl pillow")


def cmd_clean(a):
    """交付后清理：删掉截图以外的大文件不安全，这里只删索引页用不到的日志和服务记录。"""
    out = batch_dir(a)
    for p in (W(out) / "server.log", W(out) / "server.json"):
        try:
            p.unlink()
        except OSError:
            pass
    print("已清理")


def main(argv=None):
    ap = argparse.ArgumentParser(description="文档对比助手")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("scan")
    s.add_argument("--pdf")
    s.add_argument("--baseline")
    s.add_argument("--new")
    s.add_argument("--results")
    s.add_argument("--out")
    sub.add_parser("inspect").add_argument("file")
    s = sub.add_parser("extract")
    s.add_argument("--out", required=True)
    s.add_argument("--source", default="auto", choices=["auto", "ignore", "difference", "total", "pdf"])
    s = sub.add_parser("list")
    s.add_argument("--out", required=True)
    s.add_argument("--case")
    s.add_argument("--verdict", choices=["real", "exclude", "confirm"])
    s.add_argument("--cat")
    s.add_argument("--origin", choices=["kept", "filtered", "missed", "pdf"])
    s.add_argument("--limit", type=int, default=80)
    s.add_argument("--offset", type=int, default=0)
    s = sub.add_parser("setup")
    for k in ("command", "cwd", "results", "pdf", "baseline", "new"):
        s.add_argument("--" + k)
    s.add_argument("--show", action="store_true")
    s = sub.add_parser("launch")
    s.add_argument("--command")
    s.add_argument("--cwd")
    s.add_argument("--results")
    s.add_argument("--timeout", type=int, default=4 * 3600)
    s.add_argument("--runner", action="store_true", help=argparse.SUPPRESS)
    s = sub.add_parser("launch-status")
    s.add_argument("--wait", type=int, default=0)
    s.add_argument("--log", action="store_true")
    for name in ("shots", "build", "serve", "status", "clean"):
        sub.add_parser(name).add_argument("--out", required=True)
    for name in ("review", "deliver"):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True)
        s.add_argument("--title")
        s.add_argument("--versions")
        s.add_argument("--reviewer")
        if name == "review":
            s.add_argument("--rebuild", action="store_true")
            s.add_argument("--reopen", action="store_true", help="已生成过交付文档、还要再改时用")
            s.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    {"check": cmd_check, "scan": cmd_scan, "inspect": cmd_inspect, "extract": cmd_extract, "list": cmd_list,
     "shots": cmd_shots, "build": cmd_build, "serve": cmd_serve, "review": cmd_review, "status": cmd_status,
     "deliver": cmd_deliver, "clean": cmd_clean, "setup": cmd_setup, "launch": cmd_launch,
     "launch-status": cmd_launch_status}[a.cmd](a)


if __name__ == "__main__":
    main()
# ==== DCA_TOOL_END ====
```
