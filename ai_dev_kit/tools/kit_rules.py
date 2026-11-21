"""数据安全规则：识别“删除数据”的写法。守卫钩子、静态检查共用这一份。

规则：数据可以随便写；删除数据不是不行，是不能乱删——先评估风险、告诉用户、等用户同意。
守卫拦下删除命令时用 assess() 生成风险说明；测试和脚本在 kit_run.py 下运行时，删除调用默认被拦，
用户同意后用 kit_run.py --allow-delete 重新运行（删除照常执行，但每一次都记日志）。
这里只认“删数据”，不管删文件（删文件由守卫的另一条规则问用户）。

识别三类写法：
    命令    cypher-shell / mysql -e / curl -X DELETE / az ... delete 等
    SQL     DELETE FROM、TRUNCATE、DROP TABLE/DATABASE/INDEX ...
    Cypher  DETACH DELETE、MATCH ... DELETE n、DROP INDEX/CONSTRAINT
    Python  .delete(...)、.delete_documents(...)、requests.delete(...)、method="DELETE"

另外单独识别 Cypher 的 REMOVE（删属性或标签，不删节点）：守卫对它“先问用户”，不直接拦。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SQL_DELETE = re.compile(
    r"(?is)(?:^|[;(\s'\"`])("
    r"delete\s+from\b|delete\s+[a-z_][\w.`\"\[\]]*\s+from\b|"
    r"truncate\s+(?:table\s+)?[a-z_`\"\[]|"
    r"drop\s+(?:table|database|schema|index|view|collection|keyspace)\b"
    r")"
)
CYPHER_DELETE = re.compile(
    r"(?is:\bdetach\s+delete\b)|(?s:\b(?:MATCH|WITH|UNWIND|CALL)\b.{0,400}?\bDELETE\s+[A-Za-z_]\w*)|"
    r"(?i:\bdrop\s+(?:index|constraint|database|alias)\b)"
)
CYPHER_REMOVE = re.compile(r"(?s)\b(?:MATCH|WITH)\b.{0,400}?\bREMOVE\s+[A-Za-z_]\w*\s*[.:]")
HTTP_DELETE_CMD = re.compile(
    r"(?i)(?:\bcurl\b[^|;&\n]*(?:-X\s*|--request\s+)['\"]?DELETE\b)|"
    r"(?:\b(?:invoke-restmethod|invoke-webrequest|irm|iwr)\b[^|;&\n]*-method\s+['\"]?delete\b)|"
    r"(?:\bhttp[s]?\s+delete\b)|"
    r"(?:\b(?:curl|wget|invoke-restmethod|invoke-webrequest|irm|iwr)\b[^|;&\n]*https?://[^\s'\"]*/(?:delete|remove|purge|drop)(?:[/?#'\"\s_-]|$))"
)
CLOUD_DELETE_CMD = re.compile(
    r"(?i)\baz\s+(?:search|storage|cosmosdb|sql|mysql|postgres|redis|neo4j|cognitiveservices)\b[^|;&\n]*\b(?:delete|purge)\b|"
    r"\bazcopy\s+(?:rm|remove)\b|\bgsutil\s+(?:rm|rb)\b|\baws\s+s3\s+(?:rm|rb)\b|"
    r"\bredis-cli\b[^|;&\n]*\b(?:del|unlink|flushdb|flushall)\b"
)
PY_DELETE_CALL = re.compile(
    r"\.(?:delete|delete_[a-z]\w*|purge\w*|drop_[a-z]\w*|truncate\w*|flushdb|flushall|"
    r"remove_documents|delete_many|delete_one|deleteMany|deleteOne)\s*\("
)
PY_HTTP_DELETE = re.compile(r"(?i)\bmethod\s*=\s*['\"]delete['\"]|\b(?:requests|httpx|session|client)\.delete\s*\(")

# 测试里允许删“假对象”：调用者的名字以这些词开头时不算删真数据，例如 fake_repo.delete(...)
FAKE_RECEIVER = re.compile(r"(?i)(?:^|[\s.(=,])_?(fake|stub|mock|dummy|memory|inmemory|in_memory)\w*\s*$")


@dataclass
class Finding:
    kind: str       # sql / cypher / cypher-remove / http / cloud / python
    line: int       # 1 开始；命令时为 0
    snippet: str

    def describe(self) -> str:
        where = f"第 {self.line} 行：" if self.line else ""
        return f"{where}{self.snippet}"


def _snip(text: str, start: int, width: int = 70) -> str:
    s = text[max(0, start - 10): start + width].replace("\n", " ").strip()
    return s if len(s) <= width else s[:width] + "…"


def scan_text(text: str) -> list[Finding]:
    """扫描一段命令或查询文本（不是 Python 源码），返回“删数据”的写法。"""
    found: list[Finding] = []
    for kind, pattern in (("sql", SQL_DELETE), ("cypher", CYPHER_DELETE), ("http", HTTP_DELETE_CMD),
                          ("cloud", CLOUD_DELETE_CMD)):
        m = pattern.search(text)
        if m:
            found.append(Finding(kind, 0, _snip(text, m.start())))
    return found


def scan_remove(text: str) -> Finding | None:
    """Cypher 的 REMOVE（删属性或标签）。不是红线，守卫会先问用户。"""
    m = CYPHER_REMOVE.search(text)
    return Finding("cypher-remove", 0, _snip(text, m.start())) if m else None


def scan_python(source: str, allow_fakes: bool = True) -> list[Finding]:
    """扫描 Python 源码。只看真正的代码行和字符串，跳过注释行。"""
    found: list[Finding] = []
    for no, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        code = stripped.split("  #", 1)[0]
        for kind, pattern in (("sql", SQL_DELETE), ("cypher", CYPHER_DELETE)):
            if pattern.search(code) and re.search(r"['\"]", code):
                found.append(Finding(kind, no, stripped[:90]))
                break
        else:
            m = PY_DELETE_CALL.search(code) or PY_HTTP_DELETE.search(code)
            if m:
                if allow_fakes and is_fake_receiver(code[: m.start()]):
                    continue
                found.append(Finding("python", no, stripped[:90]))
    return found


def is_fake_receiver(code_before_call: str) -> bool:
    """调用前面的对象名是不是假对象（fake_repo、stub_client、memory_store……）。"""
    return bool(FAKE_RECEIVER.search(code_before_call))


# ---------------------------------------------------------------- 删除前的风险评估
#
# 删数据不是禁止，而是“先评估、告诉用户、等用户同意”。这里根据语句本身做一个粗评估，
# 帮模型把风险说清楚：删什么、范围多大、能不能恢复、删之前该做什么。

PROD_HOST = re.compile(r"(?i)(prod|prd|live|master|primary|\.azure\.|\.windows\.net|\.neo4j\.io|\.rds\.|\.cosmos\.|database\.azure)")
LOCAL_HOST = re.compile(r"(?i)(localhost|127\.0\.0\.1|::1|testserver|\btest\b|sqlite|:memory:|\bdev\b|\bsandbox\b)")
WHERE_CLAUSE = re.compile(r"(?i)\bwhere\b")
CYPHER_LABEL_FILTER = re.compile(r"\(\s*\w*\s*:\s*\w+[^)]*\{[^}]+\}|\bWHERE\b|\bid\s*\(|elementId\s*\(")
CYPHER_ALL_NODES = re.compile(r"(?i)\bMATCH\s*\(\s*\w+\s*\)\s*(?:DETACH\s+)?DELETE")
LIMIT_CLAUSE = re.compile(r"(?i)\blimit\s+\d+")


@dataclass
class Risk:
    level: str              # 高 / 中 / 低
    what: list[str]         # 要删什么
    scope: str              # 范围
    recover: str            # 能否恢复
    before: list[str]       # 删之前建议做什么

    def render(self) -> str:
        lines = [f"风险：{self.level}",
                 "要删除：" + "；".join(self.what[:4]),
                 f"影响范围：{self.scope}",
                 f"能否恢复：{self.recover}"]
        if self.before:
            lines.append("删之前建议：" + "；".join(self.before))
        return "\n".join(lines)


def assess(text: str, findings: list[Finding] | None = None) -> Risk:
    """对一条命令、一段查询或一个脚本的删除风险做粗评估。"""
    findings = findings if findings is not None else (scan_text(text) or scan_python(text))
    kinds = {f.kind for f in findings}
    what = [f.describe() for f in findings] or ["（没识别出具体语句）"]
    high: list[str] = []
    medium: list[str] = []
    if re.search(r"(?i)\b(drop|truncate)\b", text):
        high.append("DROP / TRUNCATE 会整表、整库或整个索引删除")
    if CYPHER_ALL_NODES.search(text):
        high.append("MATCH (n) 不带标签和条件，会删掉图里所有节点")
    if "sql" in kinds and re.search(r"(?i)delete\s+from", text) and not WHERE_CLAUSE.search(text):
        high.append("DELETE 没有 WHERE 条件，会删整张表")
    if "cypher" in kinds and not CYPHER_LABEL_FILTER.search(text) and not CYPHER_ALL_NODES.search(text):
        medium.append("Cypher 删除没有看到明确的过滤条件")
    if "cloud" in kinds:
        high.append("云资源删除（索引、存储、数据库）通常无法撤销")
    if "http" in kinds or "python" in kinds:
        medium.append("通过接口或客户端删除，实际范围取决于参数")
    if PROD_HOST.search(text):
        high.append("目标看起来是线上或共享环境")
    local = bool(LOCAL_HOST.search(text)) and not PROD_HOST.search(text)
    if high:
        level = "高"
    elif medium and not local:
        level = "中"
    else:
        level = "低" if local else "中"
    if high:
        scope = "；".join(high)
    elif medium:
        scope = "；".join(medium)
    else:
        scope = "带条件的定向删除" + ("，目标是本地或测试环境" if local else "")
    if LIMIT_CLAUSE.search(text):
        scope += "（带 LIMIT，单次数量有上限）"
    recover = ("通常无法恢复，除非事先有备份或快照" if level != "低"
               else "本地或测试数据，影响小；共享数据仍然无法恢复")
    before = ["先用同样的条件做一次只读查询（SELECT COUNT / MATCH ... RETURN count），把会删掉的数量告诉用户"]
    if level == "高":
        before.append("先导出或备份要删的数据（或者确认有快照）")
        before.append("能改成软删除（打标记）就别真删")
    if "cypher" in kinds or "sql" in kinds:
        before.append("确认连接的是哪个库（地址、库名），不要在共享库上试")
    return Risk(level, what, scope, recover, before)
