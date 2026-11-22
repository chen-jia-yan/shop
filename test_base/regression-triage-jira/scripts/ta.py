"""测试分析助手（命令行入口）。页面和命令行用的是同一套分析，结果相同。

    python scripts/ta.py open                      打开页面（本机服务，只监听 127.0.0.1；已开着时直接打开页面）；--bg 后台启动后立即返回
    python scripts/ta.py shortcut                  在桌面创建快捷方式（双击打开，不出现命令行窗口）
    python scripts/ta.py analyze 报告.mhtml [...]   导入执行结果、识别截图文字、分析，打印结果
          --name 批次名 --plan 测试计划 --device 设备 --env 环境；--rerun-of <批次编号> 导入重跑结果
    python scripts/ta.py list                      已导入的批次
    python scripts/ta.py show [批次编号] [--json]   失败用例的分析结果（--json 给 AI 或其他程序读取）
    python scripts/ta.py shots [批次编号] [--all]   要看截图的用例、当前判断、截图完整路径（JSON，给 AI 看图用）
    python scripts/ta.py record ai.json            AI 写入看图结果（obs）和判断（ai），写完重新分析，打印前后变化
    python scripts/ta.py export [批次编号] --out 失败分诊.csv
    python scripts/ta.py ocr [--import 结果.ocr.json]   识别还没识别的截图 / 导入手动识别的结果
    python scripts/ta.py check                     改规则或代码后运行：规则写法、纠错样本、基准样本
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is None or sys.stderr is None:
    # 用 pythonw 启动（没有窗口）时，输出写到 workspace/server.log
    _ws = Path(__file__).resolve().parent.parent / "workspace"
    _ws.mkdir(exist_ok=True)
    _log = open(_ws / "server.log", "a", encoding="utf-8", buffering=1)
    sys.stdout, sys.stderr = sys.stdout or _log, sys.stderr or _log
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 命令行显示中文

import ta_engine as E  # noqa: E402
import ta_store as T  # noqa: E402


def _run(st, rid):
    if not st.runs:
        raise T.UserError("还没有导入任何批次")
    r = st.run_of(rid) if rid else st.runs[-1]
    if not r:
        raise T.UserError("没有批次 " + str(rid) + "，用 list 查看")
    return r


IDLE_MIN = 30  # 页面关掉这么多分钟后自动退出（正在识别截图时不退出）


def _running(port):
    """已经开着的助手的端口（再次双击时直接打开页面，不重复启动）。"""
    for p in range(port, port + 20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:" + str(p) + "/api/ping", timeout=0.5) as r:
                if json.loads(r.read()).get("tool") == "ta-server":
                    return p
        except (OSError, ValueError):
            continue
    return None


def cmd_open(a):
    import ta_server
    p = _running(a.port)
    if p:
        url = "http://127.0.0.1:" + str(p) + "/"
        print("测试分析助手已经在运行：" + url)
        if not a.no_browser:
            webbrowser.open(url)
        return
    if a.bg:
        # 给 AI 用：在后台启动服务后立即返回，不占住终端
        exe = Path(sys.executable)
        if os.name == "nt" and exe.with_name("pythonw.exe").exists():
            exe = exe.with_name("pythonw.exe")
        args = [str(exe), str(Path(__file__).resolve()), "open", "--port", str(a.port)] + (["--no-browser"] if a.no_browser else [])
        kw = {"creationflags": 0x00000008 | 0x00000200 | 0x08000000} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen(args, cwd=str(E.ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)
        for _ in range(40):
            time.sleep(0.25)
            p = _running(a.port)
            if p:
                print("测试分析助手已在后台启动：http://127.0.0.1:" + str(p) + "/（页面关闭 " + str(IDLE_MIN) + " 分钟后自动退出）")
                return
        raise T.UserError("后台启动没有成功，请双击“测试分析助手”打开；日志在 workspace/server.log")
    st = T.Store()
    srv, port = ta_server.serve(st, a.port)
    url = "http://127.0.0.1:" + str(port) + "/"
    print(time.strftime("%Y-%m-%d %H:%M:%S") + " 测试分析助手已启动：" + url)
    st.last_seen = time.time()

    def watchdog():
        while True:
            time.sleep(30)
            if a.keep or st.ocr_state.get("running"):
                continue
            if time.time() - st.last_seen > IDLE_MIN * 60:
                print(time.strftime("%Y-%m-%d %H:%M:%S") + " 页面已关闭 " + str(IDLE_MIN) + " 分钟，自动退出")
                srv.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    st.ocr_async()  # 上次没识别完的截图
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_shortcut(a):
    """在桌面创建“测试分析助手”快捷方式：用 pythonw 启动，不出现命令行窗口。"""
    if os.name != "nt":
        raise T.UserError("只有 Windows 能创建快捷方式")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        raise T.UserError("找不到 pythonw.exe（" + str(pyw) + "）")
    ps = ("$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '测试分析助手.lnk')); "
          "$s.TargetPath=$env:TA_PYW; $s.Arguments='\"'+$env:TA_SCRIPT+'\" open'; $s.WorkingDirectory=$env:TA_ROOT; $s.Description='测试分析助手'; $s.Save()")
    env = dict(os.environ, TA_PYW=str(pyw), TA_SCRIPT=str(Path(__file__).resolve()), TA_ROOT=str(E.ROOT))
    r = subprocess.run(["powershell.exe", "-NoProfile", "-EncodedCommand", base64.b64encode(ps.encode("utf-16-le")).decode()], env=env, capture_output=True)
    if r.returncode:
        raise T.UserError("创建失败：" + (r.stderr or b"").decode("gbk", "replace")[-300:])
    print("已在桌面创建“测试分析助手”，以后双击它即可（不会出现命令行窗口）")


def cmd_analyze(a):
    st = T.Store(auto_ocr=False)
    info = {"name": a.name or "", "plan": a.plan or "", "device": a.device or "", "env": a.env or ""}
    if a.rerun_of:
        info.update(mode="rerun", rerunOf=a.rerun_of)
    res = st.import_paths([Path(p) for p in a.files], info)
    print(res["msg"])
    print(st.ocr_sync())
    if not a.rerun_of:
        a.run, a.json = res["run"], False
        cmd_show(a, st)


def cmd_list(a):
    st = T.Store(auto_ocr=False)
    cs = st.analyzed()
    for r in st.runs:
        f = [c for c in cs if c["run"] == r["id"] and c.get("failed") and not c.get("parent")]
        print(r["id"], r["at"], r["name"], "总数", r["total"], "失败", len(f))
    if not st.runs:
        print("还没有导入任何批次")


def cmd_show(a, st=None):
    st = st or T.Store(auto_ocr=False)
    r = _run(st, a.run)
    cs = [c for c in st.analyzed() if c["run"] == r["id"] and c.get("failed")]
    if a.json:
        print(json.dumps({"run": {k: v for k, v in r.items() if k != "cases"},
                          "cases": [dict({"uid": c["uid"], "case_id": c["id"], "name": c.get("name"), "attempt": 2 if c.get("parent") else 1}, **E.result_of(c)) for c in cs]},
                         ensure_ascii=False, indent=1))
        return
    by = {}
    for c in cs:
        by.setdefault(c["final"], []).append(c)
    print("批次", r["id"], r["name"], "失败", len([c for c in cs if not c.get("parent")]))
    for k in E.CATS:
        if k not in by:
            continue
        print("\n【" + E.CATS[k]["name"] + "】" + str(len(by[k])) + " 条 · 处理方：" + E.CATS[k]["owner"])
        for c in by[k]:
            a_ = c["auto"]
            st_ = "人工已改" if c.get("override") else "规则确认" if a_["status"] == "confirmed" else "待复核"
            print("  " + str(c["id"]) + ("（第2次）" if c.get("parent") else "") + " [" + st_ + " · " + E.rule_name(c) + " · " + E.PLAN[c["plan"]["b"]] + "] " + a_["brief"])


def cmd_export(a):
    st = T.Store(auto_ocr=False)
    r = _run(st, a.run)
    out = Path(a.out or "失败分诊_" + re.sub(r"[^\w\-]+", "_", r["name"]) + ".csv")
    out.write_text(st.cases_csv(r["id"]), encoding="utf-8")
    print("已导出", out)


def _need_look(c):
    """规则没能确认、需要看截图或 AI 补充判断的用例。"""
    a = c["auto"]
    return not c.get("override") and (a["status"] != "confirmed" or a["cat"] == "NEEDS_HUMAN")


def cmd_shots(a):
    """给 AI 看图用：列出要看的用例、当前判断、截图的完整路径（JSON）。"""
    st = T.Store(auto_ocr=False)
    r = _run(st, a.run)
    out = []
    for c in st.analyzed():
        if c["run"] != r["id"] or not c.get("failed") or not (a.all or _need_look(c)):
            continue
        files = [str((st.ws / "runs" / r["id"] / "shots" / s["file"]).resolve()) for s in c["shots"] + c["shots2"]]
        out.append({"uid": c["uid"], "case_id": c["id"], "name": c.get("name"), "category": c["final"], "status": c["auto"]["status"],
                    "rule": E.rule_name(c), "brief": c["auto"]["brief"], "error": (c.get("error") or c.get("stack") or "")[:600],
                    "screenshots": files, "screenshot_in_report": c.get("screenshot") if not files else None,
                    "obs": c.get("obs"), "ai": c.get("ai"), "ocr_text": (c.get("ocrText") or "")[:600] or None})
    print(json.dumps({"run": r["id"], "n": len(out), "obs_kinds": E.OBS_KINDS, "categories": {k: v["name"] for k, v in E.CATS.items()}, "cases": out},
                     ensure_ascii=False, indent=1))


def _post(port, path, body):
    req = urllib.request.Request("http://127.0.0.1:" + str(port) + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-TA": "1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise T.UserError(json.loads(e.read() or b"{}").get("error") or str(e))


def cmd_record(a):
    """AI 看图、分析后写入：[{"uid", "obs": {"kind", "text"}, "ai": {"cat", "reason"}}]，写完重新分析并打印前后变化。
    页面开着时通过页面的服务写入（否则页面保存时会把命令行写的内容覆盖掉）。"""
    items = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
    items = items.get("items") if isinstance(items, dict) else items
    port = _running(8765)
    st = None if port else T.Store(auto_ocr=False)
    finals = lambda: {c["uid"]: c for c in (json.loads(urllib.request.urlopen("http://127.0.0.1:" + str(port) + "/api/state", timeout=30).read())["cases"] if port else st.cases_view())}
    before, at = finals(), time.strftime("%Y-%m-%d %H:%M")
    done = []
    for it in items:
        u = it.get("uid")
        if u not in before or not before[u].get("failed"):
            print("✗ 没有失败用例 " + str(u) + "（用 ta.py shots 查看 uid）")
            continue
        v = {}
        if "obs" in it:
            v["obs"] = dict(it["obs"], by="AI", at=at) if it["obs"] else None
        if "ai" in it:
            v["ai"] = dict(it["ai"], at=at) if it["ai"] else None
        if not v:
            continue
        try:
            _post(port, "/api/case", {"uids": [u], "set": v}) if port else st.set_case([u], v)
            done.append(u)
        except T.UserError as e:
            print("✗ " + str(before[u]["id"]) + "：" + str(e))
    after = finals()
    name = lambda c: E.CATS[c["final"]]["name"] + "（" + c["ruleName"] + "）"
    for u in done:
        b, n = before[u], after[u]
        print(("  " if b["final"] == n["final"] else "→ ") + str(n["id"]) + "：" + (name(b) + " → " if b["final"] != n["final"] or b["ruleName"] != n["ruleName"] else "不变 ") + name(n))
    print("已写入 " + str(len(done)) + " 条" + ("（页面已同步，刷新即可看到）" if port else ""))


def cmd_ocr(a):
    st = T.Store(auto_ocr=False)
    if a.import_file:
        n = st.import_ocr_doc(json.loads(Path(a.import_file).read_text(encoding="utf-8-sig")))
        print("已导入识别结果，新增 " + str(n) + " 张")
        return
    print(st.ocr_sync())


def cmd_check(a) -> int:
    """规则写法 → 自定义规则 → 纠错样本 → 基准样本。全部通过返回 0。"""
    bad = 0
    try:
        doc = E.load_rule_doc()
    except (ValueError, OSError) as e:
        print("✗ 规则文件读不出来：" + str(e))
        return 1
    base = E.default_rules()
    unknown = [k for k in doc["rules"] if k not in base]
    errs = []
    for k, v in doc["rules"].items():
        if k in base and isinstance(base[k], list):
            if not isinstance(v, list):
                errs.append(k + " 应该是清单")
                continue
            for x in v:
                if isinstance(x, str) and x.startswith("re:"):
                    try:
                        re.compile(x[3:])
                    except re.error as e:
                        errs.append(k + "：模糊匹配写法有误“" + x + "”（" + str(e) + "）")
    errs += ["不认识的规则项 " + k for k in unknown] + E.validate_custom(doc["custom"])
    if errs:
        bad = 1
        print("✗ 规则写法有问题：")
        for e in errs:
            print("   -", e)
    else:
        print("✓ 规则写法正确（" + str(len(doc["rules"])) + " 项规则，" + str(len(doc["custom"])) + " 条自定义规则，最近修改："
              + ((doc["changelog"][-1]["at"] + " " + doc["changelog"][-1].get("by", "")) if doc["changelog"] else "无记录") + "）")
    corr = T.read_json(T.CORR_FILE, {"items": []}).get("items") or []
    res = E.test_corrections(corr, doc["rules"], doc["custom"])
    fail = [r for r in res if not r["ok"]]
    if fail:
        bad = 1
        print("✗ 纠错样本：" + str(len(res)) + " 条中 " + str(len(fail)) + " 条没有判对")
        for r in fail:
            print("   - " + r["id"] + "：应为 " + E.CATS.get(r["expect"].get("category"), {}).get("name", "?") + (" / " + r["expect"]["rule"] if r["expect"].get("rule") else "")
                  + "，现在判为 " + E.CATS[r["got"]["category"]]["name"] + " / " + r["got"]["rule"] + "（" + r["got"]["brief"] + "）")
    else:
        print("✓ 纠错样本：" + str(len(res)) + " 条全部判对")
    sys.path.insert(0, str(E.ROOT / "evals"))
    import check_consistency
    n, errs = check_consistency.run()
    if errs:
        bad = 1
        print("✗ 基准样本：" + str(len(errs)) + " 处和标准答案不同（判断逻辑被改动了）：")
        for e in errs[:20]:
            print("   -", e)
        print("   确认是有意的改进后运行 python evals/check_consistency.py --update")
    else:
        print("✓ 基准样本：" + str(n) + " 项与标准答案相同")
    print("全部通过" if not bad else "有问题，请先处理再使用")
    return bad


def main():
    ap = argparse.ArgumentParser(description="测试分析助手")
    sp = ap.add_subparsers(dest="cmd")
    p = sp.add_parser("open")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--keep", action="store_true", help="页面关闭后也不自动退出")
    p.add_argument("--bg", action="store_true", help="在后台启动后立即返回（给 AI 用）")
    sp.add_parser("shortcut")
    p = sp.add_parser("analyze")
    p.add_argument("files", nargs="+")
    for k in ("name", "plan", "device", "env", "rerun-of"):
        p.add_argument("--" + k)
    sp.add_parser("list")
    p = sp.add_parser("show")
    p.add_argument("run", nargs="?")
    p.add_argument("--json", action="store_true")
    p = sp.add_parser("export")
    p.add_argument("run", nargs="?")
    p.add_argument("--out")
    p = sp.add_parser("shots")
    p.add_argument("run", nargs="?")
    p.add_argument("--all", action="store_true", help="包括规则已确认的用例")
    p = sp.add_parser("record")
    p.add_argument("file")
    p = sp.add_parser("ocr")
    p.add_argument("--import", dest="import_file")
    sp.add_parser("check")
    a = ap.parse_args()
    fn = {"open": cmd_open, "shortcut": cmd_shortcut, "analyze": cmd_analyze, "list": cmd_list, "show": cmd_show, "export": cmd_export,
          "shots": cmd_shots, "record": cmd_record, "ocr": cmd_ocr, "check": cmd_check}.get(a.cmd or "open")
    if not a.cmd:
        a.port, a.no_browser, a.keep, a.bg = 8765, False, False, False
    try:
        return fn(a) or 0
    except T.UserError as e:
        print("✗ " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
