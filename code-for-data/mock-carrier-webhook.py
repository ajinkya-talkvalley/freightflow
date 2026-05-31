"""
Simulates an external carrier system posting shipment status updates to the
FreightFlow carrier webhook endpoint.

Live mode — POST to a running endpoint:
    python mock-carrier-webhook.py \\
        --webhook-url https://<api-id>.execute-api.us-west-2.amazonaws.com/prod/carrier-webhook \\
        --api-key abc123secretkey \\
        --count 50 \\
        --duration-minutes 5 \\
        --seed 42

Dry-run mode — write payloads to a JSON file (no network calls):
    python mock-carrier-webhook.py \\
        --output ../data/carrier-webhook-events.json \\
        --count 50 \\
        --seed 42

Both modes together (POST and save):
    python mock-carrier-webhook.py \\
        --webhook-url https://... \\
        --api-key abc123secretkey \\
        --output ../data/carrier-webhook-events.json \\
        --count 50 \\
        --seed 42

The script picks random tracking numbers from FF-001000 through FF-002000
(guaranteed to exist in the live DB per the FreightFlow Schema Spec §4),
generates a plausible forward status transition from IN_TRANSIT, and either
POSTs each update to the webhook or saves them to --output (or both).
Calls are spread evenly across --duration-minutes when in live mode.

Dependencies:
    pip install requests
"""

import argparse
import json
import random
import time
from datetime import datetime, timezone

# requests is only imported when actually sending HTTP requests
try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

# §3.5 — forward transitions from IN_TRANSIT; CANCELLED excluded
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
    return {
        "tracking_number": tracking_number,
        "new_status": rng.choice(STATUS_TRANSITIONS),
        "location": rng.choice(LOCATIONS),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def post_with_retry(url: str, headers: dict, payload: dict) -> tuple[int, float]:
    """POST payload, retrying once on network error with 1s backoff.

    Returns (http_status_code, elapsed_ms). Returns (-1, 0.0) after two failures.
    """
    for attempt in range(2):
        try:
            start = time.monotonic()
            resp = _requests.post(url, json=payload, headers=headers, timeout=10)
            elapsed_ms = (time.monotonic() - start) * 1000
            return resp.status_code, elapsed_ms
        except _requests.RequestException as exc:
            if attempt == 0:
                print(f"    Network error: {exc}. Retrying in 1s…")
                time.sleep(1)
            else:
                print(f"    Network error on retry: {exc}. Skipping.")
    return -1, 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate carrier webhook POSTs to the FreightFlow API."
    )
    parser.add_argument("--webhook-url", default=None, help="Full URL of the carrier webhook endpoint")
    parser.add_argument("--api-key", default=None, help="CARRIER_WEBHOOK_API_KEY value")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Write generated payloads as a JSON array to this file (dry-run when --webhook-url is omitted)")
    parser.add_argument("--count", type=int, default=50, help="Number of webhook events to generate/send (default: 50)")
    parser.add_argument("--duration-minutes", type=float, default=5.0,
                        help="Spread HTTP calls evenly over this many minutes (default: 5, ignored in dry-run)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    live_mode = args.webhook_url is not None
    dry_run = not live_mode

    if live_mode and args.api_key is None:
        parser.error("--api-key is required when --webhook-url is provided")
    if not live_mode and args.output is None:
        parser.error("Provide --webhook-url (live mode), --output (dry-run), or both")
    if live_mode and _requests is None:
        parser.error("pip install requests is required for live mode")

    rng = random.Random(args.seed)

    # §4 — FF-001000 through FF-002000 are guaranteed to exist in the live DB
    tracking_pool = [f"FF-{n:06d}" for n in range(1000, 2001)]
    selected = [rng.choice(tracking_pool) for _ in range(args.count)]

    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"} if live_mode else {}
    sleep_interval = (args.duration_minutes * 60) / args.count if (live_mode and args.count > 1) else 0

    sent = 0
    failed = 0
    total_elapsed_ms = 0.0
    all_payloads = []

    for i, tracking_number in enumerate(selected, start=1):
        payload = build_payload(tracking_number, rng)
        all_payloads.append(payload)

        if live_mode:
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
        else:
            print(f"[{i}/{args.count}] {tracking_number} → {payload['new_status']} (dry-run)")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(all_payloads, f, indent=2)
        print(f"\nWrote {len(all_payloads)} payloads to {args.output}")

    if live_mode:
        avg_ms = (total_elapsed_ms / sent) if sent > 0 else 0.0
        print(
            f"\nSent {sent}/{args.count} webhooks. "
            f"{failed} failed. "
            f"Average response time: {avg_ms:.0f}ms"
        )


if __name__ == "__main__":
    main()
