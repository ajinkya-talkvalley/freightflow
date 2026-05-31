"""
Seed the local SQLite database with demo data per Schema Spec §§1, 3, 4.

Generates:
  - 30 routes        (RT-001..RT-030)
  - 50 drivers       (EMP-001..EMP-050)
  - 3,000 shipments  (FF-000001..FF-003000)

Satisfies every reserved range:
  - FF-000001..FF-000030: proof_of_delivery = "pod_FF-NNNNNN.jpg"
  - FF-000301..FF-000308: status forced to IN_TRANSIT
  - FF-001000..FF-002000: all 1,001 tracking numbers exist

Idempotent: skips if shipments already exist.
This command is for local dev only — AWS deployments restore
`freightflow-db.sql` into RDS instead.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from shipments.models import CANONICAL_CITIES, Driver, Route, Shipment, ShipmentStatus


# Status distribution (Schema Spec §4) — applied to non-reserved shipments only
STATUS_WEIGHTS = [
    (ShipmentStatus.PENDING, 0.15),
    (ShipmentStatus.PICKED_UP, 0.10),
    (ShipmentStatus.IN_TRANSIT, 0.25),
    (ShipmentStatus.OUT_FOR_DELIVERY, 0.10),
    (ShipmentStatus.DELIVERED, 0.30),
    (ShipmentStatus.DELAYED, 0.08),
    (ShipmentStatus.CANCELLED, 0.02),
]

POD_RESERVED = set(range(1, 31))               # FF-000001..FF-000030
IN_TRANSIT_RESERVED = set(range(301, 309))     # FF-000301..FF-000308
EXISTENCE_RESERVED = set(range(1000, 2001))    # FF-001000..FF-002000 (1001 numbers)


class Command(BaseCommand):
    help = 'Seed local DB with 30 routes, 50 drivers, 3000 shipments (idempotent).'

    def handle(self, *args, **options):
        if Shipment.objects.exists():
            self.stdout.write(self.style.WARNING(
                'Shipments already exist — skipping seed (delete db.sqlite3 to reseed).'
            ))
            return

        Faker.seed(42)
        random.seed(42)
        fake = Faker('en_US')

        with transaction.atomic():
            routes = self._seed_routes()
            drivers = self._seed_drivers(fake)
            self._seed_shipments(fake, routes, drivers)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {Route.objects.count()} routes, '
            f'{Driver.objects.count()} drivers, '
            f'{Shipment.objects.count()} shipments.'
        ))

    # -- routes -----------------------------------------------------------
    def _seed_routes(self):
        routes = []
        for i in range(1, 31):
            origin, dest = random.sample(CANONICAL_CITIES, 2)
            routes.append(Route(
                route_code=f'RT-{i:03d}',
                origin_city=origin,
                destination_city=dest,
                distance_km=Decimal(f'{random.uniform(20, 150):.2f}'),
                typical_duration_hours=Decimal(f'{random.uniform(0.5, 3.5):.2f}'),
            ))
        Route.objects.bulk_create(routes)
        self.stdout.write(f'  routes:    {len(routes)} created')
        return list(Route.objects.all())

    # -- drivers ----------------------------------------------------------
    def _seed_drivers(self, fake):
        drivers = []
        hire_start = date(2018, 1, 1)
        hire_span = (date(2025, 12, 31) - hire_start).days
        for i in range(1, 51):
            drivers.append(Driver(
                employee_id=f'EMP-{i:03d}',
                full_name=fake.name(),
                license_number=f'CA-D{random.randint(1000000, 9999999)}',
                phone=fake.numerify('(###) ###-####'),
                hire_date=hire_start + timedelta(days=random.randint(0, hire_span)),
            ))
        Driver.objects.bulk_create(drivers)
        self.stdout.write(f'  drivers:   {len(drivers)} created')
        return list(Driver.objects.all())

    # -- shipments --------------------------------------------------------
    def _pick_status(self, n):
        """Pick a status honoring reserved ranges and the §4 distribution."""
        if n in IN_TRANSIT_RESERVED:
            return ShipmentStatus.IN_TRANSIT
        r = random.random()
        cumulative = 0.0
        for status, weight in STATUS_WEIGHTS:
            cumulative += weight
            if r <= cumulative:
                return status
        return ShipmentStatus.PENDING

    def _seed_shipments(self, fake, routes, drivers):
        shipments = []
        today = date.today()

        # Ensure every tracking number 1..3000 is generated — reserved ranges
        # 1..30, 301..308, 1000..2000 are all subsets of 1..3000.
        for n in range(1, 3001):
            tracking = f'FF-{n:06d}'
            status = self._pick_status(n)

            shipment_date = today - timedelta(days=random.randint(0, 364))
            est_offset = random.randint(1, 5)
            estimated_delivery = shipment_date + timedelta(days=est_offset)

            actual_delivery = None
            is_delayed = False
            if status == ShipmentStatus.DELIVERED:
                # Most delivered shipments arrive on time, some slightly late
                delivered_offset = est_offset + random.choice([-1, 0, 0, 0, 1, 2])
                delivered_offset = max(delivered_offset, 1)
                actual_delivery = shipment_date + timedelta(days=delivered_offset)
                is_delayed = actual_delivery > estimated_delivery
            elif status == ShipmentStatus.DELAYED:
                # Past ETA, not yet delivered
                is_delayed = True

            # Log-normal-ish weight in 1..500
            weight = max(1.0, min(500.0, random.lognormvariate(3.0, 1.0)))

            proof = f'pod_{tracking}.jpg' if n in POD_RESERVED else None
            carrier_tn = (
                f'CAR{random.randint(10**8, 10**9 - 1)}'
                if random.random() < 0.30 else None
            )

            shipments.append(Shipment(
                tracking_number=tracking,
                status=status,
                origin_city=random.choice(CANONICAL_CITIES),
                destination_city=random.choice(CANONICAL_CITIES),
                weight_kg=Decimal(f'{weight:.2f}'),
                pieces=random.randint(1, 50),
                shipment_date=shipment_date,
                estimated_delivery=estimated_delivery,
                actual_delivery=actual_delivery,
                is_delayed=is_delayed,
                customer_email=fake.email(),
                driver=random.choice(drivers) if random.random() < 0.95 else None,
                route=random.choice(routes) if random.random() < 0.90 else None,
                carrier_tracking_number=carrier_tn,
                proof_of_delivery=proof,
            ))

        # bulk_create skips Shipment.save(), so the SNS signal does not fire
        # (correct: signals are for live updates, not seed loads).
        Shipment.objects.bulk_create(shipments, batch_size=500)
        self.stdout.write(f'  shipments: {len(shipments)} created')
