【任务 K4c】图谱接口中的中文名和类型名单改为从 SDK 读取；补充 RELATED_TO 的显示。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【本次允许修改的文件】
- src/tap_ai/contracts/library_kg.py
- src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py
- src/tap_ai/application/library_kg.py
- docs/API-文档.md（只改图谱接口那一节）
- tests/unit/test_library_kg_service.py、tests/api/test_library_kg_api.py

【开工前确认（只读，贴原始输出）】
1. contracts/library_kg.py 中 ENTITY_TYPE_ZH、RELATION_ZH 的原文，以及所有使用它们的地方（git grep -n）
2. SDK 的 tap_ingest_sdk/kg_schema.py 中 ENTITY_TYPE_ZH、RELATION_ZH、ENTITY_TYPE_NAMES 的原文
3. 两边的键是否完全一致；不一致的逐个列出

【要做的 4 件事】
1. contracts/library_kg.py：删除手写的 ENTITY_TYPE_ZH、RELATION_ZH，改为从 tap_ingest_sdk.kg_schema 导入（导入写法照抄 sdk_ingest.py）。
   其他文件的引用不用改
2. 类型校验：实体类型的合法名单用 ENTITY_TYPE_NAMES，关系类型的合法名单用 RELATION_ZH 的键
3. subgraph 和 entity/detail 中，RELATED_TO 关系的显示名：raw_types 不为空时用 raw_types 的第一个，否则用"相关"（与 T2 一致，核对一遍）
4. 测试：
   a. 修改前后，每个接口的返回结果相同（用同一组假数据对比）
   b. contracts 中的 ENTITY_TYPE_ZH、RELATION_ZH 与 SDK 中的是同一个对象（is 判断）
   c. 传入 SDK 中没有的实体类型，返回 CCB001

【完成报告】按【通用规则】第五条


## K4c 的验收方法：

1. 全部测试（新窗口，不设环境变量），失败数不比之前多

2. 中文名只剩一份：

```powershell
git grep -n -E "\"产品\"|\"流程\"|\"负责\"" -- src

```

只能在 SDK 导入相关的地方出现，‎`contracts/library_kg.py` 里不能再有

3. 启动后端，在 ‎`/docs` 里用 ‎`jp-poc` 调一次 ‎`overview`，中文名和 T2 时显示的一样