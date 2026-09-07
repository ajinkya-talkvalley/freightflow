# FreightFlow

A logistics operations dashboard built with Django 5. Tracks shipments, drivers,
routes, and live truck telemetry. Runs on SQLite locally with zero setup, and
on AWS RDS PostgreSQL in production by changing one environment variable.

The companion document `FreightFlow_Schema_Spec.md` is the single source of
truth for models, payload contracts, identifier conventions, and environment
variables.

---

## Prerequisites

- Python 3.12 or newer
- `pip` and `venv`
- (Optional, for AWS features) AWS account with credentials available via the
  default credential chain (`~/.aws/credentials`, environment variables, or an
  IAM role).

---

## Local setup (SQLite, zero AWS)

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> freightflow
cd freightflow

# 2. Create a virtualenv and install dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env                # Default DATABASE_URL is sqlite:///db.sqlite3

# 4. Run migrations and seed demo data
python manage.py migrate
python manage.py seed_demo_data     # 30 routes, 50 drivers, 3000 shipments

# 5. (Optional) Create a Django admin superuser
python manage.py createsuperuser

# 6. Run the dev server
python manage.py runserver
```

Open <http://localhost:8000/> for the dashboard. Other pages:

| Path           | Description                                            |
|----------------|--------------------------------------------------------|
| `/`            | KPI dashboard                                          |
| `/shipments/`  | Paginated, filterable shipment list                    |
| `/shipments/FF-000001/` | Shipment detail (with POD if uploaded)        |
| `/live/`       | Live truck tracking map (polls `/api/telemetry/latest/`) |
| `/analytics/`  | Historical analytics via Athena                        |
| `/ai/`         | AI assistant (Bedrock NL → SQL → Athena)               |
| `/admin/`      | Django admin                                           |

### Default Admin Credentials

| Field    | Value      |
|----------|------------|
| Username | `admin`    |
| Password | `admin123` |

Pages that depend on unconfigured AWS env vars (Athena, Bedrock) show a
friendly "not configured" banner instead of crashing.

---

## Wiring up AWS services, week by week

Each variable in `.env.example` is labelled with the week it is first used.

### Week 2 — AWS region
Set `AWS_REGION` (e.g. `us-west-2`). All boto3 clients use the default
credential chain — never hardcode keys.

### Week 3 — S3 for proof-of-delivery images
Create an S3 bucket and set `AWS_STORAGE_BUCKET_NAME`. The storage backend
toggle in `settings.py` will switch `STORAGES['default']` from
`FileSystemStorage` to `S3Boto3Storage` automatically.

### Week 4 — Telemetry ingest Lambda
1. Deploy `lambdas/telemetry_ingest/` behind API Gateway with header API key
   auth.
2. Set `TELEMETRY_INGEST_URL` and `TELEMETRY_API_KEY` in `.env`.
3. Run the simulator:
   ```bash
   python manage.py simulate_sensors --rate 1
   ```

### Week 5 — SNS status notifications
1. Create an SNS topic, subscribe the `lambdas/status_notify/` Lambda to it,
   and verify a SES sender address.
2. Set `SNS_STATUS_TOPIC_ARN` in `.env`.
3. Any change to `Shipment.status` (via admin or ORM) will publish the
   §6.4 message. Leave the env var blank to no-op silently.

### Week 6 — Athena historical analytics
1. Run the Glue ETL job `glue/etl_job.py` against the historical CSV to
   produce cleaned Parquet output.
2. Register a Glue table over the Parquet, then set:
   ```
   ATHENA_WORKGROUP=primary
   ATHENA_OUTPUT_LOCATION=s3://your-bucket/athena-results/
   ATHENA_DATABASE=freightflow_analytics
   ```
3. Visit `/analytics/`.

### Week 7 — Bedrock AI assistant
1. Request access to a Claude model in the Bedrock console.
2. Set `BEDROCK_MODEL_ID` and `BEDROCK_REGION` in `.env`.
3. Visit `/ai/` and ask questions in natural language. Generated SQL is
   validated as SELECT-only before being sent to Athena (30s timeout).

### Week 8 — Carrier webhook
Deploy `lambdas/carrier_webhook/` behind API Gateway with its own
`CARRIER_WEBHOOK_API_KEY` (set on the Lambda, *not* in Django's `.env`).

### Week 9 — Kinesis real-time telemetry
1. Create a Kinesis stream; deploy `lambdas/kinesis_telemetry_consumer/` with
   an event source mapping pointing at the stream.
2. Set `KINESIS_STREAM_NAME` in `.env`.
3. Run the Kinesis-flavoured simulator:
   ```bash
   python manage.py simulate_sensors_kinesis --rate 1
   ```

---

## Switching to RDS

Migrating the Django app from SQLite to RDS PostgreSQL is a **one-line**
change. Edit `.env`:

```
# Before (local dev)
DATABASE_URL=sqlite:///db.sqlite3

# After (AWS RDS)
DATABASE_URL=postgresql://USER:PASSWORD@your-rds-endpoint.us-west-2.rds.amazonaws.com:5432/freightflow
```

Then run `python manage.py migrate` against RDS. No code changes are needed —
all ORM queries are written portably (no `ILIKE`, no `DISTINCT ON`, no
PostgreSQL-only functions). In AWS deployments students restore
`freightflow-db.sql` into RDS rather than running `seed_demo_data`.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'decouple'`** — activate your
virtualenv and reinstall: `pip install -r requirements.txt`.

**`psycopg2` install fails on macOS** — install `libpq` (`brew install
libpq`) then retry. `psycopg2-binary` ships precompiled wheels for most
platforms.

**`/live/` map is blank** — telemetry rows are only inserted when the
ingest pipeline is running. Run `python manage.py simulate_sensors` (after
deploying the Week 4 Lambda) to generate data.

**`/analytics/` or `/ai/` show "not configured"** — set the matching env
vars in `.env`, then restart the dev server.

**Status changes are not emailed** — check that `SNS_STATUS_TOPIC_ARN` is
set, the SES sender is verified, and the `status_notify` Lambda has SES
permissions. Django will log SNS publish failures.

**Bedrock returns SQL that the safety gate rejects** — the gate enforces
SELECT-only; ask the assistant to "return a SELECT only" or rephrase the
question to avoid words like "update" or "delete".

---

## Project layout

```
freightflow/
├── manage.py
├── requirements.txt
├── .env.example
├── data/freightflow-sensor-stream.csv  # placeholder; replace with real file
├── freightflow/                         # Django project settings
├── shipments/                           # main app: models, views, signals, commands
├── analytics/                           # Athena historical queries
├── ai_assistant/                        # Bedrock NL → SQL
├── lambdas/                             # standalone AWS Lambda functions
│   ├── telemetry_ingest/
│   ├── status_notify/
│   ├── carrier_webhook/
│   └── kinesis_telemetry_consumer/
└── glue/etl_job.py                      # PySpark ETL for historical CSV
```
