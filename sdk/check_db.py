import asyncio
import os

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def diagnose() -> None:
    url = make_url(os.environ["TAP_AI_DATABASE_URL"])
    ca = url.query.get("ssl_ca")
    print("host =", url.host)
    print("database =", url.database)
    print("query keys =", sorted(url.query.keys()))
    print("ssl_ca =", repr(ca))
    if isinstance(ca, str):
        print("ssl_ca exists =", os.path.isfile(ca))
    folder = r"C:\Users\234393\Desktop\private"
    print("private folder =", os.listdir(folder))


async def main() -> None:
    engine = create_async_engine(os.environ["TAP_AI_DATABASE_URL"])
    async with engine.connect() as conn:
        print("SELECT 1 =", (await conn.execute(text("SELECT 1"))).scalar_one())
        rows = (await conn.execute(text("SHOW TABLES LIKE 'library%'"))).fetchall()
        print("tables =", [r[0] for r in rows])
    await engine.dispose()


diagnose()
asyncio.run(main())