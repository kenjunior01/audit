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

1.  Start the infrastructure:
    ```bash
    docker-compose up -d
    ```

2.  Run the Celery Worker (for background tasks):
    ```bash
    cd django_app
    celery -A auditportal worker --loglevel=info
    ```

3.  Configure Django to use these services:
    - Set `OLLAMA_URL=http://localhost:11434`
    - Set `QDRANT_URL=http://localhost:6333`
    - Set `REDIS_URL=redis://localhost:6379/0`

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

