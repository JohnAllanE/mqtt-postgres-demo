# MQTT + PostgreSQL Demo Specification

## 1. Purpose

This project demonstrates end-to-end telemetry flow for mixed equipment types:

1. Simulated gateway generates sensor signals.
2. Gateway publishes telemetry to MQTT broker.
3. Server ingests telemetry, validates by sensor type schema, and stores in PostgreSQL using variable-length arrays.
4. Web UI queries and visualizes stored data and sends runtime control commands back to gateway.

This document is the implementation specification for the code build.

## 2. Scope and non-goals

### In scope

1. Local single-machine demo.
2. MQTT broker, gateway simulator, server, and web UI.
3. PostgreSQL-backed storage (not in-memory cache as source of truth).
4. Global and monitor data rates.
5. Data retention policy with periodic cleanup.

### Out of scope

1. Production authentication/authorization.
2. TLS certificates and secure secret distribution.
3. Distributed deployment and horizontal scaling.

## 3. Technology decisions

These choices are fixed for the first implementation pass:

1. Python: 3.12
2. MQTT broker: Eclipse Mosquitto (local process or Docker)
3. MQTT client library: `paho-mqtt`
4. Server web framework: `FastAPI`
5. Server ASGI runtime: `uvicorn`
6. Web to server live updates: WebSocket endpoint from FastAPI
7. Database: PostgreSQL 16
8. PostgreSQL driver: `asyncpg`
9. Frontend: static HTML + vanilla JS + Chart.js
10. Gateway and server concurrency: `asyncio`

Rationale:

1. FastAPI gives clean REST + WebSocket support in one process.
2. WebSocket simplifies push updates for status and monitor streams.
3. `asyncpg` is efficient and maps well to array types.

## 4. Local runtime topology

All services run on localhost.

1. MQTT broker: `localhost:1883`
2. PostgreSQL: `localhost:5432`
3. Server API + UI host: `localhost:8000`
4. Gateway simulator: outbound MQTT client to broker

## 5. Repository target structure

Expected implementation layout:

```text
.
├── readme.md
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── gateway/
│   ├── main.py
│   ├── simulator.py
│   └── models.py
├── server/
│   ├── main.py
│   ├── config.py
│   ├── mqtt_client.py
│   ├── db.py
│   ├── retention.py
│   ├── api.py
│   ├── ws.py
│   └── schema.sql
└── web/
    ├── index.html
    ├── app.js
    └── styles.css
```

## 6. MQTT protocol specification

### 6.1 Topic naming

Use one gateway id and one server id for the demo.

1. Gateway id: `gw-001`
2. Server id: `srv-001`

Topics:

1. Telemetry (global): `demo/gateway/gw-001/telemetry/global`
2. Telemetry (monitor): `demo/gateway/gw-001/telemetry/monitor`
3. Gateway status replies: `demo/gateway/gw-001/status`
4. Commands server to gateway: `demo/gateway/gw-001/cmd`
5. Optional command ack gateway to server: `demo/gateway/gw-001/cmd_ack`
6. Server health heartbeat (optional): `demo/server/srv-001/health`

### 6.2 QoS, retain, payload format

1. Payload encoding: UTF-8 JSON object.
2. Telemetry QoS: 0.
3. Command QoS: 1.
4. Status QoS: 1.
5. Retain flag:
   1. Commands: false
   2. Telemetry: false
   3. Status snapshot replies: false

### 6.3 Command messages (server -> gateway)

All commands have envelope fields:

```json
{
  "msg_type": "command",
  "cmd_id": "uuid-v4",
  "ts": "2026-08-12T12:00:00Z",
  "command": "set_global_config",
  "payload": {}
}
```

Supported `command` values:

1. `set_global_config`
2. `set_monitor_config`
3. `set_retention_policy`
4. `set_thermostat_setpoint`
5. `request_status`
6. `reset_gateway_state`

#### set_global_config payload

```json
{
  "sensor_ids": ["ac-1", "env-1", "pump-1"],
  "freq_hz": 1.0,
  "batch_window_ms": 1000
}
```

Rules:

1. `freq_hz` range: 0.1 to 20.0
2. `batch_window_ms` range: 100 to 5000
3. Empty `sensor_ids` means all sensors

#### set_monitor_config payload

```json
{
  "enabled": true,
  "sensor_ids": ["ac-1"],
  "freq_hz": 10.0,
  "batch_window_ms": 500
}
```

Rules:

1. Monitor stream is diagnostic and not persisted.
2. When `enabled` is false, other fields may be ignored.

#### set_retention_policy payload

```json
{
  "max_age_seconds": 86400,
  "max_rows_per_sensor": 20000,
  "cleanup_interval_seconds": 60
}
```

#### set_thermostat_setpoint payload

```json
{
   "sensor_id": "ac-1",
   "setpoint_f": 70.0,
   "transition": {
      "time_constant_seconds": 90,
      "max_delta_per_minute": 4.0
   }
}
```

Rules:

1. `sensor_id` must refer to a thermostat-capable sensor (v1: `ac-1`).
2. `setpoint_f` range: 60.0 to 80.0.
3. `time_constant_seconds` range: 10 to 600.
4. `max_delta_per_minute` range: 0.5 to 10.0.
5. If `transition` is omitted, gateway defaults are used.

#### request_status payload

```json
{}
```

#### reset_gateway_state payload

```json
{
  "clear_monitor": true,
  "restore_defaults": true
}
```

### 6.4 Command ack messages (gateway -> server)

Published on `cmd_ack` topic when command QoS is 1:

```json
{
  "msg_type": "command_ack",
  "cmd_id": "uuid-v4",
  "ts": "2026-08-12T12:00:00Z",
  "ok": true,
  "error": null
}
```

### 6.5 Status messages (gateway -> server)

```json
{
  "msg_type": "status",
  "gateway_id": "gw-001",
  "ts": "2026-08-12T12:00:00Z",
  "broker_connected": true,
  "global_config": {
    "sensor_ids": ["ac-1", "env-1", "pump-1"],
    "freq_hz": 1.0,
    "batch_window_ms": 1000
  },
  "monitor_config": {
    "enabled": false,
    "sensor_ids": [],
    "freq_hz": 10.0,
    "batch_window_ms": 500
  },
   "thermostat": {
      "sensor_id": "ac-1",
      "setpoint_f": 72.0,
      "response": {
         "time_constant_seconds": 90,
         "max_delta_per_minute": 4.0
      }
   },
  "sensors": [
    {
      "sensor_id": "ac-1",
      "type_id": "ac_unit_v1",
      "online": true,
      "last_seen_ts": "2026-08-12T12:00:00Z"
    }
  ]
}
```

### 6.6 Telemetry messages (gateway -> server)

Telemetry is batch-first. One message may contain multiple samples.

```json
{
  "msg_type": "telemetry",
  "stream": "global",
  "gateway_id": "gw-001",
  "sent_ts": "2026-08-12T12:00:01Z",
  "samples": [
    {
      "sensor_id": "ac-1",
      "type_id": "ac_unit_v1",
      "sample_ts": "2026-08-12T12:00:00.500Z",
      "values": [72.4, 55.1, 180.2, 30.5],
      "seq": 12345
    }
  ]
}
```

Rules:

1. `stream` is either `global` or `monitor`.
2. Server persists only `stream=global`.
3. `values` length must exactly match schema for `type_id`.
4. `seq` increases per sensor and is used for missing-sample diagnostics.

## 7. Gateway simulator specification

### 7.1 Simulated sensors

Default sensors and signal models:

1. `ac-1` type `ac_unit_v1`
   1. condenser_temp_f: sine
   2. evaporator_temp_f: sine phase-shifted
   3. high_side_psi: sawtooth
   4. low_side_psi: triangle
2. `env-1` type `env_quality_v1`
   1. temp_f: sine
   2. humidity_pct: triangle
   3. air_quality_ppm: gaussian noise around baseline
3. `pump-1` type `pump_v1`
   1. rpm: square with noise
   2. vibration_mm_s: gaussian noise

Defaults:

1. Global frequency: 1.0 Hz
2. Monitor frequency: 10.0 Hz
3. Global batch window: 1000 ms
4. Monitor batch window: 500 ms
5. Thermostat setpoint for `ac-1`: 72.0 F
6. Thermostat response defaults:
   1. first-order lag time constant: 90 seconds
   2. max change clamp: 4.0 F per minute

### 7.2 Gateway state model

Gateway stores mutable runtime state:

1. MQTT connection state
2. Global config
3. Monitor config
4. Retention config for local gateway cache (optional local ring buffer)
5. Sensor registry and last sample metadata
6. Thermostat control state:
   1. current setpoint
   2. previous setpoint
   3. setpoint update timestamp
   4. response model parameters

### 7.3 Gateway behavior rules

1. On startup, connect MQTT, then publish one status message.
2. On `request_status`, publish status within 500 ms.
3. If command parse fails, publish negative `cmd_ack` with error reason.
4. If monitor is enabled, publish monitor telemetry independently from global stream.
5. On `set_thermostat_setpoint`, update control target and publish `cmd_ack`.
6. AC-related channels must respond gradually to setpoint changes, not via instant jumps.

Thermostat response model for simulation:

1. Use first-order lag per simulation tick.
2. Suggested discrete update for each controlled channel:
   1. `delta_target = target_value - current_value`
   2. `raw_step = delta_target * (dt / time_constant_seconds)`
   3. clamp absolute step to `max_delta_per_minute * dt / 60`
   4. `new_value = current_value + clamped_step`
3. Add small post-update noise to avoid unrealistically smooth traces.

## 8. PostgreSQL schema specification

### 8.1 Database name and connection

1. Database: `mqtt_demo`
2. User: `postgres`
3. Password: `postgres`
4. Host: `localhost`
5. Port: `5432`

### 8.2 DDL

```sql
create extension if not exists pgcrypto;

create table if not exists sensor_type_schema (
  type_id text primary key,
  display_name text not null,
  field_names text[] not null,
  field_units text[] not null,
  value_count integer not null check (value_count > 0),
  created_at timestamptz not null default now(),
  check (array_length(field_names, 1) = value_count),
  check (array_length(field_units, 1) = value_count)
);

create table if not exists sensor_registry (
  sensor_id text primary key,
  type_id text not null references sensor_type_schema(type_id),
  display_name text not null,
  location text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists sensor_readings (
  id uuid primary key default gen_random_uuid(),
  sensor_id text not null references sensor_registry(sensor_id),
  type_id text not null references sensor_type_schema(type_id),
  sample_ts timestamptz not null,
  received_ts timestamptz not null default now(),
  values double precision[] not null,
  seq bigint,
  check (array_length(values, 1) > 0)
);

create unique index if not exists ux_sensor_readings_sensor_seq
  on sensor_readings(sensor_id, seq)
  where seq is not null;

create index if not exists ix_sensor_readings_sensor_time
  on sensor_readings(sensor_id, sample_ts desc);

create index if not exists ix_sensor_readings_time
  on sensor_readings(sample_ts desc);
```

### 8.3 Insert validation rules

Before insert into `sensor_readings`, server validates:

1. `sensor_id` exists in `sensor_registry`.
2. `type_id` matches registry mapping for `sensor_id`.
3. `array_length(values, 1)` equals `value_count` for `type_id`.

Invalid samples are dropped and counted in server metrics.

### 8.4 Retention cleanup

Run every `cleanup_interval_seconds`:

1. Delete rows older than `max_age_seconds`.
2. Enforce `max_rows_per_sensor` by deleting oldest overflow rows.

Order of operations:

1. Age-based delete.
2. Per-sensor row cap delete.

## 9. Server specification (Python service)

Single FastAPI application with these responsibilities:

1. MQTT ingestion and command publishing.
2. PostgreSQL write/read.
3. REST API for UI controls and historical query.
4. WebSocket for live updates to UI.
5. Static file hosting for the web page.

### 9.1 Process model

Within one server process:

1. FastAPI app event loop.
2. Background task for MQTT client.
3. Background task for retention cleanup.
4. In-memory connection status cache and last-known gateway status.

### 9.2 Web to database communication model

Decision:

1. UI does not query database directly.
2. UI calls server REST endpoints.
3. Server endpoint handlers run SQL queries via `asyncpg` and return JSON.
4. UI opens one WebSocket to server for push events.

Protocol split:

1. REST for request/response operations, history queries, and command submission.
2. WebSocket for asynchronous updates:
   1. broker/gateway connection changes
   2. status refresh results
   3. monitor stream samples
   4. command acknowledgements

## 10. REST API contract

Base path: `/api/v1`

### 10.1 Health and status

1. `GET /health`
   1. Returns server, db, mqtt connectivity summary.
2. `GET /status`
   1. Returns last gateway status snapshot and server stats.

### 10.2 Sensor metadata

1. `GET /sensors`
   1. Returns sensor registry with type schema metadata.
2. `POST /sensors/refresh-status`
   1. Sends `request_status` command to gateway.
   2. Returns accepted response with `cmd_id`.

### 10.3 Command endpoints

1. `POST /gateway/config/global`
   1. Body: `sensor_ids`, `freq_hz`, `batch_window_ms`
2. `POST /gateway/config/monitor`
   1. Body: `enabled`, `sensor_ids`, `freq_hz`, `batch_window_ms`
3. `POST /gateway/config/retention`
   1. Body: `max_age_seconds`, `max_rows_per_sensor`, `cleanup_interval_seconds`
4. `POST /gateway/config/thermostat-setpoint`
   1. Body: `sensor_id`, `setpoint_f`, optional `transition`
5. `POST /gateway/reset`
   1. Body: `clear_monitor`, `restore_defaults`

All command endpoints:

1. Validate payload.
2. Publish command over MQTT.
3. Return `202 Accepted` with `cmd_id`.

### 10.4 Data query endpoints

1. `GET /readings`
   1. Query params:
      1. `sensor_id` required
      2. `from_ts` optional ISO8601
      3. `to_ts` optional ISO8601
      4. `limit` default 500, max 5000
   2. Returns historical rows from PostgreSQL.
2. `POST /admin/reset-database`
   1. Truncates readings table and resets demo seed data.

## 11. WebSocket contract

Endpoint: `/ws`

Server-to-client event envelope:

```json
{
  "event": "status_update",
  "ts": "2026-08-12T12:00:00Z",
  "data": {}
}
```

Event types:

1. `status_update`
2. `monitor_samples`
3. `command_ack`
4. `connection_update`
5. `error`

Client-to-server WebSocket messages are not required for v1.

## 12. Web UI specification

Single-page interface sections:

1. Connection panel
   1. MQTT broker connected/disconnected
   2. Gateway online/offline
   3. Last update timestamp
2. Sensor list panel
   1. Sensor id, type, online state
   2. Buttons:
      1. `Clear Status` (local UI clear)
      2. `Query Status` (calls `/sensors/refresh-status`)
3. Historical graph panel
   1. Checkbox list of sensors and fields
   2. Time window picker
   3. Chart.js line graph using `/readings` results
4. Monitor panel
   1. Sensor multiselect
   2. Frequency input
   3. Enable/disable toggle
   4. Live values table fed by WebSocket `monitor_samples`
5. Thermostat control panel
   1. Thermostat sensor selector (v1 default `ac-1`)
   2. Setpoint numeric input and slider (60 to 80 F, step 0.5)
   3. `Set` button posts to `/gateway/config/thermostat-setpoint`
   4. Optional advanced controls for transition parameters
   5. Last acknowledged setpoint + timestamp display
6. Admin panel
   1. `Reset Demo` button calls `/admin/reset-database` and gateway reset command

## 13. Seed schema and sensors

Seed `sensor_type_schema` rows:

1. `ac_unit_v1`
   1. field_names: `['condenser_temp_f','evaporator_temp_f','high_side_psi','low_side_psi']`
   2. field_units: `['F','F','psi','psi']`
   3. value_count: `4`
2. `env_quality_v1`
   1. field_names: `['temp_f','humidity_pct','air_quality_ppm']`
   2. field_units: `['F','pct','ppm']`
   3. value_count: `3`
3. `pump_v1`
   1. field_names: `['rpm','vibration_mm_s']`
   2. field_units: `['rpm','mm/s']`
   3. value_count: `2`

Seed `sensor_registry` rows:

1. `ac-1` -> `ac_unit_v1`
2. `env-1` -> `env_quality_v1`
3. `pump-1` -> `pump_v1`

Thermostat capability:

1. In v1, only `ac-1` accepts `set_thermostat_setpoint`.
2. Non-capable sensors return negative command ack with an error message.

## 14. Configuration variables

Use `.env` file with defaults:

```env
APP_ENV=dev
LOG_LEVEL=INFO

MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID_SERVER=srv-001
MQTT_CLIENT_ID_GATEWAY=gw-001
MQTT_TOPIC_PREFIX=demo

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mqtt_demo
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

GLOBAL_DEFAULT_FREQ_HZ=1.0
MONITOR_DEFAULT_FREQ_HZ=10.0
GLOBAL_DEFAULT_BATCH_MS=1000
MONITOR_DEFAULT_BATCH_MS=500

THERMOSTAT_DEFAULT_SETPOINT_F=72.0
THERMOSTAT_MIN_SETPOINT_F=60.0
THERMOSTAT_MAX_SETPOINT_F=80.0
THERMOSTAT_RESPONSE_TIME_CONSTANT_SECONDS=90
THERMOSTAT_MAX_DELTA_PER_MINUTE=4.0

RETENTION_MAX_AGE_SECONDS=86400
RETENTION_MAX_ROWS_PER_SENSOR=20000
RETENTION_CLEANUP_INTERVAL_SECONDS=60
```

## 15. Error handling and observability

### 15.1 Error handling

1. Invalid MQTT payloads:
   1. Log warning
   2. Increment counter
   3. Continue loop
2. DB insert failure for a sample:
   1. Log error with sensor and ts
   2. Continue with other samples in batch
3. MQTT disconnect:
   1. Auto reconnect with exponential backoff
   2. Emit `connection_update` over WebSocket

### 15.2 Metrics to expose in `/health` and `/status`

1. total_samples_received
2. total_samples_persisted
3. total_samples_rejected
4. mqtt_connected
5. db_connected
6. last_sample_ts_by_sensor

## 16. Performance targets for demo

1. Support at least 20 sensors at 1 Hz global and 3 sensors at 10 Hz monitor.
2. End-to-end ingest latency target (gateway publish to DB insert): p95 under 300 ms on local machine.
3. WebSocket monitor update interval under 1 second for active monitor stream.

## 17. Security posture for local demo

1. No auth required by default.
2. CORS allow localhost origins only.
3. Input validation required on all REST endpoints.

## 18. Local run plan

### 18.0 Quick Start (recommended)

Use these commands to start infrastructure, server, gateway, and open the web GUI.

```bash
cd "/Users/jare/Documents/AMP projects/Noah/mqtt-postgres-demo"
docker context use default
docker compose up -d

.venv/bin/python -m server.main
```

In a second terminal:

```bash
cd "/Users/jare/Documents/AMP projects/Noah/mqtt-postgres-demo"
.venv/bin/python -m gateway.main
```

Open the GUI:

1. `http://localhost:8000`

Quick checks:

```bash
curl -sS http://localhost:8000/api/v1/health
curl -sS "http://localhost:8000/api/v1/readings?sensor_id=ac-1&limit=5"
```

Stop everything:

```bash
docker compose down
```

### 18.1 Start dependencies

Use Docker compose for broker and PostgreSQL:

```bash
docker compose up -d
```

### 18.2 Create Python environment and install deps

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 18.3 Run services

Terminal 1:

```bash
python -m server.main
```

Terminal 2:

```bash
python -m gateway.main
```

Open UI:

1. `http://localhost:8000`

## 19. Test scenarios and acceptance criteria

### Scenario A: baseline ingest

1. Start stack.
2. Confirm `/health` reports mqtt and db connected.
3. Observe readings appear for all seeded sensors at about 1 Hz.

Pass criteria:

1. Database row count increases continuously.
2. UI chart can query and plot stored history.

### Scenario B: monitor stream

1. Enable monitor for `ac-1` at 10 Hz.
2. Verify live monitor values update quickly in UI.
3. Verify monitor samples are not inserted into historical DB table.

Pass criteria:

1. WebSocket emits `monitor_samples` events.
2. DB growth rate remains tied to global stream only.

### Scenario C: retention cleanup

1. Set retention to very low `max_age_seconds` (for example 60).
2. Wait for cleanup cycle.

Pass criteria:

1. Old rows are removed.
2. New rows continue to ingest without interruption.

### Scenario D: status and command flow

1. Trigger `Query Status`.
2. Change global config and monitor config.

Pass criteria:

1. Gateway status reflects updates.
2. Command acknowledgements are visible in UI.

### Scenario E: thermostat setpoint control and gradual response

1. Set thermostat setpoint from 72.0 F to 68.0 F using slider/input and `Set` button.
2. Verify endpoint returns `202 Accepted` and `cmd_id`.
3. Verify gateway publishes positive `cmd_ack`.
4. Observe AC temperature channels trend gradually toward new equilibrium.

Pass criteria:

1. Status payload thermostat block reflects new setpoint.
2. Temperature transitions are smooth and bounded by configured rate limit.
3. No schema or insert validation errors occur after setpoint changes.

## 20. Implementation checklist

1. Add Docker compose for Mosquitto + PostgreSQL.
2. Implement DB schema init and seed.
3. Implement gateway simulator and command handling.
4. Implement server MQTT ingest and validation.
5. Implement REST API and WebSocket events.
6. Implement web UI panels and chart.
7. Implement thermostat setpoint command path and response model.
8. Implement retention cleaner.
9. Run scenarios A-E and verify criteria.

## 21. Vertical-slice incremental implementation plan

Use this plan to track build progress phase by phase.

### Phase 1: Foundation and bootstrapping

Status: [ ] Not started [ ] In progress [x] Complete

Tasks:

1. [x] Create project structure and base files (`requirements.txt`, `.env.example`, `docker-compose.yml`).
2. [x] Add PostgreSQL schema initialization and seed routines.
3. [x] Add FastAPI app skeleton and `GET /api/v1/health`.
4. [x] Add gateway skeleton with MQTT connect and initial status publish.
5. [x] Verify local startup for broker, database, server, and gateway.

Exit criteria:

1. [x] All services start without manual code edits.
2. [x] Health endpoint reports database and MQTT dependency states.

### Phase 2: Vertical slice v0 (single telemetry path)

Status: [ ] Not started [ ] In progress [x] Complete

Tasks:

1. [x] Implement one global telemetry publish path from gateway to broker.
2. [x] Implement server MQTT ingest and database insert for global samples.
3. [x] Implement `GET /api/v1/readings` for one sensor.
4. [x] Add minimal web page with one chart querying historical readings.

Exit criteria:

1. [x] Reading rows grow in PostgreSQL from simulated gateway data.
2. [x] Chart shows stored data retrieved through server API.

### Phase 3: Full command and status contracts

Status: [ ] Not started [ ] In progress [x] Complete

Tasks:

1. [x] Implement command handlers for global config, monitor config, retention, status request, and reset.
2. [x] Implement command acknowledgement flow (`cmd_ack`).
3. [x] Implement status snapshot publication and server cache updates.
4. [x] Implement WebSocket endpoint and events (`status_update`, `monitor_samples`, `command_ack`, `connection_update`).

Exit criteria:

1. [x] UI can send commands and receive async acknowledgement updates.
2. [x] Status panel reflects gateway changes from command activity.

### Phase 4: Thermostat setpoint end-to-end

Status: [ ] Not started [ ] In progress [ ] Complete

Tasks:

1. [ ] Add `POST /api/v1/gateway/config/thermostat-setpoint`.
2. [ ] Add gateway `set_thermostat_setpoint` command handling.
3. [ ] Implement gradual thermostat response model (first-order lag + rate clamp + noise).
4. [ ] Add UI thermostat control panel (numeric input or slider + Set button).
5. [ ] Show last acknowledged setpoint and timestamp in UI.

Exit criteria:

1. [ ] Setpoint commands are acknowledged and visible in UI.
2. [ ] AC channels move gradually toward new setpoint (no abrupt step changes).

### Phase 5: Retention, reset, and acceptance

Status: [ ] Not started [ ] In progress [ ] Complete

Tasks:

1. [ ] Implement retention cleanup worker (age-based + per-sensor cap).
2. [ ] Implement admin reset flow (`/admin/reset-database`) and reseed path.
3. [ ] Execute and document Scenario A through Scenario E results.

Exit criteria:

1. [ ] All acceptance scenarios pass.
2. [ ] Demo can be restarted and reproduced from documented run commands.

### Progress log

Record concise updates as work proceeds.

1. Date:
   1. Completed:
   2. Notes:
   3. Blockers:
2. Date: 2026-08-12
   1. Completed: Phase 1 scaffolding files, server health endpoint, gateway MQTT status publisher, DB schema and seed routines.
   2. Notes: Python modules compile cleanly with `py_compile`.
   3. Blockers: `docker` command is unavailable in this environment, so broker/database startup verification remains pending.
3. Date: 2026-08-12
   1. Completed: Docker context fix, runtime startup verification, Phase 2 telemetry publisher/ingestor, `/api/v1/readings`, and minimal chart UI.
   2. Notes: `curl /api/v1/health` reports both dependencies true, and `curl /api/v1/readings?sensor_id=ac-1` returns persisted rows.
   3. Blockers: None for Phase 1 and Phase 2.
4. Date: 2026-08-12
   1. Completed: Phase 3 command endpoints, gateway command handling, status/ack topic flow, websocket events, and UI controls.
   2. Notes: Verified `GET /api/v1/status`, command POST endpoints, and websocket connection event using a Python `websockets` client.
   3. Blockers: None for Phase 3.

## 22. Future extension points

1. Add authentication and role-based controls.
2. Add TLS MQTT transport.
3. Move from array-only storage to hybrid array + JSONB metadata.
4. Add downsampling and aggregation endpoints.
