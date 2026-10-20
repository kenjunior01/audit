"""Testes do BI Engine (REA — Power BI parity): measures, visuais, what-if."""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from dashboard.models import ApiToken, Transaction
from dashboard.bi_service import (BIValidationError, decompose_view,
                                  group_measure, matrix_view, pareto_view,
                                  run_measure, what_if_view, drillthrough_view)

NOW = timezone.now()


def _mk_tx(i, vendor, amount, category='Compras', days_ago=10):
    return Transaction.objects.create(
        transaction_id=f"TX-{uuid.uuid4().hex[:10]}-{i}", vendor=vendor,
        amount=amount, currency="BRL",
        timestamp=NOW - timedelta(days=days_ago),
        category=category, status="Completed", user_id="u1")


class BIEngineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recent = [10, 10]           # dias
        _mk_tx(1, "Alfa", 1000)
        _mk_tx(2, "Alfa", 500)
        _mk_tx(3, "Beta", 300, category="Serviços")
        _mk_tx(4, "Beta", 200, category="Serviços")
        _mk_tx(5, "Gama", 100, days_ago=500)  # fora do YoY atual

    def test_agg_sum(self):
        v, n = run_measure({'op': 'agg', 'agg': 'sum', 'field': 'amount'})
        self.assertEqual(v, 2100.0)
        self.assertEqual(n, 5)

    def test_calc_filter_context(self):
        m = {'op': 'calc', 'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'},
             'filters': [{'field': 'vendor', 'op': 'eq', 'value': 'Alfa'}]}
        v, _ = run_measure(m)
        self.assertEqual(v, 1500.0)

    def test_ratio_and_diff(self):
        m = {'op': 'ratio',
             'a': {'op': 'calc', 'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                   'filters': [{'field': 'vendor', 'op': 'eq', 'value': 'Alfa'}]},
             'b': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}}
        v, _ = run_measure(m)
        self.assertAlmostEqual(v, 1500 / 2100)
        d, _ = run_measure({'op': 'diff',
                            'a': {'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                            'b': {'op': 'const', 'value': 100}})
        self.assertEqual(d, 2000.0)

    def test_group_bar(self):
        g = group_measure({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                          'vendor', top_n=10)
        by = {r['vendor']: r['value'] for r in g['rows']}
        self.assertEqual(by['Alfa'], 1500.0)
        self.assertEqual(by['Beta'], 500.0)
        self.assertEqual(g['rows'][0]['vendor'], 'Alfa')  # ordenado desc

    def test_group_pct_of_total(self):
        g = group_measure({'op': 'pct_of_total',
                           'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}},
                          'vendor')
        total = sum(r['value'] for r in g['rows'])
        self.assertAlmostEqual(total, 1.0)

    def test_group_running_total(self):
        g = group_measure({'op': 'running_total',
                           'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}},
                          'vendor', mode='running_total')
        rows = g['rows']
        self.assertAlmostEqual(rows[-1]['value'], 2100.0)

    def test_matrix_view(self):
        m = matrix_view({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                        'vendor', 'category')
        alfa = next(r for r in m['rows'] if r['row'] == 'Alfa')
        self.assertEqual(alfa['Compras'], 1500.0)
        self.assertEqual(m['grand_total'], 2100.0)

    def test_pareto_vital_few(self):
        p = pareto_view({'op': 'agg', 'agg': 'sum', 'field': 'amount'}, 'vendor')
        self.assertTrue(p['rows'][0]['vital_few'])
        self.assertAlmostEqual(sum(r['share'] for r in p['rows']), 1.0)
        # Alfa+Beta = 95,2% ≥ 80% → ambos "vital few"; Gama é o "trivial many"
        self.assertEqual(p['n_vital_few'], 2)

    def test_decompose_tree(self):
        t = decompose_view({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                           ['vendor', 'category'])
        self.assertEqual(t['root_value'], 2100.0)
        lvl0 = t['tree'][0]
        best = lvl0['children'][0]
        self.assertEqual(best['value'], 1500.0)
        self.assertAlmostEqual(best['pct_of_parent'], 1500 / 2100)

    def test_what_if(self):
        w = what_if_view({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                         adjustment_pct=10)
        self.assertAlmostEqual(w['adjusted'], 2310.0)
        self.assertAlmostEqual(w['delta'], 210.0)

    def test_drillthrough(self):
        d = drillthrough_view([{'field': 'vendor', 'op': 'eq', 'value': 'Alfa'}])
        self.assertEqual(d['count'], 2)
        self.assertTrue(all(r['vendor'] == 'Alfa' for r in d['rows']))

    def test_validation_rejects_injection(self):
        with self.assertRaises(BIValidationError):
            run_measure({'op': 'agg', 'agg': 'sum', 'field': 'password'})
        with self.assertRaises(BIValidationError):
            run_measure({'op': 'sql'})
        with self.assertRaises(BIValidationError):
            run_measure({'op': 'calc',
                         'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                         'filters': [{'field': 'vendor', 'op': 'raw', 'value': 'x'}]})

    def test_yoy_with_previous_window(self):
        m = {'op': 'yoy', 'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}}
        v, _ = run_measure(m)
        # atual: 1000+500+300+200 = 2000 (≤365d); anterior: Gama 100 (500d atrás)
        self.assertAlmostEqual(v, (2000 - 100) / 100)


class YoYWindowTest(TestCase):
    """Time-intelligence em dataset isolado (janela sem histórico)."""

    def test_yoy_none_without_previous(self):
        _mk_tx(21, "Delta", 700, days_ago=5)
        m = {'op': 'yoy', 'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}}
        v, _ = run_measure(m)
        self.assertIsNone(v)  # janela anterior vazia → None (não divide por zero)

    def test_mom_with_previous(self):
        _mk_tx(22, "Echo", 400, days_ago=5)
        _mk_tx(23, "Foxtrot", 100, days_ago=45)
        m = {'op': 'mom', 'measure': {'op': 'agg', 'agg': 'sum', 'field': 'amount'}}
        v, _ = run_measure(m)
        self.assertAlmostEqual(v, (400 - 100) / 100)


class BIEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.t_admin = str(uuid.uuid4())
        ApiToken.objects.create(token=self.t_admin, user_id="admin@x.pt", role="admin")
        self.t_viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=self.t_viewer, user_id="viewer@x.pt", role="viewer")
        _mk_tx(9, "Alfa", 100)

    def test_meta(self):
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.get("/django/api/bi/meta")
        self.assertEqual(r.status_code, 200)
        self.assertIn('vendor', r.data['dimensions'])
        self.assertIn('sum', r.data['aggregations'])

    def test_evaluate_and_group(self):
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.post("/django/api/bi/evaluate",
                   {"measure": {"op": "agg", "agg": "sum", "field": "amount"}},
                   format="json")
        self.assertEqual(r.data["value"], 100.0)
        r = c.post("/django/api/bi/group",
                   {"measure": {"op": "agg", "agg": "sum", "field": "amount"},
                    "dimension": "vendor"}, format="json")
        self.assertEqual(len(r.data["rows"]), 1)

    def test_measure_crud_and_guard(self):
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.post("/django/api/bi/measures",
                   {"name": "Receita Total",
                    "expression": {"op": "agg", "agg": "sum", "field": "amount"}},
                   format="json")
        self.assertEqual(r.status_code, 201)
        r = c.get("/django/api/bi/measures")
        self.assertEqual(r.data["count"], 1)
        # viewer não cria
        v = APIClient(); v.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_viewer)
        r = v.post("/django/api/bi/measures",
                   {"name": "X", "expression": {"op": "agg", "agg": "count", "field": "id"}},
                   format="json")
        self.assertEqual(r.status_code, 403)
        # expressão inválida rejeitada
        r = c.post("/django/api/bi/measures",
                   {"name": "Y", "expression": {"op": "hack"}}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_whatif_endpoint(self):
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + self.t_admin)
        r = c.post("/django/api/bi/whatif",
                   {"measure": {"op": "agg", "agg": "sum", "field": "amount"},
                    "adjustment_pct": 50}, format="json")
        self.assertAlmostEqual(r.data["adjusted"], 150.0)
