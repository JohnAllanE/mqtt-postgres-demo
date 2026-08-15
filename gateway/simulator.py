#!/usr/bin/env python3
"""Minimal sensor simulator that broadcasts batches of samples over WebSockets.

Run: python3 gateway/simulator.py
"""
import asyncio
import json
import math
import random
import time
from typing import Set, Optional
import argparse

import websockets

NUM_SENSORS = 10
SAMPLE_RATE = 10  # samples per second per sensor
INTERVAL = 1.0 / SAMPLE_RATE


class SensorModel:
    def __init__(self, seed: int):
        rnd = random.Random(seed)
        # amplitudes
        self.a_low = 1.0 * rnd.uniform(0.8, 1.2)
        self.a_med = 0.5 * rnd.uniform(0.8, 1.2)
        self.a_high = 0.1 * rnd.uniform(0.8, 1.2)
        self.dc = rnd.uniform(-0.5, 0.5)
        # random phases
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


clients: Set[websockets.WebSocketServerProtocol] = set()


async def handler(ws, path=None):
    # websockets library changed handler signature in newer versions —
    # accept either (ws, path) or just (ws,) and ignore the path when present.
    clients.add(ws)
    try:
        await ws.wait_closed()
    finally:
        clients.discard(ws)


async def broadcaster():
    sensors = [SensorModel(seed=i + 1) for i in range(NUM_SENSORS)]
    while True:
        t = time.time()
        samples = []
        for i, s in enumerate(sensors):
            samples.append({
                "sensor_id": i,
                "ts": int(t * 1000),
                "value": s.sample(t),
            })

        message = json.dumps({"type": "batch", "samples": samples})

        if clients:
            await asyncio.wait([c.send(message) for c in clients])

        await asyncio.sleep(INTERVAL)


async def _run_server(port: int, duration: Optional[float] = None):
    server = await websockets.serve(handler, "0.0.0.0", port)
    # run broadcaster as a background task so we can optionally stop after `duration`
    task = asyncio.create_task(broadcaster())
    try:
        if duration is None:
            await task
        else:
            await asyncio.sleep(duration)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        server.close()
        await server.wait_closed()


def main():
    parser = argparse.ArgumentParser(description="Sensor simulator websocket server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--duration", type=float, default=None, help="number of seconds to run (default: run forever)")
    args = parser.parse_args()
    port = args.port
    duration = args.duration
    print(f"Sensor simulator websocket server listening on ws://localhost:{port}")
    try:
        asyncio.run(_run_server(port, duration))
    except KeyboardInterrupt:
        print("Shutting down")


if __name__ == "__main__":
    main()
