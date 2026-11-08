类型清单直接读 SDK 里的类型定义 ‎`kg_schema`，不查 Neo4j。入库写图用的也是这份定义，后端其他地方显示的中文名也来自它，所以三处始终一致。

设计 ￼



|项  |定的值                                                       |原因                                                 |

|---|----------------------------------------------------------|---------------------------------------------------|

|路径 |`POST …/types/list`，前缀和 `stats` 相同                        |图谱模块的列表接口都用 POST                                   |

|请求体|不需要                                                       |清单是固定的，跟租户无关。前端照常带 `saas_id` 那一套也没关系，后端不读          |

|返回 |`entity_types`、`relation_types` 两个列表，每项是 `{type, type_zh}`|`type` 就是过滤时 `entity_types`/`relation_types` 参数要传的值|

|数量 |不返回                                                       |按前端的要求，他自己统计                                       |

字段名用 ‎`type_zh`，不用 ‎`zh`：节点、边和 ‎`stats` 里都已经叫 ‎`type_zh`，统一后前端只需要记一个名字。你转告他一声就行；如果他坚持要 ‎`zh`，把下面代码里的 ‎`type_zh` 全部替换成 ‎`zh` 即可。

返回示例（具体类型以 SDK 里的定义为准）：

```json
{
  "entity_types": [{"type": "System", "type_zh": "系统"}, {"type": "Process", "type_zh": "流程"}],
  "relation_types": [{"type": "USES", "type_zh": "使用"}, {"type": "RELATED_TO", "type_zh": "相关"}]
}

```

第 0 步：先确认 SDK 里有这三个名字 ￼

```powershell
Set-Location C:\Users\234393\Desktop\tap-ai-backend
.\.venv\Scripts\python.exe -c "from tap_ingest_sdk.kg_schema import ENTITY_TYPE_NAMES, ENTITY_TYPE_ZH, RELATION_ZH; print(ENTITY_TYPE_NAMES); print(ENTITY_TYPE_ZH); print(RELATION_ZH)"

```

正常会打印出三行内容。如果报 ‎`ImportError`，说明装的 SDK 不是新版本，把报错发给我，先不要粘代码。

第 1 处：‎`src/tap_ai/contracts/library_kg.py` ￼

导入：这个文件里如果已经有 ‎`from tap_ingest_sdk.kg_schema import ...`，就把 ‎`ENTITY_TYPE_NAMES` 加进那一行，不要再写第二条导入。如果还没有，就在文件顶部的导入区加上：

```python
from tap_ingest_sdk.kg_schema import (  # type: ignore[import-untyped]
    ENTITY_TYPE_NAMES,
    ENTITY_TYPE_ZH,
    RELATION_ZH,
)

```

函数：放在文件末尾。如果文件里有 ‎`__all__`，把 ‎`"list_kg_types"` 也加进去。

```python
# 结构关系（实体→切片、文档→切片），不是业务关系，不出现在过滤面板里。
_STRUCTURAL_RELATIONS = frozenset({"MENTIONED_IN", "HAS_CHUNK"})


def list_kg_types() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """返回过滤面板用的类型清单，每项是 (英文类型, 中文名)。

    清单只来自 SDK 的 kg_schema，与入库写图用的是同一份定义；
    顺序按 SDK 中的定义顺序。数量由前端按已加载的数据自己统计。
    """
    entity_types = [(str(t), str(ENTITY_TYPE_ZH.get(t, t))) for t in ENTITY_TYPE_NAMES]
    relation_types = [
        (str(t), str(zh)) for t, zh in RELATION_ZH.items() if t not in _STRUCTURAL_RELATIONS
    ]
    return entity_types, relation_types

```

第 2 处：‎`src/tap_ai/api/dto.py` ￼

放在其他图谱类（‎`Kg` 开头的类）旁边。如果相邻的类继承的不是 ‎`BaseModel`，而是项目自己的基类，就照它们的写法改。

```python
class KgTypeItem(BaseModel):
    """过滤面板的一个类型选项。"""

    type: str = Field(description="英文类型，过滤时传它")
    type_zh: str = Field(description="中文名，显示用；没有中文时等于 type")


class KgTypeListData(BaseModel):
    """过滤面板的类型清单（不含数量，数量由前端统计）。"""

    entity_types: list[KgTypeItem] = Field(description="实体类型，对应过滤参数 entity_types")
    relation_types: list[KgTypeItem] = Field(description="关系类型，对应过滤参数 relation_types")

```

第 3 处：‎`src/tap_ai/api/library_kg.py` ￼

把 ‎`KgTypeItem`、‎`KgTypeListData` 加进这个文件已有的 ‎`from tap_ai.api.dto import (...)` 里，再加一行：

```python
from tap_ai.contracts.library_kg import list_kg_types

```

路由放在 ‎`stats` 路由后面：

```python
@router.post("/types/list", response_model=KgTypeListData)
async def list_kg_type_options() -> KgTypeListData:
    """过滤面板的类型清单：只有英文类型和中文名，不含数量。

    清单固定来自 SDK 的类型定义，不查图谱，所以不需要 scope / saas_id；
    前端照常带请求体也可以，会被忽略。
    """
    entity_types, relation_types = list_kg_types()
    return KgTypeListData(
        entity_types=[KgTypeItem(type=t, type_zh=zh) for t, zh in entity_types],
        relation_types=[KgTypeItem(type=t, type_zh=zh) for t, zh in relation_types],
    )

```

函数名特意没叫 ‎`list_kg_types`，是为了不和导入进来的同名函数冲突。

第 4 处（可选）：测试，追加到 ‎`tests/unit/test_library_kg_service.py` 末尾 ￼

这是一个纯函数测试，不连数据库：

```python
def test_list_kg_types_excludes_structural_and_has_zh() -> None:
    from tap_ai.contracts.library_kg import list_kg_types

    entity_types, relation_types = list_kg_types()
    assert entity_types and relation_types
    rel_names = {t for t, _ in relation_types}
    assert "MENTIONED_IN" not in rel_names
    assert "HAS_CHUNK" not in rel_names
    assert all(zh for _, zh in entity_types + relation_types)

```

粘贴完后检查 ￼

```powershell
.\.venv\Scripts\python.exe -m ruff check src/tap_ai/contracts/library_kg.py src/tap_ai/api/dto.py src/tap_ai/api/library_kg.py
.\.venv\Scripts\python.exe -m ruff format src/tap_ai/contracts/library_kg.py src/tap_ai/api/dto.py src/tap_ai/api/library_kg.py
.\.venv\Scripts\python.exe -m mypy src/tap_ai/contracts/library_kg.py src/tap_ai/api/library_kg.py
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_library_kg_service.py

```

这几个文件本来就是这个分支改过的，所以可以执行 ‎`ruff format`。然后在 swagger 里找到 ‎`types/list`，点 Try it out，再点 Execute，确认能返回上面那样的两个列表。

要告诉前端的两点 ￼

1. 库里可能有清单之外的类型。 jp-poc 是旧 POC 导入的数据，个别节点的类型可能不在 SDK 的定义里。前端统计数量时，如果遇到清单里没有的类型，直接用节点自带的 ‎`type_zh` 显示（找不到中文时它就等于英文名），不会出现空白。

2. 勾选项就用 ‎`type` 的值，原样放进 ‎`graph/overview` 等接口的 ‎`entity_types`/‎`relation_types` 参数里。全部取消勾选时不要调接口，传空列表会返回 422。

另外，‎`docs/API-文档.md` 的图谱那一节记得补一条 ‎`types/list`，写清请求（无参数）和上面的返回示例就够了