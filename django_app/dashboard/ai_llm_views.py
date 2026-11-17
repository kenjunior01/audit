"""Motores de IA (LLM) — endpoints de estado, teste e narração BI.

- GET  /ai/llm/status  → motores configurados + disponibilidade ao vivo
                         (viewer+)
- POST /ai/llm/test    → ping real ao LLM (auditor/admin): provider usado,
                         latência e resposta
- POST /bi/narrate     → narração executiva do painel atual gerada por IA
                         (viewer+); fallback determinístico quando não há
                         motor disponível — nunca derruba o Painel Auto.
"""
import logging
import time

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import llm_client
from .auth import IsAuditorOrAdmin, IsViewerOrAbove

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def llm_status(request):
    """Estado dos motores de IA (NVIDIA NIM → provider clássico)."""
    providers = llm_client.provider_status()
    return Response({
        "providers": providers,
        "chain": [p["id"] for p in providers if p["configured"]],
        "active_hint": ("nvidia" if llm_client._text_cfg()["api_key"]
                        else "primary"),
        "any_available": any(p["available"] for p in providers),
    })


@api_view(["POST"])
@permission_classes([IsAuditorOrAdmin])
def llm_test(request):
    """Ping real ao LLM: devolve provider usado, latência e resposta curta.
    Falha de motor devolve ok=false com HTTP 200 (o teste é o próprio payload)."""
    started = time.monotonic()
    prompt = "Responde apenas com a palavra OK."
    try:
        text, meta = llm_client.generate_meta(prompt, timeout=40, max_tokens=16)
        total_ms = int((time.monotonic() - started) * 1000)
        return Response({
            "ok": True,
            "answer": text.strip()[:120],
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "provider_latency_ms": meta.get("latency_ms"),
            "latency_ms": total_ms,
        })
    except Exception as e:  # teste falhou — payload explica, HTTP continua 200
        logger.warning("llm_test falhou: %s", e)
        return Response({"ok": False, "error": str(e)[:200],
                         "latency_ms": int((time.monotonic() - started) * 1000)})


@api_view(["POST"])
@permission_classes([IsViewerOrAbove])
def bi_narrate(request):
    """Narração executiva (IA) do Painel Auto: recebe kpis/insights do
    frontend e devolve um parágrafo em PT gerado pelo motor LLM disponível.
    Sem motor → resumo determinístico (available=false), nunca erro duro."""
    kpis = request.data.get("kpis") or []
    insights = request.data.get("insights") or []
    period = str(request.data.get("period") or "todos os períodos")[:60]
    if not kpis and not insights:
        return Response({"error": "Sem dados para narrar."}, status=400)

    kpi_lines = []
    for k in kpis[:8]:
        if not isinstance(k, dict):
            continue
        linha = f"- {k.get('label', 'KPI')}: {k.get('value')}"
        if k.get("detail"):
            linha += f" ({k.get('detail')})"
        kpi_lines.append(linha)
    signal_lines = [f"- {str(s)[:200]}" for s in insights[:8] if s]

    prompt = (
        "És um auditor sénior a apresentar ao gestor. Escreve um parágrafo "
        "executivo de 3 a 4 frases, em português de Portugal, que interprete "
        f"os KPIs e sinais seguintes (período: {period}). Sê factual — não "
        "inventes números que não estejam nos dados — e termina com a "
        "principal recomendação de auditoria.\nKPIs:\n"
        + "\n".join(kpi_lines)
        + "\nSinais:\n" + "\n".join(signal_lines))
    try:
        text, meta = llm_client.generate_meta(prompt, timeout=45, max_tokens=380)
        narrative = text.strip()
        if not narrative:
            raise ValueError("resposta vazia do LLM")
        return Response({
            "narrative": narrative,
            "available": True,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "latency_ms": meta.get("latency_ms"),
        })
    except Exception as e:
        logger.warning("bi/narrate usa fallback determinístico: %s", e)
        deterministic = ("Resumo determinístico: "
                         + " ".join(str(s) for s in insights[:4])).strip()
        return Response({
            "narrative": deterministic or "IA indisponível neste momento.",
            "available": False,
        })
