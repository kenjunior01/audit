"""Testes do Q&A — Pergunte aos dados (parser determinístico PT/EN + endpoint)."""
import uuid
from datetime import date

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import ApiToken, Transaction
from dashboard.bi_qa_service import ask_question, parse_question
from dashboard.bi_service import BIValidationError

TODAY = date(2026, 10, 15)


class ParserTest(TestCase):
    def _spec(self, q):
        return parse_question(q, today=TODAY)

    def test_total_by_vendor(self):
        s = self._spec('Total por fornecedor')
        self.assertEqual(s['visual'], 'bar')
        self.assertEqual(s['dimension'], 'vendor')
        self.assertEqual(s['measure']['agg'], 'sum')
        self.assertEqual(s['measure']['field'], 'amount')

    def test_count_kpi(self):
        s = self._spec('quantas transações este mês?')
        self.assertEqual(s['measure']['agg'], 'count')
        self.assertEqual(s['visual'], 'kpi')
        self.assertIn({'field': 'month', 'op': 'eq',
                       'value': '2026-10'}, s['filters'])

    def test_trend_series_month(self):
        s = self._spec('tendência mensal do total')
        self.assertEqual(s['visual'], 'series')
        self.assertEqual(s['dimension'], 'month')

    def test_top_n_with_pct(self):
        s = self._spec('top 5 fornecedores por percentagem')
        self.assertEqual(s['top_n'], 5)
        self.assertEqual(s['mode'], 'pct_of_total')

    def test_running_total(self):
        s = self._spec('total acumulado por mês')
        self.assertEqual(s['mode'], 'running_total')

    def test_pareto_and_last_days(self):
        s = self._spec('pareto de fornecedores últimos 90 dias')
        self.assertEqual(s['visual'], 'pareto')
        f = next(f for f in s['filters'] if f['field'] == 'date')
        self.assertEqual(f['op'], 'gte')
        self.assertEqual(f['value'], '2026-07-17')  # 2026-10-15 − 90 dias

    def test_time_words(self):
        s = self._spec('total hoje')
        self.assertIn({'field': 'date', 'op': 'eq',
                       'value': '2026-10-15'}, s['filters'])
        s = self._spec('total do mês passado')
        self.assertIn({'field': 'month', 'op': 'eq',
                       'value': '2026-09'}, s['filters'])
        s = self._spec('total deste ano')
        self.assertIn({'field': 'date', 'op': 'gte',
                       'value': '2026-01-01'}, s['filters'])

    def test_vendor_filter_extraction(self):
        s = self._spec('total do fornecedor Acme no último trimestre')
        self.assertIn({'field': 'vendor', 'op': 'contains',
                       'value': 'Acme'}, s['filters'])

    def test_status_keyword(self):
        s = self._spec('total de transações pendentes')
        self.assertIn({'field': 'status', 'op': 'contains',
                       'value': 'Pending'}, s['filters'])

    def test_media(self):
        s = self._spec('média de valor por categoria')
        self.assertEqual(s['measure']['agg'], 'avg')
        self.assertEqual(s['dimension'], 'category')

    def test_title_and_confidence(self):
        s = self._spec('total por fornecedor')
        self.assertIn('fornecedor', s['title'].lower())
        self.assertGreaterEqual(s['confidence'], 0.5)
        self.assertLessEqual(s['confidence'], 0.95)


class AskQuestionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, amount in [("QAA", 100), ("QAB", 200)]:
            Transaction.objects.create(
                transaction_id=f"QA-{uuid.uuid4().hex[:10]}", vendor=name,
                amount=amount, currency="BRL",
                timestamp=timezone.now(),
                category="Compras", status="Completed", user_id="u1")

    def test_ask_executes_bar(self):
        r = ask_question('Total por fornecedor')
        self.assertEqual(r['kind'], 'bar')
        self.assertIn('rows', r['data'])
        self.assertIn('Interpretação', r['explain'])
        self.assertEqual(r['spec']['visual'], 'bar')

    def test_ask_kpi(self):
        r = ask_question('quantas transações?')
        self.assertEqual(r['kind'], 'kpi')
        self.assertGreaterEqual(r['data']['value'], 2)

    def test_ask_empty_raises(self):
        with self.assertRaises(BIValidationError):
            ask_question('   ')


class QAEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tok = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.tok, user_id="qa@x.pt", role="viewer")

    def test_endpoint(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.tok)
        r = c.post("/django/api/bi/qa",
                   {"question": "Total por fornecedor"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['kind'], 'bar')
        r = c.post("/django/api/bi/qa", {"question": ""}, format="json")
        self.assertEqual(r.status_code, 400)
