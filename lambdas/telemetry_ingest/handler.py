"""
telemetry_ingest Lambda — API Gateway POST /telemetry

Validates X-API-Key, parses Schema Spec §6.1 payload, inserts into the
RDS PostgreSQL `shipments_telemetry` table via psycopg2.
"""
import json
import os

import psycopg2

INSERT_SQL = """
    INSERT INTO shipments_telemetry (truck_id, tracking_number, lat, lng, timestamp)
    VALUES (%s, %s, %s, %s, %s)
"""

REQUIRED_FIELDS = ('truck_id', 'tracking_number', 'lat', 'lng', 'timestamp')


def _response(status, body):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body),
    }


def _connect():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        connect_timeout=5,
    )


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    expected_key = os.environ.get('TELEMETRY_API_KEY', '')
    if not expected_key or headers.get('x-api-key') != expected_key:
        return _response(401, {'error': 'invalid api key'})

    raw_body = event.get('body') or ''
    try:
        payload = json.loads(raw_body)
    except (TypeError, ValueError):
        return _response(400, {'error': 'invalid json'})

    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        return _response(400, {'error': f'missing fields: {missing}'})

    try:
        conn = _connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(INSERT_SQL, (
                    payload['truck_id'],
                    payload['tracking_number'],
                    payload['lat'],
                    payload['lng'],
                    payload['timestamp'],
                ))
        finally:
            conn.close()
    except psycopg2.Error as exc:
        return _response(500, {'error': f'db error: {exc}'})

    return _response(201, {})
