
import os
import django
from django.conf import settings
from datetime import datetime
import json

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import RiskAgent, RiskAgentLog, Alert
from dashboard.ai_service import AuditAI

def verify_full_ecosystem():
    print("[START] Starting Full Ecosystem Verification...")
    
    # 1. Create a Test Agent
    print("\n[1] Creating Test Agent 'EcosystemValidator'...")
    agent_name = "EcosystemValidator"
    RiskAgent.objects.filter(name=agent_name).delete() # Cleanup
    
    agent = RiskAgent.objects.create(
        name=agent_name,
        specialization="Fraud Detection",
        persona="Rigorous Tester",
        training_instructions="strict mode",
        conditions=[{"field": "amount", "operator": "gt", "value": 5000}],
        action="notify_manager",
        active=True
    )
    print(f"   [OK] Agent Created: {agent.name} (ID: {agent.id})")

    # 2. Trigger Agent Run (Simulate Finding)
    print("\n[2] Triggering Agent Run...")
    service = AuditAI()
    
    # To ensure we get a finding, we might need some data.
    # The fraud logic checks: suspicious = Transaction.objects.filter...
    # If no transactions, no finding.
    # Let's create some dummy transactions if needed, OR just mock the finding directly via internal method if possible.
    # Actually, let's rely on the service to simulate.
    # But wait, if there are no transactions, it returns None.
    # Let's create a dummy transaction to ensure count > threshold (3 or 5).
    
    from dashboard.models import Transaction
    from django.utils import timezone
    
    # Create dummy transactions
    print("   Creating dummy transactions for detection...")
    for i in range(3):
        Transaction.objects.create(
            transaction_id=f"TX_TEST_{i}_{timezone.now().timestamp()}",
            vendor="Suspicious Vendor LLC",
            amount=10000.00,
            timestamp=timezone.now(),
            status="Approved"
        )
        
    from datetime import timedelta
    start_date = timezone.now() - timedelta(days=7)
    finding = service._simulate_agent_finding(agent, start_date)
    
    if finding:
        print(f"   [OK] Agent Output: {json.dumps(finding, indent=2)}")
    else:
        print("   [FAIL] Agent Output is None! (Check data or logic)")
        # Force a finding for verifying the rest of the pipeline if simulation failed
        # But we want to verify the ecosystem, so failure here is real failure.
        pass
    
    # 3. Verify RiskAgentLog
    print("\n[3] Verifying RiskAgentLog Persistence...")
    logs = RiskAgentLog.objects.filter(agent=agent).order_by('-timestamp')
    if logs.exists():
        log_entry = logs.first()
        print(f"   [OK] Log Found: ID {log_entry.id}")
        print(f"   [INFO] Content: {log_entry.finding_summary}")
        print(f"   [INFO] Score: {log_entry.risk_score}")
        print(f"   [INFO] Action: {log_entry.suggested_action}")
        
        if log_entry.risk_score > 0.8:
            print("   [OK] Risk Score indicates High Risk.")
        else:
            print(f"   [WARN] Risk Score {log_entry.risk_score} is not High (expected for Fraud).")
    else:
        print("   [FAIL] No RiskAgentLog found!")

    # 4. Verify Alert Creation (for High Risk)
    print("\n[4] Verifying Automatic Alert Creation...")
    # The service should auto-create an alert for high risk
    alerts = Alert.objects.filter(alert_type__contains=agent_name).order_by('-timestamp')
    if alerts.exists():
        alert = alerts.first()
        print(f"   [OK] Alert Found: {alert.description}")
        print(f"   [INFO] Severity: {alert.severity}")
    else:
        print("   [WARN] No specific Alert found.")

    # 5. Verify Executive Summary Inclusion
    print("\n[5] Verifying Executive Summary Integration...")
    # Generate summary
    summary = service.generate_executive_summary()
    # print(f"   [INFO] Generated Executive Summary: {json.dumps(summary, indent=2)}")
    
    # Check if our agent is mentioned
    agent_mentioned = False
    for agent_report in summary.get('agent_reports', []):
        if agent_report['agent'] == agent_name: # Key is 'agent' in finding_result
            agent_mentioned = True
            print(f"   [OK] Agent '{agent_name}' found in Executive Summary reports.")
            break
            
    if not agent_mentioned:
        print(f"   [FAIL] Agent '{agent_name}' NOT found in Executive Summary.")

    # 6. Cleanup
    print("\n[6] Cleanup...")
    RiskAgent.objects.filter(name=agent_name).delete()
    Transaction.objects.filter(vendor="Suspicious Vendor LLC").delete()
    print("   [OK] Cleanup complete.")

    print("\n[DONE] Verification Complete!")

if __name__ == "__main__":
    verify_full_ecosystem()
