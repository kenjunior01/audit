"""
Testes do Copiloto Global v4 — sinais proativos e qualidade (feedback).

Cobre:
- build_proactive_signals(): alertas críticos, casos fora do prazo,
  Benford, duplicados, previsão, importações falhadas, meta-sinal de
  qualidade — com prioridade critical > warning > info e question pronta
- GET /ai/copilot/insights (REST, auth)
- GET /ai/copilot/feedback/stats (REST, apenas admin): média, distribuição,
  por modo, por página, perguntas mal avaliadas
"""
import json

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from dashboard.models import ApiToken, CopilotFeedback, ExcelImportJob
from dashboard import copilot_service as cs

from .test_copilot import _alert, _case, _tx


class ProactiveSignalsTest(TestCase):
    def test_empty_db_no_critical_signals(self):
        out = cs.build_proactive_signals()
        self.assertEqual(out["count"], 0)
        self.assertEqual(out["signals"], [])

    def test_critical_alerts_signal(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        out = cs.build_proactive_signals()
        titles = [s["title"] for s in out["signals"]]
        self.assertTrue(any("críticos por resolver" in t for t in titles))
        sig = out["signals"][0]
        self.assertEqual(sig["level"], "critical")
        self.assertIn("question", sig)
        self.assertEqual(sig["action"]["href"], "/alerts")

    def test_resolved_alerts_do_not_signal(self):
        _alert("Alpha", 9000.0, severity="Critical", status="Resolved")
        _alert("Beta", 8000.0, severity="Critical", status="False Positive")
        out = cs.build_proactive_signals()
        self.assertFalse(any("críticos por resolver" in s["title"]
                             for s in out["signals"]))

    def test_overdue_case_signal(self):
        _case("Caso tardio", deadline_days=-3)  # prazo no passado
        out = cs.build_proactive_signals()
        self.assertTrue(any("fora do prazo" in s["title"]
                            for s in out["signals"]))
        self.assertEqual(out["signals"][0]["level"], "critical")

    def test_failed_import_signal(self):
        ExcelImportJob.objects.create(file_name="f.xlsx", status="Failed",
                                      rows_imported=0)
        out = cs.build_proactive_signals()
        self.assertTrue(any("importações de Excel falhadas" in s["title"]
                            for s in out["signals"]))
        self.assertEqual(out["signals"][0]["level"], "info")

    def test_priority_ordering(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        _case("Caso tardio", deadline_days=-1)
        ExcelImportJob.objects.create(file_name="f.xlsx", status="Failed")
        out = cs.build_proactive_signals()
        levels = [s["level"] for s in out["signals"]]
        self.assertEqual(levels[0], "critical")
        self.assertEqual(levels[-1], "info")
        self.assertEqual(out["count"], len(out["signals"]))

    def test_every_signal_has_question_and_action(self):
        _alert("Alpha", 9000.0, severity="Critical", status="New")
        _case("Caso tardio", deadline_days=-1)
        out = cs.build_proactive_signals()
        for s in out["signals"]:
            self.assertIn("level", s)
            self.assertIn("title", s)
            self.assertIn("detail", s)
            self.assertTrue(s["question"])
            self.assertTrue(s["action"]["href"].startswith("/"))


class CopilotInsightsRESTTest(TestCase):
    def setUp(self):
        self.token = "tok-ins-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        _alert("Alpha", 9000.0, severity="Critical", status="New")

    def test_insights_endpoint(self):
        resp = self.client.get("/django/api/ai/copilot/insights")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("signals", data)
        self.assertIn("count", data)
        self.assertGreaterEqual(data["count"], 1)

    def test_insights_requires_auth(self):
        client = APIClient()
        resp = client.get("/django/api/ai/copilot/insights")
        self.assertIn(resp.status_code, [401, 403])


class FeedbackStatsRESTTest(TestCase):
    def setUp(self):
        self.token = "tok-stats-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)

    def _post(self, rating, **kw):
        payload = {"rating": rating}
        payload.update(kw)
        return self.client.post("/django/api/ai/copilot/feedback", payload,
                                format="json")

    def test_empty_stats(self):
        resp = self.client.get("/django/api/ai/copilot/feedback/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)

    def test_stats_after_feedback(self):
        self._post(5, question="resumo", mode="rules", page="/alerts")
        self._post(4, question="casos", mode="llm", page="/cases")
        self._post(1, question="previsão", mode="rules", page="/")
        resp = self.client.get("/django/api/ai/copilot/feedback/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 3)
        self.assertAlmostEqual(data["avg_rating"], 3.33, places=1)
        self.assertEqual(data["distribution"]["5"], 1)
        self.assertEqual(data["distribution"]["1"], 1)
        self.assertEqual(data["by_mode"]["llm"]["n"], 1)
        self.assertEqual(data["by_mode"]["rules"]["n"], 2)
        pages = {p["page"]: p["n"] for p in data["by_page"]}
        self.assertEqual(pages.get("/alerts"), 1)
        self.assertEqual(len(data["recent_low"]), 1)
        self.assertEqual(data["recent_low"][0]["rating"], 1)
        self.assertIn("previsão", data["recent_low"][0]["question"])

    def test_stats_admin_only(self):
        viewer_token = "tok-view-stats"
        ApiToken.objects.create(token=viewer_token, user_id="test_viewer",
                                role="viewer")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + viewer_token)
        resp = client.get("/django/api/ai/copilot/feedback/stats")
        self.assertEqual(resp.status_code, 403)

    def test_stats_requires_auth(self):
        client = APIClient()
        resp = client.get("/django/api/ai/copilot/feedback/stats")
        self.assertIn(resp.status_code, [401, 403])


class LowRatingMetaSignalTest(TestCase):
    def test_meta_signal_when_quality_drops(self):
        for r in (1, 1, 2, 2, 1):
            CopilotFeedback.objects.create(rating=r)
        out = cs.build_proactive_signals()
        self.assertTrue(any("Avaliação do copiloto" in s["title"]
                            for s in out["signals"]))

    def test_no_meta_signal_with_few_ratings(self):
        CopilotFeedback.objects.create(rating=1)
        out = cs.build_proactive_signals()
        self.assertFalse(any("Avaliação do copiloto" in s["title"]
                             for s in out["signals"]))
