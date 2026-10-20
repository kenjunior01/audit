"""Testes de Row-Level Security (REA — Power BI RLS parity)."""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import ApiToken, RLSRule, Transaction
from dashboard.bi_service import rls_rules_for, run_measure

NOW = timezone.now()


def _mk(vendor, amount):
    return Transaction.objects.create(
        transaction_id=f"R-{uuid.uuid4().hex[:8]}", vendor=vendor, amount=amount,
        currency="BRL", timestamp=NOW - timedelta(days=1),
        category="Compras", status="Completed", user_id="u1")


class RLSRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("Alfa", 100)
        _mk("Beta", 200)
        _mk("Gama", 300)
        RLSRule.objects.create(name="Só Alfa", user_id="user.alfa@x.pt",
                               dimension="vendor", allowed_values=["Alfa"])
        RLSRule.objects.create(name="Viewers vêem Alfa/Beta", role="viewer",
                               dimension="vendor", allowed_values=["Alfa", "Beta"])
        RLSRule.objects.create(name="Inativa", user_id="user.alfa@x.pt",
                               dimension="vendor", allowed_values=["Gama"],
                               active=False)

    def test_rules_for_user_and_role(self):
        self.assertEqual(len(rls_rules_for("user.alfa@x.pt", "auditor")), 1)
        self.assertEqual(len(rls_rules_for("other@x.pt", "viewer")), 1)
        self.assertEqual(len(rls_rules_for("other@x.pt", "auditor")), 0)

    def test_measure_respects_rls(self):
        v, n = run_measure({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                           user_id="user.alfa@x.pt", role="auditor")
        self.assertEqual(v, 100.0)
        self.assertEqual(n, 1)
        # viewer com regra por role vê 300
        v, n = run_measure({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                           user_id="x@x.pt", role="viewer")
        self.assertEqual(v, 300.0)
        # sem regras → vê tudo
        v, n = run_measure({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                           user_id="admin@x.pt", role="admin")
        self.assertEqual(v, 600.0)

    def test_rls_endpoints_admin_only(self):
        ta = str(uuid.uuid4())
        ApiToken.objects.create(token=ta, user_id="admin@x.pt", role="admin")
        tv = str(uuid.uuid4())
        ApiToken.objects.create(token=tv, user_id="v@x.pt", role="viewer")

        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + ta)
        r = c.get("/django/api/bi/rls")
        self.assertEqual(r.data["count"], 3)
        r = c.post("/django/api/bi/rls",
                   {"name": "Regional Norte", "role": "auditor",
                    "dimension": "category", "allowed_values": ["Compras"]},
                   format="json")
        self.assertEqual(r.status_code, 201)
        pk = r.data["id"]
        r = c.patch(f"/django/api/bi/rls/{pk}", {"active": False}, format="json")
        self.assertFalse(r.data["active"])

        v = APIClient(); v.credentials(HTTP_AUTHORIZATION="Bearer " + tv)
        self.assertEqual(v.get("/django/api/bi/rls").status_code, 403)
        self.assertEqual(v.post("/django/api/bi/rls", {"dimension": "vendor",
                                                       "allowed_values": ["x"]},
                                format="json").status_code, 403)

    def test_rls_validation(self):
        ta = str(uuid.uuid4())
        ApiToken.objects.create(token=ta, user_id="admin@x.pt", role="admin")
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + ta)
        # dimensão inválida
        r = c.post("/django/api/bi/rls", {"dimension": "password",
                                          "allowed_values": ["x"], "role": "auditor"},
                   format="json")
        self.assertEqual(r.status_code, 400)
        # sem target
        r = c.post("/django/api/bi/rls", {"dimension": "vendor",
                                          "allowed_values": ["x"]}, format="json")
        self.assertEqual(r.status_code, 400)
