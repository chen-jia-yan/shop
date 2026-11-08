# Git 操作日志记录
> 环境：Windows PowerShell，仓库路径：`C:\Users\234393\Desktop\jap-cycle-poc`

```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc> git status
On branch add_gzohou_changes
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        fwdmiya.bundle

nothing added to commit but untracked files present (use "git add" to track)
```

```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc> git reflog -50
eb9ea72 (HEAD -> add_gzohou_changes, origin/HEAD, main) HEAD@{0}: reset: moving to eb9ea729c59f3888283d58a120164934c12b4788
eb9ea72 (HEAD -> add_gzohou_changes, origin/main, origin/HEAD, main) HEAD@{1}: checkout: moving from main to add_gzohou_changes
eb9ea72 (HEAD -> add_gzohou_changes, origin/main, origin/HEAD, main) HEAD@{2}: checkout: moving from main to main
eb9ea72 (HEAD -> add_gzohou_changes, origin/main, origin/HEAD, main) HEAD@{3}: reset: moving to eb9ea729c59f3888283d58a120164934c12b4788
eb9ea72 (HEAD -> add_gzohou_changes, origin/main, origin/HEAD, main) HEAD@{4}: pull origin main: Fast-forward
760eb0e HEAD@{5}: checkout: moving from FWDMiya to main
9c1030e (origin/FWDMIYA, FWDMIYA) HEAD@{6}: commit: feat: clean rag demo latest version
760eb0e HEAD@{7}: checkout: moving from main to FWDMiya
760eb0e HEAD@{8}: pull origin main: Fast-forward
e95a97a HEAD@{9}: reset: moving to HEAD
e95a97a HEAD@{10}: checkout: moving from Miya/jp-rag-demo to main
f2f893b (origin/Miya/jp-rag-demo, Miya/jp-rag-demo) HEAD@{11}: checkout: moving from FWDMiya to Miya/jp-rag-demo
f2f893b (origin/Miya/jp-rag-demo, Miya/jp-rag-demo) HEAD@{12}: checkout: moving from Miya/jp-rag-demo to FWDMiya
f2f893b (origin/Miya/jp-rag-demo, Miya/jp-rag-demo) HEAD@{13}: commit: Fixing bugs about dirty data and process pool
dc456b3 HEAD@{14}: commit: update ui with kb_admin
3ac03b1 HEAD@{15}: commit: addressing the issue of dirty data
4e208bf HEAD@{16}: commit (merge): batch processing speed
b13b728 HEAD@{17}: merge origin/main: Merge made by the 'ort' strategy.
0021072 HEAD@{18}: commit: batch processing speed
78f013d HEAD@{19}: reset: moving to origin/Miya/jp-rag-demo
78f013d HEAD@{20}: reset: moving to origin/Miya/jp-rag-demo
513464f HEAD@{21}: reset: moving to HEAD~1
78f013d HEAD@{22}: commit: update batch
513464f HEAD@{23}: commit: batch repaired
07d0591 HEAD@{24}: checkout: moving from main to Miya/jp-rag-demo
e95a97a HEAD@{25}: pull: Fast-forward
```

```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc> git log --oneline --graph --all --decorate -30
fatal: unrecognized argument: --graph

PS C:\Users\234393\Desktop\jap-cycle-poc> git log --oneline --graph --all --decorate -30
* eb9ea72 (HEAD -> add_gzohou_changes, origin/main, origin/HEAD, main) Merged PR 172942: feat: clean rag demo latest version
|\
| * 9c1030e (origin/FWDMIYA, FWDMIYA) feat: clean rag demo latest version
|/
* 760eb0e Merge remote-tracking branch 'origin/main'
|\
| * 43a2659 Merged PR 172250: Miya/jp rag demo
| * 34c2965 知识图谱
...
| * 2f8727a (refs/stash) WIP on main: e95a97a Merged PR 170714: add batching
| * 5d238ad index on main: e95a97a Merged PR 170714: add batching
| * f2f893b (origin/Miya/jp-rag-demo, Miya/jp-rag-demo) Fixing bugs about dirty data and process pool
| * dc456b3 update ui with kb_admin
| * 3ac03b1 addressing the issue of dirty data
| * 4e208bf batch processing speed
|/
* faffef1 refactor: streamline agent orchestrator, prompts, advanced QA and UI
* 2385044 fix: restore full flowchart structure and enforce anti-dumping constraints
* e41d5f5 fix: wire up follow-up detection in _chat_loop
```

```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc> git branch -a
  FWDMIYA
  Miya/jp-rag-demo
* add_gzohou_changes
  main
  remotes/origin/Document-Import
  remotes/origin/FWDMIYA
  remotes/origin/HEAD -> origin/main
  remotes/origin/Miya/jp-rag-demo
  remotes/origin/main
  remotes/origin/merge
```

```powershell
PS C:\Users\234393\Desktop\jap-cycle-poc> git remote -v
origin  https://FWDGODevOps@dev.azure.com/FWDGODevOps/CTC_Testing_Automation/_git/jp-cycle-test-poc (fetch)
origin  https://FWDGODevOps@dev.azure.com/FWDGODevOps/CTC_Testing_Automation/_git/jp-cycle-test-poc (push)
```

## 信息汇总
1. **当前分支**：`add_gzohou_changes`
2. **未跟踪文件**：`fwdmiya.bundle`
3. **本地分支列表**
    - FWDMIYA
    - Miya/jp-rag-demo
    - add_gzohou_changes（当前）
    - main
4. **远程分支（origin）**
    - origin/Document-Import
    - origin/FWDMIYA
    - origin/Miya/jp-rag-demo
    - origin/main
    - origin/merge
    - origin/HEAD -> origin/main
5. **远程仓库地址**：Azure DevOps 仓库
    - fetch & push：`https://FWDGODevOps@dev.azure.com/FWDGODevOps/CTC_Testing_Automation/_git/jp-cycle-test-poc`
6. **关键提交摘要**
    - `eb9ea72`：Merged PR 172942: feat: clean rag demo latest version
    - `9c1030e`：feat: clean rag demo latest version
    - `f2f893b`：Fixing bugs about dirty data and process pool
    - `dc456b3`：update ui with kb_admin
    - `3ac03b1`：addressing the issue of dirty data
    - `4e208bf`：batch processing speed

---

如果你需要，我可以再帮你单独提取**reflog**或者**git log**部分，或者导出成纯文本。


CONFLICT (content): Nerge conflict in kb_poc/ui/modern_chat_page.htmlAuto-merging kb_poc/ui/modern_chat_page.jsCONFLICT (content): Nerge conflict in kb_poc/ui/modern_chat_page.jsamerror: could not apply fbfbee7... fix: Mermaid flowchart rendering in web chatlineAfter resolving the conflicts, mark them with0111hint:Dllowhint:"git add/rm <pathspec>"then runhint:'git cherry-pick --continue'ap-cychint:You can instead skip this commit with "git cherry-pick --skip"hint:To abort and get back to the state before "git cherry-pick"hint:run"git cherry-pick --abortDisable this message with "git config set advice.mergeConflict false'hint:PS C:\Users\234393\Desktop\jap-cycle-poc> git cherry-pick --abortportPS C: \Users\234393\Desktop\jap-cycle-poc> git cherry-pick --aborterror: no cherry-pick or revert in progressin/mefatal: cherry-pick faileddemoPS C:\Users\234393\Desktop\jap-cycle-poc> git .statusOn branch add_gzohou_changesUntracked files:." to include in what will be committed)(use "git add <file>fwdmiya.bundle
ap-cyclev.02dev.az
nothing added to commit but untracked files present (use "git add" to track)