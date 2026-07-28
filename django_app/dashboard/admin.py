from django.contrib import admin
from .models import (
    Transaction, Alert, RegulatoryRule, AiFeedback, ContextProfile,
    RegulatorySource, ContextDocument, DocumentChunk, IntegrationSettings,
    AuditCase, AuditCaseComment, AuditCaseAttachment, RiskAgent, ApiToken, RiskAgentLog
)

@admin.register(RiskAgentLog)
class RiskAgentLogAdmin(admin.ModelAdmin):
    list_display = ('agent', 'timestamp', 'scanned_count', 'short_finding')
    list_filter = ('agent', 'timestamp')
    search_fields = ('agent__name', 'finding_summary')

    def short_finding(self, obj):
        return (obj.finding_summary[:50] + '...') if obj.finding_summary else '-'

@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'short_text', 'created_at')
    list_filter = ('document',)
    search_fields = ('text',)
    
    def short_text(self, obj):
        return obj.text[:50] + "..." if obj.text else ""

@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user_id', 'role', 'created_at')
    search_fields = ('token', 'role')
    list_filter = ('role',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'timestamp', 'amount', 'currency', 'category', 'vendor', 'status')
    search_fields = ('transaction_id', 'vendor', 'category')
    list_filter = ('currency', 'category', 'status')

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction', 'alert_type', 'severity', 'status', 'materiality', 'timestamp')
    search_fields = ('alert_type', 'vendor', 'status')
    list_filter = ('alert_type', 'severity', 'status')

@admin.register(RegulatoryRule)
class RegulatoryRuleAdmin(admin.ModelAdmin):
    list_display = ('country', 'regulation', 'alert_type', 'active', 'suggested_by_ai', 'ai_confidence')
    search_fields = ('country', 'regulation', 'alert_type')
    list_filter = ('country', 'active', 'suggested_by_ai')

@admin.register(AiFeedback)
class AiFeedbackAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user_id', 'feedback_type', 'created_at')
    list_filter = ('feedback_type',)

@admin.register(ContextProfile)
class ContextProfileAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'persona', 'updated_at')
    search_fields = ('user_id', 'persona')
    list_filter = ('persona',)

@admin.register(RegulatorySource)
class RegulatorySourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'country', 'active', 'created_at')
    search_fields = ('title', 'url')
    list_filter = ('country', 'active')

@admin.register(ContextDocument)
class ContextDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'country', 'processed', 'suggested_by_ai', 'ai_confidence')
    list_filter = ('doc_type', 'country', 'processed', 'suggested_by_ai')
    search_fields = ('title',)

@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'auto_email_enabled', 'auto_close_enabled', 'updated_at')

@admin.register(AuditCase)
class AuditCaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'priority', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'description', 'assigned_to')

@admin.register(AuditCaseComment)
class AuditCaseCommentAdmin(admin.ModelAdmin):
    list_display = ('case', 'user_id', 'created_at')

@admin.register(AuditCaseAttachment)
class AuditCaseAttachmentAdmin(admin.ModelAdmin):
    list_display = ('case', 'file_name', 'uploaded_by', 'uploaded_at')

@admin.register(RiskAgent)
class RiskAgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'action', 'active', 'last_triggered', 'created_at')
    list_filter = ('active', 'action')
    search_fields = ('name', 'action')
