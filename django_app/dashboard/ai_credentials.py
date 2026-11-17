"""Credenciais de IA encriptadas na base de dados (Fernet) — NVIDIA NIM.

Cada "slot" (text/vision/image) guarda a chave de API cifrada com Fernet
(derivação sha256(AUDIT_DJANGO_SECRET_KEY) → chave urlsafe de 32 bytes; o
cifrado é guardado com o prefixo "enc:v1:"). O modelo e o base_url do slot
também podem ser personalizados sem reinício.

Ordem de resolução (`resolve_slot`):  BD → variáveis de ambiente → vazio.
Os módulos clientes (llm_client/nvidia_client) mantêm o seu próprio fallback
de módulo para compatibilidade com testes e instalações via env.

Segurança: a chave completa nunca sai do servidor — os endpoints devolvem
apenas a versão mascarada (`mask_key`, primeiros 9 + … + últimos 4).
"""
import base64
import hashlib
import logging

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from django.utils import timezone

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:v1:"

# Defaults por slot: nomes de env da chave/modelo/base + valores por omissão.
SLOT_DEFAULTS = {
    "text": {
        "label": "Texto (Nemotron)",
        "key_envs": ["AUDIT_NVIDIA_API_KEY", "NVIDIA_API_KEY"],
        "model_env": "AUDIT_NVIDIA_MODEL",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "base_env": "AUDIT_NVIDIA_BASE_URL",
        "base_url": "https://integrate.api.nvidia.com/v1",
    },
    "vision": {
        "label": "Visão (omni — imagem/vídeo)",
        "key_envs": ["AUDIT_NIM_VISION_API_KEY", "NVIDIA_VISION_API_KEY",
                     "NVIDIA_API_KEY"],
        "model_env": "AUDIT_NIM_VISION_MODEL",
        "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "base_env": "AUDIT_NVIDIA_BASE_URL",
        "base_url": "https://integrate.api.nvidia.com/v1",
    },
    "image": {
        "label": "Imagens (FLUX.2-klein-4B)",
        "key_envs": ["AUDIT_NIM_IMAGE_API_KEY", "NVIDIA_IMAGE_API_KEY",
                     "NVIDIA_API_KEY"],
        "model_env": "AUDIT_NIM_IMAGE_MODEL",
        "model": "black-forest-labs/flux.2-klein-4b",
        "base_env": "AUDIT_NIM_IMAGE_BASE_URL",
        "base_url": "https://ai.api.nvidia.com/v1/genai",
    },
    # Bancos de imagens — só precisam de chave (sem model/base editáveis).
    # openverse/wikimedia não exigem chave e nem aparecem aqui.
    "pexels": {
        "label": "Banco: Pexels",
        "key_envs": ["AUDIT_PEXELS_API_KEY", "PEXELS_API_KEY"],
        "model_env": "", "model": "",
        "base_env": "", "base_url": "https://api.pexels.com/v1",
    },
    "unsplash": {
        "label": "Banco: Unsplash",
        "key_envs": ["AUDIT_UNSPLASH_API_KEY", "UNSPLASH_ACCESS_KEY"],
        "model_env": "", "model": "",
        "base_env": "", "base_url": "https://api.unsplash.com",
    },
    "pixabay": {
        "label": "Banco: Pixabay",
        "key_envs": ["AUDIT_PIXABAY_API_KEY", "PIXABAY_API_KEY"],
        "model_env": "", "model": "",
        "base_env": "", "base_url": "https://pixabay.com/api",
    },
    "freepik": {
        "label": "Banco: Freepik",
        "key_envs": ["AUDIT_FREEPIK_API_KEY", "FREEPIK_API_KEY"],
        "model_env": "", "model": "",
        "base_env": "", "base_url": "https://api.freepik.com/v1",
    },
}

VALID_SLOTS = tuple(SLOT_DEFAULTS)


# ---------------------------------------------------------------------------
# Cifra Fernet (sem dependência em tempo de import — cryptography é lazy)
# ---------------------------------------------------------------------------
def _fernet():
    from cryptography.fernet import Fernet
    secret = str(settings.SECRET_KEY or "change-me").encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    """Cifra com prefixo 'enc:v1:'. Valores já cifrados não são re-cifrados."""
    if not value or str(value).startswith(ENC_PREFIX):
        return value or ""
    token = _fernet().encrypt(str(value).encode("utf-8"))
    return ENC_PREFIX + token.decode("ascii")


def decrypt_secret(value):
    """Decifra 'enc:v1:…'. Valores sem prefixo passam através (legado/env).
    Cifrado corrompido → '' (a chave errada nunca é enviada a montante)."""
    if not value:
        return ""
    value = str(value)
    if not value.startswith(ENC_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(ENC_PREFIX):].encode("ascii")
                                 ).decode("utf-8")
    except Exception:
        logger.warning("credencial IA com cifrado inválido — a ignorar")
        return ""


def mask_key(value):
    """Versão para ecrã: primeiros 9 + … + últimos 4. Vazio → ''."""
    if not value:
        return ""
    value = str(value)
    if len(value) <= 16:
        return value[:2] + "…" if len(value) > 4 else "…"
    return value[:9] + "…" + value[-4:]


# ---------------------------------------------------------------------------
# Resolução e persistência
# ---------------------------------------------------------------------------
def _slot_row(slot):
    from .models import AiCredential
    return AiCredential.objects.filter(slot=slot).first()


def _env_cfg(slot):
    d = SLOT_DEFAULTS[slot]
    key = ""
    for env_name in d["key_envs"]:
        key = (os_env(env_name) or "").strip()
        if key:
            break
    model = (os_env(d["model_env"]) or "").strip() if d.get("model_env") else ""
    base = (os_env(d["base_env"]) or "").strip() if d.get("base_env") else ""
    return key, model, base


def os_env(name):
    import os
    return os.environ.get(name, "")


def resolve_slot(slot):
    """Config efetiva do slot: {'slot','api_key','model','base_url','source'}.
    source: 'db' (credencial encriptada na BD) ou 'env' (fallback) ou ''
    (nada configurado). Nunca lança — falha de BD devolve env/módulo vazio."""
    d = SLOT_DEFAULTS.get(slot)
    if not d:
        return {"slot": slot, "api_key": "", "model": "", "base_url": "",
                "source": ""}
    try:
        row = _slot_row(slot)
    except (OperationalError, ProgrammingError):
        row = None
    if row:
        key = decrypt_secret(row.api_key)
        if key:
            return {"slot": slot, "api_key": key,
                    "model": (row.model or d["model"]).strip(),
                    "base_url": (row.base_url or d["base_url"]).strip(),
                    "source": "db"}
    key, model, base = _env_cfg(slot)
    if key:
        return {"slot": slot, "api_key": key,
                "model": model or d["model"], "base_url": base or d["base_url"],
                "source": "env"}
    return {"slot": slot, "api_key": "", "model": model or d["model"],
            "base_url": base or d["base_url"], "source": ""}


def save_slot(slot, *, api_key=None, model=None, base_url=None, updated_by=""):
    """Cria/atualiza o slot. api_key="" limpa a credencial (passa a usar env);
    api_key=None mantém a atual. Devolve o AiCredential."""
    from .models import AiCredential
    if slot not in VALID_SLOTS:
        raise ValueError(f"slot inválido: {slot}")
    row = _slot_row(slot)
    if row is None:
        row = AiCredential(slot=slot)
    if api_key is not None:
        row.api_key = encrypt_secret(api_key) if api_key else ""
    if model is not None:
        row.model = model.strip()[:200]
    if base_url is not None:
        row.base_url = base_url.strip()[:300]
    row.updated_by = (updated_by or "")[:150]
    row.updated_at = timezone.now()
    row.save()
    return row


def public_status():
    """Resumo seguro dos slots (chave mascarada, sem segredo) para endpoints."""
    out = {}
    for slot in VALID_SLOTS:
        cfg = resolve_slot(slot)
        d = SLOT_DEFAULTS[slot]
        out[slot] = {
            "label": d["label"],
            "configured": bool(cfg["api_key"]),
            "masked": mask_key(cfg["api_key"]),
            "model": cfg["model"],
            "base_url": cfg["base_url"],
            "source": cfg["source"],
        }
    return out
