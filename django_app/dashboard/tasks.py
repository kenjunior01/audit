from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from .models import ImmutableAuditLog, WebhookEvent, ExternalSystem
import requests
import json
import logging

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Digest programado do Copiloto Global (cron push)
# ---------------------------------------------------------------------------

@shared_task
def send_copilot_digest(period="daily", send_email=True):
    """Gera o digest programado (briefing + sinais proativos + qualidade do
    copiloto), persiste um registo por (periodo, dia) e envia por email aos
    destinatários AUDIT_DIGEST_EMAILS (best-effort — o email nunca derruba
    o digest; com o backend console apenas regista no log do servidor).
    Pode ser invocado por celery beat (AUDIT_DIGEST_ENABLED=true), pelo
    management command `manage.py copilot_digest` (cron clássico) ou
    manualmente via POST /ai/copilot/digest (admin)."""
    from django.conf import settings as dj_settings
    from . import copilot_service as cs
    from .models import CopilotDigest

    period = period if period in ("daily", "weekly") else "daily"
    try:
        digest = cs.build_digest(period)
    except Exception as e:
        logger.warning("digest build falhou: %s", e)
        return {"ok": False, "message": f"Digest falhou: {e}"}

    recipients = list(getattr(dj_settings, "AUDIT_DIGEST_EMAILS", []) or [])
    status = "stored"
    if send_email and recipients:
        attachments = []
        try:
            attachments.append((
                f"digest-{period}-{timezone.localdate()}.pdf",
                cs.build_digest_pdf(digest),
                "application/pdf"))
        except Exception as e:
            logger.warning("digest pdf falhou (email segue sem anexo): %s", e)
        try:
            # EmailMultiAlternatives (e não send_mail): texto simples +
            # alternativa HTML premium + anexo PDF
            from django.core.mail import EmailMultiAlternatives
            email = EmailMultiAlternatives(
                subject=f"[Audit] Resumo {period} — {digest['headline'][:80]}",
                body=cs.digest_email_body(digest),
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                to=recipients,
                attachments=attachments or None,
            )
            try:
                email.attach_alternative(cs.digest_email_html(digest),
                                         "text/html")
            except Exception as e:
                logger.warning("digest html falhou (email segue texto "
                               "simples): %s", e)
            email.send(fail_silently=False)
            status = "sent"
        except Exception as e:
            logger.warning("digest email falhou: %s", e)
            status = "failed"

    row, _created = CopilotDigest.objects.update_or_create(
        period=period, day=timezone.localdate(),
        defaults={
            "payload": digest,
            "signals_count": digest.get("signals_count", 0),
            "critical_count": digest.get("critical_count", 0),
            "avg_rating": digest.get("feedback", {}).get("avg_rating"),
            "recipients": ", ".join(recipients) if status == "sent" else "",
            "status": status,
        })

    try:
        ImmutableAuditLog.objects.create(
            actor_id="System_Copilot_Digest",
            action_type=f"DIGEST_{status.upper()}",
            resource_id=str(row.id),
            details={"period": period, "signals": digest.get("signals_count", 0),
                     "critical": digest.get("critical_count", 0),
                     "recipients": recipients if status == "sent" else []},
        )
    except Exception as e:
        logger.warning("digest audit log falhou: %s", e)

    verb = {"sent": "enviado para", "stored": "armazenado (sem email — "
            "configure AUDIT_DIGEST_EMAILS)", "failed": "gerado mas o envio "
            "de email falhou"}[status]
    return {"ok": status != "failed", "status": status, "id": row.id,
            "digest": digest,
            "message": f"Digest {period} {verb} "
                       f"{len(recipients) if status == 'sent' else 0} destinatário(s)"}
