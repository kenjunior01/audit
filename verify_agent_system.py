import os
import django
import sys
import json
from datetime import timedelta

# Setup Django Environment
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'django_app'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
    django.setup()
    print("Django setup successful")
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)

from dashboard.models import Transaction, Alert, RiskAgent, RiskAgentLog
from dashboard.ai_service import AuditAI
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from dashboard.views import trigger_agent_run
from django.contrib.auth.models import User

def verify_agent_system():
    print("Starting verification...")
    try:
        with open("verification_output.txt", "w", encoding="utf-8") as f:
            def log(msg):
                print(msg)
                f.write(str(msg) + "\n")
                
            log("--- Verifying Agent Ecosystem ---")
            
            # 1. Setup Data
            log("1. Setting up test data...")
            # Clean previous test data
            RiskAgent.objects.filter(name="Test Agent 007").delete()
            Transaction.objects.filter(vendor="Suspicious Vendor LLC").delete()
            Transaction.objects.filter(transaction_id="TX-SAFE-01").delete()
            
            # Create Agent
            agent = RiskAgent.objects.create(
                name="Test Agent 007",
                specialization="Fraud",
                training_instructions="Strict check for Suspicious Vendor LLC",
                conditions=[],
                action="notify_manager",
                active=True
            )
            log(f"   Created Agent: {agent.name}")
            
            # Create Transactions (One normal, one suspicious)
            Transaction.objects.create(
                transaction_id="TX-SAFE-01",
                vendor="Safe Corp",
                amount=100.0,
                timestamp=timezone.now()
            )
            
            # Create multiple suspicious transactions to trigger threshold
            for i in range(6):
                Transaction.objects.create(
                    transaction_id=f"TX-SUS-{i}",
                    vendor="Suspicious Vendor LLC",
                    amount=5000.0,
                    timestamp=timezone.now()
                )
            log("   Created Transactions")

            # 2. Test Simulation Logic (Internal Service)
            log("\n2. Testing AI Service Simulation...")
            ai = AuditAI(user_id="system")
            start_date = timezone.now() - timedelta(days=1)
            
            # Count alerts before
            alerts_before = Alert.objects.filter(alert_type__contains=agent.name).count()
            
            finding = ai._simulate_agent_finding(agent, start_date)
            
            if finding and finding['priority'] == 'High':
                log(f"   SUCCESS: Simulation found risk: {finding['message']}")
            else:
                log(f"   FAILURE: Simulation did not find risk. Result: {finding}")
                
            # Check Log creation
            log_count = RiskAgentLog.objects.filter(agent=agent).count()
            if log_count >= 1:
                log(f"   SUCCESS: RiskAgentLog created. Count: {log_count}")
            else:
                log("   FAILURE: No RiskAgentLog created for simulation.")
                
            # Check Automatic Alert creation for High Priority
            alerts_after = Alert.objects.filter(alert_type__contains=agent.name).count()
            if alerts_after > alerts_before:
                log(f"   SUCCESS: System Alert automatically created for High Priority finding. Total: {alerts_after}")
            else:
                log("   FAILURE: No System Alert created for High Priority finding.")

            # 3. Test Action Trigger Logic
            log("\n3. Testing Action Trigger...")
            # Temporarily change action to 'flag_alert_critical' to verify alert creation
            agent.action = 'flag_alert_critical'
            agent.save()
            
            tx = Transaction.objects.filter(vendor="Suspicious Vendor LLC").first()
            ai.trigger_agent_action(agent, tx)
            
            # Check Alert
            alert = Alert.objects.filter(transaction=tx, alert_type__contains=agent.name).first()
            if alert:
                log(f"   SUCCESS: Alert created by agent action: {alert.alert_type}")
            else:
                log("   FAILURE: No Alert created by agent action.")
                
            # Check Log for action
            action_logs = RiskAgentLog.objects.filter(agent=agent, finding_summary__contains="Flagged Critical").count()
            if action_logs >= 1:
                log(f"   SUCCESS: RiskAgentLog created for action. Count: {action_logs}")
            else:
                log("   FAILURE: No RiskAgentLog created for action.")

            # 4. Test API Endpoint (Manual Run)
            log("\n4. Testing API Endpoint (Manual Run)...")
            factory = APIRequestFactory()
            request = factory.post(f'/agents/{agent.id}/run')
            
            # Need a user for auth
            user, _ = User.objects.get_or_create(username='testadmin', defaults={'email': 'admin@test.com'})
            # Mock the token/auth object to satisfy IsAuditorOrAdmin permission
            force_authenticate(request, user=user, token={'role': 'admin'})
            
            response = trigger_agent_run(request, pk=agent.id)
            
            if response.status_code == 200:
                log("   SUCCESS: API call successful.")
                log(f"   Response: {json.dumps(response.data, indent=2)}")
                
                # Verify another log was added
                new_log_count = RiskAgentLog.objects.filter(agent=agent).count()
                log(f"   Total Logs for Agent: {new_log_count}")
            else:
                log(f"   FAILURE: API call failed. Status: {response.status_code}")
                log(response.data)

            # 5. Test Agent Logs List Endpoint
            log("\n5. Testing Agent Logs List Endpoint...")
            request_logs = factory.get(f'/api/agent-logs/?agent={agent.id}')
            force_authenticate(request_logs, user=user, token={'role': 'auditor'})
            
            # Use the ViewSet directly since we don't have the URL conf loaded in this script context easily
            # But wait, we imported urls in views.py context? No.
            # We can instantiate the ViewSet
            from dashboard.views import RiskAgentLogViewSet
            view = RiskAgentLogViewSet.as_view({'get': 'list'})
            response_logs = view(request_logs)
            
            if response_logs.status_code == 200:
                log("   SUCCESS: Logs endpoint returned 200 OK.")
                data = response_logs.data
                # Pagination results check
                results = data.get('results', data)
                if len(results) > 0:
                    log(f"   SUCCESS: Returned {len(results)} logs.")
                    log(f"   First Log Summary: {results[0].get('finding_summary')}")
                else:
                    log("   WARNING: Returned 0 logs (unexpected).")
            else:
                 log(f"   FAILURE: Logs endpoint failed. Status: {response_logs.status_code}")

            log("\n--- Verification Complete ---")
    except Exception as e:
        print(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_agent_system()
