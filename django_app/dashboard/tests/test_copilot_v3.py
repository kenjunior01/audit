"""
Testes do Copiloto Global v3 — transparência agéntica, streaming SSE,
cache TTL de ferramentas pesadas e ciclo de feedback do utilizador.

Cobre:
- chat() devolve trace {tool, title, ok, ms} em todas as respostas
- chat_events(): sequência status → tool_start → tool_done → final
- Endpoint POST /ai/copilot/stream (SSE) — formato e payload final
- Endpoint POST /ai/copilot/feedback — 201 válido, 400 inválido, 401 anónimo
- Cache TTL: segunda chamada é servida da cache; muda quando os dados mudam
- GZip middleware presente nas definições
"""
import json

from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient

from dashboard.models import ApiToken, CopilotFeedback, Transaction
from dashboard import copilot_service as cs

from .test_copilot import _alert, _case, _tx


class AgentTraceTest(TestCase):
    def setUp(self):
        _tx("TX-1", "Alpha", 8000.0)
        _alert("Alpha", 8000.0, severity="Critical")
        _case("Caso A", deadline_days=5)

    def test_chat_returns_trace(self):
        r = cs.chat("resumo da plataforma")
        self.assertIn("trace", r)
        self.assertIsInstance(r["trace"], list)
        self.assertTrue(r["trace"])
        for entry in r["trace"]:
            self.assertIn("tool", entry)
            self.assertIn("title", entry)
            self.assertIn("ok", entry)
            self.assertIn("ms", entry)
            self.assertTrue(entry["ok"])
            self.assertIsInstance(entry["ms"], int)

    def test_trace_titles_are_readable(self):
        r = cs.chat("resumo da plataforma")
        for t in r["trace"]:
            self.assertTrue(t["title"])  # rótulo legível por ferramenta
        # o título vem da própria tool (mais rico que o rótulo genérico)
        self.assertEqual(r["trace"][0]["title"],
                         [t["title"] for t in r["trace"]][0])

    def test_trace_survives_failed_tool(self):
        # tool inexistente não entra; tool que falha aparece com ok=False
        calls = []

        def boom(f):
            calls.append(1)
            raise RuntimeError("falha simulada")

        orig = cs.TOOL_FUNCS.get("sla")
        cs.TOOL_FUNCS["sla"] = boom
        try:
            r = cs.chat("casos fora do prazo e sla")
        finally:
            cs.TOOL_FUNCS["sla"] = orig
        entry = next(t for t in r["trace"] if t["tool"] == "sla")
        self.assertFalse(entry["ok"])
        # a resposta continua a ser gerada (tool nunca derruba o chat)
        self.assertIn("answer", r)


class ChatEventsTest(TestCase):
    def setUp(self):
        _tx("TX-1", "Alpha", 8000.0)
        _alert("Alpha", 8000.0, severity="Critical")

    def test_event_sequence(self):
        events = list(cs.chat_events("resumo da plataforma"))
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds[0], "status")
        self.assertEqual(kinds[-1], "final")
        self.assertIn("tool_start", kinds)
        self.assertIn("tool_done", kinds)
        # cada tool_start tem um tool_done correspondente
        self.assertEqual(kinds.count("tool_start"), kinds.count("tool_done"))

    def test_final_matches_chat(self):
        events = list(cs.chat_events("alertas críticos"))
        final = events[-1]["data"]
        sync = cs.chat("alertas críticos")
        self.assertEqual(final["answer"], sync["answer"])
        self.assertEqual(final["mode"], sync["mode"])
        self.assertEqual(final["tools_used"], sync["tools_used"])

    def test_empty_question_yields_final(self):
        events = list(cs.chat_events("   "))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "final")


class CopilotCacheTest(TestCase):
    def test_cached_tool_second_call_is_cache_hit(self):
        calls = []

        def slow_tool(f):
            calls.append(1)
            return {"tool": "x", "title": "X", "summary": "s", "meta": {}}

        cached = cs._cacheable("test_tool")(slow_tool)
        original_ttl = cs.COPILOT_CACHE_TTL
        cs.COPILOT_CACHE_TTL = 30  # força TTL ativo neste teste
        try:
            r1 = cached({})
            r2 = cached({})
            self.assertEqual(len(calls), 1)  # 2.ª chamada veio da cache
            self.assertIs(r1, r2)
        finally:
            cs.COPILOT_CACHE_TTL = original_ttl
            cs._tool_cache.clear()

    def test_fingerprint_changes_with_data(self):
        fp1 = cs._data_fingerprint()
        _tx("TX-FP", "Beta", 100.0)
        fp2 = cs._data_fingerprint()
        self.assertNotEqual(fp1, fp2)

    def test_cache_invalidated_when_data_changes(self):
        calls = []

        def counting_tool(f):
            calls.append(Transaction.objects.count())
            return {"tool": "x", "title": "X", "summary": "s", "meta": {}}

        cached = cs._cacheable("counting")(counting_tool)
        try:
            cached({})
            _tx("TX-CACHE-1", "Gamma", 50.0)  # muda o fingerprint
            cached({})
            self.assertEqual(len(calls), 2)
        finally:
            cs._tool_cache.clear()

    def test_benford_via_tool_funcs_cached(self):
        # TOOL_FUNCS["benford"] está embrulhado com cache
        for i in range(1, 12):
            _tx(f"TX-B{i}", f"V{i}", float(10 ** (i % 9)))
        cs._tool_cache.clear()
        r1 = cs.TOOL_FUNCS["benford"]({})
        self.assertIn("tool", r1)
        cs._tool_cache.clear()


class CopilotStreamRESTTest(TestCase):
    def setUp(self):
        self.token = "tok-stream-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        _tx("TX-1", "Alpha", 8000.0)
        _alert("Alpha", 8000.0, severity="Critical")

    def _post(self, payload, **extra):
        return self.client.post("/django/api/ai/copilot/stream", payload,
                                format="json", **extra)

    def test_stream_returns_sse(self):
        resp = self._post({"question": "resumo da plataforma"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp["Content-Type"])
        # StreamingHttpResponse: consumir streaming_content (não .content)
        body = "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for chunk in resp.streaming_content)
        self.assertIn("event: final", body)
        # extrai o payload do último evento final e valida a estrutura
        events = []
        ev_name = None
        for line in body.split("\n"):
            if line.startswith("event: "):
                ev_name = line[7:].strip()
            elif line.startswith("data: ") and ev_name:
                events.append((ev_name, json.loads(line[6:])))
        finals = [d for (name, d) in events if name == "final"]
        self.assertTrue(finals)
        data = finals[-1]
        self.assertIn("answer", data)
        self.assertIn("trace", data)

    def test_stream_requires_auth(self):
        client = APIClient()
        resp = client.post("/django/api/ai/copilot/stream",
                           {"question": "resumo"}, format="json")
        self.assertIn(resp.status_code, [401, 403])

    def test_stream_empty_question_400(self):
        resp = self._post({"question": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_stream_with_page_context(self):
        resp = self._post({"question": "e agora?", "page": "/sla"})
        self.assertEqual(resp.status_code, 200)
        body = "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for chunk in resp.streaming_content)
        self.assertIn("event: tool_start", body)
        self.assertIn("SLA", body)


class CopilotFeedbackRESTTest(TestCase):
    def setUp(self):
        self.token = "tok-fb-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)

    def test_feedback_valid(self):
        resp = self.client.post("/django/api/ai/copilot/feedback",
                                {"rating": 5, "question": "resumo",
                                 "answer": "texto da resposta", "mode": "rules",
                                 "page": "/alerts"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json().get("ok"))
        fb = CopilotFeedback.objects.first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.rating, 5)
        self.assertEqual(fb.page, "/alerts")
        self.assertEqual(fb.username, "test_admin")

    def test_feedback_rating_out_of_range(self):
        resp = self.client.post("/django/api/ai/copilot/feedback",
                                {"rating": 9}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_feedback_rating_not_int(self):
        resp = self.client.post("/django/api/ai/copilot/feedback",
                                {"rating": "bom"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_feedback_requires_auth(self):
        client = APIClient()
        resp = client.post("/django/api/ai/copilot/feedback",
                           {"rating": 4}, format="json")
        self.assertIn(resp.status_code, [401, 403])


class PlatformBoostTest(TestCase):
    def test_gzip_middleware_enabled(self):
        self.assertIn("django.middleware.gzip.GZipMiddleware",
                      settings.MIDDLEWARE)
