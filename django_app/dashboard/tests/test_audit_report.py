"""Testes do Relatório Global de Auditoria (resumo JSON + PDF premium)."""
import io
import uuid

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from dashboard.models import Alert, ApiToken, AuditCase, Transaction
from dashboard.report_service import (audit_report_summary, build_audit_report_pdf,
                                      build_recommendations)


class ReportServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(10):
            Transaction.objects.create(
                transaction_id=f"T{i}", vendor=f"Forn {i % 3}", amount=100 + i,
                currency="BRL", timestamp="2026-01-05T10:00:00Z")
        txn = Transaction.objects.first()
        Alert.objects.create(transaction=txn, alert_type="Round Value", severity="Critical",
                             vendor="Forn 0", amount=500)
        Alert.objects.create(transaction=txn, alert_type="Duplicate", severity="High",
                             vendor="Forn 1", amount=250)
        Alert.objects.create(transaction=txn, alert_type="Weekend", severity="Low",
                             vendor="Forn 2", amount=90)
        AuditCase.objects.create(title="Caso A", status="In Progress", created_by="bob")
        AuditCase.objects.create(title="Caso B", status="Closed", created_by="bob")

    def test_summary_kpis(self):
        s = audit_report_summary(30)
        k = s["kpis"]
        self.assertEqual(k["transactions"], 10)
        self.assertEqual(k["alerts"], 3)
        self.assertEqual(k["alerts_by_severity"].get("Critical"), 1)
        self.assertEqual(k["cases_open"], 1)
        self.assertGreater(k["data_completeness"], 90)

    def test_summary_period_and_vendors(self):
        s = audit_report_summary(7)
        self.assertIn("period", s)
        self.assertEqual(len(s["top_vendors"]), 3)
        self.assertEqual(len(s["alert_vendors"]), 3)

    def test_recommendations_generated(self):
        s = audit_report_summary(30)
        recs = build_recommendations(s)
        self.assertGreaterEqual(len(recs), 1)
        self.assertTrue(any("críticos" in r or "crítico" in r.lower() for r in recs))

    def test_pdf_builds_with_content(self):
        pdf, fname, s = build_audit_report_pdf(30, generated_by="tester@x.pt")
        self.assertGreater(len(pdf), 3000)
        self.assertTrue(fname.startswith("relatorio_auditoria_"))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(pdf.count(b"/Type"), 0)  # objetos de página/documento presentes


class ReportEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.t_admin = str(uuid.uuid4())
        ApiToken.objects.create(token=self.t_admin, user_id="admin@x.pt", role="admin")
        self.t_viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=self.t_viewer, user_id="viewer@x.pt", role="viewer")

    def test_summary_requires_auth(self):
        r = APIClient().get("/django/api/reports/audit")
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_summary_viewer_forbidden(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_viewer)
        r = c.get("/django/api/reports/audit")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_summary_admin_ok(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.get("/django/api/reports/audit?days=7")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("kpis", r.data)
        self.assertIn("recommendations", r.data)
        self.assertGreaterEqual(len(r.data["recommendations"]), 1)

    def test_pdf_download(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.get("/django/api/reports/audit/pdf")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertGreater(len(r.content), 3000)
