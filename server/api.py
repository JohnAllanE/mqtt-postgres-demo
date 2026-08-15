#!/usr/bin/env python3
from flask import Flask, jsonify, request
import os
import psycopg2
from urllib.parse import urlparse
import subprocess
import json

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://demo:demo@localhost:5432/demo')


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
        subprocess.run(['psql', DATABASE_URL, '-f', schema], check=True)
        subprocess.run(['psql', DATABASE_URL, '-f', seed], check=True)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/api/config', methods=['POST'])
def config():
    # Accepts JSON with keys: broadcast_interval, maintenance_interval, maintenance_sensors
    data = request.get_json() or {}
    # For now, just echo back; integration with MQTT broker can be done here
    return jsonify({'ok': True, 'applied': data})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
