"""文档对比：一条命令完成一对文件或一整批文件的对比。

用法（在 skill 目录下）：
  # 一整批：按 Case 编号把两个文件夹里的文件配对（配对规则见配置 case_key）
  python scripts/doc_compare.py batch --baseline-dir <baseline 文件夹> --new-dir <新文件文件夹> --out <结果文件夹> \
      [--config config/doc_compare.json] [--names <测试数据人名名单>] [--ocr <截图识别结果.ocr.json> ...]

  # 一对文件
  python scripts/doc_compare.py compare <baseline.pdf> <新文件.pdf> --out <结果文件夹> [同上的选项]

  # 扫描页：先转成图片，把文件夹拖到「识别截图.bat」上识别，再用 --ocr 带上识别结果对比
  python scripts/doc_compare.py ocr-prepare <pdf 文件或文件夹> --out <图片文件夹>

结果（每个 Case 一个文件夹）：
  ignore.html         精简结果：真实差异、不确定，附录列出所有被忽略和位置变化的内容（本机核对用，截图已打码）
  total.html          完整对比，与现在的格式相同，不做任何过滤
  result.json         同样的内容，数据文件
  result.masked.json  打码后的结果，交给 AI 写汇报只用这一份
  snapshots/          每条差异在两份 PDF 上的位置截图（已打码）
  packages/<负责人>.zip  发给负责人的包：只含他的差异，文字和截图都已打码
一批对比还会生成 index.html（总览）和 summary.json。

程序不调用任何 AI，报告里所有值都直接取自 PDF 原文。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc_core import CORE_DEFAULTS, assign_sections, compare, renumber  # noqa: E402
from filters import FILTER_DEFAULTS, Filter, read_names_file  # noqa: E402
from pdf_io import IO_DEFAULTS, load_ocr, read_doc, render_pages, snapshots, verify  # noqa: E402
from report import batch_index, write_all  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUN_DEFAULTS = {
    "case_key": r"^(Case\d+)",   # 从文件名取 Case 编号，两个文件夹里编号相同的文件配成一对
    "names_file": None,          # 测试数据人名名单（也可以用 --names 指定）
    "verify_numbers": True,      # 含数字的差异用第二种方式复读核对
    "snapshots": True,           # 生成差异截图
    "total_report": True,        # 生成 total.html（文件大，不需要时可以关掉）
}
COLOR_A, COLOR_B = (220, 40, 40), (30, 150, 60)


def load_config(path: str | None) -> dict:
    cfg = {**FILTER_DEFAULTS, **CORE_DEFAULTS, **IO_DEFAULTS, **RUN_DEFAULTS}
    p = Path(path) if path else ROOT / "config" / "doc_compare.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        unknown = [k for k in data if not k.startswith("_") and k not in cfg]
        if unknown:
            raise SystemExit(f"配置里有不认识的项：{'、'.join(unknown)}（拼写错了？）")
        cfg.update({k: v for k, v in data.items() if not k.startswith("_")})
    elif path:
        raise SystemExit(f"找不到配置文件：{path}")
    return cfg


def make_mask(flt: Filter, cfg: dict):
    """返回 (打码文字的函数, 判断一个词要不要打码的函数)。人名清单 → <人名>，证件号、电话、邮箱、卡号 → <已打码>。"""
    pats = [re.compile(p) for p in cfg["mask_patterns"]]

    def mask_text(s: str) -> str:
        if not isinstance(s, str) or not s:
            return s
        if flt.name_re:
            s = flt.name_re.sub("<人名>", s)
        for p in pats:
            s = p.sub("<已打码>", s)
        return s

    def mask_word(t: str) -> bool:
        return bool((flt.name_re and flt.name_re.search(t)) or any(p.search(t) for p in pats))

    return mask_text, mask_word


def side_info(doc: dict) -> dict:
    pages = doc["pages"]
    return {"name": doc["name"], "file": doc["file"], "pages": len(pages),
            "no_text_pages": [p["page"] for p in pages if not p["text"]],
            "ocr_pages": [p["page"] for p in pages if p["ocr"]],
            "big_image_pages": [p["page"] for p in pages if p.get("big_image")],
            "header_footer_lines": sum(1 for l in doc["lines"] if l.get("hf"))}


def make_snapshots(res, da, db, out: Path, cfg, mask_word) -> None:
    jobs = {"a": [], "b": []}
    for it in res["items"]:
        if it["status"] not in ("real", "unsure"):
            continue
        it["shots"] = []
        for side, refs, color in (("a", it["a"], COLOR_A), ("b", it["b"], COLOR_B)):
            by_page = defaultdict(list)
            for r in refs:
                if r.get("page") and r.get("bbox"):
                    by_page[r["page"]].append(r["bbox"])
            for page, boxes in sorted(by_page.items()):
                f = f"snapshots/{it['id']}_{'baseline' if side == 'a' else 'new'}_p{page:03d}.png"
                jobs[side].append({"page": page, "boxes": boxes, "color": color, "out": out / f})
                it["shots"].append({"side": side, "page": page, "file": f})
    snapshots(da, jobs["a"], cfg, mask_word)
    snapshots(db, jobs["b"], cfg, mask_word)
    for it in res["items"]:  # 读 txt 时没有截图
        if it.get("shots"):
            it["shots"] = [s for s in it["shots"] if (out / s["file"]).exists()]


def run_pair(base, new, out_dir, cfg, extra_names, ocr_index) -> dict:
    out = Path(out_dir)
    da, db = read_doc(base, cfg, ocr_index), read_doc(new, cfg, ocr_index)
    A = [l for l in da["lines"] if not l.get("hf")]
    B = [l for l in db["lines"] if not l.get("hf")]
    assign_sections(A, cfg)
    assign_sections(B, cfg)
    flt = Filter(cfg, [l["n"] for l in A], [l["n"] for l in B], extra_names)
    res = compare(A, B, cfg, flt)
    res.update(tool="doc-compare", v=1, created=dt.datetime.now().isoformat(timespec="seconds"),
               baseline=side_info(da), new=side_info(db))
    if cfg["verify_numbers"]:
        res["verify"] = verify(da, db, res["items"], cfg)
        renumber(res)
    mask_text, mask_word = make_mask(flt, cfg)
    if cfg["snapshots"]:
        make_snapshots(res, da, db, out, cfg, mask_word)
    write_all(out, res, da, db, mask_text, total=cfg["total_report"])
    return res


def warn_text(res) -> str:
    w = []
    for side, label in (("baseline", "baseline"), ("new", "新文件")):
        rest = [p for p in res[side]["no_text_pages"] if p not in res[side]["ocr_pages"]]
        if rest:
            w.append(f"{label} {len(rest)} 页没有比较（没有文字层）")
    if (res.get("verify") or {}).get("note"):
        w.append("复读未采用")
    return "；".join(w)


def cmd_compare(args, cfg, names, ocr):
    res = run_pair(args.baseline, args.new, args.out, cfg, names, ocr)
    s = res["stats"]
    print(f"真实差异 {s['real']}，不确定 {s['unsure']}，已忽略 {s['ignored']}，位置变化 {s['layout']}")
    if warn_text(res):
        print("注意：" + warn_text(res))
    print(f"结果：{Path(args.out) / 'ignore.html'}")


def cmd_batch(args, cfg, names, ocr):
    key_re = re.compile(cfg["case_key"])

    def collect(folder):
        out, dup = {}, []
        for p in sorted(Path(folder).iterdir()):
            if p.suffix.lower() not in (".pdf", ".txt"):
                continue
            m = key_re.search(p.name)
            k = m.group(1) if m else p.stem
            if k in out:
                dup.append(p.name)
                k = p.stem
            out[k] = p
        return out, dup

    bases, dup_a = collect(args.baseline_dir)
    news, dup_b = collect(args.new_dir)
    out = Path(args.out) / dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for k in sorted(set(bases) | set(news), key=lambda x: (len(x), x)):
        if k not in bases or k not in news:
            rows.append({"case": k, "error": "只有新文件，没有对应的 baseline" if k in news else "只有 baseline，没有对应的新文件"})
            continue
        print(f"[{len(rows) + 1}] {k}：{bases[k].name} ↔ {news[k].name}")
        try:
            res = run_pair(bases[k], news[k], out / k, cfg, names, ocr)
            rows.append({"case": k, "dir": k, "baseline": bases[k].name, "new": news[k].name,
                         "stats": res["stats"], "warn": warn_text(res)})
        except Exception as e:  # 一个文件出错不影响其他文件
            rows.append({"case": k, "error": f"对比失败：{e}"})
    batch_index(out, rows)
    (out / "summary.json").write_text(json.dumps({"tool": "doc-compare-batch", "v": 1, "cases": rows,
                                                  "duplicate_names": dup_a + dup_b}, ensure_ascii=False, indent=1), encoding="utf-8")
    real = sum(1 for r in rows if r.get("stats", {}).get("real"))
    print(f"完成：{len(rows)} 个，其中有真实差异 {real} 个，出错或没配上 {sum(1 for r in rows if r.get('error'))} 个")
    if dup_a or dup_b:
        print("注意：这些文件的 Case 编号重复，已按完整文件名单独处理：" + "、".join(dup_a + dup_b))
    print(f"总览：{out / 'index.html'}")


def cmd_ocr_prepare(args, cfg):
    pdfs = []
    for p in args.pdf:
        p = Path(p)
        pdfs += sorted(p.glob("*.pdf")) if p.is_dir() else [p]
    total = 0
    for p in pdfs:
        doc = read_doc(p, cfg)
        pages = [x["page"] for x in doc["pages"] if not x["text"]]
        if pages:
            render_pages(p, pages, args.out, cfg["render_dpi"])
            total += len(pages)
            print(f"{p.name}：第 {', '.join(map(str, pages))} 页没有文字层，已转成图片")
    if not total:
        print("没有需要识别的页。")
        return
    print(f"\n共 {total} 页。下一步：把文件夹 {args.out} 拖到「识别截图.bat」上，"
          f"识别完成后文件夹里会有「截图识别结果.ocr.json」，对比时加 --ocr <这个文件>。")


def main():
    ap = argparse.ArgumentParser(description="文档对比（baseline ↔ 新文件）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("compare", "batch"):
        s = sub.add_parser(name)
        if name == "compare":
            s.add_argument("baseline")
            s.add_argument("new")
        else:
            s.add_argument("--baseline-dir", required=True)
            s.add_argument("--new-dir", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--config")
        s.add_argument("--names", help="测试数据人名名单（txt 或 csv）")
        s.add_argument("--ocr", nargs="*", help="「识别截图.bat」生成的 截图识别结果.ocr.json")
    s = sub.add_parser("ocr-prepare")
    s.add_argument("pdf", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--config")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.cmd == "ocr-prepare":
        return cmd_ocr_prepare(args, cfg)
    names = read_names_file(args.names or cfg["names_file"])
    ocr = load_ocr(args.ocr) if args.ocr else None
    (cmd_compare if args.cmd == "compare" else cmd_batch)(args, cfg, names, ocr)


if __name__ == "__main__":
    main()
