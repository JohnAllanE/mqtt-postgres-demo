import asyncio
import logging
import socket
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import settings
from server.db import db
from server.mqtt_client import ingestor


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("server")


async def _mqtt_tcp_probe(host: str, port: int, timeout_s: float = 1.0) -> bool:
    def _probe() -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    return await asyncio.to_thread(_probe)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    await db.init_schema_and_seed()
    await ingestor.start()
    try:
        yield
    finally:
        await ingestor.stop()
        await db.close()


app = FastAPI(title="MQTT Postgres Demo Server", version="0.1.0", lifespan=lifespan)

web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/web", StaticFiles(directory=web_dir), name="web")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.get("/api/v1/health")
async def health() -> dict:
    db_connected = await db.ping()
    mqtt_connected = await _mqtt_tcp_probe(settings.mqtt_broker_host, settings.mqtt_broker_port)

    return {
        "app": "mqtt-postgres-demo-server",
        "env": settings.app_env,
        "dependencies": {
            "db_connected": db_connected,
            "mqtt_connected": mqtt_connected,
        },
    }


@app.get("/api/v1/readings")
async def get_readings(
    sensor_id: str,
    limit: int = Query(default=200, ge=1, le=5000),
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
) -> dict:
    parsed_from = None
    if from_ts:
        parsed_from = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))

    parsed_to = None
    if to_ts:
        parsed_to = datetime.fromisoformat(to_ts.replace("Z", "+00:00"))

    rows = await db.get_readings(
        sensor_id=sensor_id,
        limit=limit,
        from_ts=parsed_from,
        to_ts=parsed_to,
    )
    return {"sensor_id": sensor_id, "count": len(rows), "rows": rows}


def main() -> None:
    uvicorn.run(
        "server.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
