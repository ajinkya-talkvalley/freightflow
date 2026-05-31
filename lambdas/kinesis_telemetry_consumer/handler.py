"""
kinesis_telemetry_consumer Lambda — triggered by Kinesis event source mapping.

Each invocation receives a batch of records (Schema Spec §6.2 payload,
base64-encoded). Bulk-inserts into the RDS `shipments_telemetry` table.
Returns batchItemFailures so Kinesis re-delivers only the records that
failed to insert.
"""
import base64
import json
import os

import psycopg2
from psycopg2.extras import execute_values

INSERT_SQL = """
    INSERT INTO shipments_telemetry (truck_id, tracking_number, lat, lng, timestamp)
    VALUES %s
"""

REQUIRED_FIELDS = ('truck_id', 'tracking_number', 'lat', 'lng', 'timestamp')


def _connect():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        connect_timeout=5,
    )


def _decode(record):
    """Return (sequence_number, payload_dict) for a single Kinesis record."""
    seq = record['kinesis']['sequenceNumber']
    raw = base64.b64decode(record['kinesis']['data'])
    payload = json.loads(raw)
    if not all(f in payload for f in REQUIRED_FIELDS):
        raise ValueError(f'missing fields in record {seq}')
    return seq, payload


def lambda_handler(event, context):
    rows = []           # list of tuples ready for execute_values
    seqs = []           # parallel list of sequence numbers
    failures = []       # records that could not be decoded

    for rec in event.get('Records', []):
        try:
            seq, payload = _decode(rec)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            bad_seq = rec.get('kinesis', {}).get('sequenceNumber')
            print(f'decode failed seq={bad_seq}: {exc}')
            if bad_seq:
                failures.append({'itemIdentifier': bad_seq})
            continue
        rows.append((
            payload['truck_id'],
            payload['tracking_number'],
            payload['lat'],
            payload['lng'],
            payload['timestamp'],
        ))
        seqs.append(seq)

    if not rows:
        return {'batchItemFailures': failures}

    try:
        conn = _connect()
        try:
            with conn, conn.cursor() as cur:
                execute_values(cur, INSERT_SQL, rows, page_size=500)
        finally:
            conn.close()
    except psycopg2.Error as exc:
        print(f'bulk insert failed: {exc}')
        # Whole batch failed — mark all valid sequence numbers for retry.
        failures.extend({'itemIdentifier': s} for s in seqs)

    return {'batchItemFailures': failures}
