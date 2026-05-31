"""
carrier_webhook Lambda — API Gateway POST /carrier-webhook

Validates X-API-Key (using CARRIER_WEBHOOK_API_KEY env var — NOT the
Django/telemetry key), parses Schema Spec §6.3 payload, updates
Shipment.status in RDS via psycopg2.
"""
import json
import os

import psycopg2

VALID_STATUSES = {
    'PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY',
    'DELIVERED', 'DELAYED', 'CANCELLED',
}

UPDATE_SQL = """
    UPDATE shipments_shipment
    SET status = %s
    WHERE tracking_number = %s
"""


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
    expected = os.environ.get('CARRIER_WEBHOOK_API_KEY', '')
    if not expected or headers.get('x-api-key') != expected:
        return _response(401, {'error': 'invalid api key'})

    try:
        payload = json.loads(event.get('body') or '')
    except (TypeError, ValueError):
        return _response(400, {'error': 'invalid json'})

    tracking = payload.get('tracking_number')
    new_status = payload.get('new_status')
    if not tracking or not new_status:
        return _response(400, {'error': 'tracking_number and new_status required'})
    if new_status not in VALID_STATUSES:
        return _response(400, {'error': f'invalid status: {new_status}'})

    try:
        conn = _connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(UPDATE_SQL, (new_status, tracking))
                if cur.rowcount == 0:
                    return _response(404, {'error': f'tracking_number not found: {tracking}'})
        finally:
            conn.close()
    except psycopg2.Error as exc:
        return _response(500, {'error': f'db error: {exc}'})

    return _response(200, {'updated': True})
