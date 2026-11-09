# 范例 3：证据不足 → 不建单，列出需要补充的信息

这个范例说明“什么时候不该起草”。

## 输入

- 分类：`NEEDS_HUMAN`，原因 `insufficient_evidence`
- 用例：Case31
- 证据：
  - E1：`TimeoutException: Message:`（报错信息为空）
  - 没有截图（截图文件不存在）
  - 没有弹窗证据（测试框架未接入证据收集）
  - 重跑 1 次仍失败

## 正确做法

**不起草 Jira。** 在汇报中写：

```
Case31：需人工判断（证据不足）
- 已有证据：TimeoutException，报错信息为空；重跑 1 次仍失败
- 缺少：失败截图、失败时的页面网址、弹窗证据
- 建议：在本地手动运行 Case31，观察超时发生在哪一步；
        或接入 scripts/popup_evidence.py 后重跑
```

## 错误做法（不要这样）

```
[NBS Regression] HK - BM case failed due to page loading slowly
```

“页面加载慢”没有任何证据支持。超时也可能是元素定位错误、弹窗遮挡、或页面跳转到了别的地方。
