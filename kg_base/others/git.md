好的，我根据你提供的《分支.md》文档，把**Git提交到提测部署的完整流程**，按文档原意整理出来。

---

# 前端任务闭环全流程（基于《分支.md》）

## 一、分支体系（文档 §1）

| 分支前缀 | 作用 | 命名格式 | 谁用 |
|----------|------|----------|------|
| `master` | 生产稳定主干，**禁止直接提交代码** | `master` | 仅做最终同步基准 |
| `feature` | 个人业务开发分支 | `feature/版本号/开发者/任务ID/功能简述` | 前端开发 |
| `nightly` | 开发环境联调分支 | `nightly` | 前后端联调 |
| `qa` | 测试环境分支 | `qa/版本号` | 测试人员 |
| `release` | 预发 & 正式上线分支 | `release/版本号` | 上线前验证 |
| `hotfix` | 线上紧急热修复 | `hotfix/版本分支-月日` | 紧急修复（日常禁用） |

---

## 二、正常迭代完整流程（文档 §1.1）

### 第1步：创建 feature 分支
```bash
# 基于 master 拉取最新代码
git checkout master
git pull
git checkout -b feature/1.0.0/zhangsan/1024/monthly-check
```

### 第2步：日常开发
- 开发中频繁执行 `git rebase origin/master`，同步主干最新代码，**提前规避冲突**

### 第3步：联调阶段
- 功能写完 → 合并到 `nightly` 分支 → 部署 dev 环境 → 前后端联调

### 第4步：提测阶段
- 联调无误 → 提交 GitLab **MR** → 合并至对应 `qa/版本号` 分支 → 部署 test 环境 → 交由测试测 BUG

### 第5步：修复BUG
- 测试提出问题 → 回到自身 `feature` 分支修改修复 → 重复联调 + 提测流程

### 第6步：压缩提交（squash）
- 所有 BUG 闭环、需求验收完成 → **将多次零散提交压缩成 1 个干净的 commit**

### 第7步：合并到 release
- 压缩完成的 `feature` 分支 → 合并至 `release/版本号` 预发分支

### 第8步：预发 & 上线
- `release` 分支完成预发回归测试 → 打版本标签 → 打包发布正式包

### 第9步：合并回 master
- 正式版本上线无问题 → **以快进合并（fast-forward only）** 将 `release` 代码合回 `master` 主干

---

## 三、提交信息规范（文档 §3）

### 格式
```
<type>(#任务ID): 简短描述
空行
详细正文（修改多必填）
空行
页脚（关闭任务填写）
```

### Type 类型
| type | 用途 |
|------|------|
| `feat` | 新增功能 |
| `fix` | 修复BUG |
| `refactor` | 重构 |
| `style` | 格式调整 |
| `docs` | 文档 |
| `build` | 打包配置 |
| `test` | 测试代码 |
| `perf` | 性能优化 |
| `ci` | 流水线配置 |

### 强制规则
1. `feat` / `fix` **必须携带任务ID** `#xxxx`
2. 描述结尾**禁止加句号**
3. 单次提交只做一件事
4. 修改多时必须用列表逐条列明

### 示例
```
feat(#1024): 新增资产盘点台账页面
- 完成盘点列表基础布局
- 接入分页查询接口
- 实现盘点状态筛选功能

Closes #1024
```

---

## 四、MR 合并请求规范（文档 §4）

| 阶段 | 要求 |
|------|------|
| 开发中期 | 可提交 **Draft 草稿 MR**，提前纠错方向 |
| 正式 MR | 需求联调完成、冒烟测试通过后发起 |
| 上线 MR | **必须完成 commit 压缩**，禁止多条杂乱提交进入上线分支 |
| MR 标题 | 必须和压缩后的正式 commit 信息完全一致 |
| MR 模板 | 必须选用项目内置 MR 模板，完成代码自检项填写 |
| 流水线 | 全部运行成功后，再通知审核人走查 |
| 整改 | 审核意见全部整改完毕，才可通过合并 |

---

## 五、热修复流程（文档 §5）

1. **使用前提**：仅线上生产环境出现**阻塞业务、紧急故障**才可启用
2. 分支命名：`hotfix/对应版本分支-月日`
3. 修复完成后 → 同步合并至 `qa`、`release`、`master` **全链路分支**，避免版本断层

---

## 六、你的实际分支情况（文档扩展部分）

根据文档中的 `git branch -a` 输出，你当前项目有这些分支：

```
master                 # 生产主干
origin/fincors         # 真实业务代码分支（205次提交，22个页面）
origin/nightly         # 开发联调分支
origin/feature/lhy/1.3.0  # 个人功能分支
```

**重要**：你的真实业务代码在 `fincors` 分支，不是 `master`。

---

## 七、你当前应该做的事（基于文档 §1.1 正常迭代流程）

### 你现在处于的步骤

根据你之前的开发记录，你已经完成了：
- ✅ 创建 feature 分支（基于 fincors）
- ✅ 日常开发
- ✅ 联调到 nightly
- ⏳ **下一步：提交 MR 合并到 qa 测试分支**

### 你需要做的事

```bash
# 1. 确认代码已全部提交
git status

# 2. 把多次提交压缩成 1 个
git rebase -i HEAD~n  # 合并零散提交

# 3. 提交 MR 到 qa 分支
# 在 GitLab 创建 Merge Request
# 目标分支：qa/1.0.0
# 标题：feat(#1024): 月结对账模块改造

# 4. 通知测试人员
# MR 合并后，部署 test 环境，通知测试
```

---

## 八、全流程总结图

```
master（基准）
    │
    └── feature/xxx（开发）
              │
              ├── 频繁 rebase master
              │
              └── 合并 → nightly（dev联调）
                              │
                              └── MR → qa/版本号（测试）
                                              │
                                              └── 修复BUG ← 回到 feature
                                              │
                                              └── 压缩commit
                                              │
                                              └── 合并 → release/版本号（预发）
                                                              │
                                                              └── 打标签、发布正式包
                                                              │
                                                              └── fast-forward 合回 master
```

---

## 九、月结对账实际操作命令

### 常用辅助命令

```bash
# 查看当前在哪个分支（前面带 * 号的）
git branch

# 查看当前分支 + 远程分支
git branch -a

# 查看当前改动文件列表
git status

# 查看最近的提交历史
git log --oneline -10
```

---

### 第一步：创建 feature 分支并推送（基于 fincors，云桌面手敲版）

> **操作说明**：`#` 后面是注释，不需要敲。

---

### 第一步：创建 feature 分支并推送

> **规范格式**：`feature/版本号/姓名/任务ID/功能简述`（来自 CLAUDE.md）
>
> **实际示例**：
> ```bash
> # 规范写法：
> feature/1.4/liwen/663549/monthly-check
> #  版本号 ↑   姓名 ↑  任务ID ↑    功能 ↑
>
> # 项目现有分支示例（仅作参考，命名略有差异）：
> # feature/lhy/1.3.0
> # feature/1.3.0/lhy
> ```
>
> **字段说明**：`1.4`=迭代版本 / `liwen`=你的 git 用户名 / `663549`=需求编号 / `monthly-check`=功能简述 kebab-case

```bash
# 切换到基准分支 fincors
git checkout fincors

# 拉取 fincors 最新代码
git pull origin fincors

# 基于 fincors 创建你自己的 feature 分支
# ★ 把下面这行替换成你的实际分支名
git checkout -b feature/1.4/liwen/663549/monthly-check

# 把新分支推送到远程仓库，首次推送后才能被 GitLab 识别
git push origin feature/1.4/liwen/663549/monthly-check
```

> **作用**：在远程仓库创建一个只属于你的开发分支，后续所有改动都在这个分支上做，不影响其他人。

---

### 第二步：提交代码

```bash
# 查看改动文件列表，确认没有漏提交或多提交
git status

# 把当前目录下所有改动文件加入暂存区（准备提交）
git add .
git commit -m "fix(#748003): 资产全息查询结果异步导出功能

  - 异步导出"

# 提交到本地仓库（-m 后面是提交信息，格式严格遵守规范）
git commit -m "feat(#751167): 月结关账页面改造 — 新增期间字段、查询区优化、入参修正、双向联动

 - 表格新增4列：起始时间(periodDateS)、结束时间(periodDateE)、会计日历(periodSetCode)、期间状态(status)
  - 查询区：资产主体和资产账簿位置对调，会计期间改为非必选
  - 月结/月结回退入参修正：astEntityCodes→astEntityCode(去s)，新增astLedgerCode，改为直接传勾选整行数组
  - 主体⇄账簿双向联动：选组织后两者独立可选，主体可筛账簿、账簿可筛主体
  - 删除表格列：封存状态、封存用户、封存时间（不再使用）
  - 放开资产主体对账簿的强制依赖：账簿为空时主体仍可选择
  - HelpMethods新增requestMonthlyCloseLedger可选entityCode参数"

# 把本地提交推送到远程 feature 分支
git push origin feature/1.4/liwen/663549/monthly-check
```

> **作用**：把本地代码保存到远程仓库，防止云桌面故障丢失，也方便后续合并。

---

### 第三步：提 MR（GitLab 网页创建，无需命令行）

```
在 GitLab 网页操作：
  左侧菜单 → Merge Requests → New merge request
  Source branch（源分支）：feature/1.4/liwen/663549/monthly-check
  Target branch（目标分支）：qa/1.4
  Title（标题）：feat(#663549): 月结对账模块改造
  不勾选 "Delete source branch when merge request is accepted"
  点击 "Create merge request"
  等 Pipeline 流水线全部通过后，通知组长审核
```

> **作用**：提交代码审核申请，组长审批通过后方可继续下一步。

---

### **标准操作流程（按这个做就不会错）**

1. 切回你的分支

   ```
   git checkout feature/1.4/liwen/663549
   ```

2. 拉取最新的 nightly 代码并合并

   ```
   git pull origin nightly
   ```

   这时候终端会告诉你哪些文件冲突了（CONFLICT）。

3. 解决冲突

   - 打开编辑器（VS Code等），找到冲突文件。
   - 你会看到类似 `<<<<<<< HEAD` 和 `>>>>>>> nightly` 的标记。
   - **保留你的代码**，或者**结合两者的代码**。删掉那些乱七八糟的符号。

4. 提交并推送

   ```
   git add .
   git commit -m "resolve conflicts with nightly"
   git push
   ```

5. **刷新网页**
   这时候那个感叹号就会消失，变成绿色的合并按钮（或者等待审核状态）。

###

---

### 第四步：组长审批通过后，合并到 nightly 联调

```bash
# 切换到联调分支
git checkout nightly

# 拉取 nightly 最新代码（可能有其他人合并过）
git pull origin nightly

# 把你的 feature 分支合并到 nightly
git merge feature/1.4/liwen/663549/monthly-check

# 如果有冲突，手动解决冲突文件，然后：
git add .
git commit -m "merge: feature/1.4/liwen/663549/monthly-check into nightly"

# 把合并后的 nightly 推送到远程（触发 dev 环境部署）
git push origin nightly
```

> **作用**：代码合入联调分支，dev 环境部署，前后端联调验证。MR 也会同步进入 qa 测试环境。

---

### 第五步：提测后修 BUG

```bash
# 回到你的 feature 分支
git checkout feature/1.4/liwen/663549/monthly-check

# === 改代码修复 BUG ===

# 提交修复
git add .
git commit -m "fix:修复错误

-全生命周期查询-联查按钮点击后无反应
-资产折旧日志查询-资产类型受账簿联动验证失败"
git push origin feature/1.4/liwen/663549/monthly-check

# 重新合入 nightly 验证修复效果
git checkout nightly
git pull origin nightly
git merge feature/1.4/liwen/663549/monthly-check
git push origin nightly
```

> **作用**：在 feature 分支修 BUG → 推送 → 合入 nightly 验证 → GitLab MR 会自动同步最新代码，通知测试重新验证。

---

### 第六步：提测通过后压缩 commit

```bash
# 回到期间重置 feature 分支
git checkout feature/1.4/liwen/663549/monthly-check

# 查看从 fincors 分叉以来一共有多少个 commit
git log --oneline origin/fincors..HEAD

# 交互式 rebase 压缩（N = 上一步看到的 commit 数量）
# ★ 示例：如果有 5 个 commit，就写 HEAD~5
git rebase -i HEAD~5

# ===== 打开的编辑器（vim）操作指南 =====
# 你会看到类似这样的内容：
#   pick a1b2c3d feat(#663549): 月结对账模块改造
#   pick d4e5f6g fix(#663549): 修复查询参数问题
#   pick g7h8i9j fix(#663549): 修复凭证清单报错
#   pick j0k1l2m style: 调整表格列宽
#   pick m3n4o5p chore: 清理调试日志
#
# ★ 操作：第一行保留 pick，其余行把 pick 改成 s
#   改完后：
#   pick a1b2c3d feat(#663549): 月结对账模块改造
#   s    d4e5f6g fix(#663549): 修复查询参数问题
#   s    g7h8i9j fix(#663549): 修复凭证清单报错
#   s    j0k1l2m style: 调整表格列宽
#   s    m3n4o5p chore: 清理调试日志
#
# vim 操作：按 i 进入编辑模式 → 改完按 Esc → 输入 :wq 保存退出

# 保存退出后编辑器再次打开，合并为一个 commit message
# 只保留最终一条描述（如 feat(#663549): 月结对账模块改造），其余删除

# 强制推送（rebase 后历史变了，必须 force push）
git push --force-with-lease origin feature/1.4/liwen/663549/monthly-check
```

> **作用**：把开发过程中的零散提交（"改个样式""修个bug"）压成 1 个干净 commit，合入 release 时历史清晰。

---

### 第七步：合并到 release 并上线

```bash
# 切到 release 分支
git checkout release/1.4
git pull origin release/1.4

# 合并你压缩后的 feature 分支
git merge feature/1.4/liwen/663549/monthly-check
git push origin release/1.4
```

> **作用**：代码进入预发分支，预发环境回归测试通过后，打版本标签、发布正式包。

---

### 第八步：合并回 master（上线后）

```bash
git checkout master
git pull origin master
git merge --ff-only release/1.4
git push origin master
```

> **作用**：上线确认无问题后，将 release 代码以快进方式合回 master，保证主干始终是最新稳定版。

---

### 日常：同步 fincors 最新代码（避免冲突）

```bash
# 在 feature 分支上执行
git checkout feature/1.4/liwen/663549/monthly-check

# 拉取 fincors 最新代码（只下载，不合并）
git fetch origin fincors

# 把 fincors 的最新提交"垫"到你的提交下面
git rebase origin/fincors

# 如果有冲突，手动解决后：
git add .
git rebase --continue

# rebase 后历史变了，必须 force push
git push --force-with-lease origin feature/1.4/liwen/663549/monthly-check
```

> **作用**：定期把你的 feature 分支变基到最新的 fincors 上，提前发现并解决冲突，避免最后合并时出现大范围冲突。

---

### 补充：如果提交了不该提交的文件

```bash
# 撤销最近一次 commit（保留文件改动）
git reset --soft HEAD~1

# 把不该提交的文件移出暂存区
git reset HEAD 文件路径

# 重新提交
git add .
git commit -m "新的提交信息"
```

> **作用**：回退提交但保留代码改动，调整后重新提交。

git commit -m "fix(#712443):
- 资产组织下拉：requestMonthlyCloseAssetOrg 返回值从 records 数组改为完整 data 对象，恢复 total 字段让 HelpScroll 正常分页
- 期间同步按钮：type 从 primary 改为 default，与月结/月结回退保持一致
- 联查跳转：门户环境用 getMenuByPageUrl() 补齐 svcCode/mfeCode，修复 URL 中 undefined 导致白屏"
