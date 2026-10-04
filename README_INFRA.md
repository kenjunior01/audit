# Audit Platform - Self-Hosted Infrastructure

This setup allows the Audit Platform to run completely offline/self-hosted using open-source components, avoiding API costs and ensuring data privacy.

## Prerequisites
- Docker & Docker Compose
- NVIDIA GPU (Recommended for Ollama) with NVIDIA Container Toolkit

## Components

1.  **Ollama (AI Inference):**
    - Runs the LLM (DeepSeek-R1-Distill-Llama-8B).
    - Port: 11434
    - Setup: After starting, pull the model:
      ```bash
      docker exec -it audit_ollama ollama run deepseek-r1:8b
      ```

2.  **Qdrant (Vector DB):**
    - Stores document embeddings for the "Corporate Brain" (RAG).
    - Port: 6333

3.  **Redis:**
    - Handles background tasks (Email sending, Hyperautomation queues).
    - Port: 6379

## How to Run

O `docker-compose.yml` atual cobre a **stack completa** com perfis:
núcleo (postgres + redis + API Django + dashboard Next.js), `worker`
(celery: digest/emails) e `ai` (Ollama + Qdrant).

1.  Start the core stack (API :8000 + web :3000):
    ```bash
    docker compose up -d --build
    ```

2.  Add the AI infrastructure (Ollama + Qdrant):
    ```bash
    docker compose --profile ai up -d
    docker compose exec ollama ollama pull deepseek-r1:8b
    ```

3.  Add the Celery worker (scheduled digest, emails, agents):
    ```bash
    docker compose --profile worker up -d
    ```

4.  Configure Django to use these services (ver `.env.example`):
    - Set `OLLAMA_URL=http://localhost:11434` (já definido no compose)
    - Set `QDRANT_URL=http://localhost:6333`
    - Set `REDIS_URL=redis://localhost:6379/0`
    - Para email real: `AUDIT_EMAIL_BACKEND=…smtp.EmailBackend` + `EMAIL_HOST`…

> Documentação geral da plataforma: [README.md](README.md).

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

