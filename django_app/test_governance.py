
import os
import django
import sys

# Setup Django environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Transaction, AIGovernanceEvent
from dashboard.ai_service import AuditAI
from django.utils import timezone

def test_governance_logging():
    print("Iniciando teste de log de governança...")
    service = AuditAI(user_id="admin")
    
    # Criar uma transação de teste
    tx = Transaction.objects.create(
        transaction_id=f"GOV_TEST_{timezone.now().timestamp()}",
        vendor="Governance Test Vendor",
        amount=1500.0,
        timestamp=timezone.now()
    )
    
    print(f"Transação de teste criada: {tx.transaction_id}")
    
    # Analisar risco (deve disparar log de governança)
    print("Analisando risco...")
    result = service.analyze_transaction_risk(tx)
    print(f"Risco calculado: {result['risk_score']}")
    
    # Verificar se o log foi criado
    count = AIGovernanceEvent.objects.count()
    print(f"Total de eventos de governança: {count}")
    
    if count > 0:
        event = AIGovernanceEvent.objects.last()
        print(f"Último evento: {event.event_type} - {event.status}")
        print(f"Modelo: {event.model_name}")
    else:
        print("ERRO: Nenhum evento de governança foi registrado!")

if __name__ == "__main__":
    test_governance_logging()
