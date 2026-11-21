"""自检：导入、工作区、纠错样本、自定义规则、Jira 起草、本机服务。不需要 Windows，也不会碰真实的 workspace/ 和 config/。

用法（在 skill 目录下）：python evals/selftest.py
全部通过输出“自检通过”，返回 0；否则列出失败项，返回 1。ta.py check 只查规则；改了 scripts/ 里的代码后跑这个。
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ta_engine as E  # noqa: E402
import ta_import as I  # noqa: E402
import ta_jira as J  # noqa: E402
import ta_store as T  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==") + b"\0" * 300
URI = "data:image/png;base64," + base64.b64encode(PNG).decode()
LOCK = ("frmPTDAdv (COM 2 Bermuda) window wait success 09/08/2047 Validation Error: Contract is currently used by other user\n"
        "Traceback (most recent call last): File \"common\\BeautifulReport\\BeautifulReport.py\", line 554, in _wrap File \"test_case\\las_test_case_all.py\", line 909, in test_27_TC_LAS_PaidToDateAdvance_01 "
        "File \"system_view\\LAS_view\\las_functions_page.py\", line 1502, in las_paid_to_date_advance Exception: job cannot submit successfully")
DESK = "RuntimeError: There is no active desktop required for moving mouse cursor"
HTML = f"""<html><body><table>
<tr><th>CaseId</th><th>Name</th><th>Result</th><th>Log</th></tr>
<tr><td>TC01</td><td>test_01_TC_LAS_Surrender_01</td><td>Failed</td><td>{LOCK.replace(chr(10), '<br>')}<img src="{URI}"></td></tr>
<tr><td colspan="4">detail line for TC01</td></tr>
<tr><th>CaseId</th><th>Name</th><th>Result</th><th>Log</th></tr>
<tr><td>TC02</td><td>test_02</td><td>Passed</td><td>ok</td></tr>
<tr><td>TC03</td><td>test_03</td><td>Failed</td><td>{DESK}</td></tr>
<tr><td>TC04</td><td>test_04</td><td>Failed</td><td>Exception: Policy is being edited by batch job</td></tr>
</table></body></html>"""

fails = []


def check(name, cond, info=""):
    if not cond:
        fails.append(name + (("：" + str(info)) if info else ""))


def t_import():
    p = I.parse_file("r.html", HTML.encode("utf-8"))
    t = p["tables"][0]["rows"]
    check("网页表格行数（跳过重复表头、合并详细日志行）", len(t) == 4, len(t))
    check("内嵌截图", len(p["images"]) == 1 and t[0].get("截图") == "img#1", t[0].get("截图"))
    check("详细日志行并入上一行", "detail line" in t[0].get("详细日志", ""))
    check("单元格保留换行", "\n" in t[0]["Log"])
    m = I.guess_mapping(I.columns_of(t))
    check("字段对应", m.get("id") == "CaseId" and m.get("result") == "Result" and m.get("name") == "Name", m)
    mh = ("MIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=\"B\"\r\n\r\n--B\r\nContent-Type: text/html\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
          "<table><tr><th>id</th><th>result</th></tr><tr><td>A1</td><td>failed<img src=3D\"http://x/a.png\"></td></tr></table>\r\n"
          "--B\r\nContent-Type: image/png\r\nContent-Transfer-Encoding: base64\r\nContent-Location: http://x/a.png\r\n\r\n" + base64.b64encode(PNG).decode() + "\r\n--B--\r\n")
    p = I.parse_file("r.mhtml", mh.encode())
    check("MHTML 截图", len(p["images"]) == 1 and p["tables"][0]["rows"][0].get("截图") == "img#1", p["tables"][0]["rows"])
    x = I.parse_file("j.xml", b'<testsuite name="s"><testcase name="a" classname="c"><failure message="boom" type="AssertionError">trace</failure></testcase><testcase name="b"/></testsuite>')
    check("JUnit", [r["status"] for r in x["tables"][0]["rows"]] == ["failed", "passed"])
    c = I.parse_file("a.csv", "id,result,msg\n1,failed,\"a,b\"\n2,passed,\n".encode("gbk"))
    check("CSV（GBK、引号）", c["tables"][0]["rows"][0]["msg"] == "a,b")
    a = I.parse_file("x.json", json.dumps({"uuid": "u", "name": "n", "status": "failed", "statusDetails": {"message": "m"}, "start": 1700000000000, "stop": 1700000001000}).encode())
    check("Allure", a["tables"][0]["rows"][0]["duration(ms)"] == "1000")


def t_store(tmp: Path):
    cfg = tmp / "config"
    cfg.mkdir()
    shutil.copy(ROOT / "config" / "rules.json", cfg / "rules.json")
    st = T.Store(ws=tmp / "ws", rules_file=cfg / "rules.json", corr_file=cfg / "corrections.json", jira_file=cfg / "jira.json", auto_ocr=False)
    MAP = {"id": "CaseId", "name": "Name", "result": "Result", "error": "Log", "stack": "详细日志"}
    p = st.parse([("report.html", HTML.encode("utf-8"))])
    check("解析返回字段对应", p["map"].get("id") == "CaseId")
    pv = st.preview(p["token"], 0, MAP)
    check("预览失败数", pv["nFail"] == 3, pv["nFail"])
    r = st.do_import(p["token"], 0, MAP, {"name": "批次1", "env": "U401"})
    rid = r["run"]
    cs = {c["id"]: c for c in st.analyzed()}
    check("锁单判为测试数据", cs["TC01"]["final"] == "TEST_DATA", cs["TC01"]["final"])
    check("截图存成文件", len(cs["TC01"]["shots"]) == 1 and (tmp / "ws" / "runs" / rid / "shots" / st.stored(cs["TC01"]["uid"])["shots"][0]["file"]).exists())
    check("桌面不可用判为环境", cs["TC03"]["final"] == "ENVIRONMENT")
    u4 = cs["TC04"]["uid"]
    # 人工记录
    st.set_case([u4], {"obs": {"kind": "popup", "text": "Policy is being edited by batch job"}})
    check("截图观察后重新分析", st.case(u4)["auto"]["rule"].startswith("OBS"), st.case(u4)["auto"]["rule"])
    try:
        st.set_case([u4], {"override": {"cat": "TEST_DATA", "reason": ""}})
        check("改判必须写原因", False)
    except T.UserError:
        pass
    # 纠错样本：现在判错 → 加自定义规则 → 判对
    res = st.add_correction(u4, "TEST_DATA", False, "批处理锁单", "自检")
    check("纠错样本先判错", not res["test"]["ok"], res["test"])
    bad = E.validate_custom([{"id": "X1", "when": {"any": ["ab"]}, "then": {"category": "NOPE"}}])
    check("自定义规则写法检查", len(bad) >= 3, bad)
    rule = {"id": "U1", "enabled": True, "name": "批处理锁单", "when": {"in": ["log", "popup"], "any": ["being edited by batch"]}, "then": {"category": "TEST_DATA", "status": "confirmed", "rerun": "fix"}, "note": "自检"}
    check("试一下命中", st.custom_test(rule)["n"] == 1)
    out = st.save_custom([rule], "自检", "加规则")
    check("加规则后样本判对", all(x["ok"] for x in out["corrections"]), out["corrections"])
    check("自定义规则生效", st.case(u4)["auto"]["rule"] == "U1" and st.case(u4)["plan"]["b"] == "fix")
    check("修改记录", st.doc["changelog"][-1]["what"].startswith("自定义规则"))
    out = st.save_rules({"lock_messages": st.rules["lock_messages"] + ["is held by"]}, "自检", "")
    check("改判断规则写修改记录", "lock_messages" in st.doc["changelog"][-1]["what"])
    try:
        st.save_rules({"env_patterns": ["re:(unclosed"]}, "自检", "")
        check("错误的模糊匹配要拒绝", False)
    except T.UserError:
        pass
    # 重跑结果：TC01 通过，TC03 报错不同
    rr = "<table><tr><th>CaseId</th><th>Result</th><th>Log</th></tr><tr><td>TC01</td><td>Passed</td><td></td></tr><tr><td>TC03</td><td>Failed</td><td>AssertionError: expected 1 but was 2</td></tr></table>"
    p2 = st.parse([("rerun.html", rr.encode())])
    st.do_import(p2["token"], 0, p2["map"], {"mode": "rerun", "rerunOf": rid})
    cs = {c["uid"]: c for c in st.analyzed()}
    u1, u3 = next(u for u, c in cs.items() if c["id"] == "TC01"), next(u for u, c in cs.items() if c["id"] == "TC03" and not c.get("parent"))
    check("重跑通过", cs[u1]["rerun"] == "pass" and cs[u1]["plan"]["b"] == "done")
    check("重跑报错不同生成第2次记录", (u3 + "#2") in cs and cs[u3 + "#2"]["parent"] == u3)
    # Jira
    ids = st.jira_new([u4, u1])
    check("重跑通过的不起草", len(ids) == 1, ids)
    d = st.draft(ids[0])
    check("草稿标题", "TC04" in d["f"]["summary"] and "{" not in d["f"]["summary"], d["f"]["summary"])
    st.jira_update(d["id"], "fields", {"f": {"assignee": "someone", "desc": d["f"]["desc"] + "\ncall 91234567 phone 98765432"}})
    v = st.draft_view(d)["val"]
    check("个人信息检查", any("个人信息" in e for e in v["errs"]), v)
    st.jira_update(d["id"], "mask", {})
    st.jira_update(d["id"], "approve", {"reviewer": "自检"})
    check("审核通过", st.draft(d["id"])["status"] == "approved")
    csv_text = st.jira_csv([d["id"]])
    check("Jira CSV", csv_text.startswith("﻿Summary") and "triage-" + d["id"] in csv_text)
    pl = st.jira_payloads([d["id"]])[0]
    check("提交内容", pl["fields"]["project"]["key"] == "ROTQA" and "triage-" + d["id"] in pl["fields"]["labels"])
    check("导出 CSV", "TC04" in st.cases_csv(rid))
    s = st.state()
    json.dumps(s, ensure_ascii=False)
    check("页面数据", len(s["cases"]) >= 5 and s["meta"]["CATS"] and s["corrections"][0]["test"]["ok"])
    # 重新打开（读文件）结果相同
    st2 = T.Store(ws=tmp / "ws", rules_file=cfg / "rules.json", corr_file=cfg / "corrections.json", jira_file=cfg / "jira.json", auto_ocr=False)
    check("重新打开结果相同", {c["uid"]: c["final"] for c in st2.analyzed() if c.get("failed")} == {c["uid"]: c["final"] for c in st.analyzed() if c.get("failed")})
    return st, rid


def t_server(st, rid):
    import ta_server
    srv, port = ta_server.serve(st, 18765)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:" + str(port)
    try:
        s = json.loads(urllib.request.urlopen(base + "/api/state", timeout=10).read())
        check("服务：读取数据", len(s["runs"]) == 1)
        html = urllib.request.urlopen(base + "/", timeout=10).read().decode("utf-8")
        check("服务：页面", "测试分析助手" in html)
        check("服务：心跳", json.loads(urllib.request.urlopen(base + "/api/ping", timeout=10).read()).get("tool") == "ta-server")
        req = urllib.request.Request(base + "/api/case", data=b'{"uids":[],"set":{}}', method="POST", headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            check("服务：没有 X-TA 头要拒绝", False)
        except urllib.error.HTTPError as e:
            check("服务：没有 X-TA 头要拒绝", e.code == 403)
        req = urllib.request.Request(base + "/api/case", data=b'{"uids":[],"set":{"bad":1}}', method="POST", headers={"Content-Type": "application/json", "X-TA": "1"})
        try:
            urllib.request.urlopen(req, timeout=10)
            check("服务：不允许的字段要拒绝", False)
        except urllib.error.HTTPError as e:
            check("服务：不允许的字段要拒绝", e.code == 400 and "不能修改" in json.loads(e.read())["error"])
        f = st.stored(next(c["uid"] for c in st.analyzed() if c.get("shots")))["shots"][0]["file"]
        check("服务：截图", urllib.request.urlopen(base + "/files/" + rid + "/" + f, timeout=10).read() == PNG)
        try:
            urllib.request.urlopen(base + "/files/" + rid + "/..%2F..%2Frun.json", timeout=10)
            check("服务：不能读截图目录以外的文件", False)
        except urllib.error.HTTPError as e:
            check("服务：不能读截图目录以外的文件", e.code == 404)
    finally:
        srv.shutdown()


def t_misc():
    check("卡号识别", J.mask("card 4111 1111 1111 1111") == "card <CARD>")
    check("非卡号不动", J.mask("policy 1234567890123456") == "policy 1234567890123456")
    check("HKID", J.mask("id A123456(7)") == "id <HKID>")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ta_selftest_"))
    try:
        for fn in (t_import, t_misc):
            try:
                fn()
            except Exception:  # noqa: BLE001
                fails.append(fn.__name__ + " 出错：\n" + traceback.format_exc())
        try:
            st, rid = t_store(tmp)
            t_server(st, rid)
        except Exception:  # noqa: BLE001
            fails.append("工作区/服务 出错：\n" + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("自检失败 " + str(len(fails)) + " 项：")
        for f in fails:
            print(" -", f)
        return 1
    print("自检通过")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
