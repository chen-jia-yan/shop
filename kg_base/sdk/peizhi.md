① env_local.bat：所有真实配置只放在这一个文件里
@echo off
set "TAP_AI_DATABASE_URL=mysql+asyncmy://用户名:密码@主机:3306/tap_ai?charset=utf8mb4&ssl=true&ssl_ca=C:/certs/mysql-ca.pem"
set "TAP_AI_STORAGE_MOUNT_DIR=C:\Users\234393\tap_local_storage"
set "TAP_AI_REDIS_URL=redis://127.0.0.1:6379/0"
set "TAP_AI_LITELLM_BASE_URL=http://127.0.0.1:4000"
set "TAP_AI_LITELLM_API_KEY=test-dummy-key"
set "TAP_AI_KB_ENABLED=false"
set "TAP_AI_LIBRARY_ENABLED=true"
set "TAP_AI_LIBRARY_KB_ENABLED=true"
set "TAP_INGEST_SDK_NO_AUTOLOAD_ENV=1"


② check_db.py：只执行 SELECT 1 和查表名，不改任何数据
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["TAP_AI_DATABASE_URL"])
    async with engine.connect() as conn:
        print("SELECT 1 =", (await conn.execute(text("SELECT 1"))).scalar_one())
        rows = (await conn.execute(text("SHOW TABLES LIKE 'library%'"))).fetchall()
        print("tables =", [r[0] for r in rows])
    await engine.dispose()


asyncio.run(main())


③ check_db.bat
@echo off
call C:\Users\234393\Desktop\private\env_local.bat
cd /d C:\Users\234393\Desktop\tap-ai-backend
uv run --no-sync python C:\Users\234393\Desktop\private\check_db.py
pause



测域名能否联通
Test-NetConnection mysql-tap-cn3-dev-ctc.mysql.database.chinacloudapi.cn -Port 3306

| 方案 | 什么时候用 | 地址怎么写 |
|---|---|---|
| **A. 用域名** | 上面的 `TcpTestSucceeded : True` | 主机写 `mysql-tap-cn3-dev-ctc.mysql.database.chinacloudapi.cn`，和 `.env.example` 一样 |
| **B. 改 hosts 文件** | A 连不上，但你有管理员权限。同事说的"没改 host"指的就是这个 | 以管理员身份打开记事本，编辑 `C:\Windows\System32\drivers\etc\hosts`，末尾加一行 `10.22.172.246 mysql-tap-cn3-dev-ctc.mysql.database.chinacloudapi.cn`，然后照方案 A 写 |
| **C. 用 IP** | 没有管理员权限 | 主机写 `10.22.172.246`，地址末尾再加 `&ssl_check_hostname=false`（证书上是域名，用 IP 连会对不上，所以要关掉这项检查） |


| 报错里有这些字 | 原因 | 怎么办 |
|---|---|---|
| `Can't connect`、`timed out`、`getaddrinfo` | 网络不通，或域名解析失败 | 换方案 B 或 C |
| `hostname` 、`doesn't match` | 用了 IP，没关主机名检查 | 用方案 C，加上那个参数 |
| `certificate verify failed`（不含 hostname） | 证书文件不对或路径错误 | 检查证书路径，问同事要正确的 CA 证书 |
| `insecure transport` | SSL 参数没生效 | 检查 `ssl=true&ssl_ca=` 有没有写错 |
| `Access denied` | 账号或密码不对，或特殊字符没编码 | 检查编码 |
| `unexpected keyword` | 驱动不认识某个参数 | 截图发我，打码后发 |




本地启动，测 6 个接口（阶段 A）
新建 run_backend.bat：

@echo off
call C:\Users\234393\Desktop\private\env_local.bat
cd /d C:\Users\234393\Desktop\tap-ai-backend
uv run --no-sync uvicorn tap_ai.main:app --port 9006
pause


冲突
| 包 | SDK 要求 | 后端当前版本 | 结论 |
|---|---|---|---|
| Pillow | `>=10,<11` | 12.3.0 | ❌ 改成 `>=11.1,<13` |
| pypdf | `>=4,<5` | 6.20.1 | ❌ 改成 `>=5.1,<7` |
| openai | `>=1,<2` | 2.54.0（litellm 带进来的） | ❌ 改成 `>=1.0,<3` |
| azure-search-documents | `>=11.6,<12` | 12.0.0 | ❌ 改成 `>=11.6,<13` |
| paddleocr | 必装 | 后端没有 | ⚠️ 移到可选依赖 `ocr = [...]` |
| click、pydantic、python-dotenv、openpyxl、neo4j | — | 都在 SDK 的范围内 | ✅ |
| python-pptx、azure-identity | — | 后端没有，属于新增 | ✅ 不冲突 |


本地试装（明天第 4 步，你自己操作
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git checkout -b feat/relax-deps-for-backend



用 VS Code 打开 pyproject.toml，按上面的表修改这 4 行，再把 paddleocr 那一行剪切到 [project.optional-dependencies] 下面，新建一个分组：
ocr = [
    "paddleocr (>=2.7,<3.0.0)",
]


先别急着装。 第四节 R1 调研会确认"不装 paddleocr 时导入 SDK 会不会直接报错"。如果会报错，这一步就交给同事改代码。如果不会，接着做：
Set-Location C:\Users\234393\Desktop\tap-ai-backend
uv pip install -e C:\Users\234393\fwd-tap-common\fwd-tap-ingest
uv run --no-sync python -c "import tap_ingest_sdk; print('sdk ok')"