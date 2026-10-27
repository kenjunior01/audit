"""
Alertas BI ao vivo — para crontab clássico (sem celery worker).

Exemplo de crontab (de hora a hora):
    0 * * * * cd /app/django_app && python manage.py run_bi_alerts

Avalia todos os alertas BI ativos (MeasureAlert) e notifica violações novas
(transição ok→breach) via Central de Notificações. A mesma ronda pode correr
via celery beat (AUDIT_ALERTS_ENABLED=true) ou manualmente em
BI Studio › Alertas › Avaliar (POST /bi/alerts/run).
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Avalia todos os alertas BI ativos e notifica violações novas "
            "(transição ok→breach) via Central de Notificações.")

    def handle(self, *args, **opts):
        from dashboard.tasks import run_bi_alerts

        result = run_bi_alerts()
        style = self.style.SUCCESS if result.get("ok") else self.style.WARNING
        self.stdout.write(style(result.get("message", "")))
