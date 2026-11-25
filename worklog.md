# Worklog — AuditAI Omni

Diário de desenvolvimento. Cada tarefa: feature branch → testes verdes →
commit → merge → entregáveis. Este ficheiro é agora rastreado pelo git.

---

## 2026-11-25/26 — Família Preditiva no repo: IPRA · IPV · **MACRO (nova fórmula)**

Branch `feature/predictive-macro` → merge em `main`.

### O que entrou

- **`dashboard/predictive_service.py`** — IPRA (deteção): fusão bayesiana
  assimétrica (γ=0.3, n0=25, π_b=0.02, Σw=10) dos sinais C1 Benford 1.º
  dígito (MAD/Nigrini), C2 2.º dígito (**lei marginal correta**
  P(d2=d)=Σ_f log10(1+1/(10f+d)) — o uso de log10(1+1/(10+d)) como
  marginal foi detectado e corrigido pelos testes), C3 comportamental
  (pesos Durtschi 0.15/0.35/0.15/0.25/0.10 com renormalização), C4 CUSUM
  mensal (k=0.5, h=5), C5 fecho de período ((u−0.12)/0.35); bandas
  Baixo<0.20≤Moderado<0.40≤Elevado<0.60≤Crítico; P_floor/P_ceil; drivers.
- **`dashboard/prevention_service.py`** — IPV (prevenção): noisy-or
  ponderado 6 eixos (Σw=1), encolhimento π_v=0.15, decomposição EXATA
  ΔV_i = λ·e_i·w_i·p_i·Π_{j≠i}(1−w_j p_j) (tolerância 1e-9 nos testes),
  plano ordenado, momentum/ETA (dead-zone 0.03, teto 12), bandas
  Sólido<0.15≤Atento<0.30≤Vulnerável<0.50≤Exposto; eixos v1 (concentração
  de operador) e v5 (falsos positivos) calculados dos dados reais.
- **`dashboard/context_service.py`** — **MACRO, a nova fórmula**:
  Modulador A priori Contextual de Risco Observável. Composição de 5
  conceitos (probit Φ por base de fator · assimetria γ=0.35 · log-odds ·
  encolhimento por cobertura · delta method) num multiplicador
  M_eff = clip(m_setor·m_regime·exp(Σβ·h(2(s−0.5))), 0.5, 3.0)^c que
  modula π_b/π_v antes de qualquer sinal; caps IPRA (0.25×, 4.0×), IPV
  (0.50×, 3.0×); banda Calmo/Neutro/Adverso/Crítico; margem de erro
  IC95% = 1.96·P(1−P)·σ(log M). Proposições P1–P5 demonstradas em
  `docs/MACRO.md`.
- **Endpoints** — `GET /django/api/macro` (dossiê MACRO por parâmetros)
  e `GET /django/api/predictive/?vendor=X` (IPRA+IPV com/sem contexto +
  plano ΔV); autenticação ApiToken padrão (IsViewerOrAbove).
- **Testes** — `dashboard/tests/test_predictive_context.py`: 50 testes
  (monotonicidades, assimetria 1/γ exata, decomposição ΔV 1e-9, bandas
  nos cortes, cobertura→neutralidade, margens, REST 200/401). CI atualizado.
- **`scripts/macro_demo.py`** + **`docs/MACRO.md`** — exemplo numérico
  reprodutível e documento formal da descoberta (definições D1–D6,
  proposições com demonstração, integração, limitações).
- **README** — secção "Família Preditiva AuditAI".

### Números reais do exemplo MACRO (Comércio Kwanza Lda)

- Estresses: impostos 0.815929 · ciclo 0.737286 · sazonal 0.828571
- M_raw = 1.30·1.30·e^0.475269 = **2.718275** [Crítico]; cobertura 1.00
- Assimetria medida: razão = **2.8571 = 1/γ exato** (P3 verificada)
- Cobertura 0.35 → M_eff = 1.071436; cobertura 0 → M_eff = 1.000000 (P4)
- IPRA: P_final 0.022954 [Baixo] → 0.062052 [Baixo] com contexto (×2.70;
  Σ logLR dos sinais inalterado +0.2072 — o contexto só move o prior)
- IC95%: ±0.010652 → [0.051399, 0.072704] (P5)
- IPV: V_final 0.348105 [Vulnerável] → 0.436372 [Vulnerável]
- Plano: v1 ΔV=0.067320 · v3 ΔV=0.035232 · v2 ΔV=0.021723

### Verificação

- Suíte nova: **50/50 verdes**; regressão CI completa: **589 testes OK**
  (40 módulos, sqlite de teste) em 12.2s.
- `python manage.py check` limpo; sem migrações novas (serviços puros).

### Histórico anterior (condensado de worklog local anterior ao recycle)

- Task 47: AppImage executável 1.0.0 (desktop Linux).
- Task 48: matemática IPRA/IPV validada E2E — 12 entidades → 1 Vulnerável /
  9 Atento / 2 Sólido (média 0.2244); Sombra SA V=0.2767 conf 0.88, plano
  V1 −11.1pp / V4 −4.9pp / V3 −1.3pp → 0.0910 Sólido; IPRA Sombra
  P=0.801 [Crítico] conf 1.00.
- Excel Studio × IA (Tasks 43–46): copiloto na cadeia NIM/Nemotron,
  Insights IA, Fórmula IA, Qualidade de Dados IA, Amostragem IA.
- Banco de Imagens + fallback sem FLUX; backup PostgreSQL com verificação.
