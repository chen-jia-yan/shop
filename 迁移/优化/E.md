【任务】P5：PR1 的最终自检、API 文档、PR 说明
只读检查为主。唯一允许修改的仓库文件：docs/API-文档.md（只追加 KB 一节，不改动原有内容）。
每条命令都在 C:\Users\234393\Desktop\tap-ai-backend 目录下运行。先做第一步，贴出结果后停下，等我回复"继续"。

【第一步：自检（只读），逐条贴出原始输出】
1. git log --oneline origin/develop.. HEAD
2. git diff --stat origin/develop...HEAD
3. 改动了哪些原有文件，以及原有行有没有被删或被改：
   git diff origin/develop...HEAD --name-status | Select-String "^M"
   对每个 M 文件：git diff origin/develop...HEAD -- <文件> | Select-String "^-[^-]"（应该没有输出；有输出的，逐行说明原因）
4. 开关关闭时，路由和 develop 完全一致：
   uv run python -c "from tap_ai.bootstrap import build_app; a=build_app(); print(sorted(r.path for r in a.routes if hasattr(r,'path')))"
   在 origin/develop 的版本里做同样的统计做不到，所以改为：确认输出中没有任何包含 /kb 的路径，并且 test_route_count_is_stable 通过
5. 开关打开时：先 $env:TAP_AI_KB_ENABLED="true"（变量名以改名后 settings.py 中的实际名字为准），再运行第 4 条的命令，列出所有包含 /kb 的路径，必须正好 19 个，并和前端对接文档中的地址逐条一致
6. 四道检查：uv run ruff check .（基线 4 个）、uv run ruff format --check（所有 kb 文件）、uv run mypy src（基线 6 个）、
   uv run pytest tests/unit tests/api -q -p no:warnings（列出所有失败，逐个标注"基线"或"新增"；新增的必须为 0）
7. uv run python C:/Users/234393/Desktop/check_chars.py src tests sql .env.example；uv run python -c "import tap_ai.application; print('ok')"
8. 安全检查：git grep -n -i -E "jp-poc|api[_-]?key\s*=\s*['\"][A-Za-z0-9]|password\s*=\s*['\"]" -- src tests sql .env.example（不得有真实的密钥、密码或 jp-poc 索引名）
9. git status --short（不得有 others/、docs/PROJECT_MEMORY.md 以外的未跟踪文件）

【第二步（等我回复"继续"）】
1. 在 docs/API-文档.md 末尾追加"KB 知识库管理"一节：格式照抄文档中已有接口的写法；内容以 C:\Users\234393\Desktop\miya\前端对接\KB前端对接文档.md 为准，
   地址和字段要和代码一致，有不一致的先停下来报告
2. 不改文档中原有的任何内容。改完贴出 git diff --stat docs/API-文档.md 和 git diff docs/API-文档.md | Select-String "^-[^-]"（应该没有输出）
3. 在回复中写一份 PR 说明（不写入任何文件），包括：
   - 做了什么：切片审阅、RAG 评估两个功能，19 个接口，5 张表
   - 默认关闭：所有开关默认 False，关闭时不挂载任何路由、不构造任何服务
   - 上线前要做的事：执行 sql/002 建表；配置 TAP_AI_KB_ENABLED、判官模型
   - 本期没做的：三个插座暂未接入，下一个 PR 接入
   - 改动的原有文件清单，以及每个文件只追加了什么
   - 测试情况：新增测试数量；本机 Windows 上已有的失败与本次无关（列出）