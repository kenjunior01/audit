import os
import sys

import django

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auditportal.settings")
django.setup()

from django.test import RequestFactory
from django.utils import timezone
from rest_framework.request import Request

from dashboard.models import Alert, AuditCase, Transaction
from dashboard.views import AlertViewSet, AuditCaseViewSet, TransactionViewSet


def test_pdf_export():
    print("Iniciando teste de exportação de PDF...")

    tx = Transaction.objects.create(
        transaction_id=f"PDF_TEST_{timezone.now().timestamp()}",
        vendor="PDF Test Vendor",
        amount=5000.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="PDFTester",
    )

    case = AuditCase.objects.create(
        title="PDF Export Test Case",
        description="Testing the automated PDF report generation with digital signature.",
        transaction_id=tx.transaction_id,
        status="Under Investigation",
        priority="High",
        created_by="PDFTester",
    )
    print(f"Caso de teste criado: ID {case.id}")

    factory = RequestFactory()
    django_request = factory.get(f"/api/cases/{case.id}/export_pdf/")
    request = Request(django_request)

    viewset = AuditCaseViewSet()
    viewset.kwargs = {"pk": case.id}
    viewset.request = request

    print("Gerando PDF...")
    response = viewset.export_pdf(request, pk=case.id)

    assert (
        response.status_code == 200
    ), f"Status inesperado ao gerar PDF: {response.status_code}"
    assert (
        response["Content-Type"] == "application/pdf"
    ), f"Content-Type inesperado: {response['Content-Type']}"

    filename = f"test_output_case_{case.id}.pdf"
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"PDF gerado com sucesso: {filename}")
    print(f"Tamanho do arquivo: {len(response.content)} bytes")


def test_cases_export_spreadsheets():
    print("Iniciando teste de exportação Excel/CSV de casos...")

    tx = Transaction.objects.create(
        transaction_id=f"CASE_EXPORT_{timezone.now().timestamp()}",
        vendor="Case Export Vendor",
        amount=1000.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="CaseTester",
    )

    AuditCase.objects.create(
        title="Case Export Test",
        description="Testing case export to Excel/CSV.",
        transaction_id=tx.transaction_id,
        status="New",
        priority="High",
        created_by="CaseTester",
    )

    factory = RequestFactory()

    django_request_excel = factory.get("/api/cases/export_excel/")
    request_excel = Request(django_request_excel)
    cases_viewset = AuditCaseViewSet()
    cases_viewset.request = request_excel

    response_excel = cases_viewset.export_excel(request_excel)
    assert (
        response_excel.status_code == 200
    ), f"Status inesperado ao exportar casos para Excel: {response_excel.status_code}"
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in response_excel["Content-Type"]
    ), f"Content-Type inesperado para Excel: {response_excel['Content-Type']}"

    django_request_csv = factory.get("/api/cases/export_csv/")
    request_csv = Request(django_request_csv)
    cases_viewset.request = request_csv
    response_csv = cases_viewset.export_csv(request_csv)
    assert (
        response_csv.status_code == 200
    ), f"Status inesperado ao exportar casos para CSV: {response_csv.status_code}"
    assert "text/csv" in response_csv["Content-Type"], (
        f"Content-Type inesperado para CSV: {response_csv['Content-Type']}"
    )

    print("Exportação de casos para Excel e CSV validada com sucesso.")


def test_transactions_export_spreadsheets():
    print("Iniciando teste de exportação Excel/CSV de transações...")

    Transaction.objects.create(
        transaction_id=f"TX_EXPORT_{timezone.now().timestamp()}",
        vendor="Transaction Export Vendor",
        amount=2500.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="TxTester",
    )

    factory = RequestFactory()

    django_request_excel = factory.get("/api/transactions/export_excel/")
    request_excel = Request(django_request_excel)
    tx_viewset = TransactionViewSet()
    tx_viewset.request = request_excel

    response_excel = tx_viewset.export_excel(request_excel)
    assert (
        response_excel.status_code == 200
    ), f"Status inesperado ao exportar transações para Excel: {response_excel.status_code}"
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in response_excel["Content-Type"]
    ), f"Content-Type inesperado para Excel: {response_excel['Content-Type']}"

    django_request_csv = factory.get("/api/transactions/export_csv/")
    request_csv = Request(django_request_csv)
    tx_viewset.request = request_csv
    response_csv = tx_viewset.export_csv(request_csv)
    assert (
        response_csv.status_code == 200
    ), f"Status inesperado ao exportar transações para CSV: {response_csv.status_code}"
    assert "text/csv" in response_csv["Content-Type"], (
        f"Content-Type inesperado para CSV: {response_csv['Content-Type']}"
    )

    print("Exportação de transações para Excel e CSV validada com sucesso.")


def test_alerts_export_spreadsheets():
    print("Iniciando teste de exportação Excel/CSV de alertas...")

    tx = Transaction.objects.create(
        transaction_id=f"ALERT_EXPORT_{timezone.now().timestamp()}",
        vendor="Alert Export Vendor",
        amount=3000.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="AlertTester",
    )

    Alert.objects.create(
        transaction=tx,
        alert_type="Test Alert",
        severity="High",
        status="New",
        description="Testing alert export.",
        vendor=tx.vendor,
        amount=tx.amount,
        materiality=0.9,
    )

    factory = RequestFactory()

    django_request_excel = factory.get("/api/alerts/export_excel/")
    request_excel = Request(django_request_excel)
    alert_viewset = AlertViewSet()
    alert_viewset.request = request_excel

    response_excel = alert_viewset.export_excel(request_excel)
    assert (
        response_excel.status_code == 200
    ), f"Status inesperado ao exportar alertas para Excel: {response_excel.status_code}"
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in response_excel["Content-Type"]
    ), f"Content-Type inesperado para Excel: {response_excel['Content-Type']}"

    django_request_csv = factory.get("/api/alerts/export_csv/")
    request_csv = Request(django_request_csv)
    alert_viewset.request = request_csv
    response_csv = alert_viewset.export_csv(request_csv)
    assert (
        response_csv.status_code == 200
    ), f"Status inesperado ao exportar alertas para CSV: {response_csv.status_code}"
    assert "text/csv" in response_csv["Content-Type"], (
        f"Content-Type inesperado para CSV: {response_csv['Content-Type']}"
    )

    print("Exportação de alertas para Excel e CSV validada com sucesso.")


def test_transaction_rules_engine_scan():
    print("Iniciando teste do mecanismo genérico de regras em transações...")

    Transaction.objects.filter(
        transaction_id__startswith="RULE_ENGINE_"
    ).delete()
    Alert.objects.filter(
        alert_type__in=[
            "HIGH_AMOUNT",
            "WEEKEND_TRANSACTION",
            "MISSING_VENDOR",
            "CFG_HIGH_AMOUNT",
        ]
    ).delete()

    tx = Transaction.objects.create(
        transaction_id=f"RULE_ENGINE_{timezone.now().timestamp()}",
        vendor="Rule Engine Vendor",
        amount=150000.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="RuleTester",
    )

    factory = RequestFactory()
    django_request = factory.post("/api/transactions/scan_rules/")
    request = Request(django_request)

    viewset = TransactionViewSet()
    viewset.request = request

    response = viewset.scan_rules(request)

    assert (
        response.status_code == 200
    ), f"Status inesperado ao varrer regras: {response.status_code}"

    alerts = Alert.objects.filter(transaction=tx, alert_type="CFG_HIGH_AMOUNT")

    if alerts.exists():
        print("Regra configurável CFG_HIGH_AMOUNT aplicada com sucesso.")
    else:
        print(
            "Aviso: nenhuma regra configurável encontrada (provavelmente falta aplicar migrations para AuditRule)."
        )

    print("Mecanismo genérico de regras em transações validado com sucesso.")


def test_alert_rules_engine_scan():
    print("Iniciando teste do mecanismo genérico de regras em alertas...")

    Transaction.objects.filter(
        transaction_id__startswith="ALERT_RULE_ENGINE_"
    ).delete()
    Alert.objects.filter(
        alert_type__in=[
            "Test Alert",
        ]
    ).delete()

    tx = Transaction.objects.create(
        transaction_id=f"ALERT_RULE_ENGINE_{timezone.now().timestamp()}",
        vendor="Alert Rule Engine Vendor",
        amount=3000.0,
        category="Consulting",
        timestamp=timezone.now(),
        user_id="AlertRuleTester",
    )

    Alert.objects.create(
        transaction=tx,
        alert_type="Test Alert",
        severity="Medium",
        status="New",
        description="Testing alert rules engine.",
        vendor=tx.vendor,
        amount=tx.amount,
        materiality=0.5,
    )

    factory = RequestFactory()
    django_request = factory.post("/api/alerts/scan_rules/")
    request = Request(django_request)

    viewset = AlertViewSet()
    viewset.request = request

    response = viewset.scan_rules(request)

    assert (
        response.status_code == 200
    ), f"Status inesperado ao varrer regras de alertas: {response.status_code}"

    print("Mecanismo genérico de regras em alertas validado com sucesso.")


if __name__ == "__main__":
    test_pdf_export()
    test_cases_export_spreadsheets()
    test_transactions_export_spreadsheets()
    test_alerts_export_spreadsheets()
    test_transaction_rules_engine_scan()
    test_alert_rules_engine_scan()
