"""
Replay the sensor stream CSV by put_record-ing telemetry payloads to a
Kinesis stream (Schema Spec §6.2).

Same CSV, same payload, same pacing rules as `simulate_sensors`:
  - --rate controls POSTs/sec (sleep 1/rate between records)
  - --duration-minutes optionally caps total runtime
  - timestamp_offset_seconds is added to the replay start time
    (NOT used for pacing)

Partition key is `tracking_number` so all records for the same shipment
land on the same shard, preserving per-truck order.
"""
import csv
import json
import time
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Replay the sensor stream CSV by put_record to Kinesis.'

    def add_arguments(self, parser):
        parser.add_argument('--csv-path', default='data/freightflow-sensor-stream.csv')
        parser.add_argument('--rate', type=float, default=1.0)
        parser.add_argument('--duration-minutes', type=float, default=None)

    def handle(self, *args, **options):
        stream = settings.KINESIS_STREAM_NAME
        if not stream:
            raise CommandError('KINESIS_STREAM_NAME must be set in .env')

        rate = max(options['rate'], 0.001)
        sleep_s = 1.0 / rate
        deadline = None
        if options['duration_minutes'] is not None:
            deadline = time.monotonic() + options['duration_minutes'] * 60

        replay_start = datetime.now(timezone.utc)
        client = boto3.client('kinesis', region_name=settings.AWS_REGION)
        sent = failed = 0

        try:
            with open(options['csv_path'], newline='') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if deadline is not None and time.monotonic() >= deadline:
                        self.stdout.write('Duration cap reached.')
                        break
                    payload = {
                        'truck_id': row['truck_id'],
                        'tracking_number': row['tracking_number'],
                        'lat': float(row['lat']),
                        'lng': float(row['lng']),
                        'timestamp': self._to_iso(replay_start, row['timestamp_offset_seconds']),
                    }
                    try:
                        client.put_record(
                            StreamName=stream,
                            Data=json.dumps(payload).encode('utf-8'),
                            PartitionKey=payload['tracking_number'],
                        )
                        sent += 1
                    except (BotoCoreError, ClientError) as exc:
                        failed += 1
                        self.stderr.write(f'  put_record failed: {exc}')
                    time.sleep(sleep_s)
        except FileNotFoundError:
            raise CommandError(f"CSV not found: {options['csv_path']}")

        self.stdout.write(self.style.SUCCESS(
            f'Done. sent={sent} failed={failed}'
        ))

    @staticmethod
    def _to_iso(replay_start, offset_seconds):
        ts = replay_start + timedelta(seconds=int(offset_seconds))
        return ts.strftime('%Y-%m-%dT%H:%M:%SZ')
