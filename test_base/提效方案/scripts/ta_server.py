"""测试分析助手的本机服务：页面（assets/）和接口都在这里，只监听 127.0.0.1，别的电脑访问不到。

页面只负责显示和收集操作，分析、导入、截图识别、Jira 起草和提交都由 Python 完成（ta_store / ta_engine / ta_jira）。
启动：python scripts/ta.py open（或双击「打开测试分析助手.bat」）。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ta_store as T

ASSETS = T.ROOT / "assets"
MAX_BODY = 400 * 1024 * 1024  # 报告网页另存的 mhtml 可能很大


def _b64(s):
    m = re.match(r"^data:[^,]*;base64,", s or "")
    return base64.b64decode(s[m.end():] if m else s or "")


def routes(st: T.Store):
    """POST 接口：路径 → 处理函数(请求 JSON) → 返回 JSON。"""
    by = lambda b: str(b.get("by") or st.settings.get("reviewer") or "")
    return {
        "/api/parse": lambda b: st.parse([(f["name"], _b64(f["data"])) for f in b.get("files") or []] or [("粘贴内容" + (".html" if b.get("html") else ""), b.get("text", "").encode("utf-8"))]),
        "/api/parse/preview": lambda b: st.preview(b["token"], int(b.get("table", 0)), b.get("map") or {}),
        "/api/import": lambda b: st.do_import(b["token"], int(b.get("table", 0)), b.get("map") or {}, b.get("info") or {}),
        "/api/run/delete": lambda b: st.delete_run(b["run"]),
        "/api/case": lambda b: {"n": st.set_case(b["uids"], b.get("set") or {})},
        "/api/shots/add": lambda b: {"n": st.add_shots(b["uid"], b.get("items") or [], b.get("which") or "shots")},
        "/api/shots/del": lambda b: st.del_shots(b["uid"], b.get("idx"), b.get("which") or "shots"),
        "/api/shots/match": lambda b: st.match_shots(b["run"], b.get("items") or []),
        "/api/ocr/run": lambda b: st.ocr_async() or {"ocr": st.ocr_state},
        "/api/ocr/import": lambda b: {"n": st.import_ocr_doc(json.loads(_b64(b["data"]).decode("utf-8-sig")))},
        "/api/rules/save": lambda b: st.save_rules(b.get("rules") or {}, by(b), b.get("note", "")),
        "/api/rules/reset": lambda b: st.reset_rules(by(b), b.get("note", "")),
        "/api/rules/import": lambda b: st.import_rules(b.get("text", ""), by(b)),
        "/api/custom/save": lambda b: st.save_custom(b.get("custom") or [], by(b), b.get("note", "")),
        "/api/custom/test": lambda b: st.custom_test(b.get("item") or {}),
        "/api/corrections/add": lambda b: st.add_correction(b["uid"], b.get("category"), bool(b.get("keepRule")), b.get("reason", ""), by(b)),
        "/api/corrections/delete": lambda b: st.del_correction(b["id"]),
        "/api/jira/new": lambda b: {"ids": st.jira_new(b.get("uids") or [])},
        "/api/jira/update": lambda b: st.jira_update(b["id"], b["act"], b.get("data") or {}),
        "/api/jira/ai": lambda b: {"text": st.ai_prompt(b["id"])},
        "/api/jira/aifill": lambda b: st.ai_fill(b["id"], b.get("text", "")),
        "/api/jira/csv": lambda b: {"text": st.jira_csv(b.get("ids") or [])},
        "/api/jira/payload": lambda b: {"items": st.jira_payloads(b.get("ids") or [])},
        "/api/jira/submit": lambda b: {"results": st.jira_submit(b.get("ids") or [], bool(b.get("dryRun", True)))},
        "/api/jira/cfg": lambda b: st.save_jira_cfg(b.get("cfg") or {}),
        "/api/rerun/send": lambda b: st.rerun_send(b.get("run"), b.get("uids") or []),
        "/api/settings": lambda b: st.save_setting(b["key"], b.get("value")),
    }


def make_handler(st: T.Store, port: int):
    R = routes(st)
    hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}

    class H(BaseHTTPRequestHandler):
        server_version = "TA/2"

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _guard(self) -> bool:
            # 只接受本机地址访问（防止别的网页借浏览器访问本服务）
            if self.headers.get("Host") not in hosts:
                self._json(403, {"error": "只能从本机访问"})
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            p = urllib.parse.unquote(u.path)
            try:
                if p == "/api/state":
                    return self._json(200, st.state())
                if p == "/api/ocr":
                    return self._json(200, st.ocr_state)
                if p == "/api/export/cases.csv":
                    rid = (q.get("run") or [None])[0]
                    return self._send(200, st.cases_csv(rid).encode("utf-8"), "text/csv; charset=utf-8",
                                      {"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote("失败分诊.csv")})
                if p == "/api/rules/file":
                    return self._send(200, st.rules_file.read_bytes(), "application/json; charset=utf-8", {"Content-Disposition": "attachment; filename=rules.json"})
                if p.startswith("/files/"):
                    parts = p.split("/")
                    if len(parts) == 4 and re.fullmatch(r"R\d+", parts[2]) and re.fullmatch(r"[\w.\-]+", parts[3]):
                        f = st.ws / "runs" / parts[2] / "shots" / parts[3]
                        if f.is_file():
                            return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                    return self._json(404, {"error": "没有这个文件"})
                name = "index.html" if p in ("/", "") else p.lstrip("/")
                f = (ASSETS / name).resolve()
                if ASSETS.resolve() in f.parents and f.is_file():
                    ct = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                    if ct.startswith("text/") or f.suffix == ".js":
                        ct = ("text/javascript" if f.suffix == ".js" else ct) + "; charset=utf-8"
                    return self._send(200, f.read_bytes(), ct)
                self._json(404, {"error": "没有这个页面"})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"error": "内部错误：" + str(e)})

        def do_POST(self):
            if not self._guard():
                return
            # 自定义请求头：别的网站的页面不能带这个头跨站提交
            if self.headers.get("X-TA") != "1":
                return self._json(403, {"error": "请求来源不对"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "文件太大（超过 400 MB）"})
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"error": "请求格式不对"})
            fn = R.get(urllib.parse.urlparse(self.path).path)
            if not fn:
                return self._json(404, {"error": "没有这个接口"})
            try:
                res = fn(body)
                self._json(200, res if isinstance(res, dict) else {"ok": True, "result": res})
            except T.UserError as e:
                self._json(400, {"error": str(e)})
            except (KeyError, ValueError, TypeError) as e:
                traceback.print_exc()
                self._json(400, {"error": "请求内容不完整或不正确（" + str(e) + "）"})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"error": "内部错误：" + str(e)})
    return H


class Server(ThreadingHTTPServer):
    # Windows 上 SO_REUSEADDR 会让两个程序同时占用一个端口，这里关掉，端口被占用时换下一个
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def serve(st: T.Store, port=8765, tries=20):
    for p in range(port, port + tries):
        try:
            srv = Server(("127.0.0.1", p), make_handler(st, p))
            return srv, p
        except OSError:
            continue
    raise OSError("端口 " + str(port) + "–" + str(port + tries - 1) + " 都被占用")
