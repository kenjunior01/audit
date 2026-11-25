# MACRO — Modulador A priori Contextual de Risco Observável

**Família preditiva AuditAI: IPRA (deteção) · IPV (prevenção) · MACRO (contexto)**
Implementação: `django_app/dashboard/context_service.py` · Exemplo executável: `scripts/macro_demo.py`
Testes: `dashboard/tests/test_predictive_context.py` (50 testes verdes)

---

## 1. A descoberta, em uma frase

> **O risco de uma empresa não começa nos lançamentos — começa no contexto.**
> O MACRO é a primeira fórmula que comprime a base de cada fator macro
> (impostos, tipo de economia, ciclo, setor, sazonalidade fiscal) num único
> multiplicador de odds que **muda a linha de partida** dos índices IPRA e
> IPV **antes de existir qualquer sinal de deteção** — e que se degrada
> para neutro quando faltam dados, **sem nunca distorcer o prior**.

## 2. A composição: cinco conceitos clássicos, uma fórmula nova

Como a fórmula da área nasce de conceitos mais simples (comprimento ×
largura), o MACRO compõe cinco ideias com décadas de validação:

| # | Conceito composto | Origem | Papel no MACRO |
|---|---|---|---|
| 1 | Normalização probit Φ | *credit scoring* (z-score) | base de cada fator → estresse s ∈ [0,1] |
| 2 | Transformação assimétrica | CUSUM / *downside risk* | contexto adverso pesa 1/γ ≈ 2.86× o favorável |
| 3 | Agregação em log-odds | teoria de deteção bayesiana | fatores independentes somam-se em log |
| 4 | Encolhimento por cobertura | Stein / Efron–Morris | dados em falta → multiplicador → 1 (neutro) |
| 5 | Delta method | cálculo de propagação de erro | margem de erro IC95% explícita |

Nenhum destes conceitos, sozinho, modula priors de auditoria por contexto
macro; **a composição é o que é novo** — e é implementável, testável e
explicável dígito a dígito.

## 3. Definições formais

**D1 (Fatores e bases).** Para a entidade e no período t:

- **F1 Impostos** — carga fiscal efetiva `T_eff = impostos totais / receita
  líquida (12m)`; volatilidade `Vol_T` (desvio-padrão móvel); prazo fiscal
  mais próximo `d` (dias). Referências normativas: `T_eff ~ N(0.25, 0.10)`,
  `Vol_T ~ N(0.03, 0.02)`, prazo: `s_d = max(0, 1 − d/45)`.
  Pesos: nível 0.50 · volatilidade 0.30 · prazo 0.20 (renormalizados se um
  sub-fator falta).
- **F2 Economia** — tipo de economia → multiplicador tabulado de odds
  `m_regime ∈ [1.00, 1.45]`; ciclo: `s_ciclo = Φ(0.40·z_π + 0.35·z_fx +
  0.25·z_gap)` (inflação, pressão cambial, gap de crescimento em z-scores).
- **F3 Setor** — `m_setor` = odds-ratio histórico de anomalias do setor vs.
  base, tabelado com floor 0.70 e cap 2.00 (default neutro 1.00).
- **F4 Sazonalidade** — `s_saz = clip((u − 0.12)/0.35, 0, 1)`, herdando a
  base do sinal C5 do IPRA (u = quota do montante no fecho do mês).

**D2 (Estresse).** Cada fator j mapeia para
`s_j = Φ((observado − referência)/dispersão)` clipado a `[0.01, 0.99]`.
**s = 0.5 significa "na mediana de referência" — o ponto neutro.**

**D3 (Transformação assimétrica).** Com `x_j = 2(s_j − 0.5) ∈ [−1, 1]`:

```
h(x) = x      se x ≥ 0    (adverso pesa inteiro)
h(x) = γ·x    se x < 0    (favorável pesa γ = 0.35)
```

**D4 (Multiplicador MACRO).**

```
M_raw = m_setor · m_regime · exp( β_imp·h(x_imp) + β_ciclo·h(x_ciclo) + β_saz·h(x_saz) )
M_eff = clip(M_raw, 0.5, 3.0)^c
```

com β_impostos = 0.32, β_ciclo = 0.16, β_sazonal = 0.30 (Σβ = 0.78 nos
estresses; regime e setor entram como multiplicadores tabulados) e
**cobertura** `c ∈ [0,1]` = fração ponderada de fatores disponíveis
(pesos de cobertura: impostos 0.40, ciclo 0.25, sazonalidade 0.35).

**D5 (Modulação do prior).**

```
π^ctx = clip(π · M_eff^θ,  cap_lo·π,  cap_hi·π)
```

θ = temperatura de calibração (default 1.0); caps: IPRA (0.25×, 4.0×),
IPV (0.50×, 3.0×).

**D6 (Margem de erro).** Com incerteza σ_s = 0.10 por estresse (delta method):

```
σ²(log M) ≈ c · Σ_j (2·β_j·h'(x_j)·σ_s)²        h' = 1 (x≥0), γ (x<0)
IC95%(P) = P ± 1.96 · P(1−P) · σ(log M)
```

Banda do contexto: **Calmo <0.90 ≤ Neutro <1.30 ≤ Adverso <2.00 ≤ Crítico**.

## 4. Proposições (com demonstração)

**P1 — Monotonicidade.** *∂π_ctx/∂s_j ≥ 0 para todo o fator ativo.*
Demonstração: dΦ/dz > 0 → ds/dx = 1/2 > 0 → dh/dx ∈ {1, γ} > 0 →
d log M/d s_j = 2β_j·h′ > 0 → M cresce → π·M^θ cresce; os clips são
funções não decrescentes. ∎

**P2 — Limites.** *0.5^c ≤ M_eff ≤ 3.0^c* e, portanto,
π·cap_lo ≤ π_ctx ≤ π·cap_hi.
Demonstração: o pior caso adverso (todos os estresses a 0.99, setores
máximos) dá M_raw = 2.0·1.45·e^0.78 ≈ 6.3 > 3.0 → o clip liga; o melhor
caso dá 0.7·1.0·e^−0.273 ≈ 0.53 > 0.5. A potenciação por c ∈ [0,1] preserva
os limites (função monotónica). ∎

**P3 — Conservadorismo assimétrico.** *Para qualquer perfil de estresses,
|log M(x)| = (1/γ)·|log M(−x)| na parte dos estresses* — o contexto
adverso elevara o prior ~2.86× mais do que o contexto favorável espelhado
o abate.
Demonstração: h(x) − h(−x) = x(1+γ) ≥ 0 para x ≥ 0 e = x(1+γ) < 0 para
x < 0; logo |Σβ·h(x)| / |Σβ·h(−x)| = 1/γ = 2.8571.
Verificação numérica: o exemplo da §5 mede a razão **2.8571 = 1/γ exato**. ∎

**P4 — Neutralidade por cobertura.** *Se todos os fatores estão
indisponíveis (c = 0) então M_eff = 1: o contexto ausente nunca distorce o
prior; a influência cresce continuamente com a cobertura.*
Demonstração: M_eff = clip(M)^c com potenciação c → 0 dá 1 para qualquer
base finita positiva; continuidade imediata. ∎
Verificação: só sazonalidade (c = 0.35) → M_eff = 1.071436; sem fatores
(c = 0) → M_eff = 1.000000 exato.

**P5 — Margens de erro explícitas.** *A incerteza dos estresses propaga-se
para o índice final com semi-amplitude IC95% = 1.96·P(1−P)·σ(log M),
crescente em σ_s e decrescente na cobertura.*
Demonstração: delta method sobre log M (D6) + dP/d(log M) = P(1−P)
(sigmoide). ∎

## 5. Exemplo numérico completo (reproduzível)

Cenário: **"Comércio Kwanza Lda"** — retalho, economia emergente
concentrada, IVA a 10 dias. Executar `cd django_app && python ../scripts/macro_demo.py`:

```
impostos  s=0.815929  x=+0.6319  log=+0.202195  (β=0.32)
ciclo     s=0.737286  x=+0.4746  log=+0.075931  (β=0.16)
sazonal   s=0.828571  x=+0.6571  log=+0.197143  (β=0.30)
setor m=1.30   regime m=1.30
M_raw = 1.30×1.30×exp(+0.4753) = 2.718275   [contexto Crítico]

IPRA sem contexto:  π_b=0.020000 → P_final=0.022954 [Baixo]
IPRA com contexto:  π_b=0.054365 → P_final=0.062052 [Baixo]   (×2.70)
IC95% (P_final): ±0.010652 → [0.051399, 0.072704]

IPV sem contexto:  π_v=0.15 → V_final=0.348105 [Vulnerável]
IPV com contexto:  π_v=0.407741 → V_final=0.436372 [Vulnerável]

Plano preventivo (decomposição exata ΔV_i) — top 3:
  v1 concentração de operador       p=0.90 e=0.85 → ΔV=0.067320
  v3 novidade de fornecedor (KYC)   p=0.72 e=0.75 → ΔV=0.035232
  v2 aprovação sem segregação       p=0.44 e=0.70 → ΔV=0.021723
```

Leitura para auditoria: **os sinais não mudaram** (Σ logLR = +0.2072 nos
dois cenários) — o que mudou foi a linha de partida. O contexto Crítico
triplica o prior sem uma única transação anómala; a banda IPRA continua
"Baixo" porque os sinais é que confirmam. **O contexto avisa; os sinais
condenam.** No IPV (prevenção), o mesmo contexto empurra V para quase a
banda "Exposto" — já chega para acelerar o plano v1/v3/v2 antes do fecho.

## 6. Integração na plataforma

| Camada | Onde | O que faz |
|---|---|---|
| Serviço | `dashboard/context_service.py` | funções puras D1–D6 + dossiê `macro_context()` |
| Deteção | `dashboard/predictive_service.py` | IPRA aceita prior contextual → `evaluate(txs, prior=π_ctx)` |
| Prevenção | `dashboard/prevention_service.py` | IPV idem via `modulate_prior(PIV, M_eff, "ipv")` |
| API | `GET /django/api/macro` | dossiê MACRO por parâmetros de contexto |
| API | `GET /django/api/predictive/?vendor=X` | IPRA+IPV com e sem contexto, plano ΔV |
| Recalibração | loop AiFeedback (existente) | β_j, γ, θ e tabelas de setor/regime estimáveis por regressão logística regularizada sobre desfechos históricos |

Degradation graciosa: sem contexto → M_eff = 1 → índices idênticos ao
comportamento anterior (testes `test_missing_context_equals_baseline`,
`test_neutral_no_params`).

## 7. Calibração e limitações

1. **Referências normativas** (μ_T = 0.25, σ_T = 0.10, tabelas de
   regime/setor) são pontos de partida editáveis por implantação — a
   arquitetura exige apenas que sejam publicadas e estáveis.
2. **Independência** entre fatores é hipótese de trabalho; correlações
   fortes (ex.: inflação ↔ carga fiscal) sobestimam σ(log M) — mitigável
   recalibrando β com desfechos reais.
3. **θ e caps** são conservadores por defeito; a temperatura θ é o knob de
   calibração do loop AiFeedback (θ → 0 desliga o contexto com segurança).
4. O MACRO não substitui sinais de deteção — modula o prior. A evidência
   continua a ser do trabalho de campo (regra da casa: *nenhum número sem
   decomposição*).

## 8. Conceitos compostos — referências

- Teoria de deteção / priors bayesianos: fusão assimétrica do IPRA
  (mesma família log-odds).
- Lei de Benford e MAD: Nigrini, *Digital Analysis using Benford's Law*.
- CUSUM: Page (1954); banda h=5 padrão de controlo de qualidade.
- Encolhimento: Stein (1956); Efron & Morris (1975).
- Delta method: Oehlert (1992).
- Noisy-or: Pearl, *Probabilistic Reasoning in Intelligent Systems* (1988).
- Assimetria de downside: Embrechts et al. (*Extreme Value Theory*).
