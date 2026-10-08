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
                              │ PostgreSQL │   Redis     │  Ollama     │
                              │  (dados)   │  (celery)   │ (LLM local) │
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

---

## Arranque rápido

### Opção A — Docker (recomendado)

```bash
cp .env.example .env            # editar segredos
docker compose up -d --build    # db + redis + api :8000 + web :3000

# opcionais
docker compose --profile worker up -d      # + celery (digest por agenda)
docker compose --profile ai up -d          # + Ollama + Qdrant
docker compose exec ollama ollama pull deepseek-r1:8b
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

> Sem Ollama tudo funciona em **modo determinístico** (router de regras) — o LLM
> só melhora a síntese. Sem SMTP, o email do digest fica em modo console.

### Credenciais demo

`demo@audit.pt` / `demo1234` (papel **admin**) — ou via API:
`Authorization: Bearer demo-token-omni`.

---

## Variáveis de ambiente (principais)

| Variável | Predefinição | Descrição |
|---|---|---|
| `AUDIT_DEBUG` | `False` | Modo debug |
| `AUDIT_ALLOWED_HOSTS` | `*` | Hosts permitidos (CSV) |
| `AUDIT_DJANGO_SECRET_KEY` | `change-me` | Segredo Django (obrigatório em prod.) |
| `AUDIT_DATABASE_URL` | SQLite local | `postgres://user:pass@host:5432/audit` |
| `AUDIT_CORS_ORIGINS` | `localhost:3000` | Origens CORS (CSV) |
| `AUDIT_EMAIL_BACKEND` | console | SMTP real: `…smtp.EmailBackend` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` | — | Credenciais SMTP |
| `AUDIT_DIGEST_EMAILS` | — | Destinatários do digest (CSV) |
| `AUDIT_DIGEST_ENABLED` | `False` | Agenda via celery beat |
| `AUDIT_DIGEST_HOUR` | `7` | Hora do digest diário |
| `OLLAMA_URL` | `localhost:11434` | Endpoint do LLM local |
| `AUDIT_OLLAMA_MODEL` | — | Ex.: `deepseek-r1:8b` (vazio = modo regras) |
| `AUDIT_OLLAMA_TIMEOUT` | `60` | Timeout do LLM (s) |
| `AUDIT_OLLAMA_PROBE_TTL` | `60` | Cooldown da sonda de disponibilidade (s); Ollama em baixo → chat degrada para regras sem esperar o timeout |
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
