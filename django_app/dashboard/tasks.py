from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from .models import ImmutableAuditLog, WebhookEvent, ExternalSystem
import requests
import json

@shared_task
def send_audit_email_task(subject, message, recipients, resource_id=None):
    """
    Background task to send email and log the result to ImmutableAuditLog.
    """
    try:
        send_mail(
            subject,
            message,
            'audit-system@internal.com',
            recipients,
            fail_silently=False,
        )
        
        if resource_id:
            ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_EMAIL_SUCCESS',
                resource_id=str(resource_id),
                details={'recipient': recipients, 'subject': subject, 'status': 'sent'}
            )
        return f"Email sent to {recipients}"
    except Exception as e:
        if resource_id:
            ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_EMAIL_FAILED',
                resource_id=str(resource_id),
                details={'recipient': recipients, 'subject': subject, 'error': str(e)}
            )
        return f"Failed to send email: {e}"

@shared_task
def send_slack_alert_task(webhook_url, payload, resource_id=None):
    try:
        requests.post(webhook_url, json=payload, timeout=10)
        if resource_id:
             ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_SLACK_SUCCESS',
                resource_id=str(resource_id),
                details={'webhook': webhook_url, 'payload': payload}
            )
    except Exception as e:
         if resource_id:
             ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_SLACK_FAILED',
                resource_id=str(resource_id),
                details={'webhook': webhook_url, 'error': str(e)}
            )

@shared_task
def send_teams_alert_task(webhook_url, payload, resource_id=None):
    try:
        requests.post(webhook_url, json=payload, timeout=10)
        if resource_id:
             ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_TEAMS_SUCCESS',
                resource_id=str(resource_id),
                details={'webhook': webhook_url, 'payload': payload}
            )
    except Exception as e:
         if resource_id:
             ImmutableAuditLog.objects.create(
                actor_id='System_Celery_Worker',
                action_type='SEND_TEAMS_FAILED',
                resource_id=str(resource_id),
                details={'webhook': webhook_url, 'error': str(e)}
            )

@shared_task
def retry_failed_webhooks():
    """Retry webhooks that failed (max 5 retries)."""
    failed_webhooks = WebhookEvent.objects.filter(
        status='FAILED',
        attempt_count__lt=5
    ).order_by('created_at')

    for webhook in failed_webhooks:
        retry_webhook.delay(webhook.id)

    return f"Scheduled retry for {failed_webhooks.count()} webhooks"

@shared_task
def retry_webhook(webhook_id):
    """Retry a single failed webhook."""
    try:
        from .webhook_service import WebhookService
        WebhookService.retry_failed(webhook_id)
        return f"Retried webhook {webhook_id}"
    except Exception as e:
        return f"Failed to retry webhook {webhook_id}: {str(e)}"

@shared_task
def process_scheduled_ingestion():
    """Process scheduled ingestion for active external systems."""
    systems = ExternalSystem.objects.filter(
        is_active=True,
        ingest_enabled=True
    )

    for system in systems:
        if not system.last_ingest_at or (timezone.now() - system.last_ingest_at).total_seconds() >= system.ingest_interval:
            ingest_from_system.delay(system.id)

    return f"Scheduled ingestion for {systems.count()} systems"

@shared_task
def ingest_from_system(system_id):
    """Ingest data from a specific external system."""
    try:
        system = ExternalSystem.objects.get(id=system_id)
        system.last_ingest_at = timezone.now()
        system.save()

        # TODO: Implement actual ingestion logic based on system type
        # For now, log that ingestion was triggered
        ImmutableAuditLog.objects.create(
            actor_id='System_Celery_Worker',
            action_type='INGESTION_TRIGGERED',
            resource_id=str(system_id),
            details={'system_name': system.name, 'system_type': system.system_type}
        )

        return f"Ingestion triggered for system {system.name}"
    except ExternalSystem.DoesNotExist:
        return f"System {system_id} not found"
    except Exception as e:
        return f"Failed to ingest from system {system_id}: {str(e)}"
