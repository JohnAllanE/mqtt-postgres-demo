-- Schema for Phase 2: equipment types and sensor data

CREATE TABLE IF NOT EXISTS equipment_type (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  sensor_count INT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensor_data (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  equipment_type INT REFERENCES equipment_type(id),
  values DOUBLE PRECISION[] NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sensor_data_ts ON sensor_data (ts DESC);
