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

**Digest semanal de alertas**: todas as segundas-feiras às 08:00
(celery beat com `AUDIT_ALERT_DIGEST_ENABLED=true` ou
`manage.py send_alert_digest` em cron clássico), a plataforma resume o estado
dos alertas BI — regras ativas, violações, erros, regras novas no período e
top ofensores por contagem acumulada — e entrega por dois canais: Central de
Notificações (in-app, admin/auditor, severidade crítica quando há violações)
e email para `AUDIT_DIGEST_EMAILS` (best-effort). Quando há LLM disponível
(`llm_client` — EXAONE/Ollama ou API OpenAI-compatible), o digest abre com um
resumo executivo gerado por IA; sem LLM, usa texto determinístico em PT.

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
| **Multimodal** | v10 | **Visão omni**: anexa um URL de imagem no copiloto — o motor omni (NIM) descreve o que vê e a observação entra no contexto agéntico (ex.: foto de uma fatura + «quantas transações como esta há?»); falha da visão degrada para só-texto |

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

**Capa IA (novo)**: o botão «Capa IA» do cartão gera uma ilustração executiva
com FLUX.2-klein-4B (`POST /api/reports/ai-cover`, 768×512, guardada na galeria
NimImage) e o PDF seguinte embute-a na capa via `?cover=<id>`. Capa é
decorativa — falha ou id desconhecido nunca bloqueia o relatório.

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

#### i18n PT/EN

A interface principal é bilingue: o **toggle PT/EN** no cabeçalho troca o
idioma de toda a shell (sidebar, cabeçalho, sair) e do **Painel Auto**
(títulos, slicers, Q&A, alertas ao vivo, estados e mensagens de erro). A
escolha persiste no `localStorage` (`audit-lang`), o padrão é português e a
tradução é feita pelo dicionário plano em `frontend/src/lib/i18n.tsx`
(pares `[pt, en]` — acrescentar uma chave aí basta para estender). As
perguntas de exemplo do Q&A continuam em PT porque o motor determinístico
`/bi/qa` interpreta português; BI Studio (`/bi`) mantém-se em PT na v1.

### Motores de IA — LLM multi-provider (NVIDIA NIM → local)

O cliente LLM da plataforma (`dashboard/llm_client.py`) é uma **cadeia de
motores com fallback automático**: quando um motor falha (rede, auth, modelo
indisponível), o seguinte assume — sem qualquer configuração extra.

| Prioridade | Motor | Configuração |
|---|---|---|
| 1 | **NVIDIA NIM** (Nemotron e catálogo NVIDIA, OpenAI-compatible) | `AUDIT_NVIDIA_API_KEY` (ou `NVIDIA_API_KEY`), `AUDIT_NVIDIA_MODEL` (default `nvidia/nemotron-3-ultra-550b-a55b`) |
| 2 | **OpenAI-compatible** (Groq/EXAONE/vLLM) | `AUDIT_LLM_API_STYLE=openai-compatible` + `AUDIT_LLM_BASE_URL` + `AUDIT_OLLAMA_MODEL` + `AUDIT_LLM_API_KEY` |
| 2 | **Ollama local** | `AUDIT_LLM_API_STYLE=ollama` + `OLLAMA_URL` |

Funcionalidades:
- **Reasoning do Nemotron** (`AUDIT_LLM_REASONING=true` →
  `chat_template_kwargs.enable_thinking`): o raciocínio (`reasoning_content`
  e blocos `<think>`) é descartado automaticamente — só a resposta final
  chega aos utilizadores.
- **Streaming SSE** (`llm_client.generate_stream`) e **geração com metadados**
  (`generate_meta` → provider/modelo/latência por resposta).
- **Toda a IA da plataforma usa a cadeia**: Copiloto Global (chat agéntico),
  Copiloto Excel, serviços de análise AI, digest de alertas e narração BI.
- **Painel "Motores de IA"** em Integrações (`GET /ai/llm/status`): disponibilidade
  ao vivo de cada motor, chave configurada, reasoning, prioridade — com
  **"Testar agora"** (`POST /ai/llm/test`, auditor/admin) que faz um ping real
  e devolve provider, modelo e latência.
- **Resumo IA no Painel Auto** (`POST /bi/narrate`): transforma KPIs e sinais
  num parágrafo executivo em PT gerado pelo motor disponível; sem motor
  disponível, devolve resumo determinístico (nunca derruba o painel).

### NIM Studio — Imagens (FLUX.2-klein-4B) e Visão (omni) + credenciais na BD (novo)

Além do motor de texto, a plataforma integra agora os motores **multimodais**
do catálogo NVIDIA NIM, geridos no painel **Integrações** (cartão
“NIM Studio — Imagens & Visão”):

- **Geração de imagens** — FLUX.2-klein-4B (`POST /ai/nim/image`): prompt,
  tamanho (512–1024, múltiplos de 16 — o upstream rejeita < 512), passos
  (1–8) e seed opcional. Cada
  imagem é guardada na **galeria** (modelo `NimImage`) e servida por
  `GET /ai/nim/images` + `GET /ai/nim/images/<id>/file` (download autenticado).
- **Compreensão de imagem e vídeo** — Nemotron-3-nano-omni-30b-a3b-reasoning
  (`POST /ai/nim/vision`): URL de imagem **ou vídeo** (auto-detetado pela
  extensão — mp4/webm/mov/mkv/avi), pergunta opcional, `max_tokens`
  (256–4096, omissão 2048). Em modelos de raciocínio é enviado
  `reasoning_budget` (4096) para o raciocínio não consumir a resposta; o
  `reasoning_content` é descartado — só a resposta final regressa.
  Nota: o download de mídia é feito pelo proxy da NVIDIA — URLs de alguns
  hosts (ex.: Wikimedia) podem ser recusadas a montante (422).
- **Credenciais encriptadas na base de dados** (`dashboard/ai_credentials.py`,
  modelo `AiCredential`): cada slot (`text` / `vision` / `image`) guarda a
  chave cifrada com **Fernet** (prefixo `enc:v1:`, derivação
  `sha256(AUDIT_DJANGO_SECRET_KEY)`), mais modelo e base_url personalizáveis —
  **sem reiniciar o serviço**. Resolução: BD → env → constantes de módulo.
  - `GET /ai/nim/credentials` (viewer+): resumo **mascarado** (`nvapi-…XXXX`) —
    a chave completa nunca sai do servidor.
  - `POST /ai/nim/credentials` (auditor/admin): grava/limpa por slot
    (`{"image_key": "nvapi-…", "image_model": "…"}`; `""` limpa → fallback env).
  - Secção “Credenciais NVIDIA NIM (BD)” no modal AI Control Plane
    (Configurações) com badges BD/Ambiente.
  - Seed: `python manage.py seed_nim_credentials` (env → BD encriptada;
    `--clear` limpa a BD).
- `GET /ai/nim/status` (viewer+): estado dos 3 slots + motores (fonte da
  credencial, modelo, disponibilidade).

### Banco de Imagens — busca real estilo Freepik dentro da plataforma (novo)

Cartão **“NIM Studio”** (Integrações) tem agora a secção **Banco de Imagens**:
busca real em catálogos públicos, guarda no servidor e reutilização em
relatórios — sem depender de hotspots de terceiros.

- **Provedores** (`dashboard/imagebank.py`, todos normalizados para o mesmo
  formato `title/author/license/url/thumb`):
  | Provedor | Chave | Conteúdo |
  |---|---|---|
  | **Met Museum** (default) | sem chave | obras Open Access **CC0** — API v1.1 (Elastic), paginada |
  | **Openverse** (WordPress) | sem chave | milhões de imagens CC (Flickr, etc.) |
  | **Wikimedia Commons** | sem chave | licenças livres (busca `filetype:bitmap`) |
  | **Pexels / Unsplash / Pixabay / Freepik** | chave própria (BD ou env) | bancos comerciais estilo Freepik |
- **Chaves dos bancos**: slots `pexels` / `unsplash` / `pixabay` / `freepik`
  do `AiCredential` (mesma cifragem Fernet na BD) — secção
  “Chaves dos bancos de imagens (opcional)” no AI Control Plane, ou env
  `AUDIT_PEXELS_API_KEY` / `AUDIT_UNSPLASH_API_KEY` / `AUDIT_PIXABAY_API_KEY` /
  `AUDIT_FREEPIK_API_KEY`. Provedores sem chave exigem nada — funcionam já.
- **Endpoints**: `GET /ai/bank/providers` (estado das chaves),
  `GET /ai/bank/search?q=&provider=&page=&page_size=` (busca, viewer+),
  `POST /ai/bank/save` (descarga com validação magic-bytes, teto 25 MB,
  deduplicação por `(provider, image_id)`, thumb opcional — viewer+),
  `GET /ai/bank/images` (galeria), `GET /ai/bank/images/<id>/file?full=1`
  (thumb por omissão, original com `full=1`), `DELETE /ai/bank/images/<id>`
  (auditor+).
- **Capa de relatórios**: `GET /reports/audit/pdf?cover=<id>` aceita tanto
  imagens FLUX da galeria NIM como imagens guardadas do banco (`StockImage`)
  — úteis com licenças CC0 para documentação formal.
- Notas: hosts de imagem de alguns provedores bloqueiam IPs de datacenter
  (Wikimedia/Openverse podem responder 403/429 de sandboxes partilhadas —
  a plataforma devolve mensagem clara; do teu IP real funcionam). O Met
  Museum (CC0) é o provedor por omissão por ser estável e sem restrições.

### Segurança de chaves

As chaves (`AUDIT_NVIDIA_API_KEY`, `AUDIT_LLM_API_KEY`, …) vivem apenas em
variáveis de ambiente / `.env` (ignorado pelo git) — **nunca** em ficheiros
versionados. `.env.example` traz os placeholders. Como alternativa (e de
forma preferencial), as chaves de IA podem ficar **encriptadas na BD**
(seção acima) — cifradas com Fernet, nunca devolvidas em texto claro por
nenhum endpoint.

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
| `AUDIT_PEXELS_API_KEY` / `AUDIT_UNSPLASH_API_KEY` / `AUDIT_PIXABAY_API_KEY` / `AUDIT_FREEPIK_API_KEY` | — | Chaves dos bancos de imagens (opcional — também na BD via AI Control Plane) |
| `AUDIT_CORS_ORIGINS` | `localhost:3000` | Origens CORS (CSV) |
| `AUDIT_EMAIL_BACKEND` | console | SMTP real: `…smtp.EmailBackend` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` | — | Credenciais SMTP |
| `AUDIT_DIGEST_EMAILS` | — | Destinatários do digest (CSV) |
| `AUDIT_DIGEST_ENABLED` | `False` | Agenda via celery beat |
| `AUDIT_DIGEST_HOUR` | `7` | Hora do digest diário |
| `AUDIT_LLM_API_STYLE` | `openai-compatible` no Compose | Protocolo `openai-compatible` (EXAONE/llama.cpp ou Groq) ou `ollama` |
| `AUDIT_LLM_BASE_URL` | `http://exaone:8080/v1` no Compose | URL base; Groq usa `https://api.groq.com/openai/v1` |
| `AUDIT_OLLAMA_MODEL` | `exaone4.0-1.2b` no Compose | Alias ou ID do modelo (Groq: `llama-3.3-70b-versatile`) |
| `GROQ_API_KEY` / `AUDIT_LLM_API_KEY` | — | Chave Groq; mantenha apenas no `.env` local, nunca no Git |
| `AUDIT_OLLAMA_TIMEOUT` | `25` | Timeout do LLM (s) |
| `AUDIT_OLLAMA_PROBE_TTL` | `60` | Cooldown da sonda de disponibilidade; o copiloto degrada para regras quando o modelo está indisponível |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` | Base da API para o proxy do Next |

Lista completa e infra self-hosted: [README_INFRA.md](README_INFRA.md) e
[.env.example](.env.example).

### Base de dados real (PostgreSQL) — produção e dev

A plataforma suporta **PostgreSQL real** via `AUDIT_DATABASE_URL` (parse
urllib: TCP, socket unix, `sslmode` para cloud, passwords url-encoded):

```bash
# Cloud (Supabase / Neon / RDS — free tiers disponíveis):
AUDIT_DATABASE_URL="postgresql://user:pass@db.xxx.supabase.co:5432/postgres?sslmode=require" \
  python manage.py migrate && python manage.py runserver

# Local com PostgreSQL embutido (pgserver, sem instalar nada):
/home/z/.venv/bin/python scripts/start_postgres.py   # imprime a URL na última linha
```

O launcher `scripts/start_audit_stack.sh` **arranca automaticamente um
PostgreSQL 16 embutido** (data-dir persistente `audit-pg/`, via `pgserver`)
quando `AUDIT_DATABASE_URL` não está definida — o SQLite só é usado como
última alternativa. Migrações, testes (458) e credenciais Fernet correm
no mesmo motor em dev e produção.

### Backup real do PostgreSQL (com verificação de restauro)

Três formas equivalentes (mesmo núcleo `dashboard/pg_backup.py`):

```bash
# 1. Comando de gestão (usa AUDIT_DATABASE_URL do launcher):
python manage.py backup_database          # --no-verify / --keep 5 / --dir X

# 2. CLI standalone (arranca o PostgreSQL se preciso):
/home/z/.venv/bin/python scripts/backup_postgres.py

# 3. Automático — celery beat diário às 03:00 (AUDIT_BACKUP_ENABLED, default
#    true; hora com AUDIT_BACKUP_HOUR) via dashboard.tasks.backup_database_task
```

Cada backup: dump custom `-Fc` + `pg_restore --list` (catálogo legível) +
**restauro VERIFICADO numa base temporária** (47 tabelas; só para o
PostgreSQL local do pgserver — com `AUDIT_DATABASE_URL` externa Supabase/
Neon salta-se para não criar bases na cloud) + retenção dos 10 mais
recentes. Destino: `AUDIT_BACKUP_DIR` ou `<BASE_DIR>/backups` (gitignored).

### Copiloto com busca de imagens agéntica (Banco de Imagens)

Perguntar «mostra imagens de escritório financeiro» ativa a tool
`images`: o copiloto busca em openverse → met (sem chave, com fallback
corporativo EN quando o termo PT não tem resultados), devolve até 3
miniaturas com título/autor/licença numa grelha clicável (URL original)
e sugere guardá-las no NIM Studio para reuso em relatórios. Falha dos
provedores degrada para mensagem amigável — o chat nunca quebra.

### Capa IA do Relatório Global — funciona sem chave FLUX

O botão "Capa IA" usa o FLUX (768×512) quando o slot `image` tem chave;
**sem chave (ou falha upstream) cai automaticamente ao Banco de Imagens** —
busca real (Met/Openverse), guarda na galeria com dedupe (`query=
'capa-relatório'`) e devolve `source='bank'`. O PDF aceita capas de
qualquer origem (`?cover=<NimImage|StockImage id>`).

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

# Motores de IA (LLM + NIM Studio)
GET  /django/api/ai/llm/status              → cadeia de motores ao vivo
POST /django/api/ai/llm/test               → ping real (auditor/admin)
POST /django/api/bi/narrate                → narração executiva do Painel Auto
GET  /django/api/ai/nim/credentials        → credenciais IA na BD (mascaradas)
POST /django/api/ai/nim/credentials        → grava/limpa slot (auditor/admin)
GET  /django/api/ai/nim/status             → estado dos slots/motores NIM
POST /django/api/ai/nim/image              → gera imagem FLUX.2-klein-4B
GET  /django/api/ai/nim/images             → galeria (metadados)
GET  /django/api/ai/nim/images/<id>/file   → JPEG da galeria
POST /django/api/ai/nim/vision             → compreensão de imagem/vídeo (omni)
POST /django/api/reports/ai-cover          → capa IA (FLUX 768×512) p/ relatório
GET  /django/api/reports/audit/pdf?cover=  → PDF com capa (FLUX ou banco)

# Banco de Imagens (estilo Freepik, real)
GET  /django/api/ai/bank/providers         → provedores + estado das chaves
GET  /django/api/ai/bank/search            → busca (q, provider, page, page_size)
POST /django/api/ai/bank/save              → guarda imagem no servidor (viewer+)
GET  /django/api/ai/bank/images            → galeria guardada
GET  /django/api/ai/bank/images/<id>/file  → ficheiro (?full=1 = original)
DELETE /django/api/ai/bank/images/<id>     → remove (auditor/admin)
(POST /django/api/ai/copilot aceita image_url → visão omni no chat)
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
| NIM Studio | Imagens FLUX.2-klein-4B + galeria, visão omni (imagem/vídeo), credenciais IA encriptadas na BD |
