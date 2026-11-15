"""报告：total.html（完整对比，格式与现在相同）、ignore.html（精简结果）、result.json、按负责人打包。

- ignore.html 在本机给同事A 自己核对用，文字不打码；差异截图一律打码。
- 发给别人的包（packages/<负责人>.zip）里的文字和截图都打码，只含这个负责人的“真实差异”和“不确定”。
- result.masked.json 是打码后的结果，交给 AI 写汇报时只给它这一份。
"""
from __future__ import annotations

import difflib
import html
import json
import zipfile
from pathlib import Path

from filters import fmt_shift

CSS = """body{font:14px/1.6 "Microsoft YaHei","PingFang SC",sans-serif;margin:0;background:#f6f7f9;color:#222}
.wrap{max-width:1200px;margin:0 auto;padding:22px}h1{font-size:20px;margin:0 0 8px}h2{font-size:16px;margin:26px 0 8px}
.sum{background:#fff;border:1px solid #e2e4e8;border-radius:8px;padding:12px 16px}.sum b{font-size:16px}
.warn{background:#fff4e5;border:1px solid #f3c98b;border-radius:8px;padding:10px 14px;margin-top:12px}
table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #e2e4e8;padding:6px 8px;vertical-align:top;text-align:left}
th{background:#f0f2f5;font-weight:600;font-size:13px}td.id{white-space:nowrap;font-weight:600}td.w{white-space:nowrap;color:#666;font-size:12px}
td.v{font-family:Consolas,Menlo,monospace;font-size:13px;word-break:break-all;width:24%}td.n{font-size:12px;color:#444}
del{background:#fbd3d3;text-decoration:none}ins{background:#c9f1cf;text-decoration:none}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:9px;background:#eef;color:#335;margin:0 3px 2px 0}
.tag.r{background:#fde2e2;color:#a11}.shots{display:flex;gap:8px;margin-top:6px}.shots a{flex:1}.shots img{width:100%;border:1px solid #ddd}
.shots span{font-size:11px;color:#666}details{margin-top:8px}summary{cursor:pointer;font-weight:600}.muted{color:#888;font-size:12px}"""

STATUS_CN = {"real": "真实差异", "unsure": "不确定", "ignored": "已忽略", "layout": "位置变化"}
KIND_CN = {"changed": "内容变化", "added": "新文件多出", "removed": "新文件缺少", "moved": "位置变化"}


def page_ranges(pages) -> str:
    pages = sorted(pages)
    out, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        out.append(str(pages[i]) if i == j else f"{pages[i]}–{pages[j]}")
        i = j + 1
    return "、".join(out)


def where(refs) -> str:
    if not refs:
        return "（无）"
    f, l = refs[0], refs[-1]
    page = f"第 {f['page']} 页 " if f.get("page") else ""
    line = f"第 {f['no']} 行" if f["no"] == l["no"] else f"第 {f['no']}–{l['no']} 行"
    return page + line


def highlight(old: str, new: str, esc=html.escape):
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    ra, rb = [], []
    for t, i1, i2, j1, j2 in sm.get_opcodes():
        x, y = esc(old[i1:i2]), esc(new[j1:j2])
        if t == "equal":
            ra.append(x)
            rb.append(y)
        else:
            ra.append(f"<del>{x}</del>" if x else "")
            rb.append(f"<ins>{y}</ins>" if y else "")
    return "".join(ra), "".join(rb)


def _values(it, mask):
    old = [mask(s) for s in it["old"]]
    new = [mask(s) for s in it["new"]]
    if old and new and len(old) == len(new):
        pairs = [highlight(o, n) for o, n in zip(old, new)]
        return "<br>".join(p[0] for p in pairs), "<br>".join(p[1] for p in pairs)
    return ("<br>".join(f"<del>{html.escape(s)}</del>" for s in old) or "（无）",
            "<br>".join(f"<ins>{html.escape(s)}</ins>" for s in new) or "（无）")


def _row(it, mask, shots=True):
    old, new = _values(it, mask)
    tags = "".join(f'<span class="tag{" r" if f in ("复读不一致", "疑似人名") else ""}">{html.escape(f)}</span>' for f in it["flags"])
    place = html.escape(mask(" › ".join(x for x in (it["section"], it["field"]) if x)) or "")
    imgs = ""
    if shots and it.get("shots"):
        imgs = '<div class="shots">' + "".join(
            f'<a href="{html.escape(s["file"])}" target="_blank"><span>{"baseline" if s["side"] == "a" else "新文件"} 第 {s["page"]} 页</span>'
            f'<img loading="lazy" src="{html.escape(s["file"])}"></a>' for s in it["shots"]) + "</div>"
    return (f'<tr><td class="id">{it["id"]}<div class="muted">{KIND_CN[it["kind"]]}</div></td>'
            f'<td class="w">{where(it["a"])}<br>{where(it["b"])}<div>{place}</div><div>负责人：{html.escape(it["owner"])}</div></td>'
            f'<td class="v">{old}</td><td class="v">{new}</td>'
            f'<td class="n">{tags}{html.escape(mask(it["reason"]))}{imgs}</td></tr>')


def _table(items, mask, shots=True):
    if not items:
        return "<p class='muted'>无</p>"
    head = "<tr><th>编号</th><th>位置（baseline / 新文件）</th><th>baseline</th><th>新文件</th><th>说明</th></tr>"
    return "<table>" + head + "".join(_row(x, mask, shots) for x in items) + "</table>"


def warnings_html(res) -> str:
    out = []
    for side, label in (("baseline", "baseline"), ("new", "新文件")):
        d = res[side]
        if d.get("no_text_pages"):
            ocr = [p for p in d["no_text_pages"] if p in d.get("ocr_pages", [])]
            rest = [p for p in d["no_text_pages"] if p not in ocr]
            if rest:
                out.append(f"{label}：第 {page_ranges(rest)} 页没有文字层（多为扫描页），<b>这些页没有比较，不代表没有差异</b>。"
                           f"可以运行 ocr-prepare 转成图片，用「识别截图.bat」识别后再对比。")
            if ocr:
                out.append(f"{label}：第 {page_ranges(ocr)} 页是扫描页，文字由识别得到，这些页上的变化都列在“不确定”里。")
        if d.get("big_image_pages"):
            out.append(f"{label}：第 {page_ranges(d['big_image_pages'])} 页大部分是图片，图片里的文字没有比较。")
    v = res.get("verify") or {}
    if v.get("note"):
        out.append(v["note"])
    return "".join(f'<div class="warn">{x}</div>' for x in out)


def report_html(res, mask=lambda s: s, title_note="", only=None, appendix=True) -> str:
    items = res["items"] if only is None else [x for x in res["items"] if only(x)]
    by = lambda s: [x for x in items if x["status"] == s]
    s = res["stats"]
    mode = res.get("date_shift")
    shift = f"日期整体{fmt_shift(mode)}" if mode is not None else ("日期平移天数不统一，见“不确定”" if res.get("date_shifts") else "没有日期变化")
    v = res.get("verify") or {}
    vtxt = f"；含数字的 {v['checked']} 行已用第二种方式复读，{v['mismatch']} 行不一致" if v.get("used") and v.get("checked") else ""
    body = f"""<h1>文档对比：{html.escape(mask(res['baseline']['name']))} ↔ {html.escape(mask(res['new']['name']))}{title_note}</h1>
<div class="sum">真实差异 <b>{len(by('real'))}</b>　不确定 <b>{len(by('unsure'))}</b>　已忽略 <b>{len(by('ignored'))}</b>　位置变化 <b>{len(by('layout'))}</b><br>
<span class="muted">{shift}；人名清单 {len(res['names'])} 个{vtxt}。比较了 baseline {s['baseline_lines']} 行、新文件 {s['new_lines']} 行（页眉页脚已去掉）。完整对比见 total.html。</span></div>
{warnings_html(res)}
<h2>一、真实差异</h2>{_table(by('real'), mask)}
<h2>二、不确定（请人工判断）</h2>{_table(by('unsure'), mask)}"""
    if appendix:
        names = "、".join(html.escape(mask(f"{n}（{src}）")) for n, src in res["names"].items())
        body += f"""<h2>附录一：已忽略（只差日期或人名，可抽查）</h2>{_table(by('ignored'), mask, shots=False)}
<h2>附录二：位置变化（内容相同，可抽查）</h2>{_table(by('layout'), mask, shots=False)}
<details><summary>人名清单（{len(res['names'])} 个）</summary><p>{names}</p></details>"""
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>文档对比结果</title><style>{CSS}</style></head><body><div class="wrap">{body}</div></body></html>'


def total_html(doc_a, doc_b) -> str:
    """完整对比：与现在的 total 报告同样的 difflib 格式，不做任何过滤。"""
    return difflib.HtmlDiff(wrapcolumn=90).make_file([l["t"] for l in doc_a["lines"]], [l["t"] for l in doc_b["lines"]],
                                                    doc_a["name"], doc_b["name"])


def mask_result(res, mask):
    def m(x):
        if isinstance(x, str):
            return mask(x)
        if isinstance(x, list):
            return [m(v) for v in x]
        if isinstance(x, dict):
            return {k: m(v) for k, v in x.items()}
        return x
    out = m({k: v for k, v in res.items() if k != "names"})
    out["names"] = {f"人名{i}": src for i, src in enumerate(res["names"].values(), 1)}
    out["masked"] = True
    return out


def write_all(out_dir, res, doc_a, doc_b, mask, total=True) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "result.masked.json").write_text(json.dumps(mask_result(res, mask), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "ignore.html").write_text(report_html(res), encoding="utf-8")
    if total:
        (out / "total.html").write_text(total_html(doc_a, doc_b), encoding="utf-8")
    write_packages(out, res, mask)


def write_packages(out: Path, res, mask) -> list[Path]:
    """按负责人打包：只含这个负责人的真实差异和不确定，文字和截图都已打码，可以直接发出。"""
    owners = sorted({x["owner"] for x in res["items"] if x["status"] in ("real", "unsure")})
    made = []
    pk = out / "packages"
    for o in owners:
        pk.mkdir(exist_ok=True)
        mine = lambda x, o=o: x["owner"] == o and x["status"] in ("real", "unsure")
        page = report_html(res, mask, f"（{html.escape(o)}）", only=mine, appendix=False)
        z = pk / f"{_safe(o)}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{_safe(o)}.html", page)
            for it in res["items"]:
                if mine(it):
                    for s in it.get("shots") or []:
                        f = out / s["file"]
                        if f.exists():
                            zf.write(f, s["file"])
        made.append(z)
    return made


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s) or "未分配"


def batch_index(out_dir, rows) -> None:
    """一批对比的总览：每个 Case 一行。"""
    tr = []
    for r in rows:
        if r.get("error"):
            tr.append(f"<tr><td>{html.escape(r['case'])}</td><td colspan=5 class='n'>{html.escape(r['error'])}</td></tr>")
            continue
        s = r["stats"]
        state = "有差异" if s["real"] else ("需核对" if s["unsure"] or r.get("warn") else "无差异")
        tr.append(f"<tr><td><a href='{html.escape(r['dir'])}/ignore.html'>{html.escape(r['case'])}</a></td><td>{state}</td>"
                  f"<td>{s['real']}</td><td>{s['unsure']}</td><td>{s['ignored']} / {s['layout']}</td><td class='n'>{html.escape(r.get('warn') or '')}</td></tr>")
    page = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>文档对比总览</title><style>{CSS}</style></head><body><div class="wrap">'
            f"<h1>文档对比总览（{len(rows)} 个）</h1><table><tr><th>Case</th><th>结果</th><th>真实差异</th><th>不确定</th><th>已忽略 / 位置变化</th><th>提醒</th></tr>"
            + "".join(tr) + "</table></div></body></html>")
    Path(out_dir, "index.html").write_text(page, encoding="utf-8")
