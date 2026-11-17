"""Testes das credenciais de IA na BD (Fernet) — ai_credentials + endpoints.

Cobre: cifra/decifra/mascaramento, precedência BD → env, gravação/limpeza,
endpoint /ai/nim/credentials (permissões, sem fuga de segredos) e o comando
seed_nim_credentials.
"""
import os
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from io import StringIO
from rest_framework.test import APIClient

from dashboard import ai_credentials
from dashboard.models import AiCredential, ApiToken

SECRET = "nvapi-AbCdEfGhI0123456789ZzYyXxWw"


class CryptoTest(TestCase):
    def test_roundtrip(self):
        enc = ai_credentials.encrypt_secret(SECRET)
        self.assertTrue(enc.startswith("enc:v1:"))
        self.assertNotIn(SECRET, enc)
        self.assertEqual(ai_credentials.decrypt_secret(enc), SECRET)

    def test_plaintext_passthrough(self):
        # valor sem prefixo passa através (legado/env)
        self.assertEqual(ai_credentials.decrypt_secret(SECRET), SECRET)
        self.assertEqual(ai_credentials.decrypt_secret(""), "")

    def test_corrupted_cipher_returns_empty(self):
        enc = ai_credentials.encrypt_secret(SECRET)
        bad = enc[:-8] + "AAAAAAAA"
        self.assertEqual(ai_credentials.decrypt_secret(bad), "")

    def test_encrypt_is_idempotent_on_cipher(self):
        enc = ai_credentials.encrypt_secret(SECRET)
        self.assertEqual(ai_credentials.encrypt_secret(enc), enc)

    def test_mask(self):
        m = ai_credentials.mask_key(SECRET)
        self.assertTrue(m.startswith("nvapi-Ab"))
        self.assertTrue(m.endswith("…ZzYyXxWw") or m.endswith("XxWw"))
        self.assertNotIn("0123456789", m)
        self.assertEqual(ai_credentials.mask_key(""), "")


class ResolveSlotTest(TestCase):
    def _row(self, slot, value):
        AiCredential.objects.create(slot=slot,
                                    api_key=ai_credentials.encrypt_secret(value))

    def test_db_wins_over_env(self):
        self._row("text", SECRET)
        with patch.dict(os.environ, {"AUDIT_NVIDIA_API_KEY": "nvapi-env"}):
            cfg = ai_credentials.resolve_slot("text")
        self.assertEqual(cfg["api_key"], SECRET)
        self.assertEqual(cfg["source"], "db")
        self.assertEqual(cfg["model"],
                         "nvidia/nemotron-3-ultra-550b-a55b")

    def test_env_fallback(self):
        with patch.dict(os.environ, {"AUDIT_NVIDIA_API_KEY": "nvapi-env"}):
            cfg = ai_credentials.resolve_slot("text")
        self.assertEqual(cfg["api_key"], "nvapi-env")
        self.assertEqual(cfg["source"], "env")

    def test_nothing_configured(self):
        cfg = ai_credentials.resolve_slot("vision")
        self.assertEqual(cfg["api_key"], "")
        self.assertEqual(cfg["source"], "")
        # defaults de modelo continuam presentes (para ecrãs de configuração)
        self.assertTrue(cfg["model"])

    def test_image_slot_defaults(self):
        cfg = ai_credentials.resolve_slot("image")
        self.assertEqual(cfg["base_url"], "https://ai.api.nvidia.com/v1/genai")
        self.assertEqual(cfg["model"], "black-forest-labs/flux.2-klein-4b")

    def test_db_model_override(self):
        row = AiCredential(slot="image")
        row.api_key = ai_credentials.encrypt_secret(SECRET)
        row.model = "black-forest-labs/outro"
        row.save()
        cfg = ai_credentials.resolve_slot("image")
        self.assertEqual(cfg["model"], "black-forest-labs/outro")


class SaveSlotTest(TestCase):
    def test_save_and_clear(self):
        ai_credentials.save_slot("text", api_key=SECRET, model="m1",
                                 updated_by="admin@x.pt")
        row = AiCredential.objects.get(slot="text")
        self.assertIn("enc:v1:", row.api_key)
        self.assertNotIn(SECRET, row.api_key)
        self.assertEqual(row.updated_by, "admin@x.pt")

        # api_key="" limpa (passa a resolver por env)
        ai_credentials.save_slot("text", api_key="")
        row.refresh_from_db()
        self.assertEqual(row.api_key, "")

        # api_key=None mantém
        ai_credentials.save_slot("text", api_key=SECRET)
        ai_credentials.save_slot("text", model="m2")
        row.refresh_from_db()
        self.assertEqual(ai_credentials.decrypt_secret(row.api_key), SECRET)
        self.assertEqual(row.model, "m2")

    def test_invalid_slot_raises(self):
        with self.assertRaises(ValueError):
            ai_credentials.save_slot("audio", api_key="x")


class CredentialsEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")
        cls.auditor = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.auditor, user_id="a@x.pt",
                                role="auditor")
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="ad@x.pt", role="admin")

    def test_get_requires_auth(self):
        r = APIClient().get("/django/api/ai/nim/credentials")
        self.assertEqual(r.status_code, 403)

    def test_get_masks_secrets(self):
        ai_credentials.save_slot("text", api_key=SECRET)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.get("/django/api/ai/nim/credentials")
        self.assertEqual(r.status_code, 200)
        body = str(r.content.decode())
        self.assertNotIn(SECRET, body)
        self.assertNotIn("enc:v1:", body)
        slot = r.data["slots"]["text"]
        self.assertTrue(slot["configured"])
        self.assertEqual(slot["source"], "db")
        self.assertIn("…", slot["masked"])

    def test_post_forbidden_for_viewer(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.post("/django/api/ai/nim/credentials",
                   {"text_key": SECRET}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_post_saves_for_auditor(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.auditor)
        r = c.post("/django/api/ai/nim/credentials",
                   {"text_key": SECRET, "image_key": "nvapi-img-123456789",
                    "vision_model": "nvidia/outro-omni"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["ok"])
        self.assertIn("text", r.data["updated"])
        row = AiCredential.objects.get(slot="text")
        self.assertEqual(ai_credentials.decrypt_secret(row.api_key), SECRET)
        self.assertIn("enc:v1:", row.api_key)
        self.assertEqual(r.data["slots"]["text"]["source"], "db")

    def test_post_empty_key_clears(self):
        ai_credentials.save_slot("image", api_key="nvapi-antiga-1234567890")
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.auditor)
        r = c.post("/django/api/ai/nim/credentials",
                   {"image_key": ""}, format="json")
        self.assertEqual(r.status_code, 200)
        row = AiCredential.objects.get(slot="image")
        self.assertEqual(row.api_key, "")

    def test_post_without_fields_400(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.auditor)
        r = c.post("/django/api/ai/nim/credentials", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_status_never_leaks(self):
        ai_credentials.save_slot("text", api_key=SECRET)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.get("/django/api/ai/nim/status")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(SECRET, str(r.content.decode()))


class SeedCommandTest(TestCase):
    def test_seed_from_env_and_clear(self):
        ai_credentials.save_slot("text", api_key="nvapi-antiga-9876543210")
        with patch.dict(os.environ, {"AUDIT_NVIDIA_API_KEY": SECRET}):
            out = StringIO()
            call_command("seed_nim_credentials", stdout=out)
            cfg = ai_credentials.resolve_slot("text")
            self.assertEqual(cfg["source"], "db")
            self.assertEqual(cfg["api_key"], SECRET)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUDIT_NVIDIA_API_KEY", None)
            call_command("seed_nim_credentials", "--clear", stdout=StringIO())
        row = AiCredential.objects.get(slot="text")
        self.assertEqual(row.api_key, "")

    def test_seed_without_env_just_reports(self):
        os.environ.pop("AUDIT_NVIDIA_API_KEY", None)
        os.environ.pop("NVIDIA_API_KEY", None)
        out = StringIO()
        call_command("seed_nim_credentials", stdout=out)
        self.assertIn("Sem env", out.getvalue())
