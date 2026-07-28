from django.core.management.base import BaseCommand
from dashboard.models import RegulatoryRule, NewsSignal, Alert, AlertStatus
from django.utils import timezone
from datetime import timedelta
from dashboard.serializers import AlertSerializer

class Command(BaseCommand):
    def handle(self, *args, **options):
        rules_active = RegulatoryRule.objects.filter(active=True).count()
        rules_pending = RegulatoryRule.objects.filter(suggested_by_ai=True).count()
        signals_pending = NewsSignal.objects.filter(suggested_by_ai=True).count()
        week_ago = timezone.now() - timedelta(days=7)
        signals_7d = NewsSignal.objects.filter(created_at__gte=week_ago).count()
        overdue = 0
        for a in Alert.objects.all()[:500]:
            ser = AlertSerializer(a, context={})
            due = ser.data.get('context_due_date')
            if due:
                try:
                    from dateutil import parser as dtp
                    due_dt = dtp.parse(due)
                    latest = AlertStatus.objects.filter(alert_id=int(a.id)).order_by('-updated_at').first()
                    st = latest.status if latest else None
                    if (st is None or st not in ('resolved','closed')) and timezone.now() > due_dt:
                        overdue += 1
                except Exception:
                    pass
        self.stdout.write(f'rules_active={rules_active} rules_pending_validation={rules_pending} signals_pending_validation={signals_pending} signals_last_7_days={signals_7d} alerts_overdue_estimate={overdue}')
