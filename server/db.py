from pathlib import Path

import asyncpg

from server.config import settings


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ping(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("select 1")
            return True
        except Exception:
            return False

    async def init_schema_and_seed(self) -> None:
        if self.pool is None:
            raise RuntimeError("Database pool is not connected")

        schema_sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        seed_sql = Path(__file__).with_name("seed.sql").read_text(encoding="utf-8")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(schema_sql)
                await conn.execute(seed_sql)


db = Database()
