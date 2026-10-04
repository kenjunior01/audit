#!/usr/bin/env bash
# Entrypoint do backend: espera pela BD, aplica migrações e arranca gunicorn.
set -euo pipefail

PY=python

echo "[entrypoint] à espera da base de dados…"
ATTEMPTS=0
until $PY -c "
import os, sys
try:
    import django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','auditportal.settings'); django.setup()
    from django.db import connection; connection.ensure_connection()
    print('db ok')
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  ATTEMPTS=$((ATTEMPTS+1))
  if [ "$ATTEMPTS" -ge 30 ]; then
    echo "[entrypoint] BD não respondeu após 30 tentativas — a continuar mesmo assim."
    break
  fi
  sleep 2
done

echo "[entrypoint] migrate…"
$PY manage.py migrate --noinput

echo "[entrypoint] gunicorn :8000"
exec $PY -m gunicorn auditportal.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - --error-logfile -
