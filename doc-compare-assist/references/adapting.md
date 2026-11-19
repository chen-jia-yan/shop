# 对接同事A 的脚本和结果格式

这个 skill 不改他的脚本。对接只靠 `config/dca.json`，格式特殊时再加一个解析文件。

## 一、调用他的对比函数

已知（11-19 他给的代码）：

```python
def policySchedule_compare_file_differences_and_total(self, file1, file2, difference_result_path,
        total_result_path, ignore_result_path, ignore_info_path, y_tolerance=0)
```

- 带 `self`，所以多半在一个类里。`a_script.class` 留空时会自动找含有这个函数的类；有多个时报错，请填类名。
- 创建类要参数时填 `init_args`，例如 `["D:/config.ini"]`。
- `file1` 是 baseline 还是新文件：他的 `get_ignore_info` 只从 file1 收集要忽略的内容。默认 `baseline_is_file1: true`，和他平时的用法不一致时改成 false。
- 他脚本里用了相对路径（读配置、模板）时，`workdir` 填他的项目目录。
- 他的函数写在模块最外层、却带 self 时也能调用：程序会补一个 self，`self.get_ignore_info` 会找到同一个文件里的 `get_ignore_info`。
- 他不想被导入、只想当命令运行时：`mode` 改成 `command`，`command` 写成命令行，可以用 `{baseline}` `{new}` `{difference}` `{total}` `{ignore}` `{ignore_info}` `{case_dir}`。

检查：`python scripts/dca.py check` 出现“✓ 找到对比函数”就对了。

## 二、他的结果写到哪

程序把四个输出路径传给他的函数（`outputs`）。运行后先找这四个文件，找不到再在 Case 文件夹里按 `existing` 的文件名规则找。都找不到时报“没有生成 difference / total 文件”，看 `cases/<Case>/run.log`，多半是他的函数忽略了传入的路径、写到了固定目录。这种情况改用 collect：让他照常跑，再用 `collect --results-dir <他的输出目录>` 整理。collect 按文件名里的 Case 编号（文件名里没有时看上一级文件夹名）把结果挂到每一对 PDF 上。

## 三、读他的 difference / total

`python scripts/dca.py inspect <文件>` 会输出：识别成什么格式、读出几条、前 8 条的行号、页码、字段、原值 → 新值。

| inspect 显示 | 怎么办 |
|---|---|
| 识别为 htmldiff，条数和他页面上一致 | 不用改 |
| 识别为 htmldiff，但条数是 0 | 他可能只把变化写进了 total，`difference.source` 改成 `["total"]` |
| 识别为 lines，前 40 行里能看到“旧值一行、新值一行” | 按实际写法改 `old_line` / `new_line` 两个正则（括号里是值） |
| 都不是 | 写 `config/my_parser.py`，`format` 改成 `custom`，`custom_parser` 填路径 |

`my_parser.py` 的样子：

```python
def parse(path):
    # 读他的文件，返回每一处变化
    return [{"old": "Premium : 587.85", "new": "Premium : 600.00",
             "line_old": 12, "line_new": 12,          # 可选：行号
             "page_old": 3, "page_new": 3,            # 可选：页码，有的话截图更准
             "field": "Premium"}]                     # 可选：字段名，不给就取冒号前面的标签
```

## 四、截图

拿原值 / 新值回到 PDF 里找：整行一样 → 包含在某一行里 → 上下 2–4 行拼起来包含。有页码时先在那一页找。

- 找不到：写“截图待补”。常见原因是他提取文字的方式和 pdfplumber 不同（比如他用 `y_tolerance=0`，一行被拆开）。可以把 `screenshot.y_tolerance` 调成和他一致再试。
- 多处相同：按行号在文件里的前后位置推断是哪一处，并写明“请核对”。
- 只框变化的词；变化的词在 PDF 里对不上时框整行。
