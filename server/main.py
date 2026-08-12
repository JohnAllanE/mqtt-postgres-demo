import asyncio
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.config import settings
from server.db import db


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
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="MQTT Postgres Demo Server", version="0.1.0", lifespan=lifespan)


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
