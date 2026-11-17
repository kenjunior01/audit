"""Testes do NIM Studio — visão (omni) e imagens (FLUX.2-klein-4B).

Cobre: nvidia_client (endpoint/Authorization da BD, payload, auto-detecção
image/video), views /ai/nim/vision, /ai/nim/image (clamps, galeria, ficheiro),
persistência NimImage e permissões.
"""
import base64
import uuid
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from dashboard import nvidia_client
from dashboard.models import ApiToken, NimImage

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0fakejpeg").decode()


def _image_response():
    r = Mock()
    r.status_code = 200
    r.json.return_value = {"artifacts": [{"base64": JPEG,
                                          "finishReason": "SUCCESS"}]}
    return r


def _vision_response(text="Uma rã verde num lago."):
    r = Mock()
    r.status_code = 200
    r.json.return_value = {"choices": [{"message": {"content": text,
                                                    "reasoning_content":
                                                        "pensar…"}}]}
    return r


class NvidiaImageClientTest(SimpleTestCase):
    def test_generate_uses_db_credential(self):
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "image",
                                 "api_key": "nvapi-db-key",
                                 "model": "black-forest-labs/flux.2-klein-4b",
                                 "base_url": "https://ai.api.nvidia.com/v1/genai",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=_image_response()) as post:
            out = nvidia_client.generate_image("uma rã", width=1024,
                                               height=1024, steps=4)
        self.assertEqual(post.call_args.args[0],
                         "https://ai.api.nvidia.com/v1/genai/"
                         "black-forest-labs/flux.2-klein-4b")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"],
                         "Bearer nvapi-db-key")
        self.assertEqual(post.call_args.kwargs["json"]["prompt"], "uma rã")
        self.assertEqual(out["image_b64"], JPEG)
        self.assertEqual(out["source"], "db")

    def test_generate_without_config_raises(self):
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "image", "api_key": "",
                                 "model": "", "base_url": "",
                                 "source": ""}), \
                patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("AUDIT_NIM_IMAGE_API_KEY", None)
            os.environ.pop("NVIDIA_IMAGE_API_KEY", None)
            os.environ.pop("AUDIT_NVIDIA_API_KEY", None)
            os.environ.pop("NVIDIA_API_KEY", None)
            with self.assertRaises(RuntimeError):
                nvidia_client.generate_image("x")

    def test_artifacts_empty_raises(self):
        r = Mock()
        r.status_code = 200
        r.json.return_value = {"artifacts": []}
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "image", "api_key": "k",
                                 "model": "m", "base_url": "u",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=r):
            with self.assertRaises(ValueError):
                nvidia_client.generate_image("x")


class VisionClientTest(SimpleTestCase):
    def test_vision_uses_db_key_and_discards_reasoning(self):
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "vision", "api_key": "nvapi-db-vision",
                                 "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                                 "base_url": "https://integrate.api.nvidia.com/v1",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=_vision_response()) as post:
            out = nvidia_client.vision_describe("https://x/fig.jpg",
                                                question="O que vês?")
        self.assertEqual(post.call_args.args[0],
                         "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"],
                         "Bearer nvapi-db-vision")
        msg = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertEqual(msg[0]["type"], "text")
        self.assertEqual(msg[1]["type"], "image_url")
        self.assertEqual(out["answer"], "Uma rã verde num lago.")
        self.assertEqual(out["media_type"], "image")

    def test_video_url_autodetected(self):
        self.assertEqual(nvidia_client.detect_media_type(
            "https://a/b/c.mp4?x=1"), "video")
        self.assertEqual(nvidia_client.detect_media_type(
            "https://a/b/c.jpg"), "image")
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "vision", "api_key": "k",
                                 "model": "m",
                                 "base_url": "https://integrate.api.nvidia.com/v1",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=_vision_response()) as post:
            nvidia_client.vision_describe("https://a/b.mp4")
        content = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "video_url")

    def test_empty_answer_raises(self):
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "vision", "api_key": "k",
                                 "model": "m", "base_url": "u",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=_vision_response(text="")):
            with self.assertRaises(ValueError):
                nvidia_client.vision_describe("https://x.jpg")


class NimStudioViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")
        cls.auditor = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.auditor, user_id="a@x.pt",
                                role="auditor")

    def _client(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return c

    def test_image_requires_auth(self):
        r = APIClient().post("/django/api/ai/nim/image",
                             {"prompt": "x"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_image_requires_prompt(self):
        r = self._client(self.viewer).post("/django/api/ai/nim/image",
                                           {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_image_generates_and_persists(self):
        with patch("dashboard.nvidia_client.ai_credentials"
                   ".resolve_slot",
                   return_value={"slot": "image", "api_key": "nvapi-db",
                                 "model": "black-forest-labs/flux.2-klein-4b",
                                 "base_url": "https://ai.api.nvidia.com/v1/genai",
                                 "source": "db"}), \
                patch("dashboard.nvidia_client.requests.post",
                      return_value=_image_response()) as post:
            r = self._client(self.viewer).post(
                "/django/api/ai/nim/image",
                {"prompt": "gráfico de auditoria", "width": 700,
                 "height": 9999, "steps": 99, "seed": 7}, format="json")
        self.assertEqual(r.status_code, 200)
        data = r.data
        self.assertIn("image", data)  # data URI
        self.assertTrue(data["image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(data["width"], 688)   # clamp para múltiplo de 16
        self.assertEqual(data["height"], 1024)  # clamp para o máximo
        self.assertEqual(data["steps"], 8)      # clamp para o máximo
        self.assertEqual(data["seed"], 7)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["width"], 688)
        self.assertEqual(body["height"], 1024)
        self.assertEqual(body["steps"], 8)
        rec = NimImage.objects.get(pk=data["id"])
        self.assertEqual(rec.prompt, "gráfico de auditoria")
        self.assertTrue(rec.image.name.startswith("nim_images/"))
        self.assertEqual(rec.image.read()[:4], b"\xff\xd8\xff\xe0")
        rec.image.delete(save=True)  # não deixar ficheiro de teste

    def test_image_engine_failure_502(self):
        with patch("dashboard.nvidia_client.generate_image",
                   side_effect=Exception("boom")):
            r = self._client(self.viewer).post("/django/api/ai/nim/image",
                                               {"prompt": "x"}, format="json")
        self.assertEqual(r.status_code, 502)

    def test_vision_endpoint_flow(self):
        with patch("dashboard.nvidia_client.vision_describe",
                   return_value={"answer": "boardwalk", "model": "omni",
                                 "media_type": "image", "latency_ms": 900,
                                 "source": "db"}):
            r = self._client(self.viewer).post(
                "/django/api/ai/nim/vision",
                {"url": "https://x/foto.jpg", "question": "o que é?"},
                format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["answer"], "boardwalk")

    def test_vision_requires_url(self):
        r = self._client(self.viewer).post("/django/api/ai/nim/vision",
                                           {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_gallery_and_file(self):
        rec = NimImage(prompt="teste galeria", width=512, height=512,
                       steps=4, model="m")
        rec.image.save("nim_test.jpg", ContentFile(b"\xff\xd8\xff\xe0abc"),
                       save=True)
        c = self._client(self.viewer)
        r = c.get("/django/api/ai/nim/images")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["images"][0]["prompt"], "teste galeria")
        self.assertIn("/ai/nim/images/", r.data["images"][0]["file_url"])

        r = c.get(f"/django/api/ai/nim/images/{rec.pk}/file")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")

        r = c.get("/django/api/ai/nim/images/999999/file")
        self.assertEqual(r.status_code, 404)
        rec.image.delete(save=True)  # não deixar ficheiro de teste

    def test_status_lists_slots_and_engines(self):
        r = self._client(self.viewer).get("/django/api/ai/nim/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text", r.data["slots"])
        self.assertIn("vision", r.data["slots"])
        self.assertIn("image", r.data["slots"])
        ids = [e["id"] for e in r.data["engines"]]
        self.assertEqual(ids, ["vision", "image"])
