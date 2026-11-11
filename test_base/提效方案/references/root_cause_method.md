# 失败归因方法（手把手）

本文件教你如何**准确**判断一次回归中每个失败用例的原因。分类规则（`taxonomy.md`）告诉你“归哪一类”，本文件告诉你“怎么一步步找到证据、怎么核对、什么时候可以下结论”。

做 AI 复核（SKILL.md 第 4 步）和起草 Jira 之前，必须按本文件的顺序走一遍。不要跳步，不要从“看起来像”直接下结论。

---

## 0. 三条基本原则

### 0.1 分清三层原因

| 层次 | 含义 | 例子（来自 2026-10-30 LAS HK 回归） |
|---|---|---|
| **现象** | 报错直接说的东西 | `RuntimeError: There is no active desktop required for moving mouse cursor!` |
| **直接原因** | 为什么出现这个报错 | 执行机此时没有可交互的桌面，pywinauto 无法移动鼠标、无法输入 |
| **根因** | 为什么会出现直接原因 | 远程桌面会话被最小化/断开/锁屏（**需要环境负责人确认**） |

规则：
- 每个结论都要写清楚说到了哪一层。证据只支持到“直接原因”，就只写到直接原因，根因写进“待确认”。
- **不允许**把现象当根因写进 Jira（例如把 `ElementNotEnabled` 写成“按钮坏了”）。

### 0.2 证据有强弱，结论要和最强的证据一致

从强到弱（详见 `evidence-and-screenshots.md`）：

1. **机器直接给出的状态**：异常类型 + 项目代码里的出错位置、窗口/控件清单、数据库核查结果、交易日志状态
2. **被测系统给出的原话**：弹窗文字（`pop-up error: ...`）、`Validation Error: ...`、Life/Asia Message
3. **截图**：现场画面，但需要判读，可能不是失败那一刻的画面
4. **包装后的笼统报错**：`job cannot submit successfully`、`Add DDA/CCD Error!`、`SystemExit: 0`

**弱证据不能推翻强证据。** 强弱证据互相矛盾时，结论是“需人工判断（证据矛盾）”，写明是哪两条证据矛盾。

### 0.3 结论只有两种状态

- `confirmed`：证据**直接**说明了原因（例如系统提示原文就是“Contract is currently used by other user”）。
- `suspected`：证据只给出了方向（例如 `ElementNotEnabled` 只说明按钮是灰的，没说为什么是灰的）。

`suspected` 必须写明“还需确认什么、去哪里看、看到什么就改成什么”。

---

## 第 1 步：先看整批，再看单个用例

**不要一上来就逐条看。** 先回答下面四个问题，它们往往一次解释掉大半失败。

### 1.1 有没有“断崖”？

按**执行顺序**排列全部用例（包括通过的）。如果从某个用例开始，后面连续的用例都以同一类环境原因失败、一直到运行结束，说明环境在那个时刻中断了，之后没有恢复。

- 记录起点：第一个断崖用例。
- **检查起点前 1～2 个用例**：它们处在边界上，失败可能也受环境影响，结论最多到 `suspected`，并建议先重跑。
- 断崖内的用例**合并成一张单**，不要逐个提单。

> 实例：No.26（`test_30_TC_LAS_DirectCredit_01`）起，后面 26 个用例全部在 `las_search_policy` 第一次输入时失败，报错都是 `There is no active desktop`。它前一个用例 No.25（`test_29`）报的是 `ElementNotEnabled`，但它的截图函数已经报 `screen grab failed`——说明桌面在 No.24 和 No.25 之间消失。No.25 因此标为“环境中断边界”，先重跑再判断。

### 1.2 同样的报错是否也出现在通过的用例里？

环境类报错（连接中断、超时）出现在**通过的**用例日志里，说明那段时间环境本身不稳定，是对环境结论的佐证。

> 实例：No.7 弹窗报 `A transport-level error has occurred ... forcibly closed by the remote host`。同一批次中**通过的** No.15 日志里也有完全相同的报错（`get policy note by Policy error: A transport-level error ...`），只是那一步没有导致失败。两条独立记录指向同一个原因：被测系统与数据库之间的连接不稳定。

### 1.3 同一功能有没有通过的用例？

同一个功能（同一窗口）在本次既有通过也有失败，就把怀疑范围缩小到**这个用例特有的参数、数据或配置**。

> 实例：No.10（`Billing_Change_Half_Annually`）弹窗报 `Cannot get MSP Config`；No.11（同为 Billing Change，改为 Annually）通过了。说明 Billing Change 功能本身可用，问题集中在“半年缴”这个缴费频率对应的配置上。

### 1.4 有没有前面用例留下的“残留”？

桌面端用例失败后，如果没有关闭它打开的窗口，会影响后面的用例：出现多个同名控件（`ElementAmbiguousError`）、找不到窗口、保单被占用。

> 实例：No.31 找不到 `Client Bank and Mandate Approval` 窗口时，报错列出了当时打开的窗口，其中有两个 `Service Fee (COM 2 Bermuda)`——这是 No.24、No.25（都是 Service Fee 用例，都失败了）留下的。No.23 的 `Contract is currently used by other user` 也应优先怀疑前面失败用例未释放保单。

---

## 第 2 步：拆开一条日志

一条失败日志由三部分组成，**分开读**：

```
[步骤日志]   Traditional Partial Surrender (COM 2 Bermuda) window wait success
             sum_assured:6267705 new_sum_assured:6205027 Passed: Job submitted! finding transaction window
[异常链 1]   Traceback ... File "base_view\win_base_view.py", line 211, in win_set_text ...
             pywinauto.findwindows.ElementAmbiguousError: There are 3 elements that match ...
             During handling of the above exception, another exception occurred:
[异常链 2]   Traceback ... File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap
             SystemExit: 0
```

### 2.1 步骤日志：看业务走到了哪一步

步骤日志是脚本在失败前打印的内容。重点找两类文字：

- **业务成功标记**：`Job submitted`（不含 `Job submitted failed`）、`xxx succeeded`、`Save Successed`、`Record Submitted`、`trans_status:COMPLETED`。
  出现了成功标记、之后才失败 → **失败在结果校验阶段，被测功能本身大概率已经完成**。这类失败不应写成产品缺陷。
- **系统给出的原话**：`Validation Error: ...`、`... error: ...`。这往往才是真正的原因（见 2.4）。

注意：`window wait success` 只表示窗口打开了，**不是**业务成功。

### 2.2 异常链：第一段是原因，后面是“处理过程中又出的事”

Python 用 `During handling of the above exception, another exception occurred` 把多个异常串起来：

- **第一段（最先发生的异常）通常最接近原因。**
- 后面的段是处理第一段时又发生的：包装（`Exception: Add DDA/CCD Error!`）、框架退出（`SystemExit: 0`）、失败后截图（`save_img → OSError: screen grab failed`）。
- `SystemExit: 0` 来自 BeautifulReport 的 `_wrap`，**永远不是原因**，忽略。
- 截图函数里的异常（`save_img`、`ImageGrab.grab`）说明**截图证据缺失**，本身不是失败原因；但 `screen grab failed` 是“当时桌面不可用”的强信号。

> 常见错误：只看最后一行。最后一行几乎总是 `SystemExit: 0` 或 `screen grab failed`，看它会得出完全错误的结论。

### 2.3 堆栈帧：找到“项目代码里的最后一帧”

忽略框架和第三方库的帧（`unittest\`、`BeautifulReport`、`pywinauto\`、`PIL\`），只看项目代码（`test_case\`、`system_view\`、`base_view\`）：

- `test_xx_...`：哪个用例
- `las_xxx`（`system_view\LAS_view\las_functions_page.py`）：哪个**业务步骤**——这是写进 Jira 的“失败步骤”
- `win_xxx`（`base_view\win_base_view.py`）：哪个**底层操作**（输入、点击、选下拉框、设日期）

常见业务步骤含义（LAS 项目）：

| 函数 | 含义 | 失败在这里说明 |
|---|---|---|
| `las_search_policy` | 打开功能后查询保单 | 用例刚开始就失败，业务还没做 |
| `handle_popups` | 提交后处理弹窗 | 提交后系统弹出了提示，**弹窗文字就是关键证据** |
| `las_transaction_log` | 打开交易日志核对结果 | 业务已提交，失败在校验阶段 |
| `win_set_text` / `win_type_keys` | 输入文字 | 输入框找不到、不唯一、不可用，或桌面不可用 |
| `win_click_button` | 点击按钮 | 按钮找不到或不可用 |
| `win_select_option` | 选下拉框 | 下拉框没有这个选项 |
| `win_date_time_picker_set_time` | 设置日期控件 | 日期值或控件有问题 |

### 2.4 系统给出的原话优先于脚本的报错

脚本自己抛出的 `Exception: ...` 往往只是“失败了”的笼统说法。真正的原因在：

- 异常信息中 `pop-up error:` 后面的文字（弹窗处理函数读到的弹窗内容）
- 步骤日志中的 `Validation Error: ...`

> 实例：No.23 最后的异常是 `Exception: job cannot submit successfully`，看它什么也判断不了；步骤日志里有一句 `Validation Error: Contract is currently used by other user`——这才是原因：保单正被其他会话占用。

---

## 第 3 步：判断这个异常“说明了什么、没说明什么”

每种异常只证明有限的事情。**只写它证明了的部分。** 完整对照表见 `pywinauto-desktop.md`，最关键的几种：

### 3.1 掩盖型报错：报错本身不是原因

```
AttributeError: 'bool' object has no attribute 'type_keys'
TypeError: 'NoneType' object is not subscriptable
```

含义：前一步查找控件/窗口/数据时**没找到**，函数返回了 `False` 或 `None`，代码没有检查就继续使用。
- 证明了：前一步没找到某样东西。
- **没证明**：为什么没找到（控件变了？窗口没打开？被弹窗挡住？数据不存在？）。
- 结论：`NEEDS_HUMAN`（`masked_failure`），**不能**直接归为脚本问题，也**不能**归为产品缺陷。
- 下一步：打开报错所在行，看变量来自哪个查找函数、查的是什么；再看截图。
- 同时给出脚本改进建议：查找函数找不到时应直接抛出带控件名称的异常。

> 实例：No.3（`las_fund_allocation` 第 1681 行）、No.6（`las_reinstatement` 第 1127 行）、No.9（`las_add_card` 第 899 行）。

### 3.2 定位不唯一：一定是脚本要改

`ElementAmbiguousError: There are 3 elements that match the criteria {'best_match': 'PolicyEdit', ...}`
- 证明了：定位条件同时匹配到 3 个控件，脚本无法决定用哪个。
- 结论：`SCRIPT_ISSUE` `confirmed`（定位条件需要更精确）。
- 但要追问：**为什么会有 3 个？** 通常是前面用例留下了窗口（第 1.4 步）。

### 3.3 控件状态类：只说明“现在不能操作”

- `ElementNotEnabled`：控件是灰的。常见原因是业务规则（前面必填项没填、保单状态不允许）。→ `NEEDS_HUMAN`，看截图。
- `ElementNotVisible`：控件存在但看不见（页签没切换、区域被折叠、窗口被最小化）。→ `SCRIPT_ISSUE` `suspected`，看截图。
- `'Reversal' is not in list`：下拉框里没有这个选项。→ `SCRIPT_ISSUE` `suspected`；选项改名了是脚本问题，本该有却没有是产品问题。
- `Failed to set time in Date Time Picker`：日期没设进去。常见原因是日期超出控件允许范围（属测试数据），需要知道脚本要设的值。

### 3.4 环境类：报错文字本身就是证据

| 报错原文 | 直接原因 | 分类 |
|---|---|---|
| `There is no active desktop required for moving mouse cursor` | 执行机没有可交互桌面 | `ENVIRONMENT` confirmed |
| `pywintypes.error: (0, 'SetCursorPos', ...)` / `(2, 'SetCursorPos', ...)` | 同上（无法移动鼠标） | `ENVIRONMENT` confirmed |
| `PIL ... OSError: screen grab failed` | 无法截屏（桌面不可用的信号） | 只作为证据，不单独分类 |
| `A transport-level error has occurred` / `An existing connection was forcibly closed by the remote host` | 被测系统与数据库连接中断 | `ENVIRONMENT` confirmed |

---

## 第 4 步：按“弹窗文字的含义”分类弹窗

桌面端的弹窗**多数不是干扰**，而是被测系统在告诉你出了什么事。先读文字，再分类：

| 弹窗文字（例） | 含义 | 分类 |
|---|---|---|
| `Transaction failed: A transport-level error ...` | 后台连接中断 | 环境问题 |
| `Contract is currently used by other user` | 保单被占用 | 测试数据问题（查占用来源） |
| `Cannot get MSP Config` | 缺少系统配置 | 需人工：环境配置缺失还是缺陷 |
| `Unhandled exception has occurred ...`（.NET） | 被测程序崩溃 | 疑似产品缺陷 |
| `pop-up error:` 后面是空的 | 弹窗出现了但没读到文字 | 需人工：看截图；改进弹窗读取 |
| `Record Submitted. Letter will be print out during EOD` | 正常的成功提示 | 不是问题 |
| `Are you sure want to delete this client?` | 正常的确认框 | 不是问题 |

只有与被测功能**无关**、且在 `popup-catalog.md` 干扰清单里的弹窗，才能归为“弹窗干扰”。

注意 `no Microsoft .NET Framework window` 是脚本打印的“**没有**出现 .NET 崩溃窗口”，是排除性信息，不是报错。

---

## 第 5 步：核对截图

**先判断截图是否有效，再看内容。** 详细清单见 `evidence-and-screenshots.md`。

1. 是不是这个用例失败那一刻的画面？
   - 日志里截图函数报了 `screen grab failed` → 这个用例**没有**有效截图；报告里显示的图片不能用。
   - 截图里任务栏时间、系统日期是否与用例执行时间吻合。
   - 窗口标题是否是这个用例的功能（例如用例是 Service Fee，截图却停在 Billing Change）。
   - 截图里的保单号是否是这个用例的测试数据。
2. 截图拍的是**失败处理之后**的画面：弹窗处理函数可能已经把弹窗关掉了，截图里看不到弹窗不代表没有弹窗。
3. 只写看得见的东西，写清楚位置：“前台窗口标题为 Transaction Log / Policy Notes，表格第 1 行 Trans Status 为 COMPLETED”。
4. 小控件（勾选框、单选框、灰色按钮）、密集表格里的数字：**不要凭截图下结论**，写“截图中无法确认”，并建议用控件状态信息核对。
5. 截图与日志对照：
   - 一致（例如日志 `trans_status:COMPLETED`，截图交易日志表格也显示 COMPLETED）→ 互相印证，可以提升结论强度。
   - 矛盾 → 先排查截图是否有效（时间、窗口、保单号）；仍矛盾 → `NEEDS_HUMAN`（`conflicting_evidence`），写明矛盾点。

---

## 第 6 步：写结论

每条结论按这个格式写，缺一项都不算完成：

```
分类：<七类之一>（confirmed / suspected）
现象：<报错原文，带证据编号>
直接原因：<证据支持到哪里就写到哪里>
根因：<有证据就写；没有就写“待确认：……”>
依据：<E1 …；E3 …>
反证检查：<如果结论是错的，会看到什么？是否看到了？>
下一步：<谁、去哪里、看什么、看到什么就改成什么>
```

**反证检查**的例子：
- 判为“环境问题（桌面不可用）”：如果不是环境问题，断崖内应该有用例走过了 `las_search_policy`。检查：26 个用例全部停在第一次输入，没有一个走过 → 结论成立。
- 判为“结果校验阶段的脚本问题”：如果业务其实没成功，步骤日志里不会有 `Job submitted`。检查：有 → 成立；但仍建议在系统交易日志里确认这笔交易。

---

## 第 7 步：提交前自检

- [ ] 我看的是异常链的**第一段**，不是最后一行。
- [ ] 我忽略了 `SystemExit: 0` 和截图函数里的异常。
- [ ] 我找到了项目代码里的失败位置（业务步骤函数 + 底层操作）。
- [ ] 我先看了步骤日志里的系统原话和业务成功标记。
- [ ] 掩盖型报错（`'bool'/'NoneType' object ...`）我没有直接归为脚本问题。
- [ ] 弹窗是按文字含义分类的，不是一律算“干扰”。
- [ ] 我检查了断崖、通过用例里的同样报错、同功能对比、残留窗口。
- [ ] 截图我先验证了有效性；看不清的细节我写了“无法确认”。
- [ ] 结论没有超出证据：根因没有证据就写“待确认”。
- [ ] 同一原因的用例合并在一起，没有逐个提单。

---

## 附：2026-10-30 LAS HK 回归（51 个用例，40 个失败）的完整归因

这是用上面方法得出的结果，作为范例和回归测试数据（`evals/las_hk_20261030/`）。

| 汇总编号 | 用例 | 分类 | 状态 | 关键证据 | 下一步 |
|---|---|---|---|---|---|
| 26–51（26 个） | test_30 … test_73 | 环境问题 | confirmed | `There is no active desktop`；全部停在第一次输入；截图失败 | 环境负责人确认执行机 RGT_AVD_11 当时的会话状态；修复后整组重跑 |
| 7 | test_08 PartialSurrender | 环境问题 | confirmed | 弹窗原文 `transport-level error`；通过的 No.15 有同样报错 | 确认该时段数据库连接；重跑 |
| 23 | test_27 PaidToDateAdvance | 测试数据问题 | confirmed | `Validation Error: Contract is currently used by other user` | 查占用来源（前面失败用例未关窗口？其他批次？）；释放后重跑 |
| 5 | test_05 TraditionalPartialSurrender | 脚本问题 | confirmed | 已 `Job submitted`；校验时 `ElementAmbiguousError`（3 个 PolicyEdit） | 改定位条件；查残留窗口；在交易日志确认这笔交易 |
| 14 | test_17 FullContractReversal | 脚本问题 | suspected | 已 `Reversal succeeded`；校验时 `'Reversal' is not in list` | 确认下拉框实际选项名 |
| 4 | test_04 ADD_PDA | 脚本问题 | suspected | `ElementNotVisible`（`las_add_pdf` 第 2042 行） | 看截图：页签/区域/窗口状态 |
| 24 | test_28 DPMSServiceFee_Register | 脚本问题 | suspected | `Failed to set time in Date Time Picker` | 确认要设的日期值与控件允许范围 |
| 3、6 | test_03 FundAllocation、test_06 Reinstatement | 需人工判断 | suspected | `'bool' object has no attribute 'type_keys'`（掩盖型） | 看报错行的查找函数；看截图 |
| 9 | test_11 Billing_Change_Monthly | 需人工判断 | suspected | `'NoneType' object is not subscriptable`（掩盖型，`las_add_card`） | 同上；重点查添加卡片用的数据 |
| 10 | test_12 Billing_Change_Half_Annually | 需人工判断 | suspected | 弹窗 `Cannot get MSP Config`；同功能 Annually 通过 | 问开发/配置负责人：半年缴的配置在测试环境是否应存在 |
| 2 | （Add booster/PDF） | 需人工判断 | suspected | 弹窗出现但文字为空 | 看截图；改进弹窗文字读取 |
| 17 | test_21 ServiceFee_termination | 需人工判断 | suspected | 找不到 Transaction Log 窗口 | 看截图；重跑 |
| 20 | test_25 CoverageMaintenance | 需人工判断 | suspected | `ElementNotEnabled` | 看截图确认哪个按钮、为什么灰 |
| 25 | test_29 DPMSServiceFee_termination | 需人工判断 | suspected | `ElementNotEnabled` + 截图失败；断崖前一个 | 先重跑 |

合计：环境问题 27、测试数据 1、脚本问题 4（confirmed 1）、需人工判断 8。**本次没有可以确认的产品缺陷**；需要逐个人工看的只有 13 个，其余 27 个按 2 个环境原因各提 1 张单（或 1 条环境事件）即可。
