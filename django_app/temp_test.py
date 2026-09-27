import os
import django
from django.utils import timezone
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Transaction, AIGovernanceEvent
from dashboard.ai_service import AuditAI

print("Starting robust test...")
service = AuditAI(user_id='admin')
tx_id = f'ROBUST_TEST_{int(time.time())}'
tx = Transaction.objects.create(
    transaction_id=tx_id, 
    vendor='Robust Vendor', 
    amount=500.0, 
    timestamp=timezone.now()
)
print(f'Transaction created: {tx_id}')

initial_count = AIGovernanceEvent.objects.count()
print(f'Initial Gov Events: {initial_count}')

print('Analyzing risk...')
try:
    print("Calling analyze_transaction_risk...")
    result = service.analyze_transaction_risk(tx)
    print(f'Analysis complete. Score: {result["risk_score"]}')
    
    print("Testing suggest_investigation_steps...")
    from dashboard.models import AuditCase
    case = AuditCase.objects.create(
        title="Test Case for Gov",
        description="Gov logging test",
        transaction_id=tx.transaction_id
    )
    steps = service.suggest_investigation_steps(case)
    print("Steps generated.")
except Exception as e:
    print(f'Analysis failed: {e}')
    import traceback
    traceback.print_exc()

print("Fetching final count...")
final_count = AIGovernanceEvent.objects.count()
print(f'Final Gov Events: {final_count}')
print(f'Events added: {final_count - initial_count}')

if final_count > initial_count:
    last_event = AIGovernanceEvent.objects.last()
    print(f'Last Event: {last_event.event_type} - {last_event.status}')
