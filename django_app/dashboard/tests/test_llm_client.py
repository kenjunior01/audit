from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from dashboard import llm_client
from dashboard import excel_ai_service


class OpenAICompatibleLlmTest(SimpleTestCase):
    def test_generate_uses_openai_chat_completions(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "local model answer"}}]
        }
        with patch.object(llm_client, "LLM_API_STYLE", "openai-compatible"), \
                patch.object(llm_client, "LLM_BASE_URL", "http://exaone:8080/v1"), \
                patch.object(llm_client, "LLM_MODEL", "exaone4.0-1.2b"), \
                patch("dashboard.llm_client.requests.post", return_value=response) as post:
            answer = llm_client.generate("Explain this result")

        self.assertEqual(answer, "local model answer")
        self.assertEqual(
            post.call_args.args[0],
            "http://exaone:8080/v1/chat/completions",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["model"],
            "exaone4.0-1.2b",
        )

    def test_availability_probes_openai_models_endpoint(self):
        response = Mock(status_code=200)
        with patch.object(llm_client, "LLM_API_STYLE", "openai-compatible"), \
                patch.object(llm_client, "LLM_BASE_URL", "http://exaone:8080/v1"), \
                patch("dashboard.llm_client.requests.get", return_value=response) as get:
            self.assertTrue(llm_client.is_available())

        self.assertEqual(get.call_args.args[0], "http://exaone:8080/v1/models")

    def test_excel_copilot_uses_openai_compatible_chat_endpoint(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"intent":"explain","answer":"resposta EXAONE"}'
                }
            }]
        }
        with patch.object(excel_ai_service, "LLM_API_STYLE", "openai-compatible"), \
                patch.object(excel_ai_service, "OLLAMA_URL", "http://exaone:8080/v1"), \
                patch("requests.post", return_value=response) as post:
            result = excel_ai_service.call_ollama_plan(
                "Explica estes dados",
                {"rows": 2, "columns": []},
                "Dados",
            )

        self.assertEqual(result["answer"], "resposta EXAONE")
        self.assertEqual(
            post.call_args.args[0],
            "http://exaone:8080/v1/chat/completions",
        )
