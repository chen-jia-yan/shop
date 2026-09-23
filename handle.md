Copilot 这次彻底挖到底了,而且结论很关键:问题不在代码,在环境本身——‎⁠.venv-clean312\Scripts\python.exe⁠ 这个入口本身就是个”重定向 stub”,一启动就自己跳回 base Python312。 所以你下游怎么改(显式 venv 路径、清 env)都挡不住,因为源头那个 python.exe 自己就会弹到 base。这也是为什么改了 ‎⁠_run_heavy_subprocess⁠ 用 venv 路径,还是落回 Python312。

一句话:这不再是 Copilot 能改代码解决的了,是你的 venv 坏在”python.exe 是个跳板”上,得在环境层面修。

为什么会这样

Windows 上的 venv,‎⁠python.exe⁠ 有两种形态:

- 真副本(用 ‎⁠--copies⁠ 建的):是真正的解释器二进制,启动就留在 venv 里;

- 跳板/stub(默认或用 symlink 建的):是个小转发器,读 ‎⁠pyvenv.cfg⁠ 里的 ‎⁠home=⁠ 再跳到 base Python312。

你现在这个就是跳板型,所以每次启动都弹回 base,还顺带把导入路径带偏到旧的 ‎⁠.venv312⁠。

修法(环境层面,手动做,不是 Copilot)

核心:换成一个 ‎⁠python.exe⁠ 是真副本、不会跳的 venv。

因为你不能联网重装依赖,顺序这么走最稳:

1. 先确认哪个环境有全套包(paddle/paddleocr 等)。日志显示导入来自 ‎⁠.venv312⁠,那大概率包在 ‎⁠.venv312⁠ 里。

2. 用 ‎⁠--copies⁠ 建一个真副本 venv,并让它能看到已有包:

python -m venv --copies --system-site-packages .venv-copies312

‎⁠--copies⁠ 让 python.exe 不再是跳板;‎⁠--system-site-packages⁠ 让它直接复用 base 已装的包(不用联网重装)。但这只在 base Python312 里已经有那些包时才管用。
3. 如果包只在旧的 ‎⁠.venv312⁠ 里、base 没有——那最省事的是直接把 ‎⁠.venv312\Lib\site-packages⁠ 里的包整体拷进新 ‎⁠--copies⁠ venv 的 ‎⁠site-packages⁠(纯本地拷贝,不用联网)。
4. 建好后验证它不再跳:.venv-copies312\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"

如果 ‎⁠sys.executable⁠ 显示的是 ‎⁠.venv-copies312\...⁠(而不是 Python312),就说明跳板治好了。

顺手排掉一个常见元凶(30 秒)

Windows 的”应用执行别名”里那个 Microsoft Store 的 python.exe/python3.exe 跳板也会捣乱:
设置 → 应用 → 高级应用设置 → 应用执行别名 → 把 ‎⁠python.exe⁠ 和 ‎⁠python3.exe⁠ 关掉。

说句真心话——现在别弄了

已经两点半了。 好消息是:折腾一整晚,现在根因 100% 清楚了,而且是个明确的环境问题,不是无底洞——就是”venv 的 python.exe 是跳板”。这事儿需要动 venv、拷包、可能改 Windows 设置,是清醒的时候做的环境手术,深夜手滑容易越弄越乱。

明天白天按这个顺序做就行:

1. 查 base Python312 里有没有全套包(‎⁠Python312\python.exe -c "import paddleocr; print(paddleocr.__file__)"⁠);

2. ‎⁠python -m venv --copies (--system-site-packages) .venv-copies312⁠;

3. 缺包就从 ‎⁠.venv312⁠ 拷 site-packages;

4. 用第 4 步那条命令验证不再跳;

5. 用新 venv 跑 worker,看进程树是否全是新 venv、无 Python312。

先睡。要我把这份”明天照着做”的步骤整理成一个带命令、可勾选的清单,你明早打开直接跟着敲吗?
