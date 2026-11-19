"""公共：配置、批次文件、读文本、规范化。只用 Python 自带的库。"""
from __future__ import annotations

import copy
import datetime
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    # 怎么调用同事A 的脚本
    "a_script": {
        "mode": "method",            # method：导入他的 .py 直接调用对比函数；command：当命令行运行
        "path": "",                  # 他的脚本文件，例如 D:/pdf_compare/compare.py
        "class": "",                 # 类名；留空时自动找含有 method 的那个类
        "init_args": [],             # 创建类时要传的参数
        "method": "policySchedule_compare_file_differences_and_total",
        "kwargs": {"y_tolerance": 0},
        "baseline_is_file1": True,   # file1 传 baseline、file2 传新文件
        "workdir": "",               # 运行时切换到的目录（他的脚本里有相对路径时填他的项目目录）
        "command": "",               # mode=command 时使用，可用 {baseline} {new} {difference} {total} {ignore} {ignore_info} {case_dir}
    },
    # 传给他的四个输出文件名（每个 Case 一个文件夹）
    "outputs": {
        "difference": "difference.html",
        "total": "total.html",
        "ignore": "ignore.html",
        "ignore_info": "ignore_info.txt",
    },
    # baseline 和新文件怎么配对：文件名里用这个正则取出的部分相同就是一对
    "pairing": {"key_regex": r"(Case\s*\d+)", "recursive": False},
    # collect 模式：整理他已经跑好的结果时，按文件名认出是哪种文件（不区分大小写）
    "existing": {"difference": "*difference*", "total": "*total*", "ignore": "*ignore*.htm*", "ignore_info": "*ignore*info*"},
    # 交付物里的差异从哪个文件读、按什么格式读
    "difference": {
        "source": ["difference", "total"],   # 先读 difference，没有再读 total
        "format": "auto",                     # auto | htmldiff | lines | custom
        "old_line": r"^\s*-\s?(.*)$",         # format=lines 时：旧值行
        "new_line": r"^\s*\+\s?(.*)$",        # format=lines 时：新值行
        "custom_parser": "",                  # format=custom 时：自己写的解析文件，里面有 parse(path) -> list[dict]
        "skip_space_only": True,              # 只是空格不同的不放进交付物（索引页里仍可看到）
    },
    "screenshot": {"enabled": True, "scale": 2, "pad": 28, "x_tolerance": 1.5, "y_tolerance": 3},
    "deliver": {"title": "文档变化对比", "word": True, "excel": True, "image_width_cm": 7.8, "excel_image_px": 380},
}


def deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> dict:
    p = Path(path) if path else ROOT / "config" / "dca.json"
    if not p.exists():
        if path:
            raise SystemExit(f"找不到配置文件：{p}")
        return copy.deepcopy(DEFAULTS)
    return deep_merge(DEFAULTS, json.loads(p.read_text(encoding="utf-8-sig")))


def need(mod: str):
    try:
        return __import__(mod)
    except ImportError:
        raise SystemExit(f"缺少 {mod}，请先运行：pip install -r requirements.txt")


def read_text_any(path) -> str:
    """他的 html 可能是 utf-8，也可能是 gbk；按 meta 里的 charset 优先。"""
    raw = Path(path).read_bytes()
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:2000], re.I)
    tries = ([m.group(1).decode("ascii", "ignore")] if m else []) + ["utf-8-sig", "gb18030", "big5"]
    for enc in tries:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def norm(s: str) -> str:
    """比较、定位用：全角转半角、去掉所有空白、小写。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def clean(s: str) -> str:
    return re.sub(r"[ \t\u00a0\u3000]+", " ", (s or "").replace("\u00a0", " ")).strip()


def now_tag() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_") or "case"


def write_json(path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_batch(batch_dir) -> dict:
    p = Path(batch_dir) / "batch.json"
    if not p.exists():
        raise SystemExit(f"{batch_dir} 里没有 batch.json，请先运行 pairs 或 collect")
    return json.loads(p.read_text(encoding="utf-8"))


def save_batch(batch_dir, batch: dict) -> None:
    write_json(Path(batch_dir) / "batch.json", batch)


def rel(path, start) -> str:
    """索引页里的相对链接（统一用 /）。"""
    import os
    try:
        return os.path.relpath(str(path), str(start)).replace("\\", "/")
    except ValueError:      # 不在同一个盘符
        return Path(path).resolve().as_uri()
