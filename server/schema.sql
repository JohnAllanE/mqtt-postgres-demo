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
