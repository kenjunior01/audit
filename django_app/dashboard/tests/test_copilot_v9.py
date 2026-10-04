"""
Testes do Copiloto Global v9 — resiliência do LLM (sonda Ollama com cooldown).

Cobre:
- ollama_available(): sucesso reinicia estado; falha de rede e HTTP != 200
  entram em cooldown; durante o cooldown não há contactos de rede;
  TTL=0 desativa o cooldown (sonda sempre)
- call_ollama_copilot(): durante o cooldown devolve None sem chamar
  requests.post (o chat degrada imediatamente para o modo regras)
"""
from unittest import mock

from django.test import TestCase

from dashboard import copilot_service as cs


def _reset_state():
    """Repõe o estado global da sonda entre testes."""
    cs._ollama_down_until = 0.0


class OllamaProbeTest(TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_probe_success_resets_cooldown(self):
        resp = mock.Mock(status_code=200)
        with mock.patch.object(cs, "OLLAMA_URL", "http://localhost:11434"), \
                mock.patch("requests.get", return_value=resp) as mget:
            self.assertTrue(cs.ollama_available())
            # sucesso limpa qualquer cooldown prévio
            self.assertEqual(cs._ollama_down_until, 0.0)
            self.assertIn("/api/tags", mget.call_args[0][0])

    def test_probe_network_failure_enters_cooldown(self):
        with mock.patch("requests.get", side_effect=ConnectionError("down")):
            self.assertFalse(cs.ollama_available())
            self.assertGreater(cs._ollama_down_until, 0.0)

    def test_probe_http_error_enters_cooldown(self):
        resp = mock.Mock(status_code=503)
        with mock.patch("requests.get", return_value=resp):
            self.assertFalse(cs.ollama_available())
            self.assertGreater(cs._ollama_down_until, 0.0)

    def test_cooldown_skips_network(self):
        cs._ollama_down_until = cs.time.time() + 999
        with mock.patch("requests.get") as mget:
            self.assertFalse(cs.ollama_available())
            mget.assert_not_called()  # nem sequer tenta a rede

    def test_ttl_zero_always_probes(self):
        with mock.patch.object(cs, "OLLAMA_PROBE_TTL", 0.0), \
                mock.patch("requests.get", side_effect=ConnectionError("x")):
            self.assertFalse(cs.ollama_available())
            # TTL=0 → sem cooldown; segunda chamada volta a sondar
            self.assertEqual(cs._ollama_down_until, 0.0)
            self.assertFalse(cs.ollama_available())


class CallOllamaShortCircuitTest(TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_call_returns_none_during_cooldown_without_post(self):
        cs._ollama_down_until = cs.time.time() + 999
        with mock.patch("requests.post") as mpost:
            self.assertIsNone(cs.call_ollama_copilot("pergunta", []))
            mpost.assert_not_called()  # degradação imediata, sem espera

    def test_call_still_works_when_probe_ok(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"response": '{"answer": "ok"}'}
        with mock.patch("requests.get", return_value=resp), \
                mock.patch("requests.post", return_value=resp):
            out = cs.call_ollama_copilot("pergunta", [])
        self.assertIsNotNone(out)
        self.assertEqual(out["answer"], "ok")
