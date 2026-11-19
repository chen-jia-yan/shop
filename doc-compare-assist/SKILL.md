---
name: doc-compare-assist
description: 文档对比助手。替同事A 批量调用他自己的 PDF 对比脚本（识别、对比、过滤都用他的），把一大堆 total / ignore / difference 结果整理成一个可搜索的索引页，并生成可以直接交给别人的 Word 和 Excel：只放变化的字段、原值、新值和新旧 PDF 对应位置的截图。用于 Policy Schedule 等产品文档的新旧版本对比。
metadata:
  version: "0.1.0"
---

# 文档对比助手（doc-compare-assist）

## 什么时候用

用户要对比一批新生成的 PDF 和 baseline，想要“哪些地方变了”的整理结果或交付文件。典型说法：“对比这两个文件夹”“把这批对比结果整理一下”“出一份变化对比给产品组”。

## 铁律

1. **对比和过滤只用同事A 的脚本。** 不改他的代码，不自己另做对比，不决定什么可以忽略。
2. **值只来自他的结果。** 交付物、汇报里的每个值都是从他的 difference / total 文件里读出来的，不改写、不补全、不换算。
3. **截图找不到就写“截图待补”。** 不凭猜测框位置；多处相同时程序已经写明“请核对”，汇报里照实转述。
4. **先给用户看配对清单。** 对比前把 pairs 的结果列给用户确认，用户说只对比其中几对时，改 pairs.csv 的“选中”列。
5. **数据不出本机。** 不把文件内容、截图发到任何外部服务。

## 步骤

### 第 1 步：检查环境

```bash
pip install -r requirements.txt
python evals/test_dca.py          # 应输出“全部通过”
python scripts/dca.py check       # 检查库、配置、能不能找到他的对比函数
```

没有 `config/dca.json` 时，提醒用户从 `config/dca.example.json` 复制一份，至少填好 `a_script.path`。

### 第 2 步：选文件

```bash
python scripts/dca.py pairs --baseline-dir <baseline 文件夹> --new-dir <新文件文件夹>
```

把输出的配对清单（✓ / ✗ 和原因）列给用户。用户要排除或改路径时，改批次文件夹里的 `pairs.csv`。

### 第 3 步：对比（二选一）

- 让他的脚本重新跑：`python scripts/dca.py run --batch <批次文件夹>`
- 他已经跑好了，只整理：`python scripts/dca.py collect --batch <批次文件夹> --results-dir <他的结果文件夹>`

### 第 4 步：整理和交付物

```bash
python scripts/dca.py report --batch <批次文件夹>
```

批次文件夹里会有：`index.html`（索引页）、`文档变化对比.docx`、`文档变化对比.xlsx`、`report.json`、`cases/<Case>/`（他的原始结果、截图、运行日志）。

一步做完也可以：`python scripts/dca.py all --baseline-dir ... --new-dir ...`（加 `--results-dir` 就是只整理不重跑）。

### 第 5 步：汇报

读 `report.json` 和终端输出，用中文汇报后停下：

```
共 N 个 Case，有变化的 X 个，共 M 处变化；截图待补 K 处。
出错：Case12（他的脚本退出了，见 cases/Case12/run.log）     ← 没有就写“无”
交付物：<批次>/文档变化对比.docx、.xlsx；索引页：<批次>/index.html
```

只报数量和文件位置，不逐条复述变化内容（用户在索引页里看）。截图待补的，提醒用户在索引页里核对后手工补。

## 读不懂他的结果时

`report` 读出 0 条但他的页面里明明有差异，或者字段、值读错了：

```bash
python scripts/dca.py inspect <他的 difference 或 total 文件>
```

把输出给用户看，按 `references/adapting.md` 调整 `config/dca.json` 的 `difference` 部分；格式特殊时写一个 `custom_parser`。不要改他的脚本。

## 文件

- `scripts/dca.py`：命令入口
- `scripts/pairing.py`：选文件、配对、pairs.csv
- `scripts/runner.py`：调用他的脚本 / 整理现有结果
- `scripts/diff_parse.py`：读他的 difference / total，取出原值、新值、字段名
- `scripts/shots.py`：回到 PDF 找位置、截图、画框
- `scripts/deliver.py`：Word、Excel
- `scripts/index_page.py`：索引页
- `config/dca.example.json`：配置说明
- `references/adapting.md`：对接他的脚本和结果格式
- `evals/test_dca.py`：测试
