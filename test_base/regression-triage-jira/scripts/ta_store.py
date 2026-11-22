"""工作区：保存导入的批次、人工记录、截图、Jira 草稿；规则、自定义规则、纠错样本的读写和修改记录。

页面（经 ta_server）和命令行（ta.py）都通过这里读写，分析一律调用 ta_engine。
文件位置（都在本机）：
    workspace/runs/<批次>/run.json   批次信息和用例（原始字段 + 人工记录）
    workspace/runs/<批次>/shots/     截图
    workspace/ocr.json              截图文字识别结果（按图片内容 sha256）
    workspace/drafts.json           Jira 草稿；workspace/jira_log.json 提交记录；workspace/settings.json 个人设置
    config/rules.json               判断规则 + 自定义规则 + 修改记录（团队共用）
    config/corrections.json         纠错样本（团队共用）
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import ta_engine as E
import ta_import as I
import ta_jira as J
import ta_ocr

ROOT = E.ROOT
CORR_FILE = ROOT / "config" / "corrections.json"
JIRA_FILE = ROOT / "config" / "jira.json"
RAW = ("uid", "run", "seq", "id", "name", "result", "error", "stack", "exceptionRaw", "pageText", "screenshot", "start",
       "module", "device", "failed", "parent", "attempt")
HUMAN = ("obs", "ai", "dataCheck", "dataNote", "override", "rerun", "rerunNote", "rerunReq", "r2")
IMG_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/gif": ".gif", "image/bmp": ".bmp", "image/webp": ".webp"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(p: Path, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, data, indent=None) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(p)


def safe_name(s: str, n=40) -> str:
    return re.sub(r"[^\w.\-]+", "_", str(s))[:n].strip("_") or "x"


class UserError(Exception):
    """可以直接显示给用户的错误。"""


class Store:
    def __init__(self, ws: Path | None = None, rules_file: Path | None = None, corr_file: Path | None = None, jira_file: Path | None = None, auto_ocr=True):
        self.ws = Path(ws or ROOT / "workspace")
        self.rules_file = Path(rules_file or E.RULES_FILE)
        self.corr_file = Path(corr_file or CORR_FILE)
        self.jira_file = Path(jira_file or JIRA_FILE)
        self.auto_ocr = auto_ocr  # 页面：导入后在后台识别；命令行：自己调用 ocr_sync()
        self.lock = threading.RLock()
        self.parsed = {}  # 导入前解析好的文件，key 是 token
        self.ocr_state = {"running": False, "msg": "", "at": ""}
        self._view = None
        self._rules_mtime = None
        self.load()

    # ------------------------------------------------------------ 读取
    def load(self):
        with self.lock:
            self.runs = []
            rd = self.ws / "runs"
            if rd.exists():
                for p in sorted(rd.glob("*/run.json")):
                    r = read_json(p, None)
                    if r and r.get("id"):
                        self.runs.append(r)
            self.runs.sort(key=lambda r: r.get("at", ""))
            self.drafts = read_json(self.ws / "drafts.json", [])
            self.jira_log = read_json(self.ws / "jira_log.json", [])
            self.settings = read_json(self.ws / "settings.json", {})
            self.ocr_idx = ta_ocr.load_index(self.ws / "ocr.json")
            self.load_rules()
            self._view = None

    def load_rules(self):
        self.doc = E.load_rule_doc(self.rules_file)
        self._rules_mtime = self.rules_file.stat().st_mtime if self.rules_file.exists() else None
        self.corr = read_json(self.corr_file, {"tool": "ta-corrections", "v": 1, "items": []})
        self.corr.setdefault("items", [])

    def check_rules_changed(self):
        """规则文件被别人改过（例如同步了团队的新版本）时自动重新读取。"""
        m = self.rules_file.stat().st_mtime if self.rules_file.exists() else None
        if m != self._rules_mtime:
            self.load_rules()
            self._view = None

    @property
    def rules(self):
        return self.doc["rules"]

    @property
    def custom(self):
        return self.doc["custom"]

    def run_of(self, rid):
        return next((r for r in self.runs if r["id"] == rid), None)

    def stored(self, uid):
        rid = uid.split("#")[0]
        r = self.run_of(rid)
        return next((c for c in r["cases"] if c["uid"] == uid), None) if r else None

    def save_run(self, r):
        write_json(self.ws / "runs" / r["id"] / "run.json", r)
        self._view = None

    def save_drafts(self):
        write_json(self.ws / "drafts.json", self.drafts)

    def save_settings(self):
        write_json(self.ws / "settings.json", self.settings, 1)

    # ------------------------------------------------------------ 分析
    def analyzed(self) -> list[dict]:
        """全部用例（工作副本）跑一遍判断。结果缓存，数据或规则变了才重新分析。"""
        with self.lock:
            self.check_rules_changed()
            if self._view is not None:
                return self._view
            cases = []
            for r in self.runs:
                for s in r["cases"]:
                    c = E.make_case(copy.deepcopy(s), self.rules)
                    c["shots"] = [dict(x, src="/files/" + r["id"] + "/" + x["file"]) for x in s.get("shots") or []]
                    c["shots2"] = [dict(x, src="/files/" + r["id"] + "/" + x["file"]) for x in s.get("shots2") or []]
                    if c.get("failed"):
                        t = E.ocr_text([self.ocr_idx.get(x.get("sha")) for x in s.get("shots") or [] if not (self.ocr_idx.get(x.get("sha")) or {}).get("error")])
                        if t:
                            c["ocrText"] = t
                    cases.append(c)
            E.classify_all(cases, self.rules, self.custom)
            self._view = cases
            self._by_uid = {c["uid"]: c for c in cases}
            return cases

    def case(self, uid):
        self.analyzed()
        return self._by_uid.get(uid)

    # ------------------------------------------------------------ 导入
    def parse(self, files: list[tuple[str, bytes]]) -> dict:
        p = I.parse_many(files)
        if not p["tables"]:
            raise UserError("没有读到任何数据行" + ("：" + p["errors"][0] if p["errors"] else ""))
        tok = hashlib.sha1((str(time.time()) + str(len(files))).encode()).hexdigest()[:12]
        with self.lock:
            self.parsed = {tok: p}  # 只保留最近一次
        return {"token": tok, "kind": p["kind"], "files": p["files"], "errors": p["errors"], "images": len(p["images"]),
                "tables": [{"path": (t.get("file", "") + " · " if len(p["files"]) > 1 and t.get("file") else "") + t["path"], "cols": I.columns_of(t["rows"]), "nrows": len(t["rows"])} for t in p["tables"]],
                "map": I.guess_mapping(I.columns_of(p["tables"][0]["rows"]), self.settings.get("mapping"))}

    def _parsed(self, tok, ti):
        p = self.parsed.get(tok)
        if not p:
            raise UserError("解析结果已过期，请重新选择文件")
        if not 0 <= ti < len(p["tables"]):
            raise UserError("没有这个列表")
        return p, p["tables"][ti]

    def preview(self, tok, ti, mapping) -> dict:
        p, t = self._parsed(tok, ti)
        cs = E.to_cases(t["rows"], mapping, self.rules, "preview")
        res = {}
        for c in cs:
            k = c["result"] or "(空)"
            res[k] = res.get(k, 0) + 1
        pv = ([c for c in cs if c["failed"]] + [c for c in cs if not c["failed"]])[:200]
        return {"n": len(cs), "nFail": sum(1 for c in cs if c["failed"]), "resVals": sorted(res.items(), key=lambda x: -x[1])[:10],
                "missing": [f["name"] for f in I.FIELDS if f.get("req") and not mapping.get(f["key"])], "map": mapping,
                "rows": [{"seq": c["seq"], "id": c["id"], "name": c["name"], "result": c["result"], "failed": c["failed"], "first": (c["error"] or c["stack"] or "").split("\n")[0][:200]} for c in pv]}

    def _write_shot(self, rid, uid, data: bytes, ext: str, name: str) -> dict:
        d = self.ws / "runs" / rid / "shots"
        d.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256(data).hexdigest()
        f = safe_name(uid.split("#", 1)[1] if "#" in uid else uid, 20) + "_" + h[:10] + ext
        (d / f).write_bytes(data)
        return {"name": name, "file": f, "sha": h}

    def _attach(self, rid, uid, cid, field, images, n0=0):
        """截图字段：img#k = 报告内嵌的图片（存成文件）；http 地址和文件路径原样保留。返回 (shots, 剩下的路径)。"""
        shots, keep = [], []
        for tk in [s.strip() for s in str(field or "").split(";") if s.strip()]:
            if tk.startswith("img#"):
                if tk in images:
                    mime, data = images[tk]
                    ext = IMG_EXT.get(mime, ".png")
                    shots.append(self._write_shot(rid, uid, data, ext, safe_name(cid, 30) + "_" + str(n0 + len(shots) + 1) + ext))
            else:
                keep.append(tk)
        return shots, "; ".join(keep)

    def do_import(self, tok, ti, mapping, info) -> dict:
        p, t = self._parsed(tok, ti)
        miss = [f["name"] for f in I.FIELDS if f.get("req") and not mapping.get(f["key"])]
        if miss:
            raise UserError("请先对应：" + "、".join(miss))
        with self.lock:
            self.settings["mapping"] = dict(mapping)
            self.save_settings()
            at = now()
            images = p["images"]
            if info.get("mode") == "rerun":
                res = self._import_rerun(t, mapping, info, images, at)
            else:
                rid = "R" + str(int(time.time() * 1000))
                cases = E.to_cases(t["rows"], mapping, self.rules, rid)
                stored, nshot = [], 0
                for c in cases:
                    s = {k: c[k] for k in RAW if k in c}
                    if c["failed"]:
                        s["shots"], s["screenshot"] = self._attach(rid, c["uid"], c["id"], c["screenshot"], images)
                        nshot += 1 if s["shots"] else 0
                    else:
                        s["screenshot"] = "; ".join(x.strip() for x in c["screenshot"].split(";") if x.strip() and not x.strip().startswith("img#"))
                    stored.append(s)
                r = {"id": rid, "name": info.get("name") or (p["files"][0].rsplit(".", 1)[0] if p["files"] else "批次" + str(len(self.runs) + 1)),
                     "plan": info.get("plan", ""), "device": info.get("device", ""), "env": info.get("env", ""),
                     "file": "、".join(p["files"])[:200], "at": at, "total": len(stored), "cases": stored}
                self.runs.append(r)
                self.save_run(r)
                nf = sum(1 for c in stored if c.get("failed"))
                res = {"run": rid, "msg": "已导入 " + str(len(stored)) + " 条，其中失败 " + str(nf) + " 条" + ("，" + str(nshot) + " 条带截图" if nshot else "")}
            self.parsed.pop(tok, None)
        self.ocr_async()
        return res

    def _import_rerun(self, t, mapping, info, images, at):
        r = self.run_of(info.get("rerunOf")) or (self.runs[-1] if self.runs else None)
        if not r:
            raise UserError("还没有可以更新的批次")
        rc = E.to_cases(t["rows"], mapping, self.rules, "rerun")
        for x in rc:
            E.prepare(x, self.rules)
        by_id = {x["id"]: x for x in rc}
        sig0 = {c["uid"]: c.get("sig0") for c in self.analyzed() if c.get("run") == r["id"]}
        hit = npass = same = diff = 0
        note = (info.get("name") or "重跑") + " " + at
        for c in [x for x in r["cases"] if x.get("failed") and not x.get("parent")]:
            x = by_id.get(c["id"])
            if not x:
                continue
            hit += 1
            r2uid = c["uid"] + "#2"
            r["cases"] = [y for y in r["cases"] if y["uid"] != r2uid]
            c["rerun"], c["rerunNote"] = ("fail" if x["failed"] else "pass"), note
            c.pop("rerunReq", None)
            err = (x["error"] or x["stack"] or "")[:4000]
            if not x["failed"] or (x.get("sig0") and x["sig0"] == sig0.get(c["uid"])):
                c["shots2"], path = self._attach(r["id"], c["uid"] + "@r2", c["id"] + "_rerun", x["screenshot"], images)
                c["r2"] = {"start": x["start"] or at, "screenshot": path, "same": None if not x["failed"] else True}
                if x["failed"]:
                    c["r2"]["error"] = err
                    same += 1
                else:
                    npass += 1
                continue
            diff += 1
            c["shots2"] = []
            c["r2"] = {"start": x["start"] or at, "screenshot": "", "error": err, "same": False}
            n = {k: x[k] for k in RAW if k in x}
            n.update(uid=r2uid, run=r["id"], seq=c["seq"], id=c["id"], name=c.get("name") or x["name"], parent=c["uid"], attempt=2,
                     module=x["module"] or c.get("module", ""), device=x["device"] or c.get("device", ""), failed=True)
            n["shots"], n["screenshot"] = self._attach(r["id"], r2uid, c["id"] + "_2", x["screenshot"], images)
            r["cases"].append(n)
        self.save_run(r)
        return {"run": r["id"], "rerun": True, "msg": "已匹配 " + str(hit) + " 条重跑结果：通过 " + str(npass) + " 条，仍失败且同一问题 " + str(same) + " 条，仍失败但报错不同 " + str(diff) + " 条"}

    def import_paths(self, paths: list[Path], info: dict) -> dict:
        """命令行导入：自动猜字段对应，猜不出必需字段时报错。"""
        p = self.parse([(Path(x).name, Path(x).read_bytes()) for x in paths])
        miss = [f["name"] for f in I.FIELDS if f.get("req") and not p["map"].get(f["key"])]
        if miss:
            raise UserError("认不出这些字段：" + "、".join(miss) + "。请用页面导入，手动对应一次（之后会记住）。可用的列：" + "、".join(p["tables"][0]["cols"][:30]))
        return self.do_import(p["token"], 0, p["map"], info)

    def delete_run(self, rid):
        with self.lock:
            self.runs = [r for r in self.runs if r["id"] != rid]
            shutil.rmtree(self.ws / "runs" / rid, ignore_errors=True)
            self.drafts = [d for d in self.drafts if d.get("run") != rid or d.get("status") == "submitted"]
            self.save_drafts()
            self._view = None

    # ------------------------------------------------------------ 人工记录
    def set_case(self, uids, values: dict):
        bad = [k for k in values if k not in HUMAN]
        if bad:
            raise UserError("不能修改：" + "、".join(bad))
        if values.get("override") and not str(values["override"].get("reason") or "").strip():
            raise UserError("人工改判必须写原因")
        o = values.get("obs")
        if o and o.get("kind") and o["kind"] not in E.OBS_KINDS:
            raise UserError("截图观察的现象只能是：" + "、".join(E.OBS_KINDS))
        ai = values.get("ai")
        if ai and (ai.get("cat") not in E.CATS or not str(ai.get("reason") or "").strip()):
            raise UserError("AI 判断要写分类（" + "、".join(E.CATS) + "）和原因")
        with self.lock:
            touched = {}
            for u in uids:
                s = self.stored(u)
                if not s:
                    continue
                for k, v in values.items():
                    if v is None or v == "":
                        s.pop(k, None)
                    else:
                        s[k] = v
                touched[s["run"]] = self.run_of(s["run"])
            for r in touched.values():
                self.save_run(r)
            return len(uids)

    def add_shots(self, uid, items: list[dict], which="shots"):
        """items: [{name, data(base64 或 data: 地址)}]"""
        with self.lock:
            s = self.stored(uid)
            if not s:
                raise UserError("找不到用例")
            lst = s.setdefault(which, [])
            for it in items:
                d = it.get("data") or ""
                m = re.match(r"^data:(image/[\w.+-]+);base64,", d)
                mime = m.group(1) if m else "image/png"
                raw = base64.b64decode(d[m.end():] if m else d)
                ext = IMG_EXT.get(mime, ".png")
                name = it.get("name") or safe_name(s["id"], 30) + "_" + str(len(lst) + 1) + ext
                lst.append(self._write_shot(s["run"], uid, raw, ext, name))
            self.save_run(self.run_of(s["run"]))
        self.ocr_async()
        return len(items)

    def del_shots(self, uid, idx=None, which="shots"):
        with self.lock:
            s = self.stored(uid)
            if not s:
                return
            lst = s.get(which) or []
            gone = lst if idx is None else [lst[idx]] if 0 <= idx < len(lst) else []
            s[which] = [x for x in lst if x not in gone]
            used = {x["file"] for c in self.run_of(s["run"])["cases"] for k in ("shots", "shots2") for x in c.get(k) or []}
            for x in gone:
                if x["file"] not in used:
                    (self.ws / "runs" / s["run"] / "shots" / x["file"]).unlink(missing_ok=True)
            self.save_run(self.run_of(s["run"]))

    def match_shots(self, rid, items: list[dict]) -> dict:
        """按截图文件名匹配用例：报告里写的截图文件名，或文件名（含文件夹名）里有用例编号。"""
        r = self.run_of(rid)
        if not r:
            raise UserError("找不到批次")
        cs = sorted([c for c in r["cases"] if c.get("failed") and not c.get("parent")], key=lambda c: -len(str(c["id"])))
        matched, un = 0, []
        for it in items:
            path = str(it.get("name") or "")
            base = path.replace("\\", "/").split("/")[-1].lower()
            c = next((c for c in cs if base in [x.strip().replace("\\", "/").split("/")[-1].lower() for x in str(c.get("screenshot") or "").split(";")]), None) \
                or next((c for c in cs if c["id"] and str(c["id"]).lower() in path.lower()), None)
            if not c:
                un.append(base)
                continue
            self.add_shots(c["uid"], [{"name": base, "data": it["data"]}])
            matched += 1
        return {"matched": matched, "unmatched": un}

    # ------------------------------------------------------------ 截图文字识别（后台）
    def ocr_files(self):
        return [self.ws / "runs" / r["id"] / "shots" / x["file"] for r in self.runs for c in r["cases"] if c.get("failed")
                for k in ("shots", "shots2") for x in c.get(k) or [] if x.get("sha") not in self.ocr_idx]

    def ocr_async(self):
        if not self.auto_ocr:
            return
        ok, why = ta_ocr.available()
        if not ok:
            self.ocr_state.update(msg=why)
            return
        with self.lock:
            if self.ocr_state["running"] or not self.ocr_files():
                return
            self.ocr_state.update(running=True, msg="正在识别截图文字…", at=now())

        def work():
            try:
                while True:
                    fs = [f for f in self.ocr_files() if f.exists()]
                    if not fs:
                        break
                    res = ta_ocr.run(fs, self.ws / "ocr.json", log=lambda m: self.ocr_state.update(msg=m))
                    with self.lock:
                        self.ocr_idx = ta_ocr.load_index(self.ws / "ocr.json")
                        self._view = None
                        self.ocr_state.update(msg=res["msg"], at=now())
                    if not res["ok"] or not res["new"]:
                        break
            finally:
                self.ocr_state["running"] = False
        threading.Thread(target=work, daemon=True).start()

    def ocr_sync(self) -> str:
        fs = [f for f in self.ocr_files() if f.exists()]
        if not fs:
            return "没有需要识别的截图"
        res = ta_ocr.run(fs, self.ws / "ocr.json")
        self.ocr_idx = ta_ocr.load_index(self.ws / "ocr.json")
        self._view = None
        return res["msg"]

    def import_ocr_doc(self, doc: dict) -> int:
        """导入手动生成的 .ocr.json（自动识别失败时的备用办法）。"""
        with self.lock:
            idx = ta_ocr.load_index(self.ws / "ocr.json")
            n = ta_ocr.merge_result(idx, doc)
            ta_ocr.save_index(self.ws / "ocr.json", idx)
            self.ocr_idx = idx
            self._view = None
            return n

    # ------------------------------------------------------------ 规则、自定义规则、修改记录
    def _write_rules(self, rules=None, custom=None, entry=None):
        data = read_json(self.rules_file, {}) if self.rules_file.exists() else {}
        doc = {"tool": "ta-rules", "_说明": data.get("_说明") or "团队共用的判断规则。在测试分析助手“配置”里修改会自动保存到这里；直接改文件后运行 python scripts/ta.py check。恢复默认用 rules.default.json。",
               "v": 2, "rules": rules if rules is not None else self.rules, "custom": custom if custom is not None else self.custom,
               "changelog": (self.doc["changelog"] + [entry]) if entry else self.doc["changelog"]}
        write_json(self.rules_file, doc, 2)
        self.load_rules()
        self._view = None

    def _finals(self):
        return {c["uid"]: c["final"] for c in self.analyzed() if c.get("failed")}

    def _after_change(self, before):
        after = self._finals()
        changed = [u for u in after if before.get(u) != after[u]]
        return {"changed": len(changed), "corrections": self.test_corrections()}

    def save_rules(self, rules: dict, by: str, note: str) -> dict:
        base = E.default_rules()
        bad = [k for k in rules if k not in base]
        if bad:
            raise UserError("不认识的规则项：" + "、".join(bad))
        for k, v in rules.items():
            if isinstance(base[k], (int, float)):
                if not isinstance(v, (int, float)) or v < 0:
                    raise UserError(k + " 要填非负数字")
            elif not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                raise UserError(k + " 要填文字清单")
            else:
                for x in v:
                    if x.startswith("re:"):
                        try:
                            re.compile(x[3:])
                        except re.error as e:
                            raise UserError(k + " 里的模糊匹配写法有误“" + x + "”（" + str(e) + "）")
        with self.lock:
            old = self.rules
            new = {**old, **rules}
            what = []
            for k in new:
                a, b = old.get(k), new[k]
                if a == b:
                    continue
                if isinstance(b, list):
                    add, rem = [x for x in b if x not in (a or [])], [x for x in (a or []) if x not in b]
                    what.append(k + "（" + ("+" + "、".join(add[:3]) + ("…" if len(add) > 3 else "") if add else "") + (" −" + "、".join(rem[:3]) + ("…" if len(rem) > 3 else "") if rem else "") + "）")
                else:
                    what.append(k + "：" + str(a) + " → " + str(b))
            if not what:
                return {"changed": 0, "corrections": self.test_corrections(), "msg": "规则没有变化"}
            before = self._finals()
            self._write_rules(rules=new, entry={"at": now()[:16], "by": by or "", "what": "修改判断规则：" + "；".join(what), "note": note or ""})
            return self._after_change(before)

    def reset_rules(self, by, note) -> dict:
        with self.lock:
            before = self._finals()
            self._write_rules(rules=E.default_rules(), entry={"at": now()[:16], "by": by or "", "what": "判断规则恢复默认（自定义规则保留）", "note": note or ""})
            return self._after_change(before)

    def import_rules(self, text: str, by: str) -> dict:
        try:
            d = json.loads(text.lstrip("﻿"))
        except ValueError:
            raise UserError("不是 JSON 文件")
        if not isinstance(d, dict) or d.get("tool") != "ta-rules":
            raise UserError("不是测试分析助手的规则文件（rules.json）")
        errs = E.validate_custom(d.get("custom") or [])
        if errs:
            raise UserError("自定义规则有问题：" + errs[0])
        with self.lock:
            before = self._finals()
            rules = {**E.default_rules(), **(d.get("rules") or {})}
            self._write_rules(rules=rules, custom=d.get("custom") or [],
                              entry={"at": now()[:16], "by": by or "", "what": "导入规则文件（" + str(len(d.get("custom") or [])) + " 条自定义规则）", "note": ""})
            return self._after_change(before)

    def save_custom(self, items: list, by: str, note: str) -> dict:
        errs = E.validate_custom(items)
        if errs:
            raise UserError("；".join(errs[:5]))
        with self.lock:
            old = {u["id"]: u for u in self.custom}
            new = {u["id"]: u for u in items}
            what = [("新增 " if k not in old else "修改 ") + k + "“" + str(new[k].get("name") or "") + "”" for k in new if old.get(k) != new[k]] + \
                   ["删除 " + k + "“" + str(old[k].get("name") or "") + "”" for k in old if k not in new]
            if [u["id"] for u in items] != [u["id"] for u in self.custom] and not what:
                what = ["调整顺序"]
            if not what:
                return {"changed": 0, "corrections": self.test_corrections(), "msg": "没有变化"}
            for u in items:
                if old.get(u["id"]) != u:
                    u["by"], u["at"] = u.get("by") or by or "", now()[:16]
            before = self._finals()
            self._write_rules(custom=items, entry={"at": now()[:16], "by": by or "", "what": "自定义规则：" + "；".join(what), "note": note or ""})
            return self._after_change(before)

    def custom_test(self, item: dict) -> dict:
        """试一下一条自定义规则（不保存）：全部失败用例里会命中哪些。"""
        errs = E.validate_custom([dict(item, id=item.get("id") or "U0")])
        if errs:
            raise UserError(errs[0])
        u = dict(item, enabled=True)
        hits = []
        for c in self.analyzed():
            if not c.get("failed"):
                continue
            m = E.custom_match(c, [u], False) or (E.custom_match(c, [u], True) if c.get("ocrText") and not (c.get("obs") or {}).get("text") else None)
            if m:
                hits.append({"uid": c["uid"], "id": c["id"], "name": c.get("name"), "now": c["final"], "hits": m[1][:3]})
        return {"n": len(hits), "cases": hits[:100]}

    # ------------------------------------------------------------ 纠错样本
    def save_corr(self):
        write_json(self.corr_file, self.corr, 1)

    def add_correction(self, uid, category, keep_rule, reason, by) -> dict:
        if category not in E.CATS:
            raise UserError("分类不正确")
        if not str(reason or "").strip():
            raise UserError("请写明为什么应该是这个分类")
        c = self.case(uid)
        if not c or not c.get("failed"):
            raise UserError("找不到失败用例")
        with self.lock:
            ids = [int(x["id"][1:]) for x in self.corr["items"] if re.fullmatch(r"C\d+", str(x.get("id")))]
            sid = "C%03d" % (max(ids, default=0) + 1)
            run = self.run_of(c["run"]) or {}
            exp = {"category": category}
            if keep_rule:
                exp["rule"] = c["auto"]["rule"]
            item = {"id": sid, "expect": exp, "reason": reason.strip(), "by": by or "", "at": now()[:16],
                    "from": {"run": run.get("name", ""), "case_id": c["id"], "was": {"category": c["auto"]["cat"], "rule": c["auto"]["rule"]}}, "case": E.sample_of(c)}
            self.corr["items"].append(item)
            self.save_corr()
            return {"id": sid, "test": next(t for t in self.test_corrections() if t["id"] == sid)}

    def del_correction(self, sid):
        with self.lock:
            self.corr["items"] = [x for x in self.corr["items"] if x.get("id") != sid]
            self.save_corr()

    def test_corrections(self, rules=None, custom=None):
        return E.test_corrections(self.corr["items"], rules or self.rules, self.custom if custom is None else custom)

    # ------------------------------------------------------------ Jira 草稿
    @property
    def jira_cfg(self):
        return J.load_cfg(self.jira_file)

    def _case_of(self, uid):
        return self.case(uid)

    def draft(self, did):
        d = next((x for x in self.drafts if x["id"] == did), None)
        if not d:
            raise UserError("找不到草稿")
        return d

    def draft_view(self, d) -> dict:
        c = self.case(d["uids"][0])
        return dict(d, val=J.validate(d, c, self.drafts, self._case_of), wiki=J.wiki(d, self.jira_cfg), labelsAll=J.labels_of(d))

    def jira_new(self, uids) -> list[str]:
        cfg = self.jira_cfg
        with self.lock:
            used = {u for d in self.drafts if d["status"] != "discarded" for u in d["uids"]}
            out = []
            for u in uids:
                c = self.case(u)
                if not c or not c.get("failed") or u in used or c.get("rerun") == "pass":
                    continue
                d = J.new_draft(c, self.run_of(c["run"]) or {}, cfg, self._case_of)
                self.drafts.append(d)
                out.append(d["id"])
            self.save_drafts()
            return out

    def jira_update(self, did, act: str, data: dict) -> dict:
        """act: fields（改字段）/ mode / ack / refresh / approve / unapprove / discard / key / ai"""
        cfg = self.jira_cfg
        with self.lock:
            d = self.draft(did)
            if d["status"] == "submitted" and act not in ("key",):
                raise UserError("已提交的单不能再修改")
            hist = lambda m: d["history"].append(now() + " " + m)

            def touched(m=None):
                if d["status"] == "approved":
                    d["status"] = "draft"
                    hist("审核后又修改，需重新审核")
                if m:
                    hist(m)
            if act == "fields":
                for k, v in (data.get("f") or {}).items():
                    if k in J.FIELD_NAMES and d["f"].get(k) != v:
                        d["f"][k], d["src"][k] = v, data.get("src") or "人工"
                touched("填入 AI 结果" if data.get("src") == "AI" else None)
            elif act == "mode":
                d["mode"] = data.get("mode") if data.get("mode") in ("create", "comment") else "create"
                d["target"] = str(data.get("target") or "").strip().upper()
                touched()
            elif act == "ack":
                d["ack"] = bool(data.get("ack"))
            elif act == "refresh":
                c = self.case(d["uids"][0])
                if c:
                    d["cat"], d["sig"] = c["final"], c.get("sig")
                    J.apply_script(d, c, self.run_of(c["run"]) or {}, cfg, self._case_of)
                touched("按最新分诊刷新")
            elif act == "mask":
                for k in d["f"]:
                    m = J.mask(d["f"][k])
                    if m != d["f"][k]:
                        d["f"][k], d["src"][k] = m, "人工"
                touched("一键脱敏")
            elif act == "approve":
                v = J.validate(d, self.case(d["uids"][0]), self.drafts, self._case_of)
                if not v["ok"]:
                    raise UserError("还有必须修改的问题：" + (v["errs"] or ["请确认“待复核”"])[0])
                d.update(status="approved", reviewedAt=now())
                hist("审核通过")
            elif act == "unapprove":
                d["status"] = "draft"
                hist("撤回审核")
            elif act == "discard":
                d["status"] = "draft" if d["status"] == "discarded" else "discarded"
                hist("放弃" if d["status"] == "discarded" else "恢复")
            elif act == "key":
                k = str(data.get("key") or "").strip().upper()
                if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", k):
                    raise UserError("单号格式不对，例如 ROTQA-5339")
                d.update(issueKey=k, status="submitted", submittedAt=now())
                hist("回填单号 " + k)
                self.log_jira("手动回填", 1, k)
            else:
                raise UserError("不支持的操作")
            self.save_drafts()
            return self.draft_view(d)

    def ai_prompt(self, did) -> str:
        d = self.draft(did)
        c = self.case(d["uids"][0])
        ev = "\n".join(e["id"] + " " + e["label"] + "：" + (e["text"][:1200] + "…（已截断）" if len(e["text"]) > 1200 else e["text"]) for e in c["auto"]["ev"] if e["kind"] != "shot") if c else ""
        return ("请把下面这张 Jira 单的描述润色成简洁、自然的英文，像测试同事写给开发的留言。要求：\n"
                "1. 第一段一两句话说清楚：哪个功能、出现什么问题、在做什么操作时出现，最后请对方帮忙看；\n"
                "2. 保留 *1st run* / *2nd run* 两段和其中的截图标记（!文件名|thumbnail!），不要改动报错原文；\n"
                "3. 只能使用给出的信息，不要编造步骤、数据或原因；\n4. 标题原因用英文短语，不超过 12 个单词；\n"
                "5. 严格按格式输出，每个【】标记单独一行：\n【Title cause】\n【Description】\n\n"
                "========== 当前草稿 ==========\nTitle: " + d["f"]["summary"] + "\nDescription:\n" + d["f"]["desc"] +
                "\n\n========== 用例证据 ==========\n" + ("Case " + str(c["id"]) + " " + str(c.get("name") or "") + "\n" + ev if c else ""))

    def ai_fill(self, did, text: str) -> dict:
        d = self.draft(did)
        parts, cur = {}, None
        for l in text.split("\n"):
            m = re.match(r"^\s*【(.+?)】\s*(.*)$", l)
            if m:
                cur = m.group(1).strip()
                parts[cur] = [m.group(2)] if m.group(2) else []
            elif cur:
                parts[cur].append(l)
        get = lambda k: "\n".join(parts.get(k) or []).strip()
        f = {}
        cause = get("Title cause")
        if cause:
            s = d["f"]["summary"]
            at = s.rfind(" due to ")
            f["summary"] = s[:at + 8] + cause if at > 0 else s + " - " + cause
        if get("Description"):
            f["desc"] = get("Description")
        if not f:
            raise UserError("没有识别到【】标记，请确认 AI 按格式输出")
        return self.jira_update(did, "fields", {"f": f, "src": "AI"})

    def log_jira(self, how, n, result):
        self.jira_log.append({"at": now(), "how": how, "n": n, "result": result, "by": self.settings.get("reviewer", "")})
        write_json(self.ws / "jira_log.json", self.jira_log)

    def jira_payloads(self, ids) -> list[dict]:
        cfg = self.jira_cfg
        out = []
        for i in ids:
            d = self.draft(i)
            if d["status"] != "approved":
                raise UserError("只有审核通过的单才能导出或提交")
            cs = [c for c in (self.case(u) for u in d["uids"]) if c]
            out.append(J.payload(d, cfg, cs, self.run_of(d["run"]) or {}))
        return out

    def jira_csv(self, ids) -> str:
        ds = [self.draft(i) for i in ids]
        if any(d["status"] != "approved" for d in ds):
            raise UserError("只有审核通过的单才能导出")
        lst = [d for d in ds if d["mode"] == "create"]
        self.log_jira("导出 CSV", len(lst), "已导出，待在 Jira 导入")
        return J.jira_csv(lst, self.jira_cfg)

    def jira_submit(self, ids, dry_run=True) -> list[dict]:
        cfg = self.jira_cfg
        items = self.jira_payloads(ids)
        file_of = lambda f: next((self.ws / "runs" / r["id"] / "shots" / f for r in self.runs if (self.ws / "runs" / r["id"] / "shots" / f).exists()), None)
        try:
            res = J.submit(items, cfg, dry_run, file_of)
        except RuntimeError as e:
            raise UserError(str(e))
        with self.lock:
            if dry_run:
                self.log_jira("预检", len(items), str(sum(1 for r in res if r.get("error"))) + " 个问题")
            else:
                for r in res:
                    if r.get("key"):
                        d = self.draft(r["draftId"])
                        d.update(issueKey=r["key"], status="submitted", submittedAt=now())
                        d["history"].append(now() + " 提交成功 " + r["key"] + ("，附件失败 " + str(r["attachmentsFailed"]) + " 个" if r.get("attachmentsFailed") else ""))
                self.save_drafts()
                self.log_jira("提交到 Jira", len(items), str(sum(1 for r in res if r.get("key"))) + " 张成功")
        return res

    # ------------------------------------------------------------ 重跑
    def rerun_send(self, rid, uids) -> dict:
        r = self.run_of(rid)
        cs = [c for c in (self.stored(u) for u in uids) if c]
        ids = [c["id"] for c in cs]
        url = self.jira_cfg.get("rerunUrl")
        if not url:
            self.set_case(uids, {"rerunReq": now()})
            return {"copied": True, "ids": ids, "msg": "没有配置重跑接口，已复制 " + str(len(ids)) + " 个用例编号，请到平台粘贴重跑"}
        try:
            msg = J.send_rerun(url, (r or {}).get("name", ""), ids)
        except RuntimeError as e:
            raise UserError(str(e))
        self.set_case(uids, {"rerunReq": now()})
        return {"copied": False, "ids": ids, "msg": "已发起重跑 " + str(len(ids)) + " 个（" + msg + "）。重跑完成后导入结果，选“重跑结果”"}

    # ------------------------------------------------------------ 给页面和命令行的数据
    def cases_view(self) -> list[dict]:
        out = []
        for c in self.analyzed():
            v = {k: c.get(k) for k in ("uid", "run", "seq", "id", "name", "result", "failed", "module", "device", "start", "parent", "attempt")}
            if c.get("failed"):
                v.update({k: c.get(k) for k in HUMAN + ("screenshot", "exception", "sig", "ocrText")})
                v["error1"] = (c.get("error") or c.get("stack") or "").split("\n")[0][:300]
                v["shots"] = [{"name": s["name"], "src": s["src"]} for s in c["shots"]]
                v["shots2"] = [{"name": s["name"], "src": s["src"]} for s in c["shots2"]]
                a = c["auto"]
                v["auto"] = {k: a.get(k) for k in ("cat", "status", "rule", "why", "need", "hits", "flags", "brief", "checkKind", "reason", "phase", "ocr", "custom")}
                v["auto"]["ev"] = [{k: e.get(k) for k in ("id", "kind", "label", "text", "src", "derived")} for e in a["ev"]]
                v["final"], v["plan"], v["ruleName"], v["aiUsed"] = c["final"], c["plan"], E.rule_name(c), c.get("aiUsed")
            out.append(v)
        return out

    def state(self) -> dict:
        with self.lock:
            cases = self.cases_view()
            cfg = self.jira_cfg
            return {
                "meta": {"CATS": E.CATS, "PLAN": E.PLAN, "PLAN_COLOR": E.PLAN_COLOR, "OBS_KINDS": E.OBS_KINDS, "CHECK_KINDS": E.CHECK_KINDS, "RULE_NAMES": E.RULE_NAMES,
                         "REASONS": E.REASONS, "FIELDS": [{k: f.get(k) for k in ("key", "name", "req")} for f in I.FIELDS], "CUSTOM_SOURCES": E.CUSTOM_SOURCES,
                         "JIRA_FIELDS": J.FIELD_NAMES, "DEFAULT_RULES": E.default_rules(), "ocr": ta_ocr.available()[0],
                         "jiraEnv": bool(os.environ.get("JIRA_API_TOKEN")) and bool(os.environ.get("JIRA_BASE_URL") or cfg.get("baseUrl"))},
                "runs": [{k: v for k, v in r.items() if k != "cases"} for r in self.runs],
                "cases": cases,
                "rules": self.rules, "custom": self.custom, "changelog": self.doc["changelog"],
                "corrections": [dict({k: x.get(k) for k in ("id", "expect", "reason", "by", "at", "from")}, test=t) for x, t in zip(self.corr["items"], self.test_corrections())],
                "drafts": [self.draft_view(d) for d in self.drafts], "jira": cfg, "jiraLog": self.jira_log[-100:],
                "settings": self.settings, "ocr": dict(self.ocr_state),
            }

    def cases_csv(self, rid=None) -> str:
        rows = [["批次", "用例编号", "名称", "第几次", "分类", "判定", "规则", "判断依据", "处理方", "重跑建议", "重跑结果", "截图观察", "核查结果", "人工改判原因"]]
        runs = {r["id"]: r["name"] for r in self.runs}
        for c in self.analyzed():
            if not c.get("failed") or (rid and c["run"] != rid):
                continue
            a, o = c["auto"], c.get("obs") or {}
            rows.append([runs.get(c["run"], ""), c["id"], c.get("name", ""), "2" if c.get("parent") else "1", E.CATS[c["final"]]["name"],
                         "人工已改" if c.get("override") else "规则确认" if a["status"] == "confirmed" else "待复核", E.rule_name(c), a["brief"], E.CATS[c["final"]]["owner"],
                         E.PLAN[c["plan"]["b"]], {"pass": "通过", "fail": "失败"}.get(c.get("rerun"), ""),
                         (E.OBS_KINDS.get(o.get("kind"), "") + (" " + o["text"] if o.get("text") else "")).strip(), E.DATA_CHECK.get(c.get("dataCheck"), ""),
                         (c.get("override") or {}).get("reason", "")])
        return J.to_csv(rows)

    def save_jira_cfg(self, cfg) -> dict:
        try:
            return J.save_cfg(self.jira_file, {**self.jira_cfg, **cfg})
        except ValueError as e:
            raise UserError(str(e))

    def save_setting(self, k, v):
        with self.lock:
            self.settings[k] = v
            self.save_settings()
