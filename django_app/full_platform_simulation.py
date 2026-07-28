
import os
import django
import random
import json
import sys
from datetime import datetime, timedelta

# Setup Django environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import RiskAgent, RiskAgentLog, Alert, Transaction, AuditCase, ApiToken
from dashboard.ai_service import AuditAI
from dashboard.views import auto_cluster_alerts
from rest_framework.test import APIRequestFactory, force_authenticate
from django.utils import timezone

def run_comprehensive_simulation():
    print("="*60)
    print("[INICIO] INICIANDO SIMULACAO COMPLETA DA PLATAFORMA DE AUDITORIA")
    print("="*60)
    
    print("   [DEBUG] Inicializando AuditAI...")
    service = AuditAI(user_id="admin")
    print("   [DEBUG] AuditAI inicializado.")
    
    # 1. Preparacao de Dados (Transacoes)
    print("\n[1/5] Gerando Dados de Transacoes Diversificados...")
    vendors = ["Global Tech Solutions", "Luxury Travel Agency", "Suspicious Vendor LLC", "Office Supplies Inc", "Cloud Services Pro"]
    
    # Limpar dados de teste anteriores
    print("   [DEBUG] Limpando dados antigos...")
    Transaction.objects.filter(vendor__in=vendors).delete()
    AuditCase.objects.all().delete()
    Alert.objects.all().delete()
    print("   [DEBUG] Dados limpos.")
    
    created_count = 0
    for i in range(15):
        print(f"   [DEBUG] Criando transacao {i+1}/15...")
        vendor = random.choice(vendors)
        amount = random.uniform(100, 15000)
        if vendor == "Suspicious Vendor LLC":
            amount = random.uniform(8000, 25000)
            
        try:
            tx = Transaction.objects.create(
                transaction_id=f"SIM_{random.randint(10000, 99999)}_{timezone.now().timestamp()}",
                vendor=vendor,
                amount=amount,
                timestamp=timezone.now() - timedelta(days=random.randint(0, 5)),
                status="Approved"
            )
            print(f"   [DEBUG] Transacao {i+1} criada com ID: {tx.id}")
        except Exception as tx_err:
            print(f"   [ERROR] Erro ao criar transacao {i+1}: {str(tx_err)}")
            
        created_count += 1
    print(f"   [OK] {created_count} transacoes geradas.")

    # 2. Configuracao de Agentes Especialistas
    print("\n[2/5] Ativando Agentes de IA Especialistas...")
    
    agents_config = [
        {
            "name": "FraudDetector_Pro",
            "specialization": "Detecao de Fraude",
            "conditions": [{"field": "amount", "operator": "gt", "value": 10000}],
            "action": "flag_alert_critical"
        },
        {
            "name": "ComplianceBot",
            "specialization": "Conformidade Regulatoria",
            "conditions": [{"field": "vendor", "operator": "contains", "value": "Suspicious"}],
            "action": "flag_alert_critical"
        }
    ]
    
    active_agents = []
    for cfg in agents_config:
        RiskAgent.objects.filter(name=cfg["name"]).delete()
        agent = RiskAgent.objects.create(
            name=cfg["name"],
            specialization=cfg["specialization"],
            persona="Auditor Senior",
            training_instructions="Analise rigorosa de padroes de risco.",
            conditions=cfg["conditions"],
            action=cfg["action"],
            active=True
        )
        active_agents.append(agent)
        print(f"   [AGENT] Agente '{cfg['name']}' ativado.")

    # 3. Execucao da Inteligencia e Geracao de Logs
    print("\n[3/5] Processando Inteligencia e Analisando Riscos...")
    start_date = timezone.now() - timedelta(days=7)
    
    for agent in active_agents:
        # Trigger agents on recent transactions
        txs = Transaction.objects.filter(timestamp__gte=start_date)
        for tx in txs:
            # Check conditions manually for simulation
            match = False
            for cond in agent.conditions:
                val = getattr(tx, cond['field'], None)
                if cond['operator'] == 'gt' and float(val) > float(cond['value']): match = True
                if cond['operator'] == 'contains' and str(cond['value']).lower() in str(val).lower(): match = True
            
            if match:
                service.trigger_agent_action(agent, tx)
                print(f"   [ACTION] {agent.name} disparou acao para {tx.vendor}")

    # 4. Smart Workflow: Auto-Clustering e Auto-Assignment
    print("\n[4/5] Executando Smart Workflow (Auto-Clustering)...")
    factory = APIRequestFactory()
    request = factory.post('/api/auto_cluster_alerts/')
    token, _ = ApiToken.objects.get_or_create(token="sim_token", user_id="admin", role="admin")
    force_authenticate(request, token=token)
    
    response = auto_cluster_alerts(request)
    if response.status_code == 200:
        cases_created = response.data.get('cases_created', 0)
        print(f"   [OK] Smart Workflow criou {cases_created} casos de auditoria.")
        
        # Verify auto-assignment
        for case_info in response.data.get('details', []):
            case = AuditCase.objects.get(id=case_info['id'])
            print(f"      [CASE] '{case.title}' -> Atribuido a: {case.assigned_to}")
            
            # Suggest steps
            print(f"      [DEBUG] Chamando suggest_investigation_steps para caso {case.id}...")
            steps = service.suggest_investigation_steps(case)
            print(f"      [AI STEPS] Sugestao: {steps[:50]}...")
            
            # Simulate resolution to test Institutional Memory
            print(f"      [DEBUG] Simulando resolucao do caso {case.id}...")
            case.status = 'Resolved'
            case.save()
            # Manually trigger memory add for simulation since we're not using the API view's perform_update here
            memory_text = f"Caso Resolvido: {case.title}. Prioridade: {case.priority}."
            print(f"      [DEBUG] Adicionando a memoria institucional...")
            service.mem_service.add(memory_text, user_id="admin", metadata={"type": "sim_resolution"})
            print(f"      [MEMORY] Caso {case.id} adicionado a memoria institucional.")

    # 5. Geracao do Relatorio Executivo Final
    print("\n[5/5] Consolidando Resultados no Resumo Executivo...")
    summary = service.generate_executive_summary()
    
    print("\n" + "="*60)
    print("RESULTADO DO RESUMO EXECUTIVO (IA)")
    print("="*60)
    print(f"Titulo: {summary['title']}")
    print(f"Nivel de Risco: {summary['risk_level']}")
    print("\nPrincipais Insights:")
    for insight in summary['insights']:
        print(f" - {insight}")
        
    print("\n" + "="*60)
    print("[OK] SIMULACAO COMPLETA CONCLUIDA")
    print("="*60)

if __name__ == "__main__":
    try:
        run_comprehensive_simulation()
    except Exception as e:
        print(f"ERRO CRITICO NA SIMULACAO: {str(e)}")
        import traceback
        traceback.print_exc()
