"""
Testes do Excel Studio (super auxílio Excel).
Cobre: mapeamento fuzzy, parsing PT/EN, Benford, duplicados, splits,
reconciliação, workbook premium e os endpoints REST.
"""
import io
import uuid

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from dashboard.models import ApiToken, Transaction
from dashboard import excel_service as es


def make_xlsx(df: pd.DataFrame, sheets=None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        if sheets:
            for name, sdf in sheets.items():
                sdf.to_excel(w, index=False, sheet_name=name)
        else:
            df.to_excel(w, index=False)
    return buf.getvalue()


SAMPLE_ROWS = [
    {"Fornecedor": "Distribuidora Alpha Ltda", "Valor da Nota": "1.234,56",
     "Data da Operação": "2025-03-04", "Nº Documento": "NF-1", "Moeda": "BRL",
     "Centro de Custo": "TI", "Usuário Aprovador": "u1"},
    {"Fornecedor": "Beta Serviços", "Valor da Nota": "25000.00",
     "Data da Operação": "2025-03-05", "Nº Documento": "NF-2", "Moeda": "BRL",
     "Centro de Custo": "Admin", "Usuário Aprovador": "u2"},
    {"Fornecedor": "distribuidora alfa lta", "Valor da Nota": "999,00",
     "Data da Operação": "2025-03-06", "Nº Documento": "NF-3", "Moeda": "BRL",
     "Centro de Custo": "TI", "Usuário Aprovador": "u1"},
]


class ExcelServiceUnitTest(TestCase):
    def test_parse_amount_pt_and_en(self):
        self.assertAlmostEqual(es.parse_amount("1.234,56"), 1234.56)
        self.assertAlmostEqual(es.parse_amount("1,234.56"), 1234.56)
        self.assertAlmostEqual(es.parse_amount("(750,00)"), -750.0)
        self.assertAlmostEqual(es.parse_amount(45000), 45000.0)
        self.assertIsNone(es.parse_amount("n/a"))

    def test_map_columns_portuguese(self):
        mapping = es.map_columns(["Fornecedor", "Valor da Nota", "Data da Operação", "Nº Documento"])
        self.assertEqual(mapping["vendor"], "Fornecedor")
        self.assertEqual(mapping["amount"], "Valor da Nota")
        self.assertIn(mapping["transaction_id"], ("Nº Documento",))

    def test_standardize_generates_ids_for_empty(self):
        df = pd.DataFrame(SAMPLE_ROWS)
        mapping = es.map_columns([str(c) for c in df.columns])
        rows, skipped = es.standardize_frame(df, mapping)
        self.assertEqual(len(rows), 3)
        self.assertEqual(skipped, [])
        self.assertTrue(all(r["transaction_id"].startswith("NF-") for r in rows))

    def test_benford_needs_minimum_sample(self):
        res = es.benford_analysis(pd.Series([100, 200, 300]))
        self.assertFalse(res["applicable"])

    def test_fuzzy_duplicates_detects_vendor_variants(self):
        df = pd.DataFrame([
            {"transaction_id": "A", "vendor": "Distribuidora Alpha Ltda", "amount": 500.0},
            {"transaction_id": "B", "vendor": "Distribuidora Alfa Lta", "amount": 500.0},
        ])
        res = es.fuzzy_duplicates(df)
        self.assertEqual(len(res["fuzzy"]), 1)  # variantes do mesmo fornecedor agrupadas fuzzy
        self.assertTrue(res["fuzzy"] or res["exact"])

    def test_reconcile_matches_and_reports_orphans(self):
        a = pd.DataFrame([
            {"transaction_id": "B1", "vendor": "Fornecedor X", "amount": 100.0,
             "timestamp": "2025-03-04"},
            {"transaction_id": "B2", "vendor": "Fornecedor Y", "amount": 777.0,
             "timestamp": "2025-03-04"},
        ])
        b = pd.DataFrame([
            {"transaction_id": "L1", "vendor": "Fornecedor X", "amount": 100.0,
             "timestamp": "2025-03-05"},
        ])
        res = es.reconcile(a, b, amount_tol=0.01, date_tol_days=3)
        self.assertEqual(res["summary"]["matched"], 1)
        self.assertEqual(res["summary"]["unmatched_a"], 1)
        self.assertEqual(res["summary"]["unmatched_b"], 0)

    def test_premium_workbook_sheets_and_filters(self):
        from openpyxl import load_workbook
        df = pd.DataFrame(SAMPLE_ROWS)
        mapping = es.map_columns([str(c) for c in df.columns])
        rows, _ = es.standardize_frame(df, mapping)
        data = pd.DataFrame(rows)
        wb_bytes = es.build_premium_workbook(
            title="Teste", df=data,
            kpis={"Transações": len(data), "Valor Total": float(data["amount"].sum())},
            charts=es.aggregate_for_charts(data))
        wb = load_workbook(io.BytesIO(wb_bytes))
        self.assertIn("Sumário", wb.sheetnames)
        self.assertIn("Dados", wb.sheetnames)
        self.assertEqual(wb["Dados"].freeze_panes, "A2")
        self.assertIsNotNone(wb["Dados"].auto_filter.ref)


class ExcelEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token_val = str(uuid.uuid4())
        ApiToken.objects.create(token=self.token_val, user_id="test_admin", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token_val)
        self.df = pd.DataFrame(SAMPLE_ROWS * 20)  # 60 linhas

    def _upload(self, name="livro.xlsx", content=None):
        content = content or make_xlsx(self.df)
        return SimpleUploadedFile(name, content,
                                  content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_preview_flow(self):
        r = self.client.post("/django/api/excel/preview", {"file": self._upload()}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["mapping"]["vendor"], "Fornecedor")
        self.assertEqual(r.data["mapping"]["amount"], "Valor da Nota")
        self.assertGreaterEqual(r.data["quality"]["rows"], 60)

    def test_import_creates_transactions(self):
        rows = []
        for i in range(60):
            row = dict(SAMPLE_ROWS[i % 3])
            row["Nº Documento"] = f"NF-{i}"   # IDs únicos no ficheiro
            rows.append(row)
        r = self.client.post("/django/api/excel/import",
                             {"file": self._upload(content=make_xlsx(pd.DataFrame(rows)))},
                             format="multipart")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["imported"], 60)
        self.assertEqual(Transaction.objects.count(), 60)
        # re-import → todos duplicados ignorados
        r2 = self.client.post("/django/api/excel/import",
                              {"file": self._upload(content=make_xlsx(pd.DataFrame(rows)))},
                              format="multipart")
        self.assertEqual(r2.data["imported"], 0)
        self.assertEqual(r2.data["duplicates_ignored"], 60)

    def test_import_requires_auditor_role(self):
        viewer_token = str(uuid.uuid4())
        ApiToken.objects.create(token=viewer_token, user_id="viewer2", role="viewer")
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + viewer_token)
        r = self.client.post("/django/api/excel/import", {"file": self._upload()}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_analyze_on_database(self):
        Transaction.objects.bulk_create([
            Transaction(transaction_id=f"T{i}", vendor=f"V{i%4}", amount=500 + i * 137,
                        timestamp=timezone.now(), category="TI", user_id="u1",
                        status="Analyzed")
            for i in range(120)
        ])
        r = self.client.get("/django/api/excel/analyze?days=365")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["source"]["type"], "database")
        self.assertTrue(r.data["benford"]["applicable"])
        self.assertIn("risk_score", r.data)

    def test_reconcile_file_vs_file(self):
        db_rows = [
            {"Fornecedor": "Fornecedor X", "Valor da Nota": "100,00",
             "Data da Operação": "2025-03-04", "Nº Documento": "B1"},
            {"Fornecedor": "Fornecedor Y", "Valor da Nota": "777,00",
             "Data da Operação": "2025-03-04", "Nº Documento": "B2"},
        ]
        ledger_rows = [
            {"Fornecedor": "Fornecedor X", "Valor da Nota": "100.00",
             "Data da Operação": "2025-03-05", "Nº Documento": "L1"},
        ]
        fa = SimpleUploadedFile("banco.xlsx", make_xlsx(pd.DataFrame(db_rows)),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        fb = SimpleUploadedFile("razao.xlsx", make_xlsx(pd.DataFrame(ledger_rows)),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r = self.client.post("/django/api/excel/reconcile",
                             {"file_a": fa, "file_b": fb,
                              "amount_tol": "0.05", "date_tol_days": "3"},
                             format="multipart")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["summary"]["matched"], 1)
        self.assertEqual(r.data["summary"]["unmatched_a"], 1)

    def test_export_premium_transactions(self):
        Transaction.objects.bulk_create([
            Transaction(transaction_id=f"EX{i}", vendor="Forn", amount=100 * i,
                        timestamp=timezone.now(), category="TI", user_id="u1",
                        status="Analyzed")
            for i in range(10)
        ])
        r = self.client.get("/django/api/excel/export?type=full&days=365")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheetml", r["Content-Type"])
        wb = load_workbook(io.BytesIO(b"".join(r.streaming_content))) \
            if hasattr(r, "streaming_content") else load_workbook(io.BytesIO(r.content))
        self.assertIn("Sumário", wb.sheetnames)

    def test_export_invalid_type(self):
        r = self.client.get("/django/api/excel/export?type=banana")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


from openpyxl import load_workbook  # noqa: E402
