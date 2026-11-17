"""Banco de imagens — endpoints da busca/galeria estilo Freepik na plataforma.

- GET    /ai/bank/providers            → provedores e estado das chaves (viewer+)
- GET    /ai/bank/search               → busca (viewer+; q, provider, page, page_size)
- POST   /ai/bank/save                 → guarda imagem no servidor (viewer+)
- GET    /ai/bank/images               → galeria guardada (viewer+)
- GET    /ai/bank/images/<pk>/file     → ficheiro (thumb por omissão; ?full=1)
- DELETE /ai/bank/images/<pk>          → remove (auditor+)

A guarda valida provedor, URL e conteúdo (magic bytes) e descarrega o
ficheiro para media/ — imagens guardadas ficam independentes do site de
origem e podem embutir-se em relatórios PDF (?cover=<id>, licenças livres).
"""
import logging
import uuid

from django.core.files.base import ContentFile
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import imagebank
from .auth import IsAuditorOrAdmin, IsViewerOrAbove
from .models import StockImage

logger = logging.getLogger(__name__)

META_MAX = {"image_id": 128, "title": 300, "author": 200, "license": 64,
            "license_url": 300, "landing_url": 500, "source_url": 2048,
            "query": 300}


def _user_name(request):
    try:
        return str(getattr(request.user, "pk", "") or "")
    except Exception:
        return ""


def _clean_meta(data):
    """Campos de metadados validados/limitados (tudo texto seguro)."""
    out = {}
    for field, max_len in META_MAX.items():
        value = str(data.get(field) or "").strip()
        out[field] = value[:max_len]
    return out


def _clean_dims(data):
    dims = []
    for field in ("width", "height"):
        try:
            v = int(data.get(field))
        except (TypeError, ValueError):
            v = None
        if v is not None and (v <= 0 or v > 100000):
            v = None
        dims.append(v)
    return dims


def _serialize(record):
    return {
        "id": record.pk, "provider": record.provider,
        "provider_image_id": record.provider_image_id,
        "query": record.query, "title": record.title,
        "author": record.author, "license": record.license,
        "license_url": record.license_url, "landing_url": record.landing_url,
        "width": record.width, "height": record.height,
        "file_size": record.file_size, "created_by": record.created_by,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M"),
        "thumb_url": f"/ai/bank/images/{record.pk}/file",
        "file_url": f"/ai/bank/images/{record.pk}/file?full=1",
    }


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def bank_providers(request):
    """Provedores disponíveis e se cada um tem chave configurada."""
    return Response({"providers": imagebank.provider_status()})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def bank_search(request):
    """Busca real num provedor do banco de imagens (metadados; sem descarga)."""
    qp = request.query_params
    try:
        result = imagebank.search(
            q := qp.get("q") or qp.get("query") or "",
            provider=qp.get("provider") or "openverse",
            page=qp.get("page") or 1,
            page_size=qp.get("page_size") or imagebank.PSIZE_DEFAULT)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:
        logger.warning("bank/search falhou: %s", e)
        return Response({"error": f"Falha na busca: {str(e)[:200]}"},
                        status=502)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
def bank_save(request):
    """Guarda uma imagem da busca no servidor (media + StockImage)."""
    data = request.data or {}
    provider = str(data.get("provider") or "").strip().lower()
    if provider not in imagebank.PROVIDERS:
        return Response({"error": f"Provedor inválido: '{provider}'."},
                        status=400)
    meta = _clean_meta(data)
    provider_image_id = meta.pop("image_id", "")
    if not provider_image_id:
        return Response({"error": "image_id é obrigatório."}, status=400)
    # aceita 'source_url' (contrato) e 'url' (alias do resultado da busca)
    url = meta.pop("source_url") or str(data.get("url") or "").strip()[:2048]
    if not url.lower().startswith(("http://", "https://")):
        return Response({"error": "source_url (http/https) é obrigatório."},
                        status=400)

    existing = StockImage.objects.filter(provider=provider,
                                         provider_image_id=provider_image_id
                                         ).first()
    if existing:
        return Response({"ok": True, "duplicate": True,
                         "image": _serialize(existing)})

    width, height = _clean_dims(data)
    try:
        full_bytes, ct, ext = imagebank.download_image(url)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=502)
    except Exception as e:
        logger.warning("bank/save descarga falhou: %s", e)
        return Response({"error": f"Falha na descarga: {str(e)[:200]}"},
                        status=502)

    record = StockImage(provider=provider, provider_image_id=provider_image_id,
                        width=width, height=height,
                        created_by=_user_name(request), **meta)
    fname = f"bank_{provider}_{uuid.uuid4().hex[:12]}.{ext}"
    record.file.save(fname, ContentFile(full_bytes), save=False)
    record.file_size = len(full_bytes)

    thumb_url = str(data.get("thumb_url") or "").strip()[:2048]
    thumb_ok = False
    if thumb_url.startswith(("http://", "https://")) and thumb_url != url:
        try:
            tb, _ct, text = imagebank.download_image(
                thumb_url, max_bytes=8 * 1024 * 1024)
            if text in ("jpg", "png", "gif", "webp", "svg"):
                record.thumb.save(f"thumb_{uuid.uuid4().hex[:12]}.{text}",
                                  ContentFile(tb), save=False)
                thumb_ok = True
        except Exception:
            thumb_ok = False  # thumb é opcional — a galeria usa o original
    record.save()
    logger.info("banco de imagens: guardada %s/%s (%d bytes%s) por %s",
                provider, provider_image_id, len(full_bytes),
                " +thumb" if thumb_ok else "", _user_name(request) or "?")
    return Response({"ok": True, "duplicate": False,
                     "image": _serialize(record)})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def bank_images(request):
    """Galeria das imagens guardadas (metadados; ficheiro por /file)."""
    try:
        limit = min(60, max(1, int(request.query_params.get("limit") or 12)))
    except (TypeError, ValueError):
        limit = 12
    rows = StockImage.objects.all()[:limit]
    return Response({"count": StockImage.objects.count(),
                     "images": [_serialize(r) for r in rows]})


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def bank_image_file(request, pk):
    """Ficheiro da galeria (thumb por omissão; ?full=1 para o original)."""
    try:
        record = StockImage.objects.get(pk=pk)
    except StockImage.DoesNotExist:
        return Response({"error": "Imagem não encontrada."}, status=404)
    full = str(request.query_params.get("full") or "") in ("1", "true")
    # thumb em falta no disco → serve o original (a galeria nunca quebra
    # por um thumb perdido; ex.: restauro de backups/recycle do sandbox)
    candidates = ([record.file] if (full or not record.thumb)
                  else [record.thumb, record.file])
    field = None
    fh = None
    for cand in candidates:
        if not cand:
            continue
        try:
            fh = cand.open("rb")
            field = cand
            break
        except (ValueError, FileNotFoundError):
            continue
    if fh is None or field is None:
        return Response({"error": "Ficheiro em falta."}, status=404)
    name = (field.name or "").lower()
    ct = ("image/svg+xml" if name.endswith(".svg")
          else "image/png" if name.endswith(".png")
          else "image/gif" if name.endswith(".gif")
          else "image/webp" if name.endswith(".webp")
          else "image/jpeg")
    return FileResponse(fh, content_type=ct)


@api_view(["DELETE"])
@permission_classes([IsAuditorOrAdmin])
def bank_image_delete(request, pk):
    """Remove uma imagem guardada (auditor+). Ficheiros vão junto."""
    try:
        record = StockImage.objects.get(pk=pk)
    except StockImage.DoesNotExist:
        return Response({"error": "Imagem não encontrada."}, status=404)
    for field in (record.file, record.thumb):
        try:
            field.delete(save=False)
        except Exception:
            pass
    record.delete()
    return Response({"ok": True, "deleted": pk})
