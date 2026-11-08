【任务】生成《KB 知识库管理 前端对接文档》
本任务只读仓库代码，不修改仓库中的任何文件。唯一允许新建的文件是：
C:\Users\234393\Desktop\miya\前端对接\KB前端对接文档.md（UTF-8，用编辑工具创建，文件夹不存在就先创建）
每条命令都在 C:\Users\234393\Desktop\tap-ai-backend 目录下运行。

【资料来源】先读完以下内容再写文档：
1. docs/API-文档.md：通用约定、成功和失败的响应格式、请求头、认证方式
2. src/tap_ai/api/conversations.py 及其请求模型：租户字段（名称、类型、是否必填）、分页字段（默认值、范围）
3. 同事所有接口的前缀：git grep -n -E "APIRouter\(|prefix=" -- src/tap_ai/api
4. 我们的代码：contracts/library.py、api/dto.py 中的 Library* / ChunkDraft* / GoldSet* / GoldQuestion* / EvalRun* / EvalItem* / EvalAnalysis* 类、
   api/library_chunks.py、api/library_eval.py、application/library_chunks.py、application/library_eval.py、core/library_eval/analyzer.py
【硬性要求】
- 每个字段名、类型、默认值、取值范围、报错文字都必须来自代码或 docs/API-文档.md，不得编造。代码里找不到的，写"待确认"
- 接口地址写最终地址：按第 3 条同事的前缀格式，把我们现在的 /tap/ai/library 换成"同事的前缀格式 + /kb"。
  例如同事用 /tap/api/xxx，就写 /tap/api/kb/...（切片审阅）和 /tap/api/kb/eval/...（评估）。
  接口的方法（GET/POST）和最后一段（/list、/add、/{id} 等）保持和代码一致
- 文档里不出现 Python 类名，只写 JSON 字段

【文档结构】
一、概述
  - 两个功能：切片审阅、RAG 评估，各一段话说明用途
  - 当前状态表：每个接口一行，写"可联调"或"暂时返回 xxx 错误"。
    判断依据：三个插座（QaAnswerPort、ChunkSourcePort、ChunkPublishPort）目前注入的都是 None，依赖它们的接口会返回"问答服务未配置"、"切片数据源未配置"、"落库服务未配置"；
    只依赖数据库的接口（评估集、草稿等）在开发环境建表、打开开关后即可联调
  - 文档开头注明：接口地址为最终地址；后端目前还在改名，字段名不会再变
二、通用约定
  - 接口前缀；方法规则（GET 查详情，其余用 POST）
  - 成功、失败的响应格式和示例（照抄 docs/API-文档.md）
  - 出错时 HTTP 状态码仍是 200，要看响应里的 code；业务错误的 code 是 CCB001
  - 分页：请求的 page、page_size（默认值、范围），返回的 items、total、page、page_size
  - 租户字段：列出名称、类型、是否必填、说明，并注明每个 POST 请求都要带
  - 时间：毫秒时间戳
  - ID 格式：草稿、评估集、任务、题目的 id 长什么样（从 models.py 的默认值函数看）；
    file_id 形如 doc::1a2b3c4d5e6f7a8b，含冒号，放进 GET 路径时要用 encodeURIComponent 编码
  - 请求头和认证（照抄 docs/API-文档.md，没有就写"无"）
三、接口总表：编号 | 方法 | 地址 | 用途 | 对应的页面操作 | 当前状态
四、每个接口的详情（19 个，每个一节）：
  - 请求字段表：字段 | 类型 | 必填 | 默认值 | 取值范围 | 说明
  - 返回 data 的字段表：同上格式，嵌套对象要展开
  - 请求示例 JSON、成功返回示例 JSON
  - 可能返回的错误：从 application 代码中找出这个接口实际可能抛出的 message，逐条列出
五、枚举值（每个值 + 中文显示名）：
  answer_mode、evidence 的 kind、草稿切片的 origin、草稿状态、评估任务状态、评估题目状态、
  category（8 个值，附 analyzer.py 中 SUGGESTIONS 的原文）、评分维度（4 个，1–5 分）
六、状态和按钮：
  - 草稿：每种状态下"修改 / 提交 / 删除"能不能用（按 application 代码的实际判断写）
  - 评估任务：每种状态下"取消 / 查看结果 / 查看分析"能不能用
七、典型操作流程（按步骤写，每步写调哪个接口）：
  - 切片审阅：选文件 → 看切片 → 创建草稿 → 编辑（修改、新增、删除切片）→ 保存 → 提交落库 → 查看结果
  - 评估：导入评估集 → 查看题目 → 发起评估 → 查进度 → 看结果（按类别筛选）→ 看单题详情 → 看分析
  - 进度查询：建议每 3 秒调一次 GET 任务详情，进度 = done / total；状态变成 succeeded / failed / cancelled / interrupted 时停止查询
八、数量和长度限制：各字段的上限（例如草稿切片 0–5000 条、评估集题目 1–1000 条、名称 1–128 字）
九、待确认问题清单：文档中所有标了"待确认"的地方，加上下面几条：
  - 评估集导入：前端读 Excel/JSONL 文件后转成 JSON 再提交，还是后端提供文件上传接口
  - 租户字段的值从哪里取
  - operator（操作人）由前端传，还是后端从登录信息中取
  - 开发环境什么时候建表、打开开关

【完成后】在回复中贴出：
1. 文档里 19 个接口的地址列表
2. 所有标了"待确认"的地方
3. 第 3 条 grep 的原始输出（用来核对前缀）