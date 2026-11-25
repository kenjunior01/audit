"""
Exemplo numérico MACRO — Modulador A priori Contextual de Risco Observável.

Reproduz EXATAMENTE as fórmulas de:
  django_app/dashboard/context_service.py    (MACRO — a nova fórmula)
  django_app/dashboard/predictive_service.py (IPRA — fusão bayesiana)
  django_app/dashboard/prevention_service.py (IPV — noisy-or ponderado)

Cenário didático: "Comércio Kwanza Lda" — retalho, economia emergente
concentrada, ciclo fiscal a 10 dias do prazo do IVA. Executar:
    cd django_app && python ../scripts/macro_demo.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "django_app"))

from dashboard.context_service import (  # noqa: E402
    BETA, GAMMA_CTX, macro_context, sigma_log_m, error_margin,
    modulate_prior, norm_cdf)
from dashboard.predictive_service import fuse, shrink, band_ipra, lr_log, W_SIGNALS  # noqa: E402
from dashboard.prevention_service import noisy_or, ipv_index, band_ipv, PIV, WV, EV  # noqa: E402

N = 48

print("=== MACRO — Modulador A priori Contextual de Risco Observável ===")
print("Empresa: Comércio Kwanza Lda (retalho; economia emergente concentrada)")
ctx = macro_context(
    t_eff=0.34, vol=0.05, days_to_deadline=10,       # F1 impostos
    z_infl=1.2, z_fx=0.8, z_gap=-0.5,                # F2 ciclo
    u=0.41,                                          # F4 sazonalidade
    economy="emergente_concentrada",                 # F2 regime
    sector="comercio", sector_table={"comercio": 1.30},  # F3 setor
    prior=0.02, kind="ipra",
)
st = ctx["factors"]["stresses"]
print("\n-- Fatores: base → estresse (Φ) → contribuição log --")
for k, beta in BETA.items():
    c = ctx["factors"]["contributions"][k]
    if c is None:
        print(f"  {k:<9} indisponível (não distorce)")
        continue
    print(f"  {k:<9} s={c['s']:.6f}  x={c['x']:+.4f}  "
          f"log={c['log_contrib']:+.6f}  (β={beta})")
print(f"  setor m={ctx['factors']['sector_multiplier']:.2f}   "
      f"regime m={ctx['factors']['regime_multiplier']:.2f}")
print(f"  Σ log = {ctx['factors']['log_sum']:+.6f}")
print(f"  M_raw = 1.30×1.30×exp({ctx['factors']['log_sum']:+.4f}) "
      f"= {ctx['factors']['m_raw']:.6f}")
print(f"  cobertura c = {ctx['factors']['coverage']:.2f} → "
      f"M_eff = {ctx['factors']['m_eff']:.6f}  "
      f"[contexto {ctx['band_macro']}]")

print("\n-- Proposição 3: assimetria (adverso vs. favorável espelhado) --")
m_adv0 = macro_multiplier(st, 1.0, 1.0)["m_eff"]
fav_stresses = {k: (1.0 - v) for k, v in st.items()}
m_fav = macro_multiplier(fav_stresses, 1.0, 1.0)["m_eff"]
ratio = math.log(m_adv0) / abs(math.log(m_fav))
print(f"  log M(adverso)={math.log(m_adv0):+.6f}  "
      f"log M(favorável)={math.log(m_fav):+.6f}")
print(f"  razão = {ratio:.4f}  (teórico 1/γ = {1/GAMMA_CTX:.4f})")

print("\n-- Proposição 4: cobertura (dados em falta nunca distorcem) --")
partial = macro_context(u=0.41)["factors"]
print(f"  só sazonalidade: c={partial['coverage']:.2f} → "
      f"M_eff={partial['m_eff']:.6f} (neutro=1.0)")
empty = macro_context()["factors"]
print(f"  sem fatores:     c={empty['coverage']:.2f} → "
      f"M_eff={empty['m_eff']:.6f}")

print("\n-- Margem de erro (Proposição 5, delta method) --")
s_lm = sigma_log_m(st)
print(f"  σ(log M) = {s_lm:.6f} (σ_s=0.10 por estresse)")

# ---------------------------------------------------- IPRA com contexto ---
print("\n=== IPRA × MACRO — o prior contextual muda a linha de partida ===")
comp = {"benford": 0.42, "digit2": 0.18, "behavioral": 0.55,
        "cusum": 0.30, "period_end": 0.62}
print("Sinais c_k: " + ", ".join(f"{k}={v:.2f}" for k, v in comp.items()))
sum_lr = sum(lr_log(W_SIGNALS[k], c) for k, c in comp.items())
p_base, _ = fuse(comp, 0.02)
pf_base = shrink(p_base, N, 0.02)
p_ctx, _ = fuse(comp, ctx["modulation"]["prior_ctx"])
pf_ctx = shrink(p_ctx, N, ctx["modulation"]["prior_ctx"])
print(f"  sem contexto:  π_b=0.020000 → P_raw={p_base:.6f} → "
      f"P_final={pf_base:.6f} [{band_ipra(pf_base)}]")
print(f"  com contexto:  π_b={ctx['modulation']['prior_ctx']:.6f} → "
      f"P_raw={p_ctx:.6f} → P_final={pf_ctx:.6f} [{band_ipra(pf_ctx)}]")
print(f"  Σ logLR sinais = {sum_lr:+.4f} (idêntico — o contexto entra no prior)")
m_ctx = error_margin(pf_ctx, s_lm)
print(f"  IC95% (P_final): ±{m_ctx:.6f} → "
      f"[{pf_ctx - m_ctx:.6f}, {pf_ctx + m_ctx:.6f}]")

print("\n=== IPV × MACRO — prevenção também ouve o contexto ===")
p_axes = {"v1": 0.90, "v2": 0.44, "v3": 0.72, "v4": 0.55,
          "v5": 0.30, "v6": 0.40}
mod_v = modulate_prior(PIV, ctx["factors"]["m_eff"], "ipv")
v_base = shrink(noisy_or(p_axes), N, PIV)
v_ctx = shrink(noisy_or(p_axes), N, mod_v["prior_ctx"])
print(f"  sem contexto:  π_v={PIV:.2f} → V_final={v_base:.6f} [{band_ipv(v_base)}]")
print(f"  com contexto:  π_v={mod_v['prior_ctx']:.6f} → "
      f"V_final={v_ctx:.6f} [{band_ipv(v_ctx)}]")
print(f"  cap IPV (0.50×, 3.0×): raw={PIV * ctx['factors']['m_eff']:.6f} "
      f"capped={mod_v['capped']}")

print("\n=== Plano preventivo (decomposição exata ΔV_i) — top 3 ===")
idx_v = ipv_index(p_axes, N, mod_v["prior_ctx"])
for row in idx_v["plan"][:3]:
    print(f"  {row['axis']}: {row['label']:<32} p={row['p']:.2f} "
          f"e={row['efficacy']:.2f} → ΔV={row['delta_v']:.6f}")
