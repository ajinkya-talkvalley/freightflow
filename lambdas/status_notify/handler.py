"""
status_notify Lambda — triggered by SNS.

Parses the Schema Spec §6.4 message, looks up the shipment in RDS to
confirm the customer_email is current, and sends an SES email.
"""
import json
import os

import boto3
import psycopg2

LOOKUP_SQL = """
    SELECT customer_email
    FROM shipments_shipment
    WHERE tracking_number = %s
"""


def _connect():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        connect_timeout=5,
    )


def _send_email(to_address, subject, body):
    ses = boto3.client('ses')
    ses.send_email(
        Source=os.environ['SES_FROM_ADDRESS'],
        Destination={'ToAddresses': [to_address]},
        Message={
            'Subject': {'Data': subject, 'Charset': 'UTF-8'},
            'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}},
        },
    )


def lambda_handler(event, context):
    processed = 0
    for record in event.get('Records', []):
        sns = record.get('Sns', {})
        try:
            msg = json.loads(sns.get('Message', '{}'))
        except (TypeError, ValueError):
            continue

        tracking = msg.get('tracking_number')
        old = msg.get('old_status')
        new = msg.get('new_status')
        if not tracking or not new:
            continue

        # Re-fetch the email to handle the case where it was updated after
        # the SNS message was published.
        email = msg.get('customer_email')
        try:
            conn = _connect()
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(LOOKUP_SQL, (tracking,))
                    row = cur.fetchone()
                    if row and row[0]:
                        email = row[0]
            finally:
                conn.close()
        except psycopg2.Error as exc:
            print(f'db lookup failed for {tracking}: {exc}')

        if not email:
            continue

        subject = f'Shipment {tracking} is now {new}'
        body = (
            f'Hello,\n\n'
            f'Your shipment {tracking} has moved from {old} to {new}.\n\n'
            f'— FreightFlow'
        )
        try:
            _send_email(email, subject, body)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            print(f'SES send_email failed for {tracking}: {exc}')

    return {'processed': processed}
