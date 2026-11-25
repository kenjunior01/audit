"""
Endpoints da família preditiva AuditAI: MACRO (contexto macroestrutural),
IPRA (deteção) e IPV (prevenção).

  GET /django/api/macro/?t_eff=0.34&vol=0.05&days_to_deadline=10&...
      Dossiê MACRO: estresses por fator, multiplicador M_eff, banda,
      prior modulado e margem de erro (delta method).
      Sem parâmetros → contexto neutro (cobertura 0, M_eff = 1).

  GET /django/api/predictive/?vendor=X
      IPRA + IPV para a base (filtro opcional por fornecedor): sinais
      C1..C5, eixos v1..v6 disponíveis, índices com e sem contexto MACRO,
      plano preventivo ordenado por ΔV.

Autenticação idêntica ao resto da plataforma (ApiToken Bearer,
IsViewerOrAbove para leitura). Sem efeitos secundários.
"""
import math

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .auth import IsViewerOrAbove
from .models import Alert, Transaction
from .context_service import macro_context, error_margin, modulate_prior
from .predictive_service import (BASE_RATE, evaluate, band_ipra, shrink)
from .prevention_service import (PIV, axis_strengths_from_data, band_ipv,
                                 ipv_index, noisy_or)


def _f(request, name):
    v = request.query_params.get(name)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _s(request, name):
    v = request.query_params.get(name)
    return v if v else None


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def macro_view(request):
    """Dossiê MACRO completo a partir de parâmetros de contexto."""
    prior = _f(request, "prior")
    kind = _s(request, "kind") or "ipra"
    if kind not in ("ipra", "ipv"):
        kind = "ipra"
    theta = _f(request, "theta") or 1.0
    theta = max(0.0, min(1.0, theta))
    out = macro_context(
        t_eff=_f(request, "t_eff"),
        vol=_f(request, "vol"),
        days_to_deadline=_f(request, "days_to_deadline"),
        z_infl=_f(request, "z_infl"),
        z_fx=_f(request, "z_fx"),
        z_gap=_f(request, "z_gap"),
        u=_f(request, "u"),
        economy=_s(request, "economy"),
        sector=_s(request, "sector"),
        prior=prior, kind=kind, theta=theta,
    )
    m_eff = out["factors"]["m_eff"]
    if prior is not None:
        mod = out["modulation"]
        s_lm = out["sigma_log_m"]
        mod["error_margin"] = error_margin(prior, s_lm)
    out["formula"] = ("M_eff = clip(m_setor·m_reg·exp(Σβ·h(2(s−0.5))), "
                      "0.5, 3.0)^c; π_ctx = clip(π·M_eff^θ, caps)")
    return Response(out)


@api_view(["GET"])
@permission_classes([IsViewerOrAbove])
def predictive_view(request):
    """IPRA + IPV com e sem contexto MACRO para a base de transações."""
    vendor = _s(request, "vendor")
    qs = Transaction.objects.all()
    if vendor:
        qs = qs.filter(vendor__iexact=vendor)
    txs = list(qs.order_by("timestamp"))
    n = len(txs)

    idx = evaluate(txs)
    alerts = list(Alert.objects.filter(vendor__iexact=vendor)
                  if vendor else Alert.objects.all())
    axes = axis_strengths_from_data(txs, alerts)
    idx_v = ipv_index(axes, n)

    # Contexto MACRO: setor do perfil de contexto, se existir
    sector = None
    try:
        from .models import ContextProfile
        prof = ContextProfile.objects.first()
        if prof is not None:
            sector = prof.sector
    except Exception:
        sector = None
    u = idx["signals"].get("period_end")
    ctx = macro_context(u=u, sector=sector, prior=BASE_RATE, kind="ipra")
    m_eff = ctx["factors"]["m_eff"]

    prior_ctx = ctx["modulation"]["prior_ctx"]
    idx_ctx = evaluate(txs, prior=prior_ctx)
    mod_v = modulate_prior(PIV, m_eff, "ipv")
    v_ctx = shrink(noisy_or(axes), n, mod_v["prior_ctx"])

    return Response({
        "n": n,
        "vendor": vendor,
        "ipra": {
            "signals": idx["signals"],
            "baseline": {"p_final": idx["p_final"], "band": idx["band"],
                         "confidence": idx["confidence"]},
            "with_context": {
                "prior_ctx": prior_ctx,
                "m_eff": m_eff,
                "band_macro": ctx["band_macro"],
                "p_final": idx_ctx["p_final"],
                "band": band_ipra(idx_ctx["p_final"]),
                "error_margin": error_margin(idx_ctx["p_final"],
                                             ctx["sigma_log_m"]),
            },
            "coverage_macro": ctx["factors"]["coverage"],
        },
        "ipv": {
            "axes": axes,
            "baseline": {"v_final": idx_v["v_final"], "band": idx_v["band"]},
            "with_context": {"prior_ctx": mod_v["prior_ctx"],
                             "v_final": v_ctx,
                             "band": band_ipv(v_ctx)},
            "plan": idx_v["plan"],
        },
    })
