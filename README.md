# MQTT -> PostgreSQL -> WebSockets Demo

Minimal end-to-end demo:
- Gateway simulator publishes sensor data
- MQTT carries messages
- Ingest writes variable-length arrays into PostgreSQL
- Web UI shows live charts, MQTT topic snapshots, and DB snapshot rows
- Million-point persistence lab compares raw JSONB, normalized samples, and
  grouped PostgreSQL arrays using equivalent generated MQTT data

## Quickstart

### 1) Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- Python 3.10+
- Internet access the first time (to install Python packages into `.venv`)

### 2) Clone and enter the repo
```bash
git clone https://github.com/JohnAllanE/mqtt-postgres-demo.git
cd mqtt-postgres-demo
```

### 3) Start infrastructure (PostgreSQL + Mosquitto)
```bash
docker compose up -d
```

### 4) Start the demo stack
```bash
python3 start_everything.py
```

What this does:
- Starts the server bridge, gateway simulator, and static web server
- If no virtual environment is active, each launcher creates/uses `.venv`
- Installs `requirements.txt` into `.venv` automatically

So yes: a new user can run Docker first, then run `start_everything.py` without manual `pip install`.

### 5) Open the demo
- Web UI: http://localhost:8000
- API recent rows: http://localhost:8080/api/recent?limit=5

## Million-point persistence lab

Open the web UI and use **Million-point Persistence Lab** to generate 1,000,000
or more deterministic sensor readings. The load data is isolated from the live
`sensor_data` table and can be cleared independently.

The three representations are:

- `mqtt_test_raw`: one JSONB row per original 10-sensor MQTT message
- `mqtt_test_samples`: one relational row per sensor reading
- `mqtt_test_arrays`: two grouped array rows per MQTT message (6 + 4 sensors)

After seeding, **Run query comparison** executes an equivalent 10-minute
sensor aggregate for all three designs. The page reports:

- rows and rows per MQTT message
- total storage and bytes per equivalent sensor point
- per-variant seed time and points/second
- median query time for single-sensor history, rebuilding the latest MQTT
  message, and scanning every sensor in a ten-minute window
- the measured storage winner and fastest design for each query workload

Each query is warmed once, measured three times, and displayed using its median
wall-clock time. Counts from 10,000 through 20,000,000 points are accepted in
multiples of 10. Reseed once after upgrading to populate the new per-variant
ingestion metrics.

## Stop

- In the terminal running `start_everything.py`, press `Ctrl+C`

To stop containers:
```bash
docker compose down
```

To also remove Postgres data volume:
```bash
docker compose down -v
```
