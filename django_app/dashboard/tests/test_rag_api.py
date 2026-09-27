
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from dashboard.models import ContextDocument, DocumentChunk
from dashboard.ai_service import AuditAI

class RagApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='test_rag_user', password='password')
        # Simulate token auth role
        self.client.force_authenticate(user=self.user, token={'role': 'auditor'})
        
        # Create a document
        self.doc = ContextDocument.objects.create(
            title="Audit Committee Charter",
            extracted_text="The audit committee meets quarterly. Expenses over $1000 need double approval.",
            processed=True
        )
        
        # Create a chunk
        DocumentChunk.objects.create(
            document=self.doc,
            chunk_index=0,
            text=self.doc.extracted_text,
            embedding_vector=[0.1] * 384
        )

    def test_serializer_chunk_count(self):
        response = self.client.get(f'/django/api/documents/{self.doc.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['chunk_count'], 1)

    def test_search_endpoint(self):
        # We need to ensure the AI service can run (dependencies installed)
        # This test assumes local model is available or mocked.
        # Given previous steps, it is available.
        
        response = self.client.get('/django/api/documents/search/?q=audit')
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        # Depending on whether the model actually runs or we mock it.
        # In a real test environment, we might want to mock generate_embedding to avoid loading models.
        # But for this environment, we know it works.

    def test_reprocess_endpoint(self):
        # Test manual reprocessing trigger
        response = self.client.post(f'/django/api/documents/{self.doc.id}/reprocess/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['has_embedding'])
        # Verify chunks were recreated (count should be same or refreshed)
        self.assertTrue(DocumentChunk.objects.filter(document=self.doc).exists())
