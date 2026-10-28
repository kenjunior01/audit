from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
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


# ---------------------------------------------------------------------------
# Alertas BI ao vivo — avaliação automática (celery beat / cron clássico)
# ---------------------------------------------------------------------------

@shared_task
def run_bi_alerts():
    """Avalia todos os alertas BI ativos e notifica violações novas (transição
    ok→breach dispara notificação via Central de Notificações — ver
    evaluate_measure_alert). Agendável via celery beat
    (AUDIT_ALERTS_ENABLED=true), por cron clássico (`manage.py run_bi_alerts`)
    ou manualmente via POST /bi/alerts/run (auditor/admin)."""
    from .bi_views import evaluate_measure_alert
    from .models import MeasureAlert

    results = []
    for a in MeasureAlert.objects.filter(active=True):
        try:
            state, value, notified = evaluate_measure_alert(a)
            results.append({"id": a.id, "name": a.name, "state": state,
                            "value": value, "notified": notified})
        except Exception as e:  # um alerta malformado nunca derruba a ronda
            logger.warning("alerta BI %s falhou: %s", a.pk, e)
            results.append({"id": a.id, "name": a.name, "state": "error",
                            "value": None, "notified": False})
    breaches = sum(1 for r in results if r["state"] == "breach")
    return {"ok": True, "evaluated": len(results), "breaches": breaches,
            "results": results,
            "message": f"{len(results)} alerta(s) avaliado(s), "
                       f"{breaches} em violação"}


# ---------------------------------------------------------------------------
# Digest semanal de alertas BI (email + Central de Notificações + resumo LLM)
# ---------------------------------------------------------------------------

@shared_task
def send_alert_digest(days=7, send_email=True):
    """Digest semanal dos alertas BI (MeasureAlert): avalia tudo em fresco
    (run_bi_alerts), resume o estado (violências, erros, regras novas,
    top ofensores por contagem de violações) e entrega por dois canais:
    1) Central de Notificações (in-app) para admin/auditor — sempre;
    2) Email para AUDIT_DIGEST_EMAILS — best-effort, apenas se configurado.
    Quando um LLM está disponível (llm_client — EXAONE/Ollama/OpenAI-
    compatible), gera um resumo executivo em PT; caso contrário usa texto
    determinístico. Nunca derruba o fluxo: qualquer falha é logada.
    Invocável por celery beat (AUDIT_ALERT_DIGEST_ENABLED=true), por cron
    clássico (`manage.py send_alert_digest`) ou diretamente em testes."""
    from django.conf import settings as dj_settings
    from .models import MeasureAlert
    from .notifications_service import notify_role

    try:
        run_bi_alerts()  # avaliação fresca — estado consistente
    except Exception as e:  # pragma: no cover — digest segue com o último estado
        logger.warning("digest: avaliação prévia falhou (%s)", e)

    since = timezone.now() - timedelta(days=days)
    alerts = list(MeasureAlert.objects.all())
    stats = {
        "total": len(alerts),
        "ativos": sum(1 for a in alerts if a.active),
        "em_violacao": sum(1 for a in alerts if a.last_state == "breach"),
        "erro": sum(1 for a in alerts if a.last_state == "error"),
        "novos": sum(1 for a in alerts if a.created_at and a.created_at >= since),
        "periodo_dias": days,
    }
    top = sorted(alerts, key=lambda a: a.breach_count, reverse=True)
    top = [a for a in top if a.breach_count > 0][:10]

    linhas = []
    for a in top:
        estado = {"breach": "EM VIOLAÇÃO", "error": "erro",
                  "ok": "ok"}.get(a.last_state, a.last_state or "—")
        valor = f"{a.last_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") \
            if a.last_value is not None else "—"
        linhas.append(f"• {a.name} — {estado} | valor atual: {valor} | "
                      f"{a.breach_count} violação(ões) acumulada(s)")

    base = (f"Alertas BI — resumo dos últimos {days} dias:\n"
            f"• {stats['total']} regra(s), {stats['ativos']} ativa(s)\n"
            f"• {stats['em_violacao']} em violação, {stats['erro']} com erro\n"
            f"• {stats['novos']} regra(s) nova(s) no período")
    if linhas:
        base += "\nTop ofensores:\n" + "\n".join(linhas)
    if stats["total"] == 0:
        base += "\nSem regras de alerta definidas — crie-as no BI Studio."

    llm_used = False
    try:
        from . import llm_client
        if llm_client.is_available():
            prompt = (
                "Escreve um resumo executivo de 2 frases, em português de "
                f"Portugal, para o digest semanal de alertas de auditoria. "
                f"Dados: {json.dumps(stats, ensure_ascii=False)}. "
                "Sê direto e factual, sem saudação nem despedida.")
            resumo = (llm_client.generate(prompt, timeout=20, max_tokens=220)
                      or "").strip()
            if resumo:
                base = f"Resumo (IA):\n{resumo}\n\n" + base
                llm_used = True
    except Exception as e:  # LLM é opcional — nunca derruba o digest
        logger.warning("digest: resumo LLM falhou (%s)", e)

    dia = timezone.localdate().strftime("%d/%m/%Y")
    titulo = f"Digest semanal de alertas — {dia}"

    notificados = notify_role(
        roles=("admin", "auditor"), kind="bi.digest", title=titulo,
        body=base, route="/bi", severity=("critical" if stats["em_violacao"]
                                          else ("warn" if stats["erro"] else "info")),
        meta={"stats": stats, "llm": llm_used}, dedupe_minutes=0)
    notificados = len(notificados) if isinstance(notificados, list) else (1 if notificados else 0)

    recipients = list(getattr(dj_settings, "AUDIT_DIGEST_EMAILS", []) or [])
    status = "stored"
    if send_email and recipients:
        try:
            send_mail(
                subject=f"[Audit] {titulo}",
                message=base,
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False)
            status = "sent"
        except Exception as e:
            logger.warning("digest alertas email falhou: %s", e)
            status = "failed"

    try:
        ImmutableAuditLog.objects.create(
            actor_id="System_Alert_Digest",
            action_type=f"ALERT_DIGEST_{status.upper()}",
            resource_id=f"week-{timezone.localdate().isoformat()}",
            details={"stats": stats, "llm": llm_used,
                     "notificados_in_app": notificados,
                     "recipients": recipients if status == "sent" else []})
    except Exception as e:  # pragma: no cover
        logger.warning("digest alertas audit log falhou: %s", e)

    verb = {"sent": "email enviado", "stored": "armazenado (sem email — "
            "configure AUDIT_DIGEST_EMAILS)", "failed": "email falhou"}[status]
    return {"ok": status != "failed", "status": status, "stats": stats,
            "llm": llm_used, "message":
            f"Digest de alertas: {stats['em_violacao']} em violação, "
            f"{stats['erro']} com erro, {stats['novos']} novo(s) — "
            f"{notificados} notificação(ões) in-app, {verb}"}
