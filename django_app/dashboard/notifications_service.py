"""Central de Notificações — serviço resiliente de eventos in-app.

Princípios:
- Nunca derruba o fluxo principal: qualquer falha ao notificar é engolida
  com log (notificação é um efeito colateral, não uma etapa crítica).
- Deduplicação opcional por (recipient, kind, título) dentro de uma janela
  de minutos — evita spam quando o mesmo evento dispara várias vezes.
- recipient segue a convenção da plataforma: string user_id (email).
"""
import logging
from datetime import timedelta

from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)

# janela de dedupe por defeito (minutos); 0 desativa
DEDUPE_MINUTES = 10


def notify_user(recipient, kind, title, body='', route='',
                severity='info', meta=None, dedupe_minutes=DEDUPE_MINUTES):
    """Cria uma notificação para um utilizador. Retorna Notification|None."""
    if not recipient:
        return None
    try:
        if dedupe_minutes and dedupe_minutes > 0:
            window = timezone.now() - timedelta(minutes=dedupe_minutes)
            if Notification.objects.filter(
                recipient=recipient, kind=kind, title=title,
                created_at__gte=window,
            ).exists():
                return None
        return Notification.objects.create(
            recipient=recipient, kind=kind, title=title[:220],
            body=body or '', route=route or '', severity=severity,
            meta=meta,
        )
    except Exception:  # pragma: no cover — resiliência acima de tudo
        logger.warning("notify_user falhou (recipient=%s kind=%s)", recipient, kind, exc_info=True)
        return None


def _recipient_user_ids():
    """user_ids distintos que já emitiram tokens (utilizadores ativos)."""
    from .models import ApiToken
    return list(
        ApiToken.objects.exclude(user_id='').values_list('user_id', flat=True).distinct()
    )


def notify_role(roles=('admin',), kind='system', title='', body='', route='',
                severity='info', meta=None, dedupe_minutes=DEDUPE_MINUTES):
    """Notifica todos os utilizadores que possuem token com qualquer um dos roles."""
    from .models import ApiToken
    try:
        qs = ApiToken.objects.filter(role__in=roles).exclude(user_id='').order_by()
        recipients = list(qs.values_list('user_id', flat=True).distinct())
    except Exception:
        logger.warning("notify_role: falha ao listar recipients", exc_info=True)
        return []
    out = []
    for r in recipients:
        n = notify_user(r, kind, title, body=body, route=route,
                        severity=severity, meta=meta, dedupe_minutes=dedupe_minutes)
        if n:
            out.append(n)
    return out


def notify_staff(kind, title, body='', route='', severity='info', meta=None,
                 dedupe_minutes=DEDUPE_MINUTES):
    """Atalho: admins + auditores (eventos de risco interessam a ambos)."""
    return notify_role(roles=('admin', 'auditor'), kind=kind, title=title,
                       body=body, route=route, severity=severity, meta=meta,
                       dedupe_minutes=dedupe_minutes)


def notify_alert(alert, created_by=None):
    """Notifica staff sobre um alerta relevante (critical/high)."""
    sev = (getattr(alert, 'severity', '') or '').lower()
    if sev not in ('critical', 'high'):
        return []
    label = 'CRÍTICO' if sev == 'critical' else 'alto'
    title = f"Alerta {label}: {getattr(alert, 'type', None) or getattr(alert, 'alert_type', 'risco detetado')}"
    body = f"Severidade {sev}. {getattr(alert, 'description', '') or ''}".strip()[:500]
    meta = {'alert_id': getattr(alert, 'id', None)}
    return notify_staff(kind='alert.created', title=title[:220], body=body,
                        route='/alerts', severity=('critical' if sev == 'critical' else 'warn'),
                        meta=meta)


def notify_case_status(case, old_status, new_status, actor=''):
    """Notifica staff sobre transição de estado de um caso."""
    if (old_status or '') == (new_status or ''):
        return []
    title = f"Caso #{case.pk} → {new_status}"
    body = (f"Estado do caso '{case.title}' mudou de {old_status or '—'} para {new_status}."
            + (f" Por {actor}." if actor else ''))[:500]
    return notify_staff(kind='case.status', title=title, body=body, route=f'/cases',
                        severity='info', meta={'case_id': case.pk, 'from': old_status, 'to': new_status})


def unread_count(recipient):
    try:
        return Notification.objects.filter(recipient=recipient, read_at__isnull=True).count()
    except Exception:
        return 0
