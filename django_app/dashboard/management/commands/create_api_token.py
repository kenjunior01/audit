from django.core.management.base import BaseCommand
from dashboard.models import User, ApiToken
from django.utils import timezone

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='admin')
        parser.add_argument('--token', type=str, default='admintoken')
        parser.add_argument('--role', type=str, default='admin')

    def handle(self, *args, **options):
        uname = options['username']
        tok = options['token']
        role = options['role']
        u = User.objects.filter(name=uname).first()
        if not u:
            # Fallback: create user record for RBAC table (separado do auth do Django)
            from dashboard.models import User as LedgerUser
            u = LedgerUser.objects.create(name=uname, role=role)
        ApiToken.objects.update_or_create(token=tok, defaults={'user_id': u.id, 'role': role, 'created_at': timezone.now()})
        self.stdout.write(f'token={tok} user_id={u.id} role={role}')
