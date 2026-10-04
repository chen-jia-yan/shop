# 富卫日本保险知识库与测试用例生成平台 (FWD Japan Insurance KB & Test-Gen Platform)

面向富卫(FWD)日本寿险业务的**企业级生产系统**。系统把海量日文保险资料(商品说明书/要件、cycle test 样例、业务全景图、规则与画面文档)沉淀为**可问答、可溯源**的知识库,并在其上实现"商品说明书 → 自动生成 cycle test 测试用例",覆盖保单全生命周期(新契約/新单、契約管理/保全、理賠、解約)。这是处理**受监管的保险数据**的系统,安全与合规优先级高于功能与进度。

客户验收两条红线,所有设计围绕它们:
1. **覆盖范围达标** —— 覆盖产品全部业务场景,覆盖率可度量、缺口可见。
2. **可追溯(有依有据)** —— 每条答案/用例都能回指源文档精确位置(文件 / sheet / 单元格 / 页)。

阶段:一期知识库、二期用例生成、三期数据库字段级校验。当前代码要为全生命周期而设计,但不为未启动阶段提前堆砌复杂度。

## 架构原则
- **分层清洁架构**,依赖单向内指:`domain`(业务模型与规则,零外部依赖)← `application`(用例编排)← `infrastructure`(Azure/向量库/解析器等外部实现)/`interface`(API/CLI)。
- 所有外部依赖(LLM、向量库、文档解析、存储)通过**接口/端口**抽象,实现可替换、可 mock。向量检索 POC 用本地库(FAISS/Chroma),生产迁 Azure AI Search,上层不变。
- **12-Factor**:配置全部来自环境/密钥库,严禁硬编码;无状态服务;结构化日志。
- LLM 调用统一走 `infrastructure/llm` 网关层,业务代码不得直连 SDK。

## 技术栈
- 语言:Python 3.11+(生产级),pydantic v2 定义/校验数据模型,FastAPI(服务接口)。
- 大模型:**仅 Azure OpenAI**(GPT-4o 含 Vision、text-embedding)。禁用一切国产/未批准模型。
- 检索:向量库抽象接口 + FAISS/Chroma(POC)/ Azure AI Search(生产,混合检索+语义重排)。
- 文档解析:openpyxl、python-pptx、python-docx、Azure Document Intelligence(日式复杂版面/表格)、GPT-4o Vision(图片流程图)。
- 工程:ruff + black + mypy(strict)、pytest + coverage、pre-commit、OpenTelemetry(可观测)、structlog(结构化日志)。

## 安全防线(最高优先级,违反任一条视为安全事故)
**1. 模型与访问边界**
- LLM 只经 Azure OpenAI 网关层调用;禁止直连 SDK、禁止硬编码 endpoint/部署名。
- 出网**白名单**:仅允许访问已批准的 Azure 端点,禁止任意外联(防数据外泄与供应链回连)。

**2. 密钥与凭据**
- 所有密钥/连接串走 **Azure Key Vault + Managed Identity**;本地开发用环境变量,严禁进仓库、日志、异常栈、注释。
- 强制 **secret scanning**(pre-commit + CI,如 gitleaks);命中即阻断合并。

**3. 数据保护(保险数据高度敏感)**
- 遵循**最小必要**:送入 LLM 的内容先做 **PII 检测与脱敏/掩码**(姓名、证件号、保单号、金额、地址、健康信息等);能不出域的原始个人数据不出域。
- **传输 TLS、静态加密**;本地缓存/中间产物加密并设保留期与安全删除。
- 遵守日本个人情報保護法(APPI)与数据**驻留**要求:确认 Azure 部署区域合规,跨境传输需授权。
- 数据**分级标注**(公开/内部/机密/受监管),不同级别不同处理与访问策略。

**4. Prompt 注入与不可信输入**
- **一切文档内容与用户输入均视为不可信**。系统提示与检索内容严格分区,检索片段不得改写指令。
- 禁止让文档/用户内容触发工具调用、代码执行、文件系统或网络操作;输出经校验后才使用。
- 系统提示加固:锚定"只依据检索片段作答、逐条标源、资料不足即声明",防越权与幻觉。

**5. 访问控制与隔离**
- RBAC + 最小权限;按**产品/租户隔离**数据与索引,防越权检索到无关保单资料。
- 服务间调用最小权限,审计每一次特权操作。

**6. 审计与可追溯**
- 全量**审计日志**:谁、何时、问了什么、命中哪些源、调了哪个模型;日志**不含 PII 明文**、防篡改、设保留期。
- 生成结果必带来源引用(见溯源 schema),支持事后核查。

**7. 供应链安全**
- 依赖**锁版本**(hash-pinned),CI 跑 SCA 漏洞扫描,产出 SBOM;禁止引入未审计的三方包与模型权重。

**8. 输出安全**
- **严禁编造**:命中不足必须返回"资料不足";开启内容过滤;低置信多模态/OCR 结果不得入库,进人工复核闸门。

## 编码规范与质量框架
- 全量类型标注;数据结构用 pydantic,边界处校验输入输出。
- 外部 I/O 全部封装、可 mock;业务逻辑不散落 SDK 调用。
- 统一异常层次 + 结构化日志(禁止 print、禁止记 PII/密钥);面向用户的错误不泄露内部细节。
- 核心模块(解析/切片/检索/生成/溯源/PII 脱敏)必须有单元 + 集成测试;**覆盖率门槛**(建议 ≥80%,安全相关逻辑更高)。
- 可复现优先:建库、增量更新、评测、脱敏校验都用脚本,不留手动步骤。
- 术语通过 `glossary` 归一,不在代码硬编码日文术语。

## 溯源元数据 schema(每个 chunk 必带,缺失不得入库)
```json
{
  "chunk_id": "uuid",
  "source_file": "商品説明書_ProductX.xlsx",
  "doc_type": "product_spec | cycle_test | flowchart | rule | other",
  "locator": { "sheet": "設計", "cell_range": "B12:F20", "page": null, "slide": null },
  "lifecycle_stage": "新契約 | 保全 | 理賠 | 解約",
  "sensitivity": "public | internal | confidential | regulated",
  "text_ja": "原文(日文)",
  "text_zh": "中文翻译",
  "terms": ["附加険", "特約解約"],
  "product": "ProductX",
  "confidence": 0.0,
  "pii_masked": true,
  "ingested_at": "2026-09-06"
}
```

## 项目结构
- `src/domain/` : 业务模型与规则(保单生命周期、场景、覆盖率),零外部依赖
- `src/application/` : 用例编排(建库、问答、用例生成、校验)
- `src/infrastructure/`
  - `llm/` : Azure OpenAI 网关(唯一允许调模型处)
  - `parsing/` : excel/pptx/docx/pdf/image 解析器
  - `indexing/` : `VectorStore` 接口 + FAISS/Chroma、AzureAISearch 实现
  - `security/` : PII 检测脱敏、加密、脱敏日志
- `src/interface/` : FastAPI 路由 / CLI
- `src/models/` : pydantic 数据模型
- `scripts/` : build_index / update_index / run_eval / mask_check
- `config/` : 环境配置(不含密钥)
- `data/` : 原始文档与缓存(gitignore,加密);`glossary.csv`
- `tests/` : unit / integration / eval
- `.github/` : CI 工作流、路径指令、hooks(格式化、密钥扫描)
- `docs/` : 方案与安全设计,保持同步

## CI/CD 质量门(全部通过才可合并)
lint(ruff)→ format 校验(black)→ 类型(mypy)→ 单元+集成测试与覆盖率 → secret scanning → 依赖漏洞扫描(SCA)→ PII 脱敏用例校验。任一失败阻断合并;所有变更需 PR review。

## 铁律速览
- 只走 Azure OpenAI,禁国产/未批准模型;禁 Copilot Studio 等低代码实现核心逻辑。
- 密钥进 Key Vault,永不入仓库/日志。
- 送模型前必做 PII 脱敏;数据驻留合规。
- 文档与用户输入一律不可信,防 prompt 注入,禁从内容触发执行。
- 生成必带来源、严禁编造;低置信不入库。
- 全链路审计,日志无 PII 明文。

## 术语对照(检索归一)
新契約=新单;契約管理=保全;投保設計書=投保建议书;附加険=riders;特約解約=附加险解约;代理店=代理网点。

## 给 agent 的工作指引
先用 1 个代表性产品打通最小闭环(1 份说明书 + 1 份 cycle test 样例 + 1 张业务全景图),跑通"解析→脱敏→切片→索引→带引用问答→覆盖率矩阵",验证安全与溯源链路无误,再横向铺产品、纵向补格式与阶段。安全与合规校验先于功能通过。