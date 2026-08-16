#!/usr/bin/env python3
"""Simple MQTT -> PostgreSQL ingestion service.

Subscribes to `sensors/broadcast` topic and writes rows into `sensor_data`.

Configuration via environment variables:
  - MQTT_HOST (default: localhost)
  - MQTT_PORT (default: 1883)
  - DATABASE_URL (default: postgres://demo:demo@localhost:5432/demo)

This is a minimal prototype for Phase 2.
"""
import json
import os
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import psycopg2


MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://demo:demo@localhost:5432/demo')


def connect_db():
    # Simple psycopg2 connection
    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=(url.path or '').lstrip('/'),
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
    )
    conn.autocommit = True
    return conn


def on_connect(client, userdata, flags, rc):
    print('Connected to MQTT broker', MQTT_HOST, MQTT_PORT)
    client.subscribe('sensors/broadcast')


def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    try:
        obj = json.loads(payload)
    except Exception as e:
        print('Invalid JSON message:', e)
        return
    # Expecting {"type":"broadcast","samples":[{sensor_id,ts,value},...]}
    if obj.get('type') not in ('batch', 'broadcast'):
        return
    samples = obj.get('samples') or []
    # Pack values into arrays ordered by sensor_id and split into two equipment
    # groups: first 6 sensors and last 4 sensors.
    samples_sorted = sorted(samples, key=lambda s: s.get('sensor_id', 0))
    values = [float(s.get('value', 0.0)) for s in samples_sorted]
    values6 = values[:6]
    values4 = values[6:10]
    ts_ms = samples_sorted[0].get('ts') if samples_sorted else int(time.time() * 1000)
    ts = time.strftime('%Y-%m-%d %H:%M:%S+00', time.gmtime(ts_ms / 1000.0))

    conn = userdata.get('db')
    cur = conn.cursor()
    try:
        if len(values6) == 6:
            cur.execute(
                'INSERT INTO sensor_data (ts, equipment_type, values) VALUES (%s, %s, %s)',
                (ts, 1, values6),
            )
        if len(values4) == 4:
            cur.execute(
                'INSERT INTO sensor_data (ts, equipment_type, values) VALUES (%s, %s, %s)',
                (ts, 2, values4),
            )
    except Exception as e:
        print('DB insert error:', e)
    finally:
        cur.close()


def main():
    conn = connect_db()
    # create tables if missing
    with conn.cursor() as c:
        with open(os.path.join(os.path.dirname(__file__), 'schema.sql')) as fh:
            c.execute(fh.read())
        try:
            c.execute('SELECT COUNT(*) FROM equipment_type')
            equipment_count = c.fetchone()[0]
        except Exception:
            equipment_count = 0
        if equipment_count == 0:
            try:
                with open(os.path.join(os.path.dirname(__file__), 'seed.sql')) as fh:
                    c.execute(fh.read())
            except FileNotFoundError:
                pass

    client = mqtt.Client(userdata={'db': conn})
    client.user_data_set({'db': conn})
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print('Stopping')
    finally:
        client.disconnect()
        conn.close()


if __name__ == '__main__':
    main()
