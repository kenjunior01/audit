
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from rest_framework.test import APIClient
from dashboard.models import ExternalSystem, ReferenceList, ReferenceItem, ContextProfile, Transaction, Alert

def run_test():
    print("Starting Full Flow Test...")
    
    # 1. Create External System
    ext_system, created = ExternalSystem.objects.get_or_create(
        name="Test ERP System",
        defaults={'webhook_url': 'http://localhost:9999/webhook'} # Mock URL
    )
    print(f"External System: {ext_system.name} (API Key: {ext_system.api_key})")
    
    # 2. Create Reference Data (High Risk Department)
    ref_list, _ = ReferenceList.objects.get_or_create(name="Departamentos de Risco")
    
    # Create 'Compras' with high risk
    ReferenceItem.objects.update_or_create(
        reference_list=ref_list,
        value="Compras",
        defaults={'risk_factor': 3.0, 'code': 'DEPT_01'}
    )
    print("Created Reference: Department 'Compras' with Risk Factor 3.0")

    # 3. Create User Profile with High Risk Department
    user_id = "user_erp_test_01"
    ContextProfile.objects.update_or_create(
        user_id=user_id,
        defaults={'persona': 'Standard Auditor', 'department': 'Compras'}
    )
    print(f"Created ContextProfile for {user_id} in 'Compras' department")

    # 4. Simulate External Ingest
    # Clean up previous run
    Transaction.objects.filter(transaction_id="TX-TEST-FULL-01").delete()

    client = APIClient()
    payload = {
        "type": "transaction",
        "transaction_id": "TX-TEST-FULL-01",
        "vendor": "Safe Vendor Ltd", # Safe vendor, so risk comes from Dept
        "amount": 500.00,
        "currency": "BRL",
        "user_id": user_id,
        "category": "Office Supplies"
    }
    
    print("Sending Ingest Request...")
    response = client.post(
        '/django/api/api/external/ingest',
        data=json.dumps(payload),
        content_type='application/json',
        HTTP_X_API_KEY=ext_system.api_key
    )
    
    if response.status_code != 200:
        print(f"FAILED: {response.status_code} - {response.data}")
        return

    print(f"Response: {response.data}")
    
    # 5. Verify Results
    # Check Transaction
    tx = Transaction.objects.filter(transaction_id="TX-TEST-FULL-01").first()
    if not tx:
        print("FAILED: Transaction not created")
        return
    print(f"Transaction created: {tx.transaction_id}")

    # Check Alert
    alert = Alert.objects.filter(transaction=tx).first()
    if alert:
        print(f"Alert Created! Severity: {alert.severity}")
        print(f"Description: {alert.description}")
        
        # Verify Department Risk Logic
        if "User department 'Compras' is flagged" in alert.description:
            print("SUCCESS: Department risk factor correctly applied!")
        else:
            print("WARNING: Department risk reason missing from alert description.")
    else:
        print("FAILED: No alert created (Risk score might be too low?)")

if __name__ == "__main__":
    run_test()
