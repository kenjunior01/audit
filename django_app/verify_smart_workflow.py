
import os
import django
import sys
from datetime import datetime

# Setup Django
sys.path.append(os.path.join(os.getcwd(), 'django_app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_backend.settings')
django.setup()

from dashboard.models import AuditCase, Transaction, ApiToken
from dashboard.ai_service import AuditAI
from rest_framework.test import APIRequestFactory, force_authenticate
from dashboard.views import AuditCaseViewSet

def verify_smart_workflow():
    print("--- Verificando Smart Audit Workflow ---")
    
    # 1. Setup Test Data
    tx, _ = Transaction.objects.get_or_create(
        transaction_id="TX_SMART_001",
        defaults={
            "amount": 95000.00,
            "vendor": "Strategic Consulting LLC",
            "category": "Consulting",
            "user_id": "test_user"
        }
    )
    
    # 2. Test Auto-Assignment
    print("\n1. Testando Auto-Atribuicao...")
    case = AuditCase.objects.create(
        title="Analise de Pagamento de Consultoria",
        description="Valor elevado para servicos de consultoria sem contrato visivel.",
        priority="High",
        transaction_id=tx.transaction_id,
        created_by="system"
    )
    
    ai = AuditAI(user_id="admin")
    assigned_to = ai.auto_assign_case(case)
    print(f"   Caso atribuido a: {assigned_to}")
    
    if assigned_to == "Senior Auditor":
        print("   [OK] Auto-atribuicao correta para prioridade High.")
    else:
        print(f"   [AVISO] Atribuicao inesperada: {assigned_to}")

    # 3. Test AI Suggestion Steps
    print("\n2. Testando Sugestao de Passos de Investigacao AI...")
    steps = ai.suggest_investigation_steps(case)
    print("   Passos sugeridos pela AI:")
    print("-" * 30)
    print(steps)
    print("-" * 30)
    
    if len(steps) > 20:
        print("   [OK] Passos gerados com sucesso.")
    else:
        print("   [ERRO] Falha ao gerar passos ou resposta muito curta.")

    # 4. Test API Endpoint (suggest_steps)
    print("\n3. Testando Endpoint API /suggest_steps...")
    factory = APIRequestFactory()
    view = AuditCaseViewSet.as_view({'post': 'suggest_steps'})
    
    # Mock Token
    token, _ = ApiToken.objects.get_or_create(token="test_token_smart", user_id="admin", role="admin")
    
    request = factory.post(f'/api/cases/{case.id}/suggest_steps/')
    force_authenticate(request, token=token)
    
    response = view(request, pk=case.id)
    if response.status_code == 200:
        print(f"   [OK] Endpoint respondeu com status 200.")
        print(f"   Steps na resposta: {response.data['steps'][:50]}...")
    else:
        print(f"   [ERRO] Endpoint falhou com status {response.status_code}")
        print(response.data)

if __name__ == "__main__":
    verify_smart_workflow()
