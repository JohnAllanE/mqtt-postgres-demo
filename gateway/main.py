import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

import paho.mqtt.client as mqtt

from gateway.config import settings


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("gateway")


SEQ = int(time.time())
MONITOR_SEQ = int(time.time())


STATE = {
    "global_config": {
        "sensor_ids": ["ac-1", "env-1", "pump-1"],
        "freq_hz": settings.global_default_freq_hz,
        "batch_window_ms": settings.global_default_batch_ms,
    },
    "monitor_config": {
        "enabled": False,
        "sensor_ids": [],
        "freq_hz": settings.monitor_default_freq_hz,
        "batch_window_ms": settings.monitor_default_batch_ms,
    },
    "retention_policy": {
        "max_age_seconds": 86400,
        "max_rows_per_sensor": 20000,
        "cleanup_interval_seconds": 60,
    },
    "thermostat": {
        "sensor_id": "ac-1",
        "setpoint_f": 72.0,
        "response": {
            "time_constant_seconds": 90,
            "max_delta_per_minute": 4.0,
        },
    },
}


def _status_topic() -> str:
    return settings.status_topic


def _telemetry_topic() -> str:
    return settings.telemetry_global_topic


def _monitor_telemetry_topic() -> str:
    return settings.telemetry_monitor_topic


def _command_topic() -> str:
    return settings.command_topic


def _command_ack_topic() -> str:
    return settings.command_ack_topic


def _status_payload() -> dict:
    return {
        "msg_type": "status",
        "gateway_id": settings.mqtt_client_id_gateway,
        "ts": datetime.now(timezone.utc).isoformat(),
        "broker_connected": True,
        "global_config": STATE["global_config"],
        "monitor_config": STATE["monitor_config"],
        "thermostat": STATE["thermostat"],
        "sensors": [
            {
                "sensor_id": "ac-1",
                "type_id": "ac_unit_v1",
                "online": True,
                "last_seen_ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "sensor_id": "env-1",
                "type_id": "env_quality_v1",
                "online": True,
                "last_seen_ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "sensor_id": "pump-1",
                "type_id": "pump_v1",
                "online": True,
                "last_seen_ts": datetime.now(timezone.utc).isoformat(),
            },
        ],
    }


def _next_ac_values(now_epoch: float) -> list[float]:
    condenser = 72.0 + 4.0 * math.sin(now_epoch / 8.0)
    evaporator = 55.0 + 2.5 * math.sin(now_epoch / 7.5 + 0.8)
    high_side = 180.0 + 12.0 * math.sin(now_epoch / 12.0)
    low_side = 30.0 + 5.0 * math.sin(now_epoch / 10.0 + 1.2)
    return [round(condenser, 3), round(evaporator, 3), round(high_side, 3), round(low_side, 3)]


def _telemetry_payload() -> dict:
    global SEQ
    now = datetime.now(timezone.utc)
    SEQ += 1

    return {
        "msg_type": "telemetry",
        "stream": "global",
        "gateway_id": settings.mqtt_client_id_gateway,
        "sent_ts": now.isoformat(),
        "samples": [
            {
                "sensor_id": "ac-1",
                "type_id": "ac_unit_v1",
                "sample_ts": now.isoformat(),
                "values": _next_ac_values(now.timestamp()),
                "seq": SEQ,
            }
        ],
    }


def _monitor_telemetry_payload() -> dict:
    global MONITOR_SEQ
    now = datetime.now(timezone.utc)
    MONITOR_SEQ += 1

    return {
        "msg_type": "telemetry",
        "stream": "monitor",
        "gateway_id": settings.mqtt_client_id_gateway,
        "sent_ts": now.isoformat(),
        "samples": [
            {
                "sensor_id": "ac-1",
                "type_id": "ac_unit_v1",
                "sample_ts": now.isoformat(),
                "values": _next_ac_values(now.timestamp()),
                "seq": MONITOR_SEQ,
            }
        ],
    }


def _publish_status(client: mqtt.Client) -> None:
    payload = json.dumps(_status_payload())
    info = client.publish(_status_topic(), payload=payload, qos=1, retain=False)
    if info.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info("Published gateway status")
    else:
        logger.error("Failed to publish status rc=%s", info.rc)


def _publish_ack(client: mqtt.Client, cmd_id: str, ok: bool, error: Optional[str] = None) -> None:
    payload = {
        "msg_type": "command_ack",
        "cmd_id": cmd_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "error": error,
    }
    info = client.publish(_command_ack_topic(), payload=json.dumps(payload), qos=1, retain=False)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.error("Failed to publish command ack rc=%s", info.rc)


def _handle_command(client: mqtt.Client, payload: dict[str, Any]) -> None:
    cmd = payload.get("command")
    cmd_id = str(payload.get("cmd_id") or "")
    body = payload.get("payload") or {}

    if not cmd_id:
        return

    try:
        if cmd == "set_global_config":
            STATE["global_config"]["sensor_ids"] = body.get("sensor_ids", STATE["global_config"]["sensor_ids"])
            STATE["global_config"]["freq_hz"] = float(body.get("freq_hz", STATE["global_config"]["freq_hz"]))
            STATE["global_config"]["batch_window_ms"] = int(body.get("batch_window_ms", STATE["global_config"]["batch_window_ms"]))
            _publish_ack(client, cmd_id, True)
            _publish_status(client)
            return

        if cmd == "set_monitor_config":
            STATE["monitor_config"]["enabled"] = bool(body.get("enabled", STATE["monitor_config"]["enabled"]))
            STATE["monitor_config"]["sensor_ids"] = body.get("sensor_ids", STATE["monitor_config"]["sensor_ids"])
            STATE["monitor_config"]["freq_hz"] = float(body.get("freq_hz", STATE["monitor_config"]["freq_hz"]))
            STATE["monitor_config"]["batch_window_ms"] = int(body.get("batch_window_ms", STATE["monitor_config"]["batch_window_ms"]))
            _publish_ack(client, cmd_id, True)
            _publish_status(client)
            return

        if cmd == "set_retention_policy":
            STATE["retention_policy"]["max_age_seconds"] = int(body.get("max_age_seconds", STATE["retention_policy"]["max_age_seconds"]))
            STATE["retention_policy"]["max_rows_per_sensor"] = int(body.get("max_rows_per_sensor", STATE["retention_policy"]["max_rows_per_sensor"]))
            STATE["retention_policy"]["cleanup_interval_seconds"] = int(body.get("cleanup_interval_seconds", STATE["retention_policy"]["cleanup_interval_seconds"]))
            _publish_ack(client, cmd_id, True)
            _publish_status(client)
            return

        if cmd == "request_status":
            _publish_ack(client, cmd_id, True)
            _publish_status(client)
            return

        if cmd == "reset_gateway_state":
            STATE["global_config"]["sensor_ids"] = ["ac-1", "env-1", "pump-1"]
            STATE["global_config"]["freq_hz"] = settings.global_default_freq_hz
            STATE["global_config"]["batch_window_ms"] = settings.global_default_batch_ms
            STATE["monitor_config"]["enabled"] = False
            STATE["monitor_config"]["sensor_ids"] = []
            STATE["monitor_config"]["freq_hz"] = settings.monitor_default_freq_hz
            STATE["monitor_config"]["batch_window_ms"] = settings.monitor_default_batch_ms
            _publish_ack(client, cmd_id, True)
            _publish_status(client)
            return

        _publish_ack(client, cmd_id, False, error=f"Unknown command: {cmd}")
    except Exception as exc:
        _publish_ack(client, cmd_id, False, error=str(exc))


def on_message(_: mqtt.Client, client_userdata: Any, msg: mqtt.MQTTMessage) -> None:
    client = client_userdata
    if not isinstance(client, mqtt.Client):
        return

    if msg.topic != _command_topic():
        return

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        logger.warning("Gateway received invalid command JSON")
        return

    _handle_command(client, payload)


def on_connect(client: mqtt.Client, _: object, __: object, rc: int, ___: object = None) -> None:
    if rc != 0:
        logger.error("Gateway failed to connect to MQTT broker with rc=%s", rc)
        return

    client.subscribe(_command_topic(), qos=1)
    _publish_status(client)


def main() -> None:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id_gateway,
        userdata=None,
    )
    client.user_data_set(client)
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(
        "Connecting gateway to MQTT broker at %s:%s",
        settings.mqtt_broker_host,
        settings.mqtt_broker_port,
    )
    client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=60)
    client.loop_start()

    last_global_emit = 0.0
    last_monitor_emit = 0.0

    try:
        while True:
            now_mono = time.monotonic()

            global_freq = max(float(STATE["global_config"]["freq_hz"]), 0.1)
            global_interval = 1.0 / global_freq
            if now_mono - last_global_emit >= global_interval:
                payload = json.dumps(_telemetry_payload())
                info = client.publish(_telemetry_topic(), payload=payload, qos=0, retain=False)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    logger.warning("Global telemetry publish returned rc=%s", info.rc)
                last_global_emit = now_mono

            monitor_enabled = bool(STATE["monitor_config"]["enabled"])
            if monitor_enabled:
                monitor_freq = max(float(STATE["monitor_config"]["freq_hz"]), 0.1)
                monitor_interval = 1.0 / monitor_freq
                if now_mono - last_monitor_emit >= monitor_interval:
                    payload = json.dumps(_monitor_telemetry_payload())
                    info = client.publish(_monitor_telemetry_topic(), payload=payload, qos=0, retain=False)
                    if info.rc != mqtt.MQTT_ERR_SUCCESS:
                        logger.warning("Monitor telemetry publish returned rc=%s", info.rc)
                    last_monitor_emit = now_mono

            time.sleep(0.02)
    except KeyboardInterrupt:
        logger.info("Gateway interrupted, shutting down")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
