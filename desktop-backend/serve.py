"""
Entry point da aplicação desktop (empacotada com PyInstaller).

Responsabilidades:
1. Resolver a pasta de dados do utilizador (AUDIT_DESKTOP_DATA_DIR ou
   ~/.auditai) e aí guardar: base SQLite, chave secreta persistente, logs.
2. Configurar as envs do Django ANTES do setup (DB, hosts, debug off,
   digest por email desligado — o desktop usa a app, não cron).
3. Correr migrações + seed_demo (idempotente) na primeira execução.
4. Servir o WSGI com waitress (servidor puro Python, Windows-friendly,
   suporta streaming SSE do copiloto) em 127.0.0.1:<AUDIT_PORT>.

O Electron arranca este executável e espera pelo marcador "AUDIT_BACKEND_READY".
"""
import os
import sys
import secrets
from pathlib import Path


def _prepare_environment() -> None:
    data_dir = Path(os.environ.get("AUDIT_DESKTOP_DATA_DIR")
                    or (Path.home() / ".auditai"))
    data_dir.mkdir(parents=True, exist_ok=True)

    # chave secreta persistente (gerada uma única vez por instalação)
    key_file = data_dir / "secret_key.txt"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(64), encoding="utf-8")

    db_path = data_dir / "audit.db"

    os.environ.setdefault("AUDIT_DESKTOP", "1")
    os.environ.setdefault("AUDIT_DB_NAME", str(db_path))
    os.environ.setdefault("AUDIT_DJANGO_SECRET_KEY", key_file.read_text("utf-8"))
    os.environ.setdefault("AUDIT_DEBUG", "False")
    os.environ.setdefault("AUDIT_ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("AUDIT_CORS_ALLOW_ALL", "False")
    os.environ.setdefault("AUDIT_CORS_ORIGINS", "http://127.0.0.1:3000")
    os.environ.setdefault("AUDIT_DIGEST_ENABLED", "False")
    os.environ.setdefault("AUDIT_THROTTLE_ANON", "240/min")
    os.environ.setdefault("AUDIT_THROTTLE_USER", "2400/min")
    # desktop: sem redis/celery externos — tarefas correm inline (eager)
    os.environ.setdefault("CELERY_BROKER_URL", "memory://")
    os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

    # django_app no path (útil em dev; no PyInstaller já está bundled)
    here = Path(__file__).resolve().parent
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(here.parent / "django_app"))


def _django_setup() -> None:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auditportal.settings")
    django.setup()


def _migrate_and_seed() -> None:
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    call_command("seed_demo", verbosity=0)


def main() -> None:
    _prepare_environment()
    _django_setup()

    from django.core.wsgi import get_wsgi_application
    app = get_wsgi_application()

    # migrações e dados demo ANTES de aceitar ligações
    _migrate_and_seed()

    port = int(os.environ.get("AUDIT_PORT", "8000"))
    host = "127.0.0.1"

    print(f"AUDIT_BACKEND_READY http://{host}:{port}", flush=True)

    from waitress import serve
    serve(app, host=host, port=port, threads=12,
          channel_timeout=300, connection_limit=200,
          ident="AuditAI-Desktop")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # erro visível no log do Electron
        import traceback
        traceback.print_exc()
        print(f"AUDIT_BACKEND_ERROR {exc}", flush=True)
        sys.exit(1)
