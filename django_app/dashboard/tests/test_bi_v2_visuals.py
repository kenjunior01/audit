"""Testes do BI Studio v2 — visuais avançados (séries, forecast, anomalias,
waterfall, funil, scatter, KPI, dimensão semana) e dispatcher /bi/visual."""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import ApiToken, Transaction
from dashboard.bi_service import (BIValidationError, anomaly_view, forecast_view,
                                  funnel_view, kpi_view, scatter_view,
                                  series_view, waterfall_view)

NOW = timezone.now()
V = f"W{uuid.uuid4().hex[:6]}"  # vendor único por corrida


def _mk(vendor, amount, days_ago=1, status="Completed", category="Compras"):
    return Transaction.objects.create(
        transaction_id=f"V2-{uuid.uuid4().hex[:10]}", vendor=vendor,
        amount=amount, currency="BRL", timestamp=NOW - timedelta(days=days_ago),
        category=category, status=status, user_id="u1")


MEAS = {'op': 'agg', 'agg': 'sum', 'field': 'amount'}
COUNT = {'op': 'agg', 'agg': 'count', 'field': 'id'}


class SeriesTimeIntelligenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 3 meses com valores distintos
        for i, (amount, days) in enumerate([(100, 90), (200, 55), (300, 15)]):
            _mk(f"{V}-m{i}", amount, days_ago=days)

    def test_series_month_with_moving_avg_and_cumulative(self):
        r = series_view(MEAS, 'month')
        self.assertGreaterEqual(len(r['rows']), 1)
        tot = sum(row['value'] for row in r['rows'])
        self.assertAlmostEqual(r['rows'][-1]['cumulative'], tot, places=2)
        # média móvel do último ponto = média dos últimos ≤3 pontos
        vals = [row['value'] for row in r['rows']]
        self.assertAlmostEqual(r['rows'][-1]['moving_avg'],
                               sum(vals[-3:]) / len(vals[-3:]), places=2)

    def test_series_granularities(self):
        for g in ('day', 'week', 'month', 'quarter', 'year'):
            r = series_view(MEAS, g)
            self.assertIn('rows', r)
        with self.assertRaises(BIValidationError):
            series_view(MEAS, 'hora_inexistente')

    def test_series_week_dimension_and_filter(self):
        _mk(f"{V}-wk", 50, days_ago=2)
        r = series_view(MEAS, 'week')
        self.assertTrue(all('-S' in row['key'] for row in r['rows']))
        # filtro por semana (lexicográfico) não rebenta
        wk = r['rows'][-1]['key']
        from dashboard.bi_service import run_measure
        v, _ = run_measure(MEAS, [{'field': 'week', 'op': 'eq', 'value': wk}])
        self.assertGreaterEqual(v, 0)


class ForecastTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # tendência linear: 100, 200, 300, 400 por mês
        for i, amount in enumerate([100, 200, 300, 400]):
            _mk(f"F{i}-{V}", amount, days_ago=100 - i * 30)

    def test_forecast_projects_future_periods(self):
        r = forecast_view(MEAS, 'month', periods=3)
        self.assertEqual(len(r['forecast']), 3)
        self.assertGreater(r['slope'], 0)
        # próxima projeção ≈ 500 (tendência de +100/mês)
        self.assertAlmostEqual(r['forecast'][0]['value'], 500, delta=60)
        self.assertLessEqual(r['forecast'][0]['lower'], r['forecast'][0]['value'])
        self.assertGreaterEqual(r['forecast'][0]['upper'], r['forecast'][0]['value'])

    def test_forecast_insufficient_data(self):
        _mk(f"UNICO-{V}", 10, days_ago=1)
        r = forecast_view({'op': 'agg', 'agg': 'sum', 'field': 'amount'},
                          'year', periods=2)
        self.assertIn('note', r)


class AnomalyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i, amount in enumerate([100, 110, 95, 105, 1000]):  # 1000 = outlier
            _mk(f"A{i}-{V}", amount, days_ago=100 - i * 22)

    def test_anomaly_flags_outlier(self):
        r = anomaly_view(MEAS, 'month', z_threshold=1.5)
        self.assertEqual(r['n_anomalies'], 1)
        flagged = [row for row in r['rows'] if row['anomaly']]
        self.assertEqual(flagged[0]['anomaly_kind'], 'high')

    def test_anomaly_without_variance(self):
        r = anomaly_view({'op': 'agg', 'agg': 'count', 'field': 'id'}, 'week')
        self.assertEqual(r['n_anomalies'], 0)


class WaterfallFunnelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, amount in [('Alfa', 500), ('Beta', 300), ('Gama', 200)]:
            _mk(name, amount)

    def test_waterfall_cumulative(self):
        r = waterfall_view(MEAS, 'vendor')
        self.assertAlmostEqual(r['total'], 1000, places=2)
        cum = 0.0
        for row in r['rows']:
            self.assertAlmostEqual(row['base'], cum, places=2)
            cum += row['value']
            self.assertAlmostEqual(row['cumulative'], cum, places=2)

    def test_funnel_conversions(self):
        r = funnel_view(MEAS, 'vendor')
        self.assertEqual(r['rows'][0]['stage'], 1)
        self.assertAlmostEqual(r['rows'][0]['pct_of_first'], 1.0, places=4)
        self.assertAlmostEqual(r['rows'][1]['conv_prev'], 0.6, places=4)
        self.assertAlmostEqual(r['rows'][-1]['pct_of_first'], 0.4, places=4)

    def test_invalid_dimension(self):
        with self.assertRaises(BIValidationError):
            waterfall_view(MEAS, 'nao_existe')
        with self.assertRaises(BIValidationError):
            funnel_view(MEAS, 'nao_existe')


class ScatterKPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, amount in [('S1', 100), ('S2', 200), ('S3', 400), ('S4', 800)]:
            _mk(name, amount)

    def test_scatter_points_and_means(self):
        r = scatter_view(MEAS, COUNT, 'vendor')
        self.assertEqual(len(r['points']), 4)
        self.assertAlmostEqual(r['mean_x'], 375.0, places=1)
        self.assertEqual(r['correlation'] is None or -1 <= r['correlation'] <= 1, True)

    def test_kpi_with_target(self):
        r = kpi_view(MEAS, target=1000)
        self.assertAlmostEqual(r['value'], 1500, places=1)
        self.assertEqual(r['status'], 'on_track')
        self.assertAlmostEqual(r['pct_of_target'], 1.5, places=4)

    def test_kpi_status_critical(self):
        r = kpi_view({'op': 'calc', 'measure': MEAS,
                      'filters': [{'field': 'vendor', 'op': 'eq', 'value': 'S1'}]},
                     target=10_000)
        self.assertEqual(r['status'], 'critical')

    def test_kpi_trend_without_history(self):
        r = kpi_view({'op': 'calc', 'measure': MEAS,
                      'filters': [{'field': 'vendor', 'op': 'eq', 'value': 'S1'}]})
        self.assertIsNone(r['target'])


class BIVisualDispatcherEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("DispA", 100)
        _mk("DispB", 300)
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="adm@x.pt", role="admin")

    def _post(self, payload):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        return c.post("/django/api/bi/visual", payload, format="json")

    def test_visual_bar(self):
        r = self._post({'kind': 'bar', 'measure': MEAS, 'dimension': 'vendor',
                        'top_n': 5})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['data']['rows'])

    def test_visual_kpi_and_series(self):
        r = self._post({'kind': 'kpi', 'measure': MEAS, 'target': 100})
        self.assertEqual(r.data['data']['status'], 'on_track')
        r = self._post({'kind': 'series', 'measure': MEAS, 'granularity': 'month'})
        self.assertIn('rows', r.data['data'])

    def test_visual_rejects_invalid(self):
        r = self._post({'kind': 'tipo_invalido', 'measure': MEAS})
        self.assertEqual(r.status_code, 400)
        r = self._post({'kind': 'bar', 'measure': {'op': 'hack'}, 'dimension': 'vendor'})
        self.assertEqual(r.status_code, 400)
        r = self._post({'kind': 'bar', 'measure': MEAS, 'dimension': 'hack'})
        self.assertEqual(r.status_code, 400)
