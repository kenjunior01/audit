"""Testes do Digest semanal de alertas BI (task send_alert_digest + comando)."""
import uuid

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from dashboard.models import ApiToken, MeasureAlert, Notification, Transaction
from dashboard.tasks import send_alert_digest

MEAS = {'op': 'agg', 'agg': 'sum', 'field': 'amount'}


def _mk(vendor, amount):
    return Transaction.objects.create(
        transaction_id=f"DG-{uuid.uuid4().hex[:10]}", vendor=vendor,
        amount=amount, currency="BRL", timestamp=timezone.now(),
        category="Compras", status="Completed", user_id="u1")


class AlertDigestTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("AlA", 100)
        _mk("AlB", 900)
        ApiToken.objects.create(token="tk-admin-digest",
                                user_id="admin@x.pt", role="admin")
        ApiToken.objects.create(token="tk-viewer-digest",
                                user_id="viewer@x.pt", role="viewer")
        # regra que viola (soma 1000 > 500)
        MeasureAlert.objects.create(
            name=f"dig-breach-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=500, created_by="admin@x.pt")
        # regra ok (soma 1000 < 5000)
        MeasureAlert.objects.create(
            name=f"dig-ok-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=5000, created_by="admin@x.pt")

    def test_digest_stats_notificacao_in_app(self):
        out = send_alert_digest()
        self.assertTrue(out["ok"])
        self.assertEqual(out["stats"]["total"], 2)
        self.assertEqual(out["stats"]["em_violacao"], 1)
        self.assertEqual(out["stats"]["novos"], 2)
        self.assertFalse(out["llm"])  # sem LLM no ambiente de teste
        n = Notification.objects.filter(
            kind='bi.digest', recipient="admin@x.pt").latest("id")
        self.assertIn("Digest semanal de alertas", n.title)
        self.assertIn("EM VIOLAÇÃO", n.body)
        self.assertIn("violação(ões) acumulada(s)", n.body)
        self.assertEqual(n.severity, "critical")
        self.assertEqual(n.route, "/bi")
        # viewer não recebe — digest é para admin/auditor
        self.assertFalse(Notification.objects.filter(
            kind='bi.digest', recipient="viewer@x.pt").exists())

    def test_digest_sem_email_fica_stored(self):
        out = send_alert_digest()
        self.assertEqual(out["status"], "stored")
        self.assertIn("configure AUDIT_DIGEST_EMAILS", out["message"])

    @override_settings(AUDIT_DIGEST_EMAILS=["fin@x.pt"],
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_digest_email_enviado(self):
        out = send_alert_digest()
        self.assertEqual(out["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[Audit] Digest semanal de alertas",
                      mail.outbox[0].subject)
        self.assertIn("EM VIOLAÇÃO", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["fin@x.pt"])

    def test_runs_sucessivos_notificam_cada_vez(self):
        send_alert_digest()
        c1 = Notification.objects.filter(kind='bi.digest').count()
        self.assertGreaterEqual(c1, 1)
        send_alert_digest()
        c2 = Notification.objects.filter(kind='bi.digest').count()
        self.assertGreater(c2, c1)  # dedupe desligado no digest (dedupe_minutes=0)

    def test_comando_management(self):
        from io import StringIO
        buf = StringIO()
        call_command("send_alert_digest", "--no-email", stdout=buf)
        self.assertIn("Digest de alertas", buf.getvalue())
        self.assertIn("notificação(ões) in-app", buf.getvalue())

    def test_digest_sem_regras(self):
        MeasureAlert.objects.all().delete()
        out = send_alert_digest()
        self.assertTrue(out["ok"])
        self.assertEqual(out["stats"]["total"], 0)
        self.assertEqual(out["stats"]["em_violacao"], 0)
        n = Notification.objects.filter(kind='bi.digest').latest("id")
        self.assertIn("Sem regras de alerta definidas", n.body)
