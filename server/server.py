#!/usr/bin/env python3
"""Server-side bridge: accepts simulator TCP input and forwards to WebSocket clients.

This runs on the web/server machine and bridges remote simulators (gateways)
to browser clients by forwarding JSON batches received over TCP to WebSocket
clients.
"""
import asyncio
import json
from typing import Set

import websockets

WS_PORT = 8765
TCP_PORT = 9999

ws_clients: Set[websockets.WebSocketServerProtocol] = set()


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

    async with ws_server, tcp_server:
        await asyncio.Future()  # run forever


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down")
