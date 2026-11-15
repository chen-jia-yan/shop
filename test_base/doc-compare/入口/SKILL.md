---
name: doc-compare
description: 对比两份产品文档（PDF），找出新文件和 baseline 的真实差异。日期、人名的变化自动忽略但全部留档；内容相同只是位置不同的不算差异；每条差异截出两份 PDF 的对应位置并框出来，按负责人打包。用于 Policy Schedule 等产品说明文件的版本对比。
metadata:
  version: "1.0.0"
---

# 文档对比（doc-compare）

## 什么时候用

用户要对比新生成的产品文档（PDF）和 baseline，找出哪些内容变了、要发给谁核对。典型输入：两个文件夹（baseline、新文件），文件名里有 Case 编号，例如 `Case7_PolSchedule-BZ600_72624_....pdf`。

## 铁律

1. **值只来自 PDF 原文。** 报告里的每一个数字、每一段文字都是脚本从 PDF 读出来的。你不得改写、补全、换算任何值，也不得凭印象说某个值“应该是多少”。
2. **你不决定什么可以忽略。** 忽略规则只在 `scripts/filters.py` 和 `config/doc_compare.json` 里。你发现可能该忽略的内容，只能在汇报里提出建议，由用户确认后再改配置。
3. **只读打码后的结果。** 写汇报时只读 `result.masked.json`，不读 `result.json`、`ignore.html`，也不打开 PDF 或截图。不把文件内容发到任何外部服务。
4. **没比较的页要说出来。** 结果里有“没有文字层的页”（扫描页）或“大部分是图片的页”时，必须在汇报第一段写明哪些页没有比较，不能说成“没有差异”。
5. **不确定的不替用户判断。** “不确定”的条目原样列出原因，不要猜它是不是真差异。
6. **未经验收不替换现有做法。** 在 `evals/check_acceptance.py` 输出“验收通过”之前，结果只能和同事A 现有脚本的结果并行参考。

## 步骤

### 第 1 步：检查环境

```bash
pip install -r requirements.txt
python evals/test_core.py
```

`test_core.py` 必须输出“全部通过”。没有 `config/doc_compare.json` 时，提醒用户从 `config/doc_compare.example.json` 复制一份（不复制也能运行，用默认值）。

### 第 2 步：扫描页（有的话）

```bash
python scripts/doc_compare.py ocr-prepare <新文件文件夹> <baseline 文件夹> --out ocr_pages
```

脚本会列出没有文字层的页并转成图片。请用户把 `ocr_pages` 文件夹拖到「识别截图.bat」上（Windows 自带识别，不安装软件，图片不出本机），完成后文件夹里会有 `截图识别结果.ocr.json`。没有扫描页时跳过这一步。

### 第 3 步：对比

```bash
python scripts/doc_compare.py batch --baseline-dir <baseline 文件夹> --new-dir <新文件文件夹> --out compare_runs \
    [--names <测试数据人名名单>] [--ocr ocr_pages/截图识别结果.ocr.json]
```

一对文件用 `compare <baseline.pdf> <新文件.pdf> --out <文件夹>`。结果在 `compare_runs/<时间>/`：`index.html` 总览，每个 Case 一个文件夹（`ignore.html`、`total.html`、`result.json`、`result.masked.json`、`snapshots/`、`packages/`）。

### 第 4 步：汇报

读每个 Case 的 `result.masked.json`，按下面的格式用中文汇报，然后停下，等用户核对：

```
共对比 N 个 Case：有真实差异 X 个，需核对 Y 个，无差异 Z 个。
没有比较的页：Case7 新文件第 93–136 页（扫描页，未识别）。   ← 没有就写“无”
复读：含数字的 M 行已用第二种方式核对，K 行不一致（列在“不确定”里）。

Case5（真实差异 2，不确定 1）
- D001 第 12 页 保單資料 › 保費：587.85 → 600.00（负责人：产品组）
- U001 第 40 页：日期平移天数和其他不同……（原因照抄）
……

建议（需要你确认）：
- 疑似人名：GARCIAYRW 出现在 3 个 Case，像测试数据里的英文名，确认后加进人名名单。
```

- 每条差异写编号、页码、位置（章节 › 字段）、原值 → 新值、负责人，值照抄 `old` / `new`（打码后的）。
- 只汇报“真实差异”和“不确定”；“已忽略”“位置变化”只报数量，说明在 `ignore.html` 附录里可以抽查。
- 发给负责人的包在每个 Case 的 `packages/` 里，文字和截图都已打码。由用户自己决定发不发。

### 第 5 步：调整规则（需要时）

用户确认某类内容可以忽略后，改 `config/doc_compare.json`（人名加进 `names` 或名单文件；每次都不同的日期标签加进 `date_any_shift_labels`），运行 `python evals/test_core.py`，再重新对比。改 `scripts/filters.py` 的判断逻辑时，同时在 `evals/test_core.py` 里加上对应的测试。

### 验收（替换现有做法之前）

```bash
python scripts/doc_compare.py batch ... --out acceptance_runs
python evals/check_acceptance.py --result acceptance_runs/<时间> --golden evals/golden.csv
```

`golden.csv` 是同事A 以前人工确认过的差异。必须输出“验收通过：一条不漏”；“标准答案以外的真实差异”逐条交给同事A 判断。

## 文件

- `scripts/doc_compare.py`：命令入口（batch / compare / ocr-prepare）
- `scripts/filters.py`：日期、人名过滤，所有忽略规则只在这里
- `scripts/dc_core.py`：对齐、位置变化、分类（不读 PDF，可单独测试）
- `scripts/pdf_io.py`：读 PDF、扫描页、复读数字、差异截图（打码）
- `scripts/report.py`：ignore.html、total.html、结果文件、按负责人打包
- `config/doc_compare.example.json`：配置说明
- `references/design.md`：架构、判断规则、结果格式
- `evals/test_core.py`、`evals/check_acceptance.py`：测试和验收
