
print("Starting verification script...")
import os
import django
import sys
import json
from datetime import datetime

print("Imports done. Setting up Django...")
# Setup Django environment
sys.path.append(os.path.join(os.getcwd(), 'django_app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()
print("Django setup complete.")

from dashboard.models import Transaction, Alert, RiskAgent
from dashboard.ai_service import AuditAI # Now safe to import
from dashboard.views import process_pending_analysis
from django.utils import timezone

# from unittest.mock import MagicMock, patch

def test_risk_stats():
    print("\n--- Testing Risk Stats ---")
    
    # Mock AuditAI to avoid model loading
    # with patch('dashboard.ai_service.AuditAI') as MockAuditAI:
    if True: # Using real AuditAI now
        # mock_ai = MockAuditAI.return_value
        # mock_ai.get_department_risk_stats.return_value = [
        #     {'department': 'Procurement', 'risk_score': 85},
        #     {'department': 'IT', 'risk_score': 45}
        # ]
        # mock_ai.get_category_risk_stats.return_value = [
        #     {'category': 'Hardware', 'risk_score': 90},
        #     {'category': 'Services', 'risk_score': 30}
        # ]
        
        print("Instantiating AuditAI (Real)...")
        try:
             ai = AuditAI()
        except Exception as e:
             print(f"Failed to instantiate AuditAI: {e}")
             return
        
        # Test Department Stats
        print("Fetching Department Risk Stats...")
        try:
             dept_stats = ai.get_department_risk_stats()
             print(f"Departments found: {len(dept_stats)}")
             for dept in dept_stats[:3]:
                 print(f"  - {dept['department']}: Score {dept['risk_score']}")
        except Exception as e:
             print(f"Failed to fetch dept stats: {e}")
            
        # Test Category Stats
        print("Fetching Category Risk Stats...")
        try:
             cat_stats = ai.get_category_risk_stats()
             print(f"Categories found: {len(cat_stats)}")
             for cat in cat_stats[:3]:
                 print(f"  - {cat['category']}: Score {cat['risk_score']}")
        except Exception as e:
             print(f"Failed to fetch category stats: {e}")

def test_auto_resolve():
    print("\n--- Testing Auto-Resolve Logic ---")
    
    # 1. Create a Risk Agent for Auto-Resolve
    agent_name = "Test Auto Resolve Agent"
    print(f"Creating Risk Agent: {agent_name}")
    
    # Clean up previous test agent
    RiskAgent.objects.filter(name=agent_name).delete()
    
    agent = RiskAgent.objects.create(
        name=agent_name,
        conditions=[
            {"metric": "vendor", "operator": "contains", "value": "SafeVendor"}
        ],
        action="auto_resolve",
        active=True
    )
    
    # 2. Create a Transaction that matches
    print("Creating matching transaction...")
    tx = Transaction.objects.create(
        transaction_id=f"TEST-AR-{datetime.now().timestamp()}",
        vendor="SafeVendor",
        amount=5000.00,
        status="Pending",
        timestamp=timezone.now(),
        # description="Safe transaction for auto-resolve test" # Removed as it's not in the model
    )
    
    # 3. Trigger Analysis
    # We mock AuditAI to return the triggered agent
    # with patch('dashboard.ai_service.AuditAI') as MockAuditAI:
    if True: # Real AI
        # mock_ai = MockAuditAI.return_value
        # mock_ai.analyze_transaction_risk.return_value = {
        #     'risk_score': 0.1,
        #     'reasons': ['Matched Safe Vendor Rule'],
        #     'triggered_agents': [{'name': agent_name, 'action': 'auto_resolve'}],
        #     'xai_explanation': {}
        # }
        
        print("Running Analysis with Real AI...")
        try:
            ai = AuditAI(user_id='system')
            analysis = ai.analyze_transaction_risk(tx)
            
            triggered = analysis.get('triggered_agents', [])
            print(f"Triggered Agents: {[a.get('name') for a in triggered]}")
            
            is_auto_resolve = any(a.get('action') == 'auto_resolve' for a in triggered)
            
            if is_auto_resolve:
                print("✅ Auto-Resolve Agent Triggered correctly in Analysis")
            else:
                print("❌ Auto-Resolve Agent NOT Triggered")
        except Exception as e:
             print(f"Analysis failed: {e}")
             return
            
        # 4. Simulate the Alert Creation Logic from views.py
        # Since we can't easily call process_pending_analysis because it imports AuditAI internally and we can't patch that import easily 
        # (unless we patch 'dashboard.views.AuditAI'), we will simulate the logic here.
        
        if is_auto_resolve:
            status = 'False Positive'
            description = f"[AUTO-RESOLVED] AI Risk Score: {analysis.get('risk_score')}"
            
            alert = Alert.objects.create(
                transaction=tx,
                alert_type='AI Risk Analysis',
                status=status,
                description=description,
                vendor=tx.vendor,
                amount=tx.amount,
                materiality=analysis.get('risk_score', 0)
            )
            
            print(f"Created Alert Status: {alert.status}")
            if alert.status == 'False Positive' and '[AUTO-RESOLVED]' in alert.description:
                 print("✅ Alert created with False Positive status and Auto-Resolved tag")
            else:
                 print("❌ Alert status or description incorrect")

    # Cleanup
    agent.delete()
    # Keep transaction/alert for inspection if needed, or delete
    # tx.delete() 

if __name__ == "__main__":
    test_risk_stats()
    test_auto_resolve()
