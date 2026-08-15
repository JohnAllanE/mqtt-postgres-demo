#!/usr/bin/env python3
from flask import Flask, jsonify, request
import os
import psycopg2
from urllib.parse import urlparse
import json

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://demo:demo@localhost:5432/demo')
MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))


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
            with open(seed, 'r', encoding='utf-8') as fh:
                cur.execute(fh.read())
        conn.close()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/api/config', methods=['POST'])
def config():
    # Accepts JSON with keys like: maintenance_interval, broadcast_interval,
    # maintenance_sensors (comma string or list[int])
    data = request.get_json() or {}
    # Publish config over MQTT so simulators can apply changes live.
    if mqtt is not None:
        try:
            client = mqtt.Client()
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.publish('sensors/config', json.dumps(data))
            client.disconnect()
        except Exception as e:
            return jsonify({'ok': False, 'error': f'mqtt publish failed: {e}'}), 500
    return jsonify({'ok': True, 'applied': data})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
