"""ai-dev-kit 的 sitecustomize：只在 AI_DEV_KIT_NODELETE=1 时启用禁删保护。

Python 启动时会自动导入 PYTHONPATH 上第一个 sitecustomize。kit_run.py 和一键验证
只在它们启动的进程里把本目录放到 PYTHONPATH 最前面，所以平时你自己运行 Python 不受影响。

如果项目环境里本来就有 sitecustomize，这里会在启用保护之后接着执行它，不会把它挡掉。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _run_next_sitecustomize() -> None:
    import importlib.util

    for entry in sys.path:
        try:
            if not entry or os.path.abspath(entry) == _HERE:
                continue
            candidate = os.path.join(entry, "sitecustomize.py")
            if os.path.isfile(candidate):
                spec = importlib.util.spec_from_file_location("_kit_chained_sitecustomize", candidate)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                return
        except Exception as exc:
            sys.stderr.write(f"[ai-dev-kit] 执行原有 sitecustomize 失败：{exc!r}\n")
            return


if os.environ.get("AI_DEV_KIT_NODELETE") == "1":
    try:
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        import kit_nodelete

        kit_nodelete.install()
    except Exception as _exc:
        sys.stderr.write(f"[ai-dev-kit] 禁删保护启用失败：{_exc!r}\n")

_run_next_sitecustomize()
