import os
import django
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Alert, Transaction, IntegrationSettings, ImmutableAuditLog
from django.utils import timezone

def test_signal_flow():
    print("Setting up test data...")
    
    # 1. Ensure Settings exist
    settings, _ = IntegrationSettings.objects.get_or_create(
        user_id=999,
        defaults={
            'auto_email_enabled': True,
            'email_digest_list': 'test@example.com'
        }
    )
    # Ensure it's enabled
    settings.auto_email_enabled = True
    settings.save()
    
    # 2. Create Transaction
    tx = Transaction.objects.create(
        transaction_id=f"TEST-TX-{int(time.time())}",
        vendor="Yellow Taxi Service",
        amount=150.00,
        timestamp=timezone.now(),
        status="Analyzed"
    )
    
    print(f"Created Transaction {tx.id}")
    
    # 3. Create Alert (Triggering Signal)
    # Condition: vendor contains 'taxi', 100 < materiality < 200
    print("Creating Alert to trigger signal...")
    alert = Alert.objects.create(
        transaction=tx,
        alert_type="Test Risk",
        severity="Low",
        status="New",
        vendor="Yellow Taxi Service",
        amount=150.00,
        materiality=150.0 # This matches 100 < 150 < 200
    )
    
    print(f"Created Alert {alert.id}")
    
    # 4. Verify ImmutableAuditLog
    print("Verifying Audit Log...")
    # Allow a brief moment for signal (synchronous, but good practice)
    
    log = ImmutableAuditLog.objects.filter(
        resource_id=str(alert.id),
        action_type='SEND_EMAIL_WARNING'
    ).first()
    
    if log:
        print("✅ SUCCESS: ImmutableAuditLog entry found!")
        print(f"   Action: {log.action_type}")
        print(f"   Hash: {log.current_hash}")
        print(f"   Details: {log.details}")
    else:
        print("❌ FAILURE: No Audit Log entry found. Signal might have failed.")
        
        # Debug: Check if any logs exist
        all_logs = ImmutableAuditLog.objects.all().order_by('-id')[:5]
        print("   Recent Logs:", [l.action_type for l in all_logs])

if __name__ == "__main__":
    test_signal_flow()
