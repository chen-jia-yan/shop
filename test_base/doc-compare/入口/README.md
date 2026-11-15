# doc-compare：文档对比

对比新生成的产品文档（PDF）和 baseline，只把真实差异报出来；日期、人名的变化和位置错位不算差异，但全部留在附录里可以抽查；每条差异自动截图、按负责人打包。

```
doc-compare/
├── SKILL.md                      # AI 执行的步骤和铁律
├── README.md                     # 本文件：安装、第一次运行、验收
├── requirements.txt              # pdfplumber、pypdfium2、Pillow（都是宽松许可）
├── config/
│   ├── doc_compare.example.json  # 配置（复制为 doc_compare.json 后修改）
│   └── names.example.txt         # 测试数据人名名单示例
├── references/
│   └── design.md                 # 架构、判断规则、结果格式
├── scripts/
│   ├── doc_compare.py            # 命令入口：batch / compare / ocr-prepare
│   ├── filters.py                # 日期、人名过滤（同事A 的过滤合并到这里）
│   ├── dc_core.py                # 对齐、位置变化、分类
│   ├── pdf_io.py                 # 读 PDF、扫描页、复读、截图打码
│   └── report.py                 # 报告和打包
└── evals/
    ├── test_core.py              # 测试（用截图里的真实写法）
    ├── check_acceptance.py       # 验收：以前确认过的差异一条不漏
    └── golden.example.csv        # 验收标准答案示例
```

## 一、安装

需要 Python 3.9 以上。

```bash
cd doc-compare
pip install -r requirements.txt
python evals/test_core.py          # 应输出“全部通过”
```

## 二、第一次运行

1. 复制配置：`config/doc_compare.example.json` → `config/doc_compare.json`。先只改 `case_key`（文件名里 Case 编号的规则，默认认 `Case5_...` 这种开头）。
2. 准备测试数据人名名单 `names.txt`（每行一个名字），NICHOLSPUN 这类名字只能从这里来。
3. 运行：

```bash
python scripts/doc_compare.py batch --baseline-dir D:\baseline --new-dir D:\new --out D:\compare_runs --names names.txt
```

4. 打开 `D:\compare_runs\<时间>\index.html`，点进每个 Case 的 `ignore.html`。

**扫描页**：报告最上面如果写着“第 93–136 页没有文字层”，说明这些页没有比较。要比较的话：

```bash
python scripts/doc_compare.py ocr-prepare D:\new D:\baseline --out D:\ocr_pages
```

把 `D:\ocr_pages` 文件夹拖到「识别截图.bat」上，完成后再对比，加上 `--ocr D:\ocr_pages\截图识别结果.ocr.json`。识别得到的内容上的变化都列为“不确定”，请对照截图核对。

## 三、看结果

| 文件 | 内容 |
|---|---|
| `ignore.html` | 真实差异、不确定（附两份 PDF 的截图），附录：已忽略、位置变化 |
| `total.html` | 完整对比，格式与现在相同，不做任何过滤 |
| `packages/<负责人>.zip` | 发给负责人的包：只含他的差异，文字和截图都已打码 |
| `result.json` | 数据文件（格式见 references/design.md 第 9 节） |

## 四、上线前验收（必做）

1. 挑 3–5 个以前人工核对过的 Case，把当时确认的差异填进 `evals/golden.csv`（格式见 `golden.example.csv`，填差异里的一段原文即可）。
2. 对比这几个 Case，然后：

```bash
python evals/check_acceptance.py --result D:\compare_runs\<时间> --golden evals/golden.csv
```

3. 必须输出“验收通过：一条不漏”。“标准答案以外的真实差异”逐条看：是以前漏掉的真差异，还是要加过滤规则。
4. 和现有脚本并行跑 2–3 轮，结果对得上再替换。附录里随机抽查 20 条，确认被忽略的都只是日期、人名或位置变化。

## 五、合并现有的过滤

同事A 脚本里已有的过滤，核实后合并到 `scripts/filters.py`（位置见 references/design.md 第 10 节），并在 `evals/test_core.py` 里各加一条测试。其他脚本不用改。
