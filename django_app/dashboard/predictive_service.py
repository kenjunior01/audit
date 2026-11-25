"""
IPRA — Índice Preditivo de Risco de Anomalia (camada de DETEÇÃO).

Fusão bayesiana assimétrica de 5 sinais c_k ∈ [0,1] (0.5 = neutro):

    x_k = 2·c_k − 1
    logLR_k = w_k·x_k            se x_k ≥ 0   (sinal adverso pesa inteiro)
    logLR_k = γ·w_k·x_k          se x_k < 0   (sinal favorável pesa γ=0.3)
    O = π_b/(1−π_b) · Π_k exp(logLR_k)
    P_raw = O/(1+O)
    P_final = (n·P_raw + n0·π_b)/(n + n0)      (encolhimento, n0=25)
    confiança = min(1, n/60) · (Σ w_disponíveis / Σ w_totais)

Bandas: Baixo <0.20 ≤ Moderado <0.40 ≤ Elevado <0.60 ≤ Crítico.
Limites teóricos: P_floor = σ(logit π − γ·Σw), P_ceil = σ(logit π + Σw).

Sinais (bases documentadas):
  C1 Benford 1.º dígito — MAD (Nigrini; bandas 0.006/0.012/0.015/0.025),
     c1 = clip(1 − MAD/0.025, 0, 1); mínimo 50 valores.
  C2 Benford 2.º dígito — z unilateral máximo sobre a lei marginal
     P(d2=d) = Σ_f log10(1+1/(10f+d)), c2 = clip(z_max/3, 0, 1)
     (convenção 3σ).
  C3 Comportamental — 5 sub-sinais de Durtschi com pesos
     0.15/0.35/0.15/0.25/0.10; sub-sinais em falta → pesos renormalizados.
  C4 CUSUM mensal (k=0.5, h=5, padrão SPX), c4 = clip(S_max/5, 0, 1);
     mínimo 6 meses.
  C5 Fecho de período — u = quota do montante mensal lançado nos últimos
     5 dias corridos; referência neutra 0.12; c5 = clip((u−0.12)/0.35, 0, 1).

Todos os sinais podem ser fornecidos explicitamente (testes/ensino) ou
calculados a partir de Transaction. Funções puras: nenhuma dependência de
rede ou de BD.
"""
import math
from datetime import timedelta

from django.utils import timezone

# ------------------------------------------------------------ parâmetros ---
BASE_RATE = 0.02      # π_b — prior de anomalia (base histórica)
SHRINK_N0 = 25        # força do encolhimento (pseudo-observações)
NEG_FACTOR = 0.3      # γ — fator assimétrico (conservadorismo)
CONF_N = 60           # n para confiança máxima
W_SIGNALS = {"benford": 2.0, "digit2": 1.4, "behavioral": 2.6, "cusum": 1.8,
             "period_end": 2.2}          # Σ w = 10.0

IPRA_BANDS = ((0.20, "Baixo"), (0.40, "Moderado"), (0.60, "Elevado"))

# Benford — proporções esperadas
_BENFORD_P1 = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
# Lei marginal do 2.º dígito (Nigrini): P(d2=d) = Σ_{f=1..9} log10(1+1/(10f+d))
_BENFORD_P2 = {d: sum(math.log10(1 + 1 / (10 * f + d))
                      for f in range(1, 10)) for d in range(0, 10)}
_MAD_CAP = 0.025          # MAD de não conformidade (Nigrini)
_BEHAVIORAL_W = (0.15, 0.35, 0.15, 0.25, 0.10)   # Durtschi (documentado)


# -------------------------------------------------------------- núcleo -----
def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def lr_log(w: float, c: float) -> float:
    """Contribuição log-verosimilhança assimétrica de um sinal."""
    x = 2.0 * c - 1.0
    return w * x if x >= 0 else w * NEG_FACTOR * x


def fuse(components: dict, prior: float = BASE_RATE) -> tuple:
    """Fusão bayesiana → (P_raw, prior_odds). Sinais None são ignorados."""
    prior_odds = prior / (1.0 - prior)
    log_lr = 0.0
    for key, c in components.items():
        if c is None:
            continue
        log_lr += lr_log(W_SIGNALS[key], c)
    odds = prior_odds * math.exp(log_lr)
    return odds / (1.0 + odds), prior_odds


def shrink(p: float, n: int, prior: float, n0: int = SHRINK_N0) -> float:
    """Encolhimento para o prior quando a amostra é pequena."""
    return (n * p + n0 * prior) / (n + n0)


def band_ipra(p: float) -> str:
    for cut, label in IPRA_BANDS:
        if p < cut:
            return label
    return "Crítico"


def ipra_index(components: dict, n: int, prior: float = BASE_RATE) -> dict:
    """Índice completo: P_raw, P_final, banda, confiança, drivers, limites."""
    p_raw, prior_odds = fuse(components, prior)
    p_final = shrink(p_raw, n, prior)
    w_total = sum(W_SIGNALS.values())
    w_present = sum(W_SIGNALS[k] for k, v in components.items() if v is not None)
    confidence = min(1.0, n / CONF_N) * (w_present / w_total)
    logit_pi = math.log(prior / (1 - prior))
    sum_w = sum(W_SIGNALS.values())
    p_floor = _sigmoid(logit_pi - NEG_FACTOR * sum_w)
    p_ceil = _sigmoid(logit_pi + sum_w)
    drivers = sorted(((k, lr_log(W_SIGNALS[k], c)) for k, c in components.items()
                      if c is not None and lr_log(W_SIGNALS[k], c) > 0.05),
                     key=lambda d: -d[1])
    return {
        "components": components,
        "n": n,
        "prior": prior,
        "prior_odds": prior_odds,
        "p_raw": p_raw,
        "p_final": p_final,
        "band": band_ipra(p_final),
        "confidence": confidence,
        "p_floor": p_floor,
        "p_ceil": p_ceil,
        "sum_log_lr": sum(lr_log(W_SIGNALS[k], c)
                          for k, c in components.items() if c is not None),
        "drivers": [{"signal": k, "log_lr": v} for k, v in drivers],
    }


# ------------------------------------------------------------ sinais -------
def _first_digits(amounts) -> list:
    digits = []
    for v in amounts:
        v = abs(float(v))
        if v >= 1:
            s = str(v).lstrip("0.").replace(".", "").lstrip("0")
            if s:
                digits.append(int(s[0]))
    return digits


def _second_digits(amounts) -> list:
    digits = []
    for v in amounts:
        v = abs(float(v))
        if v >= 10:
            s = str(v).replace(".", "").lstrip("0")
            if len(s) >= 2:
                digits.append(int(s[1]))
    return digits


def c1_benford(amounts) -> float | None:
    """C1 — MAD do 1.º dígito vs Benford (mínimo 50 valores)."""
    digits = _first_digits(amounts)
    if len(digits) < 50:
        return None
    n = len(digits)
    mad = sum(abs(digits.count(d) / n - _BENFORD_P1[d])
              for d in range(1, 10)) / 9
    return max(0.0, min(1.0, 1.0 - mad / _MAD_CAP))


def c2_digit2(amounts) -> float | None:
    """C2 — z unilateral máximo do 2.º dígito (mínimo 50 valores)."""
    digits = _second_digits(amounts)
    if len(digits) < 50:
        return None
    n = len(digits)
    z_max = 0.0
    for d in range(10):
        exp_p = _BENFORD_P2[d]
        obs_p = digits.count(d) / n
        se = math.sqrt(exp_p * (1 - exp_p) / n)
        if se > 0:
            z_max = max(z_max, (obs_p - exp_p) / se)
    return max(0.0, min(1.0, z_max / 3.0))


def c4_cusum(monthly_totals) -> float | None:
    """C4 — CUSUM unilateral ascendente dos totais mensais (mín. 6 meses)."""
    if monthly_totals is None or len(monthly_totals) < 6:
        return None
    xs = [float(x) for x in monthly_totals]
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / max(1, len(xs) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return 0.0
    s, s_max = 0.0, 0.0
    for x in xs:
        s = max(0.0, s + (x - mu) / sd - 0.5)
        s_max = max(s_max, s)
    return max(0.0, min(1.0, s_max / 5.0))


def c5_period_end(monthly_amount_by_day) -> float | None:
    """C5 — u = quota do montante nos últimos 5 dias corridos do mês."""
    total = sum(monthly_amount_by_day.values())
    if total <= 0:
        return None
    last_day = max(monthly_amount_by_day.keys())
    tail = sum(v for d, v in monthly_amount_by_day.items()
               if d > last_day - 5)
    u = tail / total
    return max(0.0, min(1.0, (u - 0.12) / 0.35))


def c3_behavioral(sub_signals) -> float | None:
    """C3 — combinação ponderada de sub-sinais (pesos em falta renormalizados)."""
    if not sub_signals:
        return None
    pairs = [(w, v) for w, v in zip(_BEHAVIORAL_W, sub_signals) if v is not None]
    if not pairs:
        return None
    w_sum = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / w_sum


def signals_from_transactions(transactions) -> dict:
    """Calcula C1..C5 a partir de objetos Transaction (amount, timestamp).

    C3 requer dados de workflow (sub-sinais); aqui devolve None — o chamador
    pode injetá-lo explicitamente. C4 usa totais por mês; C5 usa o último mês.
    """
    txs = list(transactions)
    amounts = [float(t.amount) for t in txs]
    c1 = c1_benford(amounts)
    c2 = c2_digit2(amounts)
    by_month, by_day = {}, {}
    for t in txs:
        key = (t.timestamp.year, t.timestamp.month)
        by_month[key] = by_month.get(key, 0.0) + float(t.amount)
        day = t.timestamp.day
        month_days = _days_in_month(t.timestamp.year, t.timestamp.month)
        key_day = month_days - day          # 0 = último dia do mês
        by_day[key_day] = by_day.get(key_day, 0.0) + float(t.amount)
    c4 = c4_cusum([by_month[k] for k in sorted(by_month)])
    c5 = c5_period_end(by_day)
    return {"benford": c1, "digit2": c2, "behavioral": None,
            "cusum": c4, "period_end": c5}


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (timezone.datetime(year, month + 1, 1) -
            timedelta(days=1)).day


def evaluate(transactions, prior: float = BASE_RATE,
             extra_components: dict | None = None) -> dict:
    """Pipeline completo para um conjunto de Transaction (qs ou lista)."""
    txs = list(transactions)
    components = signals_from_transactions(txs)
    if extra_components:
        components.update(extra_components)
    idx = ipra_index(components, len(txs), prior)
    idx["signals"] = components
    return idx
