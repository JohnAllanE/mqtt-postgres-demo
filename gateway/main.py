import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from gateway.config import settings


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("gateway")


def _status_topic() -> str:
    gateway_id = settings.mqtt_client_id_gateway
    return f"{settings.mqtt_topic_prefix}/gateway/{gateway_id}/status"


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
    client.loop_forever()


if __name__ == "__main__":
    main()
