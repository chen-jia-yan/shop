python -c "import sqlite3; c=sqlite3.connect(r'file:data/kg.db?mode=ro', uri=True); print('== 关系 =='); [print(r) for r in c.execute('SELECT type, COUNT(*) FROM kg_edges GROUP BY type ORDER BY 2 DESC')]; print('== 节点 =='); [print(r) for r in c.execute('SELECT type, COUNT(*) FROM kg_nodes GROUP BY type ORDER BY 2 DESC')]"



Get-Content data/chunk_content.csv -TotalCount 1


MATCH (n) RETURN n.scope AS scope, labels(n) AS labels, count(*) AS cnt ORDER BY scope, cnt DESC

MATCH (a)-[r]->() RETURN a.scope AS scope, type(r) AS rel, count(*) AS cnt ORDER BY scope, cnt DESC

MATCH (n) WITH labels(n) AS labels, keys(n) AS props RETURN labels, props, count(*) AS cnt ORDER BY cnt DESC LIMIT 20
