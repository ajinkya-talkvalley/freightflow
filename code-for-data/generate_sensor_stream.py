#!/usr/bin/env python3
"""
Generates data/freightflow-sensor-stream.csv — 600 GPS waypoints for 8 trucks
moving along Southern California routes over a ~5-minute replay window.

Conforms to FreightFlow_Schema_Spec.md §5.2:
  - Columns: truck_id, tracking_number, lat, lng, timestamp_offset_seconds
  - Trucks T-01..T-08, each assigned to FF-000301..FF-000308 (§4 reserved range)
  - Routes between the 10 canonical SoCal cities (§3.4)
  - Rows interleaved by timestamp_offset_seconds (not grouped by truck)
"""

import csv
import os
import random

SEED = 42
WAYPOINTS_PER_TRUCK = 75
NUM_TRUCKS = 8
MAX_OFFSET = 300  # ~5-minute replay window

TRUCKS = [f"T-{i:02d}" for i in range(1, NUM_TRUCKS + 1)]
TRACKING_NUMBERS = [f"FF-0003{i:02d}" for i in range(1, NUM_TRUCKS + 1)]

# §3.4 canonical cities with representative hub coordinates
CITY_COORDS = {
    "Riverside":      (33.9806, -117.3755),
    "San Bernardino": (34.1083, -117.2898),
    "Ontario":        (34.0633, -117.6508),
    "Long Beach":     (33.7701, -118.1937),
    "Los Angeles":    (34.0522, -118.2437),
    "Anaheim":        (33.8353, -117.9145),
    "Irvine":         (33.6846, -117.8265),
    "Fontana":        (34.0922, -117.4350),
    "Pomona":         (34.0553, -117.7500),
    "Corona":         (33.8753, -117.5664),
}

# One route per truck.  curve_factor bends the path slightly off straight-line
# via a quadratic Bezier control point at the perpendicular-offset midpoint.
ROUTES = [
    ("Riverside",      "San Bernardino", 0.15),  # T-01 / FF-000301
    ("Long Beach",     "Anaheim",        0.15),  # T-02 / FF-000302
    ("Ontario",        "Pomona",         0.20),  # T-03 / FF-000303
    ("Irvine",         "Corona",         0.12),  # T-04 / FF-000304
    ("Fontana",        "Riverside",      0.10),  # T-05 / FF-000305
    ("Los Angeles",    "Long Beach",     0.10),  # T-06 / FF-000306
    ("Corona",         "Ontario",        0.10),  # T-07 / FF-000307
    ("San Bernardino", "Fontana",        0.20),  # T-08 / FF-000308
]


def bezier_point(t, p0, ctrl, p2):
    """Quadratic Bezier interpolation: returns (lat, lng) at parameter t."""
    u = 1 - t
    lat = u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p2[0]
    lng = u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p2[1]
    return lat, lng


def generate_waypoints(rng, origin, dest, n, curve_factor):
    """
    Generate n waypoints along a gently curved route using a quadratic Bezier.

    The control point sits at the midpoint displaced perpendicularly by
    curve_factor * |route_vector|, producing realistic road curvature.
    Small Gaussian noise (~0.0003 deg) is added per waypoint.
    """
    lat0, lng0 = origin
    lat2, lng2 = dest
    dlat = lat2 - lat0
    dlng = lng2 - lng0

    mid_lat = (lat0 + lat2) / 2.0
    mid_lng = (lng0 + lng2) / 2.0

    # Perpendicular unit-ish offset: rotate (dlat, dlng) by 90° and scale
    ctrl = (mid_lat + (-dlng * curve_factor),
            mid_lng + (dlat * curve_factor))

    waypoints = []
    for i in range(n):
        t = i / (n - 1)
        lat, lng = bezier_point(t, origin, ctrl, dest)
        lat += rng.gauss(0, 0.0003)
        lng += rng.gauss(0, 0.0003)
        waypoints.append((round(lat, 6), round(lng, 6)))

    return waypoints


def main():
    rng = random.Random(SEED)

    all_rows = []

    for idx, (truck_id, tracking_number) in enumerate(zip(TRUCKS, TRACKING_NUMBERS)):
        origin_name, dest_name, curve = ROUTES[idx]
        origin = CITY_COORDS[origin_name]
        dest = CITY_COORDS[dest_name]

        waypoints = generate_waypoints(rng, origin, dest, WAYPOINTS_PER_TRUCK, curve)

        # Stagger each truck's start by idx seconds so rows interleave after sort.
        # Distribute waypoints evenly from start_offset to MAX_OFFSET.
        start_offset = idx  # 0..7 seconds
        span = MAX_OFFSET - start_offset

        for j, (lat, lng) in enumerate(waypoints):
            offset = start_offset + round(j * span / (WAYPOINTS_PER_TRUCK - 1))
            all_rows.append({
                "truck_id": truck_id,
                "tracking_number": tracking_number,
                "lat": lat,
                "lng": lng,
                "timestamp_offset_seconds": offset,
            })

    # Interleave by timestamp; stable sort preserves truck order on ties
    all_rows.sort(key=lambda r: r["timestamp_offset_seconds"])

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "freightflow-sensor-stream.csv",
    )
    fieldnames = ["truck_id", "tracking_number", "lat", "lng", "timestamp_offset_seconds"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    size_kb = os.path.getsize(output_path) / 1024
    print(
        f"Generated freightflow-sensor-stream.csv: {len(all_rows)} waypoints across "
        f"{NUM_TRUCKS} trucks over ~5 minutes, size {size_kb:.1f} KB"
    )


if __name__ == "__main__":
    main()
