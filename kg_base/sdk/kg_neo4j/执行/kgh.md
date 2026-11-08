可以合，而且合完以后，临时的 swagger 和 ‎`kg_api/` 都不用再启动了。我手上没有那 8 个旧接口的具体清单，所以先给你整体做法，再给你一段只读提示词，让 Copilot 把清单整理出来。

1. 整体思路 ￼

```
现在：前端 ──> kg_api/（临时 swagger，直接读 kg.db）
目标：前端 ──> tap-ai-backend /tap/ai/library/kg/*（读 Neo4j，hk 和 jp-poc 都能看）

```

以后端为准，前端改为对接后端。 旧接口能用新接口覆盖的，前端直接换；新接口缺的功能，补到后端里；旧接口里前端用不到的，就不搬了。

不建议在后端再按旧接口的格式做一套「兼容接口」。那样后端会有两套一样功能的接口，还不符合后端的统一写法：只用 GET/POST、错误码放在返回体里、分页格式统一。以后维护会很麻烦。

2. 具体步骤 ￼



|步骤    |做什么                                              |谁做                     |

|------|-------------------------------------------------|-----------------------|

|① 盘点  |列出旧 8 个接口：路径、参数、返回结构、前端哪个页面在用                    |Copilot 只读整理（提示词见第 3 节）|

|② 对照  |旧接口 → 新接口一一对应，标出「可直接替换 / 新接口缺字段 / 新接口缺功能 / 前端不用了」|我根据 ① 的结果出对照表          |

|③ 补缺口 |新接口缺的字段或功能补进后端，仍然只读、带 scope                      |我出提示词，Copilot 做        |

|④ 前端切换|改接口地址、改字段名，接上 scope 切换                           |前端                     |

|⑤ 联调  |用后端自带的接口文档页 `/docs` 测试，前端在开发环境走一遍                |你和前端                   |

|⑥ 下线  |前端全部切完、验证通过后，停用 `kg_api/`，文件夹先留着当备份              |你                      |

前端改起来最省事的办法： 前端加一个转换文件，把后端返回的新格式转成页面现在用的格式，页面组件就不用动。比如后端返回 ‎`nodes`、‎`edges`、‎`type_zh`，转成页面原来用的字段名。以后接口再变，也只改这一个文件。

3. 盘点提示词（只读，先贴【通用规则】） ￼

```
【任务 盘点】只读整理本地 kg_api 的全部接口，以及后端图谱接口，输出对照材料。不修改任何文件。

【只读目录】
- 旧接口：C:\Users\234393\Desktop\kg_api
- 新接口：C:\Users\234393\Desktop\tap-ai-backend 中 src/tap_ai/api/library_kg.py、src/tap_ai/api/dto.py（图谱相关的类）、docs/API-文档.md 图谱那一节

【绝对禁止】
- 不修改、不新建、不删除任何文件（包括 kg_api 和后端仓库）
- 不启动服务；不打开 kg.db；不读取 .env 和任何含密码、密钥的文件
- git 只允许只读命令

【要做的 3 件事】
1. 旧接口清单：kg_api 中每一个路由，列一行：
   | 序号 | 方法 | 路径 | 请求参数（名字、类型、是否必填） | 返回结构（字段名和含义，嵌套的也展开） | 代码位置 文件:行号 |
   另外说明：kg_api 读的是哪个数据文件；有没有分页、筛选、按类型过滤；返回里有没有中文类型名
2. 新接口清单：后端 /tap/ai/library/kg 下 7 个接口，按同样格式列一张表
3. 对照表：每个旧接口一行
   | 旧接口 | 对应的新接口（没有就写"无"） | 字段对应关系（旧字段 → 新字段） | 新接口缺的字段或功能 | 结论：可直接替换 / 缺字段 / 缺功能 / 无对应 |
   只按代码事实填写，不确定的写"不确定"并说明原因，不要猜

【完成报告】三张表原样贴出；最后列出"新接口缺的字段或功能"汇总清单

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据 |
| 1 | | |
| 2 | | |
| 3 | | |

```

4. 和前端对接要讲清的几件事 ￼

T2-补做完之后再交给前端：

1. 地址：开发环境的后端地址 + ‎`/tap/ai/library/kg/...`。本地联调用你自己启动的后端。

2. 接口文档：后端启动后打开 ‎`http://<后端地址>/docs`，就是后端自带的 swagger，取代临时那个。正式说明写在 ‎`docs/API-文档.md`。

3. 调用约定：

 - 7 个接口全部用 POST，请求体是 JSON。

 - 出错时 HTTP 状态码也是 200，要看返回体里的 ‎`code`。

 - 分页统一是 ‎`items / total / page / page_size`。

4. 切换图谱：页面打开时先调 ‎`scopes/list`，之后每个接口都带上 ‎`scope`。‎`has_graph=false` 时提示「暂无实体关系，可在文档列表中查看」。

5. 类型显示：显示用 ‎`type_zh`，筛选时传英文 ‎`type`。‎`RELATED_TO` 的边显示 ‎`label`（具体的关系说法），线条建议弱化。

6. 请求头和跨域：图谱接口和前端现在调用的其他后端接口（比如问答）用同一套方式。前端已经能调通问答，图谱接口一般不用额外处理。如果联调时遇到跨域报错，告诉我。

5. 两点提醒 ￼

- 数据内容基本一致。 旧 ‎`kg_api` 读的是 ‎`kg.db`，新接口里的 jp-poc 是 T1 从同一个 ‎`kg.db` 导进 Neo4j 的。区别是关系名换成了标准英文名，另外带上了中文名，前端看到的内容应该差不多。hk 只有新接口能看到。

- ‎`kg_api/` 不要放进后端仓库。 它和数据打包在一起，下线后在本地留着当备份就行。等 jp-poc 也不用了再删。

把盘点结果发我，我出对照表，并说明哪些缺口要补、怎么补。补的提示词会和 T2-补的结果一起看，避免重复改。





两份报告的代码部分都做完了，也都停在同一个原因上：后端环境里还没装 SDK。SDK 装进去时会一起带上它依赖的 ‎`docx`、‎`openpyxl`、‎`pypdf`，这两个阻塞就都解开了。这一步你自己装，不用再交给 Copilot。

1. 装 SDK（一次解决两边的阻塞） ￼

```powershell
Set-Location C:\Users\234393\Desktop\tap-ai-backend
uv pip install --offline -e C:\Users\234393\fwd-tap-common\fwd-tap-ingest
uv run python -c "import tap_ingest_sdk, docx, pptx, openpyxl, pypdf; print('ok')"

```

- 打印出 ‎`ok` 就装好了。

- 如果提示缓存里缺某个包，去掉 ‎`--offline` 再试一次。还是不行，把提示发我。

2. 装好后你自己补跑验证 ￼

SDK（修K1a-补的验证 a、b）：

```powershell
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
uv run --project C:\Users\234393\Desktop\tap-ai-backend python -m pytest -q tests 2>&1 | Select-Object -Last 15
uv run --project C:\Users\234393\Desktop\tap-ai-backend ruff check src/tap_ingest_sdk/sinks/_neo4j.py tests/test_kg_and_chunk_index.py
uv run --project C:\Users\234393\Desktop\tap-ai-backend python C:\Users\234393\Desktop\cmp_schema.py

```

- 第 1 条要求 0 failed、0 error。

- 第 2 条要求 All checks passed。之前报「缺 ruff」，是因为直接用 ‎`python` 时用的环境不对。加上 ‎`--project` 就会用后端环境里的 ruff。

- 第 3 条就是那段新旧取值对比，要求 8 行都是 ‎`SAME`。

后端（修2 的验证）：

```powershell
Set-Location C:\Users\234393\Desktop\tap-ai-backend
uv run pytest -q 2>&1 | Select-Object -Last 15
uv run pytest -q tests/unit/test_library_kb_ingest_plugin.py tests/api/test_library_kg_api.py 2>&1 | Select-Object -Last 15
git --no-pager diff --stat

```

3. 结果发我之后 ￼

- SDK 三条都通过：按昨晚给的写法，点名添加那 10 个文件，一次提交修1、修1b、修K1a、修K1a-补。

- 后端：我核对 ‎`git diff --stat` 里只有 K2a 和修2 允许改的文件，你再一起提交。全量测试如果还剩失败，我看报错判断是原有问题还是新问题。

- 之后：接着做 K2b 精简版、T2-补，以及前端那份盘点。

修2 的报告里，Copilot 对依赖问题的结论是对的：不是缺 pptx，而是后端根本找不到 SDK。另外，代码只改了允许的文件，同事的问答文件里只碰了 ‎`kg_browse.py`，这两点我都确认过，没问题。





装是装了，问题多半出在 Copilot 跑测试时用的不是这个环境。你不用重装，先跑两条命令确认一下。

先确认是哪种情况 ￼

在后端目录下运行：

```powershell
Set-Location C:\Users\234393\Desktop\tap-ai-backend
.\.venv\Scripts\python.exe -c "import sys, tap_ingest_sdk, docx, pptx; print(sys.executable); print(tap_ingest_sdk.__file__)"
uv run python -c "import sys, tap_ingest_sdk, docx, pptx; print(sys.executable); print(tap_ingest_sdk.__file__)"

```



|结果             |原因                                                                              |怎么办                                                              |

|---------------|--------------------------------------------------------------------------------|-----------------------------------------------------------------|

|两条都正常打印        |SDK 装得没问题，Copilot 用的不是这个环境。修K1a-补的报告里说「缺 ruff」，可后端环境里明明有 ruff，说明它用的是电脑自带的 Python|不用重装，你自己按上一条第 2 节跑验证就行                                           |

|第 1 条正常，第 2 条报错|`uv run` 运行前会按 pyproject 同步环境，可能把手动装的 SDK 清掉了                                   |不让 Copilot 用 `uv run`，测试改用 `.\.venv\Scripts\python.exe -m pytest`|

|两条都报错          |SDK 已经被清掉了。很可能就是某次 `uv run` 同步时清的                                               |重装一次，以后测试都按上一行的写法跑                                               |

还有一种可能：Copilot 那两份报告是在你装 SDK 之前跑的。如果是这样，结果就已经过时了，直接自己重跑验证就行。

之前那个「ok」为什么不能完全说明问题： 修1 把 SDK 改成了用到才导入，所以 ‎`import tap_ingest_sdk` 不会顺带加载 docx、pptx 这些解析器。也就是说，就算这些依赖缺了，它照样会打印 ok。上面的命令把 ‎`docx`、‎`pptx` 也一起导入了，结果才靠得住。

以后让 Copilot 跑测试时 ￼

在提示词的验证部分加上这一句：

```
所有 Python 命令统一用 C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe，先运行
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; print(sys.executable)" 贴出路径；不得使用系统 python。

```

如果确认是 ‎`uv run` 会清掉手动装的 SDK，长期的解决办法是在后端的 pyproject 里正式声明对 SDK 的依赖。这个改动影响部署方式，要先和同事确认线上是怎么装 SDK 的，所以我把它记进「要问同事的」。现在先用 ‎`.venv\Scripts\python.exe` 绕过去就行。