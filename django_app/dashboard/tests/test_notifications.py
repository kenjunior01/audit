"""Testes da Central de Notificações (modelo, serviço e endpoints REST)."""
import uuid

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from dashboard.models import Alert, ApiToken, Notification, Transaction
from dashboard.notifications_service import (notify_alert, notify_case_status,
                                             notify_role, notify_user, unread_count)


class NotificationServiceTest(TestCase):
    def test_notify_user_creates(self):
        n = notify_user("ana@x.pt", "system", "Olá", body="corpo", route="/alerts")
        self.assertIsNotNone(n)
        self.assertEqual(n.recipient, "ana@x.pt")
        self.assertTrue(n.is_unread)

    def test_notify_user_dedupe(self):
        notify_user("ana@x.pt", "system", "Duplicado")
        n2 = notify_user("ana@x.pt", "system", "Duplicado")
        self.assertIsNone(n2)  # dentro da janela de dedupe

    def test_notify_user_empty_recipient(self):
        self.assertIsNone(notify_user("", "system", "nada"))

    def test_notify_role_filters_roles(self):
        ApiToken.objects.create(token=str(uuid.uuid4()), user_id="admin1", role="admin")
        ApiToken.objects.create(token=str(uuid.uuid4()), user_id="viewer1", role="viewer")
        out = notify_role(roles=("admin",), kind="system", title="Para admins")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].recipient, "admin1")

    def test_notify_alert_only_relevant_severities(self):
        ApiToken.objects.create(token=str(uuid.uuid4()), user_id="auditor@x.pt", role="auditor")
        txn = Transaction.objects.create(
            transaction_id="T1", vendor="F", amount=100, currency="BRL",
            timestamp="2026-01-05T10:00:00Z")
        a_low = Alert.objects.create(transaction=txn, alert_type="X", severity="Low")
        self.assertEqual(notify_alert(a_low), [])
        a_crit = Alert.objects.create(transaction=txn, alert_type="Y", severity="Critical")
        out = notify_alert(a_crit)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "critical")

    def test_notify_case_status_change(self):
        from dashboard.models import AuditCase
        ApiToken.objects.create(token=str(uuid.uuid4()), user_id="auditor2@x.pt", role="admin")
        c = AuditCase.objects.create(title="Caso", status="New", created_by="bob")
        out = notify_case_status(c, "New", "In Progress", actor="alice")
        self.assertEqual(len(out), 1)
        self.assertIn("In Progress", out[0].title)
        # mesma estado → nada
        self.assertEqual(notify_case_status(c, "In Progress", "In Progress"), [])


class NotificationEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = str(uuid.uuid4())
        ApiToken.objects.create(token=self.token, user_id="me@x.pt", role="auditor")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        notify_user("me@x.pt", "alert.created", "Alerta crítico", severity="critical", route="/alerts")
        notify_user("me@x.pt", "excel.import", "Importação", severity="success")
        notify_user("other@x.pt", "system", "De outro utilizador")

    def test_list_only_own(self):
        r = self.client.get("/django/api/notifications")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        titles = [i["title"] for i in r.data["results"]]
        self.assertEqual(r.data["count"], 2)
        self.assertIn("Alerta crítico", titles)
        self.assertNotIn("De outro utilizador", titles)

    def test_unread_count_endpoint(self):
        r = self.client.get("/django/api/notifications/unread-count")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["unread"], 2)

    def test_filter_unread_param(self):
        n = Notification.objects.filter(recipient="me@x.pt").first()
        n.mark_read()
        r = self.client.get("/django/api/notifications?unread=1")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["unread"], 1)

    def test_mark_read_ids_and_all(self):
        ids = list(Notification.objects.filter(recipient="me@x.pt")
                   .values_list("id", flat=True))
        r = self.client.post("/django/api/notifications/read", {"ids": ids[:1]}, format="json")
        self.assertEqual(r.data["marked"], 1)
        r = self.client.post("/django/api/notifications/read", {"all": True}, format="json")
        self.assertEqual(r.data["marked"], 1)
        self.assertEqual(unread_count("me@x.pt"), 0)

    def test_mark_read_requires_ids_or_all(self):
        r = self.client.post("/django/api/notifications/read", {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_auth(self):
        anon = APIClient()
        r = anon.get("/django/api/notifications")
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
