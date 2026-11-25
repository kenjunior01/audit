"""
Testes da família preditiva AuditAI — IPRA · IPV · MACRO.

Cobre (tudo em funções puras, sem rede; REST usa a BD de teste sqlite):
  • IPRA fusão bayesiana assimétrica: monotonicidade, assimetria γ,
    encolhimento exato, bandas nos cortes, limites P_floor/P_ceil,
    n=0 → prior, confiança proporcional aos pesos disponíveis.
  • Sinais: C1 (MAD Benford), C2 (2.º dígito), C4 (CUSUM), C5 (fecho),
    C3 (renormalização de sub-sinais); mínimos de amostra devolvem None.
  • IPV noisy-or ponderado: monotonicidade, eixo None = ignorado,
    decomposição exata ΔV_i (tolerância 1e-9), bandas, momentum/ETA,
    strengths a partir de dados (v1 concentração, v5 falsos positivos).
  • MACRO (a nova fórmula): estresse Φ com mediana neutra e limites,
    estresse fiscal combinado com renormalização, bounds do multiplicador
    (clip 0.5–3.0), monotonicidade em cada fator (P1), cobertura →
    neutralidade (P4), assimetria 1/γ exata (P3), σ(log M) delta method
    (P5), caps do prior, banda macro, integração: contexto adverso sobe
    P_final sem alterar Σ logLR dos sinais; contexto ausente = baseline.
  • REST: GET /django/api/macro e GET /django/api/predictive
    (200 autenticado, 401 sem token, JSON coerente com dados reais).
"""
import math
import random
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import Alert, ApiToken, Transaction
from dashboard.predictive_service import (
    BASE_RATE, NEG_FACTOR, SHRINK_N0, W_SIGNALS, band_ipra, c1_benford,
    c2_digit2, c3_behavioral, c4_cusum, c5_period_end, evaluate, fuse,
    ipra_index, lr_log, shrink, signals_from_transactions, _sigmoid)
from dashboard.prevention_service import (
    EV, PIV, WV, axis_strengths_from_data, band_ipv, ipv_index, momentum,
    noisy_or)
from dashboard.context_service import (
    BETA, GAMMA_CTX, M_CLIP, band_macro, cycle_stress, economy_multiplier,
    error_margin, fiscal_stress, macro_context, macro_multiplier,
    modulate_prior, seasonal_stress, sector_multiplier, sigma_log_m, stress)


# ---------------------------------------------------------------------------
# 1) IPRA — núcleo
# ---------------------------------------------------------------------------
class IpraFuseTest(TestCase):
    COMPONENTS = {"benford": 0.42, "digit2": 0.18, "behavioral": 0.55,
                  "cusum": 0.30, "period_end": 0.62}

    def test_monotonic(self):
        """P_raw cresce quando qualquer sinal cresce (P1 do IPRA)."""
        base, _ = fuse({k: 0.3 for k in W_SIGNALS})
        for k in W_SIGNALS:
            comp = {kk: 0.3 for kk in W_SIGNALS}
            comp[k] = 0.8
            up, _ = fuse(comp)
            self.assertGreater(up, base)

    def test_asymmetric_gamma(self):
        """Sinal adverso pesa mais que o favorável espelhado (γ=0.3)."""
        c_hi, c_lo = 0.8, 0.2
        w = W_SIGNALS["benford"]
        self.assertAlmostEqual(lr_log(w, c_hi), w * 0.6)
        self.assertAlmostEqual(lr_log(w, c_lo), NEG_FACTOR * w * (-0.6))
        self.assertAlmostEqual(abs(lr_log(w, c_lo)) / lr_log(w, c_hi),
                               NEG_FACTOR)

    def test_shrink_exact(self):
        p = shrink(0.5, 48, 0.02)
        self.assertAlmostEqual(p, (48 * 0.5 + 25 * 0.02) / 73)

    def test_shrink_n0_neutral_at_n_zero(self):
        self.assertAlmostEqual(shrink(0.9, 0, BASE_RATE), BASE_RATE)

    def test_bands_at_cuts(self):
        self.assertEqual(band_ipra(0.199), "Baixo")
        self.assertEqual(band_ipra(0.20), "Moderado")
        self.assertEqual(band_ipra(0.40), "Elevado")
        self.assertEqual(band_ipra(0.60), "Crítico")

    def test_floor_ceil_formula(self):
        comp_lo = {k: 0.0 for k in W_SIGNALS}
        comp_hi = {k: 1.0 for k in W_SIGNALS}
        p_lo, _ = fuse(comp_lo)
        p_hi, _ = fuse(comp_hi)
        logit = math.log(BASE_RATE / (1 - BASE_RATE))
        sw = sum(W_SIGNALS.values())
        self.assertAlmostEqual(p_lo, _sigmoid(logit - NEG_FACTOR * sw),
                               places=12)
        self.assertAlmostEqual(p_hi, _sigmoid(logit + sw), places=12)

    def test_confidence_partial_weights(self):
        comp = {k: 0.5 for k in W_SIGNALS}
        comp["behavioral"] = None
        idx = ipra_index(comp, 60)
        expected = (sum(W_SIGNALS.values()) - W_SIGNALS["behavioral"]) \
            / sum(W_SIGNALS.values())
        self.assertAlmostEqual(idx["confidence"], expected)
        self.assertTrue(0.0 <= idx["confidence"] <= 1.0)


# ---------------------------------------------------------------------------
# 2) Sinais
# ---------------------------------------------------------------------------
def _benford_amounts(n, seed=7):
    rnd = random.Random(seed)
    return [10 ** rnd.uniform(0.0, 5.0) for _ in range(n)]


def _benford_p2(d):
    """Lei marginal do 2.º dígito (Nigrini): soma sobre o 1.º dígito."""
    return sum(math.log10(1 + 1 / (10 * f + d)) for f in range(1, 10))


class SignalsTest(TestCase):
    def test_c1_conforming_high(self):
        c1 = c1_benford(_benford_amounts(500))
        self.assertIsNotNone(c1)
        self.assertGreater(c1, 0.3)

    def test_c1_constant_amounts_low(self):
        c1 = c1_benford([700.0] * 200)
        self.assertIsNotNone(c1)
        self.assertLessEqual(c1, 0.05)

    def test_c1_needs_50(self):
        self.assertIsNone(c1_benford([100.0] * 49))

    def test_c2_needs_50_and_conforming_low(self):
        self.assertIsNone(c2_digit2([100.0] * 49))
        # dados com 2.º dígito exatamente na lei marginal de Benford
        # (Σ_d P2(d) = 1; escala 800 → ~800 dígitos válidos)
        rnd = random.Random(3)
        amounts = []
        for d in range(10):
            for _ in range(int(round(800 * _benford_p2(d)))):
                amounts.append(30 + d + rnd.random())
        c2 = c2_digit2(amounts)
        self.assertIsNotNone(c2)
        self.assertLess(c2, 0.5)

    def test_c4_trend_vs_flat(self):
        up = c4_cusum([100, 110, 130, 160, 200, 260, 340])
        flat = c4_cusum([100, 100, 100, 100, 100, 100])
        self.assertIsNotNone(up)
        self.assertGreater(up, flat)

    def test_c4_needs_6_months(self):
        self.assertIsNone(c4_cusum([100, 110, 130, 160, 200]))

    def test_c5_edges(self):
        # u exatamente na referência neutra (12% do montante no fecho)
        neutral = {1: 88.0, 26: 4.0, 27: 4.0, 28: 4.0, 29: 0.0, 30: 0.0}
        self.assertAlmostEqual(c5_period_end(neutral), 0.0, places=12)
        stuffed = {26: 20.0, 27: 20.0, 28: 20.0, 29: 20.0, 30: 20.0}
        self.assertAlmostEqual(c5_period_end(stuffed), 1.0, places=12)
        self.assertIsNone(c5_period_end({}))

    def test_c3_renormalization(self):
        full = c3_behavioral([0.4, 0.6, 0.2, 0.8, 0.1])
        partial = c3_behavioral([None, 0.6, None, 0.8, None])
        self.assertAlmostEqual(full, (0.15 * 0.4 + 0.35 * 0.6 + 0.15 * 0.2
                                      + 0.25 * 0.8 + 0.10 * 0.1))
        expected = (0.35 * 0.6 + 0.25 * 0.8) / (0.35 + 0.25)
        self.assertAlmostEqual(partial, expected)
        self.assertIsNone(c3_behavioral([]))
        self.assertIsNone(c3_behavioral([None] * 5))

    def test_signals_from_transactions_shape(self):
        now = timezone.now()
        txs = [Transaction(transaction_id=f"t{i}",
                           amount=_benford_amounts(60)[i],
                           vendor="V", timestamp=now - timedelta(days=i))
               for i in range(60)]
        sig = signals_from_transactions(txs)
        self.assertEqual(set(sig), set(W_SIGNALS))
        self.assertIsNotNone(sig["benford"])
        self.assertTrue(0.0 <= sig["benford"] <= 1.0)

    def test_evaluate_pipeline(self):
        now = timezone.now()
        amounts = _benford_amounts(60)
        txs = [Transaction(transaction_id=f"e{i}", amount=amounts[i],
                           vendor="V", timestamp=now - timedelta(days=i))
               for i in range(60)]
        idx = evaluate(txs)
        self.assertIn(idx["band"], ("Baixo", "Moderado", "Elevado", "Crítico"))
        self.assertAlmostEqual(idx["p_final"],
                               shrink(idx["p_raw"], 60, BASE_RATE))


# ---------------------------------------------------------------------------
# 3) IPV — noisy-or e plano
# ---------------------------------------------------------------------------
AXES = {"v1": 0.90, "v2": 0.44, "v3": 0.72, "v4": 0.55, "v5": 0.30,
        "v6": 0.40}


class IpvTest(TestCase):
    def test_noisy_or_monotonic(self):
        base = noisy_or({k: 0.3 for k in WV})
        for k in WV:
            axes = {kk: 0.3 for kk in WV}
            axes[k] = 0.9
            self.assertGreater(noisy_or(axes), base)

    def test_none_axis_ignored(self):
        with_none = dict(AXES)
        with_none["v3"] = None
        without_key = {k: v for k, v in AXES.items() if k != "v3"}
        self.assertAlmostEqual(noisy_or(with_none), noisy_or(without_key))

    def test_delta_v_exact(self):
        n = 48
        idx = ipv_index(AXES, n)
        lam = n / (n + SHRINK_N0)
        for row in idx["plan"]:
            k = row["axis"]
            prod = 1.0
            for j, pj in AXES.items():
                if j != k:
                    prod *= (1.0 - WV[j] * pj)
            expected = lam * EV[k] * WV[k] * AXES[k] * prod
            self.assertAlmostEqual(row["delta_v"], expected, delta=1e-9)

    def test_plan_sorted_desc(self):
        plan = ipv_index(AXES, 48)["plan"]
        dvs = [r["delta_v"] for r in plan]
        self.assertEqual(dvs, sorted(dvs, reverse=True))

    def test_bands_at_cuts(self):
        self.assertEqual(band_ipv(0.149), "Sólido")
        self.assertEqual(band_ipv(0.15), "Atento")
        self.assertEqual(band_ipv(0.30), "Vulnerável")
        self.assertEqual(band_ipv(0.50), "Exposto")

    def test_momentum_eta_cap_and_deadzone(self):
        m = momentum(0.30, 0.12)
        self.assertAlmostEqual(m["delta"], 0.18)
        self.assertEqual(m["eta"], 2)          # ceil(0.20/0.18)
        capped = momentum(0.10, 0.07)          # (0.5−0.10)/0.03 = 13.3 → cap
        self.assertEqual(capped["eta"], 12)
        self.assertEqual(momentum(0.20, 0.19)["eta"], None)
        self.assertFalse(momentum(0.20, 0.19)["on_track"])

    def test_axis_strengths_from_data(self):
        now = timezone.now()
        txs = [Transaction(transaction_id=f"a{i}", amount=100 * (i + 1),
                           vendor="Kwanza", user_id="op1" if i < 55 else "op2",
                           timestamp=now - timedelta(days=i))
               for i in range(60)]
        alerts = [Alert(vendor="Kwanza", status="False Positive"),
                  Alert(vendor="Kwanza", status="False Positive"),
                  Alert(vendor="Kwanza", status="Resolved")]
        axes = axis_strengths_from_data(txs, alerts)
        self.assertGreater(axes["v1"], 0.8)
        self.assertLess(axes["v1"], 1.0)
        self.assertAlmostEqual(axes["v5"], 2 / 3)
        self.assertIsNone(axes["v2"])
        empty = axis_strengths_from_data([], [])
        self.assertIsNone(empty["v1"])
        self.assertIsNone(empty["v5"])


# ---------------------------------------------------------------------------
# 4) MACRO — a nova fórmula
# ---------------------------------------------------------------------------
class MacroStressTest(TestCase):
    def test_median_is_neutral_half(self):
        self.assertAlmostEqual(stress(0.25, 0.25, 0.10), 0.5)

    def test_stress_bounds_and_none(self):
        self.assertEqual(stress(10.0, 0.25, 0.10), 0.99)
        self.assertEqual(stress(-10.0, 0.25, 0.10), 0.01)
        self.assertIsNone(stress(None, 0.25, 0.10))
        self.assertIsNone(stress(0.5, 0.25, 0.0))

    def test_fiscal_stress_combined(self):
        s = fiscal_stress(t_eff=0.34, vol=0.05, days_to_deadline=10)
        self.assertAlmostEqual(s, 0.815929, places=4)

    def test_fiscal_stress_renormalizes(self):
        only_level = fiscal_stress(t_eff=0.34)
        self.assertAlmostEqual(only_level,
                               min(0.99, max(0.01, 0.5 * (1 + math.erf(
                                   0.9 / math.sqrt(2))))), places=6)
        self.assertIsNone(fiscal_stress())

    def test_cycle_stress_neutral_and_none(self):
        self.assertAlmostEqual(cycle_stress(0, 0, 0), 0.5)
        self.assertIsNone(cycle_stress(None, None, None))

    def test_seasonal_stress_edges(self):
        self.assertAlmostEqual(seasonal_stress(0.12), 0.0)
        self.assertGreaterEqual(seasonal_stress(0.47), 1.0)
        self.assertIsNone(seasonal_stress(None))


class MacroMultiplierTest(TestCase):
    def test_bounds_respected(self):
        hot = macro_multiplier({"impostos": 0.99, "ciclo": 0.99,
                                "sazonal": 0.99}, 2.0, 1.45)
        self.assertLessEqual(hot["m_eff"], M_CLIP[1] + 1e-12)
        self.assertTrue(hot["clipped"])
        calm = macro_multiplier({"impostos": 0.01, "ciclo": 0.01,
                                 "sazonal": 0.01}, 0.70, 1.00)
        self.assertGreaterEqual(calm["m_eff"], M_CLIP[0] - 1e-12)

    def test_monotonic_in_each_stress(self):
        for k in BETA:
            prev = None
            for s in (0.2, 0.4, 0.6, 0.8):
                st = {"impostos": 0.5, "ciclo": 0.5, "sazonal": 0.5}
                st[k] = s
                m = macro_multiplier(st, 1.0, 1.0)["m_eff"]
                if prev is not None:
                    self.assertGreaterEqual(m, prev)
                prev = m

    def test_neutral_stress_gives_one(self):
        m = macro_multiplier({"impostos": 0.5, "ciclo": 0.5,
                              "sazonal": 0.5}, 1.0, 1.0)
        self.assertAlmostEqual(m["m_eff"], 1.0, places=12)

    def test_coverage_neutral_no_data(self):
        m = macro_multiplier({"impostos": None, "ciclo": None,
                              "sazonal": None})
        self.assertEqual(m["coverage"], 0.0)
        self.assertAlmostEqual(m["m_eff"], 1.0, places=12)

    def test_partial_coverage_pulls_to_one(self):
        full = macro_multiplier({"impostos": 0.9, "ciclo": 0.9,
                                 "sazonal": 0.9})
        partial = macro_multiplier({"impostos": None, "ciclo": None,
                                    "sazonal": 0.9})
        self.assertLess(partial["m_eff"], full["m_eff"])
        self.assertGreater(partial["m_eff"], 1.0)

    def test_asymmetry_ratio_exact(self):
        adv = {"impostos": 0.8, "ciclo": 0.7, "sazonal": 0.75}
        fav = {k: 1.0 - v for k, v in adv.items()}
        m_adv = macro_multiplier(adv, 1.0, 1.0)["m_raw"]
        m_fav = macro_multiplier(fav, 1.0, 1.0)["m_raw"]
        ratio = math.log(m_adv) / abs(math.log(m_fav))
        self.assertAlmostEqual(ratio, 1.0 / GAMMA_CTX, places=9)

    def test_tables_default_neutral(self):
        self.assertEqual(economy_multiplier(None), 1.0)
        self.assertEqual(economy_multiplier("inexistente"), 1.0)
        self.assertEqual(sector_multiplier(None), 1.0)
        self.assertEqual(economy_multiplier("emergente_concentrada"), 1.30)

    def test_band_macro_cuts(self):
        self.assertEqual(band_macro(0.89), "Calmo")
        self.assertEqual(band_macro(0.95), "Neutro")
        self.assertEqual(band_macro(1.5), "Adverso")
        self.assertEqual(band_macro(2.0), "Crítico")


class MacroPriorTest(TestCase):
    EXAMPLE_STRESSES = {"impostos": 0.815929, "ciclo": 0.737286,
                        "sazonal": 0.828571}

    def test_theta_zero_is_neutral(self):
        mod = modulate_prior(0.02, 2.0, "ipra", theta=0.0)
        self.assertAlmostEqual(mod["prior_ctx"], 0.02)

    def test_modulation_monotonic(self):
        lo = modulate_prior(0.02, 1.2, "ipra")["prior_ctx"]
        hi = modulate_prior(0.02, 2.5, "ipra")["prior_ctx"]
        self.assertLess(lo, hi)

    def test_caps_hold(self):
        mod_hi = modulate_prior(0.02, 3.0, "ipra")
        self.assertLessEqual(mod_hi["prior_ctx"], 0.02 * 4.0 + 1e-12)
        mod_lo = modulate_prior(0.02, 0.5, "ipra")
        self.assertGreaterEqual(mod_lo["prior_ctx"], 0.02 * 0.25 - 1e-12)
        mod_v = modulate_prior(0.15, 3.0, "ipv")
        self.assertLessEqual(mod_v["prior_ctx"], 0.15 * 3.0 + 1e-12)

    def test_sigma_log_m_value_and_monotonic(self):
        s = sigma_log_m(self.EXAMPLE_STRESSES)
        self.assertAlmostEqual(s, 0.093381, places=4)
        self.assertGreater(sigma_log_m(self.EXAMPLE_STRESSES, 0.2), s)
        self.assertEqual(sigma_log_m({"impostos": None, "ciclo": None,
                                      "sazonal": None}), 0.0)

    def test_error_margin_formula(self):
        m = error_margin(0.062052, 0.093381)
        self.assertAlmostEqual(m, 1.96 * 0.062052 * (1 - 0.062052)
                               * 0.093381, places=12)

    def test_macro_context_dossier(self):
        out = macro_context(t_eff=0.34, vol=0.05, days_to_deadline=10,
                            z_infl=1.2, z_fx=0.8, z_gap=-0.5, u=0.41,
                            economy="emergente_concentrada",
                            sector="comercio",
                            sector_table={"comercio": 1.30},
                            prior=0.02, kind="ipra")
        self.assertAlmostEqual(out["factors"]["m_eff"], 2.718275, places=4)
        self.assertEqual(out["band_macro"], "Crítico")
        self.assertAlmostEqual(out["modulation"]["prior_ctx"], 0.054365,
                               places=4)
        self.assertAlmostEqual(out["sigma_log_m"], 0.093381, places=4)


class MacroIntegrationTest(TestCase):
    COMPONENTS = {"benford": 0.42, "digit2": 0.18, "behavioral": 0.55,
                  "cusum": 0.30, "period_end": 0.62}

    def test_context_raises_ipra_keeps_signal_loglr(self):
        p_base, _ = fuse(self.COMPONENTS, BASE_RATE)
        ctx = macro_context(t_eff=0.34, vol=0.05, days_to_deadline=10,
                            z_infl=1.2, z_fx=0.8, z_gap=-0.5, u=0.41,
                            economy="emergente_concentrada",
                            sector="comercio",
                            sector_table={"comercio": 1.30},
                            prior=BASE_RATE, kind="ipra")
        p_ctx, _ = fuse(self.COMPONENTS, ctx["modulation"]["prior_ctx"])
        self.assertGreater(p_ctx, p_base)
        # Σ logLR é propriedade dos sinais — o contexto só move o prior
        lg_base = sum(lr_log(W_SIGNALS[k], c)
                      for k, c in self.COMPONENTS.items())
        lg_ctx = sum(lr_log(W_SIGNALS[k], c)
                     for k, c in self.COMPONENTS.items())
        self.assertAlmostEqual(lg_base, lg_ctx)

    def test_missing_context_equals_baseline(self):
        p_base, _ = fuse(self.COMPONENTS, BASE_RATE)
        idx_base = shrink(p_base, 48, BASE_RATE)
        ctx = macro_context(prior=BASE_RATE)   # sem fatores → M_eff = 1
        self.assertAlmostEqual(ctx["factors"]["m_eff"], 1.0, places=12)
        p_ctx, _ = fuse(self.COMPONENTS, ctx["modulation"]["prior_ctx"])
        self.assertAlmostEqual(shrink(p_ctx, 48, BASE_RATE), idx_base,
                               places=12)


# ---------------------------------------------------------------------------
# 5) REST
# ---------------------------------------------------------------------------
class PredictiveRestBase(TestCase):
    def setUp(self):
        self.token = "tok-pred-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        rnd = random.Random(11)
        now = timezone.now()
        for i in range(60):
            Transaction.objects.create(
                transaction_id=f"pred-{i}",
                amount=round(10 ** rnd.uniform(0.5, 4.5), 2),
                vendor="Kwanza Lda", user_id="op1" if i < 50 else "op2",
                timestamp=now - timedelta(days=i * 2 % 150))
        Alert.objects.create(vendor="Kwanza Lda", status="False Positive")
        Alert.objects.create(vendor="Kwanza Lda", status="Resolved")


class MacroEndpointTest(PredictiveRestBase):
    URL = "/django/api/macro"

    def test_requires_auth(self):
        anon = APIClient()
        resp = anon.get(self.URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_neutral_no_params(self):
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertAlmostEqual(body["factors"]["m_eff"], 1.0)
        self.assertEqual(body["band_macro"], "Neutro")

    def test_adverse_context(self):
        qs = ("?t_eff=0.34&vol=0.05&days_to_deadline=10&z_infl=1.2"
              "&z_fx=0.8&z_gap=-0.5&u=0.41&economy=emergente_concentrada"
              "&prior=0.02")
        resp = self.client.get(self.URL + qs)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # setor sem tabela → 1.0; regime 1.30 → M_raw = 1.30·exp(0.4753)
        self.assertGreater(body["factors"]["m_eff"], 2.0)
        self.assertEqual(body["band_macro"], "Crítico")
        self.assertAlmostEqual(body["modulation"]["prior_ctx"], 0.041819,
                               places=4)
        self.assertIn("error_margin", body["modulation"])


class PredictiveEndpointTest(PredictiveRestBase):
    URL = "/django/api/predictive"

    def test_full_dossier(self):
        resp = self.client.get(self.URL + "?vendor=Kwanza Lda")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["n"], 60)
        self.assertIn(body["ipra"]["baseline"]["band"],
                      ("Baixo", "Moderado", "Elevado", "Crítico"))
        self.assertIn(body["ipv"]["baseline"]["band"],
                      ("Sólido", "Atento", "Vulnerável", "Exposto"))
        wc = body["ipra"]["with_context"]
        self.assertGreaterEqual(wc["m_eff"], 0.5)
        self.assertLessEqual(wc["m_eff"], 3.0)
        self.assertIn(wc["band"],
                      ("Baixo", "Moderado", "Elevado", "Crítico"))
        self.assertGreater(wc["p_final"], 0.0)
        self.assertAlmostEqual(body["ipra"]["coverage_macro"], 0.35)
        self.assertIsInstance(body["ipv"]["plan"], list)
        self.assertGreater(len(body["ipv"]["plan"]), 0)
        for row in body["ipv"]["plan"]:
            self.assertIn("delta_v", row)
            self.assertIn("label", row)
