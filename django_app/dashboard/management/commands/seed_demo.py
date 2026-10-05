"""
Dados de demonstração para o arranque da aplicação desktop.

Idempotente: se já existirem transações E o utilizador demo, não faz nada
(pode correr em cada arranque sem duplicar dados). Cria:
- utilizador demo (demo@audit.pt / demo1234, papel admin)
- ApiToken determinístico 'demo-desktop-admin' (login devolve role admin)
- ~120 transações com padrões de auditoria detetáveis (Benford, duplicados,
  valores redondos, fins de semana, fornecedores de risco)
- ~20 alertas com severidades variadas
- ~6 casos de auditoria (alguns fora do prazo)
- regras regulatórias base, se a tabela estiver vazia

Uso:  python manage.py seed_demo [--force]
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from dashboard.models import (Alert, ApiToken, AuditCase, RegulatoryRule,
                              Transaction)

DEMO_EMAIL = "demo@audit.pt"
DEMO_PASSWORD = "demo1234"
DEMO_TOKEN = "demo-desktop-admin"

VENDORS = [
    ("NordTech Lda", 1.4), ("OfficePlus", 1.0), ("GlobalParts SA", 1.6),
    ("Consultoria Alfa", 1.8), ("Logística Rápida", 0.9), ("SoftSolutions", 1.1),
    ("BuildCo", 1.5), ("EnergiaSolar PT", 1.0), ("TravelEasy", 1.7),
    ("ManutençãoPro", 1.2), ("DataCloud", 1.3), ("PaperFlow", 0.8),
]
CATEGORIES = ["Serviços", "Material", "Software", "Viagens", "Manutenção",
              "Consultoria", "Energia", "Logística"]
STATUSES = ["Completed", "Completed", "Completed", "Pending", "Approved", "Rejected"]


class Command(BaseCommand):
    help = "Semeia dados de demonstração (idempotente)"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Recria os dados demo mesmo se já existirem")

    def handle(self, *args, **opts):
        User = get_user_model()
        has_user = User.objects.filter(username=DEMO_EMAIL).exists()
        has_tx = Transaction.objects.exists()
        if has_user and has_tx and not opts["force"]:
            self.stdout.write("seed_demo: dados já presentes — nada a fazer")
            return
        if opts["force"]:
            Alert.objects.all().delete()
            AuditCase.objects.all().delete()
            Transaction.objects.all().delete()

        rnd = random.Random(2024)

        # --- utilizador demo + token admin determinístico -------------------
        user, created = User.objects.get_or_create(
            username=DEMO_EMAIL,
            defaults={"email": DEMO_EMAIL, "first_name": "Demo",
                      "is_staff": False})
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        elif not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            user.save()
        ApiToken.objects.get_or_create(
            token=DEMO_TOKEN,
            defaults={"user_id": str(user.id), "role": "admin"})

        # --- transações (últimos 90 dias) -----------------------------------
        now = timezone.now()
        txs = []
        for i in range(120):
            vendor, risk = rnd.choice(VENDORS)
            # distribuição com cauda: maioria pequena, poucas muito grandes
            amount = round(rnd.lognormvariate(4.6, 1.15), 2)
            if rnd.random() < 0.06:
                amount = round(rnd.choice([5000, 7500, 9000, 10000, 12000]), 2)
            ts = now - timedelta(days=rnd.randint(0, 89),
                                 hours=rnd.randint(0, 23),
                                 minutes=rnd.randint(0, 59))
            if rnd.random() < 0.08:  # fins de semana (padrão anómalo)
                while ts.weekday() not in (5, 6):
                    ts -= timedelta(days=1)
            txs.append(Transaction(
                transaction_id=f"TX-{2024}{i:05d}",
                vendor=vendor, amount=amount, currency="EUR",
                timestamp=ts, category=rnd.choice(CATEGORIES),
                status=rnd.choice(STATUSES),
                user_id=f"user-{rnd.randint(1, 12):02d}",
                xai_explanation={"model": "RiskAgent-v2",
                                 "features": {"amount_z": round(amount / 1000, 2),
                                              "vendor_risk": risk},
                                 "version": "2.1.0"}))
        Transaction.objects.bulk_create(txs, batch_size=60)

        # --- alertas ---------------------------------------------------------
        sev_plan = (["Critical"] * 4 + ["High"] * 7 + ["Medium"] * 6
                    + ["Low"] * 3)
        alerts = []
        for i, sev in enumerate(sev_plan):
            tx = rnd.choice(txs)
            alerts.append(Alert(
                transaction=tx,
                alert_type=rnd.choice([
                    "Valor fora do padrão Benford", "Pagamento duplicado",
                    "Fornecedor de risco elevado", "Transação em fim de semana",
                    "Valor redondo suspeito", "Aprovação fora do horário"]),
                severity=sev,
                status=rnd.choice(["New", "New", "New", "Investigating",
                                   "Resolved"]),
                description=f"Revisão automática da transação {tx.transaction_id} "
                            f"({tx.vendor}) — padrão inconsistente com a história.",
                timestamp=tx.timestamp, vendor=tx.vendor,
                amount=tx.amount,
                materiality=round(min(1.0, float(tx.amount) / 15000), 2)))
        Alert.objects.bulk_create(alerts, batch_size=30)

        # --- casos -----------------------------------------------------------
        case_plan = [
            ("Revisão de pagamentos duplicados — NordTech", "In Progress",
             "High", -3),
            ("Desvio Benford em Consultoria Alfa", "New", "Critical", -10),
            ("Despesas de viagem fora de política", "In Progress", "Medium", 5),
            ("Contratos sem três orçamentos (BuildCo)", "New", "High", 12),
            ("Fecho de investigação SoftSolutions", "Resolved", "Low", 20),
            ("Auditoria de aprovadores fora do horário", "New", "Medium", -6),
        ]
        for j, (title, status, priority, dline) in enumerate(case_plan):
            tx = rnd.choice(txs)
            AuditCase.objects.create(
                title=title,
                description="Caso gerado pelos agentes de auditoria a partir "
                            "de sinais do RiskAgent. Ver anexos e histórico.",
                status=status, priority=priority,
                assigned_to=f"user-{rnd.randint(1, 6):02d}",
                created_by=DEMO_EMAIL, transaction_id=tx.transaction_id,
                deadline=now + timedelta(days=dline),
                finding_type=rnd.choice(["compliance", "fraud", "error"]),
                inherent_risk=round(rnd.uniform(0.4, 0.95), 2),
                residual_risk=round(rnd.uniform(0.1, 0.5), 2),
                action_owner="Comité de Auditoria",
                action_plan="Plano de remediação proposto pelo copiloto e "
                            "pendente de aprovação do gestor responsável.")

        # --- regras regulatórias base ----------------------------------------
        if not RegulatoryRule.objects.exists():
            RegulatoryRule.objects.bulk_create([
                RegulatoryRule(country="Portugal", regulation="SOC/PC",
                               alert_type="Pagamento duplicado",
                               description="Pagamentos com mesmo valor e "
                                           "fornecedor em 30 dias.",
                               threshold_amount=1000, active=True),
                RegulatoryRule(country="Portugal", regulation="LGPD/SOX",
                               alert_type="Aprovação fora do horário",
                               description="Aprovações fora do horário "
                                           "laboral (20h-06h).",
                               threshold_amount=500, active=True),
                RegulatoryRule(country="UE", regulation="AML",
                               alert_type="Valor fora do padrão Benford",
                               description="Distribuição de primeiros "
                                           "dígitos fora do esperado (MAD>0.015).",
                               threshold_amount=2500, active=True,
                               suggested_by_ai=True, ai_confidence=0.82),
            ])

        self.stdout.write(self.style.SUCCESS(
            f"seed_demo OK — user={DEMO_EMAIL} token={DEMO_TOKEN[:14]}… "
            f"tx={len(txs)} alertas={len(alerts)} casos={len(case_plan)}"))
