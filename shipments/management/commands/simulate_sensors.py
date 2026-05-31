"""
Replay the sensor stream CSV by POSTing telemetry payloads to the
ingest endpoint (API Gateway → telemetry_ingest Lambda).

Payload follows Schema Spec §6.1; header X-API-Key = TELEMETRY_API_KEY.

Conversion: `timestamp_offset_seconds` in the CSV is added to the replay
start time (datetime.utcnow() captured at command start) to produce the
absolute ISO 8601 timestamp. Pacing is controlled by --rate (sleep
1/rate between POSTs), NOT by the offset column.
"""
import csv
import time
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Replay the sensor stream CSV against the telemetry ingest endpoint.'

    def add_arguments(self, parser):
        parser.add_argument('--csv-path', default='data/freightflow-sensor-stream.csv')
        parser.add_argument('--rate', type=float, default=1.0,
                            help='POSTs per second (default 1).')
        parser.add_argument('--duration-minutes', type=float, default=None,
                            help='Optional cap on total runtime.')

    def handle(self, *args, **options):
        url = settings.TELEMETRY_INGEST_URL
        api_key = settings.TELEMETRY_API_KEY
        if not url or not api_key:
            raise CommandError(
                'TELEMETRY_INGEST_URL and TELEMETRY_API_KEY must be set in .env'
            )

        rate = max(options['rate'], 0.001)
        sleep_s = 1.0 / rate
        deadline = None
        if options['duration_minutes'] is not None:
            deadline = time.monotonic() + options['duration_minutes'] * 60

        replay_start = datetime.now(timezone.utc)
        session = requests.Session()
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
                        r = session.post(
                            url,
                            json=payload,
                            headers={'X-API-Key': api_key, 'Content-Type': 'application/json'},
                            timeout=10,
                        )
                        if r.status_code in (200, 201):
                            sent += 1
                        else:
                            failed += 1
                            self.stderr.write(f'  {r.status_code} {r.text[:120]}')
                    except requests.RequestException as exc:
                        failed += 1
                        self.stderr.write(f'  request failed: {exc}')
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
