
import os
import django
from django.core.files.uploadedfile import SimpleUploadedFile

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auditportal.settings")
django.setup()

from rest_framework.test import APIRequestFactory
from rest_framework.response import Response
from dashboard.models import Transaction, AuditCase, ContextDocument, ApiToken
from dashboard.views import upload_document, case_report, execute_ai_action, audit_chat

def test_backend():
    print("--- Starting Backend Verification ---")
    factory = APIRequestFactory()
    
    # Setup Auth Token
    token_str = "test_token_123"
    ApiToken.objects.update_or_create(
        token=token_str,
        defaults={'user_id': 'user_123', 'role': 'admin'}
    )
    auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token_str}'}
    
    # 1. Setup Data
    tx, _ = Transaction.objects.get_or_create(
        transaction_id="TX_TEST_001",
        defaults={
            "amount": 5000.00,
            "vendor": "Test Vendor",
            "timestamp": "2023-01-01T12:00:00Z",
            "user_id": "user_123"
        }
    )
    print(f"Transaction created/fetched: {tx.id}")

    # 2. Test Document Upload with Transaction ID
    print("\nTesting Document Upload...")
    file_content = b"dummy content"
    file = SimpleUploadedFile("test_doc.txt", file_content, content_type="text/plain")
    
    request = factory.post('/upload/document', {
        'file': file,
        'title': 'Test PBC',
        'doc_type': 'PBC',
        'transaction_id': str(tx.transaction_id) # Using string ID as per model
    }, format='multipart', **auth_header)
    
    response = upload_document(request)
    if response.status_code == 200:
        doc_id = response.data['id']
        doc = ContextDocument.objects.get(id=doc_id)
        print(f"SUCCESS: Document uploaded. ID: {doc.id}, Linked Transaction: {doc.transaction_id}")
    else:
        print(f"FAILURE: Upload failed. {response.data}")

    # 3. Test Case Report
    print("\nTesting Case Report...")
    case = AuditCase.objects.create(
        title="Test Case",
        description="Investigation of suspicious activity",
        transaction_id=str(tx.id),
        created_by="system"
    )
    
    request = factory.get(f'/cases/{case.id}/report', **auth_header)
    
    response = case_report(request, pk=case.id)
    if response.status_code == 200:
        print(f"SUCCESS: Report generated for Case #{case.id}")
        # print(response.data.keys())
    else:
        print(f"FAILURE: Report generation failed. {response.status_code}")

    # 4. Test Audit Chat
    print("\nTesting Audit Chat...")
    request = factory.post('/ai/chat', {'query': 'Resumo de hoje'}, format='json', **auth_header)
    response = audit_chat(request)
    if response.status_code == 200:
        print(f"SUCCESS: Chat response: {response.data.get('content')[:50]}...")
    else:
        print(f"FAILURE: Chat failed.")

    # 5. Test Execute Action
    print("\nTesting Execute Action...")
    request = factory.post('/ai/action', {
        'action_id': 'test_action',
        'action_type': 'adjust_sensitivity'
    }, format='json', **auth_header)
    response = execute_ai_action(request)
    if response.status_code == 200:
        print(f"SUCCESS: Action executed. {response.data}")
    else:
        print(f"FAILURE: Action execution failed.")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    test_backend()
