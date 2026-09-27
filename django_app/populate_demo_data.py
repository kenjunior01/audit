
import os
import django
import sys
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Alert, Transaction, ContextProfile, RegulatoryRule, ReferenceList, ReferenceItem

def seed_references():
    print("--- Seeding Reference Lists ---")
    # Departments
    dept_list, _ = ReferenceList.objects.get_or_create(name="Departamentos", defaults={'description': 'Lista de departamentos corporativos'})
    departments = [
        ('FIN', 'Financeiro', 1.2),
        ('IT', 'Tecnologia da Informação', 1.0),
        ('PROC', 'Compras', 1.5),
        ('HR', 'Recursos Humanos', 0.8),
        ('OPS', 'Operações', 1.1),
        ('LEG', 'Jurídico', 0.9)
    ]
    dept_names = []
    for code, name, risk in departments:
        ReferenceItem.objects.get_or_create(
            reference_list=dept_list,
            value=name,
            defaults={'code': code, 'risk_factor': risk}
        )
        dept_names.append(name)

    # Sectors
    sector_list, _ = ReferenceList.objects.get_or_create(name="Setores", defaults={'description': 'Setores de atuação dos fornecedores'})
    sectors = [
        ('MFG', 'Manufatura', 1.1),
        ('SRV', 'Serviços', 1.3),
        ('TECH', 'Tecnologia', 0.9),
        ('RET', 'Varejo', 1.2)
    ]
    for code, name, risk in sectors:
        ReferenceItem.objects.get_or_create(
            reference_list=sector_list,
            value=name,
            defaults={'code': code, 'risk_factor': risk}
        )
    
    print("Reference Lists seeded.")
    return dept_names

def seed_data():
    print("--- Seeding Data for Geo & Graph ---")
    
    dept_names = seed_references()
    
    # 1. Update ContextProfiles with countries
    print("Ensuring profiles for all transaction users...")
    tx_users = Transaction.objects.values_list('user_id', flat=True).distinct()
    countries = ['Brazil', 'USA', 'Germany', 'China', 'India', 'UK', 'France']
    
    for uid in tx_users:
        if not uid: continue
        profile, created = ContextProfile.objects.get_or_create(user_id=uid, defaults={'persona': 'Standard Auditor'})
        updated = False
        if created or not profile.country:
            profile.country = random.choice(countries)
            updated = True
        if not profile.department:
            profile.department = random.choice(dept_names)
            updated = True
            
        if updated:
            profile.save()
            print(f"Updated profile {uid} - Country: {profile.country}, Dept: {profile.department}")
            
    profiles = ContextProfile.objects.all()
    if not profiles.exists():
        print("Creating dummy profiles...")
        for i in range(5):
            ContextProfile.objects.create(
                user_id=f"user_{i}",
                persona="Standard Auditor",
                country=random.choice(countries),
                department=random.choice(dept_names)
            )
            
    profiles = ContextProfile.objects.all()
    for p in profiles:
        updated = False
        if not p.country:
            p.country = random.choice(countries)
            updated = True
        if not p.department:
            p.department = random.choice(dept_names)
            updated = True
            
        if updated:
            p.save()
            print(f"Updated profile {p.user_id} - Country: {p.country}, Dept: {p.department}")

    # 2. Ensure transactions have user_ids that match profiles
    txs = Transaction.objects.all()
    if not txs.exists():
        print("Creating dummy transactions...")
        for i in range(10):
            Transaction.objects.create(
                transaction_id=f"tx_{i}",
                amount=1000.00,
                timestamp=django.utils.timezone.now(),
                user_id=random.choice(profiles).user_id,
                vendor=f"Vendor_{i%3}"
            )
        txs = Transaction.objects.all()

    for tx in txs:
        if not tx.user_id:
            # Assign a random user from profiles
            p = random.choice(profiles)
            tx.user_id = p.user_id
            tx.save()
            
    # 3. Create Alerts if none exist
    alerts = Alert.objects.all()
    if not alerts.exists() or alerts.count() < 5:
        print("Creating dummy alerts...")
        for tx in txs[:5]:
             Alert.objects.create(
                 transaction=tx,
                 alert_type="Suspicious Activity",
                 severity="High",
                 materiality=0.8,
                 vendor=tx.vendor
             )
    
    # 4. Create/Update Regulatory Rules with countries
    rules = RegulatoryRule.objects.all()
    if not rules.exists():
         RegulatoryRule.objects.create(country='Brazil', regulation='LGPD', alert_type='Privacy Violation')
         RegulatoryRule.objects.create(country='USA', regulation='SOX', alert_type='Financial Misstatement')
    
    for r in rules:
        if not r.country:
            r.country = random.choice(countries)
            r.save()

    # 5. Create Audit Cases and Comments
    from dashboard.models import AuditCase, AuditCaseComment
    from django.utils import timezone
    from datetime import timedelta
    print("Creating dummy Audit Cases...")
    if AuditCase.objects.count() < 5:
        # Normal Case
        ac1 = AuditCase.objects.create(
            title="Case: Suspicious Vendor Activity",
            description="Investigating potential collusion.",
            status="In Progress",
            priority="High",
            created_by="system",
            transaction_id=txs[0].id if txs.exists() else None,
            deadline=timezone.now() + timedelta(days=5) # Future deadline
        )
        
        # Overdue Case (Missed Deadline)
        ac2 = AuditCase.objects.create(
            title="Case: OVERDUE Investigation",
            description="This case missed its deadline.",
            status="In Progress",
            priority="Critical",
            created_by="system",
            transaction_id=txs[1].id if txs.count() > 1 else None,
            deadline=timezone.now() - timedelta(days=2) # Past deadline
        )
        
        # Overdue Case (Old, no deadline)
        ac3 = AuditCase.objects.create(
            title="Case: Old Unresolved",
            description="Opened long ago.",
            status="New",
            priority="Medium",
            created_by="system",
            transaction_id=txs[2].id if txs.count() > 2 else None
        )
        ac3.created_at = timezone.now() - timedelta(days=10)
        ac3.save()

        print("Created sample Audit Cases (Normal, Overdue/Deadline, Overdue/Time).")

    print("--- Data Seeding Completed ---")

def verify_endpoints():
    print("\n--- Verifying Endpoints ---")
    from django.test import RequestFactory
    from dashboard.views import geo_risks, graph_analysis, analyze_regulation, analyze_news, audit_dashboard_stats
    from dashboard.models import ApiToken, Alert, Transaction, ContextProfile
    from rest_framework.test import force_authenticate
    from rest_framework.request import Request
    import uuid
    import json
    
    # Debug Data
    print(f"Total Alerts: {Alert.objects.count()}")
    print(f"Total Transactions: {Transaction.objects.count()}")
    print(f"Total Profiles: {ContextProfile.objects.count()}")
    
    alerts = Alert.objects.all()[:5]
    for a in alerts:
        tx = a.transaction
        country = "None"
        if tx:
            if tx.user_id:
                prof = ContextProfile.objects.filter(user_id=tx.user_id).first()
                if prof:
                    country = prof.country
        print(f"Alert {a.id} -> Tx {tx.id if tx else 'None'} -> User {tx.user_id if tx else 'None'} -> Country {country}")

    # Create a dummy token
    token_val = str(uuid.uuid4())
    ApiToken.objects.create(token=token_val, user_id="test_admin", role="admin")

    factory = RequestFactory()
    
    # Test Geo Risks
    print("Testing Geo Risks...")
    req = factory.get('/context/geo_risks', HTTP_AUTHORIZATION=f'Bearer {token_val}')
    resp = geo_risks(req)
    print(f"Geo Risks Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"Geo Risks Data Count: {len(resp.data)}")
        if len(resp.data) == 0:
            print("Response Data is empty.")
        
    # Test Graph Analysis (Global)
    print("Testing Graph Analysis...")
    req_graph = factory.get('/context/graph', HTTP_AUTHORIZATION=f'Bearer {token_val}')
    resp_graph = graph_analysis(req_graph)
    print(f"Graph Status: {resp_graph.status_code}")
    if resp_graph.status_code == 200:
        print(f"Graph Nodes: {len(resp_graph.data.get('nodes', []))}")
        print(f"Graph Links: {len(resp_graph.data.get('links', []))}")

    # Test Suggest Rules
    from dashboard.views import suggest_rules
    print("Testing Suggest Rules...")
    req_sugg = factory.get('/ai/suggest_rules', HTTP_AUTHORIZATION=f'Bearer {token_val}')
    resp_sugg = suggest_rules(req_sugg)
    print(f"Suggest Rules Status: {resp_sugg.status_code}")
    if resp_sugg.status_code == 200:
        print(f"Suggestions: {len(resp_sugg.data.get('suggestions', []))}")

    # Test Regulation Analysis
    print("Testing Regulation Analysis...")
    reg_req = factory.post(
        '/ai/analyze_regulation', 
        data=json.dumps({'text': 'Check for bribe'}), 
        content_type='application/json',
        HTTP_AUTHORIZATION=f'Bearer {token_val}'
    )
    reg_resp = analyze_regulation(reg_req)
    print(f"Regulation Analysis Status: {reg_resp.status_code}")
    
    # Test News Analysis
    print("Testing News Analysis...")
    news_req = factory.post(
        '/ai/analyze_news', 
        data=json.dumps({'vendor': 'Global Tech'}), 
        content_type='application/json',
        HTTP_AUTHORIZATION=f'Bearer {token_val}'
    )
    news_resp = analyze_news(news_req)
    print(f"News Analysis Status: {news_resp.status_code}")
    if news_resp.status_code == 200:
        print(f"News Sentiment: {news_resp.data.get('sentiment')}")

    # Test Dashboard Stats (SLA)
    print("Testing Dashboard Stats (SLA)...")
    stats_req = factory.get('/context/stats', HTTP_AUTHORIZATION=f'Bearer {token_val}')
    stats_resp = audit_dashboard_stats(stats_req)
    print(f"Dashboard Stats Status: {stats_resp.status_code}")
    if stats_resp.status_code == 200:
        print(f"Overdue Cases: {stats_resp.data.get('overdue_cases')}")

if __name__ == "__main__":
    seed_data()
    verify_endpoints()
