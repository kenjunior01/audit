"""Testes do backup PostgreSQL (dashboard.pg_backup) — Task 42.

Cobre: resolução da URI (env/pgserver), _with_db (dbname no path),
retenção de dumps, create_backup com subprocess em mock (pg_dump que
escreve o ficheiro, pg_restore --list com catálogo), falhas fatais
(dump ilegível, pg_dump erro) e verificação de restauro (pgserver +
psycopg em mock). Nenhum teste toca numa base de dados real.
"""
import os
import tempfile
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from dashboard import pg_backup


def _catalog_lines(n):
    """Linhas de catálogo do pg_restore --list (tabelas/dados/índices)."""
    out = [";", "140; 1259 16456 TABLE audit dashboard_transaction postgres"]
    for i in range(n):
        out.append(f"{16500 + i}; 1259 {16460 + i} TABLE audit t{i} postgres")
    return "\n".join(out) + "\n"


class WithDbTest(SimpleTestCase):
    def test_appends_db_when_path_empty(self):
        uri = "postgresql://user:pw@localhost:5432"
        self.assertEqual(pg_backup._with_db(uri),
                         "postgresql://user:pw@localhost:5432/audit")

    def test_keeps_existing_db(self):
        uri = "postgresql://u@/audit?host=/x"
        self.assertEqual(pg_backup._with_db(uri), uri)

    def test_socket_uri_keeps_db(self):
        uri = "postgresql://postgres:pw@/audit?host=/home/x/audit-pg"
        self.assertEqual(pg_backup._with_db(uri), uri)


class ResolveUriTest(SimpleTestCase):
    def test_env_wins(self):
        with patch.dict(os.environ, {"AUDIT_DATABASE_URL": "postgresql://x/y"}):
            uri, source = pg_backup.resolve_uri(pgdata="/nonexistent-pg")
        self.assertEqual(source, "env")
        self.assertEqual(uri, "postgresql://x/y")

    def test_none_when_nothing(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("AUDIT_DATABASE_URL", "AUDIT_PGDATA")}
        with patch.dict(os.environ, env, clear=True), \
             patch("pgserver.get_server", side_effect=ImportError("no pg")):
            uri, source = pg_backup.resolve_uri(pgdata="/tmp/t42-missing-pg")
        self.assertIsNone(uri)
        self.assertIsNone(source)


class PruneTest(SimpleTestCase):
    def test_keeps_newest_n(self):
        d = tempfile.mkdtemp()
        for name in ("audit-20260101-000001.dump", "audit-20260102-000001.dump",
                     "audit-20260103-000001.dump", "other.dump"):
            open(os.path.join(d, name), "w").close()
        removed = pg_backup.prune(d, keep=2)
        self.assertEqual(removed, ["audit-20260101-000001.dump"])
        left = sorted(os.listdir(d))
        self.assertEqual(left, ["audit-20260102-000001.dump",
                                "audit-20260103-000001.dump", "other.dump"])


class CreateBackupTest(SimpleTestCase):
    def _run_backup(self, side_effect, **kw):
        d = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items()
               if k != "AUDIT_DATABASE_URL"}
        with patch.dict(os.environ, env, clear=True), \
             patch("dashboard.pg_backup.subprocess.run",
                   side_effect=side_effect) as run:
            res = pg_backup.create_backup(
                uri="postgresql://u@/audit?host=/x", backup_dir=d, **kw)
        return res, run, d

    def _happy_side_effect(self, args, **kw):
        if "--list" in args:
            r = Mock()
            r.stdout = _catalog_lines(60)
            r.stderr = ""
            r.returncode = 0
            return r
        for a in args:
            if a.startswith("--file="):
                open(a[7:], "wb").write(b"PGDMP" * 100)
        r = Mock()
        r.returncode = 0
        r.stderr = ""
        return r

    def test_happy_path_remote_skips_restore_verify(self):
        res, run, d = self._run_backup(self._happy_side_effect)
        self.assertEqual(res["source"], "explicit")
        self.assertTrue(res["dump"].endswith(".dump"))
        self.assertGreater(res["size_kb"], 0)
        self.assertGreaterEqual(res["items"], pg_backup.MIN_ITEMS)
        self.assertFalse(res["verified"])
        self.assertIn("BD remota", res.get("note", ""))
        self.assertEqual(res["pruned"], [])
        # duas chamadas subprocess: pg_dump + pg_restore --list
        self.assertEqual(run.call_count, 2)

    def test_pg_dump_failure_raises(self):
        def boom(args, **kw):
            r = Mock()
            r.returncode = 1
            r.stderr = "connection refused"
            return r
        with self.assertRaises(pg_backup.BackupError) as ctx:
            self._run_backup(boom)
        self.assertIn("pg_dump falhou", str(ctx.exception))

    def test_illegible_dump_raises(self):
        def tiny_catalog(args, **kw):
            if "--list" in args:
                r = Mock()
                r.stdout = _catalog_lines(3)
                r.stderr = ""
                r.returncode = 0
                return r
            return self._happy_side_effect(args, **kw)
        with self.assertRaises(pg_backup.BackupError) as ctx:
            self._run_backup(tiny_catalog)
        self.assertIn("ilegível", str(ctx.exception))

    def test_retention_prunes_old_dumps(self):
        d = tempfile.mkdtemp()
        for name in ("audit-20251231-235959.dump",):
            open(os.path.join(d, name), "w").close()
        env = {k: v for k, v in os.environ.items()
               if k != "AUDIT_DATABASE_URL"}
        with patch.dict(os.environ, env, clear=True), \
             patch("dashboard.pg_backup.subprocess.run",
                   side_effect=self._happy_side_effect):
            res = pg_backup.create_backup(
                uri="postgresql://u@/audit?host=/x", backup_dir=d, keep=1)
        self.assertEqual(res["pruned"], ["audit-20251231-235959.dump"])
        self.assertEqual(len(os.listdir(d)), 1)


class RestoreVerifyTest(SimpleTestCase):
    def test_restore_verified_counts_tables(self):
        dump = "/tmp/fake.dump"
        db = Mock()
        db.psql = Mock()
        db.get_uri = Mock(return_value="postgresql://pgserver/audit")
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (47,)
        with patch("pgserver.get_server", return_value=db), \
             patch("psycopg.connect", return_value=conn):
            n = pg_backup._restore_verify(dump, "/tmp/audit-pg")
        self.assertEqual(n, 47)
        db.psql.assert_any_call("DROP DATABASE IF EXISTS audit_restore_test")
        db.psql.assert_any_call("CREATE DATABASE audit_restore_test")

    def test_incomplete_restore_raises_and_cleans(self):
        dump = "/tmp/fake.dump"
        db = Mock()
        db.psql = Mock()
        db.get_uri = Mock(return_value="postgresql://pgserver/audit")
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (3,)
        with patch("pgserver.get_server", return_value=db), \
             patch("psycopg.connect", return_value=conn):
            with self.assertRaises(pg_backup.BackupError) as ctx:
                pg_backup._restore_verify(dump, "/tmp/audit-pg")
        self.assertIn("incompleto", str(ctx.exception))
        # psql: DROP/CREATE/DROP da base temporária (o probe psycopg da
        # _start_pgserver não usa psql) = 3 chamadas
        self.assertEqual(db.psql.call_count, 3)
