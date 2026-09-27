
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import RiskAgent, Transaction, AuditCase, Alert
from dashboard.ai_service import AuditAI
from django.utils import timezone
import json

def test_risk_agent_automation():
    print("--- Testing Risk Agent Automation ---")
    
    # 1. Clean up previous test data
    RiskAgent.objects.filter(name="Test High Value Agent").delete()
    Transaction.objects.filter(transaction_id="TX_TEST_AGENT_001").delete()
    AuditCase.objects.filter(title="Auto-Case: Test High Value Agent").delete()
    
    # 2. Create a Risk Agent
    # Condition: Amount > 10000 AND Category contains 'Consulting'
    conditions = [
        {"metric": "amount", "operator": ">", "value": "10000"},
        {"metric": "category", "operator": "contains", "value": "consulting"}
    ]
    
    agent = RiskAgent.objects.create(
        name="Test High Value Agent",
        conditions=conditions,
        action="create_case_high",
        active=True
    )
    print(f"Created Risk Agent: {agent.name}")

    # 3. Create a matching Transaction
    tx = Transaction.objects.create(
        transaction_id="TX_TEST_AGENT_001",
        timestamp=timezone.now(),
        amount=15000.00,
        vendor="Test Corp",
        category="Management Consulting",
        status="Pending"
    )
    print(f"Created Transaction: {tx.transaction_id} (Amount: {tx.amount}, Category: {tx.category})")

    # 4. Run Analysis
    ai = AuditAI()
    print("Running analyze_transaction_risk...")
    analysis = ai.analyze_transaction_risk(tx)
    
    print(f"Risk Score: {analysis['risk_score']}")
    print("Reasons:", json.dumps(analysis['reasons'], indent=2))

    # 5. Verify Action (Case Creation)
    try:
        case = AuditCase.objects.get(title="Auto-Case: Test High Value Agent", transaction_id=tx.id)
        print(f"SUCCESS: Audit Case created! ID: {case.id}, Priority: {case.priority}")
    except AuditCase.DoesNotExist:
        print("FAILURE: Audit Case was NOT created.")
        
    # 6. Check Agent stats
    agent.refresh_from_db()
    print(f"Agent Last Triggered: {agent.last_triggered}")

if __name__ == '__main__':
    test_risk_agent_automation()
