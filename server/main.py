import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.config import settings
from server.db import db
from server.mqtt_client import bridge


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("server")


class WsHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        envelope = {
            "event": event,
            "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "data": data,
        }
        dead: list[WebSocket] = []
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_json(envelope)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)


ws_hub = WsHub()

STATE: dict[str, Any] = {
    "gateway_status": {},
    "last_command_ack": {},
    "mqtt_connection": {"connected": False, "reason": "not-started"},
}


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


async def _on_status(payload: dict[str, Any]) -> None:
    STATE["gateway_status"] = payload
    await ws_hub.broadcast("status_update", payload)


async def _on_cmd_ack(payload: dict[str, Any]) -> None:
    STATE["last_command_ack"] = payload
    await ws_hub.broadcast("command_ack", payload)


async def _on_monitor_samples(payload: dict[str, Any]) -> None:
    await ws_hub.broadcast("monitor_samples", payload)


async def _on_connection(payload: dict[str, Any]) -> None:
    STATE["mqtt_connection"] = payload
    await ws_hub.broadcast("connection_update", payload)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    await db.init_schema_and_seed()
    if settings.clear_readings_on_startup:
        deleted = await db.clear_readings()
        logger.info("Cleared %s historical rows at startup", deleted)
    bridge.set_event_handlers(_on_status, _on_cmd_ack, _on_monitor_samples, _on_connection)
    await bridge.start()
    try:
        yield
    finally:
        await bridge.stop()
        await db.close()


app = FastAPI(title="MQTT Postgres Demo Server", version="0.2.0", lifespan=lifespan)

web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/web", StaticFiles(directory=web_dir), name="web")


class GlobalConfigRequest(BaseModel):
    sensor_ids: list[str] = Field(default_factory=list)
    freq_hz: float = Field(ge=0.1, le=20.0)
    batch_window_ms: int = Field(ge=100, le=5000)


class MonitorConfigRequest(BaseModel):
    enabled: bool
    sensor_ids: list[str] = Field(default_factory=list)
    freq_hz: float = Field(ge=0.1, le=20.0)
    batch_window_ms: int = Field(ge=100, le=5000)


class RetentionConfigRequest(BaseModel):
    max_age_seconds: int = Field(gt=0)
    max_rows_per_sensor: int = Field(gt=0)
    cleanup_interval_seconds: int = Field(gt=0)


class ThermostatTransitionRequest(BaseModel):
    time_constant_seconds: int = Field(ge=10, le=600)
    max_delta_per_minute: float = Field(ge=0.5, le=10.0)


class ThermostatSetpointRequest(BaseModel):
    sensor_id: str
    setpoint_f: float = Field(ge=60.0, le=80.0)
    transition: Optional[ThermostatTransitionRequest] = None


class ResetRequest(BaseModel):
    clear_monitor: bool = True
    restore_defaults: bool = True


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


@app.get("/api/v1/status")
async def status() -> dict:
    return {
        "gateway_status": STATE["gateway_status"],
        "last_command_ack": STATE["last_command_ack"],
        "mqtt_connection": STATE["mqtt_connection"],
    }


@app.get("/api/v1/sensors")
async def sensors() -> dict:
    rows = await db.get_sensors()
    return {"count": len(rows), "rows": rows}


@app.post("/api/v1/sensors/refresh-status")
async def refresh_status() -> dict:
    cmd_id = await bridge.publish_command("request_status", {})
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/gateway/config/global")
async def set_global_config(req: GlobalConfigRequest) -> dict:
    cmd_id = await bridge.publish_command("set_global_config", req.model_dump())
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/gateway/config/monitor")
async def set_monitor_config(req: MonitorConfigRequest) -> dict:
    cmd_id = await bridge.publish_command("set_monitor_config", req.model_dump())
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/gateway/config/retention")
async def set_retention_config(req: RetentionConfigRequest) -> dict:
    cmd_id = await bridge.publish_command("set_retention_policy", req.model_dump())
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/gateway/config/thermostat-setpoint")
async def set_thermostat_setpoint(req: ThermostatSetpointRequest) -> dict:
    cmd_id = await bridge.publish_command("set_thermostat_setpoint", req.model_dump())
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/gateway/reset")
async def reset_gateway(req: ResetRequest) -> dict:
    cmd_id = await bridge.publish_command("reset_gateway_state", req.model_dump())
    return {"accepted": True, "cmd_id": cmd_id}


@app.post("/api/v1/admin/reset-readings")
async def reset_readings() -> dict:
    deleted = await db.clear_readings()
    return {"ok": True, "deleted_rows": deleted}


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


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws_hub.connect(ws)
    try:
        await ws.send_json(
            {
                "event": "connection_update",
                "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "data": STATE["mqtt_connection"],
            }
        )
        while True:
            # v1 server does not require client WS messages, but keep the socket alive.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        await ws_hub.disconnect(ws)


def main() -> None:
    uvicorn.run(
        "server.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
