# AuditAI — Plataforma de Auditoria com Excel Super Assistente e Copiloto Global

[![CI](https://github.com/kenjunior01/audit/actions/workflows/ci.yml/badge.svg)](./.github/workflows/ci.yml)

Plataforma de auditoria financeira (Django REST + Next.js 14) com um
**Excel Studio completo** (importação inteligente, análise forense, reconciliação
e export premium) e um **Copiloto Global** — modelo de suporte em três camadas
(reativa, proativa e programada) que cobre toda a plataforma, fala português e
**age com confirmação humana**.

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  Next.js 14  :3000          │  /api  │  Django REST  :8000          │
│  dashboard + Excel Studio   │ ─────► │  14 ferramentas do copiloto  │
│  copiloto (SSE + voz)       │ proxy  │  Excel forense · PDF · email │
└─────────────────────────────┘        └───────────┬──────────────────┘
                                                   │
                              ┌────────────┬───────┴─────┬─────────────┐
                              │ PostgreSQL │   Redis     │  EXAONE     │
                              │  (dados)   │  (celery)   │ (llama.cpp) │
                              └────────────┴─────────────┴─────────────┘
```

---

## Funcionalidades

### Excel Studio (aba dedicada no dashboard)

| Aba | O que faz |
|---|---|
| **Importar** | Upload XLSX/CSV multi-folha, mapeamento fuzzy PT/EN, pré-visualização, score de qualidade, padronização |
| **Analisar** | Lei de Benford (MAD), duplicados exatos e fuzzy, valores redondos, fins de semana, split transactions |
| **Reconciliar** | Cruzamento automático entre folhas/fontes com relatório de diferenças |
| **Exportar** | Workbook premium com gráficos nativos, formatação condicional, autofiltro e tabelas reais |

### Excel Auto — a experiência de 1 clique

Largue o ficheiro (ou clique "Testar com exemplo") e receba numa única resposta:
folha+colunas detetadas, qualidade 0-100 com nota A-D, risco de auditoria
(Benford, duplicados, fraccionamento, redondos, weekend), insights narrativos e
ações de 1 clique (importar / relatório premium / copiloto). Reconciliação Auto:
cruze 2 ficheiros ou contra a base de dados sem configurar nada. **Dossiê
completo**: 1 clique que importa os dados, gera o painel REA e consolida tudo
num único workbook (Dossiê, Painel, Qualidade, Benford, Duplicados,
Fraccionamento, Redondos, Dados). **Alertas sugeridos**: os padrões detetados
(fim-de-semana, transações acima da materialidade, concentração por fornecedor)
viram cartões com a regra pronta — um clique cria o alerta no BI Studio, que
passa a notificar quando o padrão voltar a aparecer nos dados importados.
**Alertas ao vivo**: os alertas BI são avaliados automaticamente (celery beat
com `AUDIT_ALERTS_ENABLED=true` ou `manage.py run_bi_alerts` em cron clássico)
e a transição ok→violação dispara notificação na Central — sem depender de
alguém clicar em "Avaliar". **Análise Comparativa**: compare o ficheiro com um
período mais recente — variação de linhas/totais, maiores aumentos e reduções
por fornecedor, fornecedores novos/desaparecidos, padrões (fim-de-semana,
duplicados, materialidade) e **documentos repetidos entre os dois ficheiros**
(sinal clássico de pagamento duplicado), com veredicto determinístico
(estável/moderado/acentuado) e relatório Excel dedicado.

### Copiloto IA (NL → Excel)

Conversa em português ou inglês: *"mostra o top 10 fornecedores por valor"*, *"adiciona uma coluna com o mês"*.
Responde com transformação aplicada + pré-visualização + **fórmulas prontas a copiar (PT e EN)** e gera um
workbook auto-atualizável (`tblDados` + KPIs vivos + folha de fórmulas).

### Copiloto Global — suporte em 3 camadas

| Camada | Versão | Descrição |
|---|---|---|
| **Reativa** | v1-v3 | Chat com 14 ferramentas sobre dados vivos (alertas, transações, casos, SLA, Benford, previsão de risco…), streaming SSE, trace agéntico por ferramenta, feedback 1-5 |
| **Proativa** | v4, v6 | Sinais proativos em tempo real (badge + cartões clicáveis), botão **IA** em cada linha de alerta/caso, ditadura por voz (pt-PT) |
| **Programada** | v5, v8 | **Digest** diário/semanal por cron/beat: email (texto + **HTML premium** + **PDF executivo**), dedupe por (período, dia), log imutável, card no dashboard com pré-visualização |

### Ações agénticas com confirmação humana (v7)

O copiloto **propõe** ("resolve o alerta 1"), o utilizador **confirma** no cartão, o backend
**executa** com whitelist fechada de ações/valores, validação de papel (viewer nunca executa)
e registo em `ImmutableAuditLog` com hash chain.

### Restante plataforma

Dashboard executivo, alertas com severidade, casos com comentários/anexos/relatório,
transações com inspetor, SLA, agents de investigação (LangGraph), governança de IA,
regras, integrações/webhooks, riscos geográficos, gestão de referências.

### Central de Notificações in-app

Sino no header (todas as páginas) com contador de não lidas, polling a 60s,
dropdown com severidades (info/sucesso/aviso/crítico), marcação individual/global
e navegação direta para a origem. Eventos gerados automaticamente: alertas
críticos/altos, transições de estado de casos, execuções de agentes, importações
Excel e mais — via `notifications_service` (resiliente, com dedupe de 10 min).

### Relatório Global de Auditoria (PDF)

Documento formal gerado sobre dados vivos: capa confidencial, sumário executivo
com KPIs, metodologia, análise de risco (distribuição por severidade, top
fornecedores, Benford MAD, tendência 7d), achados principais, carteira de casos,
qualidade de dados e recomendações determinísticas. Preview JSON no cartão do
dashboard + download em `/api/reports/audit/pdf?days=30` (papel auditor/admin).

### Observabilidade e documentação da API

- `GET /django/api/metrics` — métricas em formato Prometheus (HTTP por rota/estado,
  latência com buckets, gauges de domínio) via `MetricsMiddleware`, sem dependências.
- OpenAPI 3: `/django/api/schema` + **Swagger UI** `/django/api/schema/swagger-ui`
  + Redoc `/django/api/schema/redoc` (drf-spectacular) — link nas Configurações.

### Registo e integrações públicas gratuitas

O registo (`POST /django/api/auth/register`) cria utilizador, perfil da
organização e token de acesso atomicamente; login em `/django/api/auth/login`.
O backend inclui integrações sem chave para câmbio (Frankfurter), países (REST
Countries), meteorologia (Open-Meteo), notícias (GDELT) e consulta de empresas
brasileiras (BrasilAPI). Rotas e fontes oficiais de legislação:
`GET /django/api/integrations/public`. Todas as rotas de dados externos exigem
token viewer e devolvem erro explícito se o fornecedor estiver indisponível.

O catálogo [public-apis](https://github.com/public-apis/public-apis) reúne
serviços independentes e não é uma API única; por isso, a plataforma integra
um conjunto inicial relevante, sem presumir cobertura, disponibilidade ou
termos uniformes para todos os serviços listados.

### EXAONE 4.0

O perfil Compose `ai` executa o modelo EXAONE 4.0 1.2B Q4_K_M GGUF através de
llama.cpp, que expõe uma API compatível com OpenAI. Arranque:
`docker compose --profile ai up -d --build`. O primeiro arranque descarrega o
modelo; os dados ficam no volume `exaone_data`. Consulte
[README_INFRA.md](README_INFRA.md) para detalhes e endpoints.

### BI Studio — Power BI parity via metodologia REA

Aplicámos o método **REA (Reverse Engineer Anything)** — escolher o alvo,
preparar o ambiente, **compreender antes de construir** (com evidências),
iterar nos detalhes e **ir além do original** — com o Power BI como alvo
principal (e Tableau, Alteryx, Power Query e IDEA/ACL como secundários).
Resultado, na página **BI Studio** (`/bi`):

| Capacidade do mercado | Implementação nossa |
|---|---|
| DAX (medidas + filter context) | Motor `bi_service.py`: árvore de expressão JSON com whitelist fechada — `agg` (sum/avg/count/nunique/min/max/median), `calc` (CALCULATE), `ratio/diff/add/mul`, `yoy/mom` (time-intelligence), `pct_of_total`, `running_total`, `const` |
| Matrix visual | `/bi/matrix` — pivot dinâmico com margens de linha/coluna e totais |
| Decomposition Tree | `/bi/decompose` — contribuição hierárquica nível a nível com % do pai |
| What-if parameters | `/bi/whatif` — cenário base vs. ajustado com slider |
| Pareto 80/20 | `/bi/pareto` — vital few vs. trivial many com linha acumulada |
| Drillthrough | `/bi/drillthrough` — transações sob qualquer ponto do visual (clique) |
| Power Query (applied steps) | `ETLPipeline` — receita ETL re-executável (12 operações: map_columns fuzzy, filter, derive, dedupe, fillna, cast, sort, dropna, select, upper_headers, trim_text, rename) com log por passo e importação idempotente |
| RLS (Row-Level Security) | Modelo `RLSRule` + enforcement na fonte do motor (por user_id ou role, por dimensão) |
| Tableau LOD | `group_measure` por qualquer dimensão temporal (month/quarter/weekday/date/week) ou categórica |
| Alteryx workflow | Pipelines CRUD + execução com ficheiro + pré-visualização |
| Q&A em linguagem natural | **Vamos além**: o Copiloto Global responde sobre os mesmos dados vivos com 14 tools |

Medidas podem ser guardadas (`BIMeasure`) e reutilizadas; tudo respeita RLS
e as permissões por papel (viewer consulta; auditor/admin gere).

#### BI Studio v2 — relatórios interativos, Q&A e alertas (iteração REA "ir além")

| Capacidade do mercado | Implementação v2 |
|---|---|
| Relatórios multi-visual (canvas do Power BI) | Modelo `BIDashboard` — visuais fixados + slicers partilhados; execução numa só chamada (`/bi/dashboards/:id/run`) com **cross-filtering** por clique |
| Séries temporais + analytics pane | `/bi/series` — granularidades day/week/month/quarter/year + média móvel + acumulado |
| Forecast | `/bi/forecast` — tendência linear (mínimos quadrados) com intervalo ±σ para N períodos |
| Deteção de anomalias | `/bi/anomaly` — z-score da série com limiar configurável (1.0–5.0) |
| Waterfall | `/bi/waterfall` — contribuição incremental por membro até ao total |
| Funnel | `/bi/funnel` — fases com conversão fase-a-fase e % da 1ª fase |
| Scatter com quadrantes | `/bi/scatter` — duas medidas por dimensão + correlação de Pearson |
| KPI com alvo | `/bi/kpi` — valor vs. alvo, estado on_track/warn/critical e tendência 30d |
| Q&A visual (Copilot) | `/bi/qa` — "Pergunte aos dados": parser determinístico PT/EN (agregação, dimensão, tempo, fornecedor, estado, top N, modo) → visual executado + especificação auditável |
| Export data com formatação | `/bi/export/xlsx` — Excel com título, cabeçalho estilizado, formatos numéricos, escala de cor condicional, totais, autofilter e painéis congelados |
| Data alerts | Modelo `MeasureAlert` + `/bi/alerts/run` — avalia medidas e notifica a Central de Notificações na transição para breach (severity warn/critical) |

#### Painel Auto — experiência de 1 clique (método REA, passo 5 "ir além")

A página **Painel Auto** (`/studio`, endpoint `POST /bi/auto`) traz a simplicidade
que faltava: **um clique, painel completo, zero configuração**. O motor faz
*engenharia reversa do dataset* — deduz a medida padrão, pontua as dimensões
pela utilidade analítica (cobertura × cardinalidade saudável 2–12) e compõe
automaticamente:

- **KPIs**: volume total, transações, ticket médio, maior transação e líder;
- **Visuais**: volume por dimensão principal, distribuição por secundária,
  evolução mensal com média móvel, Pareto 80/20, anomalias (z-score) e
  projeção a 3 meses;
- **Insights narrativos determinísticos** (concentração, tendência, anomalias);
- **Slicers simples** (período em chips + clique no gráfico filtra o valor)
  e transações recentes com drillthrough;
- **Pergunte aos dados**: caixa Q&A em linguagem natural (reutiliza o motor
  determinístico `/bi/qa`) — a resposta chega com gráfico, visual deduzido,
  nível de confiança e explicação da interpretação;
- **Alertas ao vivo**: estado das regras de monitorização criadas no Excel
  Auto/BI Studio (ponto verde/vermelho, valor atual vs. limiar, última
  avaliação, contagem de violações) + botão "Avaliar agora"; quando alguma
  regra está em violação, o cabeçalho mostra o badge vermelho "N em violação".
  A avaliação automática hora a hora continua a cargo do agendamento
  (`run_bi_alerts` via celery beat / cron).

Cada decisão do motor é devolvida em `meta.choices` com a evidência
(espírito REA: findings com provas). Utilizadores avançados continuam com o
BI Studio (`/bi`) para medidas DAX-like, pipelines ETL, RLS e relatórios
guardados.

---

## Arranque rápido

### Opção A — Docker (recomendado)

```bash
cp .env.example .env
# Gere valores diferentes e preencha AUDIT_DJANGO_SECRET_KEY e POSTGRES_PASSWORD:
python -c 'import secrets; print(secrets.token_urlsafe(64))'
python -c 'import secrets; print(secrets.token_hex(32))'
docker compose up -d --build    # db + redis + api :8000 + web :3000

# opcionais
docker compose --profile worker up -d      # + celery worker e beat (digest/alertas)
docker compose --profile ai up -d          # + EXAONE/llama.cpp + Qdrant
```

Abrir **http://localhost:3000** — API em http://localhost:8000/django/api/health.

### Opção B — desenvolvimento local

```bash
# backend
cd django_app
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000

# frontend (noutro terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

> Sem o serviço EXAONE ativo tudo funciona em **modo determinístico** (router de regras) — o LLM
> só melhora a síntese. Sem SMTP, o email do digest fica em modo console.

### Credenciais demo

Para dados locais de demonstração, execute `docker compose exec backend python manage.py seed_demo` e entre com `demo@audit.pt` / `demo1234` (papel **admin**). Este utilizador e o token determinístico do seed são apenas para demonstração: não execute o seed em produção nem reutilize estas credenciais.

---

## Variáveis de ambiente (principais)

| Variável | Predefinição | Descrição |
|---|---|---|
| `AUDIT_DEBUG` | `False` | Modo debug |
| `AUDIT_ALLOWED_HOSTS` | `localhost,127.0.0.1,backend` | Hosts permitidos (CSV) |
| `AUDIT_DJANGO_SECRET_KEY` | obrigatório no Compose | Segredo Django longo e aleatório |
| `AUDIT_DATABASE_URL` | SQLite local | `postgres://user:pass@host:5432/audit` |
| `AUDIT_CORS_ORIGINS` | `localhost:3000` | Origens CORS (CSV) |
| `AUDIT_EMAIL_BACKEND` | console | SMTP real: `…smtp.EmailBackend` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` | — | Credenciais SMTP |
| `AUDIT_DIGEST_EMAILS` | — | Destinatários do digest (CSV) |
| `AUDIT_DIGEST_ENABLED` | `False` | Agenda via celery beat |
| `AUDIT_DIGEST_HOUR` | `7` | Hora do digest diário |
| `AUDIT_LLM_API_STYLE` | `openai-compatible` no Compose | Protocolo `openai-compatible` (llama.cpp) ou `ollama` |
| `AUDIT_LLM_BASE_URL` | `http://exaone:8080/v1` no Compose | URL base do servidor de inferência |
| `AUDIT_OLLAMA_MODEL` | `exaone4.0-1.2b` no Compose | Alias servido pelo modelo local |
| `AUDIT_OLLAMA_TIMEOUT` | `25` | Timeout do LLM (s) |
| `AUDIT_OLLAMA_PROBE_TTL` | `60` | Cooldown da sonda de disponibilidade; o copiloto degrada para regras quando o modelo está indisponível |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` | Base da API para o proxy do Next |

Lista completa e infra self-hosted: [README_INFRA.md](README_INFRA.md) e
[.env.example](.env.example).

---

## API — mapa rápido

```
GET  /django/api/health                     → estado do serviço (público)
POST /django/api/auth/login|register        → sessão (token)

# Excel
POST /django/api/excel/preview|import|analyze|reconcile|export
POST /django/api/excel/assistant            → copiloto NL→Excel
POST /django/api/excel/assistant/apply      → aplica plano e devolve .xlsx

# Copiloto Global
POST /django/api/ai/copilot                 → chat agéntico
POST /django/api/ai/copilot/stream          → streaming SSE
GET  /django/api/ai/copilot/briefing        → briefing executivo
GET  /django/api/ai/copilot/insights        → insights
GET  /django/api/ai/copilot/digest          → último digest
POST /django/api/ai/copilot/digest          → gerar agora (admin)
GET  /django/api/ai/copilot/digest/pdf      → PDF executivo
GET  /django/api/ai/copilot/digest/email/preview → email HTML no browser
POST /django/api/ai/copilot/act             → executar ação proposta (pós-confirmação)
POST /django/api/ai/copilot/feedback        → avaliar resposta (1-5)
GET  /django/api/ai/copilot/feedback/stats  → métricas de qualidade
```

---

## Testes

```bash
cd django_app
python manage.py test \
  dashboard.tests.test_copilot_v8 dashboard.tests.test_copilot_v7 \
  dashboard.tests.test_copilot_v6 dashboard.tests.test_copilot_v5 \
  dashboard.tests.test_copilot_v4 dashboard.tests.test_copilot_v3 \
  dashboard.tests.test_copilot dashboard.tests.test_excel_copilot \
  dashboard.tests.test_excel_studio dashboard.tests.test_critical_flows \
  dashboard.tests.test_health
```

**166 testes verdes** · CI no GitHub Actions corre check + migrações +
suítes + build do Next em cada PR (`.github/workflows/ci.yml`).

## Estrutura

```
django_app/           API Django (dashboard app: models/views/services/tasks)
  dashboard/
    excel_service.py        análise forense Excel (~1000 linhas)
    excel_ai_service.py     copiloto NL→Excel (planos, fórmulas PT/EN)
    copilot_service.py      14 ferramentas + briefing + sinais + digest + PDF + HTML
    copilot_actions.py      ações agénticas whitelisted (v7)
    tasks.py                celery: digest programado com email/PDF
frontend/             Next.js 14 (dashboard, Excel Studio, copiloto dock)
docker-compose.yml    stack completa (perfis: core, worker, ai)
```

## Histórico de entregas

| Versão | Entrega |
|--------|---------|
| Excel Studio | Import inteligente, forense (Benford/duplicados), reconciliação, export premium |
| Excel Copilot | NL→planos com fórmulas PT/EN e workbook vivo |
| Copiloto v1-v3 | Ferramentas sobre dados vivos, briefing, SSE, trace, feedback |
| Copiloto v4 | Sinais proativos + métricas de qualidade na Governança |
| Copiloto v5 | Digest programado (cron/beat, email, dedupe, auditoria) |
| Copiloto v6 | PDF executivo, integração contextual nas linhas, voz pt-PT |
| Copiloto v7 | Ações agénticas com confirmação humana + auditoria imutável |
| Copiloto v8 | Email HTML premium + pré-visualização no browser |
| Hardening | CI, Docker completo (perfis), health check, SMTP configurável, README |
