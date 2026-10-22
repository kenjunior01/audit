"""Testes do Auto-Dashboard (método REA aplicado — painel de 1 clique).

Cobre: engenharia reversa das dimensões, KPIs, visuais gerados, insights
narrativos, filtros, resiliência (dataset vazio) e permissões.
"""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from dashboard.models import ApiToken, Transaction

NOW = timezone.now()


def _mk_tx(i, vendor, amount, category='Compras', days_ago=10, status='Completed'):
    return Transaction.objects.create(
        transaction_id=f"AUTO-{uuid.uuid4().hex[:10]}-{i}", vendor=vendor,
        amount=amount, currency="BRL",
        timestamp=NOW - timedelta(days=days_ago),
        category=category, status=status, user_id="u1")


class AutoDashboardServiceTest(TestCase):
    """Nível de serviço: auto_dashboard() com dataset conhecido."""

    @classmethod
    def setUpTestData(cls):
        _mk_tx(1, "Alfa", 1000)                       # este mês
        _mk_tx(2, "Alfa", 500)
        _mk_tx(3, "Beta", 300, category="Serviços")
        _mk_tx(4, "Beta", 200, category="Serviços")
        _mk_tx(5, "Gama", 100, days_ago=95)           # período anterior
        _mk_tx(6, "Gama", 400, days_ago=400)          # ano anterior

    def test_basic_shape_and_kpis(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard()
        self.assertFalse(p['empty'])
        self.assertEqual(p['meta']['records'], 6)
        kpis = {k['key']: k for k in p['kpis']}
        self.assertAlmostEqual(kpis['total']['value'], 2500.0, delta=0.01)
        self.assertEqual(kpis['records']['value'], 6)
        self.assertAlmostEqual(kpis['avg']['value'], 2500 / 6, delta=0.01)
        self.assertAlmostEqual(kpis['peak']['value'], 1000.0)
        self.assertEqual(kpis['leader']['value'], 'Alfa')

    def test_reverse_engineering_choices(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard()
        choices = p['meta']['choices']
        self.assertTrue(any('dimensão principal' in c['decision'] for c in choices))
        self.assertTrue(all(c.get('evidence') for c in choices))
        # vendor deve ganhar (4 valores, cobertura 100%)
        self.assertEqual(p['visuals']['bar']['dimension'], 'vendor')

    def test_visuals_generated(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard()
        v = p['visuals']
        self.assertIn('bar', v)
        self.assertIn('series', v)
        self.assertIn('pareto', v)
        self.assertIn('anomaly', v)
        # bar ordenado desc: Alfa primeiro
        self.assertEqual(v['bar']['data']['rows'][0]['vendor'], 'Alfa')
        # pareto tem vital few
        self.assertIn('n_vital_few', v['pareto']['data'])

    def test_insights_nonempty(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard()
        self.assertTrue(p['insights'])
        self.assertTrue(all(isinstance(s, str) and s for s in p['insights']))

    def test_recent_and_period(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard()
        self.assertLessEqual(len(p['recent']), 12)
        self.assertIn('period', p['meta'])
        self.assertTrue(p['meta']['period'].get('start'))

    def test_filters_applied(self):
        from dashboard.bi_auto_service import auto_dashboard
        p = auto_dashboard(filters=[{'field': 'vendor', 'op': 'eq',
                                     'value': 'Alfa'}])
        self.assertEqual(p['meta']['records'], 2)
        kpis = {k['key']: k for k in p['kpis']}
        self.assertAlmostEqual(kpis['total']['value'], 1500.0)

    def test_empty_dataset(self):
        from dashboard.bi_auto_service import auto_dashboard
        Transaction.objects.all().delete()
        p = auto_dashboard()
        self.assertTrue(p['empty'])
        self.assertEqual(p['kpis'], [])
        self.assertIn('visuals', p)


class AutoDashboardEndpointTest(TestCase):
    """Nível de API: permissões, filtros inválidos e integração."""

    @classmethod
    def setUpTestData(cls):
        _mk_tx(1, "Alfa", 1000)
        _mk_tx(2, "Beta", 250, category="Serviços")
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")

    def _client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        return c

    def test_viewer_can_generate(self):
        r = self._client().post("/django/api/bi/auto", {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['empty'])
        self.assertEqual(r.data['meta']['records'], 2)

    def test_requires_auth(self):
        r = APIClient().post("/django/api/bi/auto", {}, format="json")
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED,
                                      status.HTTP_403_FORBIDDEN))

    def test_invalid_filter_rejected(self):
        r = self._client().post("/django/api/bi/auto",
                                {"filters": [{"field": "hack", "op": "eq",
                                              "value": "x"}]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_filters_non_list_rejected(self):
        r = self._client().post("/django/api/bi/auto",
                                {"filters": "vendor"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_period_filter_end_to_end(self):
        r = self._client().post(
            "/django/api/bi/auto",
            {"filters": [{"field": "date", "op": "gte",
                          "value": (NOW - timedelta(days=30)).strftime('%Y-%m-%d')}]},
            format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['meta']['records'], 2)
