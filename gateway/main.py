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
        "setpoint_f": settings.thermostat_default_setpoint_f,
        "response": {
            "time_constant_seconds": settings.thermostat_response_time_constant_seconds,
            "max_delta_per_minute": settings.thermostat_max_delta_per_minute,
        },
        "last_set_cmd_ts": None,
    },
    "ac_dynamics": {
        "last_update_ts": time.time(),
        "channels": {
            "condenser_temp_f": settings.thermostat_default_setpoint_f,
            "evaporator_temp_f": settings.thermostat_default_setpoint_f - 17.0,
            "high_side_psi": 180.0,
            "low_side_psi": 30.0,
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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _next_ac_values(now_epoch: float) -> list[float]:
    thermo = STATE["thermostat"]
    response = thermo["response"]
    channels = STATE["ac_dynamics"]["channels"]

    last_update = float(STATE["ac_dynamics"]["last_update_ts"])
    dt = _clamp(now_epoch - last_update, 0.02, 1.0)
    STATE["ac_dynamics"]["last_update_ts"] = now_epoch

    setpoint = float(thermo["setpoint_f"])
    time_constant = float(response["time_constant_seconds"])
    max_delta_per_minute = float(response["max_delta_per_minute"])

    targets = {
        "condenser_temp_f": setpoint + 0.35 * math.sin(now_epoch / 18.0),
        "evaporator_temp_f": (setpoint - 17.0) + 0.25 * math.sin(now_epoch / 16.0 + 0.7),
        "high_side_psi": 180.0 + (setpoint - 72.0) * 2.5 + 3.0 * math.sin(now_epoch / 14.0),
        "low_side_psi": 30.0 + (72.0 - setpoint) * 0.8 + 1.4 * math.sin(now_epoch / 12.0 + 1.1),
    }
    noise_terms = {
        "condenser_temp_f": 0.03 * math.sin(now_epoch * 2.3),
        "evaporator_temp_f": 0.03 * math.sin(now_epoch * 1.9 + 1.2),
        "high_side_psi": 0.09 * math.sin(now_epoch * 1.5 + 0.4),
        "low_side_psi": 0.07 * math.sin(now_epoch * 1.7 + 2.1),
    }

    max_step_temp = max_delta_per_minute * dt / 60.0
    max_step_psi = max_step_temp * 6.0

    updated = {}
    for channel, target in targets.items():
        current = float(channels[channel])
        raw_step = (target - current) * (dt / time_constant)
        channel_step_cap = max_step_psi if channel.endswith("psi") else max_step_temp
        clamped_step = _clamp(raw_step, -channel_step_cap, channel_step_cap)
        updated[channel] = current + clamped_step + noise_terms[channel]

    channels.update(updated)
    return [
        round(float(channels["condenser_temp_f"]), 3),
        round(float(channels["evaporator_temp_f"]), 3),
        round(float(channels["high_side_psi"]), 3),
        round(float(channels["low_side_psi"]), 3),
    ]


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

        if cmd in ("set_thermostat_setpoint", "set_thermostat_set_point"):
            sensor_id = str(body.get("sensor_id") or "")
            if sensor_id != STATE["thermostat"]["sensor_id"]:
                _publish_ack(
                    client,
                    cmd_id,
                    False,
                    error=f"Unsupported thermostat sensor_id: {sensor_id}",
                )
                return

            setpoint_f = float(body.get("setpoint_f"))
            if not (
                settings.thermostat_min_setpoint_f
                <= setpoint_f
                <= settings.thermostat_max_setpoint_f
            ):
                _publish_ack(
                    client,
                    cmd_id,
                    False,
                    error=(
                        f"setpoint_f must be in range "
                        f"{settings.thermostat_min_setpoint_f}-{settings.thermostat_max_setpoint_f}"
                    ),
                )
                return

            transition = body.get("transition") or {}
            if transition:
                time_constant_seconds = int(
                    transition.get(
                        "time_constant_seconds",
                        STATE["thermostat"]["response"]["time_constant_seconds"],
                    )
                )
                max_delta_per_minute = float(
                    transition.get(
                        "max_delta_per_minute",
                        STATE["thermostat"]["response"]["max_delta_per_minute"],
                    )
                )
                if not (10 <= time_constant_seconds <= 600):
                    _publish_ack(
                        client,
                        cmd_id,
                        False,
                        error="transition.time_constant_seconds must be in range 10-600",
                    )
                    return
                if not (0.5 <= max_delta_per_minute <= 10.0):
                    _publish_ack(
                        client,
                        cmd_id,
                        False,
                        error="transition.max_delta_per_minute must be in range 0.5-10.0",
                    )
                    return
                STATE["thermostat"]["response"]["time_constant_seconds"] = time_constant_seconds
                STATE["thermostat"]["response"]["max_delta_per_minute"] = max_delta_per_minute

            STATE["thermostat"]["setpoint_f"] = setpoint_f
            STATE["thermostat"]["last_set_cmd_ts"] = datetime.now(timezone.utc).isoformat()
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
            STATE["thermostat"]["setpoint_f"] = settings.thermostat_default_setpoint_f
            STATE["thermostat"]["response"]["time_constant_seconds"] = settings.thermostat_response_time_constant_seconds
            STATE["thermostat"]["response"]["max_delta_per_minute"] = settings.thermostat_max_delta_per_minute
            STATE["thermostat"]["last_set_cmd_ts"] = None
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
