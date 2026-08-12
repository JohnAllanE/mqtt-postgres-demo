import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

import paho.mqtt.client as mqtt

from server.config import settings
from server.db import db


logger = logging.getLogger("server.mqtt")


class TelemetryIngestor:
    def __init__(self) -> None:
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id_server,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_connect(self, client: mqtt.Client, _: Any, __: Any, rc: int, ___: Any = None) -> None:
        if rc != 0:
            logger.error("Server MQTT connect failed rc=%s", rc)
            return

        topic = settings.gateway_telemetry_global_topic
        client.subscribe(topic, qos=0)
        logger.info("Subscribed to topic=%s", topic)

    def _on_message(self, _: mqtt.Client, __: Any, msg: mqtt.MQTTMessage) -> None:
        if self._loop is None:
            logger.warning("Dropping MQTT message because event loop is unavailable")
            return

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Received invalid JSON telemetry payload")
            return

        fut = asyncio.run_coroutine_threadsafe(self._ingest_payload(payload), self._loop)
        try:
            fut.result(timeout=5)
        except Exception as exc:
            logger.exception("Failed to ingest MQTT payload: %s", exc)

    async def _ingest_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("msg_type") != "telemetry":
            return
        if payload.get("stream") != "global":
            return

        samples = payload.get("samples", [])
        if not isinstance(samples, list):
            return

        for sample in samples:
            if not isinstance(sample, dict):
                continue

            sensor_id = sample.get("sensor_id")
            type_id = sample.get("type_id")
            sample_ts_raw = sample.get("sample_ts")
            values = sample.get("values")
            seq = sample.get("seq")

            if not sensor_id or not type_id or not isinstance(values, list):
                continue

            try:
                sample_ts = datetime.fromisoformat(str(sample_ts_raw).replace("Z", "+00:00"))
            except ValueError:
                continue

            try:
                coerced_values = [float(v) for v in values]
            except (TypeError, ValueError):
                continue

            seq_int = None
            if seq is not None:
                try:
                    seq_int = int(seq)
                except (TypeError, ValueError):
                    seq_int = None

            await db.insert_global_sample(
                sensor_id=sensor_id,
                type_id=type_id,
                sample_ts=sample_ts,
                values=coerced_values,
                seq=seq_int,
            )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=60)
        self.client.loop_start()
        logger.info("Server MQTT loop started")

    async def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Server MQTT loop stopped")


ingestor = TelemetryIngestor()
