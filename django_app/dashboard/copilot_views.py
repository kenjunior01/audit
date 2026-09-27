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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def copilot_insights(request):
    """Sinais proativos — o copiloto avisa sem ser perguntado.
    Fontes best-effort: alertas críticos, casos fora do prazo, Benford,
    duplicados, previsão de risco, importações falhadas e qualidade própria."""
    try:
        result = cs.build_proactive_signals()
    except Exception as e:
        logger.exception("copilot_insights falhou")
        return Response({"error": f"Não foi possível gerar os sinais: {e}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def copilot_feedback_stats(request):
    """Qualidade do Copiloto Global a partir das avaliações 1-5.
    Apenas administradores — os outros papéis recebem 403."""
    auth = getattr(request, "auth", None)
    role = (auth.get("role") if isinstance(auth, dict)
            else getattr(auth, "role", None))
    if role != "admin":
        return Response({"error": "Apenas administradores podem ver as "
                                  "métricas de qualidade do copiloto."},
                        status=status.HTTP_403_FORBIDDEN)
    return Response(cs.feedback_stats())


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def copilot_digest(request):
    """Digest programado do Copiloto Global (push por cron/beat).

    GET  → digest mais recente (qualquer utilizador autenticado);
           filtro opcional ?period=daily|weekly. Sem digests devolve
           {"digest": null} (o frontend mostra estado vazio).
    POST → gera agora (apenas admin): body opcional {period, email}.
           Reutiliza a task send_copilot_digest (dedupe por period+dia,
           email best-effort, log de auditoria)."""
    from .models import CopilotDigest
    from .tasks import send_copilot_digest

    if request.method == "GET":
        period = str(request.query_params.get("period") or "")[:10]
        qs = CopilotDigest.objects.all()
        if period in ("daily", "weekly"):
            qs = qs.filter(period=period)
        row = qs.first()
        if not row:
            return Response({"digest": None})
        return Response({"digest": {
            "id": row.id, "period": row.period, "day": str(row.day),
            "status": row.status, "recipients": row.recipients,
            "signals_count": row.signals_count,
            "critical_count": row.critical_count,
            "avg_rating": row.avg_rating,
            "created_at": row.created_at.isoformat(),
            "payload": row.payload,
        }})

    # POST — apenas administradores
    auth = getattr(request, "auth", None)
    role = (auth.get("role") if isinstance(auth, dict)
            else getattr(auth, "role", None))
    if role != "admin":
        return Response({"error": "Apenas administradores podem gerar o "
                                  "digest."},
                        status=status.HTTP_403_FORBIDDEN)
    period = str(request.data.get("period") or "daily")
    if period not in ("daily", "weekly"):
        return Response({"error": "period deve ser 'daily' ou 'weekly'."},
                        status=status.HTTP_400_BAD_REQUEST)
    send_email = bool(request.data.get("email", False))
    result = send_copilot_digest(period=period, send_email=send_email)
    if not result.get("ok"):
        return Response({"error": result.get("message",
                                             "Digest falhou.")},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def copilot_digest_pdf(request):
    """PDF executivo do digest — para download no frontend e arquivo.
    Usa o digest guardado mais recente (filtro ?period= opcional); se
    ainda não existir nenhum, gera o payload na hora sem persistir.
    Erros de PDF devolvem 500 com mensagem clara."""
    from django.http import HttpResponse
    from django.utils import timezone
    from .models import CopilotDigest

    period = str(request.query_params.get("period") or "")[:10]
    qs = CopilotDigest.objects.all()
    if period in ("daily", "weekly"):
        qs = qs.filter(period=period)
    row = qs.first()
    if row:
        digest = row.payload
        fname_period = row.period
    else:
        fname_period = period if period in ("daily", "weekly") else "daily"
        try:
            digest = cs.build_digest(fname_period)
        except Exception as e:
            return Response({"error": f"Não foi possível gerar o digest: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    try:
        pdf = cs.build_digest_pdf(digest)
    except Exception as e:
        logger.exception("copilot_digest_pdf falhou")
        return Response({"error": f"Não foi possível gerar o PDF: {e}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="digest-{fname_period}-'
        f'{timezone.localdate()}.pdf"')
    return resp
