#!/usr/bin/env python3
"""
generate_historical_csv.py — Generate freightflow-historical.csv for the Week 6 Glue ETL pipeline.

Produces 50,000 rows of historical shipment data with five intentional data quality
issues injected at controlled rates, matching FreightFlow_Schema_Spec.md §5.3.

Usage:
    python generate_historical_csv.py [--seed N]   (default seed: 42)

Column order (§5.3):
    tracking_number, shipment_date, estimated_delivery, actual_delivery,
    origin_city, destination_city, weight_kg, pieces, status, customer_email,
    driver_employee_id, route_code, carrier_tracking_number, delivery_notes
"""

import argparse
import csv
import math
import os
import random
from datetime import date, timedelta

from faker import Faker

OUTPUT_FILE = os.path.join("data", "freightflow-historical.csv")
NUM_ROWS    = 50_000

# §3.4 — 10 canonical Southern California cities
CITIES = [
    "Riverside", "San Bernardino", "Ontario", "Long Beach", "Los Angeles",
    "Anaheim", "Irvine", "Fontana", "Pomona", "Corona",
]

# §3.5 — status distribution (same weights as live DB)
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

# CSV column order as defined in §5.3
COLUMNS = [
    "tracking_number",
    "shipment_date",
    "estimated_delivery",
    "actual_delivery",
    "origin_city",
    "destination_city",
    "weight_kg",
    "pieces",
    "status",
    "customer_email",
    "driver_employee_id",
    "route_code",
    "carrier_tracking_number",
    "delivery_notes",
]

# Approximate DQ injection rates
RATE_EMAIL_MALFORMED        = 0.02    # §5.3 DQ2 — ~2 %
RATE_BLANK_DELIVERED        = 0.01    # §5.3 DQ1 — ~1 % of all rows
RATE_DATE_IMPOSSIBLE        = 0.01    # §5.3 DQ3 — ~1 % of all rows
RATE_INVALID_MEASUREMENT    = 0.005   # §5.3 DQ4 — ~0.5 %
RATE_US_DATE_FORMAT         = 0.30    # §5.3 DQ5 — ~30 % per date field

# DELIVERED makes up ~30 % of rows; to hit ~1 % of ALL rows we scale the
# conditional probability: P(issue | DELIVERED) = target_rate / delivered_rate
_DELIVERED_FRACTION = 0.30
RATE_BLANK_DELIVERED_COND  = RATE_BLANK_DELIVERED  / _DELIVERED_FRACTION
RATE_DATE_IMPOSSIBLE_COND  = RATE_DATE_IMPOSSIBLE  / _DELIVERED_FRACTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_date(d: date, us_format: bool) -> str:
    return d.strftime("%m/%d/%Y") if us_format else d.isoformat()


def city_pair(rng: random.Random) -> tuple[str, str]:
    a = rng.choice(CITIES)
    b = rng.choice([c for c in CITIES if c != a])
    return a, b


# ---------------------------------------------------------------------------
# Row generation
# ---------------------------------------------------------------------------

def generate_rows(rng: random.Random, fake: Faker) -> tuple[list[dict], dict]:
    today      = date.today()
    hist_start = date(today.year - 5, today.month, today.day)
    hist_span  = (today - hist_start).days

    dq = {
        "dq1_blank_actual_delivered": 0,
        "dq2_malformed_email":        0,
        "dq3_impossible_date_order":  0,
        "dq4_invalid_measurement":    0,
        "dq5_us_date_fields":         0,  # counts individual date *values* in US format
    }

    rows = []

    for i in range(NUM_ROWS):
        # §3.1 — tracking numbers FF-100001..FF-150000
        tracking = f"FF-{100001 + i:06d}"

        origin, dest = city_pair(rng)

        ship_date    = hist_start + timedelta(days=rng.randint(0, hist_span))
        est_delivery = ship_date + timedelta(days=rng.randint(1, 5))

        status = rng.choices(STATUS_LIST, weights=STATUS_WVALUES, k=1)[0]

        # Normal actual_delivery: only for DELIVERED
        if status == "DELIVERED":
            delta           = rng.randint(-2, 5)
            actual_delivery = est_delivery + timedelta(days=delta)
            if actual_delivery < ship_date:
                actual_delivery = ship_date + timedelta(days=rng.randint(0, 2))
        else:
            actual_delivery = None

        # Log-normal weight (§1.3), clamped to 1–500
        weight_kg = round(min(500.0, max(1.0, math.exp(rng.gauss(3.5, 1.0)))), 2)
        pieces    = rng.randint(1, 50)

        customer_email = fake.email()

        # §3.2 / §3.3 — driver and route ranges shared with live DB
        driver_id  = f"EMP-{rng.randint(1, 50):03d}"
        route_code = f"RT-{rng.randint(1, 30):03d}"

        carrier = f"CTN{rng.randint(100_000_000, 999_999_999)}" if rng.random() < 0.30 else ""

        delivery_notes = fake.sentence(nb_words=rng.randint(4, 12)) if rng.random() < 0.60 else ""

        # ------------------------------------------------------------------
        # Inject DQ issues (order matters: DQ1 before DQ3)
        # ------------------------------------------------------------------

        # DQ1 — blank actual_delivery but status = DELIVERED (~1 % of all rows)
        if status == "DELIVERED" and rng.random() < RATE_BLANK_DELIVERED_COND:
            actual_delivery = None
            dq["dq1_blank_actual_delivered"] += 1

        # DQ2 — malformed customer_email (~2 % of all rows)
        if rng.random() < RATE_EMAIL_MALFORMED:
            kind = rng.randint(0, 2)
            if kind == 0:
                customer_email = customer_email.replace("@", "")   # no @ symbol
            elif kind == 1:
                customer_email = ""                                  # empty string
            else:
                customer_email = customer_email + "   "             # trailing whitespace
            dq["dq2_malformed_email"] += 1

        # DQ3 — actual_delivery < shipment_date (~1 % of all rows)
        # Only rows with a non-null actual_delivery can exhibit this issue.
        if actual_delivery is not None and rng.random() < RATE_DATE_IMPOSSIBLE_COND:
            actual_delivery = ship_date - timedelta(days=rng.randint(1, 10))
            dq["dq3_impossible_date_order"] += 1

        # DQ4 — weight_kg <= 0 or pieces <= 0 (~0.5 % of all rows)
        if rng.random() < RATE_INVALID_MEASUREMENT:
            if rng.random() < 0.5:
                weight_kg = round(rng.uniform(-10.0, 0.0), 2)
            else:
                pieces = rng.randint(-5, 0)
            dq["dq4_invalid_measurement"] += 1

        # DQ5 — mixed date formats (~30 % per date field)
        us_ship = rng.random() < RATE_US_DATE_FORMAT
        us_est  = rng.random() < RATE_US_DATE_FORMAT
        us_act  = rng.random() < RATE_US_DATE_FORMAT

        dq["dq5_us_date_fields"] += sum([us_ship, us_est, (actual_delivery is not None and us_act)])

        ship_date_str    = fmt_date(ship_date,    us_ship)
        est_delivery_str = fmt_date(est_delivery, us_est)
        act_delivery_str = fmt_date(actual_delivery, us_act) if actual_delivery is not None else ""

        rows.append({
            "tracking_number":         tracking,
            "shipment_date":           ship_date_str,
            "estimated_delivery":      est_delivery_str,
            "actual_delivery":         act_delivery_str,
            "origin_city":             origin,
            "destination_city":        dest,
            "weight_kg":               weight_kg,
            "pieces":                  pieces,
            "status":                  status,
            "customer_email":          customer_email,
            "driver_employee_id":      driver_id,
            "route_code":              route_code,
            "carrier_tracking_number": carrier,
            "delivery_notes":          delivery_notes,
        })

    return rows, dq


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate FreightFlow historical CSV with intentional DQ issues."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    rng  = random.Random(args.seed)
    fake = Faker("en_US")
    Faker.seed(args.seed)

    print(f"Seed: {args.seed}")
    print(f"Generating {NUM_ROWS:,} rows ...")

    rows, dq = generate_rows(rng, fake)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    size_mb   = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    row_issues = (dq["dq1_blank_actual_delivered"] + dq["dq2_malformed_email"]
                  + dq["dq3_impossible_date_order"] + dq["dq4_invalid_measurement"])
    total_dq  = row_issues + dq["dq5_us_date_fields"]

    print(f"Generated {OUTPUT_FILE}: 50,000 rows, ~{total_dq:,} data quality issues injected, size {size_mb:.1f} MB")
    print(f"  DQ1 blank actual_delivery but DELIVERED : {dq['dq1_blank_actual_delivered']:>5}  (~{dq['dq1_blank_actual_delivered']/NUM_ROWS*100:.1f}% of rows)")
    print(f"  DQ2 malformed customer_email            : {dq['dq2_malformed_email']:>5}  (~{dq['dq2_malformed_email']/NUM_ROWS*100:.1f}% of rows)")
    print(f"  DQ3 actual_delivery < shipment_date     : {dq['dq3_impossible_date_order']:>5}  (~{dq['dq3_impossible_date_order']/NUM_ROWS*100:.1f}% of rows)")
    print(f"  DQ4 weight_kg or pieces <= 0            : {dq['dq4_invalid_measurement']:>5}  (~{dq['dq4_invalid_measurement']/NUM_ROWS*100:.1f}% of rows)")
    print(f"  DQ5 US-format date values               : {dq['dq5_us_date_fields']:>5}  (~{dq['dq5_us_date_fields']/(NUM_ROWS*2.3)*100:.0f}% of date fields)")


if __name__ == "__main__":
    main()
