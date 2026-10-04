"""
Testes do Copiloto Global v6 — PDF executivo do digest.

Cobre:
- build_digest_pdf(): bytes %PDF válidos, com e sem sinais/feedback
- anexo PDF no email do digest (locmem backend)
- GET /ai/copilot/digest/pdf: digest guardado, DB vazia (gera na hora),
  filtro period, auth
"""
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from dashboard.models import ApiToken, CopilotDigest
from dashboard import copilot_service as cs
from dashboard.tasks import send_copilot_digest

from .test_copilot import _alert, _case


class DigestPdfServiceTest(TestCase):
    def _digest(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        _case("Caso tardio", deadline_days=-2)
        return cs.build_digest("daily")

    def test_pdf_valid_bytes(self):
        pdf = cs.build_digest_pdf(self._digest())
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1500)

    def test_pdf_empty_digest(self):
        pdf = cs.build_digest_pdf(cs.build_digest("weekly"))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)


@override_settings(
    AUDIT_DIGEST_EMAILS=["gestor@x.com"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DigestEmailAttachmentTest(TestCase):
    def test_email_has_pdf_attachment(self):
        result = send_copilot_digest("daily", send_email=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(len(msg.attachments), 1)
        fname, content, ctype = msg.attachments[0]
        self.assertTrue(fname.startswith("digest-daily-"))
        self.assertTrue(fname.endswith(".pdf"))
        self.assertEqual(ctype, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF"))


class DigestPdfRESTTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = "tok-pdf-1"
        ApiToken.objects.create(token=self.token, user_id="pdf_admin",
                                role="admin")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)

    def test_pdf_from_stored_digest(self):
        send_copilot_digest("daily", send_email=False)
        resp = self.client.get("/django/api/ai/copilot/digest/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("digest-daily-", resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_empty_db_builds_fresh(self):
        self.assertEqual(CopilotDigest.objects.count(), 0)
        resp = self.client.get("/django/api/ai/copilot/digest/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        # não persistiu — continua vazio
        self.assertEqual(CopilotDigest.objects.count(), 0)

    def test_pdf_filter_period(self):
        send_copilot_digest("weekly", send_email=False)
        resp = self.client.get("/django/api/ai/copilot/digest/pdf?period=weekly")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("digest-weekly-", resp["Content-Disposition"])

    def test_pdf_requires_auth(self):
        client = APIClient()
        resp = client.get("/django/api/ai/copilot/digest/pdf")
        self.assertIn(resp.status_code, [401, 403])
