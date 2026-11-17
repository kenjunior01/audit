"""Copiloto Global com visão omni (NVIDIA NIM) — Task 38.

POST /ai/copilot e /ai/copilot/stream aceitam 'image_url': a imagem é
descrita pelo motor de visão e a observação entra no contexto agéntico.
Falha da visão degrada para só-texto (nunca derruba o chat).
"""
import json
import uuid

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from dashboard.models import ApiToken


def _vision_ok():
    return {"answer": "Um cão preto ao lado de um portátil.",
            "media_type": "image", "latency_ms": 900, "source": "db"}


def _chat_result(**kw):
    base = {"answer": "Resposta do copiloto.", "mode": "llm",
            "tools_used": [], "insights": [], "actions": [],
            "tables": [], "followups": []}
    base.update(kw)
    return base


class CopilotVisionSyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="admin@x.pt",
                                role="admin")

    def _client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        return c

    def test_image_url_injects_context_and_vision_block(self):
        with patch("dashboard.copilot_views.nvidia_client.vision_describe",
                   return_value=_vision_ok()) as vdesc, \
             patch("dashboard.copilot_service.chat",
                   return_value=_chat_result()) as chat:
            r = self._client().post(
                "/django/api/ai/copilot",
                {"question": "O que vês e quantos alertas abertos há?",
                 "image_url": "https://exemplo.pt/foto.jpg"}, format="json")
        self.assertEqual(r.status_code, 200)
        q = chat.call_args.args[0]
        self.assertIn("[Imagem anexada pelo utilizador", q)
        self.assertIn("Um cão preto", q)
        self.assertEqual(vdesc.call_args.kwargs["question"],
                         "O que vês e quantos alertas abertos há?")
        self.assertEqual(r.data["vision"]["observation"], "Um cão preto ao lado de um portátil.")
        self.assertEqual(r.data["vision"]["media_type"], "image")

    def test_invalid_image_url_400(self):
        r = self._client().post(
            "/django/api/ai/copilot",
            {"question": "x", "image_url": "ftp://mau"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_vision_failure_degrades_gracefully(self):
        with patch("dashboard.copilot_views.nvidia_client.vision_describe",
                   side_effect=Exception("motor down")), \
             patch("dashboard.copilot_service.chat",
                   return_value=_chat_result()) as chat:
            r = self._client().post(
                "/django/api/ai/copilot",
                {"question": "resumo?", "image_url": "https://exemplo.pt/x.jpg"},
                format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.data["vision"])
        # contexto NÃO enriquecido (pergunta original segue para o agente)
        self.assertEqual(chat.call_args.args[0], "resumo?")


class CopilotVisionStreamTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="admin@x.pt",
                                role="admin")

    def test_stream_final_event_carries_vision(self):
        events = [{"event": "status", "data": {"msg": "a trabalhar"}},
                  {"event": "final", "data": _chat_result()}]

        def fake_events(question, history=None, page=None):
            self.assertIn("[Imagem anexada", question)
            return iter(events)

        with patch("dashboard.copilot_views.nvidia_client.vision_describe",
                   return_value=_vision_ok()), \
             patch("dashboard.copilot_service.chat_events",
                   side_effect=fake_events):
            c = APIClient()
            c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
            r = c.post("/django/api/ai/copilot/stream",
                       {"question": "descreve",
                        "image_url": "https://exemplo.pt/f.jpg"},
                       format="json")
        self.assertEqual(r.status_code, 200)
        body = b"".join(r.streaming_content).decode()
        finals = [json.loads(l[6:]) for l in body.split("\n")
                  if l.startswith("data: ") and '"vision"' in l]
        self.assertTrue(finals)
        self.assertEqual(finals[-1]["vision"]["observation"],
                         "Um cão preto ao lado de um portátil.")


class CopilotImagesToolTest(TestCase):
    """Busca agéntica de imagens no Banco de Imagens — Task 42.

    O copiloto responde a «mostra uma imagem de X» com grelha de miniaturas
    reais (openverse/met, sem chave) + licença; falha dos provedores degrada
    para mensagem amigável (nunca derruba o chat)."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="admin@x.pt",
                                role="admin")

    def _client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        return c

    def _bank_payload(self, provider, n):
        results = []
        for i in range(n):
            results.append({
                "image_id": f"{provider}-{i}", "title": f"Foto {provider} {i}",
                "author": "Ana", "license": "CC0",
                "license_url": "https://creativecommons.org/publicdomain/",
                "landing_url": f"https://ex.org/{provider}/{i}",
                "url": f"https://img.ex.org/{provider}/{i}.jpg",
                "thumb_url": f"https://img.ex.org/{provider}/{i}_t.jpg",
                "width": 800, "height": 600})
        return {"provider": provider, "query": "escritorio", "page": 1,
                "page_size": 6, "result_count": n, "results": results}

    def test_detect_and_query(self):
        from dashboard import copilot_service as cs
        self.assertIn("images", cs.detect_tools(
            "mostra uma imagem de escritório financeiro"))
        self.assertIn("images", cs.detect_tools("fotos de informatica"))
        self.assertEqual(cs.extract_image_query(
            "mostra uma imagem de escritório moderno"), "escritorio moderno")
        self.assertEqual(cs.extract_image_query("imagens de equipa"),
                         "equipa")

    def test_tool_returns_images_with_license(self):
        from dashboard import copilot_service as cs

        def fake_search(query, provider="openverse", **kw):
            return self._bank_payload(provider, 6)
        with patch("dashboard.imagebank.search", side_effect=fake_search):
            r = cs.tool_search_images({"image_query": "escritorio"})
        self.assertEqual(r["tool"], "images")
        self.assertEqual(len(r["images"]), 3)
        self.assertTrue({i["provider"] for i in r["images"]} <=
                        {"openverse", "met"})
        for i in r["images"]:
            self.assertTrue(i["thumb_url"].startswith("https://"))
            self.assertTrue(i["license"])
        self.assertIn("«", r["summary"])

    def test_tool_providers_downgrade(self):
        from dashboard import copilot_service as cs
        with patch("dashboard.imagebank.search",
                   side_effect=RuntimeError("met indisponível")):
            r = cs.tool_search_images({"image_query": "escritorio"})
        self.assertEqual(r["tool"], "images")
        self.assertEqual(r["images"], [])
        self.assertIn("Não encontrei imagens", r["summary"])

    def test_chat_final_includes_images(self):
        from dashboard import copilot_service as cs

        def fake_search(query, provider="openverse", **kw):
            return self._bank_payload(provider, 4)
        with patch("dashboard.imagebank.search", side_effect=fake_search):
            out = cs.chat("mostra imagens de informatica")
        self.assertIn("images", out["tools_used"])
        self.assertEqual(len(out.get("images") or []), 3)
        self.assertTrue(out.get("answer"))

    def test_endpoint_ok_for_auditor(self):
        def fake_search(query, provider="openverse", **kw):
            return self._bank_payload(provider, 4)
        with patch("dashboard.imagebank.search", side_effect=fake_search):
            r = self._client().post("/django/api/ai/copilot",
                                    {"question": "mostra fotos de escritorio"},
                                    format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json().get("images") or []), 3)
