"""
Testes do Copiloto Global v7 — ações com confirmação (agentic actions).

Cobre:
- detect_action(): intenções PT/EN com ID explícito; sem ID → None;
  perguntas comuns → None
- execute_action(): whitelist, validação de parâmetros/valores/papel,
  mudança de estado real (Alert/AuditCase), ImmutableAuditLog
- chat/chat_events: proposta de ação no payload final (nunca executa)
- POST /ai/copilot/act: admin OK, viewer 403, erros 400/404, auth
"""
from django.test import TestCase
from rest_framework.test import APIClient

from dashboard.models import (Alert, ApiToken, AuditCase,
                              ImmutableAuditLog)
from dashboard import copilot_actions as ca
from dashboard import copilot_service as cs

from .test_copilot import _alert, _case


class DetectActionTest(TestCase):
    def test_resolve_alert_pt(self):
        prop = ca.detect_action("resolve o alerta 42")
        self.assertEqual(prop["action"], "set_alert_status")
        self.assertEqual(prop["params"], {"alert_id": 42,
                                          "status": "Resolved"})
        self.assertIn("42", prop["label"])

    def test_false_positive_and_investigating(self):
        self.assertEqual(
            ca.detect_action("alerta 7 é falso positivo")["params"]["status"],
            "False Positive")
        self.assertEqual(
            ca.detect_action("marca o alerta 9 em investigação")
            ["params"]["status"], "Investigating")

    def test_case_status_and_priority(self):
        self.assertEqual(
            ca.detect_action("fecha o caso 3")["action"], "set_case_status")
        self.assertEqual(
            ca.detect_action("close case 5")["params"]["status"], "Closed")
        prop = ca.detect_action("define prioridade crítica do caso 5")
        self.assertEqual(prop["action"], "set_case_priority")
        self.assertEqual(prop["params"]["priority"], "Critical")
        self.assertEqual(
            ca.detect_action("caso 8 em progresso")["params"]["status"],
            "In Progress")

    def test_no_id_or_no_intent_returns_none(self):
        self.assertIsNone(ca.detect_action("resolve o alerta mais recente"))
        self.assertIsNone(ca.detect_action("fecha os casos em atraso"))
        self.assertIsNone(ca.detect_action("qual o total de transações?"))
        self.assertIsNone(ca.detect_action("resumo da plataforma"))
        self.assertIsNone(ca.detect_action(""))


class ExecuteActionTest(TestCase):
    def test_alert_status_change_and_audit(self):
        a = _alert("Alpha", 9000.0, severity="Critical", status="New")
        out = ca.execute_action("set_alert_status",
                                {"alert_id": a.id, "status": "Resolved"},
                                username="ana", role="admin")
        self.assertTrue(out["ok"])
        self.assertIn("Resolvido", out["summary"])
        a.refresh_from_db()
        self.assertEqual(a.status, "Resolved")
        self.assertTrue(ImmutableAuditLog.objects.filter(
            action_type="COPILOT_SET_ALERT_STATUS",
            resource_id=str(a.id), actor_id="ana").exists())

    def test_case_status_and_priority(self):
        c = _case("Caso X")
        out = ca.execute_action("set_case_status",
                                {"case_id": c.id, "status": "Closed"},
                                username="ana", role="auditor")
        self.assertTrue(out["ok"])
        out2 = ca.execute_action("set_case_priority",
                                 {"case_id": c.id, "priority": "High"},
                                 username="ana", role="auditor")
        self.assertTrue(out2["ok"])
        c.refresh_from_db()
        self.assertEqual(c.status, "Closed")
        self.assertEqual(c.priority, "High")

    def test_whitelist_and_validation(self):
        self.assertEqual(ca.execute_action("delete_everything", {},
                                           role="admin")["status_code"], 400)
        c = _case("Caso Y")
        out = ca.execute_action("set_case_status",
                                {"case_id": c.id, "status": "Banana"},
                                role="admin")
        self.assertEqual(out["status_code"], 400)
        out2 = ca.execute_action("set_case_status", {"case_id": c.id},
                                 role="admin")
        self.assertEqual(out2["status_code"], 400)
        self.assertIn("em falta", out2["error"])

    def test_viewer_role_forbidden(self):
        a = _alert("Beta", 100.0, status="New")
        out = ca.execute_action("set_alert_status",
                                {"alert_id": a.id, "status": "Resolved"},
                                username="v", role="viewer")
        self.assertEqual(out["status_code"], 403)

    def test_missing_object_404(self):
        out = ca.execute_action("set_alert_status",
                                {"alert_id": 999999, "status": "Resolved"},
                                username="ana", role="admin")
        self.assertEqual(out["status_code"], 404)


class ChatProposeTest(TestCase):
    def test_chat_proposes_but_does_not_execute(self):
        a = _alert("Gamma", 500.0, status="New")
        out = cs.chat(f"resolve o alerta {a.id}")
        self.assertIn("proposed_action", out)
        self.assertEqual(out["proposed_action"]["action"],
                         "set_alert_status")
        self.assertIn("Ação proposta", out["answer"])
        a.refresh_from_db()
        self.assertEqual(a.status, "New")  # NÃO executou — só propôs

    def test_chat_without_intent_has_no_proposal(self):
        out = cs.chat("resumo da plataforma")
        self.assertNotIn("proposed_action", out)

    def test_chat_events_final_proposes(self):
        a = _alert("Delta", 300.0, status="New")
        final = {}
        for ev in cs.chat_events(f"resolve o alerta {a.id}"):
            if ev.get("event") == "final":
                final = ev.get("data") or {}
        self.assertIn("proposed_action", final)
        self.assertEqual(final["proposed_action"]["params"]["alert_id"],
                         a.id)
        self.assertIn("Ação proposta", final["answer"])
        a.refresh_from_db()
        self.assertEqual(a.status, "New")


class ActRESTTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_token = "tok-act-admin"
        ApiToken.objects.create(token=self.admin_token,
                                user_id="act_admin", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_token)
        self.alert = _alert("Epsilon", 700.0, status="New")

    def test_act_ok(self):
        resp = self.client.post("/django/api/ai/copilot/act",
                                {"action": "set_alert_status",
                                 "params": {"alert_id": self.alert.id,
                                            "status": "Resolved"}},
                                format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "Resolved")

    def test_act_invalid_400(self):
        resp = self.client.post("/django/api/ai/copilot/act",
                                {"action": "hack_the_planet", "params": {}},
                                format="json")
        self.assertEqual(resp.status_code, 400)

    def test_act_viewer_403(self):
        viewer = "tok-act-viewer"
        ApiToken.objects.create(token=viewer, user_id="act_viewer",
                                role="viewer")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + viewer)
        resp = client.post("/django/api/ai/copilot/act",
                           {"action": "set_alert_status",
                            "params": {"alert_id": self.alert.id,
                                       "status": "Resolved"}},
                           format="json")
        self.assertEqual(resp.status_code, 403)

    def test_act_requires_auth(self):
        client = APIClient()
        resp = client.post("/django/api/ai/copilot/act", {}, format="json")
        self.assertIn(resp.status_code, [401, 403])
