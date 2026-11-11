# 失败分类标准（Taxonomy）

本文件是分类的唯一标准。`scripts/classify_rules.py` 按本文件实现；AI 复核时也必须遵守本文件。规则修改要同时更新本文件、`config/rules.yaml` 和 `evals/` 中的测试样本。

## 总原则

0. **先看整批，再看单个用例。** 逐条分类之前先做运行级分析（`root-cause-method.md` 第 1 步）：断崖（某个用例之后连续因环境失败到结束）、通过用例里出现的同样报错、同功能通过/失败对比、残留窗口。运行级结论会写进每个相关用例的依据。
1. **按顺序判断，先命中先生效。** 顺序是：环境问题 → 重跑可过 → 系统提示（数据占用、缺少配置、程序崩溃、读不到文字的弹窗）→ 弹窗（原生对话框）→ 业务报错 → 掩盖型报错 → 桌面端控件异常 → 弹窗（网页弹框）→ 脚本问题 → 断言失败 → 需人工判断。
   环境问题排在重跑之前：环境故障往往是暂时的，重跑会通过，如果先判“重跑可过”，环境问题就会被掩盖。这类用例归为 `ENVIRONMENT`，并标记 `passed_on_rerun: true`。
   **日志有 Python 异常链时，所有规则都基于异常链第一段（最先发生的异常）和步骤日志判断**，忽略 `SystemExit: 0` 和截图/清理函数中的异常（解析方法见 `pywinauto-desktop.md` 第 1 节）。
2. **每个结论有两个状态：**
   - `confirmed`：规则证据充分，可以直接采用；
   - `suspected`：有线索但不充分，必须由 AI 根据截图复核或由人确认。
3. **证据编号**：每个用例的证据按 `E1, E2, …` 编号（见 `data-contract.md`），所有结论都要引用编号。

## 七个类别

| 代码 | 中文名 | 默认处理方 | 是否建 Jira |
|---|---|---|---|
| `RERUN_PASS` | 重跑可过（不稳定） | 测试 | 否，记录不稳定次数；连续 3 次运行都出现时建“脚本稳定性”任务 |
| `ENVIRONMENT` | 环境问题 | 环境负责人 / 运维 | 是（一次运行只建一张，列出所有受影响用例） |
| `POPUP_INTERFERENCE` | 弹窗干扰 | 测试；来源是环境时转环境负责人 | 否，汇总到弹窗清单；同一弹窗反复出现时建任务 |
| `SCRIPT_ISSUE` | 脚本问题 | 测试 | 否，由测试修脚本；需要跟踪时建 QA 任务 |
| `TEST_DATA` | 测试数据问题 | 测试 | 视团队习惯，可配置 |
| `PRODUCT_DEFECT` | 产品缺陷 | 开发 | 是 |
| `NEEDS_HUMAN` | 需人工判断 | 测试 | 否，人工判断后再决定 |

是否建单由 `config/config.yaml` 中的 `jira.create_for_categories` 决定。

---

## 1. RERUN_PASS 重跑可过

**判定规则**

- `R1-confirmed`：本次失败，自动重跑至少一次通过。
- 附加信息（不改变类别）：历史记录中近 10 次运行通过率在 10%～90% 之间，标记 `historically_flaky: true`。

**证据要求**：重跑记录（证据编号来自 `rerun.json`，每次尝试的结果和时间）。

**注意**

- 重跑通过只说明“这个失败不是必现的”，**不说明没有问题**。并发、异步、时序类缺陷也可能表现为偶发。
- 如果原始失败是业务报错（例如页面提示 “system error”），即使重跑通过，也要在审核表中标出原报错，由测试判断是否需要跟进。脚本会给这类用例加 `rerun_pass_with_business_error: true`。

---

## 2. ENVIRONMENT 环境问题

**判定规则**

- `ENV1-confirmed`：异常类型为 `SessionNotCreatedException`（浏览器与驱动版本不匹配、浏览器无法启动）。
- `ENV2-confirmed`：报错信息或页面内容匹配 `rules.yaml` 中 `environment.patterns`（例如 `ERR_CONNECTION_REFUSED`、`ERR_NAME_NOT_RESOLVED`、`502 Bad Gateway`、`503 Service Unavailable`、`504 Gateway Time-out`、`Connection refused`、`Read timed out`；被测系统后台连接中断：`A transport-level error has occurred`、`An existing connection was forcibly closed by the remote host`）。只匹配步骤日志和异常链中的主要异常，不匹配截图函数里的异常。
- `ENV-DESK-confirmed`：Windows 执行机没有可交互桌面：`There is no active desktop required for moving mouse cursor`，或 `SetCursorPos` 调用失败。截图函数报 `screen grab failed` 只作为佐证，不单独判为环境问题。
- `ENV3-suspected`：同一次运行中，相同的标准化报错特征出现在至少 `environment.mass_failure_min_cases` 个用例（默认 5 个），且占失败总数比例不低于 `environment.mass_failure_ratio`（默认 30%），并且这些失败**在执行顺序上连续**，或发生在 `environment.mass_failure_window_minutes`（默认 15 分钟）内。（只用时间窗口会漏掉长时间运行中的断崖：本次回归运行 2.5 小时，断崖中的 26 个用例不可能落在 15 分钟内。）

**运行级标记（不改变类别）**

- `env_boundary`：断崖起点之前紧挨着的那个失败用例。它的失败可能也受环境影响，结论不得高于 `suspected`，建议先重跑。
- `corroborated_by_passed`：环境类报错也出现在本次**通过**的用例日志中，写进依据，作为“环境不稳定”的佐证。

**证据要求**：异常类型或匹配到的报错原文；ENV3 需要列出相同特征的用例数量和连续范围或时间范围。

**反例**

- 页面正常打开，只是业务接口返回“record not found”——这是业务报错，不是环境问题。
- 某个用例单独超时——单个超时不足以判断为环境问题，进入后面的规则。

---

## 3. POPUP_INTERFERENCE 弹窗干扰

弹窗分三种，判断方法见 `popup-catalog.md`。

**判定规则**

- `POP1-confirmed`：异常类型为 `UnexpectedAlertPresentException`，弹窗文字（`alert_text`）匹配 `rules.yaml` 中的 `noise_popups`。
- `POP2-confirmed`：失败时 `popup_evidence.dialogs` 中有可见的网页弹框，弹框文字匹配 `noise_popups`；并且异常类型为 `ElementClickInterceptedException`、`ElementNotInteractableException`、`NoSuchElementException` 或 `TimeoutException` 之一。
- `POP3-suspected`：异常类型为 `ElementClickInterceptedException`，报错信息中“遮挡点击的元素”（`Other element would receive the click: <...>`）的 class 或 id 含有 `modal`、`dialog`、`popup`、`overlay`、`mask` 等关键字（可配置），但没有弹框文字证据。
- `POP4-suspected`：`popup_evidence.popup_type` 为 `not_in_page`（网页内没有找到弹框），且整屏截图存在，且异常属于“点击无效 / 找不到元素 / 超时”类。这是浏览器或系统弹窗的线索，**需要人看整屏截图确认**。

**证据要求**：弹窗文字原文、遮挡元素的 HTML 片段，或整屏截图编号。

**反例（非常重要）**

- 弹窗文字是业务报错，例如 “Agent record not found”、“Policy status invalid”、“System error, please contact administrator”。这些匹配 `business_errors`，**不能归为弹窗干扰**，进入第 4 类判断。
- 弹窗文字不在 `noise_popups` 也不在 `business_errors` 中：归为 `NEEDS_HUMAN`，原因写“未知弹窗”，并在汇报中列出弹窗原文，建议补充到清单。

---

## 3a. 系统提示（桌面端弹窗、校验提示）

桌面端被测系统的弹窗多数是在说明出了什么事，**按文字含义分类，不按“是不是弹窗”分类**。文字来源：异常信息中 `pop-up error:` 后面的内容、步骤日志中的 `Validation Error:`。

- `SYS-EMPTY → NEEDS_HUMAN`（`unknown_popup`）：有 `pop-up error:` 但后面没有文字。只能看截图；同时建议改进弹窗读取。
- `DATA-LOCK-confirmed → TEST_DATA`：文字匹配 `system_messages.lock`（例如 `Contract is currently used by other user`）。下一步写明“查占用来源”。
- `SYS-CFG → NEEDS_HUMAN`（`system_config`）：文字匹配 `system_messages.config`（例如 `Cannot get MSP Config`）。需要开发或配置负责人确认配置是否应存在。
- `SYS-CRASH-suspected → PRODUCT_DEFECT`：被测程序弹出未处理异常对话框（`system_messages.crash`）。注意 `no Microsoft .NET Framework window` 是“没有出现”，不匹配。
- 文字是环境类（`transport-level error` 等）→ 已在 ENV2 命中。
- 文字是业务报错 → 进入第 4 类。

---

## 4. 业务报错：TEST_DATA 或 PRODUCT_DEFECT

当页面（包括原生对话框、网页弹框、页面错误提示区域）出现匹配 `business_errors` 的文字时，进入本规则。**仅凭报错文字不能区分是数据问题还是系统问题**，必须查看数据核查结果。

**判定规则**

- `BIZ1-confirmed → TEST_DATA`：`data_checks.yaml` 中该用例相关数据的核查结果为 `missing`（不存在）、`used`（已被使用）、`invalid_state`（状态不符合用例前提）。
- `BIZ2-confirmed → PRODUCT_DEFECT`：核查结果为 `ok`（数据存在且状态正确），但系统仍然返回业务报错。ROTQA-5339 就是这种情况：已查数据库，agent 40100 数据正常，系统仍提示 “agent record not found”。
- `BIZ3 → NEEDS_HUMAN`：没有核查结果。原因写“待数据核查”，并把需要核查的数据写入 `data_checks.todo.yaml`。

**证据要求**：业务报错原文 + 数据核查记录（核查人、时间、查询方式、结果）。

**注意**

- 数据核查必须由人完成，或由公司批准的只读查询脚本完成。AI 不得根据截图推断数据库状态。
- 同一组数据（例如同一个 agent code）只需要核查一次，`data_checks.todo.yaml` 会自动去重。

---

## 4a. 掩盖型报错与桌面端控件异常

**掩盖型（排在 SCR3 之前）**

- `MASK1 → NEEDS_HUMAN`（`masked_failure`）：异常链第一段是 `'bool' object has no attribute ...`、`'NoneType' object is not subscriptable` 等（`script.masked_patterns`）。前一步没找到东西、返回了 False/None。**不得**按 SCR3 归为脚本问题——真实原因可能是控件变了、窗口没打开、被挡住或数据不存在。下一步：看报错行的变量来自哪个查找函数、看截图。

**桌面端控件异常（pywinauto）**

- `DSK-AMB-confirmed → SCRIPT_ISSUE`：`ElementAmbiguousError`。同时提示检查残留窗口。
- `DSK-OPT-suspected → SCRIPT_ISSUE`：`'X' is not in list`（下拉框没有该选项）。
- `DSK-DTP-suspected → SCRIPT_ISSUE`：`Failed to set time in Date Time Picker`；提示可能是日期超出范围（测试数据）。
- `DSK-VIS-suspected → SCRIPT_ISSUE`：`ElementNotVisible`。
- `DSK-DIS → NEEDS_HUMAN`（`control_state`）：`ElementNotEnabled`。按钮为什么灰，只能看截图或控件状态。
- `DSK-NF → NEEDS_HUMAN`：`MatchError`、`ElementNotFoundError`、`Can't find window`。报错列出的窗口清单要检查残留窗口。
- `GEN1 → NEEDS_HUMAN`（`generic_error`）：项目代码自己抛出的笼统 `Exception: ...`（如 `job cannot submit successfully`），且步骤日志里没有系统原话。

**校验阶段标记（不改变类别）**：步骤日志中已出现业务成功标记（`Job submitted`、`xxx succeeded`、`COMPLETED` 等，见 `rules.yaml` 的 `log.success_marks`），之后才失败 → 标记 `phase: verify`。这类失败不得写成“业务功能缺陷”，起草时写明“业务操作已提交，失败在结果校验”，并建议在交易日志中人工确认。

---

## 5. SCRIPT_ISSUE 脚本问题

**判定规则**

- `SCR1-suspected`：异常类型为 `NoSuchElementException`、`StaleElementReferenceException`、`TimeoutException`、`ElementNotInteractableException`、`InvalidSelectorException` 之一，并且：
  - 没有弹框证据（`dialogs` 为空且不是原生对话框）；
  - 没有业务报错文字；
  - 重跑仍然失败（或未重跑）。
- `SCR2-confirmed`：异常类型为 `InvalidSelectorException`（定位表达式本身写错）。
- `SCR3-confirmed`：Python 自身的错误，例如 `NameError`、`AttributeError`、`TypeError`、`KeyError`、`IndexError`、`ImportError`、`ModuleNotFoundError`，且堆栈最后一帧位于测试代码目录（`config.yaml` 中的 `test_code_paths`）。

**为什么 SCR1 只能是 suspected**：找不到元素有两种可能——脚本的定位写法过时了，或者页面本该出现的内容没有出现（这是产品缺陷）。区分它们需要看截图：页面布局正常、只是元素属性变了，是脚本问题；页面空白、报错、缺少整块内容，是产品问题。

**AI 复核要求**：查看失败截图，写下看到的页面状态。例如：
- “截图 E2 中保单录入页完整显示，Submit 按钮可见” → 支持脚本问题；
- “截图 E2 中页面主体空白，只有页头” → 不支持脚本问题，建议改为 `NEEDS_HUMAN`，说明疑似页面加载失败。

---

## 6. 断言失败

**判定规则**

- `AST1-suspected → PRODUCT_DEFECT`：异常类型为 `AssertionError`，且断言信息中有明确的期望值和实际值。
- `AST2 → NEEDS_HUMAN`：`AssertionError` 但没有期望值和实际值（例如只有 `assert False`）。

**为什么是 suspected**：断言失败可能是系统算错了，也可能是测试用例的期望值过时（需求已变更）。审核人需要对照当前需求确认。

**证据要求**：断言信息原文（期望值、实际值）。

---

## 7. NEEDS_HUMAN 需人工判断

以下情况全部归入本类，并写明原因代码：

| 原因代码 | 含义 | 审核人需要做什么 |
|---|---|---|
| `pending_data_check` | 有业务报错，等待数据核查 | 按 `data_checks.todo.yaml` 查询数据并填写结果 |
| `unknown_popup` | 出现不在清单中的弹窗 | 判断弹窗性质，补充到 `rules.yaml` |
| `insufficient_evidence` | 没有截图、没有报错信息，或报错过于笼统 | 查看原始日志 |
| `conflicting_evidence` | 证据互相矛盾，例如有业务报错但重跑通过 | 人工判断 |
| `no_rule_matched` | 没有任何规则命中 | 人工判断，考虑补充规则 |
| `masked_failure` | 掩盖型报错：前一步返回了 False/None | 看报错行的查找函数和截图，找出“没找到什么” |
| `system_config` | 系统提示缺少配置 | 问开发/配置负责人：应存在但缺失 → 环境；配置正确仍报错 → 缺陷 |
| `control_state` | 控件不可用（灰色） | 看截图/控件状态找原因 |
| `generic_error` | 只有笼统的包装报错 | 看步骤日志最后几行和截图 |
| `env_boundary` | 处在环境中断的边界 | 先重跑 |

---

## 规则维护

- 每次人工把某个用例的分类改掉，审核表会记录“人工分类”和“修改原因”。每两周汇总一次，看是否需要新增或修改规则。
- 新增规则前，先把相关的历史用例加入 `evals/labeled_cases.csv`，运行 `evals/eval_classify.py`，确认新规则没有让其他用例分错。
- `PRODUCT_DEFECT` 被误分到其他类别是最严重的错误（会漏掉真实缺陷）。这个指标在评测中单独统计，必须低于 5%。