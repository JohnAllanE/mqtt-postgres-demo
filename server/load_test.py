"""Generate and benchmark equivalent high-volume MQTT persistence variants."""
from __future__ import annotations

import time
import json
import statistics
from datetime import datetime, timedelta, timezone


SENSORS_PER_MESSAGE = 10
MIN_SAMPLE_COUNT = 10_000
MAX_SAMPLE_COUNT = 20_000_000
BENCHMARK_REPEATS = 3

VARIANTS = (
    ("raw", "mqtt_test_raw", "Raw MQTT JSONB"),
    ("samples", "mqtt_test_samples", "Normalized samples"),
    ("arrays", "mqtt_test_arrays", "Grouped arrays"),
)


def validate_sample_count(value) -> int:
    """Return a bounded sample count aligned to complete MQTT messages."""
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sample_count must be an integer") from exc
    if count < MIN_SAMPLE_COUNT or count > MAX_SAMPLE_COUNT:
        raise ValueError(
            f"sample_count must be between {MIN_SAMPLE_COUNT:,} and {MAX_SAMPLE_COUNT:,}"
        )
    if count % SENSORS_PER_MESSAGE:
        raise ValueError("sample_count must be a multiple of 10")
    return count


def seed_variants(conn, sample_count: int, progress=None) -> dict:
    """Replace all load-test data with deterministic, set-generated rows."""
    sample_count = validate_sample_count(sample_count)
    message_count = sample_count // SENSORS_PER_MESSAGE
    # End at "now" so time-window queries see a historical MQTT backlog rather
    # than test records dated into the future.
    base_ts = datetime.now(timezone.utc) - timedelta(
        milliseconds=(message_count - 1) * 100
    )
    started = time.perf_counter()
    variant_seconds = {}
    progress = progress or (lambda _phase: None)

    with conn.cursor() as cur:
        progress("clearing")
        cur.execute(
            "TRUNCATE mqtt_test_raw, mqtt_test_samples, mqtt_test_arrays "
            "RESTART IDENTITY"
        )

        progress("raw")
        variant_started = time.perf_counter()
        cur.execute(
            """
            INSERT INTO mqtt_test_raw (ts, topic, payload)
            SELECT message_ts,
                   'sensors/broadcast',
                   jsonb_build_object(
                     'type', 'broadcast',
                     'samples', (
                       SELECT jsonb_agg(jsonb_build_object(
                         'sensor_id', sensor_id,
                         'ts', (extract(epoch FROM message_ts) * 1000)::bigint,
                         'value', sin((m * 10 + sensor_id)::double precision / 37.0)
                       ) ORDER BY sensor_id)
                       FROM generate_series(0, 9) AS sensor_id
                     )
                   )
            FROM (
              SELECT m, %s::timestamptz + m * interval '100 milliseconds' AS message_ts
              FROM generate_series(0, %s - 1) AS m
            ) AS messages
            """,
            (base_ts, message_count),
        )
        variant_seconds["raw"] = time.perf_counter() - variant_started

        progress("samples")
        variant_started = time.perf_counter()
        cur.execute(
            """
            INSERT INTO mqtt_test_samples (ts, sensor_id, value, topic)
            SELECT %s::timestamptz + (point / 10) * interval '100 milliseconds',
                   (point %% 10)::smallint,
                   sin(point::double precision / 37.0),
                   'sensors/broadcast'
            FROM generate_series(0, %s - 1) AS point
            """,
            (base_ts, sample_count),
        )
        variant_seconds["samples"] = time.perf_counter() - variant_started

        progress("arrays")
        variant_started = time.perf_counter()
        cur.execute(
            """
            INSERT INTO mqtt_test_arrays (ts, equipment_group, values)
            SELECT message_ts,
                   equipment_group,
                   ARRAY(
                     SELECT sin((m * 10 + sensor_id)::double precision / 37.0)
                     FROM generate_series(sensor_start, sensor_end) AS sensor_id
                     ORDER BY sensor_id
                   )
            FROM (
              SELECT m,
                     %s::timestamptz + m * interval '100 milliseconds' AS message_ts
              FROM generate_series(0, %s - 1) AS m
            ) AS messages
            CROSS JOIN (VALUES (1::smallint, 0, 5), (2::smallint, 6, 9))
              AS groups(equipment_group, sensor_start, sensor_end)
            """,
            (base_ts, message_count),
        )
        variant_seconds["arrays"] = time.perf_counter() - variant_started

        progress("analyzing")
        for _, table, _ in VARIANTS:
            cur.execute(f"ANALYZE {table}")

        elapsed = time.perf_counter() - started
        cur.execute("DELETE FROM mqtt_test_meta")
        cur.execute(
            """
            INSERT INTO mqtt_test_meta
              (singleton, sample_count, message_count, seeded_at, seed_seconds,
               variant_seed_seconds)
            VALUES (TRUE, %s, %s, now(), %s, %s::jsonb)
            """,
            (sample_count, message_count, elapsed, json.dumps(variant_seconds)),
        )
    conn.commit()
    return {
        "sample_count": sample_count,
        "message_count": message_count,
        "seed_seconds": round(time.perf_counter() - started, 3),
        "variant_seed_seconds": variant_seconds,
    }


def reset_variants(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE mqtt_test_raw, mqtt_test_samples, mqtt_test_arrays "
            "RESTART IDENTITY"
        )
        cur.execute("DELETE FROM mqtt_test_meta")
    conn.commit()


def get_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sample_count, message_count, seeded_at, seed_seconds, "
            "variant_seed_seconds "
            "FROM mqtt_test_meta WHERE singleton = TRUE"
        )
        meta = cur.fetchone()
        variants = []
        sample_count = meta[0] if meta else 0
        message_count = meta[1] if meta else 0
        seed_times = meta[4] if meta else {}
        for key, table, label in VARIANTS:
            cur.execute(
                f"SELECT count(*), pg_total_relation_size(%s::regclass) FROM {table}",
                (table,),
            )
            rows, size_bytes = cur.fetchone()
            seed_seconds = float(seed_times.get(key, 0)) if seed_times else 0
            variants.append(
                {
                    "key": key,
                    "label": label,
                    "rows": rows,
                    "size_bytes": size_bytes,
                    "bytes_per_point": (size_bytes / sample_count) if sample_count else 0,
                    "rows_per_message": (rows / message_count) if message_count else 0,
                    "seed_seconds": seed_seconds or None,
                    "points_per_second": (sample_count / seed_seconds) if seed_seconds else None,
                }
            )
    return {
        "sample_count": meta[0] if meta else 0,
        "message_count": meta[1] if meta else 0,
        "seeded_at": meta[2].isoformat() if meta else None,
        "seed_seconds": meta[3] if meta else None,
        "variants": variants,
    }


BENCHMARK_WORKLOADS = (
    (
        "sensor_history",
        "Single sensor · 10 min",
        {
            "raw": """
        SELECT count(*), avg((sample->>'value')::double precision)
        FROM mqtt_test_raw r
        CROSS JOIN LATERAL jsonb_array_elements(r.payload->'samples') AS sample
        WHERE r.ts >= (SELECT max(ts) - interval '10 minutes' FROM mqtt_test_raw)
          AND (sample->>'sensor_id')::int = 3
            """,
            "samples": """
        SELECT count(*), avg(value)
        FROM mqtt_test_samples
        WHERE sensor_id = 3
          AND ts >= (SELECT max(ts) - interval '10 minutes' FROM mqtt_test_samples)
            """,
            "arrays": """
        SELECT count(*), avg(values[4])
        FROM mqtt_test_arrays
        WHERE equipment_group = 1
          AND ts >= (SELECT max(ts) - interval '10 minutes' FROM mqtt_test_arrays)
            """,
        },
    ),
    (
        "latest_message",
        "Rebuild latest message",
        {
            "raw": """
                SELECT jsonb_array_length(payload->'samples'),
                       (SELECT avg((sample->>'value')::double precision)
                        FROM jsonb_array_elements(payload->'samples') AS sample)
                FROM mqtt_test_raw
                ORDER BY ts DESC
                LIMIT 1
            """,
            "samples": """
                SELECT count(*), avg(value)
                FROM mqtt_test_samples
                WHERE ts = (SELECT max(ts) FROM mqtt_test_samples)
            """,
            "arrays": """
                SELECT count(*), avg(value)
                FROM mqtt_test_arrays a
                CROSS JOIN LATERAL unnest(a.values) AS value
                WHERE a.ts = (
                  SELECT max(ts) FROM mqtt_test_arrays WHERE equipment_group = 1
                )
            """,
        },
    ),
    (
        "all_sensors",
        "All sensors · 10 min",
        {
            "raw": """
                SELECT count(*), avg((sample->>'value')::double precision)
                FROM mqtt_test_raw r
                CROSS JOIN LATERAL jsonb_array_elements(r.payload->'samples') AS sample
                WHERE r.ts >= (SELECT max(ts) - interval '10 minutes' FROM mqtt_test_raw)
            """,
            "samples": """
                SELECT count(*), avg(value)
                FROM mqtt_test_samples
                WHERE ts >= (
                  SELECT max(ts) - interval '10 minutes' FROM mqtt_test_samples
                )
            """,
            "arrays": """
                SELECT count(*), avg(value)
                FROM mqtt_test_arrays a
                CROSS JOIN LATERAL unnest(a.values) AS value
                WHERE a.ts >= (
                  SELECT max(ts) - interval '10 minutes'
                  FROM mqtt_test_arrays WHERE equipment_group = 1
                )
            """,
        },
    ),
)


def benchmark_variants(conn) -> list[dict]:
    results = []
    with conn.cursor() as cur:
        for workload, workload_label, queries in BENCHMARK_WORKLOADS:
            for key, _, label in VARIANTS:
                query = queries[key]
                cur.execute(query)  # warm caches and query planning paths
                timings = []
                points = average = None
                for _ in range(BENCHMARK_REPEATS):
                    started = time.perf_counter()
                    cur.execute(query)
                    points, average = cur.fetchone()
                    timings.append((time.perf_counter() - started) * 1000)
                results.append(
                    {
                        "workload": workload,
                        "workload_label": workload_label,
                        "key": key,
                        "label": label,
                        "query_ms": round(statistics.median(timings), 2),
                        "points_scanned": points,
                        "average": average,
                        "repeats": BENCHMARK_REPEATS,
                    }
                )
    return results
