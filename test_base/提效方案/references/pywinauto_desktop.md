# Windows 桌面端自动化（pywinauto + unittest/BeautifulReport）报错解读

适用于 LAS（Life Administration）这类 Windows 程序的回归：测试代码在 `test_case\`，业务步骤在 `system_view\`，底层操作在 `base_view\win_base_view.py`，报告由 BeautifulReport 生成。

每一项都写明：**它证明了什么、没有证明什么、归哪一类、下一步做什么。**

---

## 1. 读日志的固定顺序

1. 步骤日志（Traceback 之前的文字）：业务走到哪一步？有没有 `Job submitted`、`succeeded`、`COMPLETED`？有没有 `Validation Error:`？
2. 异常链第一段：最先发生的异常是什么？
3. 项目代码里的最后一帧：哪个业务步骤（`las_xxx`）、哪个底层操作（`win_xxx`）？
4. 异常信息里有没有 `pop-up error:`？后面的文字是什么？
5. 后面的段：有没有 `save_img … screen grab failed`？（有 → 截图无效、桌面可能已不可用）
6. 忽略 `SystemExit: 0`（BeautifulReport `_wrap` 退出，永远不是原因）。

---

## 2. 异常对照表

### 2.1 环境类（执行机）

| 报错 | 证明了什么 | 没证明什么 | 分类 |
|---|---|---|---|
| `RuntimeError: There is no active desktop required for moving mouse cursor!` | 当时没有可交互桌面，pywinauto 无法移动鼠标 | 桌面为什么没了（最小化、断开、锁屏、会话超时） | 环境 confirmed |
| `pywintypes.error: (0, 'SetCursorPos', 'No error message is available')` | Windows 拒绝移动鼠标 | 同上 | 环境 confirmed |
| `(2, 'SetCursorPos', 'The system cannot find the file specified.')` | 同上（另一种错误码） | 同上 | 环境 confirmed |
| `OSError: screen grab failed`（在 `save_img` 里） | 当时无法截屏 | 不是这个用例失败的原因，只说明截图缺失 | 不单独分类；作为“桌面不可用”的佐证 |

**背景知识（pywinauto 官方文档《Remote Execution Guide》）：**
- 远程桌面（RDP）窗口**最小化**时，远程机器默认没有活动桌面；RDP **断开**时，桌面被锁定。两种情况下 GUI 自动化都会失败。
- 在锁定的机器上不能工作的方法包括：`click_input` 等 `_input` 结尾的鼠标方法、`set_focus`（它使用 `SetCursorPos` 和 `SetForegroundWindow`）、`type_keys`。
  本次报错的调用链正是 `win_type_keys → type_keys → set_focus → mouse.move → _set_cursor_pos`，与文档描述一致。
- 可以在锁定状态下工作的替代方法（`win32` 后端）：`send_chars`、`send_keystrokes`、`set_edit_text`（视程序而定）。
- 通过 CI 代理触发时，代理必须**以普通程序方式运行**；以服务方式或通过 SSH 运行时 GUI 测试无法工作。
- 规避办法：不要最小化或断开 RDP 窗口；或使用 VNC；文档还链接了 TestComplete 关于“在最小化的远程桌面窗口中运行”“断开远程桌面时保持解锁”的做法。

执行机名 `RGT_AVD_11` 看起来是 Azure Virtual Desktop 的机器（推测，需要环境负责人确认）；它同样基于远程桌面会话，上述限制同样适用。

### 2.2 环境类（被测系统后台）

| 报错（通常出现在 `pop-up error:` 后面） | 含义 | 分类 |
|---|---|---|
| `A transport-level error has occurred when sending the request to the server` | 被测程序与 SQL Server 的连接在传输中断开 | 环境 confirmed |
| `An existing connection was forcibly closed by the remote host` | 对端强制关闭了连接 | 环境 confirmed |
| `A network-related or instance-specific error occurred` | 连不上数据库 | 环境 confirmed |
| `Timeout expired. The timeout period elapsed ...` | 数据库操作超时 | 环境 confirmed（反复出现在同一功能时考虑性能缺陷） |

### 2.3 控件查找类

| 报错 | 证明了什么 | 没证明什么 | 分类与下一步 |
|---|---|---|---|
| `ElementAmbiguousError: There are N elements that match the criteria {...}` | 定位条件匹配到多个控件 | 为什么有多个（常见：前面用例留下的窗口） | 脚本 confirmed；改定位条件，查残留窗口 |
| `MatchError: Could not find 'X' in 'dict_keys([...])'` | 当时顶层窗口里没有 X；`dict_keys` 里列出了当时**实际**打开的窗口 | X 为什么没打开 | 需人工；先看列出的窗口：有其他功能的窗口 → 残留；只有主菜单 → 前一步没打开窗口 |
| `pywinauto.timings.TimeoutError` | 等待超时 | 等的是什么、为什么没等到——看同一条日志后面的段 | 结合后面的 `MatchError` 等判断 |
| `ElementNotFoundError` | 没找到控件 | 原因 | 需人工；看截图 |
| `Exception: Can't find window X`（项目代码自己抛出） | 等窗口 X 失败 | 原因 | 需人工；看截图；重跑 |

### 2.4 控件状态类

| 报错 | 证明了什么 | 没证明什么 | 分类与下一步 |
|---|---|---|---|
| `ElementNotEnabled`（`verify_enabled`） | 控件存在但是灰的 | 为什么灰：必填项没填？保单状态不允许？前一步没完成？ | 需人工；看截图找提示；数据不满足 → 测试数据；步骤漏了 → 脚本；条件都满足 → 疑似缺陷 |
| `ElementNotVisible`（`verify_visible`） | 控件存在但不可见 | 为什么不可见：页签没切、区域折叠、窗口最小化 | 脚本 suspected；看截图 |
| `ValueError: 'X' is not in list`（`win_select_option` / `select`） | 下拉框里没有选项 X | 选项改名了还是本该有却没有 | 脚本 suspected；确认实际选项 |
| `RuntimeError: Failed to set time in Date Time Picker` | 日期没有设进控件 | 要设的值是什么；控件允许的范围 | 脚本 suspected；常见原因是日期超出范围（测试数据） |

### 2.5 掩盖型（报错本身不是原因）

| 报错 | 含义 | 分类与下一步 |
|---|---|---|
| `AttributeError: 'bool' object has no attribute 'type_keys'` | 前一步的查找函数没找到控件，返回了 `False` | 需人工（`masked_failure`）；打开报错行看变量来自哪个查找函数；看截图 |
| `TypeError: 'NoneType' object is not subscriptable` | 前一步返回了 `None`（没找到控件、没读到数据、查询没结果） | 同上；如果变量来自测试数据或查询结果，重点查数据 |
| 其他 `'NoneType' object has no attribute ...` | 同上 | 同上 |

**脚本改进建议（写进 Jira 或改进清单）：** 查找函数找不到时直接抛出带控件名称的异常（例如 `ControlNotFound: Fund Code 输入框`），不要返回 `False`/`None`。这样下一次报错本身就说明了原因。

### 2.6 包装型（只说“失败了”）

| 报错 | 真实原因去哪里找 |
|---|---|
| `Exception: job cannot submit successfully` | 步骤日志里的 `Validation Error:`；截图 |
| `Exception: Add DDA/CCD Error!` | 异常链第一段（例如 `TypeError ... las_add_card 第 899 行`） |
| `Exception: Job submitted failed, pop-up error: <文字>` | `<文字>` 就是弹窗内容，按 `popup-catalog.md` 第 4 节分类 |
| `Exception: Job submitted failed, pop-up error:`（后面为空） | 弹窗出现了但没有读到文字 → 看截图；改进弹窗读取 |

---

## 3. 业务步骤与失败阶段

| 阶段 | 日志特征 | 失败在这里意味着 |
|---|---|---|
| 准备 | `window wait success` 后立即失败；失败在 `las_search_policy` | 业务还没开始；多为环境或窗口问题 |
| 录入 | 失败在 `win_set_text` / `win_type_keys` / `win_select_option` / `win_date_time_picker_*` | 输入控件或输入值的问题 |
| 提交 | 失败在 `handle_popups`；异常带 `pop-up error:` | 系统拒绝了提交，**弹窗文字是关键** |
| 校验 | 步骤日志已有 `Job submitted` / `succeeded`；失败在 `las_transaction_log` | 业务大概率已完成；多为校验脚本问题；建议在交易日志中人工确认这笔交易 |

---

## 4. 本项目已知的正常输出（不是报错）

- `no Microsoft .NET Framework window`：脚本检查后**没有**发现 .NET 未处理异常窗口（排除性信息）。
- `If policy with reg cont, pls remember goes to coverage maintenance update the reg cont premium`、`Record Submitted. Letter will be print out during EOD`：系统的正常提示。
- `Are you sure want to delete this client?`：正常的确认框。
- `xxx window wait success`：窗口打开了（不代表业务成功）。
