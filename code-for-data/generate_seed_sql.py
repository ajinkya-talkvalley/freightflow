#!/usr/bin/env python3
"""
Generate freightflow-db.sql — PostgreSQL 16 seed data for the FreightFlow application.
Conforms to FreightFlow_Schema_Spec.md §1, §3, §4, §5.1.

Usage:
    python generate_seed_sql.py [--seed N]   (default seed: 42)
"""

import argparse
import math
import os
import random
from datetime import date, timedelta

from faker import Faker

OUTPUT_FILE = "freightflow-db.sql"

# §3.4 — 10 canonical Southern California cities
CITIES = [
    "Riverside", "San Bernardino", "Ontario", "Long Beach", "Los Angeles",
    "Anaheim", "Irvine", "Fontana", "Pomona", "Corona",
]

# §3.5 — exactly 7 status values with approximate distribution weights (§4 table)
STATUS_WEIGHTS = [
    ("PENDING",           15),
    ("PICKED_UP",         10),
    ("IN_TRANSIT",        25),
    ("OUT_FOR_DELIVERY",  10),
    ("DELIVERED",         30),
    ("DELAYED",            8),
    ("CANCELLED",          2),
]
STATUS_LIST    = [s for s, _ in STATUS_WEIGHTS]
STATUS_WVALUES = [w for _, w in STATUS_WEIGHTS]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def q(val) -> str:
    """Single-quote a string value, escaping internal quotes. NULL for None."""
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"

def qd(d) -> str:
    """Format a date for SQL, or NULL."""
    return "NULL" if d is None else f"'{d.isoformat()}'"

def qb(b: bool) -> str:
    return "TRUE" if b else "FALSE"


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def city_pair(rng: random.Random):
    """Return (origin, destination) — always different cities."""
    a = rng.choice(CITIES)
    b = rng.choice([c for c in CITIES if c != a])
    return a, b


def generate_routes(rng: random.Random) -> list[tuple]:
    rows = []
    for i in range(1, 31):
        origin, dest = city_pair(rng)
        distance_km      = round(rng.uniform(20.0, 150.0), 2)
        duration_hours   = round(rng.uniform(0.5, 3.5), 2)
        rows.append((i, f"RT-{i:03d}", origin, dest, distance_km, duration_hours))
    return rows


def generate_drivers(rng: random.Random, fake: Faker) -> list[tuple]:
    rows = []
    hire_start = date(2018, 1, 1)
    hire_end   = date(2025, 12, 31)
    hire_span  = (hire_end - hire_start).days

    for i in range(1, 51):
        name        = fake.name()
        license_num = f"CA-D{rng.randint(1000000, 9999999)}"
        phone       = fake.phone_number()[:20]
        hire_date   = hire_start + timedelta(days=rng.randint(0, hire_span))
        rows.append((i, f"EMP-{i:03d}", name, license_num, phone, hire_date))
    return rows


def generate_shipments(rng: random.Random, fake: Faker,
                       num_routes: int = 30, num_drivers: int = 50) -> list[tuple]:
    today      = date.today()
    date_start = today - timedelta(days=365)
    date_span  = 365
    rows = []

    for i in range(1, 3001):
        tracking  = f"FF-{i:06d}"
        origin, dest = city_pair(rng)

        ship_date    = date_start + timedelta(days=rng.randint(0, date_span))
        est_delivery = ship_date + timedelta(days=rng.randint(1, 5))

        # Log-normal weight (§1.3): clamped to 1.00–500.00 kg
        weight_kg = round(min(500.0, max(1.0, math.exp(rng.gauss(3.5, 1.0)))), 2)
        pieces    = rng.randint(1, 50)

        customer_email = fake.email()
        driver_id      = rng.randint(1, num_drivers)
        route_id       = rng.randint(1, num_routes)

        # §3.7 — POD filenames for first 30 shipments only
        pod = f"pod_FF-{i:06d}.jpg" if 1 <= i <= 30 else None

        # §4 — FF-000301..FF-000308 must be IN_TRANSIT
        if 301 <= i <= 308:
            status = "IN_TRANSIT"
        else:
            status = rng.choices(STATUS_LIST, weights=STATUS_WVALUES, k=1)[0]

        # actual_delivery / is_delayed
        actual_delivery = None
        is_delayed      = False

        if status == "DELIVERED":
            delta = rng.randint(-2, 5)
            actual_delivery = est_delivery + timedelta(days=delta)
            if actual_delivery < ship_date:
                actual_delivery = ship_date + timedelta(days=rng.randint(0, 2))
            is_delayed = actual_delivery > est_delivery
        elif status == "DELAYED":
            is_delayed = True   # past estimated, not yet delivered — actual_delivery stays NULL

        # carrier_tracking_number (nullable, ~30 % filled)
        carrier = None
        if rng.random() < 0.30:
            carrier = f"CTN{rng.randint(100_000_000, 999_999_999)}"

        rows.append((
            i, tracking, status, origin, dest,
            weight_kg, pieces,
            ship_date, est_delivery, actual_delivery,
            is_delayed, customer_email,
            driver_id, route_id,
            carrier, pod,
        ))

    return rows


# ---------------------------------------------------------------------------
# SQL writer
# ---------------------------------------------------------------------------

def build_sql(routes: list, drivers: list, shipments: list) -> str:
    out = []

    out.append("-- FreightFlow PostgreSQL 16 seed data")
    out.append("-- Generated by generate_seed_sql.py")
    out.append("-- DO NOT hand-edit — regenerate via the script.")
    out.append("")
    out.append("SET client_encoding = 'UTF8';")
    out.append("SET standard_conforming_strings = on;")
    out.append("")

    # TRUNCATE — shipments first (it holds the FKs), then drivers/routes.
    # CASCADE is included for safety but should be a no-op given the order.
    # shipments_telemetry is intentionally excluded (populated at runtime).
    out.append("-- Idempotent reset — telemetry table is preserved.")
    out.append("TRUNCATE TABLE shipments_shipment CASCADE;")
    out.append("TRUNCATE TABLE shipments_driver   CASCADE;")
    out.append("TRUNCATE TABLE shipments_route    CASCADE;")
    out.append("")

    # ---- Routes ----
    out.append("-- Routes (30)")
    route_rows = ",\n".join(
        f"  ({r[0]}, {q(r[1])}, {q(r[2])}, {q(r[3])}, {r[4]}, {r[5]})"
        for r in routes
    )
    out.append(
        "INSERT INTO shipments_route\n"
        "  (id, route_code, origin_city, destination_city, distance_km, typical_duration_hours)\n"
        "VALUES\n"
        f"{route_rows};"
    )
    out.append("")

    # ---- Drivers ----
    out.append("-- Drivers (50)")
    driver_rows = ",\n".join(
        f"  ({d[0]}, {q(d[1])}, {q(d[2])}, {q(d[3])}, {q(d[4])}, {qd(d[5])})"
        for d in drivers
    )
    out.append(
        "INSERT INTO shipments_driver\n"
        "  (id, employee_id, full_name, license_number, phone, hire_date)\n"
        "VALUES\n"
        f"{driver_rows};"
    )
    out.append("")

    # ---- Shipments (batched in 500-row chunks for readability) ----
    out.append("-- Shipments (3,000)")
    BATCH = 500
    for batch_start in range(0, len(shipments), BATCH):
        batch = shipments[batch_start : batch_start + BATCH]
        ship_rows = ",\n".join(
            "  ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
                s[0],          # id
                q(s[1]),       # tracking_number
                q(s[2]),       # status
                q(s[3]),       # origin_city
                q(s[4]),       # destination_city
                s[5],          # weight_kg
                s[6],          # pieces
                qd(s[7]),      # shipment_date
                qd(s[8]),      # estimated_delivery
                qd(s[9]),      # actual_delivery
                qb(s[10]),     # is_delayed
                q(s[11]),      # customer_email
                s[12],         # driver_id
                s[13],         # route_id
                q(s[14]),      # carrier_tracking_number
                q(s[15]),      # proof_of_delivery
            )
            for s in batch
        )
        out.append(
            "INSERT INTO shipments_shipment\n"
            "  (id, tracking_number, status, origin_city, destination_city,\n"
            "   weight_kg, pieces, shipment_date, estimated_delivery, actual_delivery,\n"
            "   is_delayed, customer_email, driver_id, route_id,\n"
            "   carrier_tracking_number, proof_of_delivery)\n"
            "VALUES\n"
            f"{ship_rows};"
        )
        out.append("")

    # Reset auto-increment sequences so future ORM inserts don't collide.
    out.append("-- Reset sequences")
    out.append("SELECT setval('shipments_route_id_seq',    (SELECT MAX(id) FROM shipments_route));")
    out.append("SELECT setval('shipments_driver_id_seq',   (SELECT MAX(id) FROM shipments_driver));")
    out.append("SELECT setval('shipments_shipment_id_seq', (SELECT MAX(id) FROM shipments_shipment));")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Validation (quick sanity checks before writing)
# ---------------------------------------------------------------------------

def validate(routes, drivers, shipments):
    assert len(routes)   == 30,   f"Expected 30 routes, got {len(routes)}"
    assert len(drivers)  == 50,   f"Expected 50 drivers, got {len(drivers)}"
    assert len(shipments) == 3000, f"Expected 3,000 shipments, got {len(shipments)}"

    tracking_set = {s[1] for s in shipments}

    # §4 — FF-000301..FF-000308 must be IN_TRANSIT
    for i in range(301, 309):
        tn = f"FF-{i:06d}"
        match = next((s for s in shipments if s[1] == tn), None)
        assert match is not None, f"{tn} missing"
        assert match[2] == "IN_TRANSIT", f"{tn} status is {match[2]}, expected IN_TRANSIT"

    # §4 — FF-001000..FF-002000 all must exist (1,001 numbers)
    for i in range(1000, 2001):
        tn = f"FF-{i:06d}"
        assert tn in tracking_set, f"{tn} missing from shipments"

    # §3.7 — POD filenames for first 30
    for i in range(1, 31):
        tn = f"FF-{i:06d}"
        match = next((s for s in shipments if s[1] == tn), None)
        assert match is not None, f"{tn} missing"
        expected_pod = f"pod_FF-{i:06d}.jpg"
        assert match[15] == expected_pod, f"{tn} pod={match[15]!r}, expected {expected_pod!r}"

    # No POD outside first 30
    for s in shipments[30:]:
        assert s[15] is None, f"{s[1]} has unexpected POD {s[15]!r}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate FreightFlow PostgreSQL seed data.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    rng  = random.Random(args.seed)
    fake = Faker("en_US")
    Faker.seed(args.seed)

    print(f"Seed: {args.seed}")
    print("Generating routes ...")
    routes = generate_routes(rng)

    print("Generating drivers ...")
    drivers = generate_drivers(rng, fake)

    print("Generating shipments ...")
    shipments = generate_shipments(rng, fake)

    print("Validating ...")
    validate(routes, drivers, shipments)

    print("Writing SQL ...")
    sql = build_sql(routes, drivers, shipments)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(sql)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"Generated {OUTPUT_FILE}: 30 routes, 50 drivers, 3,000 shipments, size {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
