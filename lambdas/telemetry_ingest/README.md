# telemetry_ingest Lambda

Receives a Schema Spec §6.1 telemetry payload from API Gateway and inserts
it into the RDS PostgreSQL `shipments_telemetry` table.

## Trigger

API Gateway, POST `/telemetry`, with `X-API-Key` header.

## Environment variables (Schema Spec §7.2)

| Variable            | Purpose                                              |
|---------------------|------------------------------------------------------|
| `TELEMETRY_API_KEY` | Shared with Django's `TELEMETRY_API_KEY` for header validation |
| `DB_HOST`           | RDS endpoint                                         |
| `DB_NAME`           | Database name (e.g. `freightflow`)                   |
| `DB_USER`           | DB user                                              |
| `DB_PASSWORD`       | DB password                                          |

## Python packages

`requirements.txt` lists only `psycopg2-binary`. `boto3` is preinstalled in
the Lambda runtime and must not be included.

## Responses

- `201` empty body on success
- `401` `{"error": "invalid api key"}` if header missing/wrong
- `400` `{"error": "missing fields: [...]"}` or `{"error": "invalid json"}`
- `500` `{"error": "db error: ..."}` on DB failure

## Build / deploy

```bash
cd lambdas/telemetry_ingest
pip install -r requirements.txt -t .
zip -r telemetry_ingest.zip .
aws lambda update-function-code --function-name telemetry_ingest \
    --zip-file fileb://telemetry_ingest.zip
```
