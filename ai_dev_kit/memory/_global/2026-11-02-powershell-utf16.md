---
id: 2026-11-02-powershell-utf16
type: lesson
project: _global
subject: Windows PowerShell 5 用 > 或 Out-File 写出的文件是 UTF-16
tags: 编码, PowerShell, UTF-16
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: .env.example 变成 UTF-16 事故
citations:
  - user:2026-11-02 git diff 把 .env.example 显示为 Bin，原因是文件变成了 UTF-16
---
事实：Windows PowerShell 5 的重定向和 Out-File 默认写成 UTF-16 LE，git 会把它当成二进制文件，Python 读取也会出错。
原因：文件编码被悄悄改掉，很难第一时间发现。
怎么用：不用 > / Out-File / Set-Content 写源码或配置；改文件一律用编辑工具；守卫钩子会拦截这些命令。
