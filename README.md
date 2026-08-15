# MQTT → PostgreSQL → Websockets Demo

This repository demonstrates a minimal end-to-end data flow: simulated IoT sensors publishing to MQTT, ingestion into PostgreSQL, and live visualization in a browser via WebSockets.

Development is organized into phases. Work only on items in the active phase.

Backup: the previous project state is preserved on branch `backup-main-20260815-1038`.

## Phase 1 — Minimum Viable Demo (High priority)

Goal: produce a small, runnable demo that shows sensor data flowing from a simulator into storage and to a simple web UI.

Checklist (Phase 1)

- [ ] Sensor simulator (`gateway/`)
	- Implement a Python script that simulates 10 sensors at 10 samples/second.
	- Each sample should include three seeded sinusoidal components (low ≈0.01Hz, med ≈0.1Hz, high ≈1Hz) plus a DC offset.

- [ ] Web UI (`web/`)
	- Basic `index.html` + `app.js` showing a grid of small Chart.js plots (5 columns × 2 rows) with raw data streamed over WebSockets.
	- The web app should connect to a lightweight WS endpoint that forwards recent samples for each sensor.

## Quick Start (Minimal)

Run these commands in two terminals to start the Phase 1 demo:

```bash
# 1) create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) start the sensor simulator (terminal A)
python3 gateway/simulator.py

# 3) serve the web UI (terminal B)
python3 -m http.server --directory web 8000
```

Open http://localhost:8000 in your browser to view the live charts. Use Ctrl-C to stop the simulator and the static server.
