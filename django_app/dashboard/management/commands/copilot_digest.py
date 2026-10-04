"""
Digest programado do Copiloto Global — para crontab clássico (sem celery).

Exemplo de crontab (todos os dias às 07:00):
    0 7 * * * cd /app/django_app && python manage.py copilot_digest

O email é enviado apenas se AUDIT_DIGEST_EMAILS estiver configurado;
use --no-email para gerar apenas o registo (visível no frontend).
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Gera o digest programado do Copiloto Global (briefing + sinais "
            "proativos + qualidade do suporte) e envia por email se houver "
            "destinatários AUDIT_DIGEST_EMAILS configurados.")

    def add_arguments(self, parser):
        parser.add_argument("--period", default="daily",
                            choices=["daily", "weekly"],
                            help="Período do digest (default: daily)")
        parser.add_argument("--no-email", action="store_true",
                            help="Apenas gera/persiste o digest, sem email")

    def handle(self, *args, **opts):
        from dashboard.tasks import send_copilot_digest

        result = send_copilot_digest(period=opts["period"],
                                     send_email=not opts["no_email"])
        style = self.style.SUCCESS if result.get("ok") else self.style.WARNING
        self.stdout.write(style(result.get("message", "")))
