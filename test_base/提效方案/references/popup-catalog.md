# 弹窗识别与处理手册

自动化测试中的“弹窗”有三种，来源不同，Selenium 的反应不同，解决办法也不同。先判断是哪一种，再处理。

## 三种弹窗对照

| | ① 浏览器原生对话框 | ② 网页内弹框 | ③ 浏览器 / 系统弹窗 |
|---|---|---|---|
| 是什么 | 网页调用 `alert()`、`confirm()`、`prompt()`，或离开页面时的 `beforeunload` 提示 | 网页自己用 HTML 画出来的框：报错框、公告、Cookie 提示、会话超时提示 | Edge/Chrome 自己的提示（保存密码、恢复页面、允许通知、翻译、下载），或 Windows 的提示（安全警告、更新、证书） |
| 外观 | 浏览器标准样式，顶部写着网址 | 和网站风格一致，比如 ROTQA-5339 截图里带蓝色 OK 按钮的框 | 浏览器地址栏下方的气泡，或独立的系统窗口 |
| Selenium 表现 | 抛出 `UnexpectedAlertPresentException`，异常对象里带弹窗文字 | 不会被当作 alert；常见报错是 `ElementClickInterceptedException`（点击被挡住），或 `NoSuchElementException`、`TimeoutException` | Selenium 看不到；表现为点击没反应、输入丢失、超时 |
| Selenium 截图能否看到 | 一般看不到，截图时甚至可能再次报错 | 能看到 | 看不到 |
| Selenium 能否关掉 | 能：`driver.switch_to.alert.accept()` 或 `.dismiss()` | 能：找到关闭按钮点击 | **不能**，所以“有时候关不掉” |
| 分诊需要的证据 | 异常里的 `alert_text` | `popup_evidence.dialogs` 里的弹框文字和 class；遮挡元素的 HTML | 整屏截图（`fullscreen_screenshot`） |

## 如何在报错里找到弹窗线索

报错信息不会直接写“弹窗”，但有几个固定特征：

1. **`UnexpectedAlertPresentException`**：异常信息中通常有 `Alert Text: ...` 或 `{Alert text : ...}`，后面就是弹窗文字。
2. **`ElementClickInterceptedException`**：异常信息格式为
   `element click intercepted: Element <button id="submit"> is not clickable at point (x, y). Other element would receive the click: <div class="modal-backdrop fade show">`
   `Other element would receive the click:` 后面就是挡住点击的元素。class 含 `modal`、`dialog`、`popup`、`overlay`、`mask`、`backdrop` 时，基本可以确定是网页弹框挡住了。
3. **找不到元素或超时，但截图里有框**：说明弹框出现后页面被遮挡或跳转了。
4. **找不到元素或超时，截图里什么都没有，但整屏截图里有框**：说明是浏览器或系统弹窗。

## 接入证据收集（一次性改造）

把 `scripts/popup_evidence.py` 接入测试框架（方法见该文件顶部说明）。接入后，每个失败用例会自动保存：

- 原生对话框的文字；
- 页面内所有可见弹框的文字、class、id；
- 当前网址、页面标题；
- Selenium 截图和整屏截图；
- 浏览器版本、驱动版本。

没有接入之前，弹窗类问题大多只能落入 `NEEDS_HUMAN`。

## 从源头减少弹窗

### 原生对话框

浏览器启动时设置 W3C 标准能力 `unhandledPromptBehavior`：

```python
options.set_capability("unhandledPromptBehavior", "ignore")
```

- `ignore`：弹窗出现时不自动处理，脚本抛出异常并保留弹窗文字，方便收集证据。**分诊阶段建议用这个。**
- `accept` / `dismiss`：自动点确定 / 取消。可以让用例继续跑，但会掩盖问题，**不建议在回归中使用**。

### 浏览器自带弹窗（Edge）

```python
from selenium.webdriver.edge.options import Options

options = Options()
options.add_argument("--inprivate")                 # 每次使用干净的浏览器配置
options.add_argument("--no-first-run")
options.add_argument("--no-default-browser-check")
options.add_argument("--disable-notifications")
options.add_argument("--disable-features=Translate")
options.add_experimental_option("prefs", {
    "credentials_enable_service": False,            # 不提示保存密码
    "profile.password_manager_enabled": False,
    "profile.default_content_setting_values.notifications": 2,  # 禁止通知请求
    "download.prompt_for_download": False,          # 下载不弹框
})
```

公司电脑上由 IT 统一管理的浏览器策略（组策略 / Intune）可能会覆盖这些设置。如果设置后仍然出现，把整屏截图发给 IT，请他们为测试机关闭对应策略。

### 网页内弹框

- **公告、Cookie 提示**：请开发在测试环境提供关闭开关（例如配置项或 Cookie），或者在用例开始前统一关闭一次。
- **会话超时提示**：用例时间过长导致。缩短单个用例的执行时间，或者在测试环境延长会话时间。
- **业务报错框**：**不要自动关闭了事。** 它是系统返回的真实错误，要截图保存并按 `taxonomy.md` 第 4 类处理。

### 统一的弹窗处理函数（可选）

对于确认属于干扰的网页弹框，可以在脚本里加一个统一的处理函数，在关键操作前调用。**只处理 `rules.yaml` 中 `noise_popups` 列出的弹框，其他弹框一律保留并让用例失败。**

```python
def dismiss_known_noise(driver, noise_patterns, close_selectors):
    """只关闭清单内的干扰弹框，返回关闭记录，供报告使用。"""
    closed = []
    for el in driver.find_elements("css selector", "[role=dialog],.modal,.popup"):
        if not el.is_displayed():
            continue
        text = el.text.strip()
        if any(p.lower() in text.lower() for p in noise_patterns):
            for sel in close_selectors:
                btns = el.find_elements("css selector", sel)
                if btns:
                    btns[0].click()
                    closed.append(text[:200])
                    break
    return closed
```

关闭记录要写入测试报告，这样即使用例通过，也能统计干扰弹窗出现的频率。

## 已知弹窗清单

> 本清单需要测试团队根据实际情况持续补充。新增时同步更新 `config/rules.yaml`。下面的条目是首批示例，**上线前请逐条核实是否符合你们系统的实际文字**。

| 编号 | 弹窗文字（关键字） | 类型 | 性质 | 来源 | 处理方式 |
|---|---|---|---|---|---|
| P001 | Agent record not found | ② 网页弹框 | **业务报错** | NBS 系统返回 | 按数据问题 / 产品缺陷处理（见 ROTQA-5339） |
| P002 | Your session has expired / 會話已逾時 | ② 网页弹框 | 干扰 | 用例耗时过长 | 缩短用例或延长测试环境会话时间 |
| P003 | Save password? / 要保存密码吗 | ③ 浏览器 | 干扰 | Edge 密码管理器 | 浏览器启动参数关闭 |
| P004 | Restore pages? / 还原页面 | ③ 浏览器 | 干扰 | 浏览器上次异常退出 | 使用 `--inprivate` 或新建配置目录 |
| P005 | Leave site? Changes you made may not be saved | ① 原生对话框 | 视情况 | 页面 `beforeunload` | 用例中途跳转导致；检查脚本流程 |
| P006 | We use cookies | ② 网页弹框 | 干扰 | 网站 Cookie 提示 | 用例开始时统一关闭 |
| P007 | System Notice / 系統公告 | ② 网页弹框 | 干扰 | 测试环境公告 | 请开发提供测试环境关闭开关 |

## 弹窗统计

`classify_rules.py` 会在 `classified.json` 的 `summary.popups` 中输出本次运行所有弹窗的文字、出现次数、所在页面。连续多次出现的同一弹窗，应该从源头解决，而不是每次在脚本里关闭。
