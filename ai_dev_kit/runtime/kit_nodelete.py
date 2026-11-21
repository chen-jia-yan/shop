"""禁删保护（运行时）：在被保护的 Python 进程里，让常见数据客户端的“删除”直接报错。

由 tools/kit_run.py 启动的命令（以及一键验证 run_checks.py 跑的测试）会带上
环境变量 AI_DEV_KIT_NODELETE=1，并把本目录加进 PYTHONPATH；Python 启动时自动导入
本目录的 sitecustomize.py，再由它调用这里的 install()。

覆盖范围（模块被导入之后才打补丁，没装这些包也不影响）：
    neo4j             Session/Transaction/Driver 执行的 DELETE、DETACH DELETE、DROP
    SQLAlchemy        所有非 sqlite 数据库执行的 DELETE / TRUNCATE / DROP（sqlite 一般是测试用的临时库）
    pymysql / MySQLdb / mysql.connector / aiomysql   直接执行的同类语句
    requests / httpx  DELETE 请求，以及路径里带 /delete /remove /purge /drop 的请求（测试客户端 testserver 除外）
    Azure 搜索、Blob、Cosmos，Elasticsearch / OpenSearch，Milvus、Qdrant、Chroma、Redis 等客户端
                      方法名以 delete / purge / drop / truncate / flush 开头的调用

被拦下时抛出 KitDeleteBlocked（PermissionError 的子类），并写一行日志到
~/.ai-dev-kit/logs/nodelete-日期.jsonl。
用户同意删除后，kit_run.py --allow-delete 会再设置 AI_DEV_KIT_ALLOW_DELETE=1：删除照常执行，
每一次删除都记一行 "allowed" 日志。只用标准库。
"""

from __future__ import annotations

import functools
import importlib.abc
import importlib.util
import inspect
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

SQL_DELETE = re.compile(
    r"(?is)(?:^|[;(\s])(delete\s+from\b|delete\s+[a-z_][\w.`\"\[\]]*\s+from\b|truncate\s+(?:table\s+)?[a-z_`\"\[]|"
    r"drop\s+(?:table|database|schema|index|view)\b)"
)
CYPHER_DELETE = re.compile(
    r"(?is:\bdetach\s+delete\b)|(?is:\bdelete\s+[a-z_]\w*\s*(?:$|,|;|\breturn\b|\bwith\b))|"
    r"(?i:\bdrop\s+(?:index|constraint|database|alias)\b)"
)
METHOD_NAME = re.compile(r"^(delete|purge|drop|truncate|flushdb|flushall|flush_all|remove_documents|clear_collection)", re.I)
URL_PATH = re.compile(r"/(delete|remove|purge|drop)(?:$|[/_?#-])", re.I)
SAFE_HOSTS = {"testserver", "test"}

DATA_DIR = Path(os.environ.get("AI_DEV_KIT_HOME") or (Path.home() / ".ai-dev-kit"))

_installed = False
_busy: set[str] = set()


class KitDeleteBlocked(PermissionError):
    """ai-dev-kit 禁删保护拦下了一次删除数据的操作。"""


def _log(record: dict[str, Any]) -> None:
    try:
        path = DATA_DIR / "logs" / f"nodelete-{time.strftime('%Y%m%d')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(record, ts=time.strftime("%Y-%m-%d %H:%M:%S"), pid=os.getpid(), cwd=os.getcwd())
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # 写日志失败不影响被保护的程序
        pass


def _deny(where: str, detail: str) -> None:
    if os.environ.get("AI_DEV_KIT_ALLOW_DELETE") == "1":
        # 用户已同意这次运行里的删除：放行，但每一次都记下来，事后可以查
        _log({"event": "allowed", "where": where, "detail": detail[:300]})
        return
    _log({"event": "blocked", "where": where, "detail": detail[:200]})
    raise KitDeleteBlocked(
        f"ai-dev-kit 禁删保护：{where} 想删除数据（{detail[:120]}），已拦下，什么都没删。"
        "删除不是不行，但要先问用户：说明要删什么、范围多大、能不能恢复，等用户回复同意后，"
        "用 kit_run.py --allow-delete -- <原命令> 重新运行。如果这是测试里的清理代码，优先改成用假对象。"
    )


def _text_of(query: Any) -> str:
    if isinstance(query, str):
        return query
    for attr in ("text", "statement", "query"):
        val = getattr(query, attr, None)
        if isinstance(val, str):
            return val
    try:
        return str(query)
    except Exception:
        return ""


def _first_query(args: tuple[Any, ...], kwargs: dict[str, Any], skip_self: bool = True) -> Any:
    for key in ("query", "query_", "statement", "operation", "sql", "cypher"):
        if key in kwargs:
            return kwargs[key]
    rest = args[1:] if skip_self else args
    return rest[0] if rest else ""


def _wrap(func: Callable[..., Any], check: Callable[[tuple[Any, ...], dict[str, Any]], None]) -> Callable[..., Any]:
    if getattr(func, "__kit_guarded__", False):
        return func
    if inspect.iscoroutinefunction(func):
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            check(args, kwargs)
            return await func(*args, **kwargs)
        wrapper: Callable[..., Any] = functools.wraps(func)(async_wrapper)
    else:
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            check(args, kwargs)
            return func(*args, **kwargs)
        wrapper = functools.wraps(func)(sync_wrapper)
    setattr(wrapper, "__kit_guarded__", True)
    return wrapper


def _patch(cls: Any, name: str, check: Callable[[tuple[Any, ...], dict[str, Any]], None], root: str = "") -> bool:
    """给定义了这个方法的那一层类打补丁（方法常常定义在父类或混入类里）。"""
    for klass in getattr(cls, "__mro__", (cls,)):
        if klass is object or name not in getattr(klass, "__dict__", {}):
            continue
        if root and not str(getattr(klass, "__module__", "")).startswith(root):
            return False
        func = klass.__dict__[name]
        if not callable(func) or isinstance(func, (staticmethod, classmethod, property)):
            return False
        try:
            setattr(klass, name, _wrap(func, check))
            return True
        except (TypeError, AttributeError):  # C 扩展类型不能改，跳过
            return False
    return False


# ---------------------------------------------------------------- 各类客户端


def _check_cypher(where: str) -> Callable[[tuple[Any, ...], dict[str, Any]], None]:
    def check(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        text = _text_of(_first_query(args, kwargs))
        if CYPHER_DELETE.search(text):
            _deny(where, text)
    return check


def _check_sql(where: str) -> Callable[[tuple[Any, ...], dict[str, Any]], None]:
    def check(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        text = _text_of(_first_query(args, kwargs))
        if SQL_DELETE.search(text):
            _deny(where, text)
    return check


def _check_method(where: str) -> Callable[[tuple[Any, ...], dict[str, Any]], None]:
    def check(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        _deny(where, "调用了删除类方法")
    return check


def _check_http(where: str) -> Callable[[tuple[Any, ...], dict[str, Any]], None]:
    def check(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        method = kwargs.get("method", args[1] if len(args) > 1 else "")
        url = kwargs.get("url", args[2] if len(args) > 2 else "")
        method_s, url_s = str(method or "").upper(), str(url or "")
        try:
            parts = urlsplit(url_s)
        except ValueError:
            return
        if (parts.hostname or "").lower() in SAFE_HOSTS:
            return
        if method_s == "DELETE" or URL_PATH.search(parts.path or ""):
            _deny(where, f"{method_s} {url_s}")
    return check


def _patch_neo4j(module: Any) -> None:
    for cls_name in ("Session", "Transaction", "ManagedTransaction", "AsyncSession", "AsyncTransaction",
                     "AsyncManagedTransaction"):
        cls = getattr(module, cls_name, None)
        if cls is not None:
            _patch(cls, "run", _check_cypher(f"neo4j.{cls_name}.run"))
    for cls_name in ("Driver", "AsyncDriver"):
        cls = getattr(module, cls_name, None)
        if cls is not None:
            _patch(cls, "execute_query", _check_cypher(f"neo4j.{cls_name}.execute_query"))


def _patch_sqlalchemy(module: Any) -> None:
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
    except Exception:
        return

    def before_cursor_execute(conn: Any, cursor: Any, statement: Any, parameters: Any,
                              context: Any, executemany: Any) -> None:
        dialect = getattr(getattr(conn, "dialect", None), "name", "")
        if dialect == "sqlite":  # 测试常用的临时 sqlite 库，删了也不影响真实数据
            return
        if SQL_DELETE.search(_text_of(statement)):
            _deny(f"SQLAlchemy({dialect})", _text_of(statement))

    if not getattr(Engine, "__kit_listener__", False):
        event.listen(Engine, "before_cursor_execute", before_cursor_execute)
        setattr(Engine, "__kit_listener__", True)


def _patch_cursor_module(module: Any, class_names: tuple[str, ...]) -> None:
    for cls_name in class_names:
        cls = getattr(module, cls_name, None)
        if cls is None:
            continue
        for meth in ("execute", "executemany"):
            _patch(cls, meth, _check_sql(f"{module.__name__}.{cls_name}.{meth}"))


def _patch_http(module: Any) -> None:
    name = module.__name__
    if name == "requests.sessions":
        cls = getattr(module, "Session", None)
        if cls is not None:
            _patch(cls, "request", _check_http("requests"))
    elif name == "httpx":
        for cls_name in ("Client", "AsyncClient"):
            cls = getattr(module, cls_name, None)
            if cls is not None:
                _patch(cls, "request", _check_http(f"httpx.{cls_name}"))


def _patch_clients(module: Any) -> None:
    """数据服务的客户端：把名字以 delete / purge / drop / truncate 开头的方法都拦下（含父类里定义的）。"""
    root = module.__name__.split(".")[0]
    for attr in list(vars(module).values()):
        if not inspect.isclass(attr) or not str(getattr(attr, "__module__", "")).startswith(root):
            continue
        for meth_name in dir(attr):
            if METHOD_NAME.match(meth_name):
                _patch(attr, meth_name, _check_method(f"{attr.__name__}.{meth_name}"), root=root)


PATCHERS: dict[str, Callable[[Any], None]] = {
    "neo4j": _patch_neo4j,
    "sqlalchemy": _patch_sqlalchemy,
    "pymysql.cursors": lambda m: _patch_cursor_module(m, ("Cursor", "SSCursor", "DictCursor", "SSDictCursor")),
    "MySQLdb.cursors": lambda m: _patch_cursor_module(m, ("BaseCursor",)),
    "mysql.connector.cursor": lambda m: _patch_cursor_module(m, ("MySQLCursor",)),
    "aiomysql.cursors": lambda m: _patch_cursor_module(m, ("Cursor",)),
    "requests.sessions": _patch_http,
    "httpx": _patch_http,
}
CLIENT_MODULES = (
    "azure.search.documents", "azure.search.documents.aio", "azure.search.documents.indexes",
    "azure.search.documents.indexes.aio", "azure.storage.blob", "azure.storage.blob.aio", "azure.cosmos",
    "azure.cosmos.aio", "elasticsearch", "opensearchpy", "pymilvus", "qdrant_client", "chromadb",
    "redis", "redis.asyncio", "pinecone", "weaviate", "pymongo.collection", "pymongo.database",
)
for _name in CLIENT_MODULES:
    PATCHERS.setdefault(_name, _patch_clients)


def _apply(name: str, module: Any) -> None:
    patcher = PATCHERS.get(name)
    if patcher is None:
        return
    try:
        patcher(module)
    except Exception as exc:  # 打补丁失败不能影响程序本身
        _log({"event": "patch-error", "module": name, "error": repr(exc)[:200]})


class _PostImportFinder(importlib.abc.MetaPathFinder):
    """模块导入完成后再打补丁：不提前导入任何第三方包。"""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname not in PATCHERS or fullname in _busy:
            return None
        _busy.add(fullname)
        try:
            spec = importlib.util.find_spec(fullname)
        except Exception:
            return None
        finally:
            _busy.discard(fullname)
        loader = getattr(spec, "loader", None) if spec else None
        exec_module = getattr(loader, "exec_module", None)
        if spec is None or exec_module is None or inspect.isclass(loader):
            return spec

        def patched_exec(module: Any, _orig: Callable[[Any], None] = exec_module, _name: str = fullname) -> None:
            _orig(module)
            _apply(_name, module)

        try:
            setattr(loader, "exec_module", patched_exec)
        except Exception:
            return spec
        return spec


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    sys.meta_path.insert(0, _PostImportFinder())
    for name in list(PATCHERS):
        if name in sys.modules:
            _apply(name, sys.modules[name])
    _log({"event": "active", "argv": " ".join(sys.argv)[:200]})


def is_active() -> bool:
    return _installed
