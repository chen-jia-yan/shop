# 2026‑09‑24 worker 日志与上传处理情况记录

## 一、当前文件总体状态
截至今天晚间，`data\kb_admin\state.db` 中当前文件状态为：

| status | count |
|---|---|
| completed | 134 |
| dead | 56 |
| failed | 1 |
| processing | 16 |
| total | 207 |

当前阶段(stage)统计为：

| stage | count |
|---|---|
| done | 191 |
| queued | 16 |

这说明目前大盘上已经完成入库的文件有 134 个，但仍有 73 个文件处于非 completed 状态，其中主要由 `dead` 和 `processing` 构成。

## 二、今天 worker 日志看到的主要问题类型
结合今天的 `logs\worker.log` 和当前状态库，可以把今天的 worker 运行情况归成下面几类：

1. **正常推进仍在发生**：worker 仍在持续 claim 文件并处理，说明系统并不是完全停住。
2. **超时问题依然存在**：heavy 文件在 `420s` 超时阈值下仍会超时，这类问题之前已经多次出现，今天依旧是主因之一。
3. **坏 Office 包/临时文件很多**：日志里持续看到 `File is not a zip file`，大多是 `~$` 开头的 Office 临时文件或者伪装成 Office 的伪文件。
4. **不支持文件类型仍在进入处理链**：如 `Thumbs.db`、`.lnk`、`.msg` 等文件依然会进入 worker，制造无效失败。
5. **EMF/WMF 元文件 OCR 问题仍在**：今天仍有 `cannot render metafile`、`no embedded image` 这类报错，说明含矢量元图的文档仍会在 OCR 阶段失败。
6. **进程池类事故仍有残留影响**：历史上 `worker pool broken while submitting tasks`、`A process in the process pool was terminated abruptly`，当前 `dead` 中仍留有这类结果。
7. **今天还看到网络连接类失败**：部分文件报错 `process_one_file failed: Connection error` / `WinError 10065`，embedding/外部调用链路出现主机不可达。
8. **Windows 日志轮转风险点未根治**：`WinError 32` 文件占用类报错，worker.log 轮转占用问题今天依旧是已知风险。

## 三、结合上传/处理结果看今天的核心判断

### 1. worker 不是完全崩了，而是“边跑边撞已知问题”
今天的日志特征不是“整个 worker 彻底挂死”，而是：
- 一边继续 claim 和处理文件；
- 一边反复撞到几类已知坏料或环境问题。

也就是说，现在更像是一条仍在跑的流水线，但上游混入大量不该进来的文件，同时 heavy 文件超时、OCR、embedding 链路存在脆弱点，因此日志噪声巨大。

### 2. 当前上传队列里，真正值得优先关注的是 processing 的 16 个文件
现在数据库里：
- `processing = 16`
- `dead = 56`
- `failed = 1`

其中 `dead/failed` 多数属于历史沉淀结果；真正影响“现在还在处理什么”的是这 16 个 `processing` 文件。它们在 `queued` 阶段位上，说明当前表的 `stage` 没有完整展开所有中间态，大量任务保留为队列中处理状态。

### 3. 当前 dead 的大头仍然是“脏文件”和“伪文件”
结合今天已生成的 `failed_dead_breakdown.md`，当前 `dead/failed` 的主要来源并不是正常业务文档 OCR 识别能力不足，而是输入目录混杂了：
- Office 临时文件（`~$*`）
- `Thumbs.db`
- `.lnk`、`.msg`
- 伪装成 Office 的损坏/非法压缩包

## 四、今天额外观察到的典型异常

1. **网络连接错误**
    - embedding 阶段报 `Connection error` / `WinError 10065`，代表外部 API/主机不可达，属于外部链路临时故障。

2. **openpyxl / openpyxl 类兼容警告（openpyxl 告警）**
    - `Cannot parse header or footer so it will be ignored`
    - `Data Validation extension is not supported and will be removed`
    这类多为警告，不一定直接终止任务，但说明真实业务样本格式复杂度高。

3. **WMF/EMF 矢量图片被丢弃或 OCR 失败**
    - 触发报错：`cannot render metafile` / `no embedded image`
    - 后果：文档解析内容残缺，部分页面丢失识别结果。

## 五、今天的结论
> **worker 仍在工作，但今天的日志噪音主要来自脏文件、坏 Office 包、heavy 超时、EMF/WMF 图片兼容问题，以及一部分 embedding 连接错误。**

如果不先清理输入目录中的无效文件，并且不处理 heavy 超时和 OCR 元文件问题，日志会继续很多，`dead/failed` 也会持续累积。

## 六、建议后续动作
1. 在源目录入口就过滤：`~$`、`Thumbs.db`、`.lnk`、`.msg` 等不应该进入任务队列的文件；
2. 重新评估 heavy 文件的 `420s` 超时阈值，确认是调大超时、拆分大文件，还是做提前拒绝；
3. 对 EMF/WMF 图片明确策略：跳过不中断，或先转位图再 OCR；
4. 针对 embedding 连接错误，单独确认网络/API 可达性与重试策略；
5. 单独拉出当前 `processing=16` 的文件明细，重点盯正在跑的文件；
6. 持续关注 Windows 下 worker.log 的 WinError 32 文件占用风险，评估日志轮转方案。

## 七、相关文件
- 状态库：`C:\Users\234393\Desktop\jap‑cycle‑poc\data\kb_admin\state.db`
- worker 日志：`C:\Users\234393\Desktop\jap‑cycle‑poc\logs\worker.log`
- 失败明细：`C:\Users\234393\Desktop\jap‑cycle‑poc\failed_dead_breakdown.md`

---
