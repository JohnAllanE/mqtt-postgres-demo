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

-- Isolated load-test tables. Each table represents the same MQTT sensor data
-- using a different persistence strategy so their row counts, storage, and
-- query cost can be compared without polluting the live sensor_data table.
CREATE TABLE IF NOT EXISTS mqtt_test_raw (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  topic TEXT NOT NULL,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS mqtt_test_samples (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  sensor_id SMALLINT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  topic TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mqtt_test_arrays (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  equipment_group SMALLINT NOT NULL,
  values DOUBLE PRECISION[] NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mqtt_test_raw_ts
  ON mqtt_test_raw USING BRIN (ts);
CREATE INDEX IF NOT EXISTS idx_mqtt_test_raw_ts_desc
  ON mqtt_test_raw (ts DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_test_samples_sensor_ts
  ON mqtt_test_samples (sensor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_test_samples_ts
  ON mqtt_test_samples (ts DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_test_arrays_group_ts
  ON mqtt_test_arrays (equipment_group, ts DESC);

CREATE TABLE IF NOT EXISTS mqtt_test_meta (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
  sample_count BIGINT NOT NULL,
  message_count BIGINT NOT NULL,
  seeded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  seed_seconds DOUBLE PRECISION NOT NULL,
  variant_seed_seconds JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE mqtt_test_meta
  ADD COLUMN IF NOT EXISTS variant_seed_seconds JSONB NOT NULL DEFAULT '{}'::jsonb;
