"""Testes de observabilidade: middleware de métricas, /metrics e OpenAPI/Swagger."""
from django.test import TestCase
from rest_framework.test import APIClient

from dashboard.observability import MetricsMiddleware, normalize_path, record_request
from dashboard.models import Alert, ApiToken, Notification, Transaction


class NormalizePathTest(TestCase):
    def test_numeric_ids_normalized(self):
        self.assertEqual(normalize_path("/django/api/cases/42"), "/django/api/cases/:id")
        self.assertEqual(normalize_path("/django/api/cases/42/comments/7"),
                         "/django/api/cases/:id/comments/:id")

    def test_no_ids_untouched(self):
        self.assertEqual(normalize_path("/django/api/health"), "/django/api/health")


class MetricsMiddlewareTest(TestCase):
    def test_record_request_counters(self):
        path = f"/django/api/counter-test-{id(self)}"
        record_request("GET", path, 200, 12.5)
        record_request("GET", path, 200, 40.0)
        from dashboard.observability import _HTTP_COUNTS
        after = _HTTP_COUNTS.get(("GET", path, 200), 0)
        self.assertEqual(after, 2)

    def test_middleware_wraps_client_requests(self):
        c = APIClient()
        c.get("/django/api/health")
        from dashboard.observability import _LATENCY_BUCKETS
        self.assertIn("/django/api/health", _LATENCY_BUCKETS)


class MetricsEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Transaction.objects.create(transaction_id="T1", vendor="F", amount=10,
                                   currency="BRL", timestamp="2026-01-05T10:00:00Z")
        Alert.objects.create(alert_type="X", severity="Critical")

    def test_metrics_public_and_prometheus_format(self):
        c = APIClient()
        c.get("/django/api/health")  # gera counter
        r = c.get("/django/api/metrics")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn("audit_transactions_total 1", body)
        self.assertIn('audit_alerts_by_severity{severity="critical"} 1', body)
        self.assertIn("# HELP audit_transactions_total", body)
        self.assertIn("# TYPE audit_http_requests_total counter", body)
        self.assertIn("audit_uptime_seconds", body)

    def test_metrics_includes_notifications_gauge(self):
        Notification.objects.create(recipient="a@x.pt", kind="system", title="t")
        c = APIClient()
        r = c.get("/django/api/metrics")
        self.assertIn("audit_notifications_unread 1", r.content.decode())


class OpenAPISchemaTest(TestCase):
    def test_schema_generates(self):
        c = APIClient()
        r = c.get("/django/api/schema")
        self.assertEqual(r.status_code, 200)
        self.assertIn("openapi", r.content.decode())

    def test_swagger_ui_serves(self):
        c = APIClient()
        r = c.get("/django/api/schema/swagger-ui")
        self.assertEqual(r.status_code, 200)
        self.assertIn("swagger", r.content.decode().lower())

    def test_redoc_serves(self):
        c = APIClient()
        r = c.get("/django/api/schema/redoc")
        self.assertEqual(r.status_code, 200)
