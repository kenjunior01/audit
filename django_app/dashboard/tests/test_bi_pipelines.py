"""Testes dos Pipelines ETL (Power Query parity) e do endpoint de execução."""
import io
import uuid

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from dashboard.etl_service import apply_pipeline
from dashboard.models import ApiToken, ETLPipeline, Transaction


def make_xlsx(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Dados")
    return buf.getvalue()


class ApplyPipelineTest(TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {"Fornecedor": "  Alfa ", "Valor da Nota": 1000, "Data": "2026-01-05", "Status": "OK"},
            {"Fornecedor": "Alfa", "Valor da Nota": 1000, "Data": "2026-01-05", "Status": "OK"},
            {"Fornecedor": "Beta", "Valor da Nota": None, "Data": None, "Status": "OK"},
        ])

    def test_map_columns_fuzzy(self):
        out, log, ok = apply_pipeline(self.df, [{"op": "map_columns"}])
        self.assertIn("vendor", out.columns)
        self.assertIn("amount", out.columns)
        self.assertEqual(ok, 1)

    def test_filter_dedupe_fillna_chain(self):
        steps = [
            {"op": "trim_text", "fields": ["Fornecedor"]},   # antes do map: cabeçalho original
            {"op": "map_columns"},
            {"op": "fillna", "field": "amount", "strategy": "zero"},
            {"op": "dedupe", "subset": ["vendor", "amount"]},
            {"op": "filter", "field": "amount", "cmp": "gt", "value": 0},
        ]
        out, log, ok = apply_pipeline(self.df, steps)
        self.assertEqual(ok, 5)
        self.assertEqual(len(out), 1)          # trim junta as 2 Alfa; Beta 0 filtrado
        self.assertEqual(out.iloc[0]["vendor"], "Alfa")

    def test_derive_variants(self):
        steps = [
            {"op": "map_columns"},
            {"op": "derive", "target": "mes", "kind": "month", "field": "timestamp"},
            {"op": "derive", "target": "pct", "kind": "pct_of_total", "field": "amount"},
            {"op": "derive", "target": "acum", "kind": "running_total", "field": "amount"},
            {"op": "derive", "target": "faixa", "kind": "bucket", "field": "amount",
             "value": [0, 500, 5000], "labels": ["Pequeno", "Médio", "Grande"]},
        ]
        out, log, ok = apply_pipeline(self.df, steps)
        self.assertEqual(ok, 5)
        self.assertIn("mes", out.columns)
        self.assertIn("faixa", out.columns)

    def test_invalid_step_logged_not_fatal(self):
        out, log, ok = apply_pipeline(self.df, [
            {"op": "inexistente"}, {"op": "map_columns"}])
        self.assertEqual(ok, 1)
        self.assertTrue(any("ignorado" in l["note"] for l in log))

    def test_max_steps_guard(self):
        steps = [{"op": "trim_text"}] * 120
        out, log, ok = apply_pipeline(self.df, steps)
        self.assertLessEqual(len(log), 50)


class PipelineEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.t = str(uuid.uuid4())
        ApiToken.objects.create(token=self.t, user_id="admin@x.pt", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.t)
        self.pipe = ETLPipeline.objects.create(
            name="Limpeza Padrão", steps=[
                {"op": "map_columns"},
                {"op": "fillna", "field": "amount", "strategy": "zero"},
            ], created_by="admin@x.pt")
        self.df = pd.DataFrame([
            {"Fornecedor": "Alfa", "Valor da Nota": 1000,
             "Data": "2026-01-05", "Status": "Completed",
             "ID Transação": "PX-1", "Usuário": "admin@x.pt"},
            {"Fornecedor": "Beta", "Valor da Nota": 50,
             "Data": "2026-01-06", "Status": "Completed",
             "ID Transação": "PX-2", "Usuário": "admin@x.pt"},
        ])

    def _upload(self):
        return {"file": SimpleUploadedFile(
            "dados.xlsx", make_xlsx(self.df),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    def test_run_without_import(self):
        r = self.client.post(f"/django/api/bi/pipelines/{self.pipe.pk}/run",
                             self._upload(), format="multipart")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["steps_ok"], 2)
        self.assertEqual(r.data["rows_out"], 2)
        self.assertEqual(r.data["imported"], 0)
        self.pipe.refresh_from_db()
        self.assertEqual(self.pipe.run_count, 1)

    def test_run_with_import_creates_transactions(self):
        before = Transaction.objects.count()
        r = self.client.post(f"/django/api/bi/pipelines/{self.pipe.pk}/run?import=true",
                             self._upload(), format="multipart")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["imported"], 2)
        self.assertEqual(Transaction.objects.count(), before + 2)
        # idempotência por transaction_id
        r = self.client.post(f"/django/api/bi/pipelines/{self.pipe.pk}/run?import=true",
                             self._upload(), format="multipart")
        self.assertEqual(r.data["imported"], 0)

    def test_requires_file(self):
        r = self.client.post(f"/django/api/bi/pipelines/{self.pipe.pk}/run")
        self.assertEqual(r.status_code, 400)

    def test_pipeline_crud_and_auth(self):
        r = self.client.get("/django/api/bi/pipelines")
        self.assertEqual(r.data["count"], 1)
        r = self.client.post("/django/api/bi/pipelines",
                             {"name": "Segundo", "steps": [{"op": "upper_headers"}]},
                             format="json")
        self.assertEqual(r.status_code, 201)
        # viewer não acede
        tv = str(uuid.uuid4())
        from dashboard.models import ApiToken as T
        T.objects.create(token=tv, user_id="v@x.pt", role="viewer")
        c2 = APIClient(); c2.credentials(HTTP_AUTHORIZATION="Bearer " + tv)
        r = c2.get("/django/api/bi/pipelines")
        self.assertEqual(r.status_code, 403)
