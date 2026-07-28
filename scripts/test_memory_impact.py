
import os
import django
import sys
from unittest.mock import MagicMock

print("Starting test script...")

# Setup Django environment
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'django_app'))
    print(f"Added to path: {sys.path[-1]}")
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
    print("Configuring Django...")
    django.setup()
    print("Django configured.")
except Exception as e:
    print(f"Setup Error: {e}")
    sys.exit(1)

# Mock sentence_transformers to avoid heavy model load
sys.modules['sentence_transformers'] = MagicMock()
print("Mocked sentence_transformers.")

try:
    from dashboard.models import Transaction, ContextProfile
    # Import PersistentMemory before AuditAI to patch it
    from dashboard.ai_service import PersistentMemory
    print("Imports successful.")
except Exception as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_institutional_memory():
    print("--- Testing Institutional Memory Impact ---")

    # 1. Mock PersistentMemory BEFORE AuditAI init to avoid real DB connection
    mock_pm = MagicMock()
    # Mock search to return a "False Positive" memory
    mock_pm.search.return_value = [
        {'memory': 'User explicitly marked similar transactions from Test Vendor Inc as False Positive in the past.', 'score': 0.9}
    ]
    # Inject mock into singleton
    PersistentMemory._instance = mock_pm
    print("Injected Mock PersistentMemory.")

    from dashboard.ai_service import AuditAI

    # 2. Create a dummy transaction
    txn = Transaction(
        id=99999,
        vendor="Test Vendor Inc",
        amount=5000.00,
        category="Services",
        user_id="user123",
        status="Pending"
    )

    # 3. Analyze Risk
    ai = AuditAI(user_id="user123")
    
    # Mock build_user_context to avoid DB hits
    ai.build_user_context = MagicMock(return_value={
        'onboarding': {},
        'top_vendors': [],
        'sector': 'Other',
        'org_structure': 'Functional',
        'avg_transaction_val': 1000,
        'learning_progress': 50,
        'persona': 'Standard'
    })

    print("Running analysis...")
    # Ensure active_learning is True (it defaults to True in build_user_context usually, but here we mocked it)
    # The code checks IntegrationSettings for active_learning.
    # We should mock that too or ensure defaults work.
    # In ai_service.py: 
    # settings = IntegrationSettings.objects.filter(...)
    # active_learning = settings.active_learning if settings else True
    
    result = ai.analyze_transaction_risk(txn)
    
    # 4. Check Results
    reasons = result.get('reasons', [])
    score = result.get('risk_score', 0)
    
    print(f"Risk Score: {score}")
    print("Reasons:")
    found_memory_reason = False
    for r in reasons:
        print(f" - {r}")
        if "[Institutional Memory]" in r:
            found_memory_reason = True
            
    if found_memory_reason:
        print("\nSUCCESS: Institutional Memory impacted the analysis!")
    else:
        print("\nFAILURE: Institutional Memory did not impact analysis.")

if __name__ == "__main__":
    test_institutional_memory()
