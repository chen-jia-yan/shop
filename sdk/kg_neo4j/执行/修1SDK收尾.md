
|失败的测试                                                             |我的初步判断                                                              |
|------------------------------------------------------------------|--------------------------------------------------------------------|
|`test_neo4j_sink_upsert_passes_now_preview_and_raw_type`          |这是 **K1a 自己新加的测试**，说明 K1a 改的写图逻辑或这个测试本身有问题                          |
|`test_neo4j_sink_drops_relations_outside_whitelist`               |很可能和 K1a 的新设计冲突：以前白名单外的关系是丢掉，现在改成存为 `RELATED_TO`。如果是这样，就该改旧测试，而不是改代码|
|`test_neo4j_sink_upsert_and_delete`                               |要看具体报错                                                              |
|`test_extractor_drops_relations_when_entity_missing_or_type_blank`|测试期望结果为空，实际多出一条 `SFDC → USES → 某个数据实体`，要看测试原文才能判断                   |


一次跑完下面三项，结果存成文件发我 ￼

① 失败详情和测试的修改历史：

[Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8"
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
python -m pytest -q tests/test_kg_and_chunk_index.py tests/test_kg_llm_extract.py --tb=short 2>&1 | Out-File -Encoding utf8 C:\Users\234393\Desktop\sdk_fail.txt
git --no-pager log --oneline -5 -- tests/test_kg_and_chunk_index.py tests/test_kg_llm_extract.py src/tap_ingest_sdk/sinks/_neo4j.py src/tap_ingest_sdk/sinks/_kg_llm_extract.py
git branch --show-current
第一行是解决中文乱码的，报错里那个乱码的实体名就是这个原因。跑完把桌面上的 ‎`sdk_fail.txt` 当附件发我，后面两条命令的输出直接复制。

② 新旧取值对比：

上次运行报错，是因为整段粘进去后换行丢了，PowerShell 收到的是一整行。这次改成先存成文件再运行：

1. 运行 ‎`notepad C:\Users\234393\Desktop\cmp_schema.py`，提示新建文件时选「是」。

2. 把下面内容粘进去，保存。

import subprocess, sys, types
sys.path.insert(0, "src")
raw = subprocess.check_output(["git", "show", "HEAD:fwd-tap-ingest/src/tap_ingest_sdk/kg_schema.py"])
old = types.ModuleType("old_kg_schema")
sys.modules["old_kg_schema"] = old
exec(compile(raw.decode("utf-8"), "old_kg_schema", "exec"), old.__dict__)
import tap_ingest_sdk.kg_schema as new
for name in ["ENTITY_TYPES", "RELATION_TYPES", "ENTITY_TYPE_NAMES", "ENTITY_TYPE_ZH", "RELATION_ZH",
             "TRAVERSABLE_RELATIONS", "SCHEMA_ALLOWED_RELATIONS", "SCHEMA_LLM_RELATION_MAP"]:
    a, b = getattr(old, name, "<missing>"), getattr(new, name, "<missing>")
    print(name, "SAME" if repr(a) == repr(b) else "DIFFERENT")



3. 回到 SDK 目录运行：
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
python C:\Users\234393\Desktop\cmp_schema.py
