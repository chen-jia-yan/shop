# 常见环境报错和真正的原因

| 报错原文（关键部分） | 常见真正原因 | 先做什么 |
|---|---|---|
| `ModuleNotFoundError: No module named 'x'` | 当前环境没装；或者跑错了环境（用了系统 Python 而不是 uv run） | 运行 kit_env.py scan 看是“未声明”还是“已声明没同步” |
| `ImportError: cannot import name 'X' from 'm'` | 循环导入；或者名字被改了 / 删了 | 单独 `python -c "import m"` 看第一个报错；grep 这个名字 |
| `'uv' is not recognized as an internal or external command` | uv 没装或不在 PATH | 装 uv 后重开终端 |
| `The term 'x' is not recognized as the name of a cmdlet` | PowerShell 里找不到命令 | 同上；确认是不是要在虚拟环境里运行 |
| `pydantic ... Field required [type=missing]` 上一行是字段名 | 配置项没设置 | 只把字段名告诉用户，让用户在 .env 里确认 |
| `KeyError: 'SOME_KEY'`（来自 os.environ） | 环境变量没设置 | 同上 |
| `requires a different Python: 3.x not in '>=3.y'` | Python 版本不符合 | 用符合 requires-python 的解释器重建环境 |
| `No matching distribution found for x` | 内网源里没有、包名写错、版本太新 | 先找本地 .whl；确认包名 |
| `SSL: CERTIFICATE_VERIFY_FAILED` | 公司代理证书 | 配置证书或用内网源，问用户公司的做法 |
| `Permission denied` / `Access is denied` | 文件被占用、没有权限、杀毒软件拦截 | 关掉占用的程序；不要用管理员权限硬来 |
| `UnicodeDecodeError` 读取文件时 | 文件是 UTF-16 或 GBK（PowerShell 写出来的） | 用 check_chars.py 查编码，改成 UTF-8 |
| `sqlalchemy.exc.OperationalError: (2006, 'MySQL server has gone away')` | 连接超时、包太大、长时间不用的连接 | 不是缺包；按 /kit-debug-bug 查连接池配置 |

## 一次修完的检查顺序
1. 解释器和环境对不对（`uv run python -c "import sys; print(sys.executable)"`）
2. 依赖是否同步（pyproject 声明的都装上了吗）
3. 额外缺的包（未声明的）
4. 命令行工具
5. 配置名
6. 版本
全部列完再动手。
