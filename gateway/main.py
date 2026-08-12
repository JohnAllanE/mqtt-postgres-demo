import json
import logging
import math
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from gateway.config import settings


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("gateway")


SEQ = 0


def _status_topic() -> str:
    return settings.status_topic


def _telemetry_topic() -> str:
    return settings.telemetry_global_topic


def _status_payload() -> dict:
    return {
        "msg_type": "status",
        "gateway_id": settings.mqtt_client_id_gateway,
        "ts": datetime.now(timezone.utc).isoformat(),
        "broker_connected": True,
        "global_config": {
            "sensor_ids": ["ac-1", "env-1", "pump-1"],
            "freq_hz": 1.0,
            "batch_window_ms": 1000,
        },
        "monitor_config": {
            "enabled": False,
            "sensor_ids": [],
            "freq_hz": 10.0,
            "batch_window_ms": 500,
        },
        "thermostat": {
            "sensor_id": "ac-1",
            "setpoint_f": 72.0,
            "response": {
                "time_constant_seconds": 90,
                "max_delta_per_minute": 4.0,
            },
        },
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


def on_connect(client: mqtt.Client, _: object, __: object, rc: int, ___: object = None) -> None:
    if rc != 0:
        logger.error("Gateway failed to connect to MQTT broker with rc=%s", rc)
        return

    payload = json.dumps(_status_payload())
    topic = _status_topic()
    info = client.publish(topic, payload=payload, qos=1, retain=False)
    if info.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info("Published initial gateway status to topic=%s", topic)
    else:
        logger.error("Failed to publish initial status rc=%s", info.rc)


def main() -> None:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id_gateway,
    )
    client.on_connect = on_connect

    logger.info(
        "Connecting gateway to MQTT broker at %s:%s",
        settings.mqtt_broker_host,
        settings.mqtt_broker_port,
    )
    client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=60)
    client.loop_start()

    interval_s = 1.0 / max(settings.global_default_freq_hz, 0.1)
    logger.info("Publishing global telemetry to topic=%s at %.3f Hz", _telemetry_topic(), settings.global_default_freq_hz)

    try:
        while True:
            payload = json.dumps(_telemetry_payload())
            info = client.publish(_telemetry_topic(), payload=payload, qos=0, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("Global telemetry publish returned rc=%s", info.rc)
            time.sleep(interval_s)
    except KeyboardInterrupt:
        logger.info("Gateway interrupted, shutting down")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
