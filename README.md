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
	- Publish JSON messages to MQTT topic `sensors/raw` (include sensor id, timestamp, and values).

- [ ] Ingest service (`server/`)
	- MQTT client that subscribes to `sensors/raw` and writes normalized rows to PostgreSQL.
	- Provide a minimal `schema.sql` for the table(s) used in Phase 1.

- [ ] Web UI (`web/`)
	- Basic `index.html` + `app.js` showing a grid of small Chart.js plots (5 columns × 2 rows) with raw data streamed over WebSockets.
	- The web app should connect to a lightweight WS endpoint that forwards recent samples for each sensor.

- [ ] Project automation & docs
	- Provide a `requirements.txt` with the Python deps needed for Phase 1.
	- Add a `.env.example` with configurable MQTT broker URL and Postgres connection string.
	- Add a `.gitignore` (this repo) to exclude venvs, editor folders, OS junk, and other local artifacts.

Acceptance criteria (Phase 1)

- A developer can create a Python virtualenv, install `requirements.txt`, start the sensor simulator and ingest service, open `web/index.html`, and see live updating charts.
- The repository contains `schema.sql`, `requirements.txt`, and a small README section with quick run steps.

Quick run (local, Phase 1)

1. Create and activate a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start a local MQTT broker (or point to one via `MQTT_URL`), start the ingest service, then run the sensor simulator.

3. Open `web/index.html` in your browser (or run a small static server) and confirm charts update.

---

Keep phase tasks small and testable. Reply which Phase 1 item you'd like me to scaffold next and I'll implement it.