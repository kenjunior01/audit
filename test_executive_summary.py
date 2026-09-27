import os
import django
import sys
import json
# Setup Django Environment
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'django_app'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
    django.setup()
    print("Django setup successful")
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)

from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth.models import User
from dashboard.views import executive_summary
from dashboard.models import RiskAgent, RiskAgentLog, Alert, Transaction
from django.utils import timezone

def test_summary():
    print("--- Testing Executive Summary ---")
    
    # 1. Setup Data
    # Ensure we have some agents and logs
    agent, _ = RiskAgent.objects.get_or_create(
        name="Summary Tester",
        defaults={
            'specialization': 'Testing',
            'active': True,
            'conditions': [],
            'action': 'notify'
        }
    )
    
    RiskAgentLog.objects.create(
        agent=agent,
        timestamp=timezone.now(),
        scanned_count=100,
        finding_summary="Found critical issue in summary test",
        finding_details={"priority": "High", "message": "Test Message"}
    )
    
    # Ensure we have some alerts
    Alert.objects.create(
        alert_type="Test Alert",
        severity="High",
        materiality=0.9,
        status="New",
        description="Test High Risk Alert",
        timestamp=timezone.now()
    )
    
    # 2. Call Endpoint
    factory = APIRequestFactory()
    request = factory.get('/ai/executive-summary')
    
    user, _ = User.objects.get_or_create(username='summary_admin', defaults={'email': 'summary@test.com'})
    force_authenticate(request, user=user, token={'role': 'viewer'})
    
    response = executive_summary(request)
    
    if response.status_code == 200:
        print("SUCCESS: Executive Summary Retrieved")
        data = response.data
        print(f"Risk Score: {data.get('risk_score')}")
        print(f"Summary: {data.get('summary')}")
        
        agent_reports = data.get('agent_reports', [])
        print(f"Agent Reports: {len(agent_reports)}")
        if len(agent_reports) > 0:
            print(f"First Report: {agent_reports[0]}")
    else:
        print(f"FAILURE: Status {response.status_code}")
        print(response.data)

if __name__ == "__main__":
    test_summary()
