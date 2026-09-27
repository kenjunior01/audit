
import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.join(os.path.dirname(__file__), 'django_app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import AuditCase, AuditCaseComment
from dashboard.views import generate_case_report
from django.test import RequestFactory
from django.utils import timezone

def test_pdf_generation():
    print("Setting up PDF test data...")
    
    # 1. Create a dummy Audit Case
    case = AuditCase.objects.create(
        title="Suspicious Vendor Activity - Test PDF",
        description="Investigation into multiple high-value transactions from a new vendor without proper documentation.",
        status="In Progress",
        priority="High",
        assigned_to="Auditor_Alice",
        created_by="System_AI",
        transaction_id="TX-999-PDF"
    )
    
    # 2. Add some comments
    AuditCaseComment.objects.create(
        case=case,
        user_id="Auditor_Alice",
        comment="I have requested the invoices from the department head."
    )
    AuditCaseComment.objects.create(
        case=case,
        user_id="Manager_Bob",
        comment="Please escalate if not received by Friday."
    )
    
    print(f"Created Case {case.id} with comments.")
    
    # 3. Simulate Request to generate_case_report
    factory = RequestFactory()
    request = factory.get(f'/cases/{case.id}/pdf')
    request.user = type('User', (object,), {'is_authenticated': True, 'username': 'test_admin'})() # Mock user
    
    # Mock permission check (since we are calling view function directly, decorators might block)
    # Actually, calling the view function directly with a request object should work if we handle permissions or bypass them.
    # The view has @permission_classes([IsAuditorOrAdmin]), so we need to mock authentication.
    # But for unit testing the logic, we can also extract the logic or just try calling it.
    # Since it's an API view, we might need APIRequestFactory.
    
    from rest_framework.test import APIRequestFactory, force_authenticate
    from django.contrib.auth.models import User
    
    # Create a real user for authentication
    user, created = User.objects.get_or_create(username='test_admin')
    if created:
        user.is_superuser = True
        user.is_staff = True
        user.save()
    
    factory = APIRequestFactory()
    request = factory.get(f'/cases/{case.id}/pdf')
    # Simulate the auth structure expected by IsAuditorOrAdmin
    # IsAuditorOrAdmin checks request.auth.get('role')
    force_authenticate(request, user=user, token={'role': 'admin'})
    
    print("Calling generate_case_report view...")
    response = generate_case_report(request, pk=case.id)
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Content Type: {response['Content-Type']}")
    
    if response.status_code == 200 and response['Content-Type'] == 'application/pdf':
        print("✅ SUCCESS: PDF generated successfully.")
        # Optional: Write to file to check
        with open(f"test_case_{case.id}.pdf", "wb") as f:
            f.write(response.content)
        print(f"   Saved to test_case_{case.id}.pdf")
    else:
        print("❌ FAILURE: PDF generation failed.")
        print(response.content)

if __name__ == "__main__":
    test_pdf_generation()
