# 文档对比助手（doc-compare-assist）

给同事A 的 PDF 对比用。识别、对比、过滤都还是他自己的脚本，这个工具只做三件事：

1. **选文件**：baseline、新文件两个文件夹按 Case 编号自动配对，生成 `pairs.csv`，可以在 Excel 里勾选只对比其中几对。
2. **批量对比、放整齐**：逐对调用他的对比函数，一个 Case 一个文件夹；他已经跑好的结果也可以直接整理（collect）。
3. **看文件、出交付物**：生成 `index.html` 索引页（Case 列表、搜索、只看有变化的、页面里直接打开他的 total / ignore / difference），以及 `文档变化对比.docx`、`文档变化对比.xlsx`：每处变化一条，字段、原值、新值、变化，加上新旧 PDF 对应位置的截图（变化处红框）。

## 一、第一次使用

```
pip install -r requirements.txt
copy config\dca.example.json config\dca.json      然后改 a_script.path 等（见下面“二”）
python evals\test_dca.py                           应输出“全部通过”
python scripts\dca.py check                        应输出“环境检查通过”
```

## 二、日常使用

最简单：双击 `一键对比.bat`，按提示把 baseline 文件夹、新文件文件夹拖进窗口，回车。做完会自动打开索引页。

命令行：

```
python scripts\dca.py all --baseline-dir D:\baseline --new-dir D:\new
python scripts\dca.py all --baseline-dir D:\baseline --new-dir D:\new --results-dir D:\他的结果    只整理不重跑
```

分步（要先挑文件时）：

```
python scripts\dca.py pairs --baseline-dir D:\baseline --new-dir D:\new     生成 runs\<时间>\pairs.csv
（用 Excel 改“选中”列 Y / N，保存）
python scripts\dca.py run --batch runs\<时间>
python scripts\dca.py report --batch runs\<时间>
```

`--config` 要写在命令名前面：`python scripts\dca.py --config my.json all ...`

## 三、结果

```
runs\<时间>\
  index.html              索引页，双击打开
  文档变化对比.docx        交付物（Word，横向，每处变化一张对照表）
  文档变化对比.xlsx        交付物（Excel，“差异”表一行一处变化，截图嵌在单元格里；“汇总”表每个 Case 一行）
  pairs.csv               配对清单
  report.json             数量统计、出错的 Case
  cases\<Case>\           他的 difference / total / ignore 原文件、shots\ 截图、run.log 他脚本的输出
```

## 四、明天要确认的事

| # | 要确认什么 | 怎么确认 / 怎么改 |
|---|---|---|
| 1 | 他的对比脚本文件在哪、类名叫什么、创建类要不要参数 | 填 `a_script.path`（类名可以先不填），运行 `check`：显示“✓ 找到对比函数”就行；报错会列出文件里有哪些类 |
| 2 | file1 是 baseline 还是新文件 | 问他平时怎么调用；不是 baseline 就把 `baseline_is_file1` 改成 false |
| 3 | 他的函数是否真的写到我们传的路径 | 先对一对文件跑 `all`，看 `cases\<Case>\` 里有没有 difference、total；没有就看 run.log，改用 collect |
| 4 | difference 文件是什么格式 | 对他的一个 difference 文件运行 `inspect`，看“读出差异 N 条”和他页面上的数量是否一致；不一致按 `references\adapting.md` 第三节调整 |
| 5 | 文件名怎么配对 | 默认按 `Case7` 这种编号；`pairs` 输出里有 ✗ 或配错时改 `pairing.key_regex` |
| 6 | 截图位置准不准 | 打开索引页抽查 5–10 条；“截图待补”多时把 `screenshot.y_tolerance` 调成和他脚本一样再 `report` |
| 7 | 交付物格式 | 打开 docx、xlsx 看是不是他想要的；标题在 `deliver.title`，不要 Word 或 Excel 就把对应项改成 false |

## 五、要注意的

- 程序只读他的结果和 PDF，不改他的脚本、不调用任何 AI，所有值照抄他的结果。
- 只差空格的变化默认不放进交付物（`difference.skip_space_only`）。
- 截图没有打码；交出去之前要不要打码，先和他确认。
- 这套程序还没在真实环境运行过，第一次用请按“四”逐条核对。
