from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from dashboard.models import Transaction, Alert, AuditCase, RegulatoryRule, ApiToken

class InnovationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = ApiToken.objects.create(token="test-token-innovations", user_id="admin", role="admin")
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token-innovations')
        
        # Create Dummy Data
        self.tx = Transaction.objects.create(
            transaction_id="TX_INN_001",
            amount=5000.00,
            vendor="Global Tech Services",
            timestamp=timezone.now()
        )
        
        self.rule = RegulatoryRule.objects.create(
            country="Global",
            regulation="Anti-Bribery",
            alert_type="Corruption",
            description="Checks for bribery keywords",
            active=True
        )

    def test_analyze_regulation(self):
        # Test 1: Direct match
        url = reverse('analyze_regulation')
        data = {'text': "This payment seems like a bribe for the official."}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data['matches']) > 0)
        self.assertIn('Corruption', str(response.data['matches']))

        # Test 2: Transaction ID enrichment
        data = {'text': "Check compliance.", 'transaction_id': self.tx.id}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        # Should contain transaction details in analysis text (implicit check via response)
        self.assertIn("Analyzed", response.data['analysis'])

    def test_analyze_news(self):
        url = reverse('analyze_news')
        
        # Test Positive Sentiment Vendor
        data = {'vendor': "Tech Giant"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sentiment'], 'positive')
        
        # Test Negative Sentiment Vendor (Mock logic)
        data = {'vendor': "Global Services Inc"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sentiment'], 'negative')

    def test_audit_case_sla(self):
        # Create cases
        now = timezone.now()
        
        # 1. Normal active case
        AuditCase.objects.create(title="Normal", created_by="me", status="New")
        
        # 2. Overdue by Deadline
        AuditCase.objects.create(
            title="Deadline Missed", 
            created_by="me", 
            status="In Progress",
            deadline=now - timedelta(days=1)
        )
        
        # 3. Overdue by Time (Legacy logic: > 7 days)
        AuditCase.objects.create(
            title="Old Case", 
            created_by="me", 
            status="New",
            created_at=now - timedelta(days=8) # Note: created_at is auto_now_add, so we need to mock it or update it
        )
        
        # Hack to update created_at since it is auto_now_add
        c3 = AuditCase.objects.get(title="Old Case")
        c3.created_at = now - timedelta(days=8)
        c3.save()
        
        url = reverse('audit_dashboard_stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # We expect 2 overdue cases:
        # - Deadline Missed
        # - Old Case (if logic holds for null deadline)
        # Wait, Old Case has null deadline, so it falls back to 7 days rule.
        # Deadline Missed has deadline < now.
        
        self.assertEqual(response.data['overdue_cases'], 2)
