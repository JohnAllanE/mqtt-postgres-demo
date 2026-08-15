# MQTT → PostgreSQL → Websockets Demo

This repository demonstrates a minimal end-to-end data flow: simulated IoT sensors publishing to MQTT, ingestion into PostgreSQL, and live visualization in a browser via WebSockets.

Development is organized into phases. Work only on items in the active phase.

Backup: the previous project is preserved on branch `backup-main-20260815-1038`.

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

Recommended (easier): use the top-level helper scripts which auto-create/use the virtualenv and install requirements when needed.

```bash
# start the gateway simulator (auto venv)
python3 start_gateway.py

# start the web server (auto venv, default port 8000)
python3 start_web.py

# or specify a port for the web server
python3 start_web.py 8080
```

Both scripts forward extra args to the underlying commands if needed. They share the repository `.venv` and `requirements.txt` (see notes below about environments).

## Development tips

- Run the gateway simulator for a limited time (useful for tests):

```bash
# the `--` separates args for the helper script from args forwarded to the simulator
python3 start_gateway.py -- --duration 10
```

- The web helper accepts a port argument: `python3 start_web.py 8080`.

- To force reinstallation inside the venv (not implemented yet), we can add a `--reinstall` flag to the helpers — tell me if you want that.

## Phase 1 — Minimum Viable Demo (High priority)

Goal: produce a small, runnable demo that shows sensor data flowing from a simulator into storage and to a simple web UI.

Checklist (Phase 1)

- [x] Sensor simulator (`gateway/`)
	- Implement a Python script that simulates 10 sensors at 10 samples/second.
	- Each sample should include three seeded sinusoidal components (low ≈0.01Hz, med ≈0.1Hz, high ≈1Hz) plus a DC offset.

- [x] Web UI (`web/`)
	- Basic `index.html` + `app.js` showing a grid of small Chart.js plots (5 columns × 2 rows) with raw data streamed over WebSockets.
	- The web app should connect to a lightweight WS endpoint that forwards recent samples for each sensor.

## Phase 2 - MQTT transport and PostgreSQL

- Label the existing chart section of the web interface "example raw sensors (no MQTT)"
- Create a second section to the web interface "logged sensor values" containing:
  - Numeric input field for polling period (seconds), default 1 second
  - Reset-database button to reset all fields
  - Two Selectors for sensors to target with maintenance-mode 
- Create a third section on the web interface with a "maintenance mode" chart
  
- Create MQTT broker (Docker mosquitto) and PostgreSQL database (on Docker)
  - PostgreSQL should contain a schema table for two equimpent types (one having a grouping of 6 sensors, another with a grouping of 4 sensors)
  - PostgreSQL should also contain a data table, using arrays so that one row can have 6 values, and the next can have 4 values, and the schema table helps pack and unpack the row contents
  - MQTT structure is three topics:
    - Broadcast of all 10 sensor values with idx, timestamp, and value, in single message, at the polling interval (default 1 second).
      - These values are saved to PostgreSQL data table, and displayed to web from that table

    Quickstart (Phase 2)

    Run the broker and database with Docker Compose from the repository root:

    ```bash
    docker-compose up -d
    ```

    Start the ingestion service which subscribes to `sensors/broadcast` and writes to Postgres:

    ```bash
    # installs into .venv if needed
    python3 start_server.py  # ensures .venv exists
    python3 server/ingest.py
    ```

    Publish messages from the simulator to the broker (example):

    ```bash
    # simulator can publish to MQTT if you forward messages; alternatively, run a small publisher
    python3 gateway/simulator.py --server-host localhost --server-port 9999
    ```

    - Higher-frequency (default 2Hz) "maintenance mode" showing data coming from selected sensors, and displayed to web without going to the SQL database
    - Configuration message indicating message frequencies, and sensors to target with maintenance-mode
