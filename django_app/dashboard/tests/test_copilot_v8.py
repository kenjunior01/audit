"""
Testes do Copiloto Global v8 — email HTML premium do digest.

Cobre:
- digest_email_html(): secções essenciais, badges de sinal, escapa HTML
  injectado nos dados, funciona com digest vazio
- envio do email: alternativa text/html presente + anexo PDF intacto
- GET /ai/copilot/digest/email/preview: stored payload, geração na hora
  (sem persistir), content-type e auth
"""
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from dashboard.models import ApiToken, CopilotDigest
from dashboard import copilot_service as cs
from dashboard.tasks import send_copilot_digest

from .test_copilot import _alert, _case


class DigestHtmlServiceTest(TestCase):
    def _digest(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        _case("Caso tardio", deadline_days=-2)
        return cs.build_digest("daily")

    def test_html_contains_core_sections(self):
        html = cs.digest_email_html(self._digest())
        self.assertIn("Resumo Diário", html)
        self.assertIn("Indicadores-chave", html)
        self.assertIn("Sinais que precisam de atenção", html)
        self.assertIn("Insights do Copiloto", html)
        self.assertIn("Gerado automaticamente pelo Copiloto Global", html)
        # badge crítico presente (o alerta é Critical)
        self.assertIn("CRÍTICO", html)
        # estrutura table-based compatível com clientes de email
        self.assertIn('role="presentation"', html)

    def test_html_escapes_injected_markup(self):
        digest = {
            "period": "daily",
            "headline": "Headline <b>injetada</b>",
            "kpis": {},
            "insights": [{"title": "<img src=x onerror=ev()>", "detail": "d"}],
            "signals": [{"level": "critical",
                         "title": "<script>alert(1)</script>",
                         "detail": "Fornecedor A & B",
                         "action": {"label": "Ver <caso>", "href": "/cases"}}],
            "feedback": None,
            "generated_at": "2026-01-01T10:00:00+00:00",
        }
        html = cs.digest_email_html(digest)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;injetada&lt;/b&gt;", html)
        self.assertIn("Fornecedor A &amp; B", html)
        self.assertIn("Ver &lt;caso&gt;", html)

    def test_html_empty_digest_still_valid(self):
        html = cs.digest_email_html(cs.build_digest("weekly"))
        self.assertIn("Resumo Semanal", html)
        self.assertIn("Sem sinais relevantes neste período", html)
        self.assertGreater(len(html), 1500)


@override_settings(
    AUDIT_DIGEST_EMAILS=["gestor@x.com"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DigestHtmlEmailTest(TestCase):
    def test_email_has_html_alternative_and_pdf(self):
        result = send_copilot_digest("daily", send_email=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        # alternativa HTML presente
        alts = [c for c, t in (msg.alternatives or []) if t == "text/html"]
        self.assertEqual(len(alts), 1)
        self.assertIn("Indicadores-chave", alts[0])
        # corpo texto simples mantém-se
        self.assertIn("Resumo daily", msg.body)
        # anexo PDF intacto
        self.assertEqual(len(msg.attachments), 1)
        self.assertEqual(msg.attachments[0][2], "application/pdf")

    def test_email_without_html_still_plain(self):
        """Se a geração do HTML falhar, o email segue em texto simples
        (best-effort) e o status mantém-se 'sent'."""
        from unittest.mock import patch
        with patch("dashboard.copilot_service.digest_email_html",
                   side_effect=RuntimeError("boom")):
            result = send_copilot_digest("daily", send_email=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].alternatives or [], [])


class DigestEmailPreviewRESTTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = "tok-html-1"
        ApiToken.objects.create(token=self.token, user_id="html_admin",
                                role="admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_preview_from_stored_payload(self):
        CopilotDigest.objects.create(
            period="daily", day=tz.localdate(),
            payload={"period": "daily", "headline": "GUARDADO-MARCADOR",
                     "kpis": {}, "signals": [], "insights": [],
                     "generated_at": "2026-01-01T10:00:00+00:00"})
        r = self.client.get("/django/api/ai/copilot/digest/email/preview")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r["Content-Type"])
        self.assertIn("GUARDADO-MARCADOR", r.content.decode("utf-8"))

    def test_preview_empty_db_generates_without_persisting(self):
        base = CopilotDigest.objects.count()
        r = self.client.get("/django/api/ai/copilot/digest/email/preview")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Resumo Diário", r.content.decode("utf-8"))
        self.assertEqual(CopilotDigest.objects.count(), base)

    def test_preview_period_filter_and_auth(self):
        CopilotDigest.objects.create(
            period="weekly", day=tz.localdate(),
            payload={"period": "weekly", "headline": "SEMANAL-MARCADOR",
                     "kpis": {}, "signals": [], "insights": [],
                     "generated_at": "2026-01-01T10:00:00+00:00"})
        r = self.client.get(
            "/django/api/ai/copilot/digest/email/preview?period=weekly")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SEMANAL-MARCADOR", r.content.decode("utf-8"))
        # sem token → bloqueado
        anon = APIClient()
        ra = anon.get("/django/api/ai/copilot/digest/email/preview")
        self.assertIn(ra.status_code, (401, 403))
