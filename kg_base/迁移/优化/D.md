【任务】把 library 模块改名为 kb，并让接口写法和同事的接口保持一致
本阶段只改名、调整接口写法，不改任何业务逻辑。
先做第一步《开工前确认》（只读），贴出原始输出后停下，等我回复"继续"。
每条命令都在 C:\Users\234393\Desktop\tap-ai-backend 目录下运行。

【背景】
- develop 已经合并进当前分支；P2–P4 整改已经提交
- origin/develop 上没有我们的代码。所以 origin/develop 里出现的 library，全部是同事原有的，一律不得修改。
  例如 contracts/prompt_library.py、PromptLibrary、prompts/library.py、DefaultPromptLibrary、default_prompt_library
- 我们新增到 prompt_library.py、prompts/library.py 里的方法和变量，属于我们的，需要改名

【第一步：开工前确认（只读）】逐条贴出原始输出
1. git status --short
2. 同事原有的 library：git grep -n -i "library" origin/develop -- src tests sql .env.example
3. 当前全部的 library：git grep -n -i "library" -- src tests sql .env.example
   用第 3 条减去第 2 条，就是我们要改的部分。按"文件名 / 类名 / 函数和方法名 / 变量和属性名 / 数据库表名 / 配置项和环境变量 / 接口地址 / 测试文件名 / 注释和说明文字"分组列出
4. 同事有没有在用 kb：git grep -n -i -E "\bkb|kb_|Kb[A-Z]|KB_" origin/develop -- src tests sql .env.example
   列出所有已有的 kb 文件名、类名、表名、配置名、接口地址。没有就写"没有"
5. 缩写的大小写习惯：git grep -n -E "class \w*(Llm|LLM|Api|API|Qa|QA|Kg|KG|Rag|RAG|Id|ID)\w*" -- src
   统计同事的类名里，缩写是全大写（LLMClient）还是首字母大写（LlmClient）
6. 同事所有接口的地址前缀：
   git grep -n -E "APIRouter\(|prefix=|include_router" -- src/tap_ai/api src/tap_ai/bootstrap.py
   git grep -n -E "@router\.(get|post|put|delete|patch)\(" -- src/tap_ai/api
7. 同事的接口写法。在同事的接口文件中选两个：chat.py，再加一个有 list/add/update/delete 的。对每个文件贴出：
   - 文件开头的说明注释（前 40 行）
   - router 的定义
   - 一个完整的接口函数
   - 接口里怎么拿到 service（Depends、request.app.state 还是别的方式）
   - 返回值怎么包装
   - 出错时怎么处理
   然后对我们的 api/library_chunks.py、api/library_eval.py 贴出同样的部分，用表格逐项对比，列出所有不一致的地方
8. 改名对照表（这是方案，不修改任何文件）。按下面的规则，列出每一个要改的名字：旧名 → 新名、出现在哪些文件、出现几次
   - 小写 library_ → kb_（文件名、函数名、变量名、表名、配置字段、app.state 上的属性名）
   - 类名中的 Library → 按第 5 条统计出来的习惯，写成 Kb 或 KB，并说明依据
   - 大写 LIBRARY_ → KB_（环境变量）
   - 接口地址：按第 6 条中同事的前缀格式给出新地址，例如同事用 /tap/api/xxx，我们就用 /tap/api/kb/chunks/...、/tap/api/kb/eval/...，逐条列出 19 个接口的旧地址 → 新地址
   - sql/002_create_library_tables.sql → sql/002_create_kb_tables.sql
   - 测试文件 test_library_*.py → test_kb_*.py
   - 注释和说明文字中的"Library"→"KB"
   - 如果第 4 条显示新名字和同事已有的名字重复，把重复的名字标出来，不要自己换名字，等我决定
9. 第 7 条对比中发现的不一致，逐条写出打算怎么改（只限接口写法，不改业务逻辑）
完成第一步后停下

【第二步：修改（等我回复"继续"）】
1. 只改第一步第 8 条对照表里的名字，以及第 9 条我确认过的写法。对照表以外的任何名字、文字都不得改动；origin/develop 里有的 library 一个都不得改
2. 重命名文件只用 Move-Item（例如 Move-Item src/tap_ai/api/library_eval.py src/tap_ai/api/kb_eval.py），不得新建文件后复制内容，不得使用任何 git 写入命令
3. 修改文件内容时，只替换名字本身，不得改变任何一行的缩进，不得重新排版
4. 修改顺序：先改文件名 → import → 类名 → 函数和变量名 → 配置项和 .env.example → sql 文件 → 接口地址 → 测试 → 接口文件开头的接口清单和写法
5. 每个 api 文件开头，按同事的格式写一份接口清单（方法、路径、一句中文说明），和文件中的实际接口一一对应
6. 测试中断言的旧名字、旧地址，改成对照表里的新名字、新地址（这一类修改是允许的，只限改名，断言的其他内容不变）
7. 接口地址只改前缀，接口的方法（GET/POST）和最后一段（/list、/add、/{id} 等）不变

【完成报告】必须贴出原始输出，不压缩、不概括：
1. 残留检查：下面这条应该没有任何输出（意思是：剩下的 library 和 origin/develop 中同事原有的完全一样）
   Compare-Object (git grep -h -i "library" origin/develop -- src tests sql .env.example | Sort-Object) (git grep -h -i "library" -- src tests sql .env.example | Sort-Object)
2. uv run python C:/Users/234393/Desktop/check_chars.py src tests sql .env.example（发现 0 处问题）
3. uv run python -c "import tap_ai.application; print('ok')"
4. uv run pytest tests/unit tests/api -q -p no:warnings -k "kb or route_count"（全部通过）
5. uv run ruff check .（只剩基线的 4 个）
6. uv run ruff format --check，检查所有改过的 kb 文件
7. uv run mypy src（只剩基线的 6 个）
8. git status --short
9. 19 个接口的最终地址列表（从 /openapi.json 或接口文件中列出）
10. 改名对照表：每一行标 ✅ / ❌
全部做完再出报告，中途不用停




我自己验收部分：
git add -A src tests sql .env.example
git diff --cached -M --stat
git diff --cached -M -w --stat

git diff --cached --name-status -M

git commit -m "refactor(kb): library 模块改名为 kb，接口写法对齐"