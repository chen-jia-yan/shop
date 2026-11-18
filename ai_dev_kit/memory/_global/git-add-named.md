---
id: 2026-11-02-git-add-named
type: convention
project: _global
subject: 提交时逐个点名添加文件，不用 git add . 或 git add -A
tags: git, 提交, 子模块
status: active
priority: high
created: 2026-11-02
verified: 2026-11-18
source: fwd-tap-common 子模块 dirty
citations:
  - user:2026-11-02 git diff --stat 出现 fwd-tap-common | 0，是嵌套子模块有未提交改动
---
事实：仓库里有处于 dirty 状态的嵌套子模块时，git add . 会把子模块指针一起提交。
原因：会把无关改动带进提交，回滚也麻烦。
怎么用：用 commit_helper.py 生成逐个点名的 git add 命令，再用 git diff --cached --stat 核对。
