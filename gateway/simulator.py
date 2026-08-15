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

NUM_SENSORS = 10
SAMPLE_RATE = 10  # samples per second per sensor
INTERVAL = 1.0 / SAMPLE_RATE


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
                    {"sensor_id": i, "ts": int(t * 1000), "value": s.sample(t)}
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


async def _print_loop(duration: Optional[float]):
    sensors = [SensorModel(i + 1) for i in range(NUM_SENSORS)]
    start = time.time()
    while True:
        t = time.time()
        samples = [
            {"sensor_id": i, "ts": int(t * 1000), "value": s.sample(t)}
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
    args = parser.parse_args()

    if args.server_host:
        asyncio.run(_send_loop_to_server(args.server_host, args.server_port, args.duration))
    else:
        asyncio.run(_print_loop(args.duration))


if __name__ == "__main__":
    main()
