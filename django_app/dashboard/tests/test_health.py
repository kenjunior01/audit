"""
Testes do health check público (/django/api/health).
"""
from django.test import TestCase
from rest_framework.test import APIClient


class HealthEndpointTest(TestCase):
    def test_health_ok_with_db(self):
        r = APIClient().get("/django/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "ok")
        self.assertTrue(r.data["db"])
        self.assertEqual(r.data["service"], "audit-api")

    def test_health_public_no_auth_needed(self):
        """Sem token → continua 200 (endpoint público de monitorização)."""
        r = APIClient().get("/django/api/health")
        self.assertEqual(r.status_code, 200)
