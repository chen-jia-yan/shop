"""文档对比助手：选文件 → 调用同事A 的脚本对比 → 整理成索引页 → 出 Word / Excel 交付物。

  python scripts/dca.py all --baseline-dir <baseline 文件夹> --new-dir <新文件文件夹>      一步做完
  python scripts/dca.py pairs --baseline-dir ... --new-dir ...                           只配对，生成 pairs.csv 让你勾选
  python scripts/dca.py run --batch runs/<批次>                                           按 pairs.csv 调用他的脚本
  python scripts/dca.py collect --batch runs/<批次> --results-dir <他已经跑好的结果>       不重跑，只整理现有结果
  python scripts/dca.py report --batch runs/<批次>                                        截图、索引页、Word、Excel
  python scripts/dca.py inspect <他的 difference 或 total 文件>                            看看能不能读懂他的格式
  python scripts/dca.py check                                                            检查环境和配置

所有命令都可以加 --config <配置文件>，默认读 config/dca.json（没有就用默认值）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, load_batch, load_config, now_tag, save_batch, write_json  # noqa: E402
import pairing  # noqa: E402


def cmd_pairs(a, cfg) -> Path:
    out = Path(a.out or ROOT / "runs") / now_tag()
    out.mkdir(parents=True, exist_ok=True)
    pairs = pairing.make_pairs(a.baseline_dir, a.new_dir, cfg)
    batch = {"baseline_dir": str(Path(a.baseline_dir).resolve()), "new_dir": str(Path(a.new_dir).resolve()), "pairs": pairs}
    save_batch(out, batch)
    pairing.write_csv(out / "pairs.csv", pairs)
    ok = sum(1 for p in pairs if p["selected"])
    print(f"配对完成：{len(pairs)} 个编号，其中 {ok} 对可以对比")
    for p in pairs:
        mark = "✓" if p["selected"] else "✗"
        print(f"  {mark} {p['key']:<10} {Path(p['baseline']).name if p['baseline'] else '—'}  ⇄  {Path(p['new']).name if p['new'] else '—'}  {p['note']}")
    print(f"批次文件夹：{out}")
    print(f"需要只对比其中几对时，用 Excel 打开 {out / 'pairs.csv'}，把“选中”列改成 Y / N 后保存，再运行 run。")
    return out


def _with_csv(batch_dir: Path, batch: dict) -> None:
    csv_path = batch_dir / "pairs.csv"
    if csv_path.is_file():
        batch["pairs"] = pairing.apply_csv(csv_path, batch["pairs"])


def cmd_run(a, cfg) -> None:
    import runner
    bd = Path(a.batch)
    batch = load_batch(bd)
    _with_csv(bd, batch)
    if not any(p["selected"] for p in batch["pairs"]):
        raise SystemExit("没有选中的文件对，请检查 pairs.csv")
    runner.run_pairs(bd, batch, cfg)
    save_batch(bd, batch)
    bad = [p for p in batch["pairs"] if p["selected"] and p.get("error")]
    print(f"对比完成：{sum(1 for p in batch['pairs'] if p['status'] == '已对比')} 对成功，{len(bad)} 对出错")


def cmd_collect(a, cfg) -> None:
    import runner
    bd = Path(a.batch)
    batch = load_batch(bd)
    _with_csv(bd, batch)
    runner.collect(batch, a.results_dir, cfg)
    save_batch(bd, batch)


def cmd_report(a, cfg) -> None:
    import diff_parse
    import deliver
    import index_page
    bd = Path(a.batch)
    batch = load_batch(bd)
    total = miss = 0
    for p in batch["pairs"]:
        if p.get("status") != "已对比":
            continue
        src = next((p["files"][k] for k in cfg["difference"]["source"] if p["files"].get(k)), None)
        if not src:
            p["items"], p["error"] = [], p.get("error") or "没有 difference / total 文件"
            continue
        try:
            items, fmt = diff_parse.parse(src, cfg)
        except Exception as e:
            p["items"], p["error"] = [], f"读差异出错：{type(e).__name__}: {e}（用 inspect 看看文件格式）"
            continue
        for it in items:
            it["skip"] = bool(cfg["difference"]["skip_space_only"] and it["space_only"])
        keep = [it for it in items if not it["skip"]]
        if cfg["screenshot"]["enabled"] and keep:
            import shots
            try:
                shots.shoot_case(p, keep, bd / "cases" / p["dir"], cfg)
            except Exception as e:
                for it in keep:
                    it.setdefault("shot_note", []).append(f"截图出错：{type(e).__name__}: {e}")
        p["items"], p["format"] = items, fmt
        total += len(keep)
        miss += sum(1 for it in keep if (it["old"] and not it.get("shot_old")) or (it["new"] and not it.get("shot_new")))
        print(f"  {p['key']:<10} {len(keep)} 处变化（{fmt}）")
    outputs = {}
    title = cfg["deliver"]["title"]
    if cfg["deliver"]["word"]:
        outputs["Word"] = bd / f"{title}.docx"
        deliver.write_word(outputs["Word"], batch, cfg)
    if cfg["deliver"]["excel"]:
        outputs["Excel"] = bd / f"{title}.xlsx"
        deliver.write_excel(outputs["Excel"], batch, cfg)
    page = index_page.write_index(bd, batch, cfg, outputs)
    save_batch(bd, batch)
    write_json(bd / "report.json", {"cases": len([p for p in batch["pairs"] if p.get("items") is not None]),
                                    "changes": total, "missing_shots": miss,
                                    "errors": [{"case": p["key"], "error": p["error"]} for p in batch["pairs"] if p.get("error")]})
    print(f"共 {total} 处变化，截图待补 {miss} 处")
    for k, v in outputs.items():
        print(f"{k}：{v}")
    print(f"索引页：{page}")


def cmd_all(a, cfg) -> None:
    bd = cmd_pairs(a, cfg)
    a.batch = str(bd)
    if a.results_dir:
        cmd_collect(a, cfg)
    else:
        cmd_run(a, cfg)
    cmd_report(a, cfg)


def cmd_inspect(a, cfg) -> None:
    import diff_parse
    rep = diff_parse.inspect_file(a.file, cfg)
    print(rep)
    out = Path(a.file).with_suffix(".inspect.txt")
    try:
        out.write_text(rep, encoding="utf-8")
        print(f"\n（以上内容也存到了 {out}）")
    except OSError:
        pass


def cmd_check(a, cfg) -> None:
    ok = True
    for mod, why in (("pdfplumber", "读 PDF 文字和位置"), ("pypdfium2", "PDF 转图片"), ("PIL", "画框裁剪"),
                     ("docx", "生成 Word（python-docx）"), ("openpyxl", "生成 Excel")):
        try:
            __import__(mod)
            print(f"  ✓ {mod}")
        except ImportError:
            ok = False
            print(f"  ✗ 缺少 {mod}（{why}），请运行 pip install -r requirements.txt")
    cpath = Path(a.config) if a.config else ROOT / "config" / "dca.json"
    print(f"  {'✓' if cpath.exists() else '!'} 配置：{cpath if cpath.exists() else '没有 config/dca.json，正在用默认值'}")
    sc = cfg["a_script"]
    if sc["mode"] == "method":
        if not sc["path"]:
            ok = False
            print("  ✗ a_script.path 没填：填他的对比脚本 .py 的路径（只用 collect 整理现有结果时可以不填）")
        else:
            import runner
            try:
                _, desc = runner.load_target(cfg)
                print(f"  ✓ 找到对比函数：{desc}")
            except SystemExit as e:
                ok = False
                print(f"  ✗ {e}")
            except Exception as e:
                ok = False
                print(f"  ✗ 导入他的脚本出错：{type(e).__name__}: {e}")
    else:
        print(f"  {'✓' if sc['command'] else '✗'} 命令：{sc['command'] or '没填 a_script.command'}")
    print("环境检查通过" if ok else "环境检查未通过，按上面的提示处理")


def main(argv=None):
    for s in (sys.stdout, sys.stderr):      # 中文 Windows 控制台是 GBK，✓ ✗ 这类字符打不出来时不报错
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="文档对比助手")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pairs", "all"):
        s = sub.add_parser(name)
        s.add_argument("--baseline-dir", required=True)
        s.add_argument("--new-dir", required=True)
        s.add_argument("--out")
        if name == "all":
            s.add_argument("--results-dir", help="他已经跑好结果时填这个，只整理不重跑")
    sub.add_parser("run").add_argument("--batch", required=True)
    s = sub.add_parser("collect")
    s.add_argument("--batch", required=True)
    s.add_argument("--results-dir", required=True)
    sub.add_parser("report").add_argument("--batch", required=True)
    sub.add_parser("inspect").add_argument("file")
    sub.add_parser("check")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    {"pairs": cmd_pairs, "run": cmd_run, "collect": cmd_collect, "report": cmd_report,
     "all": cmd_all, "inspect": cmd_inspect, "check": cmd_check}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
