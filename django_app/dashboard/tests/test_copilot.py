"""
Testes do Copiloto Global da Plataforma (Omni Copilot).
Cobre: router de intenções PT/EN, extração de filtros, tools agénticas
sobre dados vivos (overview, alertas, transações, casos, SLA, agentes,
excel, benford, duplicados, forecast, perfil de fornecedor), whitelist
de ações, orquestrador chat() e endpoints /ai/copilot + briefing.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dashboard.models import (Alert, ApiToken, AuditCase, ExcelImportJob,
                              RiskAgent, Transaction)
from dashboard import copilot_service as cs


def _tx(tid, vendor, amount, days_ago=1, category="TI", status="Approved"):
    return Transaction.objects.create(
        transaction_id=tid, vendor=vendor, amount=amount, currency="EUR",
        timestamp=timezone.now() - timedelta(days=days_ago),
        category=category, status=status, user_id="u1")


def _alert(vendor, amount, severity="High", status="New",
           materiality=0.8, days_ago=0):
    return Alert.objects.create(
        vendor=vendor, amount=amount, severity=severity, status=status,
        materiality=materiality,
        timestamp=timezone.now() - timedelta(days=days_ago),
        alert_type="Threshold", description="teste")


def _case(title, status="New", priority="High", deadline_days=None):
    deadline = None
    if deadline_days is not None:
        deadline = timezone.now() + timedelta(days=deadline_days)
    return AuditCase.objects.create(
        title=title, status=status, priority=priority,
        created_by="tester", deadline=deadline)


class RouterTest(TestCase):
    def test_detect_tools_pt(self):
        self.assertEqual(cs.detect_tools("resumo da plataforma")[0], "overview")
        self.assertEqual(cs.detect_tools("alertas críticos de hoje")[0], "alerts")
        self.assertEqual(cs.detect_tools("top 10 transações por valor")[0],
                         "transactions")
        self.assertEqual(cs.detect_tools("casos fora do prazo")[0], "cases")
        self.assertEqual(cs.detect_tools("aplica a lei de benford")[0], "benford")
        self.assertEqual(cs.detect_tools("tem duplicados na base?")[0],
                         "duplicates")
        self.assertEqual(cs.detect_tools("previsão de risco")[0], "forecast")
        self.assertEqual(cs.detect_tools("como estão os agentes?")[0], "agents")
        self.assertEqual(cs.detect_tools("importações de excel")[0], "excel")

    def test_detect_tools_en(self):
        self.assertEqual(cs.detect_tools("critical alerts today")[0], "alerts")
        self.assertEqual(cs.detect_tools("open cases overdue")[0], "cases")
        self.assertEqual(cs.detect_tools("platform overview")[0], "overview")

    def test_detect_tools_help_explain_trends(self):
        # meta-suporte
        self.assertEqual(cs.detect_tools("o que sabes fazer?")[0], "help")
        self.assertEqual(cs.detect_tools("preciso de ajuda")[0], "help")
        self.assertEqual(cs.detect_tools("what can you do")[0], "help")
        # explicabilidade
        self.assertEqual(cs.detect_tools("explica o alerta 42")[0], "explain")
        self.assertEqual(cs.detect_tools("porque foi gerado este alerta")[0],
                         "explain")
        # tendências
        self.assertEqual(cs.detect_tools("compara esta semana com a semana "
                                         "passada")[0], "trends")
        self.assertEqual(cs.detect_tools("evolução dos alertas")[0], "trends")

    def test_page_hint_vague_question(self):
        # pergunta vaga + página → dica da página
        self.assertEqual(cs.detect_tools("e agora?", page="/sla"), ["sla"])
        self.assertEqual(cs.detect_tools("e agora?", page="/cases"), ["cases"])
        # pergunta explícita sobrepõe-se à página
        self.assertEqual(cs.detect_tools("resumo da plataforma",
                                         page="/sla"), ["overview"])

    def test_multi_intent(self):
        tools = cs.detect_tools("resumo dos alertas críticos e casos em atraso")
        self.assertIn("overview", tools)
        self.assertIn("alerts", tools)
        self.assertIn("cases", tools)
        self.assertLessEqual(len(tools), 4)

    def test_extract_filters(self):
        f = cs.extract_filters("mostra alertas críticos dos últimos 7 dias "
                               "top 5 maior que 10.000")
        self.assertEqual(f["severity"], "Critical")
        self.assertEqual(f["days"], 7)
        self.assertEqual(f["top_n"], 5)
        self.assertEqual(f["min_amount"], 10000.0)

        f2 = cs.extract_filters('perfil do fornecedor "Acme Corp"')
        self.assertEqual(f2["vendor"], "Acme Corp")

    def test_extract_filters_status(self):
        f = cs.extract_filters("alertas falsos positivos")
        self.assertEqual(f["alert_status"], "False Positive")
        f2 = cs.extract_filters("casos em progresso")
        self.assertEqual(f2["case_status"], "In Progress")

    def test_extract_filters_ids(self):
        f = cs.extract_filters("explica o alerta 42")
        self.assertEqual(f["alert_id"], 42)
        f2 = cs.extract_filters("detalha o caso 7")
        self.assertEqual(f2["case_id"], 7)
        f3 = cs.extract_filters("alert #1234 porque")
        self.assertEqual(f3["alert_id"], 1234)
        # sem IDs
        f4 = cs.extract_filters("resumo da plataforma")
        self.assertIsNone(f4["alert_id"])
        self.assertIsNone(f4["case_id"])

    def test_extract_filters_latest(self):
        f = cs.extract_filters("explica o alerta mais recente")
        self.assertTrue(f["latest_alert"])
        f2 = cs.extract_filters("explica o caso mais recente")
        self.assertTrue(f2["latest_case"])
        # ID explícito tem prioridade sobre «mais recente»
        f3 = cs.extract_filters("explica o alerta 42 mais recente")
        self.assertEqual(f3["alert_id"], 42)
        self.assertFalse(f3["latest_alert"])


class ToolsTest(TestCase):
    def setUp(self):
        _tx("TX-1", "Alpha", 1200.0, days_ago=2)
        _tx("TX-2", "Beta", 25000.0, days_ago=3, category="Admin")
        _tx("TX-3", "Alpha", 1200.0, days_ago=4)   # duplicado exato
        _alert("Alpha", 25000.0, severity="Critical", days_ago=0)
        _alert("Beta", 900.0, severity="Low", status="False Positive",
               days_ago=3)
        _case("Caso crítico", status="In Progress", priority="Critical",
              deadline_days=-2)                       # fora do prazo
        RiskAgent.objects.create(name="FraudBot", specialization="Fraud",
                                 conditions={"min_amount": 1000},
                                 action="create_case_high")

    def test_tool_overview(self):
        r = cs.tool_overview({})
        self.assertEqual(r["tool"], "overview")
        self.assertEqual(r["meta"]["tx_total"], 3)
        self.assertEqual(r["meta"]["cases_overdue"], 1)
        self.assertIn("Panorama", r["summary"])
        self.assertTrue(r["table"]["columns"])

    def test_tool_query_alerts(self):
        r = cs.tool_query_alerts({"severity": "Critical"})
        self.assertEqual(r["meta"]["total"], 1)
        self.assertIn("critical", cs.norm_q(r["summary"]))

    def test_tool_query_transactions_top(self):
        r = cs.tool_query_transactions({"top_n": 2})
        self.assertEqual(r["meta"]["total"], 3)
        self.assertEqual(r["table"]["rows"][0][1], "Beta")  # 25000 maior

    def test_tool_query_cases_overdue(self):
        r = cs.tool_query_cases({"overdue": True})
        self.assertEqual(r["meta"]["total"], 1)

    def test_tool_sla(self):
        r = cs.tool_sla_check({})
        self.assertEqual(r["meta"]["overdue_cases"], 1)
        self.assertTrue(any(i["tone"] == "danger" for i in r["insights"]))

    def test_tool_agents(self):
        r = cs.tool_agents_status({})
        self.assertEqual(r["meta"]["total"], 1)
        self.assertIn("FraudBot", r["summary"])

    def test_tool_duplicates(self):
        r = cs.tool_find_duplicates({})
        self.assertGreaterEqual(r["meta"]["exact_groups"], 1)

    def test_tool_forecast(self):
        r = cs.tool_risk_forecast({})
        self.assertIn("trend", r["meta"])
        self.assertEqual(r["table"]["total"], 14)   # 14 dias analisados

    def test_tool_vendor_profile(self):
        r = cs.tool_vendor_profile({"vendor": "Alpha"})
        self.assertEqual(r["meta"]["tx"], 2)
        self.assertIn("Alpha", r["summary"])

    def test_run_tools_never_raises(self):
        results = cs.run_tools(["overview", "benford", "inexistente"],
                               "pergunta qualquer")
        self.assertEqual(len(results), 2)


class ValidationTest(TestCase):
    def test_validate_actions_whitelist(self):
        clean = cs._validate_actions([
            {"label": "Alertas", "href": "/alerts"},
            {"label": "Mal", "href": "https://evil.com"},
            {"label": "Traversal", "href": "/../../admin"},
            {"label": "Rota desconhecida", "href": "/nao-existe"},
            {"label": "Casos", "href": "/cases?priority=Critical"},
        ], max_n=6)
        hrefs = [a["href"] for a in clean]
        self.assertIn("/alerts", hrefs)
        self.assertIn("/cases?priority=Critical", hrefs)
        self.assertEqual(len(clean), 2)

    def test_validate_insights(self):
        clean = cs._validate_insights([
            {"title": "Risco", "detail": "x", "tone": "danger"},
            {"title": "Inválido", "tone": "hack"},
            {"detail": "sem título"},
        ])
        self.assertEqual(len(clean), 2)
        self.assertEqual(clean[1]["tone"], "info")


class ChatOrchestratorTest(TestCase):
    def setUp(self):
        _tx("TX-1", "Alpha", 5000.0)
        _alert("Alpha", 5000.0, severity="Critical")

    def test_chat_rules_mode(self):
        r = cs.chat("resumo da plataforma")
        self.assertEqual(r["mode"], "rules")
        self.assertIn("overview", r["tools_used"])
        self.assertIn("Panorama", r["answer"])
        self.assertTrue(r["actions"])

    def test_chat_empty_question(self):
        r = cs.chat("   ")
        self.assertIn("pergunta", r["answer"].lower())

    def test_chat_latency_present(self):
        r = cs.chat("alertas críticos")
        self.assertIsInstance(r["latency_ms"], int)

    def test_chat_page_context(self):
        # pergunta vaga na página de SLA → responde sobre SLA
        r = cs.chat("e agora?", page="/sla")
        self.assertIn("sla", r["tools_used"])
        self.assertIn("SLA", r["answer"])
        # sem página → fallback overview
        r2 = cs.chat("e agora?")
        self.assertIn("overview", r2["tools_used"])

    def test_chat_help_and_explain_flow(self):
        r = cs.chat("o que sabes fazer?")
        self.assertIn("help", r["tools_used"])
        self.assertIn("Copiloto", r["answer"])
        r2 = cs.chat("explica o alerta mais recente")
        self.assertIn("explain", r2["tools_used"])
        self.assertIn("Alerta #", r2["answer"])


class ExplicabilidadeTest(TestCase):
    """tool_explain — o coração do suporte de classe mundial."""

    def _alert_with_tx(self):
        tx = _tx("TX-EXP-1", "Gamma", 30000.0, days_ago=0, status="Approved")
        tx.xai_explanation = {"reasons": ["valor 4x acima da média",
                                          "fornecedor novo"]}
        tx.save(update_fields=["xai_explanation"])
        alert = Alert.objects.create(
            vendor="Gamma", amount=30000.0, severity="Critical",
            status="New", materiality=0.9,
            timestamp=timezone.now(), alert_type="Threshold",
            description="valor fora do padrão", transaction=tx)
        return alert, tx

    def test_explain_alert_by_id(self):
        alert, tx = self._alert_with_tx()
        r = cs.tool_explain({"alert_id": alert.id})
        self.assertEqual(r["meta"]["alert_id"], alert.id)
        self.assertIn("TX-EXP-1", r["summary"])
        self.assertIn("Critical", r["summary"])
        # fatores de risco XAI aparecem
        self.assertIn("4x acima da média", r["summary"])
        # próximos passos recomendados
        self.assertTrue(any("Próximos passos" in i["title"]
                            for i in r["insights"]))
        # tabela da transação associada
        self.assertEqual(r["table"]["rows"][0][0], "TX-EXP-1")

    def test_explain_latest_alert(self):
        alert, _ = self._alert_with_tx()
        r = cs.tool_explain({"latest_alert": True})
        self.assertEqual(r["meta"]["alert_id"], alert.id)

    def test_explain_alert_not_found(self):
        r = cs.tool_explain({"alert_id": 987654})
        self.assertFalse(r["meta"]["found"])
        self.assertIn("Não encontrei", r["summary"])

    def test_explain_without_id_is_guidance(self):
        r = cs.tool_explain({})
        self.assertIn("explica", r["summary"])
        self.assertEqual(r["insights"], [])

    def test_explain_case_overdue(self):
        case = _case("Auditoria Gamma", status="In Progress",
                     priority="High", deadline_days=-3)
        r = cs.tool_explain({"case_id": case.id})
        self.assertEqual(r["meta"]["case_id"], case.id)
        self.assertIn("FORA DO PRAZO", r["summary"])
        self.assertTrue(any(i["tone"] == "danger" for i in r["insights"]))
        # sem responsável atribuído → insight warn
        self.assertTrue(any("responsável" in i["title"].lower()
                            for i in r["insights"]))

    def test_explain_case_not_found(self):
        r = cs.tool_explain({"case_id": 987654})
        self.assertFalse(r["meta"]["found"])

    def test_explain_vendor_pattern_insight(self):
        # 4 alertas do mesmo fornecedor → insight de padrão recorrente
        self._alert_with_tx()
        Alert.objects.create(vendor="Gamma", amount=100.0,
                             severity="High", status="New",
                             materiality=0.5, timestamp=timezone.now(),
                             alert_type="Threshold", description="x")
        Alert.objects.create(vendor="Gamma", amount=200.0,
                             severity="High", status="New",
                             materiality=0.5, timestamp=timezone.now(),
                             alert_type="Threshold", description="x")
        Alert.objects.create(vendor="Gamma", amount=300.0,
                             severity="Medium", status="New",
                             materiality=0.5, timestamp=timezone.now(),
                             alert_type="Threshold", description="x")
        r = cs.tool_explain({"latest_alert": True})
        self.assertTrue(any("Padrão recorrente" in i["title"]
                            for i in r["insights"]))


class TrendsTest(TestCase):
    def setUp(self):
        # Alert.timestamp é auto_now_add → criamos e retrodatamos via
        # queryset.update() (que contorna o auto_now_add) para simular
        # distribuição temporal real entre as duas semanas.
        def _backdated_alert(vendor, amount, days_ago, **kw):
            a = _alert(vendor, amount, **kw)
            Alert.objects.filter(id=a.id).update(
                timestamp=timezone.now() - timedelta(days=days_ago))
            return a

        # semana atual: 5 alertas / 3 transações; semana passada: 2 / 1
        for i in range(5):
            _backdated_alert(f"V{i}", 100.0 + i, days_ago=i)
        for i in range(2):
            _backdated_alert("Old", 50.0, days_ago=8 + i)
        _tx("TX-A", "Alpha", 1000.0, days_ago=1)
        _tx("TX-B", "Beta", 2000.0, days_ago=2)
        _tx("TX-C", "Alpha", 3000.0, days_ago=3)
        _tx("TX-D", "Old", 500.0, days_ago=10)

    def test_tool_trends_counts(self):
        r = cs.tool_trends({})
        self.assertEqual(r["meta"]["alerts_this"], 5)
        self.assertEqual(r["meta"]["alerts_prev"], 2)
        self.assertEqual(r["meta"]["tx_this"], 3)
        self.assertEqual(r["meta"]["tx_prev"], 1)
        # série diária com 14 linhas
        self.assertEqual(r["table"]["total"], 14)

    def test_tool_trends_acceleration_insight(self):
        r = cs.tool_trends({})
        # 5 vs 2 = +150% → insight de aceleração
        self.assertTrue(any("aceleração" in i["title"].lower()
                            for i in r["insights"]))
        self.assertIn("+", r["summary"])  # delta positivo visível

    def test_tool_trends_quiet_week(self):
        # inverte: poucos alertas agora, muitos antes
        Alert.objects.all().delete()
        for i in range(6):
            a = _alert("P", 10.0, days_ago=8 + i)
            Alert.objects.filter(id=a.id).update(
                timestamp=timezone.now() - timedelta(days=8 + i))
        r = cs.tool_trends({})
        self.assertTrue(any("queda" in i["title"].lower()
                            for i in r["insights"]))


class CopilotRESTTest(TestCase):
    def setUp(self):
        self.token = "tok-omni-1"
        ApiToken.objects.create(token=self.token, user_id="test_admin",
                                role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        _tx("TX-1", "Alpha", 8000.0)
        _alert("Alpha", 8000.0, severity="Critical")
        _case("Caso A", deadline_days=5)

    def test_chat_endpoint(self):
        resp = self.client.post("/django/api/ai/copilot",
                                {"question": "resumo da plataforma",
                                 "history": []}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("answer", data)
        self.assertIn("tools_used", data)
        self.assertIn("actions", data)
        self.assertIn("followups", data)

    def test_chat_endpoint_with_page_context(self):
        resp = self.client.post("/django/api/ai/copilot",
                                {"question": "e agora?", "page": "/sla"},
                                format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("sla", resp.json()["tools_used"])

    def test_chat_endpoint_help(self):
        resp = self.client.post("/django/api/ai/copilot",
                                {"question": "o que sabes fazer?"},
                                format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("help", data["tools_used"])
        self.assertIn("Copiloto", data["answer"])

    def test_chat_endpoint_requires_question(self):
        resp = self.client.post("/django/api/ai/copilot", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_chat_endpoint_requires_auth(self):
        client = APIClient()
        resp = client.post("/django/api/ai/copilot", {"question": "x"},
                           format="json")
        self.assertIn(resp.status_code, [401, 403])

    def test_briefing_endpoint(self):
        resp = self.client.get("/django/api/ai/copilot/briefing")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("briefing_md", data)
        self.assertIn("kpis", data)
        self.assertEqual(data["kpis"]["transactions_total"], 1)

    def test_viewer_can_chat(self):
        token = "tok-view-1"
        ApiToken.objects.create(token=token, user_id="test_viewer",
                                role="viewer")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        resp = client.post("/django/api/ai/copilot",
                           {"question": "quais os casos abertos?"},
                           format="json")
        self.assertEqual(resp.status_code, 200)


class ExcelJobToolTest(TestCase):
    def test_tool_excel_imports(self):
        ExcelImportJob.objects.create(file_name="contas.xlsx",
                                      rows_imported=120, rows_skipped=3,
                                      status="Completed")
        r = cs.tool_excel_imports({})
        self.assertEqual(r["meta"]["total"], 1)
        self.assertIn("contas.xlsx", str(r["table"]["rows"]))
