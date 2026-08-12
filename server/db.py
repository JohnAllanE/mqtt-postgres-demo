from pathlib import Path
from datetime import datetime
from typing import Any, Optional

import asyncpg

from server.config import settings


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

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

    async def insert_global_sample(
        self,
        sensor_id: str,
        type_id: str,
        sample_ts: datetime,
        values: list[float],
        seq: Optional[int],
    ) -> bool:
        if self.pool is None:
            raise RuntimeError("Database pool is not connected")

        query = """
        insert into sensor_readings(sensor_id, type_id, sample_ts, values, seq)
        select $1, $2, $3, $4, $5
        where exists (
            select 1
            from sensor_registry sr
            where sr.sensor_id = $1 and sr.type_id = $2
        )
          and exists (
            select 1
            from sensor_type_schema st
            where st.type_id = $2
              and st.value_count = array_length($4::double precision[], 1)
        )
        """

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, sensor_id, type_id, sample_ts, values, seq)
        return result == "INSERT 0 1"

    async def get_readings(
        self,
        sensor_id: str,
        limit: int,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        if self.pool is None:
            raise RuntimeError("Database pool is not connected")

        query = """
        select sensor_id, type_id, sample_ts, values, seq
        from sensor_readings
        where sensor_id = $1
          and ($2::timestamptz is null or sample_ts >= $2::timestamptz)
          and ($3::timestamptz is null or sample_ts <= $3::timestamptz)
        order by sample_ts asc
        limit $4
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, sensor_id, from_ts, to_ts, limit)

        return [
            {
                "sensor_id": row["sensor_id"],
                "type_id": row["type_id"],
                "sample_ts": row["sample_ts"].isoformat(),
                "values": row["values"],
                "seq": row["seq"],
            }
            for row in rows
        ]


db = Database()
