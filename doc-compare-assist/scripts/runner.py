"""对比：调用同事A 自己的脚本，一个 Case 一个文件夹；或者整理他已经跑好的结果（collect）。

不改他的脚本，只是替他逐对调用、把输出放整齐。他脚本里的 print 记到每个 Case 的 run.log。
"""
from __future__ import annotations

import contextlib
import fnmatch
import functools
import importlib.util
import inspect
import os
import subprocess
import sys
import traceback
from pathlib import Path

from pairing import key_of


class _ModuleSelf:
    """他的函数如果写在模块最外层、却带着 self 参数，用这个对象当 self：self.xxx 会找到同一个模块里的 xxx 函数。"""

    def __init__(self, module):
        self._m = module

    def __getattr__(self, name):
        f = getattr(self._m, name)
        return functools.partial(f, self) if callable(f) else f


def load_target(cfg: dict):
    """返回 (可调用的对比函数, 说明)。找不到时抛出 SystemExit，并说明缺什么。"""
    a = cfg["a_script"]
    path = Path(a["path"] or "")
    if not a["path"] or not path.is_file():
        raise SystemExit(f"config/dca.json 里 a_script.path 没填或文件不存在：{a['path'] or '空'}")
    folder = str(path.parent.resolve())
    if folder not in sys.path:
        sys.path.insert(0, folder)            # 他脚本里 import 同目录的其他文件时能找到
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    with _cwd(a.get("workdir") or folder):
        spec.loader.exec_module(mod)
    name = a["method"]
    cls = None
    if a.get("class"):
        cls = getattr(mod, a["class"], None)
        if cls is None:
            raise SystemExit(f"{path.name} 里没有类 {a['class']}；有这些类：{', '.join(classes(mod)) or '无'}")
    else:
        hits = [c for c in classes(mod) if hasattr(getattr(mod, c), name)]
        if len(hits) == 1:
            cls = getattr(mod, hits[0])
        elif len(hits) > 1:
            raise SystemExit(f"有多个类含有 {name}：{', '.join(hits)}，请在 a_script.class 里指定一个")
    if cls is not None:
        if not hasattr(cls, name):
            raise SystemExit(f"类 {cls.__name__} 里没有 {name}")
        obj = cls(*a.get("init_args") or [])
        return getattr(obj, name), f"{path.name} › {cls.__name__}.{name}"
    f = getattr(mod, name, None)
    if f is None:
        raise SystemExit(f"{path.name} 里找不到 {name}（类里、模块里都没有）")
    params = list(inspect.signature(f).parameters)
    if params and params[0] == "self":
        return functools.partial(f, _ModuleSelf(mod)), f"{path.name} › {name}（模块函数，自动补 self）"
    return f, f"{path.name} › {name}"


def classes(mod) -> list[str]:
    return [n for n, v in vars(mod).items() if inspect.isclass(v) and getattr(v, "__module__", "") == mod.__name__]


@contextlib.contextmanager
def _cwd(path):
    old = os.getcwd()
    if path:
        os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def out_paths(case_dir: Path, cfg: dict) -> dict:
    return {k: str((case_dir / v).resolve()) for k, v in cfg["outputs"].items()}


def run_pairs(batch_dir: Path, batch: dict, cfg: dict, log=print) -> None:
    a = cfg["a_script"]
    target = None
    if a["mode"] == "method":
        target, desc = load_target(cfg)
        log(f"调用：{desc}")
    elif not a.get("command"):
        raise SystemExit("a_script.mode 是 command，但 a_script.command 没填")
    todo = [p for p in batch["pairs"] if p["selected"]]
    for i, p in enumerate(todo, 1):
        case_dir = batch_dir / "cases" / p["dir"]
        case_dir.mkdir(parents=True, exist_ok=True)
        paths = out_paths(case_dir, cfg)
        f1, f2 = (p["baseline"], p["new"]) if a.get("baseline_is_file1", True) else (p["new"], p["baseline"])
        log(f"[{i}/{len(todo)}] {p['key']} 对比中……")
        p["error"] = ""
        with open(case_dir / "run.log", "w", encoding="utf-8") as lf:
            try:
                if target is not None:
                    with contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf), _cwd(a.get("workdir")):
                        target(f1, f2, paths["difference"], paths["total"], paths["ignore"], paths["ignore_info"],
                               **(a.get("kwargs") or {}))
                else:
                    cmd = a["command"].format(baseline=f1, new=f2, case_dir=str(case_dir.resolve()), **paths)
                    r = subprocess.run(cmd, shell=True, cwd=a.get("workdir") or None, stdout=lf, stderr=subprocess.STDOUT)
                    if r.returncode:
                        p["error"] = f"命令返回 {r.returncode}，见 run.log"
            except SystemExit as e:
                p["error"] = f"他的脚本退出了（{e.code}），见 run.log"
            except Exception as e:                      # 一个 Case 出错不影响其他 Case
                traceback.print_exc(file=lf)
                p["error"] = f"{type(e).__name__}: {e}"
        p["files"] = found_outputs(case_dir, paths, cfg)
        if not p["error"] and not p["files"].get("difference") and not p["files"].get("total"):
            p["error"] = "没有生成 difference / total 文件；可能他的脚本把结果写到了别处，见 run.log"
        p["status"] = "出错" if p["error"] else "已对比"
        log(f"      {'✗ ' + p['error'] if p['error'] else '✓ 完成'}")


def found_outputs(case_dir: Path, paths: dict, cfg: dict) -> dict:
    """先找我们传过去的文件名；没有的话（他的脚本可能自己加了后缀）按文件名特征在 Case 文件夹里找。"""
    out = {}
    for k, p in paths.items():
        if Path(p).is_file():
            out[k] = p
    rest = [f for f in case_dir.iterdir() if f.is_file() and str(f.resolve()) not in out.values() and f.name != "run.log"]
    for k, pat in cfg["existing"].items():
        if k not in out:
            hit = [f for f in rest if fnmatch.fnmatch(f.name.lower(), pat.lower())]
            if hit:
                out[k] = str(hit[0].resolve())
    return out


def collect(batch: dict, results_dir, cfg: dict, log=print) -> None:
    """整理他已经跑好的结果：在结果文件夹里按文件名认出 difference / total / ignore，按 Case 编号挂到每一对上。"""
    root = Path(results_dir)
    if not root.is_dir():
        raise SystemExit(f"结果文件夹不存在：{root}")
    by_key: dict[str, dict] = {}
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        for k, pat in cfg["existing"].items():
            if fnmatch.fnmatch(f.name.lower(), pat.lower()):
                # Case 编号可能在文件名里，也可能在上一级文件夹名里
                key = key_of(f, cfg["pairing"]["key_regex"])
                if key == f.stem:
                    key = key_of(f.parent, cfg["pairing"]["key_regex"])
                by_key.setdefault(key, {}).setdefault(k, str(f.resolve()))
                break
    n = 0
    for p in batch["pairs"]:
        files = by_key.pop(p["key"], None)
        if files:
            p["files"], p["status"], p["error"] = files, "已对比", ""
            p["selected"] = bool(p["baseline"] and p["new"])
            n += 1
    for key, files in by_key.items():             # 有结果但没找到 PDF 的，也列出来（只是不能截图）
        batch["pairs"].append({"key": key, "dir": key, "selected": True, "note": "没找到对应的 PDF，不能截图",
                               "baseline": "", "new": "", "baseline_all": [], "new_all": [],
                               "files": files, "status": "已对比", "error": ""})
    log(f"认出 {n + len(by_key)} 个 Case 的结果（其中 {len(by_key)} 个没有对应 PDF）")
