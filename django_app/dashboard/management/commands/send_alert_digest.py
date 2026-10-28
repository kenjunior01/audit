"""
Digest semanal de alertas BI — para crontab clássico (sem celery).

Exemplo de crontab (toda segunda-feira às 08:00):
    0 8 * * 1 cd /app/django_app && python manage.py send_alert_digest

Resume o estado dos alertas BI (MeasureAlert): avaliação fresca, violações,
erros, regras novas e top ofensores. Entrega por Central de Notificações
(in-app, admin/auditor) e, se AUDIT_DIGEST_EMAILS estiver configurado, por
email. Quando há LLM disponível (llm_client — EXAONE/Ollama), acrescenta um
resumo executivo gerado por IA. Também agendável via celery beat
(AUDIT_ALERT_DIGEST_ENABLED=true).
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Gera o digest dos alertas BI (violações, erros, regras novas, "
            "top ofensores), notifica in-app (admin/auditor) e envia email "
            "se houver destinatários AUDIT_DIGEST_EMAILS.")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7,
                            help="Janela do digest em dias (default: 7)")
        parser.add_argument("--no-email", action="store_true",
                            help="Apenas notifica in-app, sem email")

    def handle(self, *args, **opts):
        from dashboard.tasks import send_alert_digest

        result = send_alert_digest(days=opts["days"],
                                   send_email=not opts["no_email"])
        style = self.style.SUCCESS if result.get("ok") else self.style.WARNING
        self.stdout.write(style(result.get("message", "")))
