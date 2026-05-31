# FreightFlow Schema Specification

**Purpose:** This document is the single source of truth for FreightFlow's data structure, identifier conventions, reserved ranges, JSON contracts, and configuration. Every generation prompt and every artifact must conform to this spec. If a prompt and this document disagree, this document wins.

---

## 1. Database Schema (Django Models)

All four models live in the Django app `shipments/`. The Django ORM is the sole interface for application reads/writes; Lambdas are exempt and may use psycopg2 directly.

### 1.1 Route

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | AutoField | PK | Standard Django auto-PK |
| `route_code` | CharField(10) | unique, indexed | Format: `RT-NNN` (e.g., `RT-001`) |
| `origin_city` | CharField(100) | not null | One of the 10 canonical cities (see §3.4) |
| `destination_city` | CharField(100) | not null | One of the 10 canonical cities |
| `distance_km` | DecimalField(6,2) | not null | Range: 20.00 – 150.00 |
| `typical_duration_hours` | DecimalField(4,2) | not null | Range: 0.5 – 3.5 |

### 1.2 Driver

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | AutoField | PK | |
| `employee_id` | CharField(10) | unique, indexed | Format: `EMP-NNN` (e.g., `EMP-001`) |
| `full_name` | CharField(200) | not null | Faker US locale |
| `license_number` | CharField(20) | not null | Format: `CA-D` + 7 digits (e.g., `CA-D1234567`) |
| `phone` | CharField(20) | not null | Faker US phone |
| `hire_date` | DateField | not null | Range: 2018-01-01 – 2025-12-31 |

### 1.3 Shipment

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | AutoField | PK | |
| `tracking_number` | CharField(15) | unique, indexed | Format: `FF-NNNNNN` |
| `status` | CharField(20) | not null, choices | See §3.5 for choices |
| `origin_city` | CharField(100) | not null | One of the 10 canonical cities |
| `destination_city` | CharField(100) | not null | One of the 10 canonical cities |
| `weight_kg` | DecimalField(8,2) | not null | Log-normal distribution, range ~1–500 |
| `pieces` | IntegerField | not null | Range: 1 – 50 |
| `shipment_date` | DateField | not null | Within last 365 days |
| `estimated_delivery` | DateField | not null | `shipment_date` + 1 to 5 days |
| `actual_delivery` | DateField | nullable | NULL unless status is DELIVERED |
| `is_delayed` | BooleanField | default False | True if `actual_delivery > estimated_delivery` |
| `customer_email` | EmailField | not null | Faker email (clean — historical CSV has malformed; live DB does not) |
| `driver` | ForeignKey(Driver) | nullable, on_delete=SET_NULL | |
| `route` | ForeignKey(Route) | nullable, on_delete=SET_NULL | |
| `carrier_tracking_number` | CharField(30) | nullable | External carrier ID for shipments handed off |
| `proof_of_delivery` | CharField(100) | nullable | S3 key or filename; NULL unless POD uploaded |

### 1.4 Telemetry

**Important:** `tracking_number` is denormalized (CharField, indexed) — **NOT a ForeignKey to Shipment**. This is deliberate, for write throughput. The telemetry table receives high-frequency GPS pings and must not block on FK validation.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | AutoField | PK | |
| `truck_id` | CharField(10) | indexed | Format: `T-NN` (e.g., `T-01` through `T-08`) |
| `tracking_number` | CharField(15) | indexed | NOT a FK — denormalized for throughput |
| `lat` | DecimalField(9,6) | not null | Latitude |
| `lng` | DecimalField(9,6) | not null | Longitude |
| `timestamp` | DateTimeField | indexed | ISO 8601, UTC |

---

## 2. Athena / Parquet Schema (Cleaned Historical Data)

The Glue ETL job reads `freightflow-historical.csv` from S3, cleans it (see §5.3), and writes Parquet output. Athena queries this Parquet output. **This schema differs from the live Django schema** — most importantly, it includes a computed `delay_days` column and uses `driver_employee_id` and `route_code` instead of foreign-key IDs.

This is the schema passed as context to Bedrock for natural-language-to-SQL.

| Column | Type | Notes |
|--------|------|-------|
| `tracking_number` | string | `FF-NNNNNN` |
| `shipment_date` | date | ISO 8601 |
| `estimated_delivery` | date | ISO 8601 |
| `actual_delivery` | date | ISO 8601, nullable |
| `origin_city` | string | One of the 10 canonical cities |
| `destination_city` | string | One of the 10 canonical cities |
| `weight_kg` | double | |
| `pieces` | int | |
| `status` | string | One of the status values (§3.5) |
| `customer_email` | string | Clean (malformed rows dropped by ETL) |
| `driver_employee_id` | string | `EMP-NNN` |
| `route_code` | string | `RT-NNN` |
| `carrier_tracking_number` | string | nullable |
| `delivery_notes` | string | Free text |
| `delay_days` | int | **Computed by Glue:** `actual_delivery - estimated_delivery` in days |

---

## 3. Identifier Conventions

### 3.1 Tracking Numbers
- Format: `FF-NNNNNN` (six digits, zero-padded)
- Range allocations:
  - **Live DB (Django + SQL dump):** `FF-000001` – `FF-003000` (3,000 shipments)
  - **Historical CSV:** `FF-100001` – `FF-150000` (50,000 shipments) — deliberately non-overlapping with the live DB
- See §4 for reserved ranges within the live DB

### 3.2 Driver IDs
- Format: `EMP-NNN` (three digits, zero-padded)
- Live DB range: `EMP-001` – `EMP-050` (50 drivers)
- Historical CSV uses the same range (drivers persist across history)

### 3.3 Route Codes
- Format: `RT-NNN` (three digits, zero-padded)
- Live DB range: `RT-001` – `RT-030` (30 routes)
- Historical CSV uses the same range

### 3.4 Canonical Cities

Exactly these 10 Southern California cities. Both live DB and historical CSV must use only these.

1. Riverside
2. San Bernardino
3. Ontario
4. Long Beach
5. Los Angeles
6. Anaheim
7. Irvine
8. Fontana
9. Pomona
10. Corona

### 3.5 Shipment Status

Exactly these 7 values:

| Status | Description |
|--------|-------------|
| `PENDING` | Created, not yet picked up |
| `PICKED_UP` | Picked up from origin |
| `IN_TRANSIT` | En route |
| `OUT_FOR_DELIVERY` | On final delivery vehicle |
| `DELIVERED` | Delivered successfully |
| `DELAYED` | Past estimated delivery, not yet delivered |
| `CANCELLED` | Cancelled before completion |

### 3.6 Truck IDs (for telemetry)
- Format: `T-NN` (two digits, zero-padded)
- Sensor stream uses: `T-01` through `T-08` (8 trucks)

### 3.7 POD Image Filenames
- Format: `pod_FF-NNNNNN.jpg`
- One image per shipment for the first 30 shipments only: `pod_FF-000001.jpg` through `pod_FF-000030.jpg`
- The `proof_of_delivery` column in the SQL dump must reference these exact filenames for `FF-000001` through `FF-000030`; NULL for all other shipments

---

## 4. Reserved Ranges & Required States (Live DB)

Within the live DB range `FF-000001` – `FF-003000`, these specific subranges have mandatory characteristics. Both `seed_demo_data` and `freightflow-db.sql` must satisfy all of them:

| Range | Required State | Why |
|-------|---------------|-----|
| `FF-000001` – `FF-000030` | `proof_of_delivery` set to `pod_FF-NNNNNN.jpg` | First 30 shipments have PODs (others are NULL) |
| `FF-000301` – `FF-000308` | status MUST be `IN_TRANSIT` | The sensor stream demo references these 8 trucks |
| `FF-001000` – `FF-002000` | All 1,001 tracking numbers MUST exist | The mock carrier script randomly picks from this range |

### Status Distribution (Approximate)

The remaining shipments outside the reserved ranges follow this distribution:

| Status | Approximate % |
|--------|--------------|
| PENDING | 15% |
| PICKED_UP | 10% |
| IN_TRANSIT | 25% |
| OUT_FOR_DELIVERY | 10% |
| DELIVERED | 30% |
| DELAYED | 8% |
| CANCELLED | 2% |

Note: The 8 reserved IN_TRANSIT shipments (`FF-000301`..`FF-000308`) count toward the 25% IN_TRANSIT bucket — not in addition to it.

---

## 5. Data Files

### 5.1 SQL Dump (`freightflow-db.sql`)
- PostgreSQL dump (compatible with `psql < freightflow-db.sql`)
- Contains: 30 routes, 50 drivers, 3,000 shipments
- No telemetry rows (telemetry populates at runtime from the sensor stream)
- All identifier conventions, reserved ranges, and status distribution from §3 and §4 apply

### 5.2 Sensor Stream CSV (`freightflow-sensor-stream.csv`)

| Column | Type | Notes |
|--------|------|-------|
| `truck_id` | string | `T-01` – `T-08` |
| `tracking_number` | string | One of `FF-000301` – `FF-000308` |
| `lat` | float | Latitude |
| `lng` | float | Longitude |
| `timestamp_offset_seconds` | int | Seconds from replay start (NOT an absolute timestamp) |

- 600 total rows (~75 waypoints per truck)
- 8 trucks moving along their routes within Southern California
- Coordinates within latitude 33.5–34.5, longitude -118.5 to -117.0 (encompassing the 10 canonical cities with margin)
- Designed to replay over ~5 minutes; `timestamp_offset_seconds` values range from 0 to ~300
- **Important:** The `simulate_sensors` and `simulate_sensors_kinesis` management commands convert `timestamp_offset_seconds` into an absolute ISO 8601 datetime by adding the offset to the replay start time (`datetime.utcnow()` at command start). They do NOT use the offset for pacing — the `--rate` argument (default 1 POST per second) controls runtime pacing independently of the offset column.

### 5.3 Historical CSV (`freightflow-historical.csv`)

| Column | Type | Notes |
|--------|------|-------|
| `tracking_number` | string | `FF-100001` – `FF-150000` |
| `shipment_date` | string | **Mixed formats: ISO (YYYY-MM-DD) and US (MM/DD/YYYY)** — Glue ETL normalizes |
| `estimated_delivery` | string | Same mixed formats |
| `actual_delivery` | string | Same mixed formats, may be blank |
| `origin_city` | string | One of the 10 canonical cities |
| `destination_city` | string | One of the 10 canonical cities |
| `weight_kg` | float | Log-normal distribution; **some rows have ≤ 0 values** (Glue drops these) |
| `pieces` | int | Range 1–50; **some rows have ≤ 0 values** (Glue drops these) |
| `status` | string | One of the status values (§3.5) |
| `customer_email` | string | **~2% are malformed** (no @, trailing spaces, empty) — Glue drops these |
| `driver_employee_id` | string | `EMP-001` – `EMP-050` |
| `route_code` | string | `RT-001` – `RT-030` |
| `carrier_tracking_number` | string | nullable |
| `delivery_notes` | string | Free text |

**The 5 Intentional Data Quality Issues** (Glue ETL must clean these):

1. **Blank `actual_delivery` but `status = DELIVERED`** — inconsistent state; drop the row
2. **Malformed `customer_email`** (no `@` or empty string) — drop the row
3. **`actual_delivery < shipment_date`** — impossible time ordering; drop the row
4. **`weight_kg <= 0` or `pieces <= 0`** — invalid measurements; drop the row
5. **Mixed date formats** (ISO `YYYY-MM-DD` and US `MM/DD/YYYY`) — normalize to ISO

The cleaned output is written as Parquet with an additional computed `delay_days` column.

### 5.4 POD Assets Zip (`freightflow-assets.zip`)
- Contains 30 JPEG images named `pod_FF-000001.jpg` through `pod_FF-000030.jpg`
- Generated programmatically (PIL or similar) — simple images with the tracking number rendered on a logistics-themed background
- Each ~50–200 KB; total zip under 5 MB

---

## 6. JSON Payload Contracts

These are the network protocols between services. **Every contract here must be matched exactly by every component that produces or consumes the payload.**

### 6.1 Telemetry Ingest (API Gateway → Lambda)

**Request:**
- Method: POST
- Header: `X-API-Key: <TELEMETRY_API_KEY>`
- Body:
```json
{
  "truck_id": "T-01",
  "tracking_number": "FF-000301",
  "lat": 33.9806,
  "lng": -117.3755,
  "timestamp": "2026-05-23T14:30:00Z"
}
```

**Response:** 201 Created (no body needed)

### 6.2 Telemetry Ingest (Kinesis Stream)

**Record format** (JSON string, partition key = `tracking_number`):
```json
{
  "truck_id": "T-01",
  "tracking_number": "FF-000301",
  "lat": 33.9806,
  "lng": -117.3755,
  "timestamp": "2026-05-23T14:30:00Z"
}
```

Same payload as 6.1 — only the transport differs. This identity is the whole pedagogical point of Week 9.

### 6.3 Carrier Webhook (External Carrier → API Gateway → Lambda)

**Request:**
- Method: POST
- Header: `X-API-Key: <CARRIER_WEBHOOK_API_KEY>`
- Body:
```json
{
  "tracking_number": "FF-001234",
  "new_status": "OUT_FOR_DELIVERY",
  "location": "Riverside Distribution Center",
  "timestamp": "2026-05-23T14:30:00Z"
}
```

**Response:** 200 OK with `{"updated": true}` on success, 4xx with error message on validation failure

### 6.4 SNS Status Change Message (Django → SNS → Lambda)

Published by a Django `post_save` signal on `Shipment`:

```json
{
  "tracking_number": "FF-001234",
  "old_status": "IN_TRANSIT",
  "new_status": "OUT_FOR_DELIVERY",
  "customer_email": "customer@example.com"
}
```

### 6.5 Bedrock NL-to-SQL Prompt Context

The AI assistant view passes this schema description to Bedrock (NOT the Django schema — the Athena schema from §2):

```
You are a SQL generator. Generate ONLY a SELECT query (no INSERT, UPDATE, DELETE, DROP).
Table: shipments
Columns:
  tracking_number (string)
  shipment_date (date)
  estimated_delivery (date)
  actual_delivery (date, nullable)
  origin_city (string)
  destination_city (string)
  weight_kg (double)
  pieces (int)
  status (string: PENDING, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, DELAYED, CANCELLED)
  customer_email (string)
  driver_employee_id (string)
  route_code (string)
  carrier_tracking_number (string)
  delivery_notes (string)
  delay_days (int)
```

### 6.6 Live Tracking Telemetry API (Django → Browser)

The Live Tracking page polls `GET /api/telemetry/latest/` every 3 seconds. The view returns the most recent telemetry row per `truck_id` (a `LATEST_BY truck_id` style query).

**Response:** 200 OK, JSON body:

```json
{
  "trucks": [
    {
      "truck_id": "T-01",
      "tracking_number": "FF-000301",
      "lat": 33.9806,
      "lng": -117.3755,
      "timestamp": "2026-05-23T14:30:00Z"
    }
  ]
}
```

- Empty trucks array if no telemetry rows exist yet
- Up to 8 entries (one per active truck)
- The frontend JavaScript that consumes this endpoint expects exactly this shape

---

## 7. Environment Variables

### 7.1 Django Application (`.env`)

| Variable | Week First Used | Notes |
|----------|----------------|-------|
| `DEBUG` | 1 | `True` locally, `False` on AWS |
| `SECRET_KEY` | 1 | Random string |
| `DATABASE_URL` | 1 → 4 | `sqlite:///db.sqlite3` locally; replaced with `postgresql://...` RDS URL in Week 4 |
| `AWS_REGION` | 2 | e.g., `us-west-2` |
| `AWS_STORAGE_BUCKET_NAME` | 3 | S3 bucket for POD images |
| `TELEMETRY_INGEST_URL` | 4 | API Gateway URL for telemetry-ingest Lambda |
| `TELEMETRY_API_KEY` | 4 | Shared with telemetry-ingest Lambda's own env var |
| `SNS_STATUS_TOPIC_ARN` | 5 | SNS topic Django publishes to on status change |
| `ATHENA_WORKGROUP` | 6 | Athena workgroup name |
| `ATHENA_OUTPUT_LOCATION` | 6 | `s3://your-bucket/athena-results/` |
| `ATHENA_DATABASE` | 6 | `freightflow_analytics` |
| `BEDROCK_MODEL_ID` | 7 | e.g., `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `BEDROCK_REGION` | 7 | e.g., `us-west-2` |
| `KINESIS_STREAM_NAME` | 9 | Kinesis stream name for real-time telemetry |

### 7.2 Lambda Function Environment Variables

Each Lambda has its OWN environment configuration set on the Lambda function in AWS — not in Django's `.env`. Each Lambda also has its OWN `requirements.txt` listing only the packages it needs.

**`telemetry_ingest` Lambda:**
- Env vars: `TELEMETRY_API_KEY` (same value as Django's, for header validation); `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (RDS connection)
- Python packages: `psycopg2-binary` (boto3 is preinstalled in the Lambda runtime — do not include it in requirements.txt)

**`status_notify` Lambda:**
- Env vars: `SES_FROM_ADDRESS` (verified sender); `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (RDS connection for shipment lookup)
- Python packages: `psycopg2-binary` (boto3 is preinstalled in the Lambda runtime)

**`carrier_webhook` Lambda:**
- Env vars: `CARRIER_WEBHOOK_API_KEY` (for header validation — NOT in Django's `.env`); `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (RDS connection)
- Python packages: `psycopg2-binary`

**`kinesis_telemetry_consumer` Lambda:**
- Env vars: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (RDS connection)
- No API key — invocation auth is via the Kinesis event source mapping
- Python packages: `psycopg2-binary`

### 7.3 CLI Arguments (Not Env Vars)

The `mock-carrier-webhook.py` script takes its configuration via CLI arguments — never env vars:
- `--webhook-url` (required)
- `--api-key` (required) — passes the carrier-webhook Lambda's API key
- `--count` (default 50)
- `--duration-minutes` (default 5)
- `--seed` (optional, for reproducibility)

---

## 8. Glue ETL Job Specification

**Input:** `s3://{input-bucket}/freightflow-historical.csv`  
**Output:** `s3://{output-bucket}/cleaned/` (Parquet, Snappy compression)  
**Bucket names come from job parameters, not hardcoded.**

**Operations (in order):**

1. Drop rows where `actual_delivery` is blank but `status = DELIVERED`
2. Drop rows where `customer_email` is malformed (no `@` or empty)
3. Drop rows where `actual_delivery < shipment_date`
4. Drop rows where `weight_kg <= 0` or `pieces <= 0`
5. Normalize mixed date formats (ISO and US) to ISO across `shipment_date`, `estimated_delivery`, `actual_delivery`
6. Add computed column: `delay_days = (actual_delivery - estimated_delivery)` in days, NULL if either side is NULL

Output schema matches §2 exactly.

---

## 9. Validation Checklist

Before declaring the package complete, verify every item:

### Cross-File Consistency

- [ ] Tracking number ranges don't overlap between live DB (`FF-000001`..`FF-003000`) and historical CSV (`FF-100001`..`FF-150000`)
- [ ] Driver IDs `EMP-001`..`EMP-050` appear consistently in SQL dump and historical CSV
- [ ] Route codes `RT-001`..`RT-030` appear consistently in SQL dump and historical CSV
- [ ] City names match the canonical 10-city list (§3.4) across SQL dump, historical CSV, and seed_demo_data
- [ ] Status values match the 7 canonical statuses (§3.5) across all data files

### Reserved Range Compliance

- [ ] POD image filenames `pod_FF-000001.jpg`..`pod_FF-000030.jpg` match `proof_of_delivery` values in first 30 SQL dump shipment rows
- [ ] Tracking numbers `FF-000301`..`FF-000308` exist in SQL dump with status `IN_TRANSIT`
- [ ] Tracking numbers `FF-001000`..`FF-002000` all exist in SQL dump
- [ ] `seed_demo_data` produces the same tracking ranges, status distribution, driver IDs, route codes, IN_TRANSIT reservations as the SQL dump

### Schema Conformance

- [ ] Django `models.py` matches §1 exactly
- [ ] SQL dump `CREATE TABLE` statements match Django models
- [ ] Telemetry model uses `tracking_number` as `CharField`, NOT `ForeignKey` to Shipment
- [ ] Glue ETL output schema matches §2
- [ ] AI assistant view passes the Athena schema (§2), not the Django schema, as context to Bedrock
- [ ] `GET /api/telemetry/latest/` returns the JSON shape from §6.6 (object with `trucks` array) and the frontend JavaScript consumes that exact shape

### Configuration

- [ ] `.env.example` lists every variable from §7.1 in the same order
- [ ] Each Lambda's README documents the env vars from §7.2
- [ ] `mock-carrier-webhook.py` accepts CLI args from §7.3 — does NOT read env vars

### Code Structure

- [ ] All four Lambda function folders (`telemetry_ingest`, `status_notify`, `carrier_webhook`, `kinesis_telemetry_consumer`) exist with `handler.py`, `requirements.txt`, and `README.md`
- [ ] `glue/etl_job.py` implements all 6 operations from §8 in order (5 cleaning + 1 computation)
- [ ] Both management commands exist: `simulate_sensors.py` and `simulate_sensors_kinesis.py`
- [ ] All Django database access uses the ORM (no raw SQL outside migration `RunSQL`, no `ILIKE`, no `JSONB`)
- [ ] The Django app runs locally with default `.env` (SQLite) and shows seed data after `python manage.py seed_demo_data`

### File Sizes

- [ ] Total package under 30 MB
- [ ] POD assets zip under 5 MB

---

*Version 1.2 · May 2026*