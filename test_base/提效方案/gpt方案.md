根据这三个补充信息，我会调整两个模块的技术方案。尤其是 Jira 是 Data Center / Server，而不是 Cloud，这会影响 API 接口、认证方式、附件上传、字段映射和部署架构。

目前的情况是：

| 项目    | 已知情况                      | 对技术方案的影响                                     |
| ----- | ------------------------- | -------------------------------------------- |
| 同事 A  | 暂时无法提供原始报告                | 先设计通用解析架构，不能假定现有 HTML 的 DOM 结构               |
| 同事 B  | Jira Data Center / Server | 优先采用 Jira Server/DC REST API，不按 Cloud API 开发 |
| 自动化框架 | 暂时不清楚                     | 先设计框架无关的失败数据标准，再通过适配器接入实际框架                  |

我会采用一个核心原则：

先把数据采集、解析、规则判断、AI 分析、人工审核、外部系统操作拆开。

这样即使以后发现 A 的报告格式特殊，或者 B 实际使用的是 Selenium、自研框架，而不是 Playwright，也不需要推翻整个系统。

下面给你一份可以交给开发人员进行技术评审和拆分任务的实施设计。

# 一、整体技术架构：不要把它做成两个独立的 AI 聊天机器人

我建议采用一个统一的 Testing Intelligence Platform，内部包含两个业务模块和一组公共基础服务。

## Testing Intelligence Platform

企业级测试辅助平台 · 建议架构

统一工作台 Web UI

批次管理 · 文件导入 · 失败分析 · 差异对比 · 审核 · Jira

Module A

Regression Intelligence

报告解析、Diff、Ignore 规则、变化分析、批次汇总

Module B

Failure Intelligence

失败采集、聚类、分类、根因辅助分析、Jira 草稿

公共业务服务

文件解析服务

规则引擎

Agent / LLM 服务

历史知识检索

任务队列

审核与审计

数据与系统集成层

文件存储 · PostgreSQL · Jira DC REST API · 测试框架 Adapter · 日志系统

## 技术选型建议

我不会为了追求“最新 AI 技术”而把所有东西都换成 Agent。

| 层级      | 建议技术                              | 选择理由                      |
| ------- | --------------------------------- | ------------------------- |
| 前端      | React + TypeScript                | 适合复杂批次、表格、左右差异视图          |
| 后端      | Python + FastAPI                  | 文件处理、数据分析、AI 集成生态成熟       |
| 异步任务    | Celery + Redis，或企业已有消息队列          | 处理 140 份报告、40 个失败 Case    |
| 数据库     | PostgreSQL                        | 保存批次、差异、规则、分析、审核和 Jira 记录 |
| 文件存储    | 企业批准的共享存储或对象存储                    | 保留 PDF、HTML、截图、日志原件       |
| PDF 解析  | PyMuPDF / pdfplumber              | 文本、页码、坐标提取                |
| HTML 解析 | BeautifulSoup / lxml              | 解析现有 HTML 结构              |
| 文本比较    | difflib，必要时引入专门 Diff 算法           | 确定性比较                     |
| 浏览器自动化  | Playwright Adapter（确认后启用）         | 弹窗和浏览器事件采集                |
| AI      | 企业批准的 LLM 服务                      | 变化解释、失败分类、根因候选            |
| 知识检索    | PostgreSQL + pgvector 或企业已有向量检索服务 | 检索历史案例                    |
| Jira 集成 | Jira Data Center REST API         | 创建、查询、附件和状态回传             |

这套选型不是要求全部新建。如果公司已有 PostgreSQL、Redis、Azure、内部文件存储、日志平台或模型网关，优先复用已有平台，减少运维和安全审批成本。

# 二、先做技术摸底：开发前必须确认的 6 件事

这一步很重要。因为你现在还没有 A 的样本，也不知道 B 的自动化框架。不能把未知信息当成已知条件，直接开始写代码。

我会先安排一次短周期技术摸底，产出一份《Testing Platform Integration Inventory》。

| 编号  | 要确认的内容    | 如何确认                      | 结果要保存什么                |
| --- | --------- | ------------------------- | ---------------------- |
| T01 | Jira 具体版本 | Jira 页面 About，或 REST API  | Jira 版本号、Base URL、部署类型 |
| T02 | Jira 认证方式 | 询问管理员，确认 PAT / OAuth / 其他 | 认证方式、权限范围              |
| T03 | Jira 项目字段 | 查询项目、Issue Type、字段元数据     | 项目 Key、字段 ID、必填项       |
| T04 | B 的自动化框架  | 看脚本文件、运行命令、测试报告           | 框架、语言、版本、报告格式          |
| T05 | A 的报告生成方式 | 请同事口头演示一次完整操作             | 输入目录、文件命名、处理步骤         |
| T06 | 运行环境与数据边界 | 与 IT、安全、测试负责人确认           | 部署位置、数据级别、模型使用边界       |

## 1. Jira 版本尤其要确认

Data Center 和 Server 的 REST API 有很多相似之处，但不能因此假设版本和能力完全相同。

Atlassian 官方说明：

- Jira Data Center 的 REST API 文档需要按实际版本选择；
- 认证方式包括 OAuth 2.0、PAT 等；
- PAT 在较新的 Data Center 版本中可以使用；
- Jira Server 的官方支持已于 2024 年 2 月 15 日结束。

  [image](https://www.google.com/s2/favicons?domain=https://developer.atlassian.com\&sz=32)

  developer.atlassian.com+2



如果公司实际使用的是 Jira Server，而不是 Data Center，我会把它列为技术风险：需要由平台管理员确认安全补丁、支持状态和升级计划。不能因为 API 能调用，就认为平台仍然适合长期承载新的集成系统。

第一条接口建议先只做只读验证：

```
GET {JIRA_BASE_URL}/rest/api/2/serverInfo
GET {JIRA_BASE_URL}/rest/api/2/myself
```

目的：

- 确认 Jira 版本；
- 确认实际部署地址；
- 确认认证是否成功；
- 确认当前集成账户身份。

不要先申请管理员账号。先申请一个专用集成账号，按最小权限原则授予读取项目、搜索 Issue、创建 Bug、上传附件所需的权限。

## 2. Jira 需要的接口清单

建议先封装一个 `JiraDCAdapter`，所有 Jira 调用统一从这个适配器走。

| 业务能力        | Jira DC REST API                                | 用途         |
| ----------- | ----------------------------------------------- | ---------- |
| 查询服务信息      | `GET /rest/api/2/serverInfo`                    | 获取版本       |
| 查询当前用户      | `GET /rest/api/2/myself`                        | 验证身份       |
| 获取项目        | `GET /rest/api/2/project`                       | 获取项目       |
| 获取 Issue 类型 | `GET /rest/api/2/issuetype` 或项目对应元数据            | 获取 Bug 类型  |
| 获取字段        | `GET /rest/api/2/field`                         | 获取系统及自定义字段 |
| 查询创建元数据     | `GET /rest/api/2/issue/createmeta/...`          | 了解可用字段     |
| 创建 Issue    | `POST /rest/api/2/issue`                        | 创建 Bug     |
| 查询 Issue    | `GET /rest/api/2/issue/{issueKey}`              | 回读确认       |
| 搜索 Issue    | `GET /rest/api/2/search`                        | JQL 搜索相似缺陷 |
| 上传附件        | `POST /rest/api/2/issue/{issueKey}/attachments` | 上传截图和日志    |

这里有个容易踩坑的地方：Jira 9.0 起，官方移除了旧的 `createmeta` 资源；对于 Jira 8.4 及之后的版本，官方文档建议使用按项目和 Issue Type 查询字段元数据的方式。具体接口必须按实际 Jira 版本选择。

[image](https://www.google.com/s2/favicons?domain=https://developer.atlassian.com\&sz=32)

developer.atlassian.com+1



另外，Jira DC 的附件上传需要 `multipart/form-data`，并且请求头要包含：

```
X-Atlassian-Token: no-check
```

附件表单字段名为 `file`。

[image](https://www.google.com/s2/favicons?domain=https://developer.atlassian.com\&sz=32)

developer.atlassian.com



## 3. 建议的 Jira 调用顺序

```
连接 Jira
   |
   v
获取 serverInfo / myself
   |
   v
获取项目、Issue Type、字段元数据
   |
   v
读取字段配置并建立映射
   |
   v
搜索相似历史缺陷
   |
   v
生成 Jira Draft
   |
   v
本地字段校验
   |
   v
人工审核
   |
   v
POST 创建 Issue
   |
   v
上传截图和日志
   |
   v
GET 回读确认
   |
   v
记录 Jira Key 和提交状态
```

不要让 Agent 直接拼接 Jira API 请求。Agent 只生成业务数据，`JiraDCAdapter` 负责请求构造、认证、重试策略、响应解析和错误处理。

# 三、同事 A：报告批量解析与差异工作台的具体实施方案

由于暂时拿不到文件，我会把 A 的系统做成多格式输入、统一中间数据结构、可替换解析器的架构。

这样未来无论是 HTML、PDF，还是同事后来发现的其他格式，都可以通过增加 Parser Adapter 解决。

## 1. 先定义文件导入约定

用户每次导入一个 Regression Batch。

建议支持两种模式：

模式一：目录导入

```
regression_batch/
│
├── manifest.json
│
├── baseline/
│   ├── Case001.pdf
│   ├── Case002.pdf
│   └── ...
│
├── current/
│   ├── Case001.pdf
│   ├── Case002.pdf
│   └── ...
│
├── total/
│   ├── Case001.html
│   ├── Case002.html
│   └── ...
│
└── ignore/
    ├── Case001.html
    ├── Case002.html
    └── ...
```

这是我们希望用户导入时整理成的标准目录，不代表同事当前实际目录就是这样。

模式二：直接导入已有报告目录

用户可以选择 Total HTML 或 Ignore HTML 的所在目录，系统根据文件名、目录和 HTML 内容尝试提取 Case ID。

如果无法识别 Case ID，必须进入“待人工匹配”列表，不能随意把两个文件配成一组。

## 2. 统一文件元数据结构

每个文件在进入解析器之前，先登记基本信息。

```
{
  "file_id": "FILE-000001",
  "batch_id": "REG-20261109-001",
  "case_id": "CASE-007",
  "file_type": "total_html",
  "file_name": "Case7_PolSchedule.html",
  "relative_path": "total/Case7_PolSchedule.html",
  "file_hash": "sha256:...",
  "file_size": 125600,
  "uploaded_at": "2026-11-09T10:00:00+08:00",
  "parser_status": "PENDING"
}
```

几个重要字段：

- `file_hash`：识别重复文件和文件变更；
- `case_id`：建立 Baseline 和 Current 的对应关系；
- `file_type`：明确是 PDF、Total HTML 还是 Ignore HTML；
- `parser_status`：方便失败重试和排查。

## 3. 解析器应该怎么设计？

我会建立统一的 Parser Interface。

```
from typing import Protocol, Anyclass ReportParser(Protocol):    def supports(self, file_path: str) -> bool:        ...    def parse(self, file_path: str) -> dict[str, Any]:        ...
```

然后实现：

```
ReportParser
│
├── HtmlTotalParser
├── HtmlIgnoreParser
├── PdfTextParser
├── PdfLayoutParser
└── OCRParser
```

其中：

- `HtmlTotalParser`：读取完整差异报告；
- `HtmlIgnoreParser`：读取已有过滤报告；
- `PdfTextParser`：提取 PDF 文本；
- `PdfLayoutParser`：提取文本位置和布局；
- `OCRParser`：处理扫描型 PDF。

PDF 解析不能只用一个简单的 `get_text()` 就认定提取结果正确。PyMuPDF 官方文档明确指出，普通文本提取可能出现阅读顺序不符合视觉顺序、换行异常等问题；它也提供 `blocks`、`words` 等带坐标的提取方式。

[image](https://www.google.com/s2/favicons?domain=https://pymupdf.readthedocs.io\&sz=32)

PyMuPDF documentation+1



因此 PDF 解析结果还应该做质量检测：

- 是否成功提取文本；
- 页面是否存在大量空白；
- 文本是否出现乱码；
- 是否有明显的阅读顺序异常；
- 关键字段是否能够定位；
- 是否需要 OCR；
- 是否需要人工复核。

### 解析输出统一成什么样？

我建议不是直接输出一整段纯文本，而是输出一组有位置、有来源的结构化片段。

例如：

```
{
  "document_id": "DOC-0007",
  "case_id": "CASE-007",
  "source_file_id": "FILE-000001",
  "format": "html",
  "content_blocks": [
    {
      "block_id": "BLK-001",
      "page": null,
      "section": "insured_information",
      "field_name": "insured_name",
      "text": "杨宜庭",
      "position": {
        "line": 89
      },
      "source_type": "html_dom"
    },
    {
      "block_id": "BLK-002",
      "page": null,
      "section": "policy_date",
      "field_name": "policy_date",
      "text": "2026-11-06",
      "position": {
        "line": 81
      },
      "source_type": "html_dom"
    }
  ]
}
```

这里 `field_name` 可以是解析器识别出的字段，也可以是后续业务规则映射出的字段。必须标记识别方式，不能把 AI 推测的字段名称伪装成原始数据。

## 4. Diff Engine：具体比较逻辑

Diff Engine 不应该只比较两个字符串。

我建议有三层数据：

1. 原始内容；
2. 规范化内容；
3. 差异结果。

例如：

```
{
  "diff_id": "DIFF-00001",
  "case_id": "CASE-007",
  "baseline": {
    "text": "2026 11 06",
    "source_file_id": "BASE-001"
  },
  "current": {
    "text": "2026 11 20",
    "source_file_id": "CUR-001"
  },
  "change_type": "MODIFIED",
  "comparison_level": "TOKEN",
  "normalized": false,
  "rule_hits": [],
  "review_status": "PENDING"
}
```

建议差异类型统一为：

```
ADDED
DELETED
MODIFIED
UNCHANGED
UNMATCHED
PARSER_ERROR
```

其中 `UNMATCHED` 特别重要：如果 Baseline 有某个 Case，而 Current 没有，不能把它当作“没有差异”。

## 5. Ignore Rule Engine：规则结构和执行顺序

我会把 Ignore 规则单独保存，不与原始报告混在一起。

```
{
  "rule_id": "IGNORE-001",
  "rule_name": "Ignore Report Generated Date",
  "field_path": "report.generated_date",
  "match_type": "FIELD_PATH",
  "action": "IGNORE_FROM_PRIMARY_VIEW",
  "scope": {
    "document_type": "PolicySchedule"
  },
  "reason": "报告生成时间不参与本次业务结果判断",
  "status": "ACTIVE",
  "version": 1,
  "approved_by": "QA_APPROVER",
  "created_at": "2026-11-09T10:00:00+08:00"
}
```

我建议动作至少有三种：

| 动作                         | 作用                |
| -------------------------- | ----------------- |
| `IGNORE_FROM_PRIMARY_VIEW` | 从默认重点列表隐藏，但原始差异保留 |
| `MARK_LOW_PRIORITY`        | 标记低优先级，仍可见        |
| `REQUIRE_REVIEW`           | 必须人工确认            |

不要设计成真正的 `DELETE`。

### 规则执行优先级

```
原始差异
   |
   v
字段映射
   |
   v
匹配已批准规则
   |
   +---- 命中 IGNORE_FROM_PRIMARY_VIEW
   |
   +---- 命中 MARK_LOW_PRIORITY
   |
   +---- 命中 REQUIRE_REVIEW
   |
   v
生成不同展示视图
```

另外需要增加一条保护机制：

当规则匹配结果与业务关键字段保护清单冲突时，以保护清单为准。

例如 `insured_name` 即使被某条宽泛的人名规则命中，也不能直接隐藏。

## 6. A 的 API 设计

前端不应该直接读取磁盘上的 140 个 HTML 文件，而是通过后端 API 读取解析和比较结果。

| API                                       | 方法         | 作用              |
| ----------------------------------------- | ---------- | --------------- |
| `/api/v1/regression/batches`              | POST       | 创建批次            |
| `/api/v1/regression/batches/{id}/files`   | POST       | 上传或登记文件         |
| `/api/v1/regression/batches/{id}/parse`   | POST       | 触发解析            |
| `/api/v1/regression/batches/{id}/compare` | POST       | 触发比较            |
| `/api/v1/regression/batches/{id}/summary` | GET        | 获取批次摘要          |
| `/api/v1/regression/batches/{id}/cases`   | GET        | 获取 Case 列表      |
| `/api/v1/regression/cases/{id}/diffs`     | GET        | 获取单 Case 差异     |
| `/api/v1/regression/rules`                | GET / POST | 查询或创建 Ignore 规则 |
| `/api/v1/regression/rules/{id}`           | PATCH      | 更新规则            |
| `/api/v1/regression/batches/{id}/export`  | POST       | 导出报告            |

对于 140 个 Case，列表接口要支持分页和筛选，例如：

```
GET /api/v1/regression/batches/REG-001/cases
    ?page=1
    &page_size=50
    &change_type=MODIFIED
    &risk=HIGH
```

不要一次把所有 HTML 的完整正文都传给浏览器。

列表只传：

- Case ID；
- 变化数量；
- 变化分类；
- 解析状态；
- 风险提示；
- 是否人工审核。

点击某个 Case 后，再加载详细 Diff 和原始内容。

## 7. A 的数据库表

建议至少有以下表：

| 表                  | 用途      |
| ------------------ | ------- |
| `regression_batch` | 回归批次    |
| `regression_file`  | 文件登记    |
| `regression_case`  | Case 索引 |
| `report_document`  | 解析后的文档  |
| `document_block`   | 文档内容片段  |
| `diff_record`      | 原始差异    |
| `ignore_rule`      | 忽略规则    |
| `rule_execution`   | 规则命中记录  |
| `review_record`    | 人工审核记录  |
| `analysis_result`  | AI 分析结果 |
| `export_record`    | 报告导出记录  |

特别注意：`diff_record` 应该保存原始差异，规则执行后产生的视图结果应该单独保存或动态计算。不要让规则覆盖原始结果。

# 四、同事 B：失败分析与 Jira 助手的具体实施方案

B 的系统比 A 更依赖自动化测试框架的输出，但我们可以先解决这个问题：定义统一的失败数据协议，再让不同测试框架适配这个协议。

这也是为什么我不建议一开始就把系统写死成 Playwright Agent。

## 1. 先建立统一的测试结果协议

无论同事使用的是 Selenium、Playwright、Robot Framework、Cypress，还是公司自研框架，都应该尽可能转换成统一的 JSON 格式。

建议建立 `Test Execution Result Schema`。

例如：

```
{
  "schema_version": "1.0",
  "execution_id": "EXEC-20261109-001",
  "suite_name": "NBS Regression",
  "environment": {
    "name": "NBS-SIT",
    "base_url": "https://test.example.internal",
    "build_version": "build-20261109-01"
  },
  "framework": {
    "name": "unknown",
    "version": null,
    "language": null
  },
  "started_at": "2026-11-09T10:00:00+08:00",
  "finished_at": "2026-11-09T10:30:00+08:00",
  "cases": [
    {
      "case_id": "CASE-0042",
      "title": "BM agent record lookup",
      "status": "FAILED",
      "started_at": "2026-11-09T10:15:00+08:00",
      "duration_ms": 12000,
      "error": {
        "type": "AssertionError",
        "message": "Agent record not found",
        "stack_trace": null
      },
      "steps": [],
      "evidence": {
        "screenshots": [
          "artifacts/CASE-0042.png"
        ],
        "logs": [
          "artifacts/CASE-0042.log"
        ],
        "video": null,
        "trace": null
      }
    }
  ]
}
```

这份结构的价值在于：不管底层测试框架是什么，后续的失败分析、聚类和 Jira 生成都只需要理解这一种格式。

## 2. 测试框架适配器怎么做？

我会定义统一的接口：

```
from typing import Protocol, Anyclass TestFrameworkAdapter(Protocol):    def detect(self, files: list[str]) -> bool:        ...    def parse_results(self, source: str) -> dict[str, Any]:        ...    def collect_evidence(self, case_id: str) -> list[dict]:        ...
```

未来接入不同框架时：

```
TestFrameworkAdapter
│
├── PlaywrightAdapter
│
├── SeleniumAdapter
│
├── RobotFrameworkAdapter
│
├── CypressAdapter
│
└── CustomFrameworkAdapter
```

但要注意：Adapter 不应该依赖文件名猜测框架。

更可靠的识别方式是组合判断：

- 项目依赖文件；
- 测试运行命令；
- 测试报告格式；
- 脚本语言；
- 截图和日志目录结构；
- 框架版本信息。

如果无法识别，就让用户在导入时选择框架类型，并记录为人工确认。

## 3. 失败证据必须统一收集

这是 B 系统最重要的基础。

一个 Failed Case 不应该只有一张截图和一段报错文本。

我建议为每个 Case 建立一个 Evidence Bundle。

```
{
  "evidence_id": "EVD-0042",
  "execution_id": "EXEC-001",
  "case_id": "CASE-0042",
  "captured_at": "2026-11-09T10:15:30+08:00",
  "items": [
    {
      "type": "SCREENSHOT",
      "path": "artifacts/CASE-0042.png",
      "sha256": "..."
    },
    {
      "type": "ERROR_LOG",
      "path": "artifacts/CASE-0042.log",
      "sha256": "..."
    },
    {
      "type": "CONSOLE_ERROR",
      "path": "artifacts/console.log",
      "sha256": "..."
    },
    {
      "type": "NETWORK_EVENT",
      "path": "artifacts/network.json",
      "sha256": "..."
    },
    {
      "type": "TRACE",
      "path": null,
      "sha256": null
    }
  ]
}
```

证据类型建议标准化：

| 证据类型             | 说明       | 用途               |
| ---------------- | -------- | ---------------- |
| Screenshot       | 失败截图     | 观察页面状态           |
| Error Log        | 原始错误     | 分析异常             |
| Stack Trace      | 堆栈       | 定位脚本代码           |
| Console Error    | 浏览器控制台错误 | 判断前端异常           |
| Page Error       | 页面未捕获异常  | 判断 JavaScript 异常 |
| Network Event    | 网络请求和响应  | 判断 API、网关问题      |
| Trace            | 浏览器操作轨迹  | 复现执行过程           |
| Video            | 测试过程视频   | 观察异常发生前后         |
| Environment Info | 环境信息     | 排除环境配置问题         |
| Test Data Info   | 测试数据引用   | 排除数据问题           |

有一个重要要求：

每份证据都要能够关联到 Execution ID、Case ID 和执行时间。

否则即使收集了很多日志，也很难判断哪个错误属于哪个 Case。

## 4. 失败分析引擎的规则与 AI 分工

我会把 Failure Analysis 拆成两个部分。

### 第一层：规则引擎做确定性检查

比如：

| 观察条件                 | 规则输出                             |
| -------------------- | -------------------------------- |
| 测试脚本抛出明确语法错误         | Automation Error 候选              |
| API 返回 401 / 403     | Authentication / Permission 候选   |
| API 返回 404           | Endpoint / Resource 候选           |
| API 返回 500           | Server Error 候选                  |
| 页面元素等待超时             | Locator / Timing / Page State 候选 |
| 数据查询结果为空             | Test Data / Data Setup 候选        |
| 页面访问出现网络错误           | Network / Environment 候选         |
| 多个无关 Case 同时出现同一服务错误 | Shared Dependency 候选             |

注意这些都只是候选分类，不是自动认定根因。

例如 HTTP 500 只能证明服务端返回了错误状态，不能直接证明开发代码有 Bug。还要检查请求参数、服务日志、依赖状态、异常堆栈等证据。

### 第二层：AI 负责综合分析

AI 接收：

- 规则引擎输出；
- 截图 OCR 或视觉分析结果；
- 错误日志；
- Stack Trace；
- 历史相似失败；
- 测试步骤；
- 环境和版本信息。

然后生成：

```
{
  "case_id": "CASE-0042",
  "classification": {
    "category": "AUTOMATION_OR_APPLICATION",
    "suggested_owner": "QA",
    "status": "UNCONFIRMED"
  },
  "hypotheses": [
    {
      "hypothesis": "The failure may be caused by an outdated locator",
      "supporting_evidence": [
        "The failure occurred while locating the target element"
      ],
      "contradicting_evidence": [],
      "missing_evidence": [
        "DOM snapshot",
        "Current page screenshot",
        "Recent page change information"
      ],
      "confidence": "LOW"
    }
  ],
  "recommended_actions": [
    "Inspect the current DOM",
    "Compare the locator with the previous successful execution"
  ],
  "human_review_required": true
}
```

这里的 `confidence` 不建议一开始使用看起来很精确的 97%、89% 等数字。

因为模型输出的概率或自评置信度，并不等于经过验证的真实准确率。

初期使用：

- LOW；
- MEDIUM；
- HIGH；

但这三个等级也必须由明确的评分规则定义。后续通过人工确认数据评估实际准确率，再考虑校准概率。

## 5. Failure Clustering：40 个失败 Case 如何批量分析？

这是一个很值得投入的功能。

我会使用：

- 错误签名；
- 时间窗口；
- API Endpoint；
- 环境；
- 模块；
- Trace ID；
- 异常类型；
- 文本相似度；
- 历史缺陷关联。

组合形成聚类依据。

### 失败聚类的计算逻辑

不建议只用 LLM 判断“这两个 Case 看起来很像”。

应该先提取结构化特征：

```
{
  "case_id": "CASE-0042",
  "error_signature": "HTTP_503|agent-service|lookup",
  "environment": "NBS-SIT",
  "module": "Agent Lookup",
  "timestamp": "2026-11-09T10:15:30+08:00",
  "trace_id": "trace-xxxx",
  "exception_type": "HTTPError"
}
```

然后用规则、相似度算法和时间窗口建立候选分组。

比如：

Failure Cluster Overview

示例数据，仅用于说明工作台交互

Cluster A · API 503

12 Cases

共同服务、相近时间、相似错误签名

Cluster B · Locator Timeout

8 Cases

相同页面元素或相似操作步骤

Cluster C · Test Data

6 Cases

测试数据缺失或状态不符合前置条件

Unclustered

14 Cases

没有足够共同证据，需要单独分析

聚类还要支持拆分和合并。

因为一个错误签名相同的 Case，可能实际上由不同根因引起；相反，错误信息不同的 Case，也可能源自同一个底层服务故障。

所以聚类只是减少分析工作量的工具，不能替代最终根因判断。

# 五、弹窗问题：具体做一个 Popup Diagnostic 子模块

这个问题不能等知道框架后才开始考虑，因为它本身就可以先定义统一的事件协议。

## 1. 弹窗识别与处理流程

Popup Diagnostic Workflow

自动化执行开始

监听浏览器事件和页面状态

发现异常弹窗或新窗口

已知弹窗

命中批准规则

未知弹窗

没有命中规则

记录处理策略、截图和结果

保存证据，暂停或安全失败

## 2. 事件结构

```
{
  "event_id": "POPUP-0001",
  "execution_id": "EXEC-001",
  "case_id": "CASE-0042",
  "event_type": "JAVASCRIPT_DIALOG",
  "dialog_type": "ALERT",
  "message": "Agent record not found",
  "page_url": "https://test.example.internal/agent",
  "trigger_step": "Submit Agent Search",
  "detected_at": "2026-11-09T10:15:30+08:00",
  "handling": {
    "policy": "UNKNOWN_DIALOG",
    "action": "CAPTURE_AND_PAUSE",
    "status": "PENDING_REVIEW"
  }
}
```

## 3. 如果最后确认使用 Playwright

Playwright 可以直接监听：

- `page.on('dialog')`：JavaScript Dialog；
- `page.on('popup')`：页面打开新窗口；
- `page.on('pageerror')`：未捕获的页面 JavaScript 异常；
- `page.on('requestfailed')`：网络请求失败；
- `page.on('console')`：浏览器 Console 信息。

官方文档也明确说明了 JavaScript Dialog 的处理机制：如果注册了 Dialog Listener，就必须 accept 或 dismiss，否则操作可能被阻塞；没有 Listener 时，Playwright 会自动关闭这些 Dialog。

[image](https://www.google.com/s2/favicons?domain=https://playwright.dev\&sz=32)

Playwright+2



这个细节很重要：如果同事说“有时候弹窗关不掉”，我们需要先确认它到底是不是 JavaScript Dialog，而不是直接在脚本里增加一个全局关闭弹窗的操作。

## 4. 不同弹窗的处理策略

| 弹窗类型             | 自动化处理方式         | 默认策略        |
| ---------------- | --------------- | ----------- |
| 已知业务确认弹窗         | 规则匹配，按用例预期接受或取消 | 受控处理        |
| JavaScript Alert | Dialog Listener | 记录后按规则处理    |
| HTML Modal       | DOM 识别与 Locator | 识别后人工或规则处理  |
| 新窗口              | Page / Popup 事件 | 记录并关联新 Page |
| 浏览器权限弹窗          | 浏览器配置和权限策略      | 不做盲目点击      |
| 操作系统弹窗           | 专用桌面自动化或环境配置    | 独立处理        |

未知弹窗一律先取证，不做自动关闭。

如果是业务确认弹窗，盲目点击“确定”可能造成真实业务数据变更；如果是安全警告，自动关闭也可能掩盖测试环境问题。

# 六、Jira DC：完整接口封装与数据结构

这一部分可以开始做成真正的工程模块了。

## 1. Jira Adapter 应该有哪些方法？

```
class JiraDCAdapter:    def get_server_info(self):        ...    def get_current_user(self):        ...    def get_projects(self):        ...    def get_issue_types(self, project_key):        ...    def get_fields(self):        ...    def get_create_metadata(self, project_key, issue_type_id):        ...    def search_issues(self, jql, fields=None):        ...    def create_issue(self, payload):        ...    def get_issue(self, issue_key):        ...    def upload_attachment(self, issue_key, file_path):        ...    def update_issue(self, issue_key, payload):        ...
```

我建议把 API 的 Base URL、API 版本、认证、超时、证书验证和代理都放在配置层，而不是散落在业务代码里。

## 2. Jira Draft 数据结构

这是 AI 生成后、人工审核前的内部标准格式。

```
{
  "draft_id": "JIRA-DRAFT-0001",
  "execution_id": "EXEC-001",
  "case_id": "CASE-0042",

  "analysis": {
    "category": "AUTOMATION_ISSUE",
    "root_cause_status": "PROBABLE",
    "evidence_ids": [
      "EVD-0042"
    ],
    "human_review_status": "PENDING"
  },

  "jira_fields": {
    "project_key": "ITQA",
    "issue_type": "Bug",
    "summary": "[NBS Regression] Agent lookup failed",
    "description": "Structured description...",
    "environment": "NBS-SIT",
    "priority": "Medium",
    "labels": [
      "Regression",
      "Automation"
    ],
    "components": [],
    "assignee": null
  },

  "attachments": [
    {
      "evidence_id": "EVD-0042",
      "file_path": "artifacts/CASE-0042.png",
      "upload": true
    }
  ],

  "submission": {
    "status": "NOT_SUBMITTED",
    "jira_issue_key": null
  }
}
```

注意：`jira_fields` 是内部统一格式，真正发给 Jira 时要由映射器转换为 Jira 的字段 ID 和对应格式。

## 3. Jira Description 模板

不要让 AI 自由发挥，建议固定模板：

```
Summary:
[NBS Regression] Agent record not found

Environment:
NBS-SIT

System:
NBS

Component:
Agent Management

Test Case:
CASE-0042

Execution ID:
EXEC-001

Preconditions:
1. The test environment is available.
2. Test agent data is prepared.

Steps to Reproduce:
1. Open the BM test page.
2. Enter agent code 48100.
3. Enter product code UFKT.
4. Execute the test case.

Expected Result:
The agent record should be found.

Actual Result:
The system displays "Agent record not found".

Error Details:
[Original error message]

Evidence:
1. Screenshot
2. Execution log
3. Relevant trace information

AI Analysis:
Probable category: Data / Application / Automation.
This is an unconfirmed hypothesis and requires QA review.

Impact:
To be confirmed by QA.
```

模板里的示例数据来源于你提供的 Jira 截图可见内容，只用于说明字段排版，实际提交必须由同事确认。

## 4. Jira 字段映射表

| 内部字段          | Jira 字段       | 转换逻辑                    |
| ------------- | ------------- | ----------------------- |
| `summary`     | `summary`     | 字符串                     |
| `description` | `description` | 按 Jira 版本和字段配置转换        |
| `environment` | `environment` | 字符串                     |
| `priority`    | `priority`    | 映射到 Jira 可用 Priority ID |
| `labels`      | `labels`      | 字符串数组                   |
| `components`  | `components`  | 映射 Component ID         |
| `assignee`    | `assignee`    | 映射 Jira 用户标识            |
| `issue_type`  | `issuetype`   | 映射 Issue Type ID        |
| `project_key` | `project`     | 映射项目 Key                |

Jira DC 创建 Issue 的基础请求结构是：

```
POST /rest/api/2/issue
Content-Type: application/json
```

```
{
  "fields": {
    "project": {
      "key": "ITQA"
    },
    "summary": "[NBS Regression] Agent record not found",
    "description": "Issue description",
    "issuetype": {
      "name": "Bug"
    },
    "environment": "NBS-SIT"
  }
}
```

Atlassian 官方文档提供了 Jira DC 创建 Issue 的请求结构和示例。

[image](https://www.google.com/s2/favicons?domain=https://developer.atlassian.com\&sz=32)

developer.atlassian.com+1



但真实项目要先验证字段配置，不能假设 `System`、`Components`、`Environment` 等字段都使用默认字段类型。

## 5. Jira 相似缺陷检测

在创建 Jira 前，建议先进行一次 JQL 查询。

例如：

```
project = ITQA
AND issuetype = Bug
AND statusCategory != Done
AND text ~ "Agent record not found"
ORDER BY created DESC
```

但这里不能只靠文本匹配。

建议做三层检查：

1. 文本相似：Summary、Description；
2. 业务相似：系统、模块、错误码、接口；
3. 证据相似：错误签名、日志特征、Trace 信息。

最后输出：

```
{
  "duplicate_candidates": [
    {
      "issue_key": "ITQA-1024",
      "similarity_reason": [
        "Same error signature",
        "Same system component"
      ],
      "decision": "REVIEW_REQUIRED"
    }
  ]
}
```

注意，相似度不是重复缺陷的最终结论。不同 Case 可能共享一个底层问题，也可能只是错误文字相同。

## 6. 批量提交必须具备幂等控制

这是企业级 Jira 集成很容易遗漏的地方。

例如用户点了一次“批量提交”，页面卡住了，用户以为没有提交成功又点了一次。

如果没有防重复机制，就可能创建两个相同 Bug。

建议建立：

```
{
  "submission_id": "SUBMIT-0001",
  "draft_id": "JIRA-DRAFT-0001",
  "idempotency_key": "sha256:...",
  "status": "SUBMITTING",
  "jira_issue_key": null,
  "attempt_count": 1,
  "last_error": null
}
```

状态机：

```
DRAFT
  |
  v
VALIDATED
  |
  v
APPROVED
  |
  v
SUBMITTING
  |
  +---- 成功 ---> CREATED
  |
  +---- 失败 ---> FAILED
  |
  +---- 结果未知 -> RECONCILIATION_REQUIRED
```

特别是 `RECONCILIATION_REQUIRED`：

如果 HTTP 请求超时，不能立即再创建一次。因为 Jira 可能已经创建成功，只是响应没有返回。应该先通过请求关联记录、Issue 搜索等方式确认是否已经创建，再决定是否重试。

# 七、B 的 API 设计与数据库结构

## 1. 后端 API 清单

| API                                | 方法   | 用途          |
| ---------------------------------- | ---- | ----------- |
| `/api/v1/executions`               | POST | 创建测试执行批次    |
| `/api/v1/executions/{id}/import`   | POST | 导入测试结果      |
| `/api/v1/executions/{id}/cases`    | GET  | 获取 Case 列表  |
| `/api/v1/cases/{id}/evidence`      | GET  | 获取失败证据      |
| `/api/v1/cases/{id}/analyze`       | POST | 分析单个失败 Case |
| `/api/v1/executions/{id}/analyze`  | POST | 批量分析        |
| `/api/v1/executions/{id}/clusters` | GET  | 获取失败聚类      |
| `/api/v1/clusters/{id}`            | GET  | 获取聚类详情      |
| `/api/v1/jira/drafts`              | POST | 生成 Jira 草稿  |
| `/api/v1/jira/drafts/{id}`         | GET  | 获取草稿        |
| `/api/v1/jira/drafts/{id}/review`  | POST | 审核草稿        |
| `/api/v1/jira/drafts/{id}/submit`  | POST | 提交 Jira     |
| `/api/v1/jira/submissions/{id}`    | GET  | 查询提交状态      |
| `/api/v1/jira/issues/{key}/sync`   | POST | 回读 Jira 信息  |

## 2. 数据库表设计

| 表                          | 用途                |
| -------------------------- | ----------------- |
| `test_execution`           | 测试执行批次            |
| `test_case_result`         | 每个 Case 的执行结果     |
| `test_step_result`         | 每个步骤的执行结果         |
| `test_evidence`            | 截图、日志、视频、Trace    |
| `test_event`               | 弹窗、网络、Console 等事件 |
| `failure_analysis`         | AI 分析结果           |
| `failure_hypothesis`       | 根因候选和证据           |
| `failure_cluster`          | 失败聚类              |
| `failure_cluster_member`   | 聚类成员              |
| `jira_draft`               | Jira 草稿           |
| `jira_field_mapping`       | 字段映射              |
| `jira_submission`          | 提交记录              |
| `jira_duplicate_candidate` | 相似缺陷              |
| `human_review`             | 人工审核记录            |
| `confirmed_root_cause`     | 已确认根因             |
| `knowledge_case`           | 历史案例知识库           |

这里特别建议把 `confirmed_root_cause` 和 `failure_analysis` 分开。

因为 AI 生成的根因假设不等于最终确认的根因。只有经过 QA、开发或指定责任人确认的结论，才应该进入已确认知识库，成为未来分析的可靠参考。

# 八、Agent、Skill、Workflow 到底如何组织？

我不建议给每一个功能都创建一个 Agent。那样会产生大量 Agent 之间的上下文传递、权限管理、调试和成本问题。

我的建议是：两个业务 Agent + 多个 Skill + 确定性 Workflow + 独立工具服务。

## A：Regression Agent

| 能力包                        | 负责内容          |
| -------------------------- | ------------- |
| `report-discovery`         | 文件发现和批次识别     |
| `report-parsing`           | HTML / PDF 解析 |
| `diff-analysis`            | 差异解释          |
| `ignore-rule-assistant`    | 忽略规则候选        |
| `business-impact-analysis` | 业务影响辅助分析      |
| `regression-summary`       | 批次报告总结        |

Agent 负责调用这些 Skill，回答测试人员的问题，例如：

- 这次有哪些重要变化？
- 哪些变化已经被 Ignore 规则处理？
- 哪些变化可能影响业务结果？
- 与上一轮相比，哪些 Case 的差异值得优先检查？

## B：Failure Analysis Agent

| 能力包                      | 负责内容      |
| ------------------------ | --------- |
| `failure-classification` | 失败分类      |
| `evidence-analysis`      | 证据分析      |
| `failure-clustering`     | 失败聚类      |
| `popup-diagnostics`      | 弹窗诊断      |
| `root-cause-analysis`    | 根因候选分析    |
| `jira-draft-generation`  | Jira 字段生成 |
| `jira-duplicate-search`  | 历史缺陷检索    |

## 统一 Workflow

B：从失败到 Jira 的完整流程

1. Import

   导入执行报告和附件，校验文件完整性。
2. Normalize

   转换为统一的 Test Execution Schema。
3. Collect Evidence

   建立 Case、日志、截图、Trace 和环境信息的关联。
4. Rule Analysis

   运行错误码、超时、权限、数据、网络等确定性检查。
5. AI Analysis

   生成失败分类、根因候选、证据及缺失信息。
6. Cluster

   聚合可能具有共同原因的失败 Case。
7. Human Review

   QA 确认分类、根因、责任团队及处理方式。
8. Jira Draft

   生成标准字段和附件清单，检查重复缺陷。
9. Submit

   人工批准后提交 Jira，回读 Issue Key。
10. Feedback

    后续将开发确认的根因、修复方式和复测结果写入知识库。

我会让 Workflow 控制每一步的输入输出和执行状态，而不是让一个 Agent 自己决定整个流程怎么走。

这会让系统更容易审计、重试、恢复和定位故障。

# 九、真正落地：部署和安全架构

这是富卫这种保险业务环境尤其需要考虑的部分。

## 1. 建议的部署方式

```
企业内部用户
     |
     v
Testing Intelligence Web
     |
     v
API Gateway / Authentication
     |
     v
Backend Services
     |
     +---- Regression Service
     |
     +---- Failure Analysis Service
     |
     +---- Jira DC Adapter
     |
     +---- AI Gateway
     |
     +---- Task Queue
     |
     v
Enterprise Data Layer
     |
     +---- PostgreSQL
     |
     +---- File Storage
     |
     +---- Audit Logs
```

建议优先部署在公司批准的内部基础设施中：

- 内网 Web 服务；
- 内部数据库；
- 受控文件存储；
- 企业模型网关；
- 内部 Jira 网络连通区。

如果 AI 模型部署在外部云端，必须经过公司安全、数据保护和架构审批。尤其不能把未经批准的保单、客户姓名、身份证件、账户和内部敏感日志直接上传到公共模型。

## 2. 权限设计

| 角色             | 查看结果 | 修改规则 | 审核分析 | 提交 Jira | 管理配置 |
| -------------- | ---- | ---- | ---- | ------- | ---- |
| QA Tester      | 是    | 否    | 是    | 经授权     | 否    |
| QA Lead        | 是    | 是    | 是    | 是       | 部分   |
| Developer      | 授权范围 | 否    | 反馈根因 | 否       | 否    |
| Platform Admin | 是    | 是    | 是    | 技术授权    | 是    |

还需要记录：

- 谁导入了数据；
- 谁查看了敏感证据；
- 谁修改了 Ignore 规则；
- 谁确认了根因；
- 谁审核了 Jira 草稿；
- 谁提交了 Issue；
- 哪个模型、Prompt、Skill 版本参与了分析。

日志本身也不能随意保存敏感信息。OWASP Logging Cheat Sheet 建议对访问令牌、密码、会话标识和敏感个人信息进行排除、脱敏或保护，并控制日志访问权限。

[image](https://www.google.com/s2/favicons?domain=https://cheatsheetseries.owasp.org\&sz=32)

OWASP Cheat Sheet Series+1



# 十、项目验收：不能只看“AI 能不能跑起来”

我会用真实历史数据建立评测集，给 A 和 B 各自制定验收标准。

下面是建议的初始目标，是项目立项时的目标值，不是已经测得的性能结果，也不是行业统一强制标准。应该在基线测量后由测试负责人确认。

## A 的验收标准

| 指标           | 建议验收方式                                       |
| ------------ | -------------------------------------------- |
| 文件识别准确率      | 已知文件集全部正确归类                                  |
| Case 匹配准确率   | Baseline / Current / Total / Ignore 对应关系人工核验 |
| 差异识别准确率      | 与人工标注的差异记录对比                                 |
| 原始差异保留率      | 所有原始差异都能追溯                                   |
| Ignore 规则准确性 | 误过滤关键业务字段的情况必须为零                             |
| 批次展示完整性      | 所有成功解析的 Case 均能在统一页面定位                       |
| 异常文件处理       | 损坏、缺失、格式不支持的文件明确报错                           |
| 导出一致性        | 导出的差异与页面原始差异一致                               |

最重要的安全指标：已批准规则不能误隐藏关键业务差异。

## B 的验收标准

| 指标         | 建议验收方式            |
| ---------- | ----------------- |
| 失败结果导入率    | 与原始测试报告逐项核对       |
| 证据关联完整率    | 每个失败 Case 能找到对应证据 |
| 分类准确率      | 与人工确认分类比较         |
| 根因候选有效率    | 检查 AI 候选是否有真实证据支持 |
| 无依据结论率     | 检查是否把假设写成事实       |
| Jira 字段准确率 | 与人工填写版本比较         |
| Jira 提交成功率 | 实际创建并回读确认         |
| 重复创建率      | 检查重复提交和历史缺陷冲突     |
| 人工审核时间     | 对比原来的逐条处理时间       |

### 我尤其建议增加三个指标

1\. Root Cause Evidence Coverage

AI 给出的每个根因候选，是否都能关联至少一条支持证据？

2\. Unsupported Conclusion Rate

AI 是否出现“没有日志、没有 Trace、没有验证，却直接断言开发代码有 Bug”的情况？

3\. Human Correction Rate

QA 修改 AI 分类和 Jira 内容的比例是多少？

这三个指标比单纯看模型生成了多少文字有价值。

# 十一、开发顺序：建议 8 周做出可投入真实测试工作的版本

以下是一个建议的开发计划，前提是能获得必要的测试数据、开发环境和 Jira API 权限。

## 8 周实施计划

1. 第 1 周：摸底与数据标准化
   - 确认 Jira 版本和字段；
   - 确认 B 的自动化框架；
   - 访谈 A 的完整报告处理流程；
   - 定义 A / B 的数据协议；
   - 收集脱敏历史案例。

     交付：技术调研报告、数据 Schema
2. 第 2 周：A 的解析器 + B 的导入器
   - HTML / PDF Parser；
   - Test Framework Adapter；
   - 文件完整性检查；
   - 原始数据存储。

     交付：两条数据导入流水线
3. 第 3 周：A 的 Diff Engine + B 的失败分类
   - 行、词、字符、字段差异；
   - Ignore Rule Engine；
   - 确定性失败分类；
   - 失败证据关联。

     交付：两个核心分析引擎
4. 第 4 周：统一工作台
   - A 的批次总览、双栏对比；
   - B 的失败列表、证据详情；
   - 搜索、筛选、分页。

     交付：QA 可操作界面
5. 第 5 周：AI 分析和历史检索
   - A 的变化摘要；
   - B 的失败分类辅助；
   - 根因候选和证据引用；
   - 历史案例检索。

     交付：AI 辅助分析能力
6. 第 6 周：Jira DC 集成
   - 字段元数据；
   - Jira 草稿生成；
   - 相似缺陷搜索；
   - 附件上传；
   - 人工审核和幂等提交。

     交付：Jira 闭环
7. 第 7 周：弹窗诊断与可靠性
   - 接入实际测试框架；
   - 事件采集；
   - 重试和异常恢复；
   - 权限、日志、脱敏。

     交付：稳定性和安全测试报告
8. 第 8 周：真实业务试运行
   - 选择真实回归批次；
   - 对照人工分析；
   - 统计节省时间和错误率；
   - 修复误判；
   - 测试部门验收。

     交付：试运行报告和上线建议

这里我建议把“上线”分成三个阶段：

- Shadow Mode：AI 只分析，不影响原有流程；
- Assisted Mode：QA 审核后采用 AI 结果；
- Controlled Automation：只有经过验证的规则和接口才允许自动执行。

不要直接从开发完成跳到全自动。

# 十二、我认为最有价值的长期能力：让系统从每一次测试中积累经验

你最开始提到希望工具能够长期有价值，而不是很快被新一代 AI 替代。

我的判断是：

真正不会轻易被替代的，不是某个 Agent、某个 Skill 或某个 Prompt，而是富卫测试部门自己的结构化质量数据、业务规则、失败知识和经过验证的自动化能力。

我建议把这两个模块逐步建设成一个 Test Quality Knowledge Base。

每次测试都产生：

```
Test Execution
     |
     v
Observed Failure / Difference
     |
     v
Evidence
     |
     v
AI Hypothesis
     |
     v
Human Confirmed Root Cause
     |
     v
Resolution
     |
     v
Retest Result
     |
     v
Verified Knowledge
```

例如，未来遇到一个新的 Agent Record Not Found 问题，系统可以检索：

- 过去是否出现过相同错误；
- 当时使用了什么测试数据；
- 是否是数据同步问题；
- 是否是权限问题；
- 是否是脚本问题；
- 最终由谁确认；
- 修复后是否通过复测。

这种知识不是单纯把 Jira 文档放进向量数据库就能获得的，而是需要将 Case、Evidence、Root Cause、Resolution、Retest 等信息关联起来。

未来还可以接入：

- Azure DevOps / Git；
- CI/CD；
- API 自动化测试；
- 测试覆盖率分析；
- 变更影响分析；
- 自动化脚本生成和维护；
- 缺陷趋势和质量预测。

这才是值得长期投资的方向。

# 十三、现在应该先向同事确认什么？

目前 A 缺少报告文件，B 缺少框架信息。因此我建议你不要立即开始开发完整系统，而是先把下面这张调研清单拿给两位同事。

技术摸底 Checklist

0/20 已确认

同事 A：报告与比较

PDF 是测试平台直接生成，还是由其他工具二次处理？

Total HTML 和 Ignore HTML 是由什么程序生成的？

140 个 HTML 的文件名是否包含固定 Case ID？

Baseline 是人工指定，还是系统自动选取上一轮？

Ignore 目前是按字段、按文本，还是按正则表达式过滤？

是否存在一个 Case 对应多个 PDF 或多个 HTML 的情况？

当前比较结果是否需要保留原始 PDF 页码或文本位置？

同事 B：自动化框架与失败信息

测试脚本文件扩展名是什么？例如 .py、.ts、.java？

执行测试使用什么命令或平台？

失败结果是 JUnit XML、JSON、HTML，还是平台自定义报告？

截图、日志、视频分别存储在哪里？

是否有每一步操作的日志或 Trace ID？

失败 Case 是否有人工确认的最终根因记录？

Jira 中创建 Bug 时哪些字段是必填的？

平台管理员：Jira 与部署

Jira 的具体版本号和部署类型是什么？

是否允许为集成系统申请专用 API 账号？

PAT 或 OAuth 是否允许使用？

目标项目的 Bug 创建权限和附件权限如何申请？

Jira 是否存在自定义字段、工作流校验或必填字段？

内部是否有批准的模型服务、数据库和文件存储？

&#x20;复制调研清单

## 最后，我给你的实际工程建议

如果我是这个项目的 AI 应用工程师，我会把接下来两周的工作定为：

第一件事：先做 B 的 Jira 集成验证。

因为 Jira DC 的 API 路径相对明确，哪怕暂时不知道测试框架，也可以先用人工导出的 5 条失败记录，验证字段映射、草稿生成、附件上传和审核提交的完整闭环。

第二件事：先做 A 的 HTML 解析技术验证。

虽然没有文件，但可以先准备通用 Parser 和统一 Diff 数据结构；真正决定解析逻辑的部分必须等拿到脱敏样本后再完成。

第三件事：先把 B 的测试结果 Schema 定下来。

未来接入任何自动化框架，都必须转换成这个标准。这样你不是在开发一个只能服务某个同事的工具，而是在建立公司测试部门可以复用的基础能力。

我的建议是：先把两个模块做成可独立运行的业务工具，再逐渐合并成统一平台；先让 AI 提供有证据的辅助判断，再逐步开放自动化操作。

这条路线比一开始追求多 Agent、自主规划和全自动执行更可靠，也更符合企业级 AI 工程的发展方向。

## 技术依据与官方文档

下面这些是方案中关键技术选择的原始依据，建议后续技术评审时直接使用：

1. [Atlassian：Jira REST API Examples](https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/?utm_source=chatgpt.com) — Jira Data Center 创建、编辑 Issue 和版本差异。
2. [Atlassian：Jira Data Center REST API](https://developer.atlassian.com/server/jira/platform/rest/v10002/?utm_source=chatgpt.com) — REST API 版本、认证和接口参考。
3. [Atlassian：Jira Data Center Attachment API](https://developer.atlassian.com/server/jira/platform/rest/v11000/api-group-issue/?utm_source=chatgpt.com) — 附件上传方式。
4. [Atlassian：Jira JQL Search API](https://developer.atlassian.com/server/jira/platform/rest/v10007/api-group-search/?utm_source=chatgpt.com) — 历史缺陷查询。
5. [Playwright：Page API](https://playwright.dev/docs/api/class-page?utm_source=chatgpt.com) — Dialog、Popup、Page Error、Network Event。
6. [Playwright：Dialogs](https://playwright.dev/docs/dialogs?utm_source=chatgpt.com) — 弹窗处理行为。
7. [PyMuPDF：Text Extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html?utm_source=chatgpt.com) — PDF 文本、块、坐标提取。
8. [OWASP：Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html?utm_source=chatgpt.com) — 敏感信息保护、日志审计和访问控制。

这些依据支持的是技术可行性和工程设计原则；具体到富卫内部流程、字段、业务规则和数据权限，仍然需要由实际系统和负责人确认。