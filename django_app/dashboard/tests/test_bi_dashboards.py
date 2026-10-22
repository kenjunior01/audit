"""Testes dos Relatórios BI guardados (dashboards com cross-filtering)."""
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import ApiToken, BIDashboard, Transaction

MEAS = {'op': 'agg', 'agg': 'sum', 'field': 'amount'}


def _mk(vendor, amount):
    return Transaction.objects.create(
        transaction_id=f"D-{uuid.uuid4().hex[:10]}", vendor=vendor,
        amount=amount, currency="BRL",
        timestamp=timezone.now(),
        category="Compras", status="Completed", user_id="u1")


CONFIG = {
    'slicers': [],
    'visuals': [
        {'id': 'v1', 'kind': 'bar', 'measure': MEAS, 'dimension': 'vendor',
         'title': 'Por fornecedor'},
        {'id': 'v2', 'kind': 'kpi', 'measure': MEAS, 'target': 100,
         'title': 'Total vs alvo'},
        {'id': 'v3', 'kind': 'bar', 'measure': MEAS, 'dimension': 'status',
         'title': 'Por estado'},
    ],
}


class DashboardCrudTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("DashA", 100)
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="adm@x.pt", role="admin")
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")

    def test_create_list_get_delete(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = c.post("/django/api/bi/dashboards",
                   {"name": "Relatório Mensal", "description": "demo",
                    "config": CONFIG}, format="json")
        self.assertEqual(r.status_code, 201)
        pk = r.data['id']

        r = c.get("/django/api/bi/dashboards")
        self.assertEqual(r.data['count'], 1)
        r = c.get(f"/django/api/bi/dashboards/{pk}")
        self.assertEqual(r.data['config']['visuals'][0]['id'], 'v1')

        r = c.put(f"/django/api/bi/dashboards/{pk}",
                  {"config": {**CONFIG, 'slicers': [
                      {'field': 'status', 'op': 'eq', 'value': 'Completed'}]}},
                  format="json")
        self.assertEqual(r.status_code, 200)
        r = c.get(f"/django/api/bi/dashboards/{pk}")
        self.assertEqual(len(r.data['config']['slicers']), 1)

        r = c.delete(f"/django/api/bi/dashboards/{pk}")
        self.assertEqual(r.data['deleted'], pk)
        r = c.get("/django/api/bi/dashboards")
        self.assertEqual(r.data['count'], 0)

    def test_permissions_and_validation(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        # viewer lê, mas não cria
        r = c.get("/django/api/bi/dashboards")
        self.assertEqual(r.status_code, 200)
        r = c.post("/django/api/bi/dashboards",
                   {"name": "X", "config": CONFIG}, format="json")
        self.assertEqual(r.status_code, 403)

        a = APIClient()
        a.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = a.post("/django/api/bi/dashboards",
                   {"name": "Sem visuals", "config": {}}, format="json")
        self.assertEqual(r.status_code, 400)
        bad = {**CONFIG, 'visuals': [{'id': 'v1', 'kind': 'hack',
                                      'measure': MEAS}]}
        r = a.post("/django/api/bi/dashboards",
                   {"name": "Visual inválido", "config": bad}, format="json")
        self.assertEqual(r.status_code, 400)
        r = a.post("/django/api/bi/dashboards",
                   {"name": "Dim inválida",
                    "config": {**CONFIG, 'visuals': [
                        {'id': 'v1', 'kind': 'bar', 'measure': MEAS,
                         'dimension': 'hack'}]}}, format="json")
        self.assertEqual(r.status_code, 400)
        # duplicado
        a.post("/django/api/bi/dashboards", {"name": "Rel X", "config": CONFIG},
               format="json")
        r = a.post("/django/api/bi/dashboards",
                   {"name": "Rel X", "config": CONFIG}, format="json")
        self.assertEqual(r.status_code, 409)


class DashboardRunTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("RunA", 100)
        _mk("RunB", 200)
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="adm@x.pt", role="admin")
        cls.pk = BIDashboard.objects.create(
            name=f"Rel-{uuid.uuid4().hex[:6]}", config=CONFIG,
            created_by="adm@x.pt").id
        # relatório com slicer + visual com erro embutido
        cls.pk2 = BIDashboard.objects.create(
            name=f"Rel2-{uuid.uuid4().hex[:6]}",
            config={'slicers': [{'field': 'status', 'op': 'eq',
                                 'value': 'Completed'}],
                    'visuals': [
                        {'id': 'ok', 'kind': 'bar', 'measure': MEAS,
                         'dimension': 'vendor'},
                        {'id': 'bad', 'kind': 'bar', 'measure': {'op': 'x'},
                         'dimension': 'vendor'}]},
            created_by="adm@x.pt").id

    def test_run_executes_all_visuals(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = c.post(f"/django/api/bi/dashboards/{self.pk}/run", {}, format="json")
        self.assertEqual(r.status_code, 200)
        vs = r.data['visuals']
        self.assertEqual(len(vs), 3)
        self.assertTrue(all(v['ok'] for v in vs))
        bar = next(v for v in vs if v['id'] == 'v1')
        self.assertIn('rows', bar['data'])

    def test_run_with_cross_filters(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        cross = [{'field': 'vendor', 'op': 'eq', 'value': 'RunA'}]
        r = c.post(f"/django/api/bi/dashboards/{self.pk}/run",
                   {"cross_filters": cross}, format="json")
        vs = r.data['visuals']
        kpi = next(v for v in vs if v['id'] == 'v2')
        self.assertAlmostEqual(kpi['data']['value'], 100.0, places=2)
        self.assertEqual(r.data['cross_filters'], cross)

    def test_run_isolates_visual_errors(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = c.post(f"/django/api/bi/dashboards/{self.pk2}/run", {}, format="json")
        vs = r.data['visuals']
        ok = next(v for v in vs if v['id'] == 'ok')
        bad = next(v for v in vs if v['id'] == 'bad')
        self.assertTrue(ok['ok'])
        self.assertFalse(bad['ok'])
        self.assertIn('error', bad)
        # slicer aplicado: RunA/RunB são Completed → visíveis
        self.assertGreaterEqual(len(ok['data']['rows']), 2)

    def test_run_404(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = c.post("/django/api/bi/dashboards/999999/run", {}, format="json")
        self.assertEqual(r.status_code, 404)
