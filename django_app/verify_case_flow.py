
import os
import sys

print("Starting script...")

try:
    import django
    from django.core.files.uploadedfile import SimpleUploadedFile
    import json
    
    # Setup Django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auditportal.settings")
    django.setup()
    print("Django setup complete.")
except Exception as e:
    print(f"Error during setup: {e}")
    sys.exit(1)

from rest_framework.test import APIRequestFactory
from dashboard.models import Transaction, AuditCase, AuditCaseComment, AuditCaseAttachment, ApiToken
from dashboard.views import AuditCaseViewSet, AuditCaseCommentViewSet, AuditCaseAttachmentViewSet, case_report

def test_case_workflow():
    print("--- Starting Audit Case Workflow Verification ---")
    factory = APIRequestFactory()
    
    # Setup Auth Token & User
    token_str = "test_case_token_123"
    user_id = "auditor_test_user"
    ApiToken.objects.update_or_create(
        token=token_str,
        defaults={'user_id': user_id, 'role': 'auditor'}
    )
    auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token_str}'}
    
    # 1. Setup Transaction
    print("\n1. Setting up Test Transaction...")
    tx, _ = Transaction.objects.get_or_create(
        transaction_id="TX_CASE_FLOW_001",
        defaults={
            "amount": 12500.00,
            "vendor": "Test Corp Inc",
            "timestamp": "2023-06-15T10:00:00Z",
            "user_id": user_id,
            "category": "Services"
        }
    )
    print(f"   Transaction Ready: {tx.transaction_id}")

    # 2. Create Audit Case
    print("\n2. Creating Audit Case...")
    case_data = {
        "title": "Suspicious Service Payment",
        "description": "Investigating potential duplicate payment for services.",
        "priority": "High",
        "status": "New",
        "transaction_id": str(tx.transaction_id)
    }
    
    request = factory.post('/cases/', case_data, format='json', **auth_header)
    view = AuditCaseViewSet.as_view({'post': 'create'})
    response = view(request)
    
    if response.status_code == 201:
        case_id = response.data['id']
        print(f"   SUCCESS: Case Created. ID: {case_id}")
    else:
        print(f"   FAILURE: Create Case Failed. {response.status_code} - {response.data}")
        return

    # 3. Add Comment to Case
    print("\n3. Adding Comment to Case...")
    comment_data = {
        "case": case_id,
        "comment": "Initial review started. Waiting for vendor confirmation."
    }
    
    request = factory.post('/case_comments/', comment_data, format='json', **auth_header)
    view = AuditCaseCommentViewSet.as_view({'post': 'create'})
    response = view(request)
    
    if response.status_code == 201:
        print(f"   SUCCESS: Comment Added. ID: {response.data['id']}")
    else:
        print(f"   FAILURE: Add Comment Failed. {response.status_code} - {response.data}")

    # 4. Upload Attachment to Case
    print("\n4. Uploading Attachment to Case...")
    file_content = b"evidence_data_sample"
    file = SimpleUploadedFile("evidence.txt", file_content, content_type="text/plain")
    
    # Note: Using multipart format for file upload
    data = {
        "case": case_id,
        "file": file,
        "file_name": "evidence.txt"
    }
    
    request = factory.post('/case_attachments/', data, format='multipart', **auth_header)
    view = AuditCaseAttachmentViewSet.as_view({'post': 'create'})
    response = view(request)
    
    if response.status_code == 201:
        print(f"   SUCCESS: Attachment Uploaded. ID: {response.data['id']}")
    else:
        print(f"   FAILURE: Upload Attachment Failed. {response.status_code} - {response.data}")

    # 5. Verify Case Details (Fetch)
    print("\n5. Verifying Case Details (Get)...")
    request = factory.get(f'/cases/{case_id}/', **auth_header)
    view = AuditCaseViewSet.as_view({'get': 'retrieve'})
    response = view(request, pk=case_id)
    
    if response.status_code == 200:
        data = response.data
        comments_count = len(data.get('comments', []))
        attachments_count = len(data.get('attachments', []))
        
        print(f"   Case Title: {data.get('title')}")
        print(f"   Comments Found: {comments_count}")
        print(f"   Attachments Found: {attachments_count}")
        
        if comments_count > 0 and attachments_count > 0:
             print("   SUCCESS: Case details verified.")
        else:
             print("   WARNING: Comments or Attachments missing in details response.")
    else:
        print(f"   FAILURE: Get Case Failed. {response.status_code}")

    # 6. Generate Case Report
    print("\n6. Generating Case Report (AI Analysis)...")
    # Using the case_report view directly
    request = factory.get(f'/cases/{case_id}/report', **auth_header)
    response = case_report(request, pk=case_id)
    
    if response.status_code == 200:
        print(f"   SUCCESS: Report Generated.")
        # Optional: Check for 3-layer XAI structure in response if mocked/available
        if 'risk_analysis' in response.data:
            print("   Risk Analysis Data Present.")
    else:
        print(f"   FAILURE: Report Generation Failed. {response.status_code}")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    test_case_workflow()
