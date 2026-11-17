"""Cliente NVIDIA NIM — visão (nemotron omni) e geração de imagens (FLUX.2).

Configuração por slot da BD (dashboard.ai_credentials) com fallback para env/
constantes de módulo:

- Visão  — POST {base}/chat/completions com mensagens multimodais
           (image_url | video_url) no modelo omni reasoning; o raciocínio
           (reasoning_content) é descartado, só a resposta final regressa.
- Imagem — POST {base}/{model} (ex.: …/genai/black-forest-labs/flux.2-klein-4b)
           devolve {"artifacts":[{"base64": …, "finishReason": …}]} (JPEG).
"""
import logging
import os
import time

import requests

from . import ai_credentials

logger = logging.getLogger(__name__)

# Defaults de módulo (env → valor fixo); a BD ganha sempre quando existir.
VISION_MODEL = os.environ.get(
    "AUDIT_NIM_VISION_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
VISION_BASE_URL = os.environ.get(
    "AUDIT_NIM_VISION_BASE_URL",
    os.environ.get("AUDIT_NVIDIA_BASE_URL",
                   "https://integrate.api.nvidia.com/v1")).rstrip("/")
IMAGE_MODEL = os.environ.get(
    "AUDIT_NIM_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
IMAGE_BASE_URL = os.environ.get(
    "AUDIT_NIM_IMAGE_BASE_URL", "https://ai.api.nvidia.com/v1/genai").rstrip("/")

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")


def _vision_cfg():
    try:
        cfg = ai_credentials.resolve_slot("vision")
        if cfg.get("api_key"):
            return cfg
    except Exception:  # BD indisponível (ex.: SimpleTestCase) → fallback
        pass
    key = (os.environ.get("AUDIT_NIM_VISION_API_KEY")
           or os.environ.get("NVIDIA_VISION_API_KEY")
           or os.environ.get("AUDIT_NVIDIA_API_KEY")
           or os.environ.get("NVIDIA_API_KEY", ""))
    return {"slot": "vision", "api_key": key, "model": VISION_MODEL,
            "base_url": VISION_BASE_URL, "source": "module"}


def _image_cfg():
    try:
        cfg = ai_credentials.resolve_slot("image")
        if cfg.get("api_key"):
            return cfg
    except Exception:
        pass
    key = (os.environ.get("AUDIT_NIM_IMAGE_API_KEY")
           or os.environ.get("NVIDIA_IMAGE_API_KEY")
           or os.environ.get("AUDIT_NVIDIA_API_KEY")
           or os.environ.get("NVIDIA_API_KEY", ""))
    return {"slot": "image", "api_key": key, "model": IMAGE_MODEL,
            "base_url": IMAGE_BASE_URL, "source": "module"}


def detect_media_type(url):
    """'video' se a extensão do URL for de vídeo, senão 'image'."""
    path = str(url or "").split("?")[0].lower()
    if path.endswith(VIDEO_EXTS):
        return "video"
    return "image"


# ---------------------------------------------------------------------------
# Visão — compreensão de imagem/vídeo (omni reasoning)
# ---------------------------------------------------------------------------
def vision_describe(media_url, *, question="", media_type=None,
                    max_tokens=1024, timeout=90):
    """Devolve {'answer','model','media_type','latency_ms','source'}.
    media_type: 'image' (image_url) ou 'video' (video_url) — auto-detetado
    pela extensão quando None."""
    cfg = _vision_cfg()
    if not cfg["api_key"]:
        raise RuntimeError("Motor de visão não configurado (slot vision)")
    mtype = media_type if media_type in ("image", "video") \
        else detect_media_type(media_url)
    field = f"{mtype}_url"
    content = [
        {"type": "text",
         "text": question or "Descreve o que vês numa frase."},
        {"type": field, field: {"url": media_url}},
    ]
    body = {"model": cfg["model"],
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max(256, int(max_tokens)), "stream": False,
            "temperature": 0.6, "top_p": 0.95}
    started = time.monotonic()
    response = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['api_key']}"},
        json=body, timeout=timeout)
    response.raise_for_status()
    choices = response.json().get("choices") or []
    if not choices:
        raise ValueError("resposta do omni sem completion")
    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    if not answer:
        # reasoning pode ter consumido o budget — apenas sinaliza erro claro
        raise ValueError("resposta vazia do omni (reasoning consumiu budget?)")
    return {"answer": answer, "model": cfg["model"], "media_type": mtype,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "source": cfg["source"]}


# ---------------------------------------------------------------------------
# Imagens — FLUX.2-klein-4B (genai)
# ---------------------------------------------------------------------------
def generate_image(prompt, *, width=1024, height=1024, steps=4, seed=None,
                   timeout=240):
    """Devolve {'image_b64','finish_reason','model','width','height','steps',
    'seed','latency_ms','source'}. Resposta: artifacts[0].base64 = JPEG."""
    cfg = _image_cfg()
    if not cfg["api_key"]:
        raise RuntimeError("Motor de imagem não configurado (slot image)")
    body = {"prompt": str(prompt), "width": int(width), "height": int(height),
            "steps": int(steps)}
    if seed is not None:
        body["seed"] = int(seed)
    started = time.monotonic()
    response = requests.post(
        f"{cfg['base_url']}/{cfg['model'].strip('/')}",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": f"Bearer {cfg['api_key']}"},
        json=body, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    artifacts = data.get("artifacts") or []
    if not artifacts or not artifacts[0].get("base64"):
        raise ValueError("resposta do FLUX sem imagem (artifacts vazio)")
    artifact = artifacts[0]
    return {"image_b64": artifact["base64"],
            "finish_reason": artifact.get("finishReason", ""),
            "model": cfg["model"], "width": int(width), "height": int(height),
            "steps": int(steps), "seed": seed,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "source": cfg["source"]}


def engines_status(timeout=2.5):
    """Resumo dos motores visão/imagem (sem live probe — é caro):
    configurado, modelo, base e origem da credencial."""
    out = []
    for slot, fn, label in (("vision", _vision_cfg, "Visão (omni)"),
                            ("image", _image_cfg, "Imagens (FLUX.2)")):
        try:
            cfg = fn()
        except Exception:
            cfg = {"api_key": "", "model": "", "base_url": "", "source": ""}
        out.append({"id": slot, "label": label,
                    "configured": bool(cfg.get("api_key")),
                    "model": cfg.get("model", ""),
                    "base_url": cfg.get("base_url", ""),
                    "source": cfg.get("source", "")})
    return out
