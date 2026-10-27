"""Testes dos Alertas de Medidas BI (avaliação + notificações integradas)."""
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import ApiToken, MeasureAlert, Notification, Transaction
from dashboard.bi_views import evaluate_measure_alert

MEAS = {'op': 'agg', 'agg': 'sum', 'field': 'amount'}


def _mk(vendor, amount):
    return Transaction.objects.create(
        transaction_id=f"AL-{uuid.uuid4().hex[:10]}", vendor=vendor,
        amount=amount, currency="BRL", timestamp=timezone.now(),
        category="Compras", status="Completed", user_id="u1")


class AlertEvaluationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("AlA", 100)
        _mk("AlB", 900)
        cls.uid = "auditor.alert@x.pt"

    def test_breach_transition_notifies_once(self):
        a = MeasureAlert.objects.create(
            name=f"gt-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=500, created_by=self.uid)
        state, value, notified = evaluate_measure_alert(a)
        self.assertEqual(state, 'breach')
        self.assertAlmostEqual(value, 1000.0, places=2)
        self.assertTrue(notified)
        self.assertEqual(a.last_state, 'breach')
        self.assertEqual(a.breach_count, 1)
        self.assertTrue(Notification.objects.filter(
            recipient=self.uid, kind='bi.alert').exists())
        # 2ª avaliação: continua breach → sem nova notificação
        a.refresh_from_db()
        state, value, notified = evaluate_measure_alert(a)
        self.assertFalse(notified)
        self.assertEqual(a.breach_count, 2)
        self.assertEqual(Notification.objects.filter(
            recipient=self.uid, kind='bi.alert').count(), 1)

    def test_ok_state_no_notification(self):
        a = MeasureAlert.objects.create(
            name=f"gt-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=5000, created_by=self.uid)
        state, value, notified = evaluate_measure_alert(a)
        self.assertEqual(state, 'ok')
        self.assertFalse(notified)
        self.assertFalse(Notification.objects.filter(kind='bi.alert').exists())

    def test_lt_breach_when_below(self):
        a = MeasureAlert.objects.create(
            name=f"ltlow-{uuid.uuid4().hex[:6]}",
            measure={'op': 'calc', 'measure': MEAS,
                     'filters': [{'field': 'vendor', 'op': 'eq',
                                  'value': 'AlA'}]},
            comparator='lt', threshold=500, created_by=self.uid)
        state, value, notified = evaluate_measure_alert(a)
        self.assertEqual(state, 'breach')
        self.assertTrue(notified)

    def test_severity_critical_above_125pct(self):
        a = MeasureAlert.objects.create(
            name=f"crit-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=100, created_by=self.uid)
        evaluate_measure_alert(a)
        n = Notification.objects.get(kind='bi.alert', recipient=self.uid)
        self.assertEqual(n.severity, 'critical')


class AlertEndpointsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _mk("EpA", 100)
        cls.admin = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.admin, user_id="adm@x.pt", role="admin")
        cls.viewer = str(uuid.uuid4())
        ApiToken.objects.create(token=cls.viewer, user_id="v@x.pt", role="viewer")

    def test_crud_and_permissions(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.get("/django/api/bi/alerts")
        self.assertEqual(r.status_code, 200)
        r = c.post("/django/api/bi/alerts",
                   {"name": "X", "measure": MEAS, 'comparator': 'gt',
                    'threshold': 10}, format="json")
        self.assertEqual(r.status_code, 403)

        a = APIClient()
        a.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        r = a.post("/django/api/bi/alerts",
                   {"name": "Valor alto", "measure": MEAS,
                    "comparator": "gt", "threshold": 50,
                    "filters": [{"field": 'vendor', 'op': 'eq', 'value': 'EpA'}]},
                   format="json")
        self.assertEqual(r.status_code, 201)
        pk = r.data['id']
        r = a.patch(f"/django/api/bi/alerts/{pk}",
                    {"active": False, "threshold": 77}, format="json")
        self.assertEqual(r.data['threshold'], 77)
        r = a.post("/django/api/bi/alerts",
                   {"name": "Valor alto", "measure": MEAS,
                    'comparator': 'gt', 'threshold': 1}, format="json")
        self.assertEqual(r.status_code, 409)
        r = a.post("/django/api/bi/alerts",
                   {"name": "Sem comparator", "measure": MEAS}, format="json")
        self.assertEqual(r.status_code, 400)
        r = a.post("/django/api/bi/alerts",
                   {"name": "Medida má", "measure": {'op': 'zzz'},
                    'comparator': 'gt', 'threshold': 1}, format="json")
        self.assertEqual(r.status_code, 400)
        r = a.delete(f"/django/api/bi/alerts/{pk}")
        self.assertEqual(r.data['deleted'], pk)

    def test_run_all_active(self):
        a = APIClient()
        a.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin)
        MeasureAlert.objects.create(
            name=f"run-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=99999, created_by="adm@x.pt")
        MeasureAlert.objects.create(
            name=f"inativo-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=0, active=False, created_by="adm@x.pt")
        r = a.post("/django/api/bi/alerts/run", {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['evaluated'], 1)
        self.assertEqual(r.data['results'][0]['state'], 'ok')

    def test_run_viewer_forbidden(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.viewer)
        r = c.post("/django/api/bi/alerts/run", {}, format="json")
        self.assertEqual(r.status_code, 403)


class ScheduledAlertsTest(TestCase):
    """Alertas BI ao vivo — avaliação automática (task + management command)."""

    @classmethod
    def setUpTestData(cls):
        cls.uid = "sched.alert@x.pt"
        _mk("SchedA", 100)
        _mk("SchedB", 900)

    def test_task_evaluates_active_and_notifies_breach(self):
        from dashboard.tasks import run_bi_alerts
        a = MeasureAlert.objects.create(
            name=f"live-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=500, created_by=self.uid)
        MeasureAlert.objects.create(  # inativo → não entra na ronda
            name=f"off-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=0, active=False, created_by=self.uid)
        r = run_bi_alerts()
        self.assertTrue(r["ok"])
        self.assertEqual(r["evaluated"], 1)
        self.assertEqual(r["breaches"], 1)
        self.assertEqual(r["results"][0]["id"], a.id)
        self.assertEqual(r["results"][0]["state"], "breach")
        a.refresh_from_db()
        self.assertEqual(a.last_state, "breach")
        self.assertTrue(Notification.objects.filter(
            recipient=self.uid, kind='bi.alert').exists())

    def test_task_empty_base(self):
        from dashboard.tasks import run_bi_alerts
        r = run_bi_alerts()
        self.assertTrue(r["ok"])
        self.assertEqual(r["evaluated"], 0)
        self.assertEqual(r["breaches"], 0)
        self.assertIn("0 alerta(s)", r["message"])

    def test_task_survives_malformed_alert(self):
        from dashboard.tasks import run_bi_alerts
        MeasureAlert.objects.create(
            name=f"bad-{uuid.uuid4().hex[:6]}",
            measure={'op': 'agg', 'agg': 'sum', 'field': 'não_existe'},
            comparator='gt', threshold=0, created_by=self.uid)
        r = run_bi_alerts()
        self.assertTrue(r["ok"])
        self.assertEqual(r["results"][0]["state"], "error")

    def test_management_command_runs(self):
        from io import StringIO
        from django.core.management import call_command
        MeasureAlert.objects.create(
            name=f"cmd-{uuid.uuid4().hex[:6]}", measure=MEAS,
            comparator='gt', threshold=500, created_by=self.uid)
        out = StringIO()
        call_command("run_bi_alerts", stdout=out)
        self.assertIn("1 alerta(s) avaliado(s)", out.getvalue())
        self.assertIn("1 em violação", out.getvalue())
