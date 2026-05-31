# status_notify Lambda

Triggered by SNS. Parses the Schema Spec §6.4 status-change message,
re-fetches `customer_email` from RDS, and sends a notification email via
SES.

## Trigger

SNS topic — set Django's `SNS_STATUS_TOPIC_ARN` to this topic so a
`Shipment.status` change publishes here.

## Environment variables (Schema Spec §7.2)

| Variable           | Purpose                                            |
|--------------------|----------------------------------------------------|
| `SES_FROM_ADDRESS` | Verified SES sender (e.g. `noreply@your-domain.com`) |
| `DB_HOST`          | RDS endpoint                                       |
| `DB_NAME`          | Database name                                      |
| `DB_USER`          | DB user                                            |
| `DB_PASSWORD`      | DB password                                        |

## Python packages

`psycopg2-binary` only. `boto3` is preinstalled in the Lambda runtime.

## IAM

The execution role needs:
- `ses:SendEmail` on the `SES_FROM_ADDRESS` identity
- VPC permissions if RDS is in a private subnet

## Build / deploy

```bash
cd lambdas/status_notify
pip install -r requirements.txt -t .
zip -r status_notify.zip .
aws lambda update-function-code --function-name status_notify \
    --zip-file fileb://status_notify.zip
```
