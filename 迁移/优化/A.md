git branch --show-current
git ls-files others

uv run python C:/Users/234393/Desktop/check_chars.py src tests sql .env.example
uv run python -c "import tap_ai.application; print('ok')"
uv run ruff check .
uv run mypy src
uv run pytest tests/unit/test_library_eval_core.py tests/unit/test_library_eval_service.py tests/api/test_library_eval_api.py tests/unit/test_library_chunks_api.py tests/unit/test_library_chunks.py -q


git add src tests
git diff --cached --name-only

git commit -m "fix(library): P2-P4 整改"



## 把 develop 合进你的分支
git status --short
git branch backup/before-merge-develop
git fetch origin
git log --oneline HEAD..origin/develop
$base = git merge-base HEAD origin/develop; $base
$mine = git diff --name-only $base HEAD; $theirs = git diff --name-only $base origin/develop; $mine | Where-Object { $theirs -contains $_ }

git merge origin/develop

## 合并后检查
uv run pytest tests/unit tests/api -q -p no:warnings 2>&1 | Out-File -Encoding utf8 C:\Users\234393\Desktop\after_merge.txt


# F 推送， 提PR1
git status --short
git push -u origin <你的分支名>