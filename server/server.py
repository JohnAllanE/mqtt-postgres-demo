#!/usr/bin/env python3
"""Server-side bridge: accepts simulator TCP input and forwards to WebSocket clients.

This runs on the web/server machine and bridges remote simulators (gateways)
to browser clients by forwarding JSON batches received over TCP to WebSocket
clients.
"""
import asyncio
import json
import os
from typing import Set

import websockets

WS_PORT = int(os.environ.get('WS_PORT', 8765))
TCP_PORT = int(os.environ.get('TCP_PORT', 9999))

ws_clients: Set[websockets.WebSocketServerProtocol] = set()

# Optional MQTT bridge: if paho-mqtt is available, subscribe to maintenance and
# broadcast topics and forward payloads to websocket clients.
try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
_mqtt_client = None
_mqtt_loop = None


async def ws_handler(ws, path=None):
    ws_clients.add(ws)
    try:
        await ws.wait_closed()
    finally:
        ws_clients.discard(ws)


async def _safe_send(ws, message):
    try:
        await ws.send(message)
    except Exception:
        ws_clients.discard(ws)


async def broadcast(message: str):
    if not ws_clients:
        return
    await asyncio.gather(*(_safe_send(ws, message) for ws in list(ws_clients)), return_exceptions=True)


def _mqtt_on_message(client, userdata, msg):
    payload = None
    try:
        payload = msg.payload.decode('utf-8')
    except Exception:
        return
    loop = userdata.get('loop') if isinstance(userdata, dict) else None
    if loop is None:
        return
    try:
        parsed = json.loads(payload) if payload else payload
    except Exception:
        parsed = payload
    wrapped = json.dumps({'topic': msg.topic, 'payload': parsed})
    # schedule broadcast on the asyncio loop
    try:
        asyncio.run_coroutine_threadsafe(broadcast(wrapped), loop)
    except Exception:
        pass


def start_mqtt_bridge(loop):
    global _mqtt_client
    if mqtt is None:
        print('paho-mqtt not installed; skipping MQTT bridge')
        return
    try:
        client = mqtt.Client(userdata={'loop': loop})
        client.on_message = _mqtt_on_message
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.subscribe('sensors/maintenance')
        client.subscribe('sensors/broadcast')
        client.subscribe('sensors/config')
        client.loop_start()
        _mqtt_client = client
        print(f'MQTT bridge connected to {MQTT_HOST}:{MQTT_PORT} and forwarding topics to websockets')
    except Exception as e:
        print('Failed to start MQTT bridge:', e)


async def handle_simulator(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info('peername')
    print(f"Simulator connected: {peer}")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                # validate JSON
                msg = json.loads(line.decode())
            except Exception as e:
                print(f"Invalid JSON from simulator {peer}: {e}")
                continue
            # forward raw text to websocket clients
            await broadcast(json.dumps(msg))
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"Simulator disconnected: {peer}")


async def main():
    ws_server = await websockets.serve(ws_handler, '0.0.0.0', WS_PORT)
    tcp_server = await asyncio.start_server(handle_simulator, '0.0.0.0', TCP_PORT)

    print(f"WebSocket server listening on ws://localhost:{WS_PORT}")
    print(f"TCP server for simulators listening on 0.0.0.0:{TCP_PORT}")

    # start optional MQTT bridge that forwards maintenance/broadcast topics
    loop = asyncio.get_running_loop()
    try:
        start_mqtt_bridge(loop)
    except Exception:
        pass

    async with ws_server, tcp_server:
        await asyncio.Future()  # run forever


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down")
