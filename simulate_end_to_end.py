
import os
import django
import sys
from django.utils import timezone
from datetime import timedelta

# Add django_app to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'django_app'))

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Transaction, ContextProfile, AuditCase, RiskAgent, Alert
from dashboard.ai_service import AuditAI

def print_header(title):
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def simulate_end_to_end():
    print_header("STARTING END-TO-END AUDIT SIMULATION")

    # 1. SETUP CONTEXT (The Client)
    print("\n[STEP 1] Setting up Client Context...")
    user_id = "sim_user_001"
    
    # Reset previous data for clean run
    Transaction.objects.filter(user_id=user_id).delete()
    AuditCase.objects.filter(created_by=user_id).delete()
    RiskAgent.objects.filter(name="Auto-Block High Value SaaS").delete()
    
    # Define Corporate Profile (SaaS + SME)
    profile, _ = ContextProfile.objects.update_or_create(
        user_id=user_id,
        defaults={
            'sector': 'SaaS',
            'org_structure': 'SME',
            'persona': 'Risk Manager',
            'base_currency': 'BRL'
        }
    )
    print(f" > Profile Configured: Sector={profile.sector}, Structure={profile.org_structure}")

    # 2. INJECT FRAUD (The Incident)
    print("\n[STEP 2] Injecting High-Risk Transaction...")
    # Pattern: High Value (>100k) + Anomalous Category for SaaS (Raw Materials)
    tx = Transaction.objects.create(
        transaction_id=f"TX-{timezone.now().strftime('%H%M%S')}",
        user_id=user_id,
        vendor="Industrial Supplies Corp",
        amount=150000.00,
        timestamp=timezone.now(),
        category="Raw Materials",
        status="Pending"
    )
    print(f" > Transaction Created: ID={tx.id}, Vendor={tx.vendor}, Amount=${tx.amount:,.2f}, Category={tx.category}")

    # 3. AI ANALYSIS (The Detection)
    print("\n[STEP 3] Running AI Risk Analysis (3-Layer Model)...")
    ai = AuditAI(user_id=user_id)
    analysis = ai.analyze_transaction_risk(tx)
    
    score = analysis['risk_score']
    reasons = analysis['reasons']
    
    print(f" > Risk Score: {int(score * 100)}% ({'CRITICAL' if score > 0.7 else 'HIGH' if score > 0.4 else 'LOW'})")
    print(" > Detected Risk Factors:")
    for r in reasons:
        print(f"   - {r}")

    # Verify XAI Logic
    xai = analysis.get('xai_explanation', {})
    print(f" > XAI Log Generated: {bool(xai)}")
    if xai:
        print(f"   - Layers: Personal={len(xai['feature_weights']['layer_1_personal'])}, "
              f"Corporate={len(xai['feature_weights']['layer_2_corporate'])}, "
              f"Global={len(xai['feature_weights']['layer_3_global'])}")

    # 4. INVESTIGATION (The Case)
    print("\n[STEP 4] Simulating User Investigation...")
    case = AuditCase.objects.create(
        title=f"Investigation: Suspicious {tx.vendor}",
        description=f"AI detected high risk ({int(score*100)}%). Analyzing anomaly.",
        transaction_id=tx.id,
        priority="High",
        status="In Progress",
        created_by=user_id
    )
    print(f" > Case #{case.id} Opened. Status: {case.status}")
    
    # 5. AUTOMATION (The Agent)
    print("\n[STEP 5] Creating Remediation Agent (Automation)...")
    # Simulate user asking: "Block all future Raw Materials > 100k"
    agent_name = "Auto-Block High Value SaaS"
    agent = RiskAgent.objects.create(
        name=agent_name,
        conditions=[
            {"metric": "amount", "operator": ">", "value": "100000"},
            {"metric": "category", "operator": "contains", "value": "Raw Materials"}
        ],
        action="flag_alert_critical", # Escalate to critical alert
        active=True
    )
    print(f" > Risk Agent Created: '{agent.name}'")
    print(f" > Logic: IF Amount > 100k AND Category contains 'Raw Materials' THEN Flag Critical")

    # 6. VERIFICATION (The Protection)
    print("\n[STEP 6] Verifying Protection (New Attack)...")
    # Create a new similar transaction
    tx2 = Transaction.objects.create(
        transaction_id=f"TX-{timezone.now().strftime('%H%M%S')}-2",
        user_id=user_id,
        vendor="Another Steel Co",
        amount=125000.00, # Still > 100k
        timestamp=timezone.now(),
        category="Raw Materials",
        status="Pending"
    )
    
    print(f" > New Transaction: ID={tx2.id}, Amount=${tx2.amount:,.2f}")
    
    # Analyze again - Agent should trigger
    analysis_2 = ai.analyze_transaction_risk(tx2)
    reasons_2 = analysis_2['reasons']
    
    agent_triggered = any("Triggered Risk Agents" in r for r in reasons_2)
    
    if agent_triggered:
        print(" > SUCCESS: Risk Agent Triggered! 🛡️")
        for r in reasons_2:
            if "Automation" in r:
                print(f"   - {r}")
    else:
        print(" > FAILURE: Agent did not trigger.")
        print(f"   - Reasons found: {reasons_2}")

    print_header("SIMULATION COMPLETE")

if __name__ == "__main__":
    simulate_end_to_end()
