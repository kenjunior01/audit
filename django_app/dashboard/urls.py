from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlertViewSet, TransactionViewSet, export_alerts, export_transactions, upload_samples, process_pending_analysis, upload_document, my_profile, upsert_profile, analyze_regulation, analyze_news, wizard, RegulatoryRuleViewSet, fetch_news_sources, fetch_regulatory_sources, context_stats, forecast_risk, analyze_root_cause, geo_risks, suggest_rules, ContextDocumentViewSet, graph_analysis, IntegrationSettingsViewSet, ai_user_insights, submit_ai_feedback, audit_chat, execute_ai_action, health, AuditCaseViewSet, AuditCaseCommentViewSet, AuditCaseAttachmentViewSet, case_report, generate_case_report, RiskAgentViewSet, simulate_rule, audit_dashboard_stats, sla_stats, ExternalSystemViewSet, IngestedSignalViewSet, ingest_external_data, ReferenceListViewSet, ReferenceItemViewSet, auto_cluster_alerts, register_user, login_user, agent_investigation, executive_summary, RiskAgentLogViewSet, trigger_agent_run, AIGovernanceViewSet, AuditRuleViewSet, WebhookEventViewSet, ExternalActionTemplateViewSet, ExternalActionExecutionViewSet
from .excel_views import excel_preview, excel_import, excel_analyze, excel_reconcile, excel_export, excel_assistant, excel_assistant_apply
from .copilot_views import (copilot_chat, copilot_briefing, copilot_stream,
                            copilot_feedback, copilot_insights,
                            copilot_feedback_stats, copilot_digest,
                            copilot_digest_pdf, copilot_digest_email_preview,
                            copilot_act)

router = DefaultRouter()
router.register(r'governance', AIGovernanceViewSet, basename='governance')
router.register(r'alerts', AlertViewSet, basename='alerts')
router.register(r'transactions', TransactionViewSet, basename='transactions')
router.register(r'rules', RegulatoryRuleViewSet, basename='rules')
router.register(r'audit-rules', AuditRuleViewSet, basename='audit_rules')
router.register(r'agents', RiskAgentViewSet, basename='agents')
router.register(r'agent-logs', RiskAgentLogViewSet, basename='agent_logs')
router.register(r'documents', ContextDocumentViewSet, basename='documents')
router.register(r'settings', IntegrationSettingsViewSet, basename='settings')
router.register(r'cases', AuditCaseViewSet, basename='cases')
router.register(r'case_comments', AuditCaseCommentViewSet, basename='case_comments')
router.register(r'case_attachments', AuditCaseAttachmentViewSet, basename='case_attachments')
router.register(r'external-systems', ExternalSystemViewSet, basename='external_systems')
router.register(r'external-action-templates', ExternalActionTemplateViewSet, basename='external_action_templates')
router.register(r'external-action-executions', ExternalActionExecutionViewSet, basename='external_action_executions')
router.register(r'webhook-events', WebhookEventViewSet, basename='webhook_events')
router.register(r'ingested-signals', IngestedSignalViewSet, basename='ingested_signals')
router.register(r'reference-lists', ReferenceListViewSet, basename='reference_lists')
router.register(r'reference-items', ReferenceItemViewSet, basename='reference_items')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register', register_user, name='register_user'),
    path('auth/login', login_user, name='login_user'),
    path('health', health, name='health'),
    path('upload/document', upload_document, name='upload_document'),
    path('api/external/ingest', ingest_external_data, name='ingest_external_data'),
    path('export/alerts.csv', export_alerts, name='export_alerts'),
    path('export/transactions.csv', export_transactions, name='export_transactions'),
    path('upload/samples', upload_samples, name='upload_samples'),
    path('upload/process-pending', process_pending_analysis, name='process_pending_analysis'),
    path('upload/document', upload_document, name='upload_document'),
    path('profile/me', my_profile, name='my_profile'),
    path('profile', upsert_profile, name='upsert_profile'),
    path('ai/profile', ai_user_insights, name='ai_user_insights'),
    path('ai/analyze_regulation', analyze_regulation, name='analyze_regulation'),
    path('ai/analyze_news', analyze_news, name='analyze_news'),
    path('wizard', wizard, name='wizard'),
    path('ai/fetch_news', fetch_news_sources, name='fetch_news_sources'),
    path('ai/fetch_regulations', fetch_regulatory_sources, name='fetch_regulatory_sources'),
    path('context/stats', audit_dashboard_stats, name='audit_dashboard_stats'),
    path('context/risk-stats', context_stats, name='context_risk_stats'),
    path('ai/forecast', forecast_risk, name='forecast_risk'),
    path('ai/rca/<int:pk>', analyze_root_cause, name='analyze_root_cause'),
    path('context/geo_risks', geo_risks, name='geo_risks'),
    path('context/graph', graph_analysis, name='graph_analysis'),
    path('ai/suggest_rules', suggest_rules, name='suggest_rules'),
    path('ai/agent-investigate', agent_investigation, name='agent_investigation'),
    path('ai/feedback', submit_ai_feedback, name='submit_ai_feedback'),
    path('ai/chat', audit_chat, name='audit_chat'),
    path('ai/action', execute_ai_action, name='execute_ai_action'),
    path('ai/simulate', simulate_rule, name='simulate_rule'),
    path('ai/executive-summary', executive_summary, name='executive_summary'),
    path('agents/<int:pk>/run', trigger_agent_run, name='trigger_agent_run'),
    path('cases/<int:pk>/report', case_report, name='case_report'),
    path('cases/<int:pk>/pdf', generate_case_report, name='case_report_pdf'),
    path('cases/auto-cluster', auto_cluster_alerts, name='auto_cluster_alerts'),
    path('cases/sla-stats', sla_stats, name='sla_stats'),

    # Excel Studio — super auxílio de documentos
    path('excel/preview', excel_preview, name='excel_preview'),
    path('excel/import', excel_import, name='excel_import'),
    path('excel/analyze', excel_analyze, name='excel_analyze'),
    path('excel/reconcile', excel_reconcile, name='excel_reconcile'),
    path('excel/export', excel_export, name='excel_export'),
    path('excel/assistant', excel_assistant, name='excel_assistant'),
    path('excel/assistant/apply', excel_assistant_apply, name='excel_assistant_apply'),

    # Copiloto Global — assistente agéntico em toda a plataforma
    path('ai/copilot', copilot_chat, name='copilot_chat'),
    path('ai/copilot/stream', copilot_stream, name='copilot_stream'),
    path('ai/copilot/briefing', copilot_briefing, name='copilot_briefing'),
    path('ai/copilot/feedback', copilot_feedback, name='copilot_feedback'),
    path('ai/copilot/insights', copilot_insights, name='copilot_insights'),
    path('ai/copilot/feedback/stats', copilot_feedback_stats,
         name='copilot_feedback_stats'),
    path('ai/copilot/digest', copilot_digest, name='copilot_digest'),
    path('ai/copilot/digest/pdf', copilot_digest_pdf,
         name='copilot_digest_pdf'),
    path('ai/copilot/digest/email/preview', copilot_digest_email_preview,
         name='copilot_digest_email_preview'),
    path('ai/copilot/act', copilot_act, name='copilot_act'),
]
