# kinesis_telemetry_consumer Lambda

Triggered by a Kinesis event source mapping. Each invocation receives a
batch of records carrying the Schema Spec §6.2 telemetry payload
(base64-encoded). The handler bulk-inserts them into the RDS
`shipments_telemetry` table.

## Trigger

Kinesis event source mapping. No API key — invocation auth is via the
event source mapping itself.

Enable **report batch item failures** on the event source mapping so the
handler can return `{"batchItemFailures": [...]}` and Kinesis re-delivers
only the failed records.

## Environment variables (Schema Spec §7.2)

| Variable      | Purpose          |
|---------------|------------------|
| `DB_HOST`     | RDS endpoint     |
| `DB_NAME`     | Database name    |
| `DB_USER`     | DB user          |
| `DB_PASSWORD` | DB password      |

## Python packages

`psycopg2-binary` only. `boto3` is preinstalled in the Lambda runtime.

## Build / deploy

```bash
cd lambdas/kinesis_telemetry_consumer
pip install -r requirements.txt -t .
zip -r kinesis_telemetry_consumer.zip .
aws lambda update-function-code --function-name kinesis_telemetry_consumer \
    --zip-file fileb://kinesis_telemetry_consumer.zip
```
