"""Backup real do PostgreSQL da plataforma (dump + verificação de restauro).

Uso:
    python manage.py backup_database               # dump + verify + retenção
    python manage.py backup_database --no-verify   # só dump (rápido)
    python manage.py backup_database --dir /tmp/bk --keep 5

Origem da ligação: AUDIT_DATABASE_URL (env/launcher) ou PostgreSQL embutido
pgserver em AUDIT_PGDATA (ou /home/z/my-project/audit-pg). O restauro de
verificação só corre em BD local — em Supabase/Neon salta automaticamente.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dashboard import pg_backup


class Command(BaseCommand):
    help = ("Backup real do PostgreSQL: dump custom -Fc + pg_restore --list "
            "+ restauro verificado numa base temporária + retenção")

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int,
                            default=pg_backup.DEFAULT_KEEP,
                            help="nº de dumps a manter (default 10)")
        parser.add_argument("--no-verify", action="store_true",
                            help="salta o restauro de verificação")
        parser.add_argument("--dir", default="",
                            help="directório de destino (default: "
                                 "AUDIT_BACKUP_DIR ou <BASE_DIR>/backups)")
        parser.add_argument("--pgdata", default="",
                            help="data-dir pgserver (default: AUDIT_PGDATA)")

    def handle(self, *args, **opts):
        backup_dir = (opts["dir"] or os.environ.get("AUDIT_BACKUP_DIR")
                      or os.path.join(settings.BASE_DIR, "backups"))
        pgdata = opts["pgdata"] or os.environ.get("AUDIT_PGDATA") or None
        try:
            res = pg_backup.create_backup(
                backup_dir=backup_dir, keep=opts["keep"],
                verify=not opts["no_verify"], pgdata=pgdata)
        except pg_backup.BackupError as e:
            raise CommandError(f"backup falhou: {e}")
        self.stdout.write(self.style.SUCCESS(
            json.dumps(res, ensure_ascii=False, indent=2)))
        self.stdout.write(self.style.SUCCESS("BACKUP_OK"))
