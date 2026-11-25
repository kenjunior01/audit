"""
MACRO — Modulador A priori Contextual de Risco Observável.
================================================================

NOVA FÓRMULA (composição de conceitos): modula o prior bayesiano dos
índices IPRA (π_b) e IPV (π_v) com o contexto macroestrutural da empresa,
partindo da BASE de cada fator — impostos, tipo de economia, ciclo,
setor e sazonalidade — para antecipar e mitigar falhas, erros e margens
de erro antes de qualquer sinal de deteção existir.

Composição de 5 conceitos clássicos numa fórmula nova:
  1. Normalização probit por fator      → estresse s_j ∈ [0.01, 0.99]
     s_j = Φ((observado − referência)/dispersão)      (base de cada fator)
  2. Transformação assimétrica (tipo CUSUM/conservadorismo)
     x_j = 2(s_j − 0.5);  h(x) = x se x ≥ 0, γ·x se x < 0   (γ = 0.35)
  3. Agregação em log-odds (teoria de deteção bayesiana)
     M = m_setor · m_regime · exp(Σ_j β_j·h(x_j))
  4. Encolhimento por cobertura (Stein/Efron–Morris)
     M_eff = clip(M, 0.5, 3.0)^c     (c = cobertura dos fatores ∈ [0,1])
  5. Delta method para a MARGEM DE ERRO explícita
     σ²(log M) ≈ c·Σ_j (2·β_j·h'(x_j)·σ_s)²
     IC95%(P) = P ± 1.96·P(1−P)·σ(log M)

Modulação dos priors (com temperatura θ e caps por índice):
  π^ctx = clip(π · M_eff^θ, cap_lo·π, cap_hi·π)

Propriedades (demonstrações em docs/MACRO.md):
  P1 Monotonicidade: ∂π^ctx/∂s_j ≥ 0 para todo o fator ativo.
  P2 Limites: 0.5^c ≤ M_eff ≤ 3.0^c; prior nunca sai do cap.
  P3 Conservadorismo assimétrico: o efeito log adverso pesa 1/γ ≈ 2.86×
     o efeito favorável espelhado — o contexto bom não adormece o auditor.
  P4 Neutralidade por cobertura: c → 0 ⇒ M_eff → 1; dados em falta
     NUNCA distorcem o prior (degradação suave, sem saltos).
  P5 Margens de erro: IC95% calibrado pelo delta method; a largura cresce
     com a incerteza σ_s dos inputs e decresce com a cobertura.

Bases (referências) dos fatores — editáveis por implantação:
  F1 Impostos    T_eff ~ N(μ_T=0.25, σ_T=0.10); volatilidade ~ N(0.03, 0.02);
                 deadline fiscal: s_d = max(0, 1 − d/45), d = dias até ao
                 prazo mais próximo; pesos (0.50, 0.30, 0.20).
  F2 Economia    tabela de regime por TIPO de economia (odds multipliers
                 1.00–1.45); ciclo: s_ciclo = Φ(0.40·z_π + 0.35·z_fx +
                 0.25·z_gap) — inflação, pressão cambial, gap de crescimento.
  F3 Setor       m_setor = odds-ratio histórico de anomalias do setor vs.
                 base, tabelado com floor 0.70 e cap 2.00 (default 1.00).
  F4 Sazonalidade s_saz = clip((u − 0.12)/0.35, 0, 1) — herda a base do
                 sinal C5 do IPRA (u = quota do montante no fecho do mês).

Pesos de agregação: β_impostos=0.32, β_ciclo=0.16, β_sazonal=0.30 (Σβ=0.78
nos estresses; regime e setor entram como multiplicadores tabulados).
Caps: M ∈ [0.5, 3.0]; prior IPRA cap (0.25×, 4.0×); prior IPV cap
(0.50×, 3.0×). θ = 1.0 por defeito (temperatura de calibração).

Funções puras; `macro_context(inputs)` devolve o dossiê completo com
contribuições, cobertura, multiplicador, prior modulado e margens.
"""
import math

GAMMA_CTX = 0.35                       # γ — conservadorismo assimétrico
BETA = {"impostos": 0.32, "ciclo": 0.16, "sazonal": 0.30}
M_CLIP = (0.5, 3.0)                    # limites do multiplicador bruto
PRIOR_CAPS = {"ipra": (0.25, 4.0), "ipv": (0.50, 3.0)}
THETA_DEFAULT = 1.0
SIGMA_S_DEFAULT = 0.10                 # incerteza típica de cada estresse

# F1 — bases fiscais (referência normativa; ajustável por implantação)
T_MU, T_SIGMA = 0.25, 0.10             # carga fiscal efetiva esperada
VOL_MU, VOL_SIGMA = 0.03, 0.02         # volatilidade da carga fiscal
FISCAL_W = (0.50, 0.30, 0.20)          # nível / volatilidade / deadline
DEADLINE_HORIZON = 45                  # dias: a partir daqui o deadline é neutro

# F2 — tipo de economia → multiplicador de odds (tabela aberta)
ECONOMY_TABLE = {
    "desenvolvida_diversificada": 1.00,
    "emergente_diversificada": 1.15,
    "emergente_concentrada": 1.30,
    "fragil_dolarizada": 1.45,
}
CYCLE_W = (0.40, 0.35, 0.25)           # inflação / câmbio / crescimento

# F3 — setor → odds-ratio histórico (tabela aberta, default neutro)
SECTOR_CAPS = (0.70, 2.00)


def norm_cdf(z: float) -> float:
    """Φ — distribuição normal padrão (via erf)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def stress(observed: float | None, mu: float, sigma: float) -> float | None:
    """Base de um fator: z → Φ, clipado a [0.01, 0.99]. 0.5 = na mediana."""
    if observed is None or sigma <= 0:
        return None
    return clip(norm_cdf((observed - mu) / sigma), 0.01, 0.99)


def _h(x: float) -> float:
    """Transformação assimétrica: adverso pesa inteiro, favorável γ."""
    return x if x >= 0 else GAMMA_CTX * x


def fiscal_stress(t_eff=None, vol=None, days_to_deadline=None,
                  t_mu=T_MU, t_sigma=T_SIGMA,
                  vol_mu=VOL_MU, vol_sigma=VOL_SIGMA) -> float | None:
    """F1 — estresse fiscal combinado (nível, volatilidade, deadline)."""
    parts = []
    w_used = 0.0
    s_level = stress(t_eff, t_mu, t_sigma)
    s_vol = stress(vol, vol_mu, vol_sigma)
    s_dead = None if days_to_deadline is None else \
        clip(max(0.0, 1.0 - days_to_deadline / DEADLINE_HORIZON), 0.0, 1.0)
    for w, s in zip(FISCAL_W, (s_level, s_vol, s_dead)):
        if s is not None:
            parts.append((w, s))
            w_used += w
    if not parts or w_used == 0:
        return None
    return sum(w * s for w, s in parts) / w_used


def cycle_stress(z_infl=None, z_fx=None, z_gap=None) -> float | None:
    """F2 (ciclo) — z-scores de inflação/câmbio/crescimento → Φ ponderado."""
    pairs = [(w, z) for w, z in zip(CYCLE_W, (z_infl, z_fx, z_gap))
             if z is not None]
    if not pairs:
        return None
    w_sum = sum(w for w, _ in pairs)
    z = sum(w * zz for w, zz in pairs) / w_sum
    return clip(norm_cdf(z), 0.01, 0.99)


def seasonal_stress(u=None) -> float | None:
    """F4 — sazonalidade de fecho; herda a base do sinal C5 do IPRA."""
    if u is None:
        return None
    return clip((u - 0.12) / 0.35, 0.0, 1.0)


def economy_multiplier(economy: str | None) -> float:
    """F2 (regime) — multiplicador tabulado por tipo de economia."""
    if not economy:
        return 1.00
    return ECONOMY_TABLE.get(economy, 1.00)


def sector_multiplier(sector: str | None, table: dict | None = None) -> float:
    """F3 — odds-ratio histórico do setor (floor 0.70, cap 2.00)."""
    if not sector:
        return 1.00
    tab = table or {}
    return clip(float(tab.get(sector, 1.00)), *SECTOR_CAPS)


def coverage(stresses: dict, weights: dict | None = None) -> float:
    """Cobertura c ∈ [0,1]: fração ponderada de fatores disponíveis."""
    w = weights or {"impostos": 0.40, "ciclo": 0.25, "sazonal": 0.35}
    tot = sum(w.values())
    ok = sum(w[k] for k, v in stresses.items() if v is not None)
    return ok / tot


def macro_multiplier(stresses: dict, sector_m: float = 1.00,
                     regime_m: float = 1.00) -> dict:
    """Núcleo MACRO: M_raw → clip → M_eff = M_clip^c + dossiê explicável."""
    contribs = {}
    log_sum = 0.0
    for key, beta in BETA.items():
        s = stresses.get(key)
        if s is None:
            contribs[key] = None
            continue
        x = 2.0 * s - 1.0
        contrib = beta * _h(x)
        contribs[key] = {"s": s, "x": x, "log_contrib": contrib}
        log_sum += contrib
    m_raw = sector_m * regime_m * math.exp(log_sum)
    m_clipped = clip(m_raw, *M_CLIP)
    c = coverage(stresses)
    m_eff = m_clipped ** c
    return {
        "stresses": stresses,
        "contributions": contribs,
        "log_sum": log_sum,
        "sector_multiplier": sector_m,
        "regime_multiplier": regime_m,
        "m_raw": m_raw,
        "m_clipped": m_clipped,
        "coverage": c,
        "m_eff": m_eff,
        "clipped": m_raw > M_CLIP[1] or m_raw < M_CLIP[0],
    }


def modulate_prior(pi: float, m_eff: float, kind: str = "ipra",
                   theta: float = THETA_DEFAULT) -> dict:
    """π^ctx = clip(π·M_eff^θ, cap_lo·π, cap_hi·π). kind: 'ipra' | 'ipv'."""
    lo, hi = PRIOR_CAPS[kind]
    raw = pi * (m_eff ** theta)
    ctx = clip(raw, pi * lo, pi * hi)
    return {"prior": pi, "m_eff": m_eff, "theta": theta,
            "prior_ctx": ctx, "capped": ctx != raw,
            "cap_low": pi * lo, "cap_high": pi * hi}


def sigma_log_m(stresses: dict, sigma_s: float = SIGMA_S_DEFAULT) -> float:
    """Delta method: desvio-padrão de log M_eff pela incerteza dos estresses.

    d log M/d s_j = 2·β_j·h'(x_j), com h' = 1 (x≥0) ou γ (x<0);
    Var(log M) ≈ c · Σ_j (2·β_j·h'(x_j)·σ_s)².
    """
    c = coverage(stresses)
    acc = 0.0
    for key, beta in BETA.items():
        s = stresses.get(key)
        if s is None:
            continue
        x = 2.0 * s - 1.0
        h_prime = 1.0 if x >= 0 else GAMMA_CTX
        acc += (2.0 * beta * h_prime * sigma_s) ** 2
    return math.sqrt(c * acc)


def error_margin(p: float, sigma_lm: float) -> float:
    """Semi-amplitude IC95% para a probabilidade final P (delta method):
    dP/d(log M) = P(1−P) → margem = 1.96·P(1−P)·σ(log M)."""
    return 1.96 * p * (1.0 - p) * sigma_lm


def macro_context(t_eff=None, vol=None, days_to_deadline=None,
                  z_infl=None, z_fx=None, z_gap=None, u=None,
                  economy: str | None = None, sector: str | None = None,
                  sector_table: dict | None = None,
                  prior: float | None = None, kind: str = "ipra",
                  theta: float = THETA_DEFAULT) -> dict:
    """Dossiê MACRO completo — única entrada numérica, saída explicável."""
    stresses = {
        "impostos": fiscal_stress(t_eff, vol, days_to_deadline),
        "ciclo": cycle_stress(z_infl, z_fx, z_gap),
        "sazonal": seasonal_stress(u),
    }
    mm = macro_multiplier(stresses, sector_multiplier(sector, sector_table),
                          economy_multiplier(economy))
    out = {"factors": mm}
    if prior is not None:
        out["modulation"] = modulate_prior(prior, mm["m_eff"], kind, theta)
        out["modulation"]["kind"] = kind
    out["sigma_log_m"] = sigma_log_m(stresses)
    out["band_macro"] = band_macro(mm["m_eff"])
    return out


def band_macro(m_eff: float) -> str:
    """Rótulo do contexto: Calmo <0.9 ≤ Neutro <1.3 ≤ Adverso <2.0 ≤ Crítico."""
    for cut, label in ((0.90, "Calmo"), (1.30, "Neutro"), (2.00, "Adverso")):
        if m_eff < cut:
            return label
    return "Crítico"
