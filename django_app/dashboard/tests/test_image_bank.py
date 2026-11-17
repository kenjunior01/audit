"""Testes do Banco de Imagens — busca real estilo Freepik na plataforma.

Cobre: normalização dos 6 provedores (openverse/wikimedia sem chave;
pexels/unsplash/pixabay/freepik com chave na BD/env), validação de URL,
descarga com magic bytes, endpoints /ai/bank/* (permissões, guarda,
duplicados, galeria, ficheiro thumb/full, delete), fallback de capa do PDF
para StockImage e cifragem Fernet das chaves dos provedores.

Nenhum teste acede à rede — todas as chamadas HTTP são mocks.
"""
import base64
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from dashboard import ai_credentials, ai_nim_views, imagebank
from dashboard.models import ApiToken, StockImage

PNG = b"\x89PNG\r\n\x1a\n" + base64.b64encode(b"pngdata")[:16]
GIF = b"GIF89a" + b"gifdata"


def _http(payload):
    r = Mock()
    r.status_code = 200
    r.raise_for_status = Mock()
    r.json.return_value = payload
    return r


# ---------------------------------------------------------------------------
# Utilidades do módulo
# ---------------------------------------------------------------------------
class SniffExtTest(SimpleTestCase):
    def test_magic_bytes(self):
        self.assertEqual(imagebank.sniff_ext("", PNG[:10]), "png")
        self.assertEqual(imagebank.sniff_ext("", GIF[:10]), "gif")
        self.assertEqual(imagebank.sniff_ext("image/jpeg", b"\xff\xd8\xffE"), "jpg")
        self.assertEqual(imagebank.sniff_ext("", b"RIFF1234WEBPVP8 "), "webp")
        self.assertEqual(imagebank.sniff_ext("", b"<svg xmlns='x'>"), "svg")
        self.assertEqual(imagebank.sniff_ext("image/png", b"nope"), "png")
        self.assertEqual(imagebank.sniff_ext("text/html", b"<html>"), "")
        self.assertEqual(imagebank.sniff_ext("", b""), "")

    def test_strip_html(self):
        self.assertEqual(imagebank.strip_html("<a href='x'>Ana</a>"), "Ana")
        self.assertEqual(imagebank.strip_html("Cão <b>feliz</b>"), "Cão feliz")
        self.assertEqual(imagebank.strip_html(None), "")


class DownloadImageTest(SimpleTestCase):
    def test_download_validates_and_caps(self):
        r = Mock()
        r.status_code = 200
        r.headers = {"Content-Type": "image/png"}
        r.iter_content = Mock(return_value=[PNG[:8], PNG[8:]])
        with patch("dashboard.imagebank._get", return_value=r) as get:
            data, ct, ext = imagebank.download_image("https://x/y.png")
        self.assertEqual(data, PNG)
        self.assertEqual((ct, ext), ("image/png", "png"))
        # descarga nunca pede application/json (metmuseum responde 406)
        self.assertTrue(str(get.call_args.kwargs["headers"]["Accept"])
                        .startswith("image/"))

    def test_download_rejects_non_image(self):
        r = Mock()
        r.status_code = 200
        r.headers = {"Content-Type": "text/html"}
        r.iter_content = Mock(return_value=[b"<html></html>"])
        with patch("dashboard.imagebank._get", return_value=r):
            with self.assertRaises(RuntimeError):
                imagebank.download_image("https://x/page.html")

    def test_download_rejects_bad_scheme_and_size(self):
        with self.assertRaises(RuntimeError):
            imagebank.download_image("ftp://x/y.jpg")
        r = Mock()
        r.status_code = 200
        r.headers = {"Content-Type": "image/png"}
        r.iter_content = Mock(return_value=[b"x" * 70000] * 400)  # >25 MB
        with patch("dashboard.imagebank._get", return_value=r):
            with self.assertRaises(RuntimeError):
                imagebank.download_image("https://x/huge.png")


# ---------------------------------------------------------------------------
# Adapters de provedores (HTTP todo em mock)
# ---------------------------------------------------------------------------
class ProviderAdaptersTest(SimpleTestCase):
    def test_openverse_normalizes(self):
        payload = {"result_count": 7, "results": [{
            "id": "abc-123", "title": "Cão <b>feliz</b>", "creator": "Ana",
            "license": "cc0", "license_version": "1.0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "foreign_landing_url": "https://openverse.org/image/abc",
            "url": "https://example.org/full.jpg",
            "thumbnail": "https://api.openverse.org/v1/images/abc/thumb/",
            "width": 1200, "height": 800}]}
        with patch("dashboard.imagebank._get", return_value=_http(payload)):
            out = imagebank.search("cão", "openverse")
        self.assertEqual(out["result_count"], 7)
        r0 = out["results"][0]
        self.assertEqual(r0["image_id"], "abc-123")
        self.assertEqual(r0["title"], "Cão feliz")
        self.assertEqual(r0["license"], "cc0 1.0")
        self.assertEqual(r0["provider"], "openverse")
        self.assertTrue(r0["thumb_url"].endswith("/thumb/"))

    def test_wikimedia_strips_artist_html(self):
        payload = {"query": {"pages": {"42": {
            "pageid": 42, "title": "File:<i>Auditoria</i>.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/orig.jpg",
                "thumburl": "https://upload.wikimedia.org/480.jpg",
                "width": 3000, "height": 2000,
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:A",
                "extmetadata": {
                    "Artist": {"value": "<a href='#'>João</a>"},
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {"value":
                                   "https://creativecommons.org/licenses/by-sa/4.0"},
                }}]}}}}
        with patch("dashboard.imagebank._get", return_value=_http(payload)):
            out = imagebank.search("auditoria", "wikimedia")
        r0 = out["results"][0]
        self.assertEqual(r0["author"], "João")
        self.assertEqual(r0["license"], "CC BY-SA 4.0")
        self.assertEqual(r0["image_id"], "42")
        self.assertTrue(r0["url"].startswith("https://upload.wikimedia.org/"))

    def test_met_normalizes_and_skips_broken_objects(self):
        search_payload = {"total": 2, "objectIDs": [100, 200]}
        obj_payload = {
            "objectID": 100, "title": "Retrato de <i>Dama</i>",
            "artistDisplayName": "Pintor X",
            "primaryImage": "https://images.metmuseum.org/full.jpg",
            "primaryImageSmall": "https://images.metmuseum.org/small.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/100",
        }
        broken_payload = {"objectID": 200, "title": "Sem imagem"}
        with patch("dashboard.imagebank._get", side_effect=[
                _http(search_payload), _http(obj_payload),
                _http(broken_payload)]):
            out = imagebank.search("retrato", "met")
        self.assertEqual(out["result_count"], 2)
        self.assertEqual(len(out["results"]), 1)  # objeto sem imagem → salta
        r0 = out["results"][0]
        self.assertEqual(r0["image_id"], "100")
        self.assertEqual(r0["title"], "Retrato de Dama")
        self.assertEqual(r0["license"], "Open Access (CC0)")
        self.assertTrue(r0["thumb_url"].endswith("small.jpg"))

    def test_keyed_providers_send_key_header_and_normalize(self):
        cases = [
            ("pexels", "https://api.pexels.com/v1/search",
             {"photos": [{"id": 5, "alt": "Escritório", "photographer": "Ana",
                          "url": "https://www.pexels.com/photo/5",
                          "src": {"original": "https://images.pexels.com/o.jpg",
                                  "medium": "https://images.pexels.com/m.jpg"},
                          "width": 1920, "height": 1080}],
              "total_results": 1},
             "k-x"),
            ("unsplash", "https://api.unsplash.com/search/photos",
             {"total": 3, "results": [{
                 "id": "u1", "alt_description": "Reunião",
                 "user": {"name": "Bia"},
                 "links": {"html": "https://unsplash.com/photos/u1"},
                 "urls": {"full": "https://images.unsplash.com/full",
                          "small": "https://images.unsplash.com/small"},
                 "width": 4000, "height": 3000}]},
             "Client-ID k-x"),
            ("pixabay", "https://pixabay.com/api/",
             {"totalHits": 9, "hits": [{
                 "id": 77, "tags": "finanças, escritório", "user": "Cato",
                 "pageURL": "https://pixabay.com/photos/77/",
                 "largeImageURL": "https://cdn.pixabay.com/l.jpg",
                 "webformatURL": "https://cdn.pixabay.com/w.jpg",
                 "imageWidth": 1280, "imageHeight": 720}]}, None),
            ("freepik", "https://api.freepik.com/v1/resources/images",
             {"total": 4, "data": [{
                 "id": "f9", "title": "Equipa corporativa",
                 "author": "Duda", "url": "https://www.freepik.com/free/f9",
                 "image": {"src": "https://img.freepik.com/f9.jpg",
                           "thumbnail": "https://img.freepik.com/t.jpg"},
                 "width": 1600, "height": 1200}]}, None),
        ]
        for provider, url, payload, extra_header in cases:
            with patch("dashboard.imagebank._bank_key", return_value="k-x"), \
                 patch("dashboard.imagebank._get",
                       return_value=_http(payload)) as get:
                out = imagebank.search("negócios", provider)
            self.assertEqual(get.call_args.args[0], url, provider)
            headers = get.call_args.kwargs.get("headers") or {}
            if extra_header:
                self.assertEqual(headers.get("Authorization"), extra_header,
                                 provider)
            if provider == "freepik":
                self.assertEqual(headers.get("x-freepik-api-key"), "k-x")
            if provider == "pixabay":
                self.assertEqual(get.call_args.kwargs["params"].get("key"),
                                 "k-x")
            r0 = out["results"][0]
            self.assertTrue(r0["url"], provider)
            self.assertEqual(r0["provider"], provider)

    def test_provider_without_key_raises_with_hint(self):
        with patch("dashboard.imagebank._bank_key", return_value=""):
            with self.assertRaises(RuntimeError) as ctx:
                imagebank.search("x", "pexels")
        self.assertIn("AUDIT_PEXELS_API_KEY", str(ctx.exception))

    def test_unknown_provider_and_empty_query(self):
        with self.assertRaises(RuntimeError):
            imagebank.search("x", "shutterstock")
        with self.assertRaises(RuntimeError):
            imagebank.search("  ", "openverse")

    def test_provider_status_shape(self):
        with patch("dashboard.imagebank._bank_key", return_value=""):
            st = imagebank.provider_status()
        ids = {p["id"]: p for p in st}
        self.assertFalse(ids["openverse"]["needs_key"])
        self.assertTrue(ids["openverse"]["configured"])
        self.assertFalse(ids["met"]["needs_key"])
        self.assertTrue(ids["met"]["configured"])
        self.assertFalse(ids["freepik"]["configured"])
        self.assertIs(ids["freepik"]["needs_key"], True)


# ---------------------------------------------------------------------------
# Credenciais dos bancos de imagens na BD (Fernet)
# ---------------------------------------------------------------------------
class BankCredentialsTest(TestCase):
    def test_save_and_resolve_pexels_key(self):
        row = ai_credentials.save_slot("pexels", api_key="pxk_secret_123",
                                       updated_by="t")
        self.assertEqual(row.slot, "pexels")
        self.assertTrue(row.api_key.startswith("enc:v1:"))
        cfg = ai_credentials.resolve_slot("pexels")
        self.assertEqual(cfg["api_key"], "pxk_secret_123")
        self.assertEqual(cfg["source"], "db")
        st = ai_credentials.public_status()["pexels"]
        self.assertTrue(st["configured"])
        self.assertEqual(st["masked"], "px…")

    def test_bank_slot_rejects_invalid(self):
        with self.assertRaises(ValueError):
            ai_credentials.save_slot("shutterstock", api_key="x")


# ---------------------------------------------------------------------------
# Endpoints /ai/bank/*
# ---------------------------------------------------------------------------
class BankViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt",
                                role="viewer")
        cls.auditor = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.auditor, user_id="a@x.pt",
                                role="auditor")

    def _client(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return c

    # --- providers / search ---
    def test_providers_requires_auth(self):
        self.assertEqual(
            APIClient().get("/django/api/ai/bank/providers").status_code, 403)

    def test_providers_ok(self):
        with patch("dashboard.imagebank._bank_key", return_value=""):
            r = self._client(self.viewer).get("/django/api/ai/bank/providers")
        self.assertEqual(r.status_code, 200)
        ids = [p["id"] for p in r.json()["providers"]]
        self.assertEqual(sorted(ids), sorted(["openverse", "wikimedia", "met",
                                              "pexels", "unsplash", "pixabay",
                                              "freepik"]))
        self.assertEqual(len(ids), 7)

    def test_search_requires_auth(self):
        self.assertEqual(
            APIClient().get("/django/api/ai/bank/search?q=x").status_code, 403)

    def test_search_unknown_provider_400(self):
        r = self._client(self.viewer).get(
            "/django/api/ai/bank/search?q=x&provider=nada")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Provedor", r.json()["error"])

    def test_search_openverse_ok(self):
        payload = {"result_count": 1, "results": [{
            "id": "z1", "title": "Gráfico", "creator": "Ana",
            "license": "by", "license_version": "4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "foreign_landing_url": "https://ov.org/z1",
            "url": "https://example.org/z1.jpg",
            "thumbnail": "https://api.openverse.org/v1/images/z1/thumb/",
            "width": 800, "height": 600}]}
        with patch("dashboard.imagebank._get",
                   return_value=_http(payload)) as get:
            r = self._client(self.viewer).get(
                "/django/api/ai/bank/search?q=gráfico&provider=openverse")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["result_count"], 1)
        self.assertEqual(body["results"][0]["image_id"], "z1")
        self.assertTrue(str(get.call_args.kwargs["params"]["q"])
                        .startswith("gr"))

    def test_search_keyed_provider_without_key_400(self):
        with patch("dashboard.imagebank._bank_key", return_value=""):
            r = self._client(self.viewer).get(
                "/django/api/ai/bank/search?q=x&provider=freepik")
        self.assertEqual(r.status_code, 400)
        self.assertIn("AUDIT_FREEPIK_API_KEY", r.json()["error"])

    # --- save ---
    def _save_payload(self, **over):
        p = {"provider": "openverse", "image_id": "z1",
             "title": "Gráfico", "author": "Ana", "license": "CC BY 4.0",
             "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "landing_url": "https://ov.org/z1", "query": "gráfico",
             "source_url": "https://example.org/z1.jpg",
             "thumb_url": "https://example.org/z1_t.jpg",
             "width": 800, "height": 600}
        p.update(over)
        return p

    def test_save_requires_auth(self):
        self.assertEqual(
            APIClient().post("/django/api/ai/bank/save", {},
                             format="json").status_code, 403)

    def test_save_validations(self):
        c = self._client(self.viewer)
        r = c.post("/django/api/ai/bank/save",
                   self._save_payload(provider="nada"), format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/django/api/ai/bank/save",
                   self._save_payload(image_id=""), format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/django/api/ai/bank/save",
                   self._save_payload(source_url="ftp://x/y.jpg"),
                   format="json")
        self.assertEqual(r.status_code, 400)

    def test_save_download_failure_502(self):
        with patch("dashboard.imagebank.download_image",
                   side_effect=RuntimeError("HTTP 404.")):
            r = self._client(self.viewer).post(
                "/django/api/ai/bank/save", self._save_payload(),
                format="json")
        self.assertEqual(r.status_code, 502)
        self.assertIn("404", r.json()["error"])

    def test_save_happy_path_duplicate_and_gallery(self):
        with patch("dashboard.imagebank.download_image",
                   side_effect=[(PNG, "image/png", "png"),
                                (PNG, "image/png", "png")]):
            r = self._client(self.viewer).post(
                "/django/api/ai/bank/save", self._save_payload(),
                format="json")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["duplicate"])
        img = body["image"]
        self.assertEqual(img["provider"], "openverse")
        self.assertEqual(img["license"], "CC BY 4.0")
        self.assertEqual(img["file_size"], len(PNG))
        pk = img["id"]
        record = StockImage.objects.get(pk=pk)
        self.assertTrue(record.file.name.endswith(".png"))
        self.assertTrue(record.thumb.name.endswith(".png"))

        # duplicado → mesmo id, sem nova descarga
        with patch("dashboard.imagebank.download_image") as dl:
            r2 = self._client(self.viewer).post(
                "/django/api/ai/bank/save", self._save_payload(),
                format="json")
        self.assertTrue(r2.json()["duplicate"])
        self.assertEqual(r2.json()["image"]["id"], pk)
        dl.assert_not_called()

        # galeria
        r3 = self._client(self.viewer).get("/django/api/ai/bank/images")
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["count"], 1)
        self.assertEqual(r3.json()["images"][0]["id"], pk)

        # ficheiro: thumb por omissão, full com ?full=1
        c = self._client(self.viewer)
        r4 = c.get(f"/django/api/ai/bank/images/{pk}/file")
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4["Content-Type"], "image/png")
        r5 = c.get(f"/django/api/ai/bank/images/{pk}/file?full=1")
        self.assertEqual(r5.status_code, 200)
        self.assertEqual(r5["Content-Type"], "image/png")

    def test_file_404(self):
        r = self._client(self.viewer).get("/django/api/ai/bank/images/999/file")
        self.assertEqual(r.status_code, 404)

    def test_file_serves_full_when_thumb_missing_on_disk(self):
        """Thumb perdido no disco (ex.: restauro de backup) não quebra a
        galeria — o endpoint serve o original automaticamente."""
        import os
        with patch("dashboard.imagebank.download_image",
                   side_effect=[(PNG, "image/png", "png"),
                                (PNG, "image/png", "png")]):
            img = self._client(self.viewer).post(
                "/django/api/ai/bank/save", self._save_payload(),
                format="json").json()
        pk = img["image"]["id"]
        record = StockImage.objects.get(pk=pk)
        self.assertTrue(record.thumb)
        os.remove(record.thumb.path)  # thumb some do disco, campo fica na BD
        c = self._client(self.viewer)
        r = c.get(f"/django/api/ai/bank/images/{pk}/file")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(b"".join(r.streaming_content), PNG)
        r2 = c.get(f"/django/api/ai/bank/images/{pk}/file?full=1")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2["Content-Type"], "image/png")

    # --- delete ---
    def test_delete_requires_auditor(self):
        with patch("dashboard.imagebank.download_image",
                   side_effect=[(PNG, "image/png", "png")]):
            img = self._client(self.viewer).post(
                "/django/api/ai/bank/save",
                self._save_payload(thumb_url=""), format="json").json()
        pk = img["image"]["id"]
        self.assertEqual(
            self._client(self.viewer).delete(
                f"/django/api/ai/bank/images/{pk}").status_code, 403)
        self.assertEqual(
            self._client(self.auditor).delete(
                f"/django/api/ai/bank/images/{pk}").status_code, 200)
        self.assertFalse(StockImage.objects.filter(pk=pk).exists())
        self.assertEqual(
            self._client(self.auditor).delete(
                f"/django/api/ai/bank/images/{pk}").status_code, 404)


# ---------------------------------------------------------------------------
# Capa do PDF também aceita imagem do banco (StockImage)
# ---------------------------------------------------------------------------
class CoverFallbackTest(TestCase):
    def test_cover_image_bytes_from_stock(self):
        from django.core.files.base import ContentFile
        record = StockImage(provider="wikimedia", provider_image_id="9",
                            title="Capa", license="CC0")
        record.file.save("capa_test.png", ContentFile(PNG), save=True)
        self.assertEqual(ai_nim_views.cover_image_bytes(record.pk), PNG)

    def test_cover_fallback_none_for_unknown(self):
        self.assertIsNone(ai_nim_views.cover_image_bytes(424242))
        self.assertIsNone(ai_nim_views.cover_image_bytes(None))
