import requests
import json
import hmac
import hashlib
from django.utils import timezone
from django.conf import settings
from .models import WebhookEvent, ExternalSystem
import logging

logger = logging.getLogger(__name__)

class WebhookService:
    @staticmethod
    def _generate_signature(payload: dict, secret: str) -> str:
        """Generate HMAC SHA256 signature for webhook payload."""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f'sha256={signature}'

    @staticmethod
    def send_event(system: ExternalSystem, event_type: str, payload: dict) -> WebhookEvent:
        """Cria um evento de webhook e envia (ou aguarda tarefa Celery)."""
        webhook = WebhookEvent.objects.create(
            system=system,
            event_type=event_type,
            payload=payload
        )
        # Tentar enviar imediatamente (ou usar Celery para background)
        WebhookService._attempt_send(webhook)
        return webhook

    @staticmethod
    def _attempt_send(webhook: WebhookEvent) -> None:
        """Tenta enviar o webhook."""
        system = webhook.system
        if not system.webhook_url:
            webhook.status = 'FAILED'
            webhook.error_message = 'URL do webhook não configurada'
            webhook.save()
            return

        webhook.status = 'RETRYING'
        webhook.attempt_count += 1
        webhook.last_attempt_at = timezone.now()
        webhook.save()

        try:
            # Use system-specific secret or fall back to global setting
            secret = system.api_secret or getattr(settings, 'WEBHOOK_SECRET', 'audit-command-center-secret')
            
            headers = {
                'Content-Type': 'application/json',
                'X-Audit-Command-Center-Signature': WebhookService._generate_signature(webhook.payload, secret),
                'X-Audit-Command-Center-Event': webhook.event_type,
                'X-Audit-Command-Center-Timestamp': str(int(webhook.created_at.timestamp()))
            }

            auth = None
            if system.auth_type == 'BEARER' and system.api_key:
                headers['Authorization'] = f'Bearer {system.api_key}'
            elif system.auth_type == 'API_KEY' and system.api_key:
                headers['X-API-Key'] = system.api_key
            elif system.auth_type == 'BASIC' and system.api_key and system.api_secret:
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(system.api_key, system.api_secret)

            response = requests.post(
                system.webhook_url,
                json=webhook.payload,
                headers=headers,
                auth=auth,
                timeout=10
            )

            response.raise_for_status()
            webhook.status = 'SUCCESS'
            webhook.error_message = None
            logger.info(f'Webhook enviado com sucesso: {webhook.id} - {webhook.event_type}')

        except requests.exceptions.RequestException as e:
            webhook.status = 'FAILED'
            webhook.error_message = str(e)
            logger.error(f'Falha ao enviar webhook {webhook.id}: {e}')

        webhook.save()

    @staticmethod
    def retry_failed(webhook_id: int) -> WebhookEvent:
        """Tenta reenviar um webhook que falhou."""
        webhook = WebhookEvent.objects.get(id=webhook_id)
        WebhookService._attempt_send(webhook)
        return webhook

    @staticmethod
    def broadcast_event(event_type: str, payload: dict) -> list[WebhookEvent]:
        """Envia evento para todos os sistemas externos ativos com webhook configurado."""
        systems = ExternalSystem.objects.filter(is_active=True, webhook_url__isnull=False)
        webhooks = []
        for system in systems:
            webhook = WebhookService.send_event(system, event_type, payload)
            webhooks.append(webhook)
        return webhooks