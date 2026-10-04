import json
from dateutil import parser
from rest_framework import viewsets, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from .models import Alert, Transaction, ContextProfile, RegulatoryRule, IntegrationSettings, AiFeedback, AuditCase, AuditCaseComment, AuditCaseAttachment, ContextDocument, RiskAgent, ExternalSystem, IngestedSignal, ReferenceList, ReferenceItem, ApiToken, RiskAgentLog, AIGovernanceEvent, AuditRule, WebhookEvent, ExternalActionTemplate, ExternalActionExecution, ExcelImportJob
from .serializers import AlertSerializer, TransactionSerializer, ContextProfileSerializer, RegulatoryRuleSerializer, ContextDocumentSerializer, IntegrationSettingsSerializer, AuditCaseSerializer, AuditCaseCommentSerializer, AuditCaseAttachmentSerializer, RiskAgentSerializer, ExternalSystemSerializer, IngestedSignalSerializer, ReferenceListSerializer, ReferenceItemSerializer, RiskAgentLogSerializer, AIGovernanceEventSerializer, AuditRuleSerializer, WebhookEventSerializer, ExternalActionTemplateSerializer, ExternalActionExecutionSerializer
from .auth import IsViewerOrAbove, IsAuditorOrAdmin
from rest_framework.decorators import (api_view, permission_classes,
                                        parser_classes,
                                        authentication_classes)
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
import uuid
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from django.http import HttpResponse, StreamingHttpResponse
from django.db.utils import OperationalError

class AIGovernanceViewSet(viewsets.ModelViewSet):
    queryset = AIGovernanceEvent.objects.all().order_by('-timestamp')
    serializer_class = AIGovernanceEventSerializer
    permission_classes = [IsAuditorOrAdmin]
    filterset_fields = ['event_type', 'status', 'model_name']

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        """
        Returns aggregated metrics for the AI Governance Dashboard.
        """
        from django.db.models import Count, Avg, StdDev
        from django.utils import timezone
        from datetime import timedelta

        last_24h = timezone.now() - timedelta(hours=24)
        events = AIGovernanceEvent.objects.filter(timestamp__gte=last_24h)

        total_calls = events.count()
        success_rate = (events.filter(status='SUCCESS').count() / total_calls * 100) if total_calls > 0 else 100
        avg_latency = events.aggregate(Avg('latency_ms'))['latency_ms__avg'] or 0
        
        # Hallucination rate (if status='HALLUCINATION')
        hallucination_count = events.filter(status='HALLUCINATION').count()
        hallucination_rate = (hallucination_count / total_calls * 100) if total_calls > 0 else 0

        # Distribution by model
        model_dist = events.values('model_name').annotate(count=Count('id')).order_by('-count')

        # Accuracy trend (Success rate over time)
        # For simplicity, just return the last 100 events for a trend chart
        recent_events = AIGovernanceEvent.objects.all()[:100].values('timestamp', 'status', 'confidence_score')

        return Response({
            'total_calls_24h': total_calls,
            'success_rate': round(success_rate, 2),
            'avg_latency_ms': round(avg_latency, 2),
            'hallucination_rate': round(hallucination_rate, 2),
            'model_distribution': model_dist,
            'recent_events': recent_events
        })

class ExternalSystemViewSet(viewsets.ModelViewSet):
    queryset = ExternalSystem.objects.all().order_by('-created_at')
    serializer_class = ExternalSystemSerializer
    permission_classes = [IsAuditorOrAdmin]

class ReferenceListViewSet(viewsets.ModelViewSet):
    queryset = ReferenceList.objects.all().order_by('-created_at')
    serializer_class = ReferenceListSerializer
    permission_classes = [IsViewerOrAbove]

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser])
    def upload_csv(self, request, pk=None):
        import csv
        import io
        
        ref_list = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=400)
        
        try:
            # Decode file
            file_data = file_obj.read().decode('utf-8')
            io_string = io.StringIO(file_data)
            reader = csv.DictReader(io_string)
            
            items_created = 0
            
            # Expect CSV headers: value, code, risk_factor, metadata
            for row in reader:
                value = row.get('value') or row.get('nome') or row.get('name')
                if not value: continue # Skip empty rows
                
                ReferenceItem.objects.create(
                    reference_list=ref_list,
                    value=value,
                    code=row.get('code', ''),
                    risk_factor=float(row.get('risk_factor', 1.0)),
                    metadata=json.loads(row.get('metadata', '{}'))
                )
                items_created += 1
                
            return Response({'status': 'success', 'items_created': items_created})
            
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class ReferenceItemViewSet(viewsets.ModelViewSet):
    queryset = ReferenceItem.objects.all().order_by('value')
    serializer_class = ReferenceItemSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['reference_list']

class IngestedSignalViewSet(viewsets.ModelViewSet):
    queryset = IngestedSignal.objects.all().order_by('-created_at')
    serializer_class = IngestedSignalSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['source', 'signal_type', 'processed']

@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_external_data(request):
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return Response({'error': 'Missing X-API-Key header'}, status=401)
    
    try:
        source = ExternalSystem.objects.get(api_key=api_key, is_active=True)
    except ExternalSystem.DoesNotExist:
        return Response({'error': 'Invalid API Key'}, status=401)

    payload = request.data
    signal_type = payload.get('type', 'generic_event')
    
    # Save signal
    signal = IngestedSignal.objects.create(
        source=source,
        signal_type=signal_type,
        payload=payload
    )
    
    # Process immediately if it's a known type
    if signal_type == 'transaction':
        try:
            # Map payload to Transaction model
            # Expecting payload keys: amount, vendor, timestamp, currency, transaction_id, user_id, category
            from dateutil import parser
            
            # Default fallback for missing fields
            tx_data = {
                'amount': payload.get('amount', 0.0),
                'vendor': payload.get('vendor', 'Unknown Vendor'),
                'currency': payload.get('currency', 'BRL'),
                'transaction_id': payload.get('transaction_id', f"EXT-{signal.id}"),
                'user_id': payload.get('user_id'),
                'category': payload.get('category', 'External'),
                'status': 'Pending'
            }
            
            # Parse timestamp safely
            ts_str = payload.get('timestamp')
            if ts_str:
                try:
                    tx_data['timestamp'] = parser.parse(ts_str)
                except:
                    tx_data['timestamp'] = timezone.now()
            else:
                tx_data['timestamp'] = timezone.now()

            # Create Transaction
            txn = Transaction.objects.create(**tx_data)
            
            # Trigger Risk Analysis
            from .ai_service import AuditAI
            ai = AuditAI(user_id=str(txn.user_id) if txn.user_id else 'system')
            analysis = ai.analyze_transaction_risk(txn)
            
            # Create Alert if Risk is detected or Auto-Resolved by Agent
            risk_score = analysis.get('risk_score', 0)
            triggered_agents = analysis.get('triggered_agents', [])
            should_auto_resolve = any(a.get('action') == 'auto_resolve' for a in triggered_agents)

            if risk_score > 0.3 or should_auto_resolve: # Threshold for creating an alert
                severity = 'Low'
                if risk_score > 0.7: severity = 'High'
                elif risk_score > 0.5: severity = 'Medium'
                
                status = 'New'
                description = f"AI Risk Score: {int(risk_score*100)}%. Factors: {', '.join(analysis.get('reasons', []))}"
                
                if should_auto_resolve:
                    status = 'False Positive'
                    description = f"[AUTO-RESOLVED] {description}"

                alert = Alert.objects.create(
                    transaction=txn,
                    alert_type='External Risk Signal',
                    severity=severity,
                    status=status,
                    description=description,
                    vendor=txn.vendor,
                    amount=txn.amount,
                    materiality=risk_score
                )

                # Webhook Notification
                if source.webhook_url:
                    try:
                        import requests
                        webhook_payload = {
                            "event": "risk_alert",
                            "transaction_id": txn.transaction_id,
                            "risk_score": risk_score,
                            "severity": severity,
                            "reasons": analysis.get('reasons', []),
                            "alert_id": alert.id
                        }
                        # Fire and forget (with short timeout)
                        requests.post(source.webhook_url, json=webhook_payload, timeout=2)
                    except Exception as wh_err:
                        print(f"Webhook failed: {wh_err}")
            
            signal.processed = True
            signal.save()
            
        except Exception as e:
            # Log error but don't fail the request (signal is saved)
            print(f"Error processing external signal {signal.id}: {str(e)}")
            pass
    
    return Response({
        'status': 'success', 
        'signal_id': signal.id,
        'message': 'Data ingested successfully'
    })
from django.http import StreamingHttpResponse
from math import tanh
from django.db.models import Count, Avg, Sum, Max, Q, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncWeek
from datetime import timedelta

class RiskAgentViewSet(viewsets.ModelViewSet):
    queryset = RiskAgent.objects.all().order_by('-created_at')
    serializer_class = RiskAgentSerializer
    permission_classes = [IsAuditorOrAdmin]

class RiskAgentLogViewSet(viewsets.ModelViewSet):
    queryset = RiskAgentLog.objects.all().order_by('-timestamp')
    serializer_class = RiskAgentLogSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['agent']

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def trigger_agent_run(request, pk):
    """
    Manually triggers a specific agent to run immediately.
    """
    try:
        agent = RiskAgent.objects.get(pk=pk)
        
        # Instantiate AI Service to run logic
        from .ai_service import AuditAI
        ai = AuditAI(user_id=request.user.id if request.user.id else 'system')
        
        # Run finding simulation
        from django.utils import timezone
        from datetime import timedelta
        start_date = timezone.now() - timedelta(days=7)
        
        finding = ai._simulate_agent_finding(agent, start_date)
        
        # Update last triggered
        agent.last_triggered = timezone.now()
        agent.save()
        
        return Response({
            'status': 'success',
            'agent': agent.name,
            'finding': finding
        })
    except RiskAgent.DoesNotExist:
        return Response({'error': 'Agent not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

import pandas as pd
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
import json
import io


def get_audit_context():
    from .models import ContextProfile
    profile = ContextProfile.objects.order_by('-updated_at').first()
    if not profile:
        return {
            "regulatory_frameworks": [],
            "audit_domains": [],
            "risk_appetite": "Balanced",
        }
    return {
        "regulatory_frameworks": profile.regulatory_frameworks or [],
        "audit_domains": profile.audit_domains or [],
        "risk_appetite": profile.risk_appetite or "Balanced",
    }


def evaluate_transaction_rules(tx):
    rules = []

    try:
        context = get_audit_context()
        domains = context.get("audit_domains") or []
        risk_appetite = context.get("risk_appetite") or "Balanced"
        qs = AuditRule.objects.filter(active=True, model='transaction')
        if domains:
            qs = qs.filter(domain__in=domains)
        db_rules = list(qs)
    except OperationalError:
        return rules

    for rule in db_rules:
        value = getattr(tx, rule.field, None)

        if value is None:
            continue

        target = rule.value

        try:
            value_num = float(value)
            target_num = float(target)
            value_cmp = value_num
            target_cmp = target_num
        except Exception:
            value_cmp = str(value)
            target_cmp = target

        op = rule.operator
        match = False

        if op == '>':
            match = value_cmp > target_cmp
        elif op == '>=':
            match = value_cmp >= target_cmp
        elif op == '<':
            match = value_cmp < target_cmp
        elif op == '<=':
            match = value_cmp <= target_cmp
        elif op == '==':
            match = value_cmp == target_cmp
        elif op == '!=':
            match = value_cmp != target_cmp

        if match:
            materiality = rule.materiality
            if risk_appetite == "Conservative":
                materiality = min(1.0, materiality * 1.2)
            elif risk_appetite == "Aggressive":
                materiality = max(0.0, materiality * 0.8)
            rules.append({
                "code": rule.code,
                "description": rule.description or "",
                "severity": rule.severity,
                "materiality": materiality,
            })

    return rules


def evaluate_alert_rules(alert):
    rules = []

    try:
        context = get_audit_context()
        domains = context.get("audit_domains") or []
        risk_appetite = context.get("risk_appetite") or "Balanced"
        qs = AuditRule.objects.filter(active=True, model='alert')
        if domains:
            qs = qs.filter(domain__in=domains)
        db_rules = list(qs)
    except OperationalError:
        return rules

    for rule in db_rules:
        value = getattr(alert, rule.field, None)

        if value is None:
            continue

        target = rule.value

        try:
            value_num = float(value)
            target_num = float(target)
            value_cmp = value_num
            target_cmp = target_num
        except Exception:
            value_cmp = str(value)
            target_cmp = target

        op = rule.operator
        match = False

        if op == '>':
            match = value_cmp > target_cmp
        elif op == '>=':
            match = value_cmp >= target_cmp
        elif op == '<':
            match = value_cmp < target_cmp
        elif op == '<=':
            match = value_cmp <= target_cmp
        elif op == '==':
            match = value_cmp == target_cmp
        elif op == '!=':
            match = value_cmp != target_cmp

        if match:
            materiality = rule.materiality
            if risk_appetite == "Conservative":
                materiality = min(1.0, materiality * 1.2)
            elif risk_appetite == "Aggressive":
                materiality = max(0.0, materiality * 0.8)
            rules.append(
                {
                    "code": rule.code,
                    "description": rule.description or "",
                    "severity": rule.severity,
                    "materiality": materiality,
                }
            )

    return rules


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all().order_by('-timestamp')
    serializer_class = TransactionSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['vendor', 'category', 'status', 'user_id', 'transaction_id']

    @action(detail=False, methods=['post'])
    def scan_rules(self, request):
        """
        Varre transações aplicando regras genéricas de auditoria
        e gera Alertas padronizados.
        """
        queryset = self.filter_queryset(self.get_queryset())

        alerts_created = 0
        transactions_scanned = 0

        for tx in queryset:
            transactions_scanned += 1
            matches = evaluate_transaction_rules(tx)

            for rule in matches:
                alert, created = Alert.objects.get_or_create(
                    transaction=tx,
                    alert_type=rule["code"],
                    defaults={
                        "severity": rule["severity"],
                        "status": "New",
                        "description": rule["description"],
                        "vendor": tx.vendor,
                        "amount": tx.amount,
                        "materiality": rule["materiality"],
                    },
                )
                if created:
                    alerts_created += 1

        return Response({
            "transactions_scanned": transactions_scanned,
            "alerts_created": alerts_created,
        })

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Exporta transações filtradas para Excel."""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Convert queryset to list of dicts
        data = []
        for txn in queryset:
            data.append({
                'ID': txn.id,
                'ID Transação': txn.transaction_id,
                'Data': txn.timestamp.strftime('%Y-%m-%d %H:%M'),
                'Valor': float(txn.amount),
                'Moeda': txn.currency,
                'Fornecedor': txn.vendor,
                'Categoria': txn.category,
                'Usuário': txn.user_id,
                'Status': txn.status,
                'Score de Risco': getattr(txn, 'risk_score', None)
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Transações')
        
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Transacoes_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
        return response

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Exporta transações filtradas para CSV."""
        queryset = self.filter_queryset(self.get_queryset())
        
        data = []
        for txn in queryset:
            data.append({
                'ID': txn.id,
                'ID_Transacao': txn.transaction_id,
                'Data': txn.timestamp.isoformat(),
                'Valor': float(txn.amount),
                'Moeda': txn.currency,
                'Fornecedor': txn.vendor,
                'Categoria': txn.category,
                'Usuario': txn.user_id,
                'Status': txn.status,
                'Risco': getattr(txn, 'risk_score', None)
            })
            
        df = pd.DataFrame(data)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Transacoes_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        
        df.to_csv(path_or_buf=response, index=False, encoding='utf-8-sig')
        return response

class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.select_related('transaction').order_by('-timestamp')
    serializer_class = AlertSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['status', 'severity', 'alert_type', 'vendor']

    @action(detail=False, methods=['post'])
    def scan_rules(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        alerts_scanned = 0
        alerts_updated = 0

        for alert in queryset:
            alerts_scanned += 1
            matches = evaluate_alert_rules(alert)

            if not matches:
                continue

            best = max(
                matches,
                key=lambda r: r.get('materiality', 0) if r.get('materiality', None) is not None else 0,
            )

            new_severity = best.get('severity')
            new_materiality = best.get('materiality')

            changed = False

            if new_severity and alert.severity != new_severity:
                alert.severity = new_severity
                changed = True

            if new_materiality is not None and alert.materiality != new_materiality:
                alert.materiality = new_materiality
                changed = True

            if changed:
                alert.save()
                alerts_updated += 1

        return Response(
            {
                'alerts_scanned': alerts_scanned,
                'alerts_updated': alerts_updated,
            }
        )

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Exporta alertas filtrados para Excel."""
        queryset = self.filter_queryset(self.get_queryset())
        
        data = []
        for alert in queryset:
            data.append({
                'ID': alert.id,
                'Data': alert.timestamp.strftime('%Y-%m-%d %H:%M') if alert.timestamp else 'N/A',
                'Fornecedor': alert.vendor,
                'Valor': float(alert.amount) if alert.amount else 0.0,
                'Tipo': alert.alert_type,
                'Severidade': alert.severity,
                'Status': alert.status,
                'Materialidade/Risco': float(alert.materiality) if alert.materiality else 0.0,
                'Descrição': alert.description
            })
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Alertas')
        
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Alertas_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
        return response

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Exporta alertas filtrados para CSV."""
        queryset = self.filter_queryset(self.get_queryset())
        
        data = []
        for alert in queryset:
            data.append({
                'ID': alert.id,
                'Data': alert.timestamp.isoformat() if alert.timestamp else '',
                'Fornecedor': alert.vendor,
                'Valor': float(alert.amount) if alert.amount else 0.0,
                'Tipo': alert.alert_type,
                'Severidade': alert.severity,
                'Status': alert.status,
                'Risco': float(alert.materiality) if alert.materiality else 0.0
            })
            
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Alertas_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        df.to_csv(path_or_buf=response, index=False, encoding='utf-8-sig')
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        department = self.request.query_params.get('department')
        category = self.request.query_params.get('category')
        
        if department:
            # Filter by department via Transaction -> User -> ContextProfile
            # Note: transaction.user_id is a string, ContextProfile.user_id is a string
            user_ids = ContextProfile.objects.filter(department=department).values_list('user_id', flat=True)
            queryset = queryset.filter(transaction__user_id__in=user_ids)
            
        if category:
            queryset = queryset.filter(transaction__category=category)
            
        return queryset

    def perform_create(self, serializer):
        alert = serializer.save()
        
        # Check and execute risk agents for this alert
        try:
            from .ai_service import AuditAI
            ai = AuditAI(user_id=self.request.user.id if self.request.user.id else 'system')
            
            # Get all active risk agents
            from .models import RiskAgent
            active_agents = RiskAgent.objects.filter(active=True)
            
            for agent in active_agents:
                # Evaluate conditions against alert and transaction
                if agent.conditions:
                    try:
                        q_filter = ai._conditions_to_filter(agent.conditions)
                        # Check if alert's transaction matches conditions (if transaction exists)
                        match_found = False
                        if alert.transaction:
                            match_found = alert.transaction.id in alert.transaction.__class__.objects.filter(id=alert.transaction.id).filter(q_filter).values_list('id', flat=True)
                        # Also check alert-level fields if conditions include alert metrics
                        
                        if match_found:
                            # Execute external action if configured
                            execution = ai._execute_agent_external_action(
                                agent,
                                alert=alert,
                                transaction=alert.transaction
                            )
                            if execution:
                                print(f"External action executed: {agent.name} -> {execution.id}")
                    except Exception as e:
                        print(f"Error evaluating agent {agent.name} for alert {alert.id}: {e}")
        except Exception as e:
            print(f"Error running risk agents for alert {alert.id}: {e}")
        
        # Enviar webhook para sistemas externos
        try:
            from .webhook_service import WebhookService
            WebhookService.broadcast_event(
                'alert.created',
                {
                    'id': alert.id,
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'status': alert.status,
                    'materiality': float(alert.materiality) if alert.materiality else 0.0,
                    'vendor': alert.vendor,
                    'amount': float(alert.amount) if alert.amount else 0.0,
                    'description': alert.description,
                    'transaction_id': alert.transaction.id if alert.transaction else None,
                    'created_at': alert.timestamp.isoformat()
                }
            )
        except Exception as e:
            print(f"Erro ao enviar webhook para criação de alerta: {e}")

    def perform_update(self, serializer):
        old_instance = self.get_object()
        alert = serializer.save()
        
        # Enviar webhook de atualização
        try:
            from .webhook_service import WebhookService
            WebhookService.broadcast_event(
                'alert.updated',
                {
                    'id': alert.id,
                    'old_status': old_instance.status,
                    'new_status': alert.status,
                    'severity': alert.severity,
                    'materiality': float(alert.materiality) if alert.materiality else 0.0,
                    'updated_at': timezone.now().isoformat()
                }
            )
        except Exception as e:
            print(f"Erro ao enviar webhook para atualização de alerta: {e}")

class ContextProfileViewSet(viewsets.ModelViewSet):
    queryset = ContextProfile.objects.all()
    serializer_class = ContextProfileSerializer
    permission_classes = [IsViewerOrAbove]

    @action(detail=False, methods=['get', 'post', 'patch'])
    def current(self, request):
        # Assume single user for MVP or get from auth
        user_id = '1' # Default for now
        
        if request.method in ['POST', 'PATCH']:
            defaults = request.data.copy()
            # If onboarding_data is present, we might want to merge it instead of overwrite if doing PATCH, 
            # but update_or_create defaults replaces.
            # For PATCH, let's fetch first if we want to merge, but standard behavior is fine for now.
            
            profile, _ = ContextProfile.objects.update_or_create(
                user_id=user_id,
                defaults=defaults
            )
            return Response(ContextProfileSerializer(profile).data)
        
        profile, created = ContextProfile.objects.get_or_create(user_id=user_id, defaults={'persona': 'Standard Auditor'})
        return Response(ContextProfileSerializer(profile).data)

class RegulatoryRuleViewSet(viewsets.ModelViewSet):
    queryset = RegulatoryRule.objects.all()
    serializer_class = RegulatoryRuleSerializer
    permission_classes = [IsViewerOrAbove]

class ExternalSystemViewSet(viewsets.ModelViewSet):
    queryset = ExternalSystem.objects.all().order_by('-created_at')
    serializer_class = ExternalSystemSerializer
    permission_classes = [IsAuditorOrAdmin]

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Testa a conexão com o sistema externo"""
        system = self.get_object()
        try:
            # Implementação básica de teste (expandir conforme tipo de sistema)
            if system.base_url:
                import requests
                response = requests.get(system.base_url, timeout=5)
                return Response({'status': 'success', 'status_code': response.status_code})
            return Response({'status': 'success', 'message': 'Configuração salva (sem URL base para teste)'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

    @action(detail=True, methods=['post'])
    def trigger_ingest(self, request, pk=None):
        """Dispara a ingestão manualmente"""
        system = self.get_object()
        system.last_ingest_at = timezone.now()
        system.save()
        return Response({'status': 'success', 'message': 'Ingestão iniciada'})

class WebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WebhookEvent.objects.all().order_by('-created_at')
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuditorOrAdmin]

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry a specific failed webhook."""
        try:
            from .tasks import retry_webhook
            retry_webhook.delay(pk)
            return Response({'status': 'success', 'message': 'Retry scheduled'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def retry_all_failed(self, request):
        """Retry all failed webhooks."""
        try:
            from .tasks import retry_failed_webhooks
            retry_failed_webhooks.delay()
            return Response({'status': 'success', 'message': 'Retry all failed webhooks scheduled'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

class AuditRuleViewSet(viewsets.ModelViewSet):
    queryset = AuditRule.objects.all().order_by('-created_at')
    serializer_class = AuditRuleSerializer
    permission_classes = [IsAuditorOrAdmin]

class ExternalActionTemplateViewSet(viewsets.ModelViewSet):
    queryset = ExternalActionTemplate.objects.all().order_by('-created_at')
    serializer_class = ExternalActionTemplateSerializer
    permission_classes = [IsAuditorOrAdmin]
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test an external action template."""
        template = self.get_object()
        try:
            from .external_action_service import ExternalActionExecutor
            execution = ExternalActionExecutor.execute_template(template)
            return Response({'status': 'success', 'execution_id': execution.id})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

class ExternalActionExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExternalActionExecution.objects.all().order_by('-created_at')
    serializer_class = ExternalActionExecutionSerializer
    permission_classes = [IsAuditorOrAdmin]

class ContextDocumentViewSet(viewsets.ModelViewSet):
    queryset = ContextDocument.objects.all().order_by('-created_at')
    serializer_class = ContextDocumentSerializer
    permission_classes = [IsAuditorOrAdmin]

    def perform_create(self, serializer):
        doc = serializer.save()
        # Trigger RAG Processing
        from .ai_service import AuditAI
        ai = AuditAI()
        
        # 1. Extract Text
        ai.extract_text_from_file(doc)
        
        # 2. Generate Embedding (Local or API)
        success = ai.process_document_embedding(doc.id)
        
        if success:
            doc.ai_summary = f"Processed by Corporate Brain. Ready for RAG retrieval."
        else:
            doc.ai_summary = "Processing failed or pending."
            
        doc.save()

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Directly search the Corporate Brain (RAG).
        Query param: q
        """
        query = request.query_params.get('q', '')
        if not query:
            return Response({'error': 'Missing query parameter "q"'}, status=400)
            
        from .ai_service import AuditAI
        ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
        results = ai.query_corporate_brain(query)
        
        return Response({
            'query': query,
            'results': results
        })

    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        """Manually trigger reprocessing of a document"""
        doc = self.get_object()
        from .ai_service import AuditAI
        ai = AuditAI()
        
        # Only try to extract if file exists, otherwise rely on existing text
        if doc.file:
            ai.extract_text_from_file(doc)
            
        success = ai.process_document_embedding(doc.id)
        
        # Refresh to get updated fields (embedding_vector, chunks count)
        doc.refresh_from_db()
        
        return Response({
            'status': 'success' if success else 'failed',
            'extracted_text_preview': doc.extracted_text[:100] if doc.extracted_text else None,
            'has_embedding': bool(doc.embedding_vector)
        })

class IntegrationSettingsViewSet(viewsets.ModelViewSet):
    queryset = IntegrationSettings.objects.all()
    serializer_class = IntegrationSettingsSerializer
    permission_classes = [IsAuditorOrAdmin]

    @action(detail=False, methods=['get', 'patch'])
    def current(self, request):
        # Assume single user ID 1 for MVP
        user_id = 1
        settings, created = IntegrationSettings.objects.get_or_create(user_id=user_id)
        
        if request.method == 'PATCH':
            serializer = self.get_serializer(settings, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
            
        return Response(self.get_serializer(settings).data)

from rest_framework.decorators import action
from .ai_service import AuditAI

class AuditCaseViewSet(viewsets.ModelViewSet):
    queryset = AuditCase.objects.all().order_by('-updated_at')
    serializer_class = AuditCaseSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['status', 'priority', 'assigned_to', 'created_by', 'transaction_id']

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Exporta casos filtrados para Excel."""
        queryset = self.filter_queryset(self.get_queryset())
        
        data = []
        for case in queryset:
            data.append({
                'ID': case.id,
                'Título': case.title,
                'Descrição': case.description,
                'Status': case.status,
                'Prioridade': case.priority,
                'Responsável': case.assigned_to,
                'Transação ID': case.transaction_id,
                'Criado em': case.created_at.strftime('%Y-%m-%d %H:%M') if case.created_at else 'N/A',
                'Atualizado em': case.updated_at.strftime('%Y-%m-%d %H:%M') if case.updated_at else 'N/A'
            })
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Casos')
        
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Casos_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
        return response

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Exporta casos filtrados para CSV."""
        queryset = self.filter_queryset(self.get_queryset())
        
        data = []
        for case in queryset:
            data.append({
                'ID': case.id,
                'Titulo': case.title,
                'Status': case.status,
                'Prioridade': case.priority,
                'Responsavel': case.assigned_to,
                'TX_ID': case.transaction_id,
                'Atualizado': case.updated_at.isoformat() if case.updated_at else ''
            })
            
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Casos_Auditoria_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
        df.to_csv(path_or_buf=response, index=False, encoding='utf-8-sig')
        return response

    def perform_create(self, serializer):
        uid = str(getattr(getattr(self.request, 'user', None), 'id', 'system'))
        case = serializer.save(created_by=uid)
        
        # Smart Workflow: Auto-assign and Suggest Steps
        ai = AuditAI(user_id=uid)
        ai.auto_assign_case(case)
        
        # Enviar webhook para sistemas externos
        try:
            from .webhook_service import WebhookService
            WebhookService.broadcast_event(
                'case.created',
                {
                    'id': case.id,
                    'title': case.title,
                    'description': case.description,
                    'status': case.status,
                    'priority': case.priority,
                    'assigned_to': case.assigned_to,
                    'created_by': case.created_by,
                    'transaction_id': case.transaction_id,
                    'finding_type': case.finding_type,
                    'inherent_risk': float(case.inherent_risk) if case.inherent_risk else None,
                    'residual_risk': float(case.residual_risk) if case.residual_risk else None,
                    'created_at': case.created_at.isoformat()
                }
            )
        except Exception as e:
            print(f"Erro ao enviar webhook para criação de caso: {e}")

    def perform_update(self, serializer):
        old_instance = self.get_object()
        case = serializer.save()
        
        # Enviar webhook de atualização
        try:
            from .webhook_service import WebhookService
            WebhookService.broadcast_event(
                'case.updated',
                {
                    'id': case.id,
                    'title': case.title,
                    'old_status': old_instance.status,
                    'new_status': case.status,
                    'priority': case.priority,
                    'assigned_to': case.assigned_to,
                    'updated_at': case.updated_at.isoformat()
                }
            )
        except Exception as e:
            print(f"Erro ao enviar webhook para atualização de caso: {e}")
        
        closed_statuses = ['Resolved', 'Closed', 'Closed - Remediated', 'Closed - No Issue']
        if case.status in closed_statuses and old_instance.status not in closed_statuses:
            uid = str(getattr(getattr(self.request, 'user', None), 'id', 'system'))
            ai = AuditAI(user_id=uid)
            
            memory_text = (
                f"Caso de Auditoria Resolvido: {case.title}. "
                f"Descricao: {case.description}. "
                f"Prioridade: {case.priority}. "
                f"Resolvido em: {timezone.now().strftime('%d/%m/%Y')}. "
                f"Contexto: Transacao {case.transaction_id}."
            )
            
            comments = case.comments.all()
            if comments.exists():
                memory_text += " Notas de Investigacao: " + " ".join([c.comment for c in comments])
                
            ai.mem_service.add(
                memory_text,
                user_id=uid,
                metadata={"type": "case_resolution", "case_id": case.id, "priority": case.priority}
            )
            print(f"MEMORY: Case {case.id} added to institutional memory.")
            
            # Enviar webhook de resolução
            try:
                from .webhook_service import WebhookService
                WebhookService.broadcast_event(
                    'case.resolved',
                    {
                        'id': case.id,
                        'title': case.title,
                        'status': case.status,
                        'resolved_at': timezone.now().isoformat()
                    }
                )
            except Exception as e:
                print(f"Erro ao enviar webhook para resolução de caso: {e}")
        
    @action(detail=True, methods=['get'])
    def export_pdf(self, request, pk=None):
        case = self.get_object()
        uid = str(getattr(getattr(request, 'user', None), 'id', 'system'))
        ai = AuditAI(user_id=uid)
        
        # 1. Get rich data from AI Service
        report_data = ai.generate_case_report(case)
        
        # 2. Prepare Response
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Audit_Report_Case_{case.id}.pdf"'
        
        # 3. Create PDF
        doc = SimpleDocTemplate(response, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Custom styles
        from reportlab.lib.styles import ParagraphStyle
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            spaceAfter=20,
            textColor=colors.HexColor('#2c3e50')
        )
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.HexColor('#2980b9')
        )
        
        story = []
        
        # Header / Title
        story.append(Paragraph(f"Relatório de Investigação de Auditoria", title_style))
        story.append(Paragraph(f"Caso #{case.id}: {case.title}", styles['Heading3']))
        story.append(Spacer(1, 12))
        
        # Summary Table
        data = [
            ["Campo", "Informação"],
            ["Status", case.status],
            ["Prioridade", case.priority],
            ["Responsável", case.assigned_to or "Não atribuído"],
            ["Criado por", case.created_by],
            ["Data de Criação", case.created_at.strftime('%d/%m/%Y %H:%M')],
            ["ID Transação", case.transaction_id or "N/A"]
        ]
        t = Table(data, colWidths=[150, 300])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 20))
        
        # Executive Summary (AI Generated)
        story.append(Paragraph("Resumo Executivo (IA)", header_style))
        story.append(Paragraph(report_data.get('executive_summary', 'Sem resumo disponível.'), styles['Normal']))
        story.append(Spacer(1, 15))
        
        # Description
        story.append(Paragraph("Descrição do Caso", header_style))
        story.append(Paragraph(case.description or "Sem descrição fornecida.", styles['Normal']))
        story.append(Spacer(1, 15))
        
        # Risk Analysis
        story.append(Paragraph("Análise de Risco XAI", header_style))
        xai = report_data.get('risk_analysis', {}).get('xai_explanation', {})
        if xai and isinstance(xai, dict):
            reasons = xai.get('reasons', [])
            for reason in reasons:
                story.append(Paragraph(f"• {reason}", styles['Normal']))
        else:
            story.append(Paragraph("Nenhuma análise detalhada disponível.", styles['Normal']))
        story.append(Spacer(1, 15))
        
        # Investigation Log
        story.append(Paragraph("Histórico de Investigação", header_style))
        log_data = [["Usuário", "Data", "Ação/Comentário"]]
        for log in report_data.get('investigation_log', []):
            log_data.append([log['user'], log['date'], Paragraph(log['content'], styles['Normal'])])
        
        if len(log_data) > 1:
            lt = Table(log_data, colWidths=[80, 100, 320])
            lt.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(lt)
        else:
            story.append(Paragraph("Nenhum comentário registrado.", styles['Normal']))
            
        story.append(Spacer(1, 30))
        
        # Digital Signature Simulation
        import hashlib
        signature_content = f"{case.id}-{case.updated_at.isoformat()}-{uid}-AUDIT-VERIFIED"
        signature_hash = hashlib.sha256(signature_content.encode()).hexdigest()
        
        story.append(Paragraph("Assinatura Digital de Auditoria", header_style))
        sig_box_data = [
            [Paragraph(f"<b>Audit Verified:</b> Documento gerado e verificado pelo sistema de IA.", styles['Normal'])],
            [Paragraph(f"<b>Assinado por:</b> {uid}", styles['Normal'])],
            [Paragraph(f"<b>Timestamp:</b> {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal'])],
            [Paragraph(f"<b>Hash de Integridade:</b> <font face='Courier' size='8'>{signature_hash}</font>", styles['Normal'])]
        ]
        sig_table = Table(sig_box_data, colWidths=[450])
        sig_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#27ae60')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9f9f9')),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(sig_table)
        
        # Build PDF
        doc.build(story)
        return response

class AuditCaseCommentViewSet(viewsets.ModelViewSet):
    queryset = AuditCaseComment.objects.all().order_by('created_at')
    serializer_class = AuditCaseCommentSerializer
    permission_classes = [IsViewerOrAbove]
    filterset_fields = ['case', 'user_id']

    def perform_create(self, serializer):
        uid = str(getattr(getattr(self.request, 'user', None), 'id', 'system'))
        serializer.save(user_id=uid)

class AuditCaseAttachmentViewSet(viewsets.ModelViewSet):
    queryset = AuditCaseAttachment.objects.all().order_by('uploaded_at')
    serializer_class = AuditCaseAttachmentSerializer
    permission_classes = [IsAuditorOrAdmin]
    filterset_fields = ['case']
    parser_classes = [MultiPartParser]

    def perform_create(self, serializer):
        uid = str(getattr(getattr(self.request, 'user', None), 'id', 'system'))
        # If file_name is not provided, use the file's name
        file_obj = self.request.FILES.get('file')
        file_name = self.request.data.get('file_name')
        if not file_name and file_obj:
            file_name = file_obj.name
            
        serializer.save(uploaded_by=uid, file_name=file_name)

# Function Views

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def auto_cluster_alerts(request):
    """
    Groups 'New' alerts by vendor and creates Audit Cases for high-risk clusters.
    This enables efficient 100% sample analysis by reducing noise.
    """
    print("[DEBUG] Iniciando auto_cluster_alerts...")
    # 1. Fetch New Alerts
    new_alerts = Alert.objects.filter(status='New').select_related('transaction')
    print(f"[DEBUG] Encontrados {new_alerts.count()} alertas 'New'.")
    
    # 2. Group by Vendor
    clusters = {}
    for alert in new_alerts:
        vendor = alert.vendor or 'Unknown'
        if vendor not in clusters:
            clusters[vendor] = []
        clusters[vendor].append(alert)
    print(f"[DEBUG] Agrupados em {len(clusters)} clusters por fornecedor.")
        
    created_cases = []
    
    # 3. Analyze Clusters
    for vendor, alerts in clusters.items():
        print(f"[DEBUG] Analisando cluster: {vendor} ({len(alerts)} alertas)")
        # Heuristic: Create case if > 2 alerts or any Critical alert or high accumulated materiality
        is_critical = any(a.severity == 'Critical' for a in alerts)
        total_materiality = sum(a.materiality for a in alerts)
        
        # Thresholds: 3+ alerts OR Critical severity OR >1.5 total risk score
        if len(alerts) >= 3 or is_critical or total_materiality > 1.5:
            print(f"[DEBUG] Cluster {vendor} atingiu limite de risco. Criando caso...")
            # Find representative transaction (highest risk)
            highest_risk_alert = max(alerts, key=lambda a: a.materiality)
            
            case_title = f"Cluster Risk: {vendor} ({len(alerts)} Alerts)"
            priority = 'High' if is_critical or total_materiality > 2.0 else 'Medium'
            
            case_desc = (
                f"Auto-clustered {len(alerts)} alerts for vendor {vendor}.\n"
                f"Total Risk Score: {total_materiality:.2f}\n"
                f"Critical Alerts: {sum(1 for a in alerts if a.severity == 'Critical')}\n"
                f"Included Alert IDs: {', '.join([str(a.id) for a in alerts])}"
            )
            
            # Create Case
            case = AuditCase.objects.create(
                title=case_title,
                description=case_desc,
                status='New',
                priority=priority,
                created_by='AutoCluster',
                transaction_id=highest_risk_alert.transaction.transaction_id if highest_risk_alert.transaction else None
            )
            print(f"[DEBUG] Caso criado: ID {case.id}")

            # Smart Workflow: Auto-assign
            print(f"[DEBUG] Iniciando auto-atribuição para o caso {case.id}...")
            ai = AuditAI(user_id='AutoCluster')
            ai.auto_assign_case(case)
            print(f"[DEBUG] Caso {case.id} atribuído.")
            
            # Update Alerts to 'Investigating' to prevent re-clustering
            print(f"[DEBUG] Atualizando {len(alerts)} alertas para 'Investigating'...")
            for a in alerts:
                a.status = 'Investigating'
                a.save()
                
            created_cases.append({
                'id': case.id,
                'title': case.title,
                'alert_count': len(alerts),
                'priority': priority
            })
            
    print(f"[DEBUG] Finalizado auto_cluster_alerts. Criados {len(created_cases)} casos.")
    return Response({
        'cases_created': len(created_cases),
        'processed_alerts': sum(c['alert_count'] for c in created_cases),
        'details': created_cases
    })

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def audit_dashboard_stats(request):
    total_tx = Transaction.objects.count()
    high_risk = Alert.objects.filter(severity='High').count()
    open_cases = AuditCase.objects.exclude(status__startswith='Closed').count()
    
    # Logic for Overdue Cases (deadline < now AND not closed) OR (open > 7 days if no deadline)
    now = timezone.now()
    overdue_query = Q(status__in=['New', 'In Progress', 'Under Review']) & (
        (Q(deadline__lt=now)) | 
        (Q(deadline__isnull=True) & Q(created_at__lt=now - timedelta(days=7)))
    )
    overdue_cases = AuditCase.objects.filter(overdue_query).count()
    
    closed_high_prio_cases = AuditCase.objects.filter(status__startswith='Closed', priority__in=['High', 'Critical'])
    potential_savings = 0
    for case in closed_high_prio_cases:
        if case.transaction_id:
            try:
                t = Transaction.objects.get(transaction_id=case.transaction_id) # Fixed to use transaction_id string
                potential_savings += t.amount
            except:
                pass
                
    # If no string match, try PK match (legacy)
    if potential_savings == 0:
        for case in closed_high_prio_cases:
            if case.transaction_id and case.transaction_id.isdigit():
                 try:
                    t = Transaction.objects.get(id=int(case.transaction_id))
                    potential_savings += t.amount
                 except:
                    pass

    return Response({
        "transactions_today": Transaction.objects.filter(timestamp__gte=now.date()).count(),
        "alerts_today": Alert.objects.filter(timestamp__gte=now.date()).count(),
        "high_risk_total": high_risk,
        "open_cases": open_cases,
        "overdue_cases": overdue_cases,
        "potential_savings": potential_savings,
        "risk_trend": "stable"
    })

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def sla_stats(request):
    now = timezone.now()
    
    closed_cases = AuditCase.objects.filter(status__startswith='Closed')
    avg_resolution = closed_cases.annotate(
        duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
    ).aggregate(avg=Avg('duration'))['avg']
    
    # Convert to hours
    avg_hours = 0
    if avg_resolution:
        avg_hours = avg_resolution.total_seconds() / 3600
        
    open_overdue = AuditCase.objects.exclude(status__startswith='Closed').filter(deadline__lt=now).count()
    
    closed_overdue = AuditCase.objects.filter(status__startswith='Closed', deadline__lt=F('updated_at')).count()
    
    total_breaches = open_overdue + closed_overdue
    total_cases = AuditCase.objects.count()
    
    compliance_rate = 100.0
    if total_cases > 0:
        compliance_rate = ((total_cases - total_breaches) / total_cases) * 100
        
    # By Auditor
    auditor_stats = AuditCase.objects.values('assigned_to').annotate(
        total=Count('id'),
        closed=Count('id', filter=Q(status__startswith='Closed')),
        overdue=Count('id', filter=Q(deadline__lt=now) & ~Q(status__startswith='Closed'))
    ).order_by('-total')
    
    return Response({
        'avg_resolution_hours': round(avg_hours, 1),
        'total_breaches': total_breaches,
        'compliance_rate': round(compliance_rate, 1),
        'active_overdue': open_overdue,
        'auditor_stats': auditor_stats
    })

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def ai_user_insights(request):
    from .ai_service import AuditAI
    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    return Response(ai.generate_user_insights())

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def executive_summary(request):
    from .ai_service import AuditAI
    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    return Response(ai.generate_executive_summary())

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def forecast_risk(request):
    now = timezone.now()
    start_date = now - timedelta(days=180) # Increased history to 6 months
    history = Alert.objects.filter(timestamp__gte=start_date).annotate(week=TruncWeek('timestamp')).values('week').annotate(count=Count('id'), avg_materiality=Avg('materiality')).order_by('week')
    
    # Prepare time series data
    series = []
    if not history:
        return Response({
            'forecast_dates': [(now + timedelta(weeks=i)).strftime('%Y-%m-%d') for i in range(1, 13)],
            'predicted_risk_score': [0] * 12,
            'confidence_interval': 0.0,
            'insight': 'Sem dados históricos suficientes para previsão.'
        })

    # Fill missing weeks with 0
    history_dict = {h['week'].strftime('%Y-%m-%d'): (h['count'] * (h['avg_materiality'] or 0)) / 10.0 for h in history}
    
    # Generate full weekly timeline
    current_loop_date = start_date
    while current_loop_date <= now:
        d_str = current_loop_date.strftime('%Y-%m-%d')
        # Find closest week start or just match loosely
        # Simplified: just append known values, in real world we align weeks strictly
        val = 0
        for k, v in history_dict.items():
            # If date is within the same week
            k_date = parser.parse(k).date()
            if abs((k_date - current_loop_date.date()).days) < 4:
                val = v
                break
        series.append(val)
        current_loop_date += timedelta(weeks=1)

    # Double Exponential Smoothing (Holt's Linear Trend)
    # Parameters (alpha: level smoothing, beta: trend smoothing)
    alpha = 0.5
    beta = 0.3
    
    n = len(series)
    if n < 2:
        # Fallback to simple average
        forecast_val = sum(series)/n if n > 0 else 0
        predictions = [forecast_val] * 12
        sigma = 0
    else:
        # Initialization
        level = series[0]
        trend = series[1] - series[0]
        
        smoothed = []
        residuals = []
        
        for t in range(n):
            if t == 0:
                smoothed.append(level)
                continue
            
            last_level = level
            last_trend = trend
            
            # Update equations
            level = alpha * series[t] + (1 - alpha) * (last_level + last_trend)
            trend = beta * (level - last_level) + (1 - beta) * last_trend
            
            smoothed.append(level)
            
            # Calculate residual (error)
            pred = last_level + last_trend
            residuals.append(series[t] - pred)
            
        # Calculate standard deviation of residuals (for confidence interval)
        if residuals:
            variance = sum(r*r for r in residuals) / len(residuals)
            sigma = variance ** 0.5
        else:
            sigma = 0.1 # Default small sigma

    # Forecast future with expanding uncertainty cone
    predictions = []
    upper_bounds = []
    lower_bounds = []
    
    # Standard error of forecast roughly grows with sqrt(h) in random walk, 
    # but in Holt's it's more complex. We'll approximate with sigma * sqrt(h).
    import math
    
    for i in range(1, 13):
        # h = i (1 to 12 steps ahead)
        pred = level + i * trend
        
        # Uncertainty cone: 1.96 * sigma * sqrt(i)
        uncertainty = 1.96 * sigma * math.sqrt(i)
        
        predictions.append(max(0, round(pred, 2)))
        upper_bounds.append(round(pred + uncertainty, 2))
        lower_bounds.append(max(0, round(pred - uncertainty, 2)))

    # Determine Trend Insight
    trend_msg = "estável"
    trend_direction = "stable"
    if n >= 2:
        if trend > 0.05: 
            trend_msg = "tendência de alta (Alerta!)"
            trend_direction = "up"
        elif trend > 0: 
            trend_msg = "leve crescimento"
            trend_direction = "up_slight"
        elif trend < -0.05: 
            trend_msg = "tendência de queda (Melhoria)"
            trend_direction = "down"
        elif trend < 0: 
            trend_msg = "leve redução"
            trend_direction = "down_slight"

    # Dynamic Confidence Interval (95% -> 1.96 sigma)
    # We return normalized confidence (0 to 1 scale for UI)
    confidence_metric = max(0, min(1.0, 1.0 - (sigma / 5.0)))

    return Response({
        'forecast_dates': [(now + timedelta(weeks=i)).strftime('%Y-%m-%d') for i in range(1, 13)],
        'predicted_risk_score': predictions,
        'upper_bounds': upper_bounds,
        'lower_bounds': lower_bounds,
        'confidence_interval': round(confidence_metric, 2),
        'trend_direction': trend_direction,
        'insight': f'Modelo Holt-Winters (Otimizado) detectou {trend_msg}. Volatilidade do risco: {"Alta" if sigma > 2 else "Baixa"}.'
    })

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def submit_ai_feedback(request):
    user_id = str(getattr(getattr(request, 'user', None), 'id', 'anonymous'))
    transaction_id = request.data.get('transaction_id')
    feedback_type = request.data.get('feedback_type')
    comment = request.data.get('comment')
    
    # DPO Fields
    input_context = request.data.get('input_context')
    ai_response = request.data.get('ai_response')
    human_correction = request.data.get('human_correction')
    model_version = request.data.get('model_version', 'DeepSeek-R1-Distill-Llama-8B') # Default to target model
    
    if not transaction_id or not feedback_type:
        return Response({'error': 'Missing required fields'}, status=400)
    
    AiFeedback.objects.create(
        transaction_id=transaction_id,
        user_id=user_id,
        feedback_type=feedback_type,
        comment=comment,
        created_at=timezone.now(),
        input_context=input_context,
        ai_response=ai_response,
        human_correction=human_correction,
        model_version=model_version
    )

    # Check Active Learning Setting
    active_learning = True
    try:
        if user_id and user_id != 'anonymous' and user_id.isdigit():
             settings = IntegrationSettings.objects.filter(user_id=int(user_id)).first()
             if settings:
                 active_learning = settings.active_learning
    except:
        pass

    if active_learning:
        # Add to Persistent Memory (Mem0)
        try:
            from .ai_service import PersistentMemory
            mem_service = PersistentMemory.get_instance()
            
            # Construct a meaningful memory string for future retrieval
            memory_text = f"Feedback on {transaction_id}: {comment}. Type: {feedback_type}."
            if feedback_type == 'inaccurate':
                memory_text += " The user marked this as False Positive (Safe). Adjust future risk scores down."
            elif feedback_type == 'accurate':
                 memory_text += " The user confirmed this risk. Maintain or increase vigilance."

            mem_service.add(memory_text, user_id=user_id, metadata={"transaction_id": transaction_id, "feedback_type": feedback_type})
        except Exception as e:
            print(f"Failed to add to persistent memory: {e}")

    return Response({'status': 'Feedback recorded', 'message': 'Thank you! The model will learn from this.' if active_learning else 'Feedback recorded (Active Learning disabled).'})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def graph_analysis(request, pk=None):
    nodes = []
    links = []
    
    if not pk:
        pk = request.query_params.get('pk')
    
    if not pk:
        # Global view: Show high risk transactions and their network
        # Find transactions with high materiality alerts
        high_risk_alerts = Alert.objects.filter(materiality__gt=0.7).select_related('transaction')[:20]
        
        processed_tx_ids = set()
        
        for alert in high_risk_alerts:
            txn = alert.transaction
            if not txn or txn.id in processed_tx_ids:
                continue
                
            processed_tx_ids.add(txn.id)
            
            # Add transaction node
            nodes.append({
                "id": str(txn.id), 
                "type": "transaction", 
                "label": f"Tx {str(txn.id)[:8]}", 
                "val": 20, 
                "risk": alert.materiality
            })
            
            # Add vendor node
            if txn.vendor:
                if not any(n['id'] == txn.vendor for n in nodes):
                    nodes.append({"id": txn.vendor, "type": "vendor", "label": txn.vendor, "val": 15})
                links.append({"source": str(txn.id), "target": txn.vendor})
            
            # Add user node
            if txn.user_id:
                if not any(n['id'] == txn.user_id for n in nodes):
                    nodes.append({"id": txn.user_id, "type": "user", "label": f"User {txn.user_id}", "val": 15})
                links.append({"source": str(txn.id), "target": txn.user_id})

        return Response({'nodes': nodes, 'links': links})

    # Transaction specific view
    txn = Transaction.objects.filter(id=pk).first()
    if not txn:
        return Response({'error': 'Transaction not found'}, status=404)
        
    main_risk = 0
    main_alerts = Alert.objects.filter(transaction=txn)
    if main_alerts.exists():
        main_risk = main_alerts.aggregate(Max('materiality'))['materiality__max'] or 0

    nodes.append({"id": str(txn.id), "type": "transaction", "label": f"Tx {str(txn.id)[:8]}", "val": 20, "risk": main_risk})
    
    if txn.vendor:
        nodes.append({"id": txn.vendor, "type": "vendor", "label": txn.vendor, "val": 15})
        links.append({"source": str(txn.id), "target": txn.vendor})
        
        others = Transaction.objects.filter(vendor=txn.vendor).exclude(id=txn.id).order_by('-timestamp')[:5]
        
        # Collusion Logic: Check if all recent transactions for this vendor are approved by the same user
        users_involved = set()
        if txn.user_id: users_involved.add(txn.user_id)

        for o in others:
            o_risk = 0
            o_alerts = Alert.objects.filter(transaction=o)
            if o_alerts.exists():
                o_risk = o_alerts.aggregate(Max('materiality'))['materiality__max'] or 0

            nodes.append({"id": str(o.id), "type": "transaction", "label": f"Tx {str(o.id)[:8]}", "val": 10, "risk": o_risk})
            links.append({"source": txn.vendor, "target": str(o.id)})
            
            # Add user for related transactions to detect collusion
            if o.user_id:
                users_involved.add(o.user_id)
                # Check if node already exists
                if not any(n['id'] == o.user_id for n in nodes):
                    nodes.append({"id": o.user_id, "type": "user", "label": f"User {o.user_id}", "val": 15})
                # Link related tx to its user
                links.append({"source": str(o.id), "target": o.user_id})
            
    if txn.user_id:
        if not any(n['id'] == txn.user_id for n in nodes):
             nodes.append({"id": txn.user_id, "type": "user", "label": f"User {txn.user_id}", "val": 15})
        links.append({"source": str(txn.id), "target": txn.user_id})
    
    # Collusion Analysis Result
    collusion_risk = None
    if len(others) >= 2 and len(users_involved) == 1 and txn.user_id:
         collusion_risk = {
             "detected": True,
             "message": f"Possible Collusion: User {txn.user_id} is the sole approver for {len(others)+1} recent transactions with {txn.vendor}. This violates segregation of duties patterns."
         }
    
    return Response({"nodes": nodes, "links": links, "collusion_risk": collusion_risk})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def analyze_root_cause(request, pk):
    from .ai_service import AuditAI
    try:
        txn = Transaction.objects.get(pk=pk)
    except Transaction.DoesNotExist:
        # Try alert
        try:
            alert = Alert.objects.get(pk=pk)
            if alert.transaction_id:
                try:
                    txn = Transaction.objects.get(pk=alert.transaction_id)
                except Transaction.DoesNotExist:
                    return Response({
                        "root_cause": alert.alert_type,
                        "confidence": alert.materiality,
                        "contributing_factors": [alert.description],
                        "recommended_action": "Review Alert Manually",
                        "ai_summary": "Alert linked to missing transaction."
                    })
            else:
                 return Response({
                    "root_cause": alert.alert_type,
                    "confidence": alert.materiality,
                    "contributing_factors": [alert.description],
                    "recommended_action": "Review Alert Manually",
                    "ai_summary": "Alert analysis limited (no transaction linked)."
                 })
        except Alert.DoesNotExist:
             return Response({"error": "Transaction or Alert not found"}, status=404)

    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    context = ai.build_user_context()
    analysis = ai.analyze_transaction_risk(txn, context=context)
    
    return Response({
        "root_cause": analysis['reasons'][0] if analysis['reasons'] else "Unknown Risk Pattern",
        "confidence": analysis['risk_score'],
        "contributing_factors": analysis['reasons'],
        "recommended_action": "Investigate Vendor Relationship" if "Vendor" in str(analysis['reasons']) else "Review Transaction Details",
        "ai_summary": f"AI detected {len(analysis['reasons'])} risk factors. Risk Score: {int(analysis['risk_score']*100)}%.",
        "ai_context": analysis['ai_context'],
        "xai_explanation": analysis.get('xai_explanation')
    })

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def suggest_rules(request):
    from django.db.models import Avg, Count
    suggestions = []
    
    # Suggestion 1: High Risk Vendors
    # Find vendors with multiple high-risk alerts
    risky_vendors = Alert.objects.filter(materiality__gt=0.7).values('vendor').annotate(
        risk_count=Count('id'),
        avg_risk=Avg('materiality')
    ).filter(risk_count__gte=2)
    
    for v in risky_vendors:
        vendor_name = v['vendor']
        if vendor_name:
            suggestions.append({
                'id': f'sugg_vendor_{vendor_name}',
                'title': f'Monitor Risky Vendor: {vendor_name}',
                'description': f'Vendor {vendor_name} has {v["risk_count"]} high-risk alerts (Avg: {v["avg_risk"]:.2f}). Suggest creating an automated review rule.',
                'suggested_rule': {
                    'name': f'Auto-Review {vendor_name}',
                    'conditions': [
                        {'metric': 'vendor', 'operator': '==', 'value': vendor_name},
                        {'metric': 'risk_score', 'operator': '>', 'value': '0.5'}
                    ],
                    'action': 'review'
                }
            })

    # Suggestion 2: High Value Transactions
    # Suggest rule for very large amounts if not already present
    suggestions.append({
        'id': 'sugg_high_value',
        'title': 'High Value Protocol',
        'description': 'Standard protocol: Freeze payments over $50,000 for manual sign-off.',
        'suggested_rule': {
            'name': 'Freeze Large Amounts',
            'conditions': [
                {'metric': 'amount', 'operator': '>', 'value': '50000'}
            ],
            'action': 'freeze'
        }
    })

    return Response({'suggestions': suggestions})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def geo_risks(request):
    from django.db.models import Sum, Count
    country_stats = {}
    alerts = Alert.objects.all().select_related()
    for alert in alerts:
        country = 'Unknown'
        try:
            txn = Transaction.objects.filter(id=alert.transaction_id).first()
            if txn and txn.user_id:
                prof = ContextProfile.objects.filter(user_id=txn.user_id).first()
                if prof and prof.country:
                    country = prof.country
        except:
            pass
        if country == 'Unknown':
            rule = RegulatoryRule.objects.filter(alert_type=alert.alert_type).first()
            if rule:
                country = rule.country
        if country not in country_stats:
            country_stats[country] = {'risk_score': 0, 'alert_count': 0}
        country_stats[country]['alert_count'] += 1
        country_stats[country]['risk_score'] += (alert.materiality or 0)
    country_coords = {
        'Brazil': [-14.235, -51.925], 'Brasil': [-14.235, -51.925],
        'USA': [37.090, -95.712], 'United States': [37.090, -95.712],
        'Germany': [51.165, 10.451], 'Alemanha': [51.165, 10.451],
        'China': [35.861, 104.195],
        'India': [20.593, 78.962],
        'Nigeria': [9.082, 8.675],
        'UK': [55.378, -3.436], 'Reino Unido': [55.378, -3.436],
        'France': [46.227, 2.213], 'França': [46.227, 2.213],
        'Unknown': [0, 0]
    }
    results = []
    for c, stats in country_stats.items():
        if c == 'Unknown': continue
        avg_risk = stats['risk_score'] / stats['alert_count'] if stats['alert_count'] > 0 else 0
        coords = country_coords.get(c, [0, 0])
        results.append({
            'country': c,
            'risk_score': min(100, avg_risk / 100),
            'alert_count': stats['alert_count'],
            'coordinates': coords
        })
    return Response(results)

@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@parser_classes([MultiPartParser])
def upload_document(request):
    from .ai_service import AuditAI
    import hashlib
    from django.utils.text import slugify
    from django.utils import timezone

    file = request.FILES.get('file')
    title = request.data.get('title')
    doc_type = request.data.get('doc_type')
    country = request.data.get('country')
    transaction_id = request.data.get('transaction_id')
    
    if not file:
        return Response({'error': 'No file'}, status=400)

    # Security: File Size Check (e.g., max 10MB)
    if file.size > 10 * 1024 * 1024:
        return Response({'error': 'File too large (max 10MB)'}, status=400)

    # Security: File Extension Check
    allowed_extensions = ['.pdf', '.txt', '.csv', '.md', '.docx', '.xlsx']
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in allowed_extensions:
        return Response({'error': f'Unsupported file type: {ext}'}, status=400)

    # Security: Sanitize Filename
    original_name = os.path.splitext(file.name)[0]
    safe_name = f"{slugify(original_name)}_{int(timezone.now().timestamp())}{ext}"
    file.name = safe_name

    # Security: Calculate Hash
    hasher = hashlib.sha256()
    for chunk in file.chunks():
        hasher.update(chunk)
    file_hash = hasher.hexdigest()

    # Check for duplicates (optional, but good for security/cleanliness)
    if ContextDocument.objects.filter(file_hash=file_hash).exists():
        return Response({'error': 'Duplicate file detected'}, status=409)

    # Security: Virus Scan
    from .security_service import scan_file
    scan_status, scan_msg = scan_file(file, file_hash)
    
    if scan_status == 'Infected':
        return Response({'error': f'Security Alert: {scan_msg}'}, status=400)

    user_id = str(getattr(getattr(request, 'user', None), 'id', 'system'))

    rec = ContextDocument.objects.create(
        title=title or original_name,
        doc_type=doc_type,
        file=file,
        country=country,
        transaction_id=transaction_id,
        uploaded_by=user_id,
        file_hash=file_hash,
        scan_status=scan_status,
        scan_date=timezone.now()
    )

    # Trigger AI Processing (Extracts text & Embeds)
    try:
        # Simple Text Extraction (for .txt, .md, .csv)
        if ext in ['.txt', '.md', '.csv']:
             rec.extracted_text = file.read().decode('utf-8', errors='ignore')
             rec.save()
        
        # Process (Handles PDF extraction internally if text missing)
        ai = AuditAI(user_id=user_id)
        ai.process_document_embedding(rec.id)
    except Exception as e:
        print(f"Error processing document {rec.id}: {e}")

    return Response({'status': 'ok', 'id': rec.id})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def export_alerts(request):
    import csv
    response = StreamingHttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="alerts.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Timestamp', 'Vendor', 'Risk Score', 'Status'])
    
    alerts = Alert.objects.all().values_list('id', 'timestamp', 'vendor', 'materiality', 'status')
    for alert in alerts:
        writer.writerow(alert)
        
    return response

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def export_transactions(request):
    import csv
    response = StreamingHttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Timestamp', 'Vendor', 'Amount', 'Status'])
    
    txs = Transaction.objects.all().values_list('id', 'timestamp', 'vendor', 'amount', 'status')
    for tx in txs:
        writer.writerow(tx)
        
    return response

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
@parser_classes([MultiPartParser])
def upload_samples(request):
    """
    Upload de amostras (CSV e Excel) — delega o parsing pesado ao Excel Studio
    (excel_service) e usa bulk_create para performance.
    Compatível com a resposta anterior ({status, imported_count, errors, message}).
    """
    import uuid
    from . import excel_service as es

    files = request.FILES.getlist('files')
    if not files:
        return Response({'error': 'No files provided'}, status=400)

    total_imported = 0
    errors = []

    for file in files:
        try:
            name = file.name or ''
            if not name.lower().endswith(es.SUPPORTED_EXTENSIONS):
                errors.append(f"Skipped {name}: Only CSV/Excel supported ({es.SUPPORTED_EXTENSIONS}).")
                continue

            frames = es.read_uploaded_file(file.read(), name)
            sheet = es.pick_best_sheet(frames)
            df = frames[sheet]
            mapping = es.map_columns([str(c) for c in df.columns])
            rows, skipped = es.standardize_frame(df, mapping)
            for s in skipped[:20]:
                errors.append(f"{name}: linha {s['row']} ignorada ({s['reason']})")

            if not rows:
                errors.append(f"{name}: nenhuma linha válida encontrada (verifique cabeçalhos).")
                continue

            # Deduplica dentro do próprio ficheiro (mantém a 1ª ocorrência)
            seen, unique_rows = set(), []
            for r in rows:
                if r['transaction_id'] in seen:
                    continue
                seen.add(r['transaction_id'])
                unique_rows.append(r)

            existing = set(Transaction.objects.filter(
                transaction_id__in=[r['transaction_id'] for r in unique_rows]
            ).values_list('transaction_id', flat=True))

            to_create = [Transaction(**r) for r in unique_rows
                         if r['transaction_id'] not in existing]
            created = len(Transaction.objects.bulk_create(to_create, batch_size=500))
            total_imported += created

            ExcelImportJob.objects.create(
                file_name=name,
                uploaded_by=str(getattr(getattr(request, 'user', None), 'id', 'system') or 'system'),
                sheet=sheet,
                rows_imported=created,
                rows_skipped=len(rows) - created,
                mapping=mapping,
                status='Completed',
            )
        except Exception as e:
            errors.append(f"Error processing {file.name}: {str(e)}")

    return Response({
        'status': 'completed',
        'imported_count': total_imported,
        'errors': errors,
        'message': f"Imported {total_imported} transactions. Ready for analysis."
    })

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def process_pending_analysis(request):
    from .ai_service import AuditAI
    
    limit = int(request.data.get('limit', 10))
    pending_txs = Transaction.objects.filter(status='Pending')[:limit]
    
    processed_count = 0
    
    for txn in pending_txs:
        try:
            ai = AuditAI(user_id=str(txn.user_id) if txn.user_id else 'system')
            analysis = ai.analyze_transaction_risk(txn)
            
            # Save XAI log
            txn.xai_explanation = analysis.get('xai_explanation')
            
            # Create Alert logic
            risk_score = analysis.get('risk_score', 0)
            triggered_agents = analysis.get('triggered_agents', [])
            should_auto_resolve = any(a.get('action') == 'auto_resolve' for a in triggered_agents)

            if risk_score > 0.3 or should_auto_resolve:
                 severity = 'Low'
                 if risk_score > 0.7: severity = 'High'
                 elif risk_score > 0.5: severity = 'Medium'
                 
                 status = 'New'
                 description = f"AI Risk Score: {int(risk_score*100)}%. Factors: {', '.join(analysis.get('reasons', []))}"
                 
                 if should_auto_resolve:
                     status = 'False Positive'
                     description = f"[AUTO-RESOLVED] {description}"
                 
                 Alert.objects.create(
                    transaction=txn,
                    alert_type='AI Risk Analysis',
                    severity=severity,
                    status=status,
                    description=description,
                    vendor=txn.vendor,
                    amount=txn.amount,
                    materiality=risk_score
                )
            
            txn.status = 'Analyzed'
            txn.save()
            processed_count += 1
            
        except Exception as e:
            print(f"Error analyzing tx {txn.id}: {e}")
            txn.status = 'Error'
            txn.save()
            
    remaining = Transaction.objects.filter(status='Pending').count()
    
    return Response({
        'processed': processed_count,
        'remaining': remaining,
        'status': 'processing' if remaining > 0 else 'done'
    })

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def my_profile(request):
    user_id = str(getattr(getattr(request, 'user', None), 'id', 'system'))
    profile = ContextProfile.objects.filter(user_id=user_id).first()
    if not profile:
        return Response({})
    
    data = ContextProfileSerializer(profile).data
    
    # Adaptive Layout Logic based on Persona
    layout_config = {
        'show_stats': True,
        'show_charts': True,
        'show_recent_alerts': True,
        'show_recent_transactions': True,
        'layout_mode': 'standard',
        'welcome_message': f"Bem-vindo, {profile.persona}"
    }
    
    if profile.persona == 'Skeptical Analyst':
        layout_config.update({
            'show_charts': False, # Analyst prefers raw data tables
            'layout_mode': 'dense',
            'welcome_message': "Painel de Análise Detalhada"
        })
    elif profile.persona == 'Executive':
        layout_config.update({
            'show_recent_transactions': False, # Exec doesn't need row-level details
            'show_recent_alerts': False, # Exec needs summary only
            'layout_mode': 'summary',
            'welcome_message': "Visão Executiva de Riscos"
        })
        
    data['layout_config'] = layout_config
    return Response(data)

@api_view(['POST', 'PATCH'])
@permission_classes([IsViewerOrAbove])
def upsert_profile(request):
    user_id = str(getattr(getattr(request, 'user', None), 'id', 'system'))
    data = request.data
    profile, created = ContextProfile.objects.update_or_create(
        user_id=user_id,
        defaults=data
    )
    return Response(ContextProfileSerializer(profile).data)

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def analyze_regulation(request):
    text = request.data.get('text', '')
    transaction_id = request.data.get('transaction_id')
    
    # If transaction_id provided, fetch its details to enrich text
    if transaction_id:
        try:
            tx = Transaction.objects.get(id=transaction_id)
            text += f" Transaction {tx.id} for {tx.vendor} amount {tx.amount} {tx.currency}."
        except Transaction.DoesNotExist:
            pass

    if not text:
         return Response({'analysis': 'No text provided for analysis.', 'matches': []})

    # Simple keyword matching against RegulatoryRule
    matches = []
    rules = RegulatoryRule.objects.filter(active=True)
    for rule in rules:
        # Check if rule.regulation or keywords in text
        if rule.regulation.lower() in text.lower() or rule.alert_type.lower() in text.lower():
            matches.append({
                'regulation': rule.regulation,
                'alert_type': rule.alert_type,
                'description': rule.description,
                'country': rule.country
            })
    return Response({'analysis': f"Analyzed {len(rules)} rules.", 'matches': matches})

@api_view(['GET'])
@permission_classes([IsAuditorOrAdmin])
def generate_case_report(request, pk):
    try:
        case = AuditCase.objects.get(pk=pk)
    except AuditCase.DoesNotExist:
        return Response({'error': 'Case not found'}, status=404)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="AuditCase_{case.id}_Report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(f"Audit Case Report: #{case.id}", styles['Title']))
    story.append(Spacer(1, 12))

    # Details
    story.append(Paragraph(f"<b>Title:</b> {case.title}", styles['Normal']))
    story.append(Paragraph(f"<b>Status:</b> {case.status}", styles['Normal']))
    story.append(Paragraph(f"<b>Priority:</b> {case.priority}", styles['Normal']))
    story.append(Paragraph(f"<b>Assigned To:</b> {case.assigned_to or 'Unassigned'}", styles['Normal']))
    story.append(Paragraph(f"<b>Created By:</b> {case.created_by}", styles['Normal']))
    story.append(Paragraph(f"<b>Created At:</b> {case.created_at.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Description:</b>", styles['Heading2']))
    story.append(Paragraph(case.description or "No description.", styles['Normal']))
    story.append(Spacer(1, 12))

    # Comments
    comments = case.comments.all().order_by('-created_at')
    if comments:
        story.append(Paragraph("<b>Comments History:</b>", styles['Heading2']))
        data = [['User', 'Comment', 'Date']]
        for c in comments:
            data.append([c.user_id, c.comment[:100], c.created_at.strftime('%Y-%m-%d')])
        
        t = Table(data, colWidths=[100, 300, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(t)

    try:
        doc.build(story)
    except Exception as e:
        return Response({'error': f"PDF Generation Error: {str(e)}"}, status=500)
        
    return response

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def analyze_news(request):
    vendor = request.data.get('vendor')
    if not vendor:
        return Response({'news': [], 'sentiment': 'neutral'})

    # Mock News API
    # In production, this would call Google News API or similar
    import random
    
    news_items = []
    sentiment = 'neutral'
    
    # Deterministic mock for demo purposes
    if 'Tech' in vendor or 'Consulting' in vendor:
        news_items.append({
            'title': f"{vendor} announces record profits",
            'source': 'Financial Times',
            'date': '2023-10-25',
            'sentiment': 'positive'
        })
        sentiment = 'positive'
    elif 'Global' in vendor or 'Services' in vendor:
        news_items.append({
            'title': f"Investigation opened into {vendor} accounting practices",
            'source': 'Reuters',
            'date': '2023-10-20',
            'sentiment': 'negative'
        })
        sentiment = 'negative'
    else:
        news_items.append({
            'title': f"{vendor} expands into new markets",
            'source': 'Local Business',
            'date': '2023-10-22',
            'sentiment': 'neutral'
        })

    return Response({
        'vendor': vendor,
        'news': news_items,
        'sentiment': sentiment,
        'risk_score': 0.8 if sentiment == 'negative' else 0.1
    })

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def wizard(request):
    return Response({'status': 'Wizard completed'})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def fetch_news_sources(request):
    return Response({'sources': []})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def fetch_regulatory_sources(request):
    return Response({'sources': []})

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def context_stats(request):
    from django.db.models import Count, Avg, Q
    from .models import Alert
    from .ai_service import AuditAI
    
    # Use AuditAI for consistent department risk logic
    ai = AuditAI()
    dept_results = ai.get_department_risk_stats()
    
    # Reference List Stats
    ref_stats = ReferenceList.objects.annotate(
        item_count=Count('items'),
        high_risk_items=Count('items', filter=Q(items__risk_factor__gt=1.0))
    ).values('name', 'item_count', 'high_risk_items')
    
    # Risk by Category
    cat_results = ai.get_category_risk_stats()
    
    return Response({
        'departments': dept_results,
        'references': list(ref_stats),
        'categories': cat_results
    })

@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
def audit_chat(request):
    from .ai_service import AuditAI
    query = request.data.get('query')
    if not query:
        return Response({'error': 'No query provided'}, status=400)
        
    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    
    # Check for external signal queries
    if 'extern' in query.lower() or 'sinal' in query.lower() or 'signal' in query.lower():
        signals = IngestedSignal.objects.order_by('-created_at')[:5]
        if not signals:
            return Response({'type': 'message', 'content': 'Não encontrei nenhum sinal externo recente.'})
        
        signal_list = "\n".join([f"- {s.signal_type} de {s.source.name} em {s.created_at.strftime('%d/%m %H:%M')}" for s in signals])
        return Response({'type': 'message', 'content': f"Aqui estão os sinais externos mais recentes:\n{signal_list}"})

    response = ai.process_natural_language_query(query)
    
    # If not matched by simple intents, use LLM (mocked for now or use the _query_llm if configured)
    if response['content'] == "I didn't understand that query.":
         # Fallback to "I am still learning" or similar
         response['content'] = "Ainda estou aprendendo a processar consultas livres. Tente comandos como 'Resumo de hoje', 'Mostrar riscos altos', 'Sinais externos' ou 'Criar caso para transação 123'."
         
    return Response(response)

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def execute_ai_action(request):
    from .ai_service import AuditAI
    action_id = request.data.get('action_id')
    action_type = request.data.get('action_type')
    params = request.data.get('params', {})
    
    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    result = ai.execute_suggestion_action(action_id, action_type, params)
    
    return Response(result)

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def simulate_rule(request):
    from django.db.models import Q, Sum, Count
    from django.db.models.functions import TruncDay
    conditions = request.data.get('conditions', [])
    start_date_str = request.data.get('start_date')
    end_date_str = request.data.get('end_date')

    if not conditions:
        return Response({'count': 0, 'total_amount': 0, 'matches': [], 'daily_stats': []})

    query = Q()
    
    # Date filtering
    if start_date_str:
        try:
            start_date = parser.parse(start_date_str)
            query &= Q(timestamp__gte=start_date)
        except:
            pass
            
    if end_date_str:
        try:
            end_date = parser.parse(end_date_str)
            query &= Q(timestamp__lte=end_date)
        except:
            pass

    for cond in conditions:
        metric = cond.get('metric')
        operator = cond.get('operator')
        value = cond.get('value')

        if not value:
            continue

        if metric == 'amount':
            try:
                val = float(value)
                if operator == '>':
                    query &= Q(amount__gt=val)
                elif operator == '<':
                    query &= Q(amount__lt=val)
                elif operator == '=':
                    query &= Q(amount=val)
                elif operator == '!=':
                    query &= ~Q(amount=val)
            except ValueError:
                pass
        elif metric == 'category':
             if operator == 'contains':
                 query &= Q(category__icontains=value)
             elif operator == '=':
                 query &= Q(category__iexact=value)
             elif operator == '!=':
                 query &= ~Q(category__iexact=value)
        elif metric == 'risk_score':
             # Filter Transactions that have Alerts with this materiality
             try:
                val = float(value)
                if operator == '>':
                    query &= Q(alert__materiality__gt=val)
                elif operator == '<':
                    query &= Q(alert__materiality__lt=val)
             except ValueError:
                pass
    
    # Execute query
    txs = Transaction.objects.filter(query).distinct()
    count = txs.count()
    total_amount = txs.aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Daily stats for chart
    daily_stats = txs.annotate(day=TruncDay('timestamp')).values('day').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    ).order_by('day')
    
    formatted_stats = [
        {
            'date': item['day'].strftime('%Y-%m-%d') if item['day'] else 'N/A',
            'count': item['count'],
            'amount': float(item['total_amount'] or 0)
        }
        for item in daily_stats
    ]
    
    # Get sample matches
    limit = int(request.data.get('limit', 20))
    matches = []
    for tx in txs.order_by('-timestamp')[:limit]:
        matches.append({
            'id': tx.id,
            'vendor': tx.vendor,
            'amount': float(tx.amount),
            'date': tx.timestamp.strftime('%Y-%m-%d'),
            'category': tx.category
        })

    return Response({
        'count': count,
        'total_amount': total_amount,
        'matches': matches,
        'daily_stats': formatted_stats
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    data = request.data
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    company = data.get('company_name')
    sector = data.get('sector', 'Other')
    
    if not email or not password:
        return Response({'error': 'Email and password are required'}, status=400)
        
    if User.objects.filter(username=email).exists():
        return Response({'error': 'User already exists'}, status=400)
        
    try:
        # Create Django User
        user = User.objects.create_user(username=email, email=email, password=password)
        user.first_name = name or ''
        user.save()
        
        # Create API Token
        token_str = uuid.uuid4().hex
        ApiToken.objects.create(token=token_str, user_id=str(user.id), role='viewer')
        
        # Create Context Profile (Organization Context)
        ContextProfile.objects.create(
            user_id=str(user.id),
            persona='Standard Auditor',
            department=company, 
            sector=sector,
            org_structure='Functional',
            onboarding_data={'company_name': company, 'registration_date': str(timezone.now())}
        )
        
        return Response({
            'token': token_str,
            'user_id': user.id,
            'role': 'viewer',
            'message': 'Registration successful. Please complete KYC.'
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response({'error': 'Email and password are required'}, status=400)

    user = authenticate(username=email, password=password)
    if not user:
        return Response({'error': 'Invalid credentials'}, status=401)
        
    # Get or create token
    try:
        token_obj = ApiToken.objects.filter(user_id=str(user.id)).first()
        if not token_obj:
            token_str = uuid.uuid4().hex
            token_obj = ApiToken.objects.create(token=token_str, user_id=str(user.id), role='viewer')
        
        return Response({
            'token': token_obj.token,
            'user_id': user.id,
            'role': token_obj.role,
            'name': user.first_name or user.username
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuditorOrAdmin])
def agent_investigation(request):
    """
    Endpoint for Deep Investigation via Agents (LangGraph).
    """
    transaction_id = request.data.get('transaction_id')
    
    if not transaction_id:
        return Response({'error': 'Transaction ID required'}, status=400)
        
    from .agent_service import get_audit_graph
    
    graph = get_audit_graph()
    
    initial_state = {
        "transaction_id": str(transaction_id),
        "risk_score": 0.0,
        "reasons": [],
        "status": "New",
        "decision": "",
        "logs": [],
        "work_paper": ""
    }

    try:
        result = graph.invoke(initial_state)
        return Response(result)
    except Exception as e:
        return Response({'error': f"Agent execution failed: {str(e)}"}, status=500)

@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
def case_report(request, pk):
    from .ai_service import AuditAI
    ai = AuditAI(user_id=str(getattr(getattr(request, 'user', None), 'id', 'system')))
    report = ai.generate_case_report(pk)
    if "error" in report:
        return Response(report, status=404)
    return Response(report)


@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def health(request):
    """Health check público (para Docker/monitorização/CI smoke).
    Verifica a ligação à base de dados sem expor informação sensível."""
    from django.db import connection

    db_ok = False
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            db_ok = cur.fetchone() is not None
    except Exception:
        db_ok = False
    return Response({
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "service": "audit-api",
    })
