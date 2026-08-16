#!/usr/bin/env python3
"""Sensor simulator: pure data generator with optional TCP publisher.

This script generates simulated sensor batches and either prints them to
stdout or forwards them to a TCP server (the server that handles WebSocket
clients). It intentionally contains no WebSocket or web-serving code so it can
run on a separate machine.

Usage examples:
  # print batches to stdout
  python3 gateway/simulator.py --duration 5

  # connect to a server at 10.0.0.5:9999 and send batches
  python3 gateway/simulator.py --server-host 10.0.0.5 --server-port 9999
"""
import argparse
import asyncio
import json
import math
import random
import time
from typing import Optional

# optional MQTT support
try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

NUM_SENSORS = 10
SAMPLE_RATE = 10  # samples per second per sensor
INTERVAL = 1.0 / SAMPLE_RATE
MIN_INTERVAL = 0.5


class SensorModel:
    def __init__(self, seed: int):
        rnd = random.Random(seed)
        self.a_low = 1.0 * rnd.uniform(0.8, 1.2)
        self.a_med = 0.5 * rnd.uniform(0.8, 1.2)
        self.a_high = 0.1 * rnd.uniform(0.8, 1.2)
        self.dc = rnd.uniform(-0.5, 0.5)
        self.phi_low = rnd.uniform(0, 2 * math.pi)
        self.phi_med = rnd.uniform(0, 2 * math.pi)
        self.phi_high = rnd.uniform(0, 2 * math.pi)

    def sample(self, t: float) -> float:
        return (
            self.a_low * math.sin(2 * math.pi * 0.01 * t + self.phi_low)
            + self.a_med * math.sin(2 * math.pi * 0.1 * t + self.phi_med)
            + self.a_high * math.sin(2 * math.pi * 1.0 * t + self.phi_high)
            + self.dc
        )


async def _send_loop_to_server(host: str, port: int, duration: Optional[float]):
    sensors = [SensorModel(i + 1) for i in range(NUM_SENSORS)]
    backoff = 1.0
    start = time.time()
    while True:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            print(f"Connected to server {host}:{port}")
            while True:
                t = time.time()
                samples = [
                    {"sensor_id": i, "ts": int(t * 1000), "value": round(s.sample(t), 4)}
                    for i, s in enumerate(sensors)
                ]
                message = json.dumps({"type": "batch", "samples": samples}) + "\n"
                writer.write(message.encode())
                await writer.drain()
                if duration and (time.time() - start) >= duration:
                    writer.close()
                    await writer.wait_closed()
                    return
                await asyncio.sleep(INTERVAL)
        except Exception as e:
            print(f"Connection failed: {e}; retrying in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10)


async def _mqtt_broadcast_loop(mqtt_client, host: str, port: int, broadcast_interval: float, duration: Optional[float], maintenance_cfg: dict):
    sensors = [SensorModel(i + 1) for i in range(NUM_SENSORS)]
    start = time.time()
    config_event = maintenance_cfg.get('config_event')

    def current_interval() -> float:
        return max(MIN_INTERVAL, float(maintenance_cfg.get('broadcast_interval', broadcast_interval)))

    while True:
        t = time.time()
        samples = [
            {"sensor_id": i, "ts": int(t * 1000), "value": round(s.sample(t), 4)}
            for i, s in enumerate(sensors)
        ]
        message = json.dumps({"type": "broadcast", "samples": samples})
        try:
            mqtt_client.publish('sensors/broadcast', message)
        except Exception as e:
            print('MQTT publish error:', e)
        if duration and (time.time() - start) >= duration:
            return

        while True:
            interval = current_interval()
            if config_event is None:
                await asyncio.sleep(interval)
                break
            try:
                await asyncio.wait_for(config_event.wait(), timeout=interval)
                config_event.clear()
                continue
            except asyncio.TimeoutError:
                break


async def _mqtt_maintenance_loop(mqtt_client, maintenance_interval: float, duration: Optional[float], maintenance_cfg: dict):
    sensors = [SensorModel(i + 1) for i in range(NUM_SENSORS)]
    start = time.time()
    config_event = maintenance_cfg.get('config_event')

    def current_interval() -> float:
        return max(MIN_INTERVAL, float(maintenance_cfg.get('maintenance_interval', maintenance_interval)))

    while True:
        t = time.time()
        selected = maintenance_cfg.get('sensors', [])
        if selected:
            samples = [
                {"sensor_id": i, "ts": int(t * 1000), "value": round(sensors[i].sample(t), 4)}
                for i in selected if 0 <= i < len(sensors)
            ]
            message = json.dumps({"type": "maintenance", "samples": samples})
            try:
                mqtt_client.publish('sensors/maintenance', message)
            except Exception as e:
                print('MQTT publish error:', e)
        if duration and (time.time() - start) >= duration:
            return

        while True:
            interval = current_interval()
            if config_event is None:
                await asyncio.sleep(interval)
                break
            try:
                await asyncio.wait_for(config_event.wait(), timeout=interval)
                config_event.clear()
                continue
            except asyncio.TimeoutError:
                break


async def _print_loop(duration: Optional[float]):
    sensors = [SensorModel(i + 1) for i in range(NUM_SENSORS)]
    start = time.time()
    while True:
        t = time.time()
        samples = [
            {"sensor_id": i, "ts": int(t * 1000), "value": round(s.sample(t), 4)}
            for i, s in enumerate(sensors)
        ]
        message = json.dumps({"type": "batch", "samples": samples})
        print(message)
        if duration and (time.time() - start) >= duration:
            return
        await asyncio.sleep(INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="Sensor data generator")
    parser.add_argument("--server-host", type=str, default=None, help="TCP server to send data to")
    parser.add_argument("--server-port", type=int, default=9999, help="TCP server port")
    parser.add_argument("--duration", type=float, default=None, help="seconds to run (default: forever)")
    parser.add_argument("--mqtt-host", type=str, default=None, help="MQTT broker host to publish to (optional)")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--broadcast-interval", type=float, default=1.0, help="seconds between MQTT broadcast messages (default 1.0, min 0.5)")
    parser.add_argument("--maintenance-interval", type=float, default=0.5, help="seconds between maintenance MQTT messages (default 0.5, min 0.5)")
    parser.add_argument("--maintenance-sensors", type=str, default="", help="comma-separated sensor ids for maintenance mode (0-based)")
    args = parser.parse_args()

    # Prepare optional MQTT client
    mqtt_client = None
    maintenance_cfg = {
        'sensors': [],
        'broadcast_interval': max(MIN_INTERVAL, float(args.broadcast_interval)),
        'maintenance_interval': max(MIN_INTERVAL, float(args.maintenance_interval)),
    }
    if args.maintenance_sensors:
        try:
            maintenance_cfg['sensors'] = [int(x) for x in args.maintenance_sensors.split(',') if x.strip()!='']
        except Exception:
            maintenance_cfg['sensors'] = []

    async def _run_all():
        loop = asyncio.get_running_loop()
        config_event = asyncio.Event()
        maintenance_cfg['config_event'] = config_event
        tasks = []
        if args.server_host:
            tasks.append(asyncio.create_task(_send_loop_to_server(args.server_host, args.server_port, args.duration)))
        else:
            tasks.append(asyncio.create_task(_print_loop(args.duration)))

        # MQTT: connect and run publisher tasks if requested
        if args.mqtt_host and mqtt is not None:
            client = mqtt.Client(userdata={'loop': loop, 'config_event': config_event})
            def _on_config(_client, _userdata, msg):
                try:
                    data = json.loads(msg.payload.decode('utf-8'))
                except Exception:
                    return
                if 'maintenance_interval' in data:
                    try:
                        maintenance_cfg['maintenance_interval'] = max(MIN_INTERVAL, float(data['maintenance_interval']))
                    except Exception:
                        pass
                if 'broadcast_interval' in data:
                    try:
                        maintenance_cfg['broadcast_interval'] = max(MIN_INTERVAL, float(data['broadcast_interval']))
                    except Exception:
                        pass
                if 'maintenance_sensors' in data:
                    raw = data['maintenance_sensors']
                    parsed = []
                    if isinstance(raw, str):
                        parsed = [x.strip() for x in raw.split(',') if x.strip()]
                    elif isinstance(raw, list):
                        parsed = raw
                    try:
                        maintenance_cfg['sensors'] = [int(x) for x in parsed]
                    except Exception:
                        pass
                print(
                    'Applied config from MQTT:',
                    {
                        'broadcast_interval': maintenance_cfg['broadcast_interval'],
                        'maintenance_interval': maintenance_cfg['maintenance_interval'],
                        'maintenance_sensors': maintenance_cfg['sensors'],
                    },
                )
                loop.call_soon_threadsafe(config_event.set)

            client.on_message = _on_config
            try:
                client.connect(args.mqtt_host, args.mqtt_port, 60)
                client.subscribe('sensors/config')
                client.loop_start()
                tasks.append(asyncio.create_task(_mqtt_broadcast_loop(client, args.mqtt_host, args.mqtt_port, args.broadcast_interval, args.duration, maintenance_cfg)))
                tasks.append(asyncio.create_task(_mqtt_maintenance_loop(client, args.maintenance_interval, args.duration, maintenance_cfg)))
            except Exception as e:
                print('Could not start MQTT client:', e)

        if tasks:
            await asyncio.gather(*tasks)

    asyncio.run(_run_all())


if __name__ == "__main__":
    main()
