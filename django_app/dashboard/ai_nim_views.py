"""NIM Studio — endpoints das capacidades NVIDIA NIM geridas pela plataforma.

- GET/POST /ai/nim/credentials  → credenciais por slot na BD (Fernet).
    GET (viewer+): resumo mascarado — a chave completa nunca sai do servidor.
    POST (auditor+): grava/clear por slot (api_key="" limpa → fallback env).
- GET /ai/nim/status            → estado dos 3 slots + motores (viewer+).
- POST /ai/nim/vision           → compreensão de imagem/vídeo (omni), viewer+.
- POST /ai/nim/image            → geração de imagem (FLUX.2-klein-4B), viewer+;
                                  guarda na galeria (NimImage) e devolve data URI.
- GET  /ai/nim/images           → galeria (últimos 30, metadados).
- GET  /ai/nim/images/<pk>/file → ficheiro JPEG (viewer+; download autenticado).
"""
import base64
import logging
import re
import uuid

from django.core.files.base import ContentFile
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import ai_credentials, llm_client, nvidia_client
from .auth import IsAuditorOrAdmin, IsViewerOrAbove
from .models import NimImage, StockImage

logger = logging.getLogger(__name__)

PROMPT_MAX = 2000
# FLUX.2-klein-4B (upstream): dimensões aceites são múltiplos de 16 no
# intervalo [512, …]; abaixo de 512 o motor devolve 422. Teto prático 1024.
SIZE_MIN, SIZE_MAX, SIZE_STEP = 512, 1024, 16
STEPS_MIN, STEPS_MAX, STEPS_DEFAULT = 1, 8, 4


def _user_name(request):
    try:
        return str(getattr(request.user, "pk", "") or "")
    except Exception:
        return ""


def _clamp_size(value, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    v = max(SIZE_MIN, min(SIZE_MAX, v))
    return v - (v % SIZE_STEP) if v % SIZE_STEP else v


def _clamp_steps(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return STEPS_DEFAULT
    return max(STEPS_MIN, min(STEPS_MAX, v))


def _slot_payload(request, slot):
    """Campos aceites no POST /credentials para um slot: text_key/text_model/
    text_base_url, vision_*, image_*."""
    data = request.data or {}
    out = {}
    key = data.get(f"{slot}_key")
    if key is not None:
        out["api_key"] = str(key).strip()[:512]
    model = data.get(f"{slot}_model")
    if model is not None:
        out["model"] = str(model).strip()[:200]
    base = data.get(f"{slot}_base_url")
    if base is not None:
        out["base_url"] = str(base).strip()[:300]
    return out


@api_view(["GET", "POST"])
@permission_classes([IsViewerOrAbove])
def nim_credentials(request):
    """Credenciais IA na BD (mascaradas) / gravação por slot (auditor+)."""
    if request.method == "GET":
        return Response({"slots": ai_credentials.public_status()})

    # POST — só auditor/admin (viewer chega aqui? não: IsViewerOrAbove deixa
    # viewer passar, pelo que o papel é re-verificado explicitamente)
    auth = request.auth if hasattr(request, "auth") else None
    role = None
    if isinstance(auth, dict):
        role = auth.get("role")
    elif hasattr(auth, "role"):
        role = getattr(auth, "role")
    if role not in ("auditor", "admin"):
        return Response({"error": "Requer papel auditor ou admin."}, status=403)

    changed = []
    for slot in ai_credentials.VALID_SLOTS:
        fields = _slot_payload(request, slot)
        if not fields:
            continue
        kwargs = {"updated_by": _user_name(request)}
        kwargs.update(fields)
        ai_credentials.save_slot(slot, **kwargs)
        changed.append(slot)
    if not changed:
        return Response({"error": "Nenhum campo de credencial enviado."},
                        status=400)
    logger.info("credenciais IA atualizadas na BD: %s (por %s)",
                ", ".join(changed), _user_name(request) or "?")
    return Response({"ok": True, "updated": changed,
                     "slots": ai_credentials.public_status()})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def nim_status(request):
    """Estado completo do NIM Studio: slots + motores de texto ao vivo."""
    providers = llm_client.provider_status()
    return Response({
        "slots": ai_credentials.public_status(),
        "text_providers": providers,
        "text_chain": [p["id"] for p in providers if p["configured"]],
        "engines": nvidia_client.engines_status(),
        "any_available": any(p["available"] for p in providers),
    })


@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
def nim_vision(request):
    """Compreensão de imagem/vídeo pelo omni reasoning (viewer+)."""
    data = request.data or {}
    url = str(data.get("url") or "").strip()
    if not url:
        return Response({"error": "URL da imagem/vídeo é obrigatório."},
                        status=400)
    if len(url) > 2048:
        return Response({"error": "URL demasiado longo."}, status=400)
    question = str(data.get("question") or "").strip()[:1000]
    media_type = str(data.get("media_type") or "").strip().lower() or None
    try:
        max_tokens = min(4096, max(256, int(data.get("max_tokens") or 2048)))
    except (TypeError, ValueError):
        max_tokens = 2048
    try:
        result = nvidia_client.vision_describe(url, question=question,
                                               media_type=media_type,
                                               max_tokens=max_tokens)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.warning("nim/vision falhou: %s", e)
        return Response({"error": f"Falha no motor de visão: {str(e)[:200]}"},
                        status=502)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
def nim_image(request):
    """Geração de imagem FLUX.2-klein-4B (viewer+) com galeria automática."""
    data = request.data or {}
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return Response({"error": "O prompt é obrigatório."}, status=400)
    if len(prompt) > PROMPT_MAX:
        return Response({"error": f"Prompt máximo {PROMPT_MAX} caracteres."},
                        status=400)
    width = _clamp_size(data.get("width"), 1024)
    height = _clamp_size(data.get("height"), 1024)
    steps = _clamp_steps(data.get("steps"))
    seed = data.get("seed")
    if seed in ("", None):
        seed = None
    else:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return Response({"error": "seed tem de ser inteiro."}, status=400)

    try:
        result = nvidia_client.generate_image(prompt, width=width,
                                              height=height, steps=steps,
                                              seed=seed)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.warning("nim/image falhou: %s", e)
        return Response({"error": f"Falha no motor de imagem: {str(e)[:200]}"},
                        status=502)

    record = NimImage(prompt=prompt, width=width, height=height, steps=steps,
                      seed=seed, model=result["model"],
                      created_by=_user_name(request))
    try:
        raw = base64.b64decode(result["image_b64"])
    except Exception:
        return Response({"error": "Resposta do FLUX inválida."}, status=502)
    record.image.save(f"nim_{uuid.uuid4().hex[:12]}.jpg",
                      ContentFile(raw), save=True)

    data_uri = "data:image/jpeg;base64," + result["image_b64"]
    return Response({
        "id": record.pk, "image": data_uri, "width": width, "height": height,
        "steps": steps, "seed": seed, "model": result["model"],
        "finish_reason": result.get("finish_reason", ""),
        "latency_ms": result.get("latency_ms"), "source": result["source"],
        "file_url": f"/ai/nim/images/{record.pk}/file",
    })


def _serialize_nim_image(record):
    return {
        "id": record.pk, "prompt": record.prompt[:300], "width": record.width,
        "height": record.height, "steps": record.steps,
        "seed": record.seed, "model": record.model,
        "created_by": record.created_by,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M"),
        "file_url": f"/ai/nim/images/{record.pk}/file",
    }


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def nim_images(request):
    """Galeria das últimas imagens geradas (metadados; ficheiro por /file)."""
    try:
        limit = min(30, max(1, int(request.query_params.get("limit") or 12)))
    except (TypeError, ValueError):
        limit = 12
    rows = NimImage.objects.all()[:limit]
    return Response({"count": NimImage.objects.count(),
                     "images": [_serialize_nim_image(r) for r in rows]})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def nim_image_file(request, pk):
    """Ficheiro JPEG da galeria (fetch autenticado do frontend via blob)."""
    try:
        record = NimImage.objects.get(pk=pk)
    except NimImage.DoesNotExist:
        return Response({"error": "Imagem não encontrada."}, status=404)
    try:
        fh = record.image.open("rb")
    except (ValueError, FileNotFoundError):
        return Response({"error": "Ficheiro em falta."}, status=404)
    return FileResponse(fh, content_type="image/jpeg")


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
def nim_report_cover(request):
    """Capa ilustrada para o Relatório Global de Auditoria, gerada por FLUX
    (768×512 paisagem). Guardada na galeria NimImage — o PDF aceita
    ?cover=<id> para a embutir na capa."""
    days = str(request.data.get("days") or 30)
    prompt = ("Capa de relatório executivo de auditoria financeira, design "
              "corporativo moderno, paleta azul-escuro e dourado, gráficos "
              "abstratos elegantes em fundo claro, estilo profissional "
              "minimalista, sem texto, sem letras, sem palavras")
    try:
        result = nvidia_client.generate_image(prompt, width=768, height=512,
                                              steps=4)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.warning("nim/report-cover falhou: %s", e)
        return Response({"error": f"Falha no motor de imagem: {str(e)[:200]}"},
                        status=502)
    record = NimImage(prompt=f"[capa de relatório days={days}] {prompt}",
                      width=768, height=512, steps=4, seed=None,
                      model=result["model"], created_by=_user_name(request))
    try:
        raw = base64.b64decode(result["image_b64"])
    except Exception:
        return Response({"error": "Resposta do FLUX inválida."}, status=502)
    record.image.save(f"nim_cover_{uuid.uuid4().hex[:12]}.jpg",
                      ContentFile(raw), save=True)
    return Response({
        "id": record.pk, "image": "data:image/jpeg;base64," + result["image_b64"],
        "width": 768, "height": 512, "model": result["model"],
        "latency_ms": result.get("latency_ms"), "source": result["source"],
        "file_url": f"/ai/nim/images/{record.pk}/file",
    })


def cover_image_bytes(cover_id):
    """Bytes JPEG/PNG da capa para embutir no PDF (None se falhar).
    Aceita id da galeria NIM (FLUX) ou do banco de imagens (StockImage) —
    primeiro procura NimImage, depois StockImage."""
    if not cover_id:
        return None
    try:
        record = NimImage.objects.get(pk=cover_id)
        fh = record.image.open("rb")
        return fh.read()
    except (NimImage.DoesNotExist, ValueError, FileNotFoundError):
        pass
    try:
        record = StockImage.objects.get(pk=cover_id)
        fh = record.file.open("rb")
        return fh.read()
    except (StockImage.DoesNotExist, ValueError, FileNotFoundError):
        return None
