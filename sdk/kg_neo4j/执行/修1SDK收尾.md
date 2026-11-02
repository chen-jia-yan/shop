Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
$py = "C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe"

# ① 只跑和这次改动有关的两个测试文件
& $py -m pytest -q tests/test_lazy_import.py tests/test_kg_schema.py 2>&1 | Select-Object -Last 15

# ② 跳过收集失败的文件，其余测试照常跑
& $py -m pytest -q tests --continue-on-collection-errors 2>&1 | Select-Object -Last 15



# SDK 自己声明了哪些依赖
Select-String -Path C:\Users\234393\fwd-tap-common\fwd-tap-ingest\pyproject.toml -Pattern "pptx|docx|openpyxl|pdf|dependencies"

# SDK 那个坏掉的 .venv 里有没有 pptx
Test-Path C:\Users\234393\fwd-tap-common\fwd-tap-ingest\.venv\Lib\site-packages\pptx

# uv 本地缓存里有没有 python-pptx 的安装包（离线也许能装）
Get-ChildItem (uv cache dir) -Recurse -Directory -Filter "python_pptx*" -ErrorAction SilentlyContinue | Select-Object -First 5 FullName

# 后端是怎么依赖 SDK 的
Select-String -Path C:\Users\234393\Desktop\tap-ai-backend\pyproject.toml -Pattern "tap-ingest|tap_ingest|fwd-tap|pptx"



Set-Location C:\Users\234393\fwd-tap-common
git add fwd-tap-ingest/README.md `
        fwd-tap-ingest/src/tap_ingest_sdk/__init__.py `
        fwd-tap-ingest/src/tap_ingest_sdk/kg_schema.py `
        fwd-tap-ingest/src/tap_ingest_sdk/sinks/_kg_schema.py `
        fwd-tap-ingest/src/tap_ingest_sdk/embeddings/_internal/config.py `
        fwd-tap-ingest/src/tap_ingest_sdk/sinks/_internal/config.py `
        fwd-tap-ingest/tests/test_lazy_import.py
git diff --cached --stat


git commit -m "fix(sdk): 修1 按需导入、清理旧配置名；修1b 解开 kg_schema 循环导入"


git grep -n "TAP_AI_KB_AOAI" -- src README.md