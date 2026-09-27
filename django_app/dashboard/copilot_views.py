"""
Endpoints do Copiloto Global da Plataforma.

- POST /ai/copilot           → chat agéntico {question, history}
- POST /ai/copilot/stream    → chat em streaming (Server-Sent Events)
- GET  /ai/copilot/briefing  → briefing executivo proativo (KPIs + sinais)
- POST /ai/copilot/feedback  → avaliação (1-5) de respostas pelo utilizador

Permissões: IsAuthenticated (leitura de dados da plataforma).
"""
import json
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import copilot_service as cs
from .models import CopilotFeedback

logger = logging.getLogger(__name__)


def _clean_history(history):
    """Sanitiza o histórico recebido do frontend (máx. 8 msgs, texto curto)."""
    if not isinstance(history, list):
        return []
    clean = []
    for m in history[-8:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            clean.append({"role": m["role"],
                          "content": str(m.get("content", ""))[:400]})
    return clean


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copilot_chat(request):
    """Chat do Copiloto Global — pergunta em lingu natural, dados vivos."""
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "Indique uma pergunta."},
                        status=status.HTTP_400_BAD_REQUEST)
    history = _clean_history(request.data.get("history"))
    # página atual do frontend (consciência de contexto do copiloto)
    page = str(request.data.get("page") or "")[:60]
    try:
        result = cs.chat(question, history, page=page)
    except Exception as e:
        logger.exception("copilot_chat falhou")
        return Response({"error": f"O Copiloto não conseguiu responder: {e}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def copilot_briefing(request):
    """Briefing executivo proativo — KPIs, sinais e recomendações."""
    try:
        result = cs.build_briefing()
    except Exception as e:
        logger.exception("copilot_briefing falhou")
        return Response({"error": f"Não foi possível gerar o briefing: {e}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copilot_stream(request):
    """Chat do Copiloto em streaming (Server-Sent Events).
    O cliente vê a execução agéntica em tempo real:
    event: status → tool_start → tool_done (×N) → status → final.
    Mesma permissão e sanitização do chat síncrono."""
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "Indique uma pergunta."},
                        status=status.HTTP_400_BAD_REQUEST)
    history = _clean_history(request.data.get("history"))
    page = str(request.data.get("page") or "")[:60]

    def event_stream():
        try:
            for ev in cs.chat_events(question, history, page=page):
                payload = json.dumps(ev.get("data", {}),
                                     ensure_ascii=False, default=str)
                yield f"event: {ev.get('event', 'status')}\ndata: {payload}\n\n"
        except Exception as e:
            logger.exception("copilot_stream falhou")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    resp = StreamingHttpResponse(event_stream(),
                                 content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copilot_feedback(request):
    """Regista a avaliação (1-5) do utilizador sobre uma resposta.
    Fecha o ciclo de melhoria contínua do modelo de suporte."""
    try:
        rating = int(request.data.get("rating"))
    except (TypeError, ValueError):
        return Response({"error": "rating deve ser um inteiro de 1 a 5."},
                        status=status.HTTP_400_BAD_REQUEST)
    if not 1 <= rating <= 5:
        return Response({"error": "rating deve ser um inteiro de 1 a 5."},
                        status=status.HTTP_400_BAD_REQUEST)
    user = getattr(request, "user", None)
    fb = CopilotFeedback.objects.create(
        rating=rating,
        question=str(request.data.get("question") or "")[:1000],
        answer_excerpt=str(request.data.get("answer") or "")[:2000],
        mode=str(request.data.get("mode") or "")[:10],
        page=str(request.data.get("page") or "")[:60],
        comment=str(request.data.get("comment") or "")[:1000],
        # utilizador vem da autenticação por token (SimpleNamespace com id/role)
        username=str(getattr(user, "username", "")
                     or getattr(user, "id", "")
                     or getattr(user, "pk", "") or "")[:150],
    )
    return Response({"ok": True, "id": fb.id}, status=status.HTTP_201_CREATED)
