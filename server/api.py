#!/usr/bin/env python3
from flask import Flask, jsonify, request
import os
import psycopg2
from urllib.parse import urlparse
import json
import threading

from load_test import (
    benchmark_variants,
    get_stats,
    reset_variants,
    seed_variants,
    validate_sample_count,
)

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://demo:demo@localhost:5432/demo')
MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
MIN_INTERVAL = 0.5
load_test_lock = threading.Lock()
load_test_state = {'running': False, 'phase': 'idle', 'error': None}


def connect_db():
    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=(url.path or '').lstrip('/'),
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
    )
    return conn


def ensure_schema(conn):
    with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), encoding='utf-8') as fh:
        with conn.cursor() as cur:
            cur.execute(fh.read())
    conn.commit()


def clamp_interval(value):
    try:
        return max(MIN_INTERVAL, float(value))
    except Exception:
        return MIN_INTERVAL


@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp


@app.route('/api/<path:_any>', methods=['OPTIONS'])
def preflight(_any):
    return ('', 204)


@app.route('/api/recent')
def recent():
    limit = int(request.args.get('limit', '10'))
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT ts, values FROM sensor_data ORDER BY ts DESC LIMIT %s', (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = [{'ts': r[0].isoformat(), 'values': r[1]} for r in rows]
    return jsonify(out)


@app.route('/api/reset-db', methods=['POST'])
def reset_db():
    base = os.path.dirname(__file__)
    schema = os.path.join(base, 'schema.sql')
    seed = os.path.join(base, 'seed.sql')
    try:
        conn = connect_db()
        conn.autocommit = True
        with conn.cursor() as cur:
            with open(schema, 'r', encoding='utf-8') as fh:
                cur.execute(fh.read())
            cur.execute('TRUNCATE TABLE sensor_data, equipment_type RESTART IDENTITY CASCADE')
            with open(seed, 'r', encoding='utf-8') as fh:
                cur.execute(fh.read())
        conn.close()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True})


def run_load_test_seed(sample_count):
    conn = None
    try:
        conn = connect_db()
        ensure_schema(conn)

        def progress(phase):
            with load_test_lock:
                load_test_state['phase'] = phase

        result = seed_variants(conn, sample_count, progress)
        with load_test_lock:
            load_test_state.update(result)
            load_test_state.update({'running': False, 'phase': 'complete', 'error': None})
    except Exception as exc:
        if conn:
            conn.rollback()
        with load_test_lock:
            load_test_state.update({'running': False, 'phase': 'failed', 'error': str(exc)})
    finally:
        if conn:
            conn.close()


@app.route('/api/test-db/seed', methods=['POST'])
def seed_test_db():
    data = request.get_json(silent=True) or {}
    try:
        sample_count = validate_sample_count(data.get('sample_count', 1_000_000))
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    with load_test_lock:
        if load_test_state['running']:
            return jsonify({'ok': False, 'error': 'a seed job is already running'}), 409
        load_test_state.clear()
        load_test_state.update({
            'running': True,
            'phase': 'starting',
            'error': None,
            'sample_count': sample_count,
        })
    threading.Thread(target=run_load_test_seed, args=(sample_count,), daemon=True).start()
    return jsonify({'ok': True, 'sample_count': sample_count}), 202


@app.route('/api/test-db/status')
def test_db_status():
    with load_test_lock:
        state = dict(load_test_state)
    if state.get('running'):
        return jsonify({'ok': True, **state})
    try:
        conn = connect_db()
        ensure_schema(conn)
        stats = get_stats(conn)
        conn.close()
        return jsonify({'ok': True, **state, **stats})
    except Exception as exc:
        return jsonify({'ok': False, **state, 'error': str(exc)}), 500


@app.route('/api/test-db/benchmark', methods=['POST'])
def benchmark_test_db():
    with load_test_lock:
        if load_test_state['running']:
            return jsonify({'ok': False, 'error': 'wait for the seed job to finish'}), 409
    try:
        conn = connect_db()
        ensure_schema(conn)
        stats = get_stats(conn)
        if not stats['sample_count']:
            conn.close()
            return jsonify({'ok': False, 'error': 'seed the test database first'}), 400
        results = benchmark_variants(conn)
        conn.close()
        return jsonify({'ok': True, 'results': results})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/test-db/reset', methods=['POST'])
def reset_test_db():
    with load_test_lock:
        if load_test_state['running']:
            return jsonify({'ok': False, 'error': 'wait for the seed job to finish'}), 409
    try:
        conn = connect_db()
        ensure_schema(conn)
        reset_variants(conn)
        conn.close()
        with load_test_lock:
            load_test_state.clear()
            load_test_state.update({'running': False, 'phase': 'idle', 'error': None})
        return jsonify({'ok': True})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/config', methods=['POST'])
def config():
    # Accepts JSON with keys like: maintenance_interval, broadcast_interval,
    # maintenance_sensors (comma string or list[int])
    data = request.get_json() or {}
    if 'broadcast_interval' in data:
        data['broadcast_interval'] = clamp_interval(data['broadcast_interval'])
    if 'maintenance_interval' in data:
        data['maintenance_interval'] = clamp_interval(data['maintenance_interval'])
    # Publish config over MQTT so simulators can apply changes live.
    if mqtt is None:
        return jsonify({'ok': False, 'error': 'paho-mqtt is not available in the API environment'}), 500
    if mqtt is not None:
        try:
            client = mqtt.Client()
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.loop_start()
            info = client.publish('sensors/config', json.dumps(data), retain=True)
            info.wait_for_publish()
            client.loop_stop()
            client.disconnect()
        except Exception as e:
            return jsonify({'ok': False, 'error': f'mqtt publish failed: {e}'}), 500
    return jsonify({'ok': True, 'applied': data})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
