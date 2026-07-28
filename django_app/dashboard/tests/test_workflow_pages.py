from rest_framework.test import APITestCase
from rest_framework import status
from dashboard.models import Transaction, AuditCase, RiskAgent, ApiToken
from django.utils import timezone
import uuid

class WorkflowPagesTest(APITestCase):
    def setUp(self):
        # Create Admin Token
        self.token_val = "test-token-admin"
        ApiToken.objects.create(token=self.token_val, user_id="admin_user", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token_val)
        
        # Setup data
        self.tx = Transaction.objects.create(
            transaction_id="tx_case_1",
            amount=5000.00,
            vendor="Test Vendor",
            timestamp=timezone.now()
        )

    def test_audit_case_lifecycle(self):
        """Test creating, updating, and retrieving audit cases"""
        # 1. Create Case
        data = {
            "title": "Investigate Vendor X",
            "priority": "High",
            "transaction_id": self.tx.id,
            "status": "Open",
            "description": "Suspicious activity detected"
        }
        # Note: using /django/api/ prefix as discovered earlier
        response = self.client.post('/django/api/cases/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        case_id = response.data['id']
        
        # 2. Retrieve List
        response = self.client.get('/django/api/cases/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) > 0)
        
        # 3. Update Status
        patch_data = {"status": "In Progress"}
        response = self.client.patch(f'/django/api/cases/{case_id}/', patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], "In Progress")

    def test_risk_agent_creation(self):
        """Test creating a risk automation rule (Risk Agent)"""
        data = {
            "name": "Freeze High Value",
            "conditions": [{"field": "amount", "op": "gt", "val": 10000}],
            "action": "freeze_payment",
            "is_active": True
        }
        response = self.client.post('/django/api/agents/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(RiskAgent.objects.filter(name="Freeze High Value").exists())

    def test_smart_suggestions_endpoint(self):
        """Test if the smart suggestions endpoint returns valid data"""
        response = self.client.get('/django/api/ai/suggest_rules')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('suggestions', response.data)
        self.assertTrue(len(response.data['suggestions']) > 0)
