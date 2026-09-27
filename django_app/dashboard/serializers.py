from rest_framework import serializers
from .models import Alert, Transaction, ContextProfile, RegulatoryRule, ContextDocument, IntegrationSettings, AuditCase, AuditCaseComment, AuditCaseAttachment, RiskAgent, ExternalSystem, IngestedSignal, ReferenceList, ReferenceItem, RiskAgentLog, AIGovernanceEvent, AuditRule, WebhookEvent, ExternalActionTemplate, ExternalActionExecution

class AIGovernanceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIGovernanceEvent
        fields = '__all__'

class ExternalSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalSystem
        fields = '__all__'
        read_only_fields = ['last_ingest_at', 'created_at', 'updated_at']

    def create(self, validated_data):
        import secrets
        if not validated_data.get('api_key'):
            validated_data['api_key'] = secrets.token_urlsafe(32)
        return super().create(validated_data)

class IngestedSignalSerializer(serializers.ModelSerializer):
    source_name = serializers.ReadOnlyField(source='source.name')
    class Meta:
        model = IngestedSignal
        fields = '__all__'

class ReferenceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferenceItem
        fields = '__all__'

class ReferenceListSerializer(serializers.ModelSerializer):
    items = ReferenceItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = ReferenceList
        fields = ['id', 'name', 'description', 'created_at', 'items', 'item_count']
    
    def get_item_count(self, obj):
        return obj.items.count()


class RiskAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAgent
        fields = '__all__'

class RiskAgentLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAgentLog
        fields = '__all__'

class IntegrationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationSettings
        fields = '__all__'

class AlertSerializer(serializers.ModelSerializer):
    context_risk = serializers.SerializerMethodField()
    context_explanation = serializers.SerializerMethodField()
    context_due_date = serializers.SerializerMethodField()
    context_severity = serializers.SerializerMethodField()
    category = serializers.ReadOnlyField(source='transaction.category')
    
    class Meta:
        model = Alert
        fields = ('id','timestamp','transaction_id','alert_type','materiality','amount','category','vendor','context_risk','context_explanation','context_due_date','context_severity')

    def get_context_risk(self, obj):
        return round(float(obj.materiality or 0.0), 2)

    def get_context_explanation(self, obj):
        return ""

    def get_context_due_date(self, obj):
        from django.utils import timezone
        ts = obj.timestamp
        if not ts:
            ts = timezone.now()
        return (ts + timezone.timedelta(days=7)).isoformat()

    def get_context_severity(self, obj):
        risk = self.get_context_risk(obj)
        # simple bands; could be driven by SlaPolicy too
        if risk is None:
            return ''
        if risk > 8000:
            return 'critical'
        elif risk > 3000:
            return 'high'
        elif risk > 1000:
            return 'medium'
        return 'low'

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class ContextProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextProfile
        fields = '__all__'

class RegulatoryRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegulatoryRule
        fields = '__all__'

class ExternalSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalSystem
        fields = '__all__'
        read_only_fields = ['last_ingest_at', 'created_at', 'updated_at']

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = '__all__'
        read_only_fields = ['status', 'attempt_count', 'last_attempt_at', 'error_message', 'created_at', 'updated_at']

class AuditRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditRule
        fields = '__all__'

class ContextDocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ContextDocument
        fields = '__all__'
    
    def get_chunk_count(self, obj):
        return obj.chunks.count()

class AuditCaseCommentSerializer(serializers.ModelSerializer):
    user_id = serializers.ReadOnlyField()
    class Meta:
        model = AuditCaseComment
        fields = '__all__'

class AuditCaseAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.ReadOnlyField()
    file_url = serializers.ReadOnlyField()
    
    class Meta:
        model = AuditCaseAttachment
        fields = '__all__'

class AuditCaseSerializer(serializers.ModelSerializer):
    comments = AuditCaseCommentSerializer(many=True, read_only=True)
    attachments = AuditCaseAttachmentSerializer(many=True, read_only=True)
    created_by = serializers.ReadOnlyField()
    class Meta:
        model = AuditCase
        fields = '__all__'

class ExternalActionTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalActionTemplate
        fields = '__all__'

class ExternalActionExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalActionExecution
        fields = '__all__'
