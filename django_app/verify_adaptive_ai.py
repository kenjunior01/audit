
import os
import django
import sys
from django.utils import timezone
import time

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import RiskAgent, Transaction, Alert, AiFeedback
from dashboard.ai_service import AuditAI

def verify_adaptive_reputation():
    print("="*60)
    print("[INICIO] TESTE DE IA AUTO-ADAPTATIVA: SISTEMA DE REPUTACAO")
    print("="*60)
    
    ai = AuditAI(user_id="admin")
    
    # 1. Criar um Agente "Ruidoso" (Noisy Agent)
    agent_name = "Noisy_Detector"
    RiskAgent.objects.filter(name=agent_name).delete()
    
    agent = RiskAgent.objects.create(
        name=agent_name,
        specialization="General",
        conditions=[{"metric": "amount", "operator": ">", "value": "100"}], # Muito sensível
        action="notify_manager",
        active=True,
        reputation_score=1.0 # Reputação inicial neutra
    )
    print(f"[1] Agente '{agent_name}' criado com reputação {agent.reputation_score}")

    # 2. Criar uma transação que ativa o agente
    tx = Transaction.objects.create(
        transaction_id=f"ADAPT_{int(time.time())}",
        amount=500.00,
        vendor="Common Store",
        timestamp=timezone.now(),
        status="Pending"
    )
    
    # 3. Primeira Analise (Reputacao Neutra)
    print("\n[2] Primeira Analise (Reputacao Neutra 1.0):")
    sys.stdout.flush()
    try:
        analysis1 = ai.analyze_transaction_risk(tx)
        print(f"   Score de Risco: {analysis1['risk_score']:.2f}")
        for r in analysis1['reasons']:
            if "[Automation]" in r: print(f"   Motivo: {r}")
        sys.stdout.flush()
    except Exception as e:
        print(f"   [ERRO] Falha na analise 1: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

    # 4. Simular Feedback Negativo (False Positive)
    # Primeiro, precisamos de um alerta gerado por esse agente
    # Na verdade, a analise acima ja gera um log, mas vamos criar o alerta que o sistema esperaria
    alert = Alert.objects.create(
        transaction=tx,
        alert_type=f"Agent Finding: {agent_name}",
        severity='High',
        description="Deteccao ruidosa"
    )
    
    print(f"\n[3] Simulando Feedback do Usuario: 'Incorreto / Falso Positivo'...")
    sys.stdout.flush()
    ai.process_alert_feedback(alert.id, 'inaccurate', 'Este agente e muito sensivel.')
    
    # Recarregar agente
    agent.refresh_from_db()
    print(f"   Nova Reputacao do Agente: {agent.reputation_score:.2f}")
    
    # Verificar Log
    from dashboard.models import RiskAgentLog
    last_log = RiskAgentLog.objects.filter(agent=agent).first()
    if last_log:
        print(f"   [LOG] Achado: {last_log.finding_summary}")
        print(f"   [LOG] Score de Risco: {last_log.risk_score}")
        print(f"   [LOG] Acao Sugerida: {last_log.suggested_action}")
    
    sys.stdout.flush()

    # 5. Segunda Analise (Reputacao Reduzida)
    print("\n[4] Segunda Analise (Reputacao Reduzida):")
    sys.stdout.flush()
    analysis2 = ai.analyze_transaction_risk(tx)
    print(f"   Score de Risco: {analysis2['risk_score']:.2f}")
    for r in analysis2['reasons']:
        if "[Automation]" in r: print(f"   Motivo: {r}")
    sys.stdout.flush()
        
    # 6. Forcar Reputacao Critica para ver o "Skip"
    print("\n[5] Forcando Reputacao Critica (< 0.5) para desativacao automatica...")
    sys.stdout.flush()
    agent.reputation_score = 0.4
    agent.save()
    
    print(f"   Analisando novamente com reputacao {agent.reputation_score}...")
    sys.stdout.flush()
    analysis3 = ai.analyze_transaction_risk(tx)
    found_agent = False
    for r in analysis3['reasons']:
        if agent_name in r:
            found_agent = True
            print(f"   [ERRO] Agente ainda presente nos motivos!")
    
    if not found_agent:
        print(f"   [OK] Agente '{agent_name}' foi ignorado automaticamente por baixa reputacao.")
    sys.stdout.flush()

    # Cleanup
    # RiskAgent.objects.filter(name=agent_name).delete()
    # tx.delete()
    
    print("\n" + "="*60)
    print("[OK] TESTE DE ADAPTABILIDADE CONCLUIDO")
    print("="*60)
    sys.stdout.flush()

if __name__ == "__main__":
    verify_adaptive_reputation()
