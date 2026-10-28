# Audit Platform - Self-Hosted Infrastructure

This setup allows the Audit Platform to run completely offline/self-hosted using open-source components, avoiding API costs and ensuring data privacy.

## Prerequisites
- Docker & Docker Compose
- Internet access on first AI startup to download the EXAONE GGUF model

## Components

1.  **EXAONE 4.0 1.2B via llama.cpp (AI inference):**
    - Uses the official Q4_K_M GGUF release and llama.cpp's OpenAI-compatible API.
    - Port: 8080 (bound to localhost).
    - The first `ai` profile startup downloads and caches the model in the `exaone_data` volume.
    - CPU inference is supported; a compatible GPU can be configured separately.

2.  **Qdrant (Vector DB):**
    - Stores document embeddings for the "Corporate Brain" (RAG).
    - Port: 6333 (bound to localhost)

3.  **PostgreSQL:**
    - Primary persistent database for all application records.
    - Port: 5432 (bound to localhost); Django migrations run at backend startup.

4.  **Redis:**
    - Handles background tasks (Email sending, Hyperautomation queues).
    - Port: 6379 (bound to localhost)

## How to Run

O `docker-compose.yml` atual cobre a **stack completa** com perfis:
núcleo (postgres + redis + API Django + dashboard Next.js), `worker`
(Celery worker + Beat: digest/alertas) e `ai` (EXAONE/llama.cpp + Qdrant).

1.  Start the core stack (API :8000 + web :3000):
    ```bash
    docker compose up -d --build
    ```

2.  Add the AI infrastructure (EXAONE + Qdrant):
    ```bash
    docker compose --profile ai up -d --build
    ```
    The model is downloaded automatically; wait for `audit_exaone` to become healthy.

3.  Add the Celery worker and scheduler (scheduled digest, alerts, emails, agents):
    ```bash
    docker compose --profile worker up -d
    ```

4.  Configure Django to use these services (ver `.env.example`):
    - Docker Compose liga o backend ao servidor local EXAONE e ao Qdrant.
    - As portas de Postgres, Redis, EXAONE e Qdrant só são publicadas em `127.0.0.1`.
    - Set `REDIS_URL=redis://localhost:6379/0`
    - Para email real: `AUDIT_EMAIL_BACKEND=…smtp.EmailBackend` + `EMAIL_HOST`…

### Linux Docker bridge workaround

The standard Compose setup above is the portable default. On Linux hosts where
containers cannot communicate over their Docker bridge, an optional override
uses host networking for the application services while PostgreSQL and Redis
remain isolated and published only on localhost:

```bash
docker compose -f docker-compose.yml -f docker-compose.host-network.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.host-network.yml --profile ai up -d
docker compose -f docker-compose.yml -f docker-compose.host-network.yml --profile worker up -d
```

This override is Linux-specific; do not use it with Docker Desktop on macOS or
Windows. llama.cpp and Qdrant bind to localhost in this mode. The normal
bridge-network commands remain recommended on hosts where container networking
works.

> Documentação geral da plataforma: [README.md](README.md).

## Public APIs without API keys

The backend exposes a curated selection of no-key public providers used by the
platform. They are independent services, so their coverage, availability, rate
limits and terms remain provider-controlled:

| Endpoint | Data source |
|---|---|
| `GET /django/api/integrations/public` | Provider directory and official legal-source links |
| `GET /django/api/integrations/public/currencies?base=EUR&symbols=USD,BRL` | Frankfurter / ECB exchange rates |
| `GET /django/api/integrations/public/countries?q=Portugal` | REST Countries (CountriesNow fallback) |
| `GET /django/api/integrations/public/weather?location=Lisbon` | Open-Meteo geocoding and forecast |
| `GET /django/api/integrations/public/news?q=company` | GDELT (Google News RSS fallback) |
| `GET /django/api/integrations/public/companies/br?cnpj=...` | BrasilAPI CNPJ lookup |

These endpoints require an authenticated viewer token. None of the providers
requires an API key for the documented requests. The integration directory is
not an exhaustive mirror of the public-apis catalog: that catalog contains
unrelated services with different terms, credentials and data policies.
Search terms and lookup identifiers are sent to the selected provider; do not
send confidential or personal information.

## Account registration

`POST /django/api/auth/register` creates the Django user, viewer API token and
organization context in one database transaction. Required JSON fields:
`name`, `email`, `password`, `company_name`; `sector` is optional. Email
addresses are normalized, duplicates are rejected, and Django's configured
password validators apply. `POST /django/api/auth/login` issues the existing
account token.

## DPO Feedback Loop (Self-Improving AI)

1. **Export Data:**
   Export auditor corrections to a training dataset:
   ```bash
   python django_app/manage.py export_dpo_dataset --output training_data.jsonl
   ```

2. **Fine-Tune (Unsloth):**
   Run the training script (requires GPU):
   ```bash
   python django_app/train_dpo_unsloth.py
   ```
   This will save the new model adapters to `fine_tuned_model/`.
