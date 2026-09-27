"""
Endpoints do Copiloto Global da Plataforma.

- POST /ai/copilot           → chat agéntico {question, history}
- GET  /ai/copilot/briefing  → briefing executivo proativo (KPIs + sinais)

Permissões: IsViewerOrAbove (leitura de dados da plataforma).
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import copilot_service as cs

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copilot_chat(request):
    """Chat do Copiloto Global — pergunta em lingu natural, dados vivos."""
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "Indique uma pergunta."},
                        status=status.HTTP_400_BAD_REQUEST)
    history = request.data.get("history")
    if not isinstance(history, list):
        history = []
    # limita histórico a 8 mensagens com conteúdo textual curto
    clean_history = []
    for m in history[-8:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            clean_history.append({"role": m["role"],
                                  "content": str(m.get("content", ""))[:400]})
    # página atual do frontend (consciência de contexto do copiloto)
    page = str(request.data.get("page") or "")[:60]
    try:
        result = cs.chat(question, clean_history, page=page)
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
