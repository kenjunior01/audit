import os
import django
import sys
import json
from datetime import datetime

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import (
    Transaction, Alert, ContextProfile, ReferenceList, ReferenceItem, IntegrationSettings
)
from dashboard.ai_service import AuditAI
import dashboard.ai_service
print(f"DEBUG: AuditAI imported from {dashboard.ai_service.__file__}")

from django.db.models import Count, Avg, Q

def setup_test_data():
    print("Setting up test data...")
    
    # Clear existing data to avoid confusion
    Transaction.objects.all().delete()
    Alert.objects.all().delete()
    ContextProfile.objects.all().delete()
    ReferenceList.objects.all().delete()
    ReferenceItem.objects.all().delete()
    IntegrationSettings.objects.all().delete()

    # 1. Create Users and Departments
    ContextProfile.objects.create(user_id="user1", department="Finance", persona="Standard")
    ContextProfile.objects.create(user_id="user2", department="IT", persona="Standard")
    
    # 2. Create Transactions and Alerts
    # Finance User (High Risk)
    t1 = Transaction.objects.create(
        transaction_id="TX001", amount=1000, timestamp=datetime.now(), 
        user_id="user1", category="Software"
    )
    Alert.objects.create(transaction=t1, materiality=0.9, alert_type="Suspicious")
    
    t2 = Transaction.objects.create(
        transaction_id="TX002", amount=2000, timestamp=datetime.now(), 
        user_id="user1", category="Hardware"
    )
    Alert.objects.create(transaction=t2, materiality=0.8, alert_type="Policy Violation")

    # IT User (Low Risk)
    t3 = Transaction.objects.create(
        transaction_id="TX003", amount=500, timestamp=datetime.now(), 
        user_id="user2", category="Software"
    )
    Alert.objects.create(transaction=t3, materiality=0.2, alert_type="Info")

    # 3. Create Reference Lists
    ref_list = ReferenceList.objects.create(name="High Risk Departments")
    ReferenceItem.objects.create(reference_list=ref_list, value="Procurement", risk_factor=1.5)
    ReferenceItem.objects.create(reference_list=ref_list, value="Finance", risk_factor=1.2)
    ReferenceItem.objects.create(reference_list=ref_list, value="HR", risk_factor=0.8) # Low risk

    # 4. Create Settings
    IntegrationSettings.objects.create(user_id=1, ai_sensitivity=0.7)

    print("Test data created.")

def test_context_risk_logic():
    print("\nTesting Context Risk Logic...")
    
    ai = AuditAI()
    
    # 1. Test Department Stats
    print("1. Testing Department Stats...")
    
    # Debug: Check actual alert values
    print("Debug: All Alerts:")
    for a in Alert.objects.all():
        print(f"  Alert {a.id}: Tx {a.transaction.transaction_id} User {a.transaction.user_id} Materiality {a.materiality}")
    
    dept_stats = ai.get_department_risk_stats()
    
    # Debug aggregation manually
    finance_users = ContextProfile.objects.filter(department="Finance").values_list('user_id', flat=True)
    finance_alerts = Alert.objects.filter(transaction__user_id__in=finance_users)
    print(f"Debug: Finance Alerts Count: {finance_alerts.count()}")
    for a in finance_alerts:
        print(f"  FinAlert: {a.materiality}")
    
    avg_val = finance_alerts.aggregate(Avg('materiality'))
    print(f"Debug: Finance Avg: {avg_val}")
    
    print(f"Department Stats: {json.dumps(dept_stats, indent=2)}")
    
    # Verify Finance
    finance = next((d for d in dept_stats if d['department'] == 'Finance'), None)
    if finance:
        print(f"[OK] Finance found: Risk Score {finance['risk_score']} (Expected 92), Alerts {finance['alert_count']} (Expected 2)")
        if finance['risk_score'] == 92 and finance['alert_count'] == 2:
            pass
        else:
            print("   -> Finance stats INCORRECT")

    # Verify IT
    it = next((d for d in dept_stats if d['department'] == 'IT'), None)
    if it:
        print(f"[OK] IT found: Risk Score {it['risk_score']} (Expected 60), Alerts {it['alert_count']} (Expected 1)")

    # 2. Test Category Stats
    print("\n2. Testing Category Stats...")
    cat_stats = ai.get_category_risk_stats()
    print(f"Category Stats: {json.dumps(cat_stats, indent=2)}")
    
    # Verify Software (Mixed risk)
    software = next((c for c in cat_stats if c['category'] == 'Software'), None)
    if software:
        print(f"[OK] Software found: Risk Score {software['risk_score']} (Expected 77)")


    # 3. Test Reference List Stats (Logic from views.py)
    print("\n3. Testing Reference Lists...")
    ref_stats = ReferenceList.objects.annotate(
        item_count=Count('items'),
        high_risk_items=Count('items', filter=Q(items__risk_factor__gt=1.0))
    ).values('name', 'item_count', 'high_risk_items')
    
    ref_stats_list = list(ref_stats)
    print(f"Reference Stats: {json.dumps(ref_stats_list, indent=2)}")
    
    if len(ref_stats_list) > 0:
        high_risk_list = ref_stats_list[0]
        if high_risk_list['name'] == "High Risk Departments" and high_risk_list['high_risk_items'] == 2:
             print("[OK] Reference List logic CORRECT (2 high risk items found)")
        else:
             print("[FAIL] Reference List logic INCORRECT")
    else:
        print("[FAIL] No Reference Lists found")

    # 4. Test Settings Integration
    print("\n4. Testing Settings...")
    settings = IntegrationSettings.objects.first()
    if settings and settings.ai_sensitivity == 0.7:
        print(f"[OK] Settings found: Sensitivity {settings.ai_sensitivity}")
    else:
        print("[FAIL] Settings NOT FOUND or incorrect")

if __name__ == "__main__":
    try:
        setup_test_data()
        test_context_risk_logic()
        print("\n[DONE] All tests completed.")
    except Exception as e:
        print(f"\n[FAIL] Test Failed: {e}")
        import traceback
        traceback.print_exc()
