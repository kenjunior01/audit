
import os
import django
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auditportal.settings')
django.setup()

from dashboard.models import Transaction, Alert, RegulatoryRule, ApiToken

def seed_data():
    print("Seeding data...")

    # Create Transactions
    vendors = ['TechCorp', 'OfficeSupply', 'TravelAgency', 'ConsultingFirm', 'CloudServices']
    categories = ['IT', 'Office', 'Travel', 'Professional Services', 'Infrastructure']
    
    transactions = []
    for i in range(20):
        txn = Transaction(
            transaction_id=f'TX-{1000+i}',
            vendor=random.choice(vendors),
            amount=Decimal(random.uniform(100.0, 10000.0)).quantize(Decimal('0.01')),
            currency='BRL',
            timestamp=datetime.now() - timedelta(days=random.randint(0, 30)),
            category=random.choice(categories),
            status='Pending',
            user_id=f'user_{random.randint(1, 5)}'
        )
        txn.save()
        transactions.append(txn)
    print(f"Created {len(transactions)} transactions")

    # Create Alerts
    alert_types = ['High Value', 'Suspicious Vendor', 'Weekend Transaction', 'Duplicate']
    severities = ['Low', 'Medium', 'High', 'Critical']
    
    for i in range(10):
        txn = random.choice(transactions)
        alert = Alert(
            transaction=txn,
            alert_type=random.choice(alert_types),
            severity=random.choice(severities),
            status='New',
            description=f'Potential issue detected for {txn.transaction_id}',
            vendor=txn.vendor,
            amount=txn.amount,
            materiality=random.uniform(0.1, 0.9)
        )
        alert.save()
    print("Created 10 alerts")

    # Create Regulatory Rules
    rules = [
        {'country': 'Brazil', 'regulation': 'LGPD', 'alert_type': 'Data Privacy', 'threshold': 0},
        {'country': 'US', 'regulation': 'SOX', 'alert_type': 'Compliance', 'threshold': 5000},
    ]
    
    for r in rules:
        RegulatoryRule.objects.get_or_create(
            country=r['country'],
            regulation=r['regulation'],
            defaults={
                'alert_type': r['alert_type'],
                'description': f'Rule for {r["regulation"]}',
                'threshold_amount': r['threshold'],
                'active': True
            }
        )
    print("Created regulatory rules")

    # Ensure Token exists
    token, created = ApiToken.objects.get_or_create(
        token='demo-token-123',
        defaults={'user_id': 'admin', 'role': 'admin'}
    )
    if created:
        print("Created demo token")
    else:
        print("Demo token already exists")

if __name__ == '__main__':
    seed_data()
