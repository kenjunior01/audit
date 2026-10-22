from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from .views import AlertViewSet, TransactionViewSet, export_alerts, export_transactions, upload_samples, process_pending_analysis, upload_document, my_profile, upsert_profile, analyze_regulation, analyze_news, wizard, RegulatoryRuleViewSet, fetch_news_sources, fetch_regulatory_sources, context_stats, forecast_risk, analyze_root_cause, geo_risks, suggest_rules, ContextDocumentViewSet, graph_analysis, IntegrationSettingsViewSet, ai_user_insights, submit_ai_feedback, audit_chat, execute_ai_action, health, AuditCaseViewSet, AuditCaseCommentViewSet, AuditCaseAttachmentViewSet, case_report, generate_case_report, RiskAgentViewSet, simulate_rule, audit_dashboard_stats, sla_stats, ExternalSystemViewSet, IngestedSignalViewSet, ingest_external_data, ReferenceListViewSet, ReferenceItemViewSet, auto_cluster_alerts, register_user, login_user, agent_investigation, executive_summary, RiskAgentLogViewSet, trigger_agent_run, AIGovernanceViewSet, AuditRuleViewSet, WebhookEventViewSet, ExternalActionTemplateViewSet, ExternalActionExecutionViewSet
from .excel_views import excel_preview, excel_import, excel_analyze, excel_reconcile, excel_export, excel_assistant, excel_assistant_apply
from .copilot_views import (copilot_chat, copilot_briefing, copilot_stream,
                            copilot_feedback, copilot_insights,
                            copilot_feedback_stats, copilot_digest,
                            copilot_digest_pdf, copilot_digest_email_preview,
                            copilot_act)
from .notification_views import (notifications_list, notifications_unread_count,
                                 notifications_mark_read)
from .report_views import audit_report_summary_view, audit_report_pdf_view
from .observability import metrics_view
from .bi_views import (bi_measures, bi_measure_delete, bi_dimensions,
                       bi_evaluate, bi_group, bi_matrix, bi_pareto,
                       bi_decompose, bi_whatif, bi_drillthrough,
                       bi_pipelines, bi_pipeline_delete, bi_pipeline_run,
                       bi_rls, bi_rls_detail, bi_auto,
                       bi_visual, bi_series, bi_forecast, bi_anomaly,
                       bi_waterfall, bi_funnel, bi_scatter, bi_kpi,
                       bi_dashboards, bi_dashboard_detail, bi_dashboard_run,
                       bi_qa, bi_export, bi_alerts, bi_alert_detail,
                       bi_alerts_run)

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
    # alias usado pelo frontend (home, signals, transactions, settings, cases)
    path('context/profile/current', my_profile, name='context_profile_current'),
    # alias usado por AISettingsModal/ContextRiskChart
    path('settings/integration/current',
         IntegrationSettingsViewSet.as_view({'get': 'current', 'patch': 'current'}),
         name='settings_integration_current'),
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

    # Central de Notificações in-app
    path('notifications', notifications_list, name='notifications_list'),
    path('notifications/unread-count', notifications_unread_count,
         name='notifications_unread_count'),
    path('notifications/read', notifications_mark_read, name='notifications_mark_read'),

    # Relatório Global de Auditoria (JSON preview + PDF premium)
    path('reports/audit', audit_report_summary_view, name='audit_report_summary'),
    path('reports/audit/pdf', audit_report_pdf_view, name='audit_report_pdf'),

    # Observabilidade — métricas formato Prometheus
    path('metrics', metrics_view, name='metrics'),

    # BI Studio — Power BI parity (REA)
    path('bi/auto', bi_auto, name='bi_auto'),
    path('bi/measures', bi_measures, name='bi_measures'),
    path('bi/measures/<int:pk>', bi_measure_delete, name='bi_measure_delete'),
    path('bi/meta', bi_dimensions, name='bi_meta'),
    path('bi/evaluate', bi_evaluate, name='bi_evaluate'),
    path('bi/group', bi_group, name='bi_group'),
    path('bi/matrix', bi_matrix, name='bi_matrix'),
    path('bi/pareto', bi_pareto, name='bi_pareto'),
    path('bi/decompose', bi_decompose, name='bi_decompose'),
    path('bi/whatif', bi_whatif, name='bi_whatif'),
    path('bi/drillthrough', bi_drillthrough, name='bi_drillthrough'),
    path('bi/pipelines', bi_pipelines, name='bi_pipelines'),
    path('bi/pipelines/<int:pk>', bi_pipeline_delete, name='bi_pipeline_delete'),
    path('bi/pipelines/<int:pk>/run', bi_pipeline_run, name='bi_pipeline_run'),
    path('bi/rls', bi_rls, name='bi_rls'),
    path('bi/rls/<int:pk>', bi_rls_detail, name='bi_rls_detail'),

    # BI Studio v2 — visuais avançados, relatórios, Q&A, exportação e alertas
    path('bi/visual', bi_visual, name='bi_visual'),
    path('bi/series', bi_series, name='bi_series'),
    path('bi/forecast', bi_forecast, name='bi_forecast'),
    path('bi/anomaly', bi_anomaly, name='bi_anomaly'),
    path('bi/waterfall', bi_waterfall, name='bi_waterfall'),
    path('bi/funnel', bi_funnel, name='bi_funnel'),
    path('bi/scatter', bi_scatter, name='bi_scatter'),
    path('bi/kpi', bi_kpi, name='bi_kpi'),
    path('bi/dashboards', bi_dashboards, name='bi_dashboards'),
    path('bi/dashboards/<int:pk>', bi_dashboard_detail, name='bi_dashboard_detail'),
    path('bi/dashboards/<int:pk>/run', bi_dashboard_run, name='bi_dashboard_run'),
    path('bi/qa', bi_qa, name='bi_qa'),
    path('bi/export/xlsx', bi_export, name='bi_export'),
    path('bi/alerts', bi_alerts, name='bi_alerts'),
    path('bi/alerts/run', bi_alerts_run, name='bi_alerts_run'),
    path('bi/alerts/<int:pk>', bi_alert_detail, name='bi_alert_detail'),

    # Documentação OpenAPI 3
    path('schema', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui', SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger_ui'),
    path('schema/redoc', SpectacularRedocView.as_view(url_name='schema'),
         name='redoc'),
]
