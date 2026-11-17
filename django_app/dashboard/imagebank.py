"""Banco de imagens — busca real estilo Freepik/Pexels dentro da plataforma.

Provedores suportados:
- openverse  (sem chave — Openverse/WordPress; imagens com licenças CC/abertas)
- wikimedia  (sem chave — Wikimedia Commons; licenças livres)
- pexels / unsplash / pixabay / freepik
    (requerem chave própria do utilizador — guardada cifrada na BD via
     AiCredential slot, ou em env AUDIT_<PROVEDOR>_API_KEY)

Todos os resultados são normalizados para o mesmo formato:
    {provider, image_id, title, author, license, license_url, landing_url,
     url (original), thumb_url, width, height}

A guarda em galeria (StockImage) descarrega o ficheiro para o servidor —
a plataforma deixa de depender do site de origem (o hotspot pode expirar).

Limites de segurança: pedidos com timeout, User-Agent identificável,
descarga com teto de bytes (25 MB) e validação de content-type/magic bytes.
"""
import logging
import re
import time

import requests

from . import ai_credentials

logger = logging.getLogger(__name__)

UA = "AuditAI-Omni/1.0 (banco de imagens interno; contacto: admin local)"
SEARCH_TIMEOUT = 20
DOWNLOAD_TIMEOUT = 45
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

QUERY_MAX = 300
PAGE_MIN, PAGE_MAX = 1, 50
PSIZE_MIN, PSIZE_MAX, PSIZE_DEFAULT = 4, 40, 20

NO_KEY_MSG = ("Chave do provedor {p} não configurada — guarda-a em "
              "Integrações → AI Control Plane (slot '{slot}') ou env {env}.")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text):
    """Remove etiquetas HTML de campos como Artist do Wikimedia Commons."""
    if not text:
        return ""
    return _TAG_RE.sub("", str(text)).strip()


def _fmt_license(name, version=None):
    name = (name or "").strip()
    if not name:
        return ""
    version = (version or "").strip()
    return f"{name} {version}".strip() if version else name


def _bank_key(provider):
    """Chave do provedor na BD (cifrada) com fallback env — nunca lança."""
    try:
        return (ai_credentials.resolve_slot(provider).get("api_key") or "").strip()
    except Exception:
        return ""


def _get(url, **kwargs):
    """GET com UA identificável e 1 retry com backoff (403/429/5xx e rede)."""
    kwargs.setdefault("headers", {})
    kwargs["headers"].setdefault("User-Agent", UA)
    kwargs["headers"].setdefault("Accept", "application/json")
    kwargs.setdefault("timeout", SEARCH_TIMEOUT)
    for attempt in (1, 2):
        try:
            r = requests.get(url, **kwargs)
            if r.status_code in (403, 429, 500, 502, 503, 504) and attempt == 1:
                time.sleep(1.2)
                continue
            return r
        except requests.RequestException:
            if attempt == 1:
                time.sleep(1.2)
                continue
            raise
    return r  # inatingível (loop termina antes)


# ---------------------------------------------------------------------------
# Provedores sem chave
# ---------------------------------------------------------------------------
def search_openverse(query, page, page_size, api_key=None):
    """Openverse (api.openverse.org) — milhões de imagens CC sem chave."""
    r = _get("https://api.openverse.org/v1/images/",
             params={"q": query, "page": page, "page_size": page_size})
    r.raise_for_status()
    data = r.json()
    results = []
    for it in data.get("results", []):
        results.append({
            "provider": "openverse",
            "image_id": str(it.get("id") or ""),
            "title": strip_html(it.get("title"))[:300],
            "author": strip_html(it.get("creator"))[:200],
            "license": _fmt_license(it.get("license"),
                                    it.get("license_version"))[:64],
            "license_url": (it.get("license_url") or "")[:300],
            "landing_url": (it.get("foreign_landing_url") or "")[:500],
            "url": it.get("url") or "",
            "thumb_url": it.get("thumbnail") or it.get("url") or "",
            "width": it.get("width"), "height": it.get("height"),
        })
    return data.get("result_count"), results


def search_wikimedia(query, page, page_size, api_key=None):
    """Wikimedia Commons — API pública, sem chave, licenças livres."""
    limit = max(1, min(50, page_size))
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": limit, "gsroffset": (page - 1) * limit,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata",
        "iiurlwidth": 480, "origin": "*",
    }
    r = _get("https://commons.wikimedia.org/w/api.php", params=params)
    r.raise_for_status()
    pages = ((r.json().get("query") or {}).get("pages") or {})
    results = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}

        def _meta(field):
            return strip_html((meta.get(field) or {}).get("value"))
        results.append({
            "provider": "wikimedia",
            "image_id": str(p.get("pageid") or ""),
            "title": strip_html(p.get("title"))[:300],
            "author": _meta("Artist")[:200],
            "license": _fmt_license(_meta("LicenseShortName"))[:64],
            "license_url": (_meta("LicenseUrl") or "")[:300],
            "landing_url": (info.get("descriptionurl") or "")[:500],
            "url": info.get("url") or "",
            "thumb_url": info.get("thumburl") or info.get("url") or "",
            "width": info.get("width"), "height": info.get("height"),
        })
    return len(results), results


# ---------------------------------------------------------------------------
# Provedores com chave
# ---------------------------------------------------------------------------
def search_pexels(query, page, page_size, api_key):
    r = _get("https://api.pexels.com/v1/search",
             params={"query": query, "page": page, "per_page": page_size},
             headers={"Authorization": api_key})
    r.raise_for_status()
    data = r.json()
    results = []
    for it in data.get("photos", []):
        src = it.get("src") or {}
        results.append({
            "provider": "pexels",
            "image_id": str(it.get("id") or ""),
            "title": strip_html(it.get("alt"))[:300],
            "author": strip_html(it.get("photographer"))[:200],
            "license": "Pexels License"[:64],
            "license_url": "https://www.pexels.com/license/"[:300],
            "landing_url": (it.get("url") or "")[:500],
            "url": src.get("original") or "",
            "thumb_url": src.get("medium") or src.get("small") or "",
            "width": it.get("width"), "height": it.get("height"),
        })
    return data.get("total_results"), results


def search_unsplash(query, page, page_size, api_key):
    r = _get("https://api.unsplash.com/search/photos",
             params={"query": query, "page": page, "per_page": page_size},
             headers={"Authorization": f"Client-ID {api_key}"})
    r.raise_for_status()
    data = r.json()
    results = []
    for it in data.get("results", []):
        urls = it.get("urls") or {}
        results.append({
            "provider": "unsplash",
            "image_id": str(it.get("id") or ""),
            "title": strip_html(it.get("description")
                                or it.get("alt_description"))[:300],
            "author": strip_html((it.get("user") or {}).get("name"))[:200],
            "license": "Unsplash License"[:64],
            "license_url": "https://unsplash.com/license"[:300],
            "landing_url": ((it.get("links") or {}).get("html") or "")[:500],
            "url": urls.get("full") or urls.get("regular") or "",
            "thumb_url": urls.get("small") or urls.get("thumb") or "",
            "width": it.get("width"), "height": it.get("height"),
        })
    return data.get("total"), results


def search_pixabay(query, page, page_size, api_key):
    r = _get("https://pixabay.com/api/",
             params={"key": api_key, "q": query, "page": page,
                     "per_page": max(3, min(50, page_size))})
    r.raise_for_status()
    data = r.json()
    results = []
    for it in data.get("hits", []):
        results.append({
            "provider": "pixabay",
            "image_id": str(it.get("id") or ""),
            "title": strip_html(it.get("tags"))[:300],
            "author": strip_html(it.get("user"))[:200],
            "license": "Pixabay Content License"[:64],
            "license_url":
                "https://pixabay.com/service/license-summary/"[:300],
            "landing_url": (it.get("pageURL") or "")[:500],
            "url": it.get("largeImageURL") or it.get("webformatURL") or "",
            "thumb_url": it.get("webformatURL") or it.get("previewURL") or "",
            "width": it.get("imageWidth"), "height": it.get("imageHeight"),
        })
    return data.get("totalHits"), results


def search_freepik(query, page, page_size, api_key):
    r = _get("https://api.freepik.com/v1/resources/images",
             params={"query": query, "page": page, "limit": page_size},
             headers={"x-freepik-api-key": api_key})
    r.raise_for_status()
    data = r.json()
    results = []
    for it in data.get("data", []):
        image = it.get("image") or {}
        # shape defensivo: a Freepik usa image.source[0].src noutras versões
        url = image.get("src") or ""
        thumb = image.get("thumbnail") or ""
        for src in (image.get("source") or []):
            src_url = (src or {}).get("src") or (src or {}).get("url") or ""
            url = url or src_url
        for tb in (image.get("thumbnails") or []):
            thumb = thumb or (tb or {}).get("src") or ""
        results.append({
            "provider": "freepik",
            "image_id": str(it.get("id") or ""),
            "title": strip_html(it.get("title") or it.get("name"))[:300],
            "author": strip_html(it.get("author") or "")[:200],
            "license": "Freepik License"[:64],
            "license_url": "https://www.freepik.com/company/terms"[:300],
            "landing_url": (it.get("url") or "")[:500],
            "url": url, "thumb_url": thumb or url,
            "width": it.get("width"), "height": it.get("height"),
        })
    return data.get("total") or len(results), results


def search_met(query, page, page_size, api_key=None):
    """Metropolitan Museum of Art — Open Access CC0, sem chave.
    API v1.1 (Elastic): busca paginada com offset/limit; o detalhe do objeto
    continua em /v1/objects/{id}. Objetos sem imagem são saltados."""
    limit = max(1, min(50, page_size))
    r = _get("https://collectionapi.metmuseum.org/public/collection/v1.1/"
             "search",
             params={"q": query, "hasImages": "true", "limit": limit,
                     "offset": (page - 1) * limit})
    r.raise_for_status()
    data = r.json()
    ids = data.get("objectIDs") or []
    results = []
    for oid in ids:
        try:
            ro = _get(f"https://collectionapi.metmuseum.org/public/collection/"
                      f"v1/objects/{oid}")
            if ro.status_code != 200:
                continue
            o = ro.json()
            img = o.get("primaryImage") or o.get("primaryImageSmall") or ""
            if not str(img).startswith("http"):
                continue
            results.append({
                "provider": "met",
                "image_id": str(oid),
                "title": strip_html(o.get("title"))[:300],
                "author": (strip_html(o.get("artistDisplayName"))
                           or "The Metropolitan Museum of Art")[:200],
                "license": "Open Access (CC0)"[:64],
                "license_url":
                    "https://www.metmuseum.org/about-the-met/policies-and-"
                    "documents/open-access"[:300],
                "landing_url": (o.get("objectURL") or "")[:500],
                "url": img,
                "thumb_url": o.get("primaryImageSmall") or img,
                "width": None, "height": None,
            })
        except Exception:
            continue  # objeto individual nunca derruba a busca
    return data.get("total") or len(results), results


# ---------------------------------------------------------------------------
# Registo de provedores
# ---------------------------------------------------------------------------
PROVIDERS = {
    # met primeiro: API estável, CC0, sem chave — melhor experiência por omissão
    "met": {"label": "Met Museum (domínio público, sem chave)",
            "needs_key": False, "search": search_met},
    "openverse": {"label": "Openverse (CC, sem chave)", "needs_key": False,
                  "search": search_openverse},
    "wikimedia": {"label": "Wikimedia Commons (sem chave)", "needs_key": False,
                  "search": search_wikimedia},
    "pexels": {"label": "Pexels", "needs_key": True,
               "env": "AUDIT_PEXELS_API_KEY", "search": search_pexels},
    "unsplash": {"label": "Unsplash", "needs_key": True,
                 "env": "AUDIT_UNSPLASH_API_KEY", "search": search_unsplash},
    "pixabay": {"label": "Pixabay", "needs_key": True,
                "env": "AUDIT_PIXABAY_API_KEY", "search": search_pixabay},
    "freepik": {"label": "Freepik", "needs_key": True,
                "env": "AUDIT_FREEPIK_API_KEY", "search": search_freepik},
}
PROVIDER_IDS = tuple(PROVIDERS)


def search(query, provider="openverse", page=1, page_size=PSIZE_DEFAULT):
    """Busca normalizada. Lança RuntimeError com mensagem pt em falha de uso
    (provedor desconhecido / sem chave / erro do provedor)."""
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise RuntimeError(f"Provedor desconhecido: '{provider}'. "
                           f"Disponíveis: {', '.join(PROVIDER_IDS)}.")
    query = (query or "").strip()
    if not query:
        raise RuntimeError("Escreve um termo de busca.")
    if len(query) > QUERY_MAX:
        raise RuntimeError(f"Busca máxima {QUERY_MAX} caracteres.")
    page = max(PAGE_MIN, min(PAGE_MAX, int(page or 1)))
    page_size = max(PSIZE_MIN, min(PSIZE_MAX, int(page_size or PSIZE_DEFAULT)))

    cfg = PROVIDERS[provider]
    api_key = _bank_key(provider)
    if cfg["needs_key"] and not api_key:
        raise RuntimeError(NO_KEY_MSG.format(p=cfg["label"], slot=provider,
                                             env=cfg.get("env", "")))
    try:
        count, results = cfg["search"](query, page, page_size,
                                       api_key=api_key)
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("bank search %s falhou: %s", provider, e)
        raise RuntimeError(f"Falha a buscar no provedor {cfg['label']}: "
                           f"{str(e)[:180]}")
    results = [r for r in results if r.get("url")]
    return {"provider": provider, "query": query, "page": page,
            "page_size": page_size, "result_count": count,
            "results": results}


def provider_status():
    """Estado seguro dos provedores para o frontend (chave mascarada)."""
    out = []
    for pid, cfg in PROVIDERS.items():
        key = _bank_key(pid)
        out.append({
            "id": pid, "label": cfg["label"], "needs_key": cfg["needs_key"],
            "configured": (not cfg["needs_key"]) or bool(key),
            "masked": ai_credentials.mask_key(key) if key else "",
        })
    return out


# ---------------------------------------------------------------------------
# Descarga de imagem (guarda em galeria)
# ---------------------------------------------------------------------------
_MAGIC = (  # (assinatura, extensão)
    (b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"RIFF", "webp"),  # RIFF….WEBP verificado abaixo
)


def sniff_ext(content_type, data):
    """Extensão a partir de magic bytes / content-type. '' se não-imagem."""
    for sig, ext in _MAGIC:
        if data[:len(sig)] == sig:
            if ext == "webp" and data[8:12] != b"WEBP":
                continue
            return ext
    if data[:4] in (b"<svg", b"<?xm") or b"<svg" in data[:512]:
        return "svg"
    ct = (content_type or "").split(";")[0].strip().lower()
    return {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
            "image/webp": "webp", "image/svg+xml": "svg",
            "image/tiff": "tif"}.get(ct, "")


def download_image(url, max_bytes=MAX_DOWNLOAD_BYTES):
    """Descarrega (stream, com teto) e devolve (bytes, content_type, ext).
    Lança RuntimeError com mensagem pt em falha (rede / não-imagem / grande)."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        raise RuntimeError("URL da imagem inválido (só http/https).")
    if len(str(url)) > 2048:
        raise RuntimeError("URL demasiado longo.")
    try:
        # Accept de imagem (metmuseum devolve 406 a Accept: application/json)
        r = _get(str(url), timeout=DOWNLOAD_TIMEOUT, stream=True,
                 headers={"User-Agent": UA,
                          "Accept": "image/*,*/*;q=0.8"})
    except Exception as e:
        raise RuntimeError(f"Descarga falhou: {str(e)[:180]}")
    if r.status_code != 200:
        raise RuntimeError(f"Descarga falhou: HTTP {r.status_code}.")
    content_type = r.headers.get("Content-Type", "")
    chunks, total = [], 0
    try:
        for chunk in r.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(
                    f"Imagem excede o limite de {max_bytes // (1024 * 1024)} MB.")
            chunks.append(chunk)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Descarga interrompida: {str(e)[:180]}")
    data = b"".join(chunks)
    ext = sniff_ext(content_type, data[:64])
    if not ext or not data:
        raise RuntimeError("O URL não devolveu uma imagem válida.")
    return data, content_type.split(";")[0].strip(), ext
