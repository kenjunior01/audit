"""Backup e verificação de restauro do PostgreSQL da plataforma AuditAI.

Core Django-independente — usado por:
- comando de gestão:  python manage.py backup_database
- task Celery/beat:   dashboard.tasks.backup_database_task
- CLI standalone:     scripts/backup_postgres.py (wrapper)

Estratégia (backup só conta se restaurar mesmo):
1. dump custom (-Fc) via pg_dump do pgserver (ou do PATH)
2. `pg_restore --list` → estrutura legível (mín. MIN_ITEMS entradas)
3. restauro VERIFICADO numa base temporária `audit_restore_test` (só para
   PostgreSQL local via pgserver — em BD remota Supabase/Neon salta-se,
   para não criar bases na instância de produção)
4. retenção: mantém os `keep` dumps mais recentes
"""
import glob
import os
import subprocess
import time
from urllib.parse import urlparse

DEFAULT_DB = "audit"
DEFAULT_KEEP = 10
DEFAULT_BACKUP_DIR = "/home/z/my-project/backups"
DEFAULT_PGDATA = "/home/z/my-project/audit-pg"
RESTORE_TEST_DB = "audit_restore_test"
MIN_ITEMS = 40   # entradas no catálogo do dump (tabelas+dados+índices)
MIN_TABLES = 40  # tabelas após restauro de verificação


class BackupError(RuntimeError):
    """Falha fatal de backup (dump ilegível, restauro incompleto, etc.)."""


def pg_bin(name):
    """Binário pg_dump/pg_restore do pgserver (auto-contido) ou do PATH."""
    try:
        import pgserver
        p = os.path.join(os.path.dirname(pgserver.__file__), "pginstall",
                         "bin", name)
        if os.path.exists(p):
            return p
    except ImportError:
        pass
    return name


def _start_pgserver(pgdata):
    """Arranca (idempotente) o PostgreSQL embutido e devolve (handle, uri).
    Cria a base 'audit' apenas se ainda não existe (sem ruído de stderr)."""
    import psycopg
    import pgserver
    os.makedirs(pgdata, exist_ok=True)
    db = pgserver.get_server(pgdata, cleanup_mode=None)
    uri = db.get_uri(DEFAULT_DB)
    try:
        conn = psycopg.connect(uri, connect_timeout=15)
        conn.close()  # base existe — nada a fazer
    except Exception:
        try:
            db.psql(f"CREATE DATABASE {DEFAULT_DB}")
        except Exception:
            pass  # corrida idempotente
    return db, uri


def resolve_uri(pgdata=None):
    """(uri, origem): AUDIT_DATABASE_URL → ('env'); pgserver em pgdata →
    ('pgserver'); nada configurado → (None, None). Nunca lança."""
    uri = os.environ.get("AUDIT_DATABASE_URL", "").strip()
    if uri:
        return uri, "env"
    pgdata = pgdata or os.environ.get("AUDIT_PGDATA", "") or DEFAULT_PGDATA
    try:
        _, uri = _start_pgserver(pgdata)
        return uri, "pgserver"
    except Exception:
        return None, None


def _with_db(uri, db=DEFAULT_DB):
    """pg_dump aceita UMA spec de ligação — se a URI não tem db no path,
    acrescenta-se; nunca passar dbname posicional junto da URI."""
    if not urlparse(uri).path.strip("/"):
        uri = uri.rstrip("/") + "/" + db
    return uri


def prune(backup_dir, keep=DEFAULT_KEEP, prefix="audit-"):
    """Apaga dumps antigos mantendo os `keep` mais recentes. Devolve a
    lista de nomes removidos."""
    olds = sorted(glob.glob(os.path.join(backup_dir, prefix + "*.dump")))
    removed = []
    for old in (olds[:-keep] if keep > 0 else olds):
        try:
            os.remove(old)
            removed.append(os.path.basename(old))
        except OSError:
            pass
    return removed


def _restore_verify(dump, pgdata):
    """Restaura o dump numa base temporária local e conta tabelas."""
    import psycopg
    db, uri = _start_pgserver(pgdata)
    try:
        db.psql(f"DROP DATABASE IF EXISTS {RESTORE_TEST_DB}")
        db.psql(f"CREATE DATABASE {RESTORE_TEST_DB}")
        rr = subprocess.run(
            [pg_bin("pg_restore"), "--no-owner", "--no-privileges",
             "-d", db.get_uri(RESTORE_TEST_DB), dump],
            capture_output=True, text=True, timeout=600)
        conn = psycopg.connect(db.get_uri(RESTORE_TEST_DB),
                               connect_timeout=15)
        n_tables = conn.execute(
            "select count(*) from information_schema.tables "
            "where table_schema='public'").fetchone()[0]
        conn.close()
        db.psql(f"DROP DATABASE IF EXISTS {RESTORE_TEST_DB}")
        if n_tables < MIN_TABLES:
            raise BackupError(
                f"restauro incompleto ({n_tables} tabelas) "
                + (rr.stderr or "")[-200:])
        return n_tables
    except BackupError:
        raise
    except Exception as e:
        try:
            db.psql(f"DROP DATABASE IF EXISTS {RESTORE_TEST_DB}")
        except Exception:
            pass
        raise BackupError(f"verificação de restauro falhou: {str(e)[:200]}")


def _is_local_pgserver(uri, pgdata=None):
    """True se a URI aponta para o PostgreSQL local do pgserver (socket
    unix dentro do data-dir) — só nesse caso a verificação de restauro
    é segura (a base temporária é criada na MESMA instância)."""
    from urllib.parse import urlparse, parse_qs
    try:
        host = (parse_qs(urlparse(uri).query).get("host") or [""])[0]
    except Exception:
        return False
    if not host.startswith("/"):  # TCP: localhost/remoto/ docker
        return False
    pgdata = os.path.abspath(pgdata or os.environ.get("AUDIT_PGDATA", "")
                             or DEFAULT_PGDATA)
    return os.path.abspath(host).startswith(pgdata.rstrip("/") + os.sep) \
        or os.path.abspath(host) == pgdata


def create_backup(uri=None, backup_dir=None, keep=DEFAULT_KEEP, verify=True,
                  pgdata=None):
    """Cria dump + verifica + aplica retenção. Devolve dict-resumo:
    {dump, basename, size_kb, items, source, verified, restored_tables,
     elapsed_s, pruned}. Lança BackupError em falha fatal.

    uri=None → resolve via resolve_uri(pgdata).
    verify=True → só verifica de facto quando a origem é local (pgserver).
    """
    t0 = time.time()
    if uri:
        source = "explicit"
    else:
        uri, source = resolve_uri(pgdata)
    if not uri:
        raise BackupError("Sem PostgreSQL: AUDIT_DATABASE_URL não definida "
                          "e pgserver indisponível.")
    local = (source == "pgserver") or _is_local_pgserver(uri, pgdata)
    uri = _with_db(uri)
    backup_dir = backup_dir or os.environ.get("AUDIT_BACKUP_DIR") \
        or DEFAULT_BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    dump = os.path.join(backup_dir, time.strftime("audit-%Y%m%d-%H%M%S.dump"))
    r = subprocess.run([pg_bin("pg_dump"), "--format=custom",
                        "--file=" + dump, uri],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise BackupError("pg_dump falhou: " + (r.stderr or "")[-300:])
    size_kb = round(os.path.getsize(dump) / 1024, 1)

    rl = subprocess.run([pg_bin("pg_restore"), "--list", dump],
                        capture_output=True, text=True, timeout=120)
    items = len([l for l in (rl.stdout or "").splitlines()
                 if l.strip() and not l.strip().startswith(";")])
    if rl.returncode != 0 or items < MIN_ITEMS:
        raise BackupError(f"dump ilegível (itens={items}) "
                          + (rl.stderr or "")[-200:])

    result = {"dump": dump, "basename": os.path.basename(dump),
              "size_kb": size_kb, "items": items, "source": source,
              "verified": False, "restored_tables": 0,
              "elapsed_s": round(time.time() - t0, 1), "pruned": []}
    if verify and local:
        result["restored_tables"] = _restore_verify(
            dump, pgdata or DEFAULT_PGDATA)
        result["verified"] = True
    elif verify and not local:
        result["note"] = "restauro local ignorado (BD remota)"
    result["pruned"] = prune(backup_dir, keep)
    return result
