# tap-config —— 四个 skill 共用的配置

Word、Excel、PPT、变更影响分析四个 skill 的脚本里**不写死**品牌、颜色、字体、主题、固定文字、合规词表和阈值，全部从这个目录读取。改这里即可全局生效，不需要改代码。

## 目录

| 文件 | 内容 | 常见改法 |
|---|---|---|
| `brand.json` | 机构名与简称、全部颜色（色名 → 色值）、图表配色顺序、字体候选链、字号倍数、字体方案（modern / formal） | 品牌部核对色值；换机构名；换字体 |
| `themes.json` | 各 skill 的风格（Word 6 套，默认淡雅蓝 / Excel 3 套 / PPT 7 套）、文档类型 → 默认风格、Excel 单元格角色色与数字格式 | 新增一套风格：复制一段改名，`--style` / `--theme` 直接可选 |
| `labels.json` | 生成到文档里的固定文字：表头、提示语、页码格式、状态名称、符号 | 换说法、做英文版 |
| `compliance.json` | 禁用词、否定式白名单、各文档类型必备要素、占位符写法、试算免责提示 | 合规部审定后修改 |
| `rules.json` | 页面尺寸、字号、拆页与质检阈值、预警天数、变更影响评分权重 | 调整版面和阈值 |
| `impact.json` | 变更影响分析：12 个业务类别（权重、关键词、受影响对象）、信号加分、影响度加分、级别下限、义务 / 否定 / 范围词表、标题识别规则、处置建议库、各级别处置要求 | 业务与合规共同审定；新业务线加类别 |
| `icons.json` | PPT 图标自动匹配关键词 | 增删业务关键词 |
| `tapconf.py` | 加载器（合并、颜色引用、字体选择） | 一般不用改 |
| `tapcheck.py` | 共享质检工具（合规扫描、必备要素、报告格式） | 一般不用改 |

## 覆盖顺序（后面的覆盖前面的）

1. 本目录的 JSON
2. 环境变量 `TAP_CONFIG`：指向一个文件或目录（多个用系统路径分隔符隔开），适合按机构/部门放一份差异配置
3. 命令行 `--config 文件或目录`（可写多次）
4. 内容 JSON 的 `meta.config`：只写要改的部分，例如
   ```json
   "meta": {"config": {"colors": {"primary": "#0072CE"}, "fonts": {"cn": ["思源黑体", "微软雅黑"]}}}
   ```
5. 快捷覆盖：`meta.brand`（机构名）、`meta.fonts`、命令行 `--font-cn` `--font-en` `--font-num` `--font-mode` `--font-scale`

字典逐层合并，列表整体替换。差异配置只需写变化的键。

## 字体为什么是“候选链”

- 每个角色（中文正文 cn、中文标题 head、西文 en、数字 num、引文 quote、等宽 mono）写一串候选字体；head 不写时同 cn。
- `mode: "first"`（默认）：Office 文件里写入第一个候选。文件在别人的电脑上打开，以对方装的字体为准，Office 会自动替换缺失字体。
- `mode: "installed"`：优先选**本机已安装**的候选，适合生成后在本机直接打印或转 PDF。
- 图表图片（Word 里的 matplotlib 图）总是按本机已安装的候选选择，否则中文会显示为方块。
- `scale`：整体字号倍数（如 1.1 放大 10%），PPT 的自动缩字号会把倍数算进去。
- 每个 skill 可以单独覆盖：`fonts_by_scope.word.en` 等。
- **字体方案** `font_presets`：一次换一整套（标题、正文、西文、数字）。Word 按文档类型自动选（`rules.word.font_preset`）：制度、通知、合规用 formal（黑体标题 + 宋体正文 + Times New Roman），其余用 modern（微软雅黑 + Arial）；可用 `--font-preset` 或 `meta.font_preset` 指定。
- 叠加顺序：fonts → fonts_by_scope → 字体方案 → 用户指定（`meta.fonts`、`--font-cn` 等），用户指定的永远优先。

## 颜色引用

主题里写 `"@primary"` 表示引用 `brand.json` 的 `colors.primary`；也可以直接写 `"#RRGGBB"`。色名是语义化的（primary 主色、secondary 辅助色、accent 点缀色……），换品牌时只改色值，不用改主题。

## 部署

把 `tap-config/` 和各 skill 目录放在同一级：

```
skills/
  tap-config/
  kb-to-word/
  kb-to-excel/
  kb-to-ppt/
  change-impact/
```

如果放在别处，设置环境变量 `TAP_CONFIG_HOME=/path/to/tap-config`。
