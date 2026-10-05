"""
Testes do comando seed_demo — arranque da aplicação desktop.

Cobre: criação completa (user+token, 120 transações, alertas, casos,
regras), credenciais demo funcionais (login + papel admin) e
idempotência (segunda corrida não duplica nada).
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from dashboard.models import (Alert, ApiToken, AuditCase, RegulatoryRule,
                              Transaction)

DEMO_EMAIL = "demo@audit.pt"
DEMO_PASSWORD = "demo1234"


class SeedDemoTest(TestCase):
    def test_seed_creates_full_demo_dataset(self):
        call_command("seed_demo", verbosity=0)

        self.assertTrue(
            get_user_model().objects.filter(username=DEMO_EMAIL).exists())
        user = get_user_model().objects.get(username=DEMO_EMAIL)
        self.assertTrue(user.check_password(DEMO_PASSWORD))

        token = ApiToken.objects.filter(token="demo-desktop-admin").first()
        self.assertIsNotNone(token)
        self.assertEqual(token.role, "admin")
        self.assertEqual(token.user_id, str(user.id))

        self.assertEqual(Transaction.objects.count(), 120)
        self.assertGreaterEqual(Alert.objects.count(), 15)
        self.assertEqual(AuditCase.objects.count(), 6)
        self.assertTrue(RegulatoryRule.objects.exists())

        # severidades variadas (o dashboard e o digest dependem disto)
        sevs = set(Alert.objects.values_list("severity", flat=True))
        self.assertIn("Critical", sevs)
        self.assertIn("High", sevs)

        # casos com prazos em ambos os lados (fora do prazo existe)
        self.assertTrue(
            AuditCase.objects.filter(deadline__lt=user.date_joined).exists()
            or AuditCase.objects.exclude(deadline__isnull=True).exists())

    def test_seed_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)  # 2ª corrida não duplica
        self.assertEqual(Transaction.objects.count(), 120)
        self.assertEqual(AuditCase.objects.count(), 6)
        self.assertEqual(
            ApiToken.objects.filter(token="demo-desktop-admin").count(), 1)

    def test_force_recreates_data(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", "--force", verbosity=0)
        self.assertEqual(Transaction.objects.count(), 120)
        self.assertEqual(get_user_model()
                         .objects.filter(username=DEMO_EMAIL).count(), 1)
