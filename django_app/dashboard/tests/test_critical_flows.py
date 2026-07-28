
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from dashboard.models import Alert, Transaction, ContextProfile, RegulatoryRule, ApiToken, ContextDocument
from django.core.files.uploadedfile import SimpleUploadedFile
import uuid
from django.utils import timezone

class CriticalFlowsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create Admin Token
        self.token_val = str(uuid.uuid4())
        self.token = ApiToken.objects.create(token=self.token_val, user_id="test_admin", role="admin")
        
        # Create Viewer Token
        self.viewer_token_val = str(uuid.uuid4())
        self.viewer_token = ApiToken.objects.create(token=self.viewer_token_val, user_id="test_viewer", role="viewer")
        
        # Setup Data
        self.tx = Transaction.objects.create(
            transaction_id="tx_test_001",
            amount=1500.00,
            vendor="TestVendor",
            timestamp=timezone.now(),
            category="Services",
            user_id="user_test"
        )
        
        self.alert = Alert.objects.create(
            transaction=self.tx,
            alert_type="Test Alert",
            materiality=0.9,
            vendor="TestVendor"
        )
        
        self.profile = ContextProfile.objects.create(
            user_id="user_test",
            persona="Standard Auditor",
            country="Brazil"
        )

    def authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    def test_alerts_endpoint(self):
        """Test if alerts endpoint returns 200 and correct structure (Fix verification)"""
        self.authenticate(self.token_val)
        # Using DefaultRouter, viewsets usually map to the root or prefix
        # Based on auditportal/urls.py, it is mapped to /django/api/
        # But in tests, if we test dashboard.urls directly or if we use client, we should use the full path.
        # However, usually tests use reverse or relative to root.
        # Let's try /django/api/alerts/
        response = self.client.get('/django/api/alerts/') 
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) > 0)
        # Check if category field is present (Fix verification)
        self.assertIn('category', response.data['results'][0])
        self.assertEqual(response.data['results'][0]['category'], "Services")

    def test_graph_endpoint(self):
        """Test if graph endpoint returns nodes and links"""
        self.authenticate(self.token_val)
        response = self.client.get('/django/api/context/graph')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('nodes', response.data)
        self.assertIn('links', response.data)
        # Should have at least the transaction node
        nodes = response.data['nodes']
        self.assertTrue(any(n['id'] == str(self.tx.id) for n in nodes))

    def test_upload_document(self):
        """Test document upload flow"""
        self.authenticate(self.token_val)
        
        file_content = b"dummy pdf content"
        file = SimpleUploadedFile("test_doc.pdf", file_content, content_type="application/pdf")
        
        data = {
            "file": file,
            "title": "Test Policy",
            "doc_type": "policy",
            "country": "Brazil"
        }
        
        response = self.client.post('/django/api/upload/document', data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify in DB
        self.assertTrue(ContextDocument.objects.filter(title="Test Policy").exists())
        doc = ContextDocument.objects.get(title="Test Policy")
        self.assertEqual(doc.country, "Brazil")

    def test_geo_risks(self):
        """Test Geo Risks endpoint"""
        self.authenticate(self.token_val)
        response = self.client.get('/django/api/context/geo_risks')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return list
        self.assertIsInstance(response.data, list)
        # Should have Brazil
        brazil_data = next((item for item in response.data if item['country'] == 'Brazil'), None)
        self.assertIsNotNone(brazil_data)

    def test_smart_suggestions(self):
        """Test AI Smart Suggestions endpoint"""
        self.authenticate(self.token_val)
        response = self.client.get('/django/api/ai/suggest_rules')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('suggestions', response.data)
        # Should have at least one suggestion (High Risk Vendor or High Value)
        self.assertTrue(len(response.data['suggestions']) > 0)

    def test_simulation(self):
        """Test Rule Simulation endpoint"""
        self.authenticate(self.token_val)
        # Create a condition that matches the setup transaction
        conditions = [
            {'metric': 'amount', 'operator': '>', 'value': '1000'}
        ]
        response = self.client.post('/django/api/ai/simulate', {'conditions': conditions}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('matches', response.data)
        self.assertTrue(response.data['count'] >= 1)
        self.assertEqual(response.data['matches'][0]['id'], self.tx.id)

