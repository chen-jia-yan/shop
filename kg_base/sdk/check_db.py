import asyncio

import uvicorn

# 仅本机 Windows 使用：asyncmy 在 Proactor 事件循环下建立 SSL 连接会报 WinError 87，
# 所以由这里直接创建 Selector 事件循环来运行 uvicorn，不让 uvicorn 自己选择
config = uvicorn.Config("tap_ai.main:app", host="127.0.0.1", port=9006, loop="none")
server = uvicorn.Server(config)

with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
    runner.run(server.serve())
    
    
Select-String -Path C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\ingest\sdk_ingest.py -Pattern "password|\*\*\*\*" -Context 2,2

这里显示的 ****** 是 Copilot CLI 的脱敏显示，不是文件的真实内容。这一段由我手动处理：
1. 不要修改 Neo4jGraphSink(...) 构造调用所在的那几行，也不要对这几行使用 Edit
2. 其余 K9a 修订内容照常完成
3. 如果这一段需要改动（例如改为传入共享 driver），在完成报告中写出你建议的完整代码（password 参数写成 password=<配置变量名>，用变量名，不写值），我手动修改
4. 完成报告中说明哪些测试依赖这一段；我改完以后再运行测试


uv run --no-sync pytest tests/unit/test_library_kb_ingest_plugin.py -v -p no:warnings