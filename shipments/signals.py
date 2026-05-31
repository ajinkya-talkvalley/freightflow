"""
Signals for the shipments app.

A Shipment status change publishes the Schema Spec §6.4 message to SNS if
SNS_STATUS_TOPIC_ARN is set. Silent no-op when unset (local dev).
"""
import json
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Shipment

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Shipment)
def _stash_old_status(sender, instance, **kwargs):
    """Capture the prior status so post_save can compare."""
    if instance.pk:
        instance._old_status = (
            Shipment.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        )
    else:
        instance._old_status = None


@receiver(post_save, sender=Shipment)
def _publish_status_change(sender, instance, created, **kwargs):
    """Publish §6.4 SNS message when status actually changes."""
    arn = settings.SNS_STATUS_TOPIC_ARN
    if not arn:
        return  # silent no-op when not configured
    old_status = getattr(instance, '_old_status', None)
    if created or old_status is None or old_status == instance.status:
        return

    message = {
        'tracking_number': instance.tracking_number,
        'old_status': old_status,
        'new_status': instance.status,
        'customer_email': instance.customer_email,
    }
    try:
        boto3.client('sns', region_name=settings.AWS_REGION).publish(
            TopicArn=arn,
            Message=json.dumps(message),
            Subject=f'Shipment {instance.tracking_number} status changed',
        )
    except (BotoCoreError, ClientError):
        logger.exception('SNS publish failed for %s', instance.tracking_number)
