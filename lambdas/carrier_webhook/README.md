# carrier_webhook Lambda

Receives a Schema Spec §6.3 webhook payload from an external carrier and
updates the corresponding `Shipment.status` in RDS.

## Trigger

API Gateway, POST `/carrier-webhook`, with `X-API-Key` header.

## Environment variables (Schema Spec §7.2)

| Variable                   | Purpose                                            |
|----------------------------|----------------------------------------------------|
| `CARRIER_WEBHOOK_API_KEY`  | Header validation. **Not** in Django's `.env`.     |
| `DB_HOST`                  | RDS endpoint                                       |
| `DB_NAME`                  | Database name                                      |
| `DB_USER`                  | DB user                                            |
| `DB_PASSWORD`              | DB password                                        |

## Python packages

`psycopg2-binary` only. `boto3` is preinstalled in the Lambda runtime.

## Responses

- `200` `{"updated": true}` on success
- `400` `{"error": "..."}` on bad payload / invalid status
- `401` `{"error": "invalid api key"}`
- `404` `{"error": "tracking_number not found: ..."}`
- `500` `{"error": "db error: ..."}`

## Build / deploy

```bash
cd lambdas/carrier_webhook
pip install -r requirements.txt -t .
zip -r carrier_webhook.zip .
aws lambda update-function-code --function-name carrier_webhook \
    --zip-file fileb://carrier_webhook.zip
```
