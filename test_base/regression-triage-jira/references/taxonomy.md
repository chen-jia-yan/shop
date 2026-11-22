# 失败分类标准（Taxonomy）

本文件是分类的唯一标准。判断只由 `scripts/ta_engine.py` 完成（页面和命令行都调用它，没有第二套）；规则内容在 `config/rules.json`：`rules` 是内置规则用到的关键字和数值，`custom` 是团队自己加的自定义规则（第 8 节）。AI 复核时也必须遵守本文件。改判断逻辑要同时更新本文件和 `ta_engine.py`，并运行 `python scripts/ta.py check`。下面括号里的 `xxx_messages` 等是 `rules.json` 里的项名。

## 总原则

0. **先看整批，再看单个用例。** 逐条分类之前先做运行级分析（`root-cause-method.md` 第 1 步）：断崖（某个用例之后连续因环境失败到结束）、通过用例里出现的同样报错、同功能通过/失败对比、残留窗口。运行级结论会写进每个相关用例的依据。
1. **按顺序判断，先命中先生效。** 顺序是：环境问题 → 系统提示（读不到文字的弹窗、数据占用、缺少配置、程序崩溃、截图中的干扰弹窗）→ 原生对话框 → 业务报错 → 网页弹框 → 掩盖型报错 → 桌面端控件异常 → 脚本问题 → 断言失败 → 需人工判断；最后，人工记录了“截图观察”的，再按截图修正（第 7 节）。
   分类只看本次失败的证据，**不看重跑结果**。重跑是分类之后的一步，见“重跑标准”。
   **日志有 Python 异常链时，所有规则都基于异常链第一段（最先发生的异常）和步骤日志判断**，忽略 `SystemExit: 0` 和截图/清理函数中的异常（解析方法见 `pywinauto-desktop.md` 第 1 节）。
2. **每个结论有两个状态：**
   - `confirmed`：规则证据充分，可以直接采用；
   - `suspected`：有线索但不充分，必须由 AI 根据截图复核或由人确认。
3. **证据编号**：每个用例的证据按 `E1, E2, …` 编号（见 `data-contract.md`），所有结论都要引用编号。

## 六个类别

| 代码 | 中文名 | 默认处理方 | 是否建 Jira |
|---|---|---|---|
| `ENVIRONMENT` | 环境问题 | 测试（由测试联系环境负责人） | 是（一次运行只建一张，列出所有受影响用例） |
| `POPUP_INTERFERENCE` | 弹窗干扰 | 测试；来源是环境时转环境负责人 | 否，汇总到弹窗清单；同一弹窗反复出现时建任务 |
| `SCRIPT_ISSUE` | 脚本问题 | 测试 | 否，由测试修脚本；需要跟踪时建 QA 任务 |
| `TEST_DATA` | 测试数据问题 | 测试 | 视团队习惯，可配置 |
| `PRODUCT_DEFECT` | 产品缺陷 | 开发 | 是 |
| `NEEDS_HUMAN` | 需人工判断 | 测试 | 否，人工判断后再决定 |

重跑通过的用例保留原来的类别，只是不提单（见“重跑标准”）。

起草时默认勾选哪些分类，在页面“Jira 提报 → 起草范围”里设置（`config/jira.json` 的 `draftCats`）。

---

## 1. ENVIRONMENT 环境问题

**判定规则**

- `ENV1-confirmed`：异常类型为 `SessionNotCreatedException`（浏览器与驱动版本不匹配、浏览器无法启动）。
- `ENV2-confirmed`：报错信息或页面内容匹配 `env_patterns`（例如 `ERR_CONNECTION_REFUSED`、`ERR_NAME_NOT_RESOLVED`、`502 Bad Gateway`、`503 Service Unavailable`、`504 Gateway Time-out`、`Connection refused`、`Read timed out`；被测系统后台连接中断：`A transport-level error has occurred`、`An existing connection was forcibly closed by the remote host`）。只匹配步骤日志和异常链中的主要异常，不匹配截图函数里的异常。
- `ENV-DESK-confirmed`：Windows 执行机没有可交互桌面：`There is no active desktop required for moving mouse cursor`，或 `SetCursorPos` 调用失败。截图函数报 `screen grab failed` 只作为佐证，不单独判为环境问题。
- `ENV3-suspected`：同一次运行中，相同的标准化报错特征出现在至少 `mass_min_cases` 个用例（默认 5 个），且占失败总数比例不低于 `mass_ratio`（默认 30%），并且这些失败**在执行顺序上连续**，或发生在 `mass_window_min`（默认 15 分钟）内。（只用时间窗口会漏掉长时间运行中的断崖：本次回归运行 2.5 小时，断崖中的 26 个用例不可能落在 15 分钟内。）

**运行级标记（不改变类别）**

- “环境中断边界”：断崖起点之前紧挨着的那个失败用例。它的失败可能也受环境影响，重跑建议为“建议立即重跑”，一句话结论末尾加“紧挨环境中断的起点，建议先重跑”；不是环境类的，原因代码为 `env_boundary`。
- 通过用例里的同样报错：环境类报错也出现在本次**通过**的用例日志中，写进依据，作为“环境不稳定”的佐证。

**证据要求**：异常类型或匹配到的报错原文；ENV3 需要列出相同特征的用例数量和连续范围或时间范围。

**反例**

- 页面正常打开，只是业务接口返回“record not found”——这是业务报错，不是环境问题。
- 某个用例单独超时——单个超时不足以判断为环境问题，进入后面的规则。

---

## 2. POPUP_INTERFERENCE 弹窗干扰

弹窗分三种，判断方法见 `popup-catalog.md`。

**判定规则**

- `POP1-confirmed`：异常类型为 `UnexpectedAlertPresentException`，对话框文字匹配 `noise_popups`。
- `POP1-未知 → NEEDS_HUMAN`（`unknown_popup`）：原生对话框的文字既不在 `noise_popups` 也不是业务报错。
- `POP2-confirmed`：页面/弹窗文字匹配 `noise_popups`，并且异常属于点击被挡或找不到元素（`intercept_exceptions`、`locator_exceptions`）。
- `POP3-suspected`：`ElementClickInterceptedException`，“遮挡点击的元素”（`Other element would receive the click: <...>`）含 `overlay_keywords`（modal、dialog、popup、overlay、mask 等）；不含时为 `POP3-弱`（点击被遮挡，遮挡物待确认）。

**证据要求**：弹窗文字原文、遮挡元素的 HTML 片段，或截图编号。网页内找不到弹框、但截图里有弹窗时，在截图观察里记下（第 7 节）。

**反例（非常重要）**

- 弹窗文字是业务报错，例如 “Agent record not found”、“Policy status invalid”、“System error, please contact administrator”。这些匹配 `business_errors`，**不能归为弹窗干扰**，进入第 3 类判断。
- 弹窗文字不在 `noise_popups` 也不在 `business_errors` 中：归为 `NEEDS_HUMAN`，原因写“未知弹窗”，并在汇报中列出弹窗原文，建议补充到清单。

---

## 2a. 系统提示（桌面端弹窗、校验提示）

桌面端被测系统的弹窗多数是在说明出了什么事，**按文字含义分类，不按“是不是弹窗”分类**。文字来源：异常信息中 `pop-up error:` 后面的内容、步骤日志中的 `Validation Error:` / `Error Message:`，以及人工抄下的截图文字（截图观察）或截图自动识别的文字。

- `SYS-EMPTY → NEEDS_HUMAN`（`unknown_popup`）：有 `pop-up error:` 但后面没有文字。只能看截图；同时建议改进弹窗读取。
- `DATA-LOCK-confirmed → TEST_DATA`：文字匹配 `lock_messages`（例如 `Contract is currently used by other user`）。需要人工核查占用来源：
  - 核查结果“被本批次前面的用例占用（失败后没有释放）” → `CHK-LOCK1-confirmed → SCRIPT_ISSUE`（前面用例的清理步骤有问题）；
  - “被其他人或其他批次占用”“查不到占用来源” → 保持 `DATA-LOCK → TEST_DATA`。
- `SYS-CFG → NEEDS_HUMAN`（`system_config`）：文字匹配 `config_messages`（例如 `Cannot get MSP Config`）。核查结果：“应该存在，但测试环境缺失” → `CHK-CFG → ENVIRONMENT`；“配置正确，系统仍然报错” → `CHK-CFG → PRODUCT_DEFECT`；“本来就不支持（用例前提不成立）” → `CHK-CFG → SCRIPT_ISSUE`。
- `SYS-CRASH-suspected → PRODUCT_DEFECT`：被测程序弹出未处理异常对话框（`crash_messages`）。注意 `no Microsoft .NET Framework window` 是“没有出现”，不匹配。
- `OBS-POPN-confirmed → POPUP_INTERFERENCE`：截图中的弹窗文字匹配 `noise_popups`。
- 文字是环境类（`transport-level error` 等）→ 已在 ENV2 命中。
- 文字是业务报错 → 进入第 3 类。

---

## 3. 业务报错：TEST_DATA 或 PRODUCT_DEFECT

当页面（包括原生对话框、网页弹框、页面错误提示区域）出现匹配 `business_errors` 的文字时，进入本规则。**仅凭报错文字不能区分是数据问题还是系统问题**，必须查看数据核查结果。

**判定规则**

- `BIZ1-confirmed → TEST_DATA`：核查结果为“数据不存在”（`missing`）、“数据已被使用”（`used`）、“数据状态不符合用例前提”（`invalid`）。核查结果在页面上选择，或写在 `data_checks.yaml`（旧写法 `invalid_state` 等同 `invalid`）；一个用例涉及多项数据时，有一项有问题就按那一项。
- `BIZ2-confirmed → PRODUCT_DEFECT`：涉及的数据**全部**核查过且为 `ok`（数据存在且状态正确），系统仍然返回业务报错。ROTQA-5339 就是这种情况：已查数据库，agent 40100 数据正常，系统仍提示 “agent record not found”。
- `BIZ3 → NEEDS_HUMAN`：没有核查结果，或只核查了一部分。原因写“待数据核查”，并把需要核查的数据写入 `data_checks.todo.yaml`。

**证据要求**：业务报错原文 + 数据核查记录（核查人、时间、查询方式、结果）。

**注意**

- 数据核查必须由人完成，或由公司批准的只读查询脚本完成。AI 不得根据截图推断数据库状态。
- 同一组数据（例如同一个 agent code）只需要核查一次，`data_checks.todo.yaml` 会自动去重。

---

## 3a. 掩盖型报错与桌面端控件异常

**掩盖型（排在 SCR3 之前）**

- `MASK1 → NEEDS_HUMAN`（`masked_failure`）：异常链第一段是 `'bool' object has no attribute ...`、`'NoneType' object is not subscriptable` 等（`masked_patterns`）。前一步没找到东西、返回了 False/None。**不得**按 SCR3 归为脚本问题——真实原因可能是控件变了、窗口没打开、被挡住或数据不存在。下一步：看报错行的变量来自哪个查找函数、看截图。

**桌面端控件异常（pywinauto）**

- `DSK-AMB-confirmed → SCRIPT_ISSUE`：`ElementAmbiguousError`。同时提示检查残留窗口。
- `DSK-OPT-suspected → SCRIPT_ISSUE`：`'X' is not in list`（下拉框没有该选项）。
- `DSK-DTP-suspected → SCRIPT_ISSUE`：`Failed to set time in Date Time Picker`。需要人工核查日期值：“日期超出允许范围” → `CHK-DTP → TEST_DATA`；“日期在范围内，仍然设置失败” → `CHK-DTP → SCRIPT_ISSUE`。
- `DSK-VIS-suspected → SCRIPT_ISSUE`：`ElementNotVisible`。
- `DSK-DIS → NEEDS_HUMAN`（`control_state`）：`ElementNotEnabled`。按钮为什么灰，只能看截图或控件状态。
- `DSK-NF → NEEDS_HUMAN`：`MatchError`、`ElementNotFoundError`、`Can't find window`。报错列出的窗口清单要检查残留窗口。
- `GEN1 → NEEDS_HUMAN`（`generic_error`）：项目代码自己抛出的笼统 `Exception: ...`（如 `job cannot submit successfully`），且步骤日志里没有系统原话。

**校验阶段标记（不改变类别）**：步骤日志中已出现业务成功标记（`Job submitted`、`xxx succeeded`、`COMPLETED` 等，见 `success_marks`），之后才失败 → 标记 `phase: verify`。这类失败不得写成“业务功能缺陷”，起草时写明“业务操作已提交，失败在结果校验”，并建议在交易日志中人工确认。

---

## 4. SCRIPT_ISSUE 脚本问题

**判定规则**

- `SCR2-confirmed`：`InvalidSelectorException`（定位表达式本身写错）。
- `SCR3`：测试代码运行错误（`code_errors`：`NameError`、`AttributeError`、`TypeError`、`KeyError`、`IndexError`、`ImportError` 等）。堆栈里出现测试代码路径（`test_code_paths`）时为 `confirmed`，否则为 `suspected`（也可能是被测系统返回了异常数据）。
- `SCR1-suspected`：找不到元素或等待超时（`locator_exceptions`：`NoSuchElementException`、`StaleElementReferenceException`、`TimeoutException`、`ElementNotInteractableException` 等），并且前面的规则都没有命中（没有弹框文字、没有业务报错）。

**为什么 SCR1 只能是 suspected**：找不到元素有两种可能——脚本的定位写法过时了，或者页面本该出现的内容没有出现（这是产品缺陷）。区分它们需要看截图：页面布局正常、只是元素属性变了，是脚本问题；页面空白、报错、缺少整块内容，是产品问题。

**AI 复核要求**：查看失败截图，写下看到的页面状态。例如：
- “截图 E2 中保单录入页完整显示，Submit 按钮可见” → 支持脚本问题；
- “截图 E2 中页面主体空白，只有页头” → 不支持脚本问题，建议改为 `NEEDS_HUMAN`，说明疑似页面加载失败。

---

## 5. 断言失败

**判定规则**

- `AST1-suspected → PRODUCT_DEFECT`：异常类型为 `AssertionError`，且断言信息中有明确的期望值和实际值。
- `AST2 → NEEDS_HUMAN`：`AssertionError` 但没有期望值和实际值（例如只有 `assert False`）。

**为什么是 suspected**：断言失败可能是系统算错了，也可能是测试用例的期望值过时（需求已变更）。审核人需要对照当前需求确认。

**证据要求**：断言信息原文（期望值、实际值）。

---

## 6. NEEDS_HUMAN 需人工判断

以下情况全部归入本类，并写明原因代码：

| 原因代码 | 含义 | 审核人需要做什么 |
|---|---|---|
| `pending_data_check` | 有业务报错，等待数据核查 | 按 `data_checks.todo.yaml` 查询数据，在页面选核查结果或填 `data_checks.yaml` |
| `unknown_popup` | 出现不在清单中的弹窗 | 判断弹窗性质，在页面“判断规则 → 弹窗清单”补上，再下载规则文件覆盖 `config/rules.json` |
| `insufficient_evidence` | 没有截图、没有报错信息，或报错过于笼统 | 查看原始日志 |
| `conflicting_evidence` | 证据互相矛盾，例如日志说成功、截图却是报错 | 人工判断 |
| `no_rule_matched` | 没有任何规则命中 | 人工判断，考虑补充规则 |
| `masked_failure` | 掩盖型报错：前一步返回了 False/None | 看报错行的查找函数和截图，找出“没找到什么” |
| `system_config` | 系统提示缺少配置 | 问开发/配置负责人：应存在但缺失 → 环境；配置正确仍报错 → 缺陷 |
| `control_state` | 控件不可用（灰色） | 看截图/控件状态找原因 |
| `generic_error` | 只有笼统的包装报错 | 看步骤日志最后几行和截图 |
| `env_boundary` | 处在环境中断的边界 | 先重跑确认 |

---

## 7. 截图观察与截图识别（按截图修正）

**截图观察**：看过截图后写下的现象和截图上的文字（工作文件 `obs`）。现在由 AI 看图写入：`ta.py shots` 列出要看的用例和截图路径，AI 看完用 `ta.py record` 写入并重新分析（`by: "AI"`）。只修正“待复核 / 需人工判断”的结论；规则已确认的结论、依赖核查的结论（BIZ、SYS-CFG、SYS-CRASH、DATA-LOCK、CHK-*、AST）不改。**AI 写的观察让结论变了，一律降为 `suspected`**（下表的 confirmed 也变成待复核），人打开截图确认后在页面“确认 / 改分类”。

| 记录的现象 | 规则 | 结果 |
|---|---|---|
| 页面正常，要操作的控件在屏幕上 | `OBS-OK` | SCRIPT_ISSUE（confirmed） |
| 有弹窗，没抄文字 | `OBS-POP` | POPUP_INTERFERENCE（suspected） |
| 有弹窗，文字不在任何清单 | `OBS-POPU` | NEEDS_HUMAN（unknown_popup） |
| 页面空白、报错页或一直在加载 | `OBS-BLANK` | PRODUCT_DEFECT（suspected） |
| 停在别的窗口或页面 | `OBS-OTHER` | NEEDS_HUMAN，先重跑 |
| 控件是灰色不可用的 | `OBS-DIS` | NEEDS_HUMAN（control_state） |
| 锁屏、黑屏或远程桌面断开 | `OBS-DESK` | ENVIRONMENT（confirmed） |

抄下的文字和日志里的系统提示一样参与第 2a、3 节的判断（例如抄下 `Contract is currently used by other user` → DATA-LOCK）。

**截图识别（自动）**：「识别截图.bat」识别出的文字（工作文件 `ocrText`）只在截图观察里没有文字时使用。用了它而结论变了，一律降为 `suspected`，结论后面加“（依据截图识别的文字，待确认）”；日志已能确认的非“需人工判断”结论不被它改变。

**AI 判断**（工作文件 `ai`）：看完截图和报错后，规则仍没能确认的用例，AI 可以写一个分类和一句依据。页面显示“AI 判断·待复核”，分类按 AI 的写，规则原来的判断保留在依据里；规则已确认的用例不生效。

---

## 8. 自定义规则（团队自己加，优先于内置规则）

内置规则判不对、又不想改代码时，在页面“配置 → 自定义规则”加一条（写在 `rules.json` 的 `custom`）。

- **先于内置规则判断**，按列表顺序，第一条命中的生效。规则编号写成 `U` 加数字（`U1`、`U2`），结果里的规则名称就是这条的名称。
- **条件**：在哪些文字里找（`log` 日志和报错 / `popup` 弹窗和系统提示，含人工抄下的截图文字 / `screenshot` 截图自动识别的文字），出现任一（`any`）、还要全部出现（`all`）、不能出现（`none`）、异常类型（`exceptions`）。写法和其他规则相同，`re:` 开头是模糊匹配；普通文字至少 3 个字，避免误命中。
- **结论**：分类、`confirmed` 或 `suspected`、可选的一句话结论、下一步、重跑建议。
- 只靠截图自动识别的文字命中的，一律是 `suspected`，并提示核对截图；日志已能确认的内置结论不被它改变。
- 截图观察（第 7 节）不会改掉自定义规则的结论：既然团队写了规则，就以规则为准。
- 自定义规则判为“需人工判断”时，原因代码是 `custom_rule`。

什么时候用自定义规则、什么时候改关键字：
- 新的弹窗文字、新的环境报错、新的锁单提示 → 直接加到对应的关键字清单（`noise_popups`、`env_patterns`、`lock_messages` 等），走内置规则的判断和证据说明。
- 某个系统特有的报错，要判成固定的分类 → 自定义规则。
- 要改判断顺序或新增判断逻辑 → 改 `ta_engine.py`（见 `maintenance.md`）。

## 重跑标准（重跑不是分类）

**顺序：先分析每个用例的原因 → 列出需要重跑的用例 → 人工确认 → 重跑 → 用重跑结果确认判断。** 分类之前不重跑，重跑结果也不会产生新的类别。

**重跑建议**（`ta_engine.rerun_plan`，结果里的 `rerun_plan`；自定义规则可以指定）：

| 建议 | 什么情况 | 原因 |
|---|---|---|
| `go` 建议立即重跑 | 环境问题（确认环境已恢复后）；弹窗干扰；环境中断起点附近的用例（`env_boundary`）；可能偶发的情况（找不到窗口或元素、控件不可见、读不到文字的弹窗、未知对话框、点击被遮挡、断言不一致、截图中停在别处或页面空白，见 `ta_engine.RERUN_GO`）；有前面用例残留窗口的 | 这些失败与用例本身无关或可能是偶发，重跑能确认 |
| `fix` 处理后再重跑 | 还没做人工核查的（业务报错、数据占用、缺少配置、日期设置失败）；测试数据问题（先补数据、换数据或释放被占用的数据）；脚本问题（先修脚本）；掩盖型报错；证据不足 | 不处理就重跑，结果不会变，白白占用环境 |
| `no` 不需要重跑 | 产品缺陷 | 已判断是系统问题，直接起草 Jira |
| `done` 已重跑 | 已有重跑结果 | 见下表 |

**重跑结果怎么用**（`rerun_result`，只用来确认判断，分类不变）：

| 结果 | 含义 | 怎么处理 |
|---|---|---|
| `pass` | 重跑通过，这次失败是偶发的 | 不提单；分类和原因保留，用来统计哪类问题经常偶发。同一用例连续 3 次运行都偶发失败，建“脚本稳定性”任务 |
| `fail_same` | 重跑失败，报错与第一次相同，问题可复现 | 提单时同一张单写 *1st run* 和 *2nd run*，各附截图 |
| `fail_diff` | 重跑失败，但报错不同 | 第 2 次失败单独分析、单独提单（`group_id` 以 `-2` 结尾，先归为需人工判断） |

**注意**

- 重跑通过只说明“这个失败不是必现的”，**不说明没有问题**。并发、异步、时序类缺陷也可能表现为偶发。原始失败是业务报错（例如页面提示 “system error”）时，即使重跑通过，也要在汇报中列出原报错，由测试判断是否需要跟进。

---

## 规则维护

详细步骤见 `maintenance.md`。要点：
- 人工改判时勾选“同时加入纠错样本”（或在用例详情点“加入纠错样本”），样本存在 `config/corrections.json`。
- 改关键字、改自定义规则：在页面“配置”里改，保存时写修改人和修改说明，自动记进修改记录（`rules.json` 的 `changelog`），并把全部纠错样本重新判一遍；有样本判错会直接跳到“纠错样本”页。
- 改判断逻辑：改 `ta_engine.py` 和本文件，运行 `python scripts/ta.py check`（规则写法 + 纠错样本 + 基准样本）。基准样本的变化确认是有意的，再运行 `python evals/check_consistency.py --update`。
- `PRODUCT_DEFECT` 被误分到其他类别是最严重的错误（会漏掉真实缺陷），加规则时优先检查这一类的纠错样本。
