import os
import django
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal

# Setup Django
import sys
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Transaction, Alert, AuditCase, RiskAgentLog
from dashboard.ai_service import AuditAI

def mass_ingest_transactions(count=50):
    print(f"--- Iniciando Ingestão em Massa de {count} Transações ---")
    
    vendors = ["Cloud Services Inc", "Global Logistics", "Office Supplies Co", "Tech Solutions", "Travel & Expense", "Marketing Group", "HR Consulting"]
    users = ["user_123", "user_456", "user_789", "admin_01", "auditor_02"]
    categories = ["IT", "Logistics", "Office", "Travel", "Marketing", "HR"]
    
    ai = AuditAI(user_id="mass_ingest_system")
    
    for i in range(count):
        txn_id = f"MASS_TXN_{int(time.time())}_{i}"
        amount = Decimal(random.uniform(10.0, 50000.0)).quantize(Decimal("0.00"))
        vendor = random.choice(vendors)
        user = random.choice(users)
        category = random.choice(categories)
        
        # Randomize date within last 30 days
        days_ago = random.randint(0, 30)
        timestamp = datetime.now() - timedelta(days=days_ago)
        
        print(f"[{i+1}/{count}] Criando transação {txn_id} - R$ {amount}...")
        
        txn = Transaction.objects.create(
            transaction_id=txn_id,
            amount=amount,
            vendor=vendor,
            user_id=user,
            category=category,
            timestamp=timestamp
        )
        
        # Analyze Risk
        print(f"    - Analisando risco para {txn_id}...")
        risk_data = ai.analyze_transaction_risk(txn)
        
        # Simulate some alerts based on risk
        if risk_data['risk_score'] > 0.4:
            print(f"    - Risco ALTO detectado ({risk_data['risk_score']}). Criando Alerta...")
            alert = Alert.objects.create(
                transaction=txn,
                alert_type="HIGH_RISK_DETECTED",
                description=f"Alerta automático: Risco de {int(risk_data['risk_score']*100)}% identificado pela IA.",
                severity="High" if risk_data['risk_score'] > 0.7 else "Medium",
                status="New"
            )
            
            # 10% chance of auto-creating a case for high risk
            if risk_data['risk_score'] > 0.7 or random.random() < 0.1:
                print(f"    - Criando Caso de Auditoria para {txn_id}...")
                case = AuditCase.objects.create(
                    title=f"Investigação: Risco Elevado em {vendor}",
                    description=f"Caso aberto automaticamente via ingestão em massa. Motivos: {', '.join(risk_data['reasons'])}",
                    status="New",
                    priority="Critical" if risk_data['risk_score'] > 0.8 else "High",
                    transaction_id=txn_id,
                    created_by="System_AI"
                )
                
                # Assign to random auditor
                case.assigned_to = random.choice(["Auditor_Alpha", "Auditor_Beta", "Auditor_Gamma"])
                case.save()
                
    print(f"--- Ingestão concluída! {count} transações processadas. ---")

if __name__ == "__main__":
    mass_ingest_transactions(100) # Teste de carga real com 100 transações simultâneas
