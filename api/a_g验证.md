零、她卡住了怎么办 ￼

先看她卡在哪一步：



|现象              |多半的原因                                                            |怎么处理                       |

|----------------|-----------------------------------------------------------------|---------------------------|

|跑 pytest 后一直没有输出|测试**死锁**了：在主事件循环的线程里直接调用 `complete()`，线程在等主循环，主循环又在等线程，谁也动不了     |按 `Ctrl+C` 停掉，把下面的「补充 1」发给她|

|她一直在改测试 g，反复失败  |测试 g 要求用真实 SDK 加内存版写入端。可是内存版写入端不调用关系抽取，只有 Neo4j 写入端才调用，所以怎么写都测不出来|发「补充 2」                    |

|一直在想、在读文件，不动手   |注意力散了                                                            |发「补充 3」，让她只做剩下的部分          |

补充 1（测试卡死）：

```
测试卡死了。按以下要求修正，不改其他内容：
- 调用 complete() 的测试，一律放在 asyncio.to_thread(...) 或 threading.Thread 里调用，不得在事件循环所在的线程里直接调用
- 每个用到 future.result 的地方必须带 timeout；测试里用的 timeout_s 设成 2 秒以内
- 单独跑这个文件确认不卡：& <py> -m pytest -x -vv tests/unit/test_kg_providers.py 2>&1 | Select-Object -Last 30

```

补充 2（测试 g 测不出来）：

```
测试 g 改为：用真实 SDK 把测试文件处理成 ProcessedDocument（与 test_sdk_ingest_success_with_memory_mode_real_sdk 相同的方式），
然后直接调用 _sinks_factory 里构造的那个 relation_extractor(document)，假网关返回一段固定 JSON（实体和关系的两端都必须在实体列表里，否则会被 SDK 丢弃），
断言返回结果里有这条关系。不连 Neo4j，不改原用例。

```

补充 3（继续做剩下的）：

```
继续 K3a，只做还没完成的部分，已完成的不要重做。做完后按【完成报告】输出，并贴出验证 a 到 g 的原始输出和核对表。

```

一、验收前先准备（PowerShell，新开一个窗口） ￼

```powershell
Set-Location C:\Users\234393\Desktop\tap-ai-backend
$py = "C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe"
& $py -c "import sys, tap_ingest_sdk; print(sys.executable)"

```

输出路径里要有 ‎`tap-ai-backend\.venv`，并且不报错。

二、7 条验证命令（a 到 g） ￼



|编号|命令                                                                                                                            |通过标准                       |

|--|------------------------------------------------------------------------------------------------------------------------------|---------------------------|

|a |`& $py -m pytest -q tests/unit/test_kg_providers.py tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 15`|全部 passed，0 failed         |

|b |`& $py -m pytest -q -rf 2>&1 | Select-Object -Last 25`                                                                        |看下面的说明                     |

|c |`& $py -m ruff check src/tap_ai/plugins/ingest tests/unit/test_kg_providers.py tests/unit/test_library_kb_ingest_plugin.py`   |`All checks passed!`       |

|d |`& $py -m mypy src/tap_ai/plugins/ingest`                                                                                     |看下面的说明                     |

|e |`& $py -m ruff format --check src/tap_ai/plugins/ingest/kg_providers.py tests/unit/test_kg_providers.py`                      |`2 files already formatted`|

|f |`git status --short` 和 `git diff --stat`                                                                                      |只能出现允许修改的文件（见第三节）          |

|g |`& $py C:/Users/234393/Desktop/check_chars.py src tests`                                                                      |没有报出问题                     |

b 怎么判断： 加了 ‎`-rf`，最后会列出每个失败用例的名字。

- 失败用例都在这次没碰过的文件里，并且之前就失败过：没问题。

- 只要有失败出现在 ‎`test_kg_providers`、‎`test_library_kb_ingest_plugin`、‎`test_library_kb_worker` 这几个文件里：就是这次改出来的，不能提交。

- 失败数比她报告里的「修改前」多：也不能提交。

d 怎么判断： 如果 ‎`parsers.py` 报的就是原来那 1 个错，那是原有的 Windows 问题，不算。但只要 ‎`kg_providers.py` 或 ‎`sdk_ingest.py` 里有新的报错，就要改。

g 报问题怎么办： 她的开工确认是用繁体字写的（「重點說明」「已確認事實」）。如果代码注释里也混进了繁体字或全角符号，这一条就会报出来。让她把报出的那些行改成简体。

另外，如果改了 ‎`library_kb_worker.py`，再加跑一条：

```powershell
& $py -m pytest -q tests/unit -k "kb_worker" 2>&1 | Select-Object -Last 10

```

三、看代码改动：确认她没越线（都是只读命令） ￼

1. 改了哪些文件

‎`git status --short` 里只允许出现这些：



|文件                                           |要求                     |

|---------------------------------------------|-----------------------|

|`src/tap_ai/plugins/ingest/kg_providers.py`  |新建                     |

|`src/tap_ai/plugins/ingest/sdk_ingest.py`    |修改                     |

|`src/tap_ai/bootstrap.py`                    |修改，只改几行（也可以没改）         |

|`src/tap_ai/application/library_kb_worker.py`|只有在网关没有同步聊天方法时才改，并且只加几行|

|`tests/unit/test_kg_providers.py`            |新建                     |

|`tests/unit/test_library_kb_ingest_plugin.py`|只追加用例                  |

另外，‎`fwd-tap-common` 那一行本来就有，不算她改的。

2. 逐条检查关键点

```powershell
git diff -- src/tap_ai/plugins/extensions src/tap_ai/config

```

要求：什么都不输出。没碰同事的问答插件，也没加开关。

```powershell
git grep -n -E "litellm|asyncio\.run\(|new_event_loop|tap_ai\.core" -- src/tap_ai/plugins/ingest/kg_providers.py

```

要求：什么都不输出。没有直接调用 litellm，没有新开事件循环，也没有引用评估模块。

```powershell
git grep -n "embedding_provider" -- src/tap_ai/plugins/ingest/sdk_ingest.py

```

要求：Neo4j 那一处传入的变量，和 ‎`SdkIngestAdapter(embedding_provider=...)` 用的是同一个变量名，不能在 ‎`_sinks_factory` 里再 ‎`GatewayEmbeddingProvider(...)` 新建一个。

```powershell
git diff --stat

```

要求：‎`library_kb_worker.py` 和 ‎`bootstrap.py` 的改动行数都应该是个位数。如果出现几十行、上百行，说明她格式化了整个文件，或者顺手改了别的地方。这种情况把这两个文件的 diff 发我。

3. 打开 ‎`kg_providers.py` 看三处（不用看懂每一行）：

- 文件开头有中文注释，说明为什么要走模型网关，以及失败时会被 SDK 接住、不中断入库。

- 只要有 ‎`future.result(` 的地方，括号里必须有 ‎`timeout`。

- 如果用的是异步桥接方案：要能找到两处判断，一处是「没有绑定事件循环就报错」，一处是「在主循环所在的线程里调用就报错」。

四、她报告里的两个结论，要特别看 ￼

1. 网关有没有同步的聊天方法。 有的话应该直接用，‎`library_kb_worker.py` 就不该出现在修改列表里。

2. 调用大模型的次数和超时。

 - 如果是一个文档只调用一次，超长部分被截掉：600 秒肯定够。但长文档后半部分的关系会抽不到，这一条记进待办，告诉同事，以后改 SDK。

 - 如果是每个切片调用一次：30 个切片约 150 秒，还够用。但 100 多页的文档有可能超时，到时候再考虑调高 ‎`library_kb_job_timeout_sec`。这次先不改。

五、可能出现的其他问题 ￼



|问题                            |怎么看出来                                                                |怎么解决                                                                               |

|------------------------------|---------------------------------------------------------------------|-----------------------------------------------------------------------------------|

|模型名写死成了某个字符串                  |在 `sdk_ingest.py` 或 `bootstrap.py` 里搜 `model=`，看到的是 `"gpt-..."` 这种字面值|让她改成读取评估模块用的那个配置项，不新增配置项                                                           |

|模型网关没传进去，大模型抽取实际上没启用          |测试 e 只判断了「不为空」。如果网关是空的，她可能悄悄降级成只用规则抽取                                |看测试 e 是否断言了 `GatewayChatProvider` 收到的网关就是假网关对象。没有的话让她补上                            |

|`bind_loop` 没有被调用（异步桥接方案才有）   |测试都过了，但真实运行时日志里出现「未绑定事件循环」                                           |检查 worker 启动方法里有没有那一行；这在 kg-test 真实上传时才能看出来                                        |

|测试偶尔失败、偶尔通过                   |连续跑 3 次 a，结果不一样                                                      |一般是测试的超时设得太短，或者线程没等结束。让她把等待改成 `join(timeout)` 加断言                                  |

|mypy 报 `Neo4jGraphSink` 参数类型不对|命令 d 报错                                                              |SDK 的导入本来就带 `# type: ignore[import-untyped]`，不允许再新加 `type: ignore`。让她按 SDK 的签名把类型写对|

六、全部通过以后 ￼

1. 提交前检查

```powershell
git add src/tap_ai/plugins/ingest/kg_providers.py src/tap_ai/plugins/ingest/sdk_ingest.py tests/unit/test_kg_providers.py tests/unit/test_library_kb_ingest_plugin.py

```

如果改了 ‎`bootstrap.py` 或 ‎`library_kb_worker.py`，把它们也加上。然后看一下：

```powershell
git diff --cached --stat

```

确认里面没有 ‎`fwd-tap-common`，再提交：

```powershell
git commit -m "feat(kb): 入库时图谱写入端抽取实体关系并生成实体向量，统一走模型网关"

```

2. 先不做真实上传。 单元测试只能证明代码接对了。真正有没有写进实体和向量，要等测试索引 ‎`kg-test` 准备好以后，在本地上传一个文件，再到 Neo4j 里只读查询：

```cypher
MATCH (e:Entity {scope:'kg-test'}) RETURN count(e) AS 实体数, count(e.embedding) AS 有向量的实体数

```

两个数都大于 0，才算 K3a 真正跑通。