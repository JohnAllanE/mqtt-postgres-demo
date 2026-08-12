import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

import paho.mqtt.client as mqtt

from server.config import settings
from server.db import db


logger = logging.getLogger("server.mqtt")

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class MqttBridge:
    def __init__(self) -> None:
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id_server,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_status: Optional[EventHandler] = None
        self._on_cmd_ack: Optional[EventHandler] = None
        self._on_monitor_samples: Optional[EventHandler] = None
        self._on_connection: Optional[EventHandler] = None

    def set_event_handlers(
        self,
        on_status: EventHandler,
        on_cmd_ack: EventHandler,
        on_monitor_samples: EventHandler,
        on_connection: EventHandler,
    ) -> None:
        self._on_status = on_status
        self._on_cmd_ack = on_cmd_ack
        self._on_monitor_samples = on_monitor_samples
        self._on_connection = on_connection

    def _dispatch(self, handler: Optional[EventHandler], payload: dict[str, Any]) -> None:
        if self._loop is None or handler is None:
            return
        fut = asyncio.run_coroutine_threadsafe(handler(payload), self._loop)
        try:
            fut.result(timeout=5)
        except Exception as exc:
            logger.exception("MQTT event handler failed: %s", exc)

    def _on_connect(self, client: mqtt.Client, _: Any, __: Any, rc: int, ___: Any = None) -> None:
        if rc != 0:
            logger.error("Server MQTT connect failed rc=%s", rc)
            self._dispatch(self._on_connection, {"connected": False, "reason": f"rc={rc}"})
            return

        topics = [
            settings.gateway_telemetry_global_topic,
            settings.gateway_telemetry_monitor_topic,
            settings.gateway_status_topic,
            settings.gateway_cmd_ack_topic,
        ]
        for topic in topics:
            client.subscribe(topic, qos=1)
            logger.info("Subscribed to topic=%s", topic)

        self._dispatch(self._on_connection, {"connected": True, "reason": "connected"})

    def _on_disconnect(self, _: mqtt.Client, __: Any, rc: int, ___: Any = None) -> None:
        self._dispatch(self._on_connection, {"connected": False, "reason": f"disconnect rc={rc}"})

    def _on_message(self, _: mqtt.Client, __: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Received invalid JSON payload on topic=%s", msg.topic)
            return

        if msg.topic == settings.gateway_status_topic:
            self._dispatch(self._on_status, payload)
            return

        if msg.topic == settings.gateway_cmd_ack_topic:
            self._dispatch(self._on_cmd_ack, payload)
            return

        if payload.get("msg_type") == "telemetry":
            self._handle_telemetry(payload)

    def _handle_telemetry(self, payload: dict[str, Any]) -> None:
        stream = payload.get("stream")
        samples = payload.get("samples", [])
        if not isinstance(samples, list):
            return

        if stream == "monitor":
            self._dispatch(self._on_monitor_samples, payload)
            return

        if stream != "global" or self._loop is None:
            return

        fut = asyncio.run_coroutine_threadsafe(self._ingest_global_samples(samples), self._loop)
        try:
            fut.result(timeout=5)
        except Exception as exc:
            logger.exception("Failed to ingest MQTT global telemetry: %s", exc)

    async def _ingest_global_samples(self, samples: list[Any]) -> None:
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

    async def publish_command(self, command: str, payload: dict[str, Any]) -> str:
        cmd_id = str(uuid4())
        message = {
            "msg_type": "command",
            "cmd_id": cmd_id,
            "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "command": command,
            "payload": payload,
        }
        info = self.client.publish(
            settings.gateway_cmd_topic,
            payload=json.dumps(message),
            qos=1,
            retain=False,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed rc={info.rc}")
        return cmd_id


bridge = MqttBridge()
