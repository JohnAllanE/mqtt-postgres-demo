# MQTT -> PostgreSQL -> WebSockets Demo

Minimal end-to-end demo:
- Gateway simulator publishes sensor data
- MQTT carries messages
- Ingest writes variable-length arrays into PostgreSQL
- Web UI shows live charts, MQTT topic snapshots, and DB snapshot rows

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