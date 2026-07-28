from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Alert, IntegrationSettings, ImmutableAuditLog
from django.utils import timezone
from .tasks import send_audit_email_task, send_slack_alert_task, send_teams_alert_task

@receiver(post_save, sender=Alert)
def alert_automation(sender, instance, created, **kwargs):
    if not created:
        return

    print(f"[System] Processing new alert {instance.id} for automation...")

    # 1. Hyperautomation: Auto-Close Low Risk / FP
    # Example playbook: Close if Materiality < 50 (Low Value)
    # In a real system, this would be configurable via a Rule Engine
    # Only process if status is 'New' (don't override False Positive or other statuses)
    if instance.status == 'New' and instance.materiality and float(instance.materiality) < 0.1:
        # Check if auto-close is enabled for any user
        settings_obj = IntegrationSettings.objects.filter(auto_close_enabled=True).first()
        if settings_obj:
            instance.status = 'Resolved'
            instance.save()
            
            # Create Immutable Log
            ImmutableAuditLog.objects.create(
                actor_id='System_Hyperautomation',
                action_type='AUTO_CLOSE_ALERT',
                resource_id=str(instance.id),
                details={'reason': 'Risk Score < 0.1', 'alert_type': instance.alert_type}
            )
            print(f"[Hyperautomation] Auto-closed alert {instance.id} (Low Risk < 0.1)")

    # 2. Hyperautomation: Auto-Email for Out of Policy but Low Risk
    # Example: "Taxi" expense > 100 but < 200 -> Send Warning Email
    if instance.vendor and 'taxi' in instance.vendor.lower() and instance.materiality and 100 < float(instance.materiality) < 200:
        settings_obj = IntegrationSettings.objects.filter(auto_email_enabled=True).first()
        if settings_obj:
            # Use email_digest_list as recipient or fallback
            recipients = settings_obj.email_digest_list.split(',') if settings_obj.email_digest_list else ['auditor@example.com']
            
            subject = f"Audit Warning: High Taxi Expense - Alert #{instance.id}"
            message = f"""
            System detected a Taxi expense that requires justification.
            
            Vendor: {instance.vendor}
            Amount: {instance.amount}
            Risk Score: {instance.materiality}
            
            Please attach receipt to the system.
            """
            
            # Use Celery Task
            send_audit_email_task.delay(subject, message, recipients, resource_id=instance.id)
            print(f"[Hyperautomation] Queued auto-email for Alert {instance.id}")

    # 3. Notifications (Slack/Teams) for High Risk
    # Only notify if risk is high or medium
    if instance.materiality and float(instance.materiality) > 500:
        # Slack
        settings_list = IntegrationSettings.objects.exclude(slack_webhook_url__isnull=True).exclude(slack_webhook_url__exact='')
        for s in settings_list:
            if s.slack_webhook_url:
                payload = {
                    "text": f"🚨 *High Risk Alert Detected* 🚨\n*ID:* {instance.id}\n*Type:* {instance.alert_type}\n*Risk:* {instance.materiality}\n*Vendor:* {instance.vendor or 'N/A'}"
                }
                send_slack_alert_task.delay(s.slack_webhook_url, payload, resource_id=instance.id)
                print(f"[Notification] Queued Slack to {s.slack_webhook_url}")

        # Teams
        settings_list_teams = IntegrationSettings.objects.exclude(teams_webhook_url__isnull=True).exclude(teams_webhook_url__exact='')
        for s in settings_list_teams:
            if s.teams_webhook_url:
                payload = {
                    "@type": "MessageCard",
                    "text": f"🚨 High Risk Alert: {instance.alert_type} - Amount {instance.materiality}"
                }
                send_teams_alert_task.delay(s.teams_webhook_url, payload, resource_id=instance.id)
                print(f"[Notification] Queued Teams to {s.teams_webhook_url}")
