"""截图文字识别：自动调用 tools/识别截图.bat（Windows 自带 OCR，不用安装软件，截图不离开本机）。

导入报告或补充截图后由 ta_store 自动调用，不需要手动拖文件。
识别结果按图片内容（sha256）存在 workspace/ocr.json，同一张图只识别一次。
不是 Windows 时跳过识别，其余功能照常使用。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "tools" / "识别截图.bat"
# 与 bat 第一段相同：读取 bat 自身，把 # 之后的 PowerShell 部分执行一遍（直接调用 PowerShell，避免 cmd 的引号和中文路径问题）
PS_CMD = "$s=[IO.File]::ReadAllText($env:TA_SELF,[Text.Encoding]::UTF8); Invoke-Expression ('& {' + $s + [char]10 + '}')"
TIMEOUT = 900  # 秒；几百张截图一般 1–3 分钟


def available() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "不是 Windows，跳过截图文字识别"
    if not BAT.exists():
        return False, "找不到 tools/识别截图.bat"
    return True, ""


def load_index(path: Path) -> dict:
    """{sha256: 识别结果}；识别失败的图记为 {"error": ...}。"""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")).get("images", {})
    except (OSError, ValueError):
        return {}


def save_index(path: Path, idx: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"tool": "ta-ocr-index", "v": 1, "images": idx}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def merge_result(idx: dict, doc: dict) -> int:
    """把 .ocr.json（bat 生成的）并入索引，返回新增张数。"""
    if not isinstance(doc, dict) or doc.get("tool") != "ta-ocr":
        raise ValueError("不是识别截图工具生成的结果文件")
    n = 0
    for im in doc.get("images") or []:
        h = im.get("sha256")
        if not h:
            continue
        if h not in idx or idx[h].get("error"):
            n += 1
        idx[h] = {k: im[k] for k in ("langs", "w", "h", "error") if k in im}
    return n


def run(files: list[Path], idx_path: Path, log=print) -> dict:
    """识别 files 里还没识别过的图片。返回 {ok, new, skipped, msg}。"""
    ok, why = available()
    if not ok:
        return {"ok": False, "new": 0, "msg": why}
    idx = load_index(idx_path)
    import hashlib
    todo = []
    for f in files:
        try:
            h = hashlib.sha256(f.read_bytes()).hexdigest()
        except OSError:
            continue
        if h not in idx:
            todo.append(f)
    if not todo:
        return {"ok": True, "new": 0, "msg": "截图都已识别过"}
    tmp = Path(tempfile.mkdtemp(prefix="ta_ocr_"))
    try:
        src = tmp / "shots"
        src.mkdir()
        for i, f in enumerate(todo):
            shutil.copyfile(f, src / (str(i + 1) + f.suffix.lower()))
        out = tmp / "result.ocr.json"
        env = dict(os.environ, TA_SELF=str(BAT), TA_ARGS='"' + str(src) + '"', TA_OCR_QUIET="1", TA_OCR_OUT=str(out))
        t0 = time.time()
        log("正在识别 " + str(len(todo)) + " 张截图的文字…")
        p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", PS_CMD],
                           env=env, capture_output=True, timeout=TIMEOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not out.exists():
            err = (p.stdout or b"").decode("utf-8", "replace")[-600:] + (p.stderr or b"").decode("utf-8", "replace")[-600:]
            return {"ok": False, "new": 0, "msg": "识别没有生成结果（" + (err.strip() or "退出码 " + str(p.returncode)) + "）"}
        n = merge_result(idx, json.loads(out.read_text(encoding="utf-8-sig")))
        save_index(idx_path, idx)
        bad = sum(1 for f in todo if idx.get(hashlib.sha256(f.read_bytes()).hexdigest(), {}).get("error"))
        return {"ok": True, "new": n, "msg": "已识别 " + str(n) + " 张（用时 " + str(round(time.time() - t0)) + " 秒）" + ("，" + str(bad) + " 张识别失败" if bad else "")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "new": 0, "msg": "识别超过 " + str(TIMEOUT // 60) + " 分钟，已停止"}
    except (OSError, ValueError) as e:
        return {"ok": False, "new": 0, "msg": "识别失败：" + str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    # 手动识别：python scripts/ta_ocr.py <图片或文件夹>...
    fs = []
    for a in sys.argv[1:]:
        p = Path(a)
        fs += [x for x in p.rglob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif")] if p.is_dir() else [p]
    print(run(fs, ROOT / "workspace" / "ocr.json")["msg"])
