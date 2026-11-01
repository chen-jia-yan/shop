python -c "import sqlite3; c=sqlite3.connect(r'file:data/kg.db?mode=ro', uri=True); print('== 关系 =='); [print(r) for r in c.execute('SELECT type, COUNT(*) FROM kg_edges GROUP BY type ORDER BY 2 DESC')]; print('== 节点 =='); [print(r) for r in c.execute('SELECT type, COUNT(*) FROM kg_nodes GROUP BY type ORDER BY 2 DESC')]"



Get-Content data/chunk_content.csv -TotalCount 1


MATCH (n) RETURN n.scope AS scope, labels(n) AS labels, count(*) AS cnt ORDER BY scope, cnt DESC

MATCH (a)-[r]->() RETURN a.scope AS scope, type(r) AS rel, count(*) AS cnt ORDER BY scope, cnt DESC

MATCH (n) WITH labels(n) AS labels, keys(n) AS props RETURN labels, props, count(*) AS cnt ORDER BY cnt DESC LIMIT 20


$env:TAP_AI_LITELLM_BASE_URL="http://127.0.0.1:4000"
$env:TAP_AI_LITELLM_API_KEY="test-dummy-key"
$env:TAP_AI_DATABASE_URL="mysql+asyncmy://test:test@127.0.0.1:3306/test"
$env:TAP_AI_REDIS_URL="redis://127.0.0.1:6379/0"


git diff a1a06ac~1 --stat
git diff a1a06ac~1 --stat src/tap_ai/bootstrap.py
git diff a1a06ac~1 -w --stat src/tap_ai/bootstrap.py
git diff a1a06ac~1 src/tap_ai/bootstrap.py
git diff a1a06ac~1 src/tap_ai/main.py src/tap_ai/config/settings.py | Select-String "^-"
Test-Path .env
Select-String -Path src/tap_ai/config/settings.py -Pattern "gpt-5.4"
