import json
import re
import requests
from django.utils import timezone
from django.core.mail import send_mail
from .models import ExternalActionTemplate, ExternalActionExecution, Alert, AuditCase, Transaction
import logging

logger = logging.getLogger(__name__)

class ExternalActionExecutor:
    """Service to execute external actions based on templates."""
    
    VARIABLE_PATTERN = re.compile(r'\{\{(\s*[\w.]+\s*)\}\}')
    
    @staticmethod
    def _resolve_variables(template_value, context):
        """Resolve variables in template strings."""
        if isinstance(template_value, dict):
            return {k: ExternalActionExecutor._resolve_variables(v, context) for k, v in template_value.items()}
        elif isinstance(template_value, list):
            return [ExternalActionExecutor._resolve_variables(v, context) for v in template_value]
        elif isinstance(template_value, str):
            def replace_match(match):
                var_name = match.group(1).strip()
                parts = var_name.split('.')
                value = context
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    elif hasattr(value, part):
                        value = getattr(value, part)
                    else:
                        logger.warning(f"Variable {var_name} not found in context")
                        return match.group(0)
                return str(value) if value is not None else ''
            return ExternalActionExecutor.VARIABLE_PATTERN.sub(replace_match, template_value)
        return template_value
    
    @staticmethod
    def _build_context(alert=None, case=None, transaction=None, agent=None):
        """Build context dictionary for variable resolution."""
        context = {}
        
        if alert:
            context['alert'] = {
                'id': alert.id,
                'alert_type': alert.alert_type,
                'severity': alert.severity,
                'status': alert.status,
                'materiality': alert.materiality,
                'vendor': alert.vendor,
                'amount': float(alert.amount) if alert.amount else None,
                'description': alert.description,
                'transaction_id': alert.transaction.id if alert.transaction else None,
                'timestamp': alert.timestamp.isoformat() if alert.timestamp else None
            }
        
        if case:
            context['case'] = {
                'id': case.id,
                'title': case.title,
                'description': case.description,
                'status': case.status,
                'priority': case.priority,
                'assigned_to': case.assigned_to,
                'created_by': case.created_by,
                'transaction_id': case.transaction_id,
                'created_at': case.created_at.isoformat() if case.created_at else None
            }
        
        if transaction:
            context['transaction'] = {
                'id': transaction.id,
                'transaction_id': transaction.transaction_id,
                'vendor': transaction.vendor,
                'amount': float(transaction.amount) if transaction.amount else None,
                'currency': transaction.currency,
                'category': transaction.category,
                'timestamp': transaction.timestamp.isoformat() if transaction.timestamp else None
            }
        
        if agent:
            context['agent'] = {
                'id': agent.id,
                'name': agent.name,
                'specialization': agent.specialization
            }
        
        return context
    
    @staticmethod
    def execute_template(template, alert=None, case=None, transaction=None, agent=None):
        """Execute an external action template with the given context."""
        execution = ExternalActionExecution.objects.create(
            template=template,
            agent=agent,
            alert=alert,
            case=case,
            transaction=transaction,
            action_type=template.action_type,
            endpoint_url=template.endpoint_url,
            status='running',
            executed_at=timezone.now()
        )
        
        try:
            context = ExternalActionExecutor._build_context(alert, case, transaction, agent)
            
            if template.action_type in ['webhook', 'api_rest']:
                result = ExternalActionExecutor._execute_webhook_api(template, context)
            elif template.action_type == 'email':
                result = ExternalActionExecutor._execute_email(template, context)
            elif template.action_type in ['slack_message', 'jira_ticket']:
                result = ExternalActionExecutor._execute_integration(template, context)
            else:
                raise ValueError(f"Unsupported action type: {template.action_type}")
            
            execution.status = 'success'
            execution.payload_sent = result.get('payload_sent')
            execution.response_received = result.get('response_received')
            execution.completed_at = timezone.now()
            execution.save()
            
            logger.info(f"Successfully executed external action: {template.name}")
            return execution
            
        except Exception as e:
            logger.error(f"Failed to execute external action {template.name}: {str(e)}")
            execution.status = 'failed'
            execution.error_message = str(e)
            execution.completed_at = timezone.now()
            execution.save()
            raise
    
    @staticmethod
    def _execute_webhook_api(template, context):
        """Execute webhook or REST API action."""
        url = ExternalActionExecutor._resolve_variables(template.endpoint_url, context) if template.endpoint_url else None
        if not url:
            raise ValueError("Endpoint URL is required")
        
        payload = ExternalActionExecutor._resolve_variables(template.payload_template, context) if template.payload_template else None
        headers = ExternalActionExecutor._resolve_variables(template.headers, context) if template.headers else {}
        
        # Add authentication from template or system
        auth = None
        if template.auth_type == 'basic' and template.auth_credentials:
            username = template.auth_credentials.get('username')
            password = template.auth_credentials.get('password')
            if username and password:
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(username, password)
        
        if template.auth_type == 'bearer' and template.auth_credentials:
            token = template.auth_credentials.get('token')
            if token:
                headers['Authorization'] = f'Bearer {token}'
        
        if template.auth_type == 'api_key' and template.auth_credentials:
            api_key = template.auth_credentials.get('api_key')
            header_name = template.auth_credentials.get('header_name', 'X-API-Key')
            if api_key:
                headers[header_name] = api_key
        
        # Also check system-level auth if available
        if template.system and not auth and not headers.get('Authorization') and not headers.get('X-API-Key'):
            system = template.system
            if system.auth_type == 'BEARER' and system.api_key:
                headers['Authorization'] = f'Bearer {system.api_key}'
            elif system.auth_type == 'API_KEY' and system.api_key:
                headers['X-API-Key'] = system.api_key
            elif system.auth_type == 'BASIC' and system.api_key and system.api_secret:
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(system.api_key, system.api_secret)
        
        logger.info(f"Executing {template.http_method} request to {url}")
        
        response = requests.request(
            method=template.http_method,
            url=url,
            json=payload,
            headers=headers,
            auth=auth,
            timeout=30
        )
        
        response.raise_for_status()
        
        try:
            response_data = response.json()
        except:
            response_data = {'text': response.text}
        
        return {
            'payload_sent': payload,
            'response_received': response_data,
            'status_code': response.status_code
        }
    
    @staticmethod
    def _execute_email(template, context):
        """Execute email action."""
        recipients = template.email_recipients.split(',') if template.email_recipients else []
        recipients = [r.strip() for r in recipients if r.strip()]
        
        if not recipients:
            raise ValueError("Email recipients are required")
        
        subject = ExternalActionExecutor._resolve_variables(template.email_subject_template, context) if template.email_subject_template else "Audit Alert"
        body = ExternalActionExecutor._resolve_variables(template.email_body_template, context) if template.email_body_template else ""
        
        send_mail(
            subject=subject,
            message=body,
            from_email='audit-command-center@internal.com',
            recipient_list=recipients,
            fail_silently=False
        )
        
        return {
            'payload_sent': {'subject': subject, 'body': body, 'recipients': recipients},
            'response_received': {'status': 'sent'}
        }
    
    @staticmethod
    def _execute_integration(template, context):
        """Execute integration-specific actions (Slack, Jira, etc.)."""
        if template.action_type == 'slack_message':
            return ExternalActionExecutor._execute_slack(template, context)
        elif template.action_type == 'jira_ticket':
            return ExternalActionExecutor._execute_jira(template, context)
        raise ValueError(f"Unsupported integration: {template.action_type}")
    
    @staticmethod
    def _execute_slack(template, context):
        """Execute Slack message action (reuses existing Slack integration)."""
        from .tasks import send_slack_alert_task
        
        payload = ExternalActionExecutor._resolve_variables(template.payload_template, context) if template.payload_template else {}
        
        url = template.endpoint_url or (template.system.webhook_url if template.system else None)
        if not url:
            raise ValueError("Slack webhook URL is required")
        
        send_slack_alert_task.delay(url, payload)
        
        return {
            'payload_sent': payload,
            'response_received': {'status': 'queued'}
        }
    
    @staticmethod
    def _execute_jira(template, context):
        """Execute Jira ticket creation action."""
        url = template.endpoint_url
        if not url:
            raise ValueError("Jira API URL is required")
        
        project_key = template.jira_project_key or 'PROJECT'
        issue_type = template.jira_issue_type or 'Task'
        
        # Build issue payload from template or default
        if template.payload_template:
            payload = ExternalActionExecutor._resolve_variables(template.payload_template, context)
        else:
            payload = {
                'fields': {
                    'project': {'key': project_key},
                    'summary': ExternalActionExecutor._resolve_variables('Audit Alert: {{ alert.description }}', context),
                    'description': ExternalActionExecutor._resolve_variables('''
                        *Alert ID:* {{ alert.id }}
                        *Type:* {{ alert.alert_type }}
                        *Severity:* {{ alert.severity }}
                        *Vendor:* {{ alert.vendor }}
                        *Amount:* {{ alert.amount }}
                    ''', context),
                    'issuetype': {'name': issue_type}
                }
            }
        
        return ExternalActionExecutor._execute_webhook_api(template, context)