"""
Testes do Copiloto Global v5 — digest programado (cron push).

Cobre:
- build_digest(): composição briefing + sinais proativos + qualidade
- digest_email_body(): corpo de email em texto simples
- task send_copilot_digest: persistência, dedupe (period, dia), email
  best-effort (locmem backend), log de auditoria, falha controlada
- management command copilot_digest
- REST: GET /ai/copilot/digest (auth, digest null vazio, filtro period)
        POST /ai/copilot/digest (admin-only, period inválido)
"""
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import (ApiToken, CopilotDigest, ImmutableAuditLog)
from dashboard import copilot_service as cs
from dashboard.tasks import send_copilot_digest

from .test_copilot import _alert, _case, _tx


class DigestServiceTest(TestCase):
    def test_empty_db_shape(self):
        out = cs.build_digest("daily")
        self.assertEqual(out["period"], "daily")
        self.assertEqual(out["signals"], [])
        self.assertEqual(out["signals_count"], 0)
        self.assertIn("0 alertas abertos", out["headline"])
        self.assertEqual(out["feedback"]["total"], 0)
        self.assertIsNone(out["feedback"]["avg_rating"])
        self.assertIn("generated_at", out)

    def test_composition_with_data(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        _case("Caso tardio", deadline_days=-2)
        out = cs.build_digest("daily")
        self.assertGreaterEqual(out["signals_count"], 1)
        self.assertGreaterEqual(out["critical_count"], 1)
        self.assertIn("1 casos fora do prazo", out["headline"])
        self.assertTrue(out["insights"])
        self.assertTrue(out["narrative"])

    def test_headline_includes_rating_when_feedback_exists(self):
        from dashboard.models import CopilotFeedback
        CopilotFeedback.objects.create(rating=4, question="x", mode="rules")
        out = cs.build_digest("weekly")
        self.assertEqual(out["period"], "weekly")
        self.assertIn("4.0/5", out["headline"])

    def test_email_body_contains_key_sections(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        body = cs.digest_email_body(cs.build_digest("daily"))
        self.assertIn("Resumo daily", body)
        self.assertIn("[CRÍTICO]", body)
        self.assertIn("Ação:", body)
        self.assertIn("Copiloto Global", body)


@override_settings(AUDIT_DIGEST_EMAILS=[])
class DigestTaskTest(TestCase):
    def test_creates_row_stored(self):
        result = send_copilot_digest("daily", send_email=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "stored")
        row = CopilotDigest.objects.get(id=result["id"])
        self.assertEqual(row.period, "daily")
        self.assertEqual(row.status, "stored")
        self.assertEqual(row.recipients, "")
        self.assertEqual(row.payload["period"], "daily")
        self.assertEqual(row.signals_count, row.payload["signals_count"])

    def test_dedupe_same_period_day(self):
        send_copilot_digest("daily", send_email=False)
        send_copilot_digest("daily", send_email=False)
        self.assertEqual(CopilotDigest.objects.count(), 1)

    def test_weekly_is_separate_row(self):
        send_copilot_digest("daily", send_email=False)
        send_copilot_digest("weekly", send_email=False)
        self.assertEqual(CopilotDigest.objects.count(), 2)

    def test_invalid_period_falls_back_to_daily(self):
        result = send_copilot_digest("mensal", send_email=False)
        row = CopilotDigest.objects.get(id=result["id"])
        self.assertEqual(row.period, "daily")

    @override_settings(
        AUDIT_DIGEST_EMAILS=["gestor@x.com", "cfo@y.com"],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_sent_and_audited(self):
        result = send_copilot_digest("daily", send_email=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Resumo daily", msg.subject)
        self.assertEqual(msg.to, ["gestor@x.com", "cfo@y.com"])
        self.assertIn("Plataforma de Auditoria", msg.body)
        row = CopilotDigest.objects.get(id=result["id"])
        self.assertEqual(row.status, "sent")
        self.assertIn("gestor@x.com", row.recipients)
        self.assertTrue(ImmutableAuditLog.objects.filter(
            action_type="DIGEST_SENT", resource_id=str(row.id)).exists())

    @override_settings(
        AUDIT_DIGEST_EMAILS=["gestor@x.com"],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_no_email_flag_stores_without_sending(self):
        result = send_copilot_digest("daily", send_email=False)
        self.assertEqual(result["status"], "stored")
        self.assertEqual(len(mail.outbox), 0)

    def test_build_failure_returns_error_without_row(self):
        with patch.object(cs, "build_digest",
                          side_effect=RuntimeError("boom")):
            result = send_copilot_digest("daily", send_email=False)
        self.assertFalse(result["ok"])
        self.assertIn("boom", result["message"])
        self.assertEqual(CopilotDigest.objects.count(), 0)


class DigestCommandTest(TestCase):
    def test_command_creates_digest(self):
        from io import StringIO
        out = StringIO()
        call_command("copilot_digest", "--no-email", stdout=out)
        self.assertIn("Digest daily", out.getvalue())
        self.assertEqual(CopilotDigest.objects.filter(period="daily").count(), 1)

    def test_command_weekly(self):
        call_command("copilot_digest", "--period", "weekly", "--no-email")
        self.assertTrue(CopilotDigest.objects.filter(period="weekly").exists())


class DigestRESTTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_token = "tok-digest-admin"
        ApiToken.objects.create(token=self.admin_token,
                                user_id="admin_dg", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_token)

    def test_get_empty_returns_null(self):
        resp = self.client.get("/django/api/ai/copilot/digest")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["digest"])

    def test_get_returns_latest_with_payload(self):
        send_copilot_digest("daily", send_email=False)
        resp = self.client.get("/django/api/ai/copilot/digest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["digest"]
        self.assertEqual(data["period"], "daily")
        self.assertEqual(data["status"], "stored")
        self.assertIn("headline", data["payload"])
        self.assertIn("signals", data["payload"])

    def test_get_filter_period(self):
        send_copilot_digest("daily", send_email=False)
        send_copilot_digest("weekly", send_email=False)
        resp = self.client.get("/django/api/ai/copilot/digest?period=weekly")
        self.assertEqual(resp.json()["digest"]["period"], "weekly")

    def test_get_requires_auth(self):
        client = APIClient()
        resp = client.get("/django/api/ai/copilot/digest")
        self.assertIn(resp.status_code, [401, 403])

    def test_post_generates_now(self):
        resp = self.client.post("/django/api/ai/copilot/digest",
                                {"period": "daily"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(CopilotDigest.objects.count(), 1)

    def test_post_invalid_period_400(self):
        resp = self.client.post("/django/api/ai/copilot/digest",
                                {"period": "mensal"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_post_viewer_403(self):
        viewer = "tok-digest-viewer"
        ApiToken.objects.create(token=viewer, user_id="viewer_dg",
                                role="viewer")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + viewer)
        resp = client.post("/django/api/ai/copilot/digest", {},
                           format="json")
        self.assertEqual(resp.status_code, 403)

    def test_post_requires_auth(self):
        client = APIClient()
        resp = client.post("/django/api/ai/copilot/digest", {},
                           format="json")
        self.assertIn(resp.status_code, [401, 403])
