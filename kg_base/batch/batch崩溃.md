```markdown
# Batch系统崩溃
> Friday, September 18, 2026 6:04 PM

`json.dumps(...)`到内存里时直接炸了。

另一个出现在这里：
```python
kb_poc\retrieval\embedding.py
response = self._client.embeddings.create(...)
...
httpx2/_models.py -> response.json()
MemoryError
```
也就是 embedding 请求/响应处理时也撞到了内存问题。

再结合代码看，这个上传链路本身就比较吃内存：
- worker 是 `ProcessPoolExecutor(MAX_WORKERS=8)`，8个子进程并发
- 每个子进程都会跑 Excel/PPT 解析、OCR、artifact生成、embedding
- Excel 解析器会生成大量 structured/ocr/semantic JSON 文件
- OCR 这边会做多轮图片预处理 + PaddleOCR
- 解析完成后

> 你说得对，刚才那个 ManagedBatch 不是这次“传到一半突然一串报错然后整个系统崩掉”的主因。我重新按“上传过程中崩”的线索查了，已经找到更贴近现场的问题链路。

这次更关键的证据有两类：
1. Windows 崩溃记录
    - 时间点就在你说的那次：9/18 17:47:41
    - 进程：`python.exe`
    - 异常：`0xc0000005`（访问冲突，原生层 crash）
    - 同一时间还有 `dwm.exe / ucrtbase.dll` 异常，所以才会出现 PyCharm 被一起带崩溃/直接关闭的现象
2. 上传批次的实际处理中断痕迹

---

最新大批次是 `batch_380eb5e3c313`，一共 15 个文件
- 当时确实已经处理了一大半，很多文件是 completed
- 崩掉前最后几项状态很关键：
    - `...SalesTool_設計書_1.2.xlsx`: failed，报 MemoryError
    - `...SalesTool_申込書_1.2.xlsx`: failed，报 MemoryError
    - `...SalesTool_設計書_1.3.xlsx`: failed，报 429 RateLimitReached
    - `...SalesTool_申込書_1.1.xlsx`、`...SalesTool_設計書_1.3.xlsx`: 当时还停在 processing

从库里抓到的真实错误里，最关键的是这两个：

**MemoryError**

一个出现在这里：
```python
kb_poc\parsing\artifacts.py
target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf‑8")
```
也就是把很大的 structured/ocr/semantic artifact 整个 `json.dumps(...)` 到内存里时直接炸了。

另一个出现在这里：
```python
kb_poc\retrieval\embedding.py
response = self._client.embeddings.create(...)
...
httpx2/_models.py -> response.json()
MemoryError
```
也就是 embedding 请求/响应处理时也撞到了内存问题。

再结合代码看，这个上传链路本身就比较吃内存：
- worker 是 `ProcessPoolExecutor(MAX_WORKERS=8)`，8个子进程并发
- 每个子进程都会跑 Excel/PPT 解析、OCR、artifact生成、embedding
- Excel 解析器会生成大量 structured/ocr/semantic JSON 文件
- OCR 这边会做多轮图片预处理 + PaddleOCR
- 解析完成后还会把 chunk 列表转 dict 返回给父进程
- 有些文件本身就含大量图片/OCR内容，artifact 很容易变得特别大

所以这次更像是：

大批量上传进行到中后段时，多个 worker 并发处理重文件，内存占用持续抬升，先出现 MemoryError 和 embedding 429，随后 Python 进程在原生扩展栈里直接 `0xc0000005` 崩溃，连带 PyCharm 窗口一起被系统打掉。

## 结论按优先级排

| 级别 | 现象 | 判断 |
|------|------|------|
| 1 | `python.exe` 访问冲突 `0xc0000005` | 这是“整个系统突然退出、PyCharm被关掉”的直接表现 |
| 2 | 多个文件处理中出现 MemoryError | 这是最像“崩前一大串报错”的业务层直接诱因 |
| 3 | 429 RateLimitReached | 不是崩溃根因，但说明并发打 embedding 太猛，也会放大问题 |
| 4 | OCR / Pillow / numpy / paddleocr 原生栈 | 因为是原生库链路，内存吃满后更容易从普通异常升级成进程级 crash |

> 一句话判断原因：这次不是单纯代码语法错，而是上传批次里有较重的 Excel/OCR 文件，8进程并发下内存被打爆，随后 Python 原生栈崩溃。

你这次现场最关键的两条证据已经有了：
- `ingest.db` 里明确有 MemoryError
- Windows 事件日志里明确有 `python.exe` 的 `0xc0000005`

如果后面要彻底修，最该先动的是这几处：
1. 把 `MAX_WORKERS=8` 降下来，先降到 2 或 4
2. artifact 写文件不要先整包 `json.dumps` 到内存
3. embedding 增加限流/重试/批量控制
4. 大 Excel/OCR 文件单独串行处理
5. 给 worker 单独落盘日志，不然下次还得靠事件日志倒推
```

### 使用方法
1. 全选复制上面全部内容
2. 在本地新建文本文件，粘贴进去
3. 另存为，文件名填 `batch_crash_report.md`，编码选 **UTF‑8**

如果你需要，我还可以帮你再输出一版面向团队的极简故障复盘摘要。


