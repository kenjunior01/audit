"""Testes dos Motores de IA (llm_client v2 multi-provider + endpoints).

Cobre:
- Cadeia NVIDIA NIM → provider primário (generate/generate_meta)
- Reasoning do Nemotron: chat_template_kwargs + descarte de reasoning_content
- generate_stream: SSE com chunks de conteúdo (reasoning ignorado)
- provider_status: forma e disponibilidade
- Endpoints /ai/llm/status, /ai/llm/test, /bi/narrate (permissões + fallback)
"""
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from dashboard import llm_client
from dashboard.models import ApiToken


class NvidiaChainTest(SimpleTestCase):
    def test_nvidia_generate_used_when_key_set(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "  resposta nemotron "}}]
        }
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch.object(llm_client, "NVIDIA_BASE_URL",
                             "https://integrate.api.nvidia.com/v1"), \
                patch.object(llm_client, "NVIDIA_MODEL",
                             "nvidia/nemotron-3-ultra-550b-a55b"), \
                patch("dashboard.llm_client.requests.post",
                      return_value=response) as post:
            text, meta = llm_client.generate_meta("Olá")

        self.assertEqual(text, "resposta nemotron")
        self.assertEqual(meta["provider"], "nvidia")
        self.assertEqual(meta["model"], "nvidia/nemotron-3-ultra-550b-a55b")
        self.assertEqual(
            post.call_args.args[0],
            "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"],
                         "Bearer nvapi-test")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "nvidia/nemotron-3-ultra-550b-a55b")
        self.assertNotIn("chat_template_kwargs", body)  # reasoning desligado

    def test_nvidia_reasoning_flag_adds_chat_template_kwargs(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "final"}}]
        }
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch.object(llm_client, "NVIDIA_REASONING", True), \
                patch("dashboard.llm_client.requests.post",
                      return_value=response) as post:
            llm_client.generate("ping")

        self.assertEqual(
            post.call_args.kwargs["json"]["chat_template_kwargs"],
            {"enable_thinking": True})

    def test_chain_falls_back_to_primary_on_nvidia_failure(self):
        ok_response = Mock()
        ok_response.json.return_value = {
            "choices": [{"message": {"content": "resposta primária"}}]
        }
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch.object(llm_client, "LLM_API_STYLE", "openai-compatible"), \
                patch.object(llm_client, "LLM_BASE_URL", "http://fallback:8080/v1"), \
                patch("dashboard.llm_client.requests.post",
                      side_effect=[__import__("requests").ConnectionError("boom"),
                                   ok_response]) as post:
            text, meta = llm_client.generate_meta("ping")

        self.assertEqual(text, "resposta primária")
        self.assertEqual(meta["provider"], "primary")
        self.assertEqual(post.call_count, 2)

    def test_generate_forces_provider_primary(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "primária"}}]
        }
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch.object(llm_client, "LLM_API_STYLE", "openai-compatible"), \
                patch.object(llm_client, "LLM_BASE_URL", "http://f:8080/v1"), \
                patch("dashboard.llm_client.requests.post",
                      return_value=response) as post:
            text = llm_client.generate("ping", provider="primary")

        self.assertEqual(text, "primária")
        self.assertEqual(post.call_args.args[0], "http://f:8080/v1/chat/completions")

    def test_stream_yields_content_and_skips_reasoning(self):
        sse = "\n".join([
            'data: {"choices":[{"delta":{"reasoning_content":"pensando..."}}]}',
            'data: {"choices":[{"delta":{"content":"Olá"}}]}',
            'data: {"choices":[{"delta":{"content":" mundo"}}]}',
            'data: [DONE]',
        ])
        response = Mock()
        response.raise_for_status.return_value = None
        response.iter_lines.return_value = [ln.encode() for ln in sse.split("\n")]
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch("dashboard.llm_client.requests.post",
                      return_value=response) as post:
            chunks = list(llm_client.generate_stream("ping"))

        self.assertEqual("".join(chunks), "Olá mundo")
        self.assertTrue(post.call_args.kwargs["json"]["stream"] is True)

    def test_provider_status_shape(self):
        with patch.object(llm_client, "NVIDIA_API_KEY", "nvapi-test"), \
                patch.object(llm_client, "NVIDIA_BASE_URL",
                             "https://integrate.api.nvidia.com/v1"):
            status = llm_client.provider_status(timeout=0.1)
        self.assertEqual([p["id"] for p in status], ["nvidia", "primary"])
        nvidia = status[0]
        self.assertEqual(nvidia["label"], "NVIDIA NIM")
        self.assertTrue(nvidia["auth"])
        self.assertEqual(nvidia["priority"], 1)

    def test_is_available_without_keys_probes_primary_only(self):
        with patch.object(llm_client, "NVIDIA_API_KEY", ""), \
                patch("dashboard.llm_client.requests.get",
                      return_value=Mock(status_code=200)) as get:
            self.assertTrue(llm_client.is_available())
        self.assertIn("/api/tags", get.call_args.args[0])


class AiLlmEndpointsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")
        cls.auditor = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.auditor, user_id="a@x.pt", role="auditor")

    def test_status_requires_auth(self):
        r = APIClient().get("/django/api/ai/llm/status")
        self.assertEqual(r.status_code, 403)  # convenção da plataforma: anónimo → 403

    def test_status_viewer_ok(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.get("/django/api/ai/llm/status")
        self.assertEqual(r.status_code, 200)
        providers = r.data["providers"]
        self.assertEqual([p["id"] for p in providers], ["nvidia", "primary"])
        self.assertIn("any_available", r.data)

    def test_llm_test_forbidden_for_viewer(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.post("/django/api/ai/llm/test")
        self.assertEqual(r.status_code, 403)

    def test_llm_test_ok_for_auditor(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.auditor)
        with patch.object(llm_client, "generate_meta",
                          return_value=("OK", {"provider": "nvidia",
                                               "model": "nemotron",
                                               "latency_ms": 123})):
            r = c.post("/django/api/ai/llm/test")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["ok"])
        self.assertEqual(r.data["provider"], "nvidia")
        self.assertIn("latency_ms", r.data)

    def test_narrate_requires_payload(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.post("/django/api/bi/narrate", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_narrate_fallback_deterministic(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        with patch.object(llm_client, "generate_meta",
                          side_effect=RuntimeError("sem motores")):
            r = c.post("/django/api/bi/narrate",
                       {"kpis": [{"label": "Volume", "value": 1000}],
                        "insights": ["Concentração alta no fornecedor X"],
                        "period": "30 dias"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["available"])
        self.assertIn("Resumo determinístico", r.data["narrative"])
        self.assertIn("Concentração alta", r.data["narrative"])

    def test_narrate_with_llm(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        with patch.object(llm_client, "generate_meta",
                          return_value=("Volume total de 1.000. Recomendo "
                                        "verificar a concentração.",
                                        {"provider": "nvidia",
                                         "model": "nemotron",
                                         "latency_ms": 900})):
            r = c.post("/django/api/bi/narrate",
                       {"kpis": [{"label": "Volume", "value": 1000}],
                        "insights": ["Concentração alta"],
                        "period": "30 dias"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["available"])
        self.assertEqual(r.data["provider"], "nvidia")
        self.assertIn("concentração", r.data["narrative"])
