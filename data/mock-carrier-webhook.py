"""
Simulates an external carrier system posting shipment status updates to the
FreightFlow carrier webhook endpoint.

Example invocation:
    python mock-carrier-webhook.py \\
        --webhook-url https://<api-id>.execute-api.us-west-2.amazonaws.com/prod/carrier-webhook \\
        --api-key abc123secretkey \\
        --count 50 \\
        --duration-minutes 5 \\
        --seed 42

The script picks random tracking numbers from FF-001000 through FF-002000
(guaranteed to exist in the live DB per the FreightFlow Schema Spec §4),
generates a plausible forward status transition from IN_TRANSIT, and POSTs
each update to the webhook, spreading calls evenly across --duration-minutes.

Dependencies:
    pip install requests
"""

import argparse
import random
import time
from datetime import datetime, timezone

import requests

# §3.5 — status values and forward transitions from IN_TRANSIT
# Occasional DELAYED is realistic; CANCELLED is excluded (forward progress only)
STATUS_TRANSITIONS = [
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELIVERED",
    "DELIVERED",
    "DELAYED",
]

LOCATIONS = [
    "Riverside Distribution Center",
    "San Bernardino Sorting Facility",
    "Ontario Freight Hub",
    "Long Beach Port Terminal",
    "Los Angeles Central Depot",
    "Anaheim Logistics Park",
    "Irvine Business Center",
    "Fontana Warehouse District",
    "Pomona Transfer Station",
    "Corona Industrial Zone",
]


def build_payload(tracking_number: str, rng: random.Random) -> dict:
    new_status = rng.choice(STATUS_TRANSITIONS)
    location = rng.choice(LOCATIONS)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "tracking_number": tracking_number,
        "new_status": new_status,
        "location": location,
        "timestamp": timestamp,
    }


def post_with_retry(url: str, headers: dict, payload: dict) -> tuple[int, float]:
    """POST payload, retrying once on network error with exponential backoff.

    Returns (http_status_code, elapsed_ms). On two consecutive network errors,
    returns (-1, 0.0).
    """
    for attempt in range(2):
        try:
            start = time.monotonic()
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            elapsed_ms = (time.monotonic() - start) * 1000
            return resp.status_code, elapsed_ms
        except requests.RequestException as exc:
            if attempt == 0:
                backoff = 2 ** attempt  # 1 second before retry
                print(f"    Network error: {exc}. Retrying in {backoff}s…")
                time.sleep(backoff)
            else:
                print(f"    Network error on retry: {exc}. Skipping.")
    return -1, 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate carrier webhook POSTs to the FreightFlow API."
    )
    parser.add_argument("--webhook-url", required=True, help="Full URL of the carrier webhook endpoint")
    parser.add_argument("--api-key", required=True, help="CARRIER_WEBHOOK_API_KEY value")
    parser.add_argument("--count", type=int, default=50, help="Number of webhook calls to send (default: 50)")
    parser.add_argument("--duration-minutes", type=float, default=5.0, help="Spread calls evenly over this many minutes (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    # §4 — FF-001000 through FF-002000 are guaranteed to exist in the live DB
    tracking_pool = [f"FF-{n:06d}" for n in range(1000, 2001)]
    selected = [rng.choice(tracking_pool) for _ in range(args.count)]

    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}

    # Sleep between calls so they're evenly spread across --duration-minutes
    total_seconds = args.duration_minutes * 60
    sleep_interval = total_seconds / args.count if args.count > 1 else 0

    sent = 0
    failed = 0
    total_elapsed_ms = 0.0

    for i, tracking_number in enumerate(selected, start=1):
        payload = build_payload(tracking_number, rng)
        status_code, elapsed_ms = post_with_retry(args.webhook_url, headers, payload)

        if status_code == -1:
            failed += 1
            print(f"[{i}/{args.count}] {tracking_number} → {payload['new_status']} (NETWORK ERROR)")
        elif status_code >= 400:
            failed += 1
            print(f"[{i}/{args.count}] {tracking_number} → {payload['new_status']} ({status_code} ERROR)")
        else:
            sent += 1
            total_elapsed_ms += elapsed_ms
            print(f"[{i}/{args.count}] {tracking_number} → {payload['new_status']} ({status_code} OK)")

        if i < args.count:
            time.sleep(sleep_interval)

    avg_ms = (total_elapsed_ms / sent) if sent > 0 else 0.0
    print(
        f"\nSent {sent}/{args.count} webhooks. "
        f"{failed} failed. "
        f"Average response time: {avg_ms:.0f}ms"
    )


if __name__ == "__main__":
    main()
