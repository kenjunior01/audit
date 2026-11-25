"""
IPV — Índice Preditivo de Vulnerabilidade (camada de PREVENÇÃO).

6 eixos de controlo interno; cada um expõe uma probabilidade de falha
p_i ∈ [0,1] (None = dado indisponível) e combina por noisy-or ponderado:

    V_raw = 1 − Π_i (1 − w_i·p_i),   Σ w_i = 1
    V_final = (n·V_raw + n0·π_v)/(n + n0)          (π_v = 0.15, n0 = 25)
    banda: Sólido <0.15 ≤ Atento <0.30 ≤ Vulnerável <0.50 ≤ Exposto

Decomposição EXATA do ganho por ação (mitigar eixo i reduz p_i de
p_i → p_i·(1−e_i)):

    ΔV_i = λ · e_i · w_i · p_i · Π_{j≠i}(1 − w_j·p_j),   λ = n/(n+n0)

Eixos (pesos w_i; eficácia típica de mitigação e_i):
  v1 concentração de operador          w=0.20  e=0.85
  v2 aprovação sem segregação          w=0.18  e=0.70
  v3 novidade de fornecedor (KYC)      w=0.16  e=0.75
  v4 contornos de controlo/threshold   w=0.16  e=0.60
  v5 histórico de falsos positivos     w=0.18  e=0.55
  v6 latência de revisão               w=0.12  e=0.65

Funções puras; `axis_strengths_from_data` calcula v1 e v5 a partir de
Transaction/Alert e devolve None nos eixos sem dados (a matemática trata
indisponibilidade sem distorcer o índice).
"""
import math

from .predictive_service import shrink

PIV = 0.15            # π_v — prior de vulnerabilidade
SHRINK_N0 = 25
WV = {"v1": 0.20, "v2": 0.18, "v3": 0.16, "v4": 0.16, "v5": 0.18, "v6": 0.12}
EV = {"v1": 0.85, "v2": 0.70, "v3": 0.75, "v4": 0.60, "v5": 0.55, "v6": 0.65}
LABELS = {
    "v1": "concentração de operador",
    "v2": "aprovação sem segregação",
    "v3": "novidade de fornecedor (KYC)",
    "v4": "contornos de controlo",
    "v5": "histórico de falsos positivos",
    "v6": "latência de revisão",
}

IPV_BANDS = ((0.15, "Sólido"), (0.30, "Atento"), (0.50, "Vulnerável"))


def band_ipv(v: float) -> str:
    for cut, label in IPV_BANDS:
        if v < cut:
            return label
    return "Exposto"


def noisy_or(p_by_axis: dict) -> float:
    """Noisy-or ponderado; eixos None são ignorados (não distorcem)."""
    survival = 1.0
    for k, v in p_by_axis.items():
        if v is None:
            continue
        survival *= (1.0 - WV[k] * max(0.0, min(1.0, v)))
    return 1.0 - survival


def ipv_index(p_by_axis: dict, n: int, prior: float = PIV) -> dict:
    v_raw = noisy_or(p_by_axis)
    v_final = shrink(v_raw, n, prior, SHRINK_N0)
    lam = n / (n + SHRINK_N0)
    plan = []
    for k, p in p_by_axis.items():
        if p is None:
            continue
        prod_others = 1.0
        for j, pj in p_by_axis.items():
            if j != k and pj is not None:
                prod_others *= (1.0 - WV[j] * max(0.0, min(1.0, pj)))
        dv = lam * EV[k] * WV[k] * max(0.0, min(1.0, p)) * prod_others
        plan.append({"axis": k, "label": LABELS[k], "p": p,
                     "efficacy": EV[k], "delta_v": dv,
                     "v_after": v_final - dv})
    plan.sort(key=lambda r: -r["delta_v"])
    return {
        "axes": p_by_axis,
        "n": n,
        "prior": prior,
        "v_raw": v_raw,
        "v_final": v_final,
        "band": band_ipv(v_final),
        "lambda": lam,
        "plan": plan,
    }


def momentum(v_now: float, v_prev: float, target: float = 0.50,
             dead_zone: float = 0.03, cap: int = 12) -> dict:
    """Momentum Δ = V − V_prev e ETA (períodos até à banda-alvo)."""
    delta = v_now - v_prev
    if delta >= dead_zone and v_now < target:
        eta = min(cap, math.ceil((target - v_now) / delta))
    else:
        eta = None
    return {"delta": delta, "eta": eta,
            "on_track": delta >= dead_zone}


def axis_strengths_from_data(transactions, alerts) -> dict:
    """v1 (concentração de operador) e v5 (falsos positivos) dos dados.

    v1 = quota máxima do montante movimentado por um único user_id
         (0.5 → operador único pleno; None se sem dados).
    v5 = quota de alertas 'False Positive' sobre alertas encerrados
         (None se sem alertas encerrados).
    v2/v3/v4/v6 exigem metadados de workflow → None (neutro).
    """
    txs = list(transactions)
    total = sum(float(t.amount) for t in txs)
    v1 = None
    if txs and total > 0:
        by_user = {}
        for t in txs:
            u = getattr(t, "user_id", None) or "unknown"
            by_user[u] = by_user.get(u, 0.0) + float(t.amount)
        v1 = max(by_user.values()) / total
    closed = [a for a in alerts
              if a.status in ("Resolved", "False Positive")]
    v5 = None
    if closed:
        fps = sum(1 for a in closed if a.status == "False Positive")
        v5 = fps / len(closed)
    return {"v1": v1, "v2": None, "v3": None, "v4": None,
            "v5": v5, "v6": None}
