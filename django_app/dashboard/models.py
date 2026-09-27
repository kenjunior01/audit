from django.db import models
from django.utils import timezone

class Transaction(models.Model):
    id = models.AutoField(primary_key=True)
    transaction_id = models.CharField(max_length=128, unique=True, default='UNKNOWN_TX_ID')
    vendor = models.CharField(max_length=128, null=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default='BRL')
    timestamp = models.DateTimeField()
    category = models.CharField(max_length=64, null=True)
    status = models.CharField(max_length=32, default='Pending')
    user_id = models.CharField(max_length=128, null=True) # ID of user who initiated/approved
    xai_explanation = models.JSONField(null=True, blank=True) # AI Audit Log (Model Version, Feature Weights)

    class Meta:
        indexes = [
            models.Index(fields=['timestamp'], name='dashboard_tx_ts_idx'),
            models.Index(fields=['status'], name='dashboard_tx_status_idx'),
            models.Index(fields=['vendor'], name='dashboard_tx_vendor_idx'),
        ]

class Alert(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, null=True)
    alert_type = models.CharField(max_length=64)
    severity = models.CharField(max_length=32, default='Medium') # Low, Medium, High, Critical
    status = models.CharField(max_length=32, default='New') # New, Investigating, Resolved, False Positive
    description = models.TextField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    vendor = models.CharField(max_length=128, null=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    materiality = models.FloatField(default=0.0) # 0.0 to 1.0

    class Meta:
        indexes = [
            models.Index(fields=['timestamp'], name='dashboard_alert_ts_idx'),
            models.Index(fields=['severity'], name='dashboard_alert_sev_idx'),
            models.Index(fields=['status'], name='dashboard_alert_status_idx'),
        ]

class RegulatoryRule(models.Model):
    country = models.CharField(max_length=64)
    regulation = models.CharField(max_length=128) # e.g. "SOX", "FCPA", "LGPD"
    alert_type = models.CharField(max_length=64)
    description = models.TextField(null=True)
    threshold_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    active = models.BooleanField(default=True)
    suggested_by_ai = models.BooleanField(default=False)
    ai_confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

class AiFeedback(models.Model):
    transaction_id = models.CharField(max_length=128, null=True)
    user_id = models.CharField(max_length=128, null=True)
    feedback_type = models.CharField(max_length=32) # 'accurate', 'inaccurate', 'helpful', 'not_helpful'
    comment = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Fields for DPO / Self-Improving AI
    model_version = models.CharField(max_length=64, null=True, blank=True) # e.g. "DeepSeek-R1-Distill"
    input_context = models.JSONField(null=True, blank=True) # What the AI saw
    ai_response = models.JSONField(null=True, blank=True) # What the AI output
    human_correction = models.JSONField(null=True, blank=True) # The 'Ground Truth' from user action

class ImmutableAuditLog(models.Model):
    id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    actor_id = models.CharField(max_length=128) # User who performed the action
    action_type = models.CharField(max_length=64) # e.g. "APPROVE_CASE", "CHANGE_RISK_RULE"
    resource_id = models.CharField(max_length=128) # ID of the affected object
    details = models.JSONField(null=True, blank=True) # Snapshot of data
    previous_hash = models.CharField(max_length=64, default='0') # Chaining
    current_hash = models.CharField(max_length=64) # SHA-256 of this record

    def save(self, *args, **kwargs):
        import hashlib
        import json
        
        if not self.pk: # Only calculate hash on creation to ensure immutability
            if not self.timestamp:
                self.timestamp = timezone.now()

            # Get the hash of the last log entry
            last_log = ImmutableAuditLog.objects.order_by('-id').first()
            if last_log:
                self.previous_hash = last_log.current_hash
            
            # Construct payload for hashing
            payload = {
                "timestamp": str(self.timestamp),
                "actor_id": self.actor_id,
                "action_type": self.action_type,
                "resource_id": self.resource_id,
                "details": self.details,
                "previous_hash": self.previous_hash
            }
            # Simple serialization for hashing
            payload_str = json.dumps(payload, sort_keys=True, default=str)
            self.current_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
            
        super().save(*args, **kwargs)

class ExternalSystem(models.Model):
    SYSTEM_TYPE_CHOICES = [
        ('ERP', 'Sistema ERP'),
        ('CRM', 'Sistema CRM'),
        ('DATABASE', 'Banco de Dados'),
        ('DOCUMENT', 'Sistema de Documentos'),
        ('HR', 'Sistema RH'),
        ('FINANCE', 'Sistema Financeiro'),
        ('CUSTOM', 'Sistema Customizado'),
    ]
    
    AUTH_TYPE_CHOICES = [
        ('API_KEY', 'Chave API'),
        ('OAUTH2', 'OAuth 2.0'),
        ('BASIC', 'Autenticação Básica'),
        ('BEARER', 'Token Bearer'),
        ('NONE', 'Sem Autenticação'),
    ]

    name = models.CharField(max_length=128)
    system_type = models.CharField(max_length=32, choices=SYSTEM_TYPE_CHOICES, default='CUSTOM')
    auth_type = models.CharField(max_length=20, choices=AUTH_TYPE_CHOICES, default='API_KEY')
    
    # Credenciais (armazenadas de forma segura, idealmente usar encriptação em produção)
    api_key = models.CharField(max_length=256, null=True, blank=True)
    api_secret = models.CharField(max_length=256, null=True, blank=True)
    base_url = models.URLField(max_length=512, null=True, blank=True)
    webhook_url = models.URLField(max_length=512, null=True, blank=True)
    oauth_client_id = models.CharField(max_length=256, null=True, blank=True)
    oauth_client_secret = models.CharField(max_length=256, null=True, blank=True)
    oauth_token_url = models.URLField(max_length=512, null=True, blank=True)
    oauth_access_token = models.TextField(null=True, blank=True)
    oauth_refresh_token = models.TextField(null=True, blank=True)
    oauth_token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Configurações de ingestão
    ingest_enabled = models.BooleanField(default=True)
    ingest_interval = models.IntegerField(default=300, help_text='Intervalo de ingestão em segundos')
    last_ingest_at = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_system_type_display()})"

class IngestedSignal(models.Model):
    source = models.ForeignKey(ExternalSystem, on_delete=models.CASCADE)
    signal_type = models.CharField(max_length=64) # e.g. 'transaction', 'log', 'user_activity'
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source.name} - {self.signal_type} ({self.created_at})"

class WebhookEvent(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pendente'),
        ('SUCCESS', 'Sucesso'),
        ('FAILED', 'Falha'),
        ('RETRYING', 'Tentando Novamente'),
    ]

    system = models.ForeignKey(ExternalSystem, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=128) # e.g. 'alert.created', 'case.updated', 'risk.detected'
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    attempt_count = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - {self.get_status_display()}"

class ContextProfile(models.Model):
    user_id = models.CharField(max_length=128, unique=True)
    persona = models.CharField(max_length=64) # 'Standard Auditor', 'Skeptical Analyst', 'High-Value Approver'
    country = models.CharField(max_length=64, null=True, blank=True)
    department = models.CharField(max_length=128, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Organization Context Fields
    ORG_STRUCTURE_CHOICES = [
        ('Functional', 'Funcional'),
        ('Divisional', 'Divisional'),
        ('Matrix', 'Matricial'),
        ('SME', 'Pequena/Média Empresa'),
    ]
    org_structure = models.CharField(max_length=32, choices=ORG_STRUCTURE_CHOICES, default='Functional')
    
    SECTOR_CHOICES = [
        ('Manufacturing', 'Manufatura'),
        ('Services', 'Serviços/Consultoria'),
        ('SaaS', 'Tecnologia (SaaS)'),
        ('Retail', 'Varejo'),
        ('Public', 'Setor Público'),
        ('Financial', 'Financeiro'),
        ('Other', 'Outros'),
    ]
    sector = models.CharField(max_length=32, choices=SECTOR_CHOICES, default='Other')
    base_currency = models.CharField(max_length=10, default='BRL')
    approval_limits = models.JSONField(default=dict, blank=True) # e.g. {"L1": 5000, "L2": 50000}
    onboarding_data = models.JSONField(default=dict, blank=True) # Stores conversational onboarding answers
    regulatory_frameworks = models.JSONField(default=list, blank=True) # e.g. ["SOX", "FCPA", "LGPD"]
    audit_domains = models.JSONField(default=list, blank=True) # e.g. ["Compras", "Despesas/Viagem"]
    risk_appetite = models.CharField(max_length=32, default='Balanced') # Conservative, Balanced, Aggressive

class RegulatorySource(models.Model):
    title = models.CharField(max_length=128)
    url = models.CharField(max_length=512)
    country = models.CharField(max_length=64, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ContextDocument(models.Model):
    title = models.CharField(max_length=256)
    doc_type = models.CharField(max_length=64, null=True) # Policy, Manual, Contract, etc.
    file = models.FileField(upload_to='documents/')
    extracted_text = models.TextField(null=True, blank=True) # Full text for RAG
    embedding_id = models.CharField(max_length=128, null=True, blank=True) # Reference to vector DB if external
    embedding_vector = models.JSONField(null=True, blank=True) # Local vector storage (list of floats)
    country = models.CharField(max_length=64, null=True)
    region = models.CharField(max_length=64, null=True)

    def __str__(self):
        return self.title
    company_type = models.CharField(max_length=64, null=True)
    sector = models.CharField(max_length=64, null=True)
    effective_date = models.DateField(null=True)
    source_url = models.CharField(max_length=512, null=True)
    suggested_by_ai = models.BooleanField(default=False)
    ai_summary = models.CharField(max_length=1000, null=True)
    ai_confidence = models.FloatField(default=0.0)
    processed = models.BooleanField(default=False)
    validated_by = models.CharField(max_length=128, null=True)
    validated_at = models.DateTimeField(null=True)
    transaction_id = models.CharField(max_length=128, null=True, blank=True)
    
    # Security Fields
    uploaded_by = models.CharField(max_length=128, null=True) # User ID who uploaded
    file_hash = models.CharField(max_length=64, null=True, blank=True) # SHA-256 for integrity
    scan_status = models.CharField(max_length=32, default='Pending') # Pending, Clean, Infected, Skipped
    scan_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class DocumentChunk(models.Model):
    document = models.ForeignKey(ContextDocument, related_name='chunks', on_delete=models.CASCADE)
    chunk_index = models.IntegerField()
    text = models.TextField()
    embedding_vector = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']

class IntegrationSettings(models.Model):
    user_id = models.IntegerField(unique=True)
    slack_webhook_url = models.CharField(max_length=512, null=True, blank=True)
    teams_webhook_url = models.CharField(max_length=512, null=True, blank=True)
    email_digest_list = models.CharField(max_length=512, null=True, blank=True)
    auto_email_enabled = models.BooleanField(default=True)
    auto_close_enabled = models.BooleanField(default=True)
    
    # AI Control Plane
    ai_sensitivity = models.FloatField(default=0.5) # 0.0 (Conservative) to 1.0 (Aggressive)
    active_learning = models.BooleanField(default=True) # Enable/Disable Mem0 Feedback Loop
    
    updated_at = models.DateTimeField(auto_now=True)

class AuditCase(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=256)
    description = models.TextField(null=True)
    status = models.CharField(max_length=32, default='New') # New, In Progress, Resolved, Closed
    priority = models.CharField(max_length=32, default='Medium') # Low, Medium, High, Critical
    assigned_to = models.CharField(max_length=128, null=True)
    created_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transaction_id = models.CharField(max_length=128, null=True)
    deadline = models.DateTimeField(null=True, blank=True)
    finding_type = models.CharField(max_length=32, null=True, blank=True)
    inherent_risk = models.FloatField(null=True, blank=True)
    residual_risk = models.FloatField(null=True, blank=True)
    action_owner = models.CharField(max_length=128, null=True, blank=True)
    action_plan = models.TextField(null=True, blank=True)
    action_due_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='dashboard_case_status_idx'),
            models.Index(fields=['created_at'], name='dashboard_case_created_idx'),
        ]

class AuditCaseComment(models.Model):
    case = models.ForeignKey(AuditCase, related_name='comments', on_delete=models.CASCADE)
    user_id = models.CharField(max_length=128)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class AuditCaseAttachment(models.Model):
    case = models.ForeignKey(AuditCase, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='case_attachments/', null=True)
    file_name = models.CharField(max_length=256, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(max_length=128)

    @property
    def file_url(self):
        return self.file.url if self.file else ''

class AuditRule(models.Model):
    MODEL_CHOICES = [
        ('transaction', 'Transaction'),
        ('alert', 'Alert'),
        ('case', 'AuditCase'),
    ]
    OPERATOR_CHOICES = [
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('==', '=='),
        ('!=', '!='),
    ]
    SEVERITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, unique=True)
    domain = models.CharField(max_length=64, default='General')
    model = models.CharField(max_length=32, choices=MODEL_CHOICES, default='transaction')
    field = models.CharField(max_length=64)
    operator = models.CharField(max_length=4, choices=OPERATOR_CHOICES, default='>=')
    value = models.CharField(max_length=128)
    severity = models.CharField(max_length=32, choices=SEVERITY_CHOICES, default='Medium')
    materiality = models.FloatField(default=0.5)
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ExternalActionTemplate(models.Model):
    """Template for reusable external actions that agents can trigger."""
    ACTION_TYPE_CHOICES = [
        ('webhook', 'Webhook'),
        ('api_rest', 'REST API'),
        ('jira_ticket', 'Jira Ticket'),
        ('slack_message', 'Slack Message'),
        ('email', 'Email'),
        ('custom', 'Custom Action'),
    ]

    name = models.CharField(max_length=128)
    description = models.TextField(null=True, blank=True)
    action_type = models.CharField(max_length=32, choices=ACTION_TYPE_CHOICES, default='webhook')
    system = models.ForeignKey(ExternalSystem, on_delete=models.CASCADE, null=True, blank=True)
    
    # Common configuration
    endpoint_url = models.URLField(max_length=512, null=True, blank=True)
    http_method = models.CharField(max_length=10, default='POST', choices=[('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('PATCH', 'PATCH'), ('DELETE', 'DELETE')])
    
    # Payload template (supports Jinja2-like variables: {{ alert.id }}, {{ case.title }}, etc.)
    payload_template = models.JSONField(null=True, blank=True)
    headers = models.JSONField(null=True, blank=True)
    
    # Authentication (can override system settings)
    auth_type = models.CharField(max_length=32, null=True, blank=True, choices=[('none', 'None'), ('api_key', 'API Key'), ('bearer', 'Bearer Token'), ('basic', 'Basic Auth'), ('oauth2', 'OAuth2')])
    auth_credentials = models.JSONField(null=True, blank=True)
    
    # Jira specific
    jira_project_key = models.CharField(max_length=64, null=True, blank=True)
    jira_issue_type = models.CharField(max_length=64, null=True, blank=True, default='Task')
    
    # Email specific
    email_recipients = models.CharField(max_length=512, null=True, blank=True)
    email_subject_template = models.CharField(max_length=256, null=True, blank=True)
    email_body_template = models.TextField(null=True, blank=True)
    
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_action_type_display()})"

class RiskAgent(models.Model):
    name = models.CharField(max_length=128)
    specialization = models.CharField(max_length=64, default='General') # e.g., Fraud, IT, Compliance
    persona = models.TextField(null=True, blank=True) # Description of the agent's "personality"
    training_instructions = models.TextField(null=True, blank=True) # Specific knowledge/rules for this agent
    reputation_score = models.FloatField(default=1.0) # Feedback score (1.0 = Neutral)
    conditions = models.JSONField()
    action = models.CharField(max_length=64) # e.g., "create_case_high", "notify_manager", etc.
    external_action_template = models.ForeignKey(ExternalActionTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ExternalActionExecution(models.Model):
    """Log of external action executions."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    template = models.ForeignKey(ExternalActionTemplate, on_delete=models.CASCADE, null=True, blank=True)
    agent = models.ForeignKey(RiskAgent, on_delete=models.CASCADE, null=True, blank=True)
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, null=True, blank=True)
    case = models.ForeignKey(AuditCase, on_delete=models.CASCADE, null=True, blank=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, null=True, blank=True)
    
    action_type = models.CharField(max_length=32)
    endpoint_url = models.URLField(max_length=512, null=True, blank=True)
    payload_sent = models.JSONField(null=True, blank=True)
    response_received = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    executed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class RiskAgentLog(models.Model):
    agent = models.ForeignKey(RiskAgent, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    scanned_count = models.IntegerField(default=0)
    finding_summary = models.TextField(null=True, blank=True) # e.g., "Found 3 suspicious items"
    finding_details = models.JSONField(null=True, blank=True) # Full details
    risk_score = models.FloatField(default=0.0) # Normalized risk score (0-100)
    suggested_action = models.CharField(max_length=128, null=True, blank=True) # e.g., "Review Vendor", "Freeze Account"
    action_taken = models.BooleanField(default=False) # Whether the user acted on it
    
    class Meta:
        ordering = ['-timestamp']

class ApiToken(models.Model):
    token = models.CharField(max_length=128, primary_key=True)
    user_id = models.CharField(max_length=128)
    role = models.CharField(max_length=32) # viewer, auditor, admin
    created_at = models.DateTimeField(auto_now_add=True)

class ReferenceList(models.Model):
    name = models.CharField(max_length=128) # e.g., "Departamentos", "Setores", "Tipos de Operação"
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ReferenceItem(models.Model):
    reference_list = models.ForeignKey(ReferenceList, on_delete=models.CASCADE, related_name='items')
    code = models.CharField(max_length=64, null=True, blank=True) # Optional code
    value = models.CharField(max_length=256) # The actual value, e.g., "Financeiro"
    risk_factor = models.FloatField(default=1.0) # >1.0 means higher risk
    metadata = models.JSONField(null=True, blank=True) # Extra info
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.value} ({self.reference_list.name})"

class ExcelImportJob(models.Model):
    """Trilha de auditoria das importações Excel/CSV (Excel Studio)."""
    id = models.AutoField(primary_key=True)
    STATUS_CHOICES = [
        ('Completed', 'Concluída'),
        ('Partial', 'Parcial'),
        ('Failed', 'Falhada'),
    ]
    file_name = models.CharField(max_length=256)
    uploaded_by = models.CharField(max_length=128, null=True, blank=True)
    sheet = models.CharField(max_length=128, null=True, blank=True)
    rows_imported = models.IntegerField(default=0)
    rows_skipped = models.IntegerField(default=0)
    mapping = models.JSONField(default=dict, blank=True)   # campo canônico → coluna
    errors = models.JSONField(default=list, blank=True)    # amostra de linhas inválidas
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Completed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.file_name} ({self.rows_imported} linhas, {self.status})"


class AIGovernanceEvent(models.Model):
    id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=64) # e.g., 'LLM_CALL', 'RISK_SCORING', 'AUTO_CLUSTER'
    model_name = models.CharField(max_length=128, null=True, blank=True)
    input_data = models.JSONField(null=True, blank=True)
    output_data = models.JSONField(null=True, blank=True)
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=32, default='SUCCESS') # SUCCESS, FAILED, HALLUCINATION
    confidence_score = models.FloatField(null=True, blank=True)
    was_corrected = models.BooleanField(default=False)
    correction_details = models.JSONField(null=True, blank=True)
    user_id = models.CharField(max_length=128, null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True) # Para armazenar flags de anomalia, etc.

    class Meta:
        ordering = ['-timestamp']


class CopilotFeedback(models.Model):
    """Avaliação (1-5) do utilizador sobre respostas do Copiloto Global.
    Fecha o ciclo de feedback do modelo de suporte: respostas mal
    avaliadas podem ser revistas; métricas por página/modo orientam
    melhorias contínuas."""
    id = models.AutoField(primary_key=True)
    rating = models.IntegerField()  # 1-5 (1 = péssima, 5 = excelente)
    question = models.TextField(blank=True)
    answer_excerpt = models.TextField(blank=True)  # recorte da resposta
    mode = models.CharField(max_length=10, blank=True)  # 'llm' | 'rules'
    page = models.CharField(max_length=60, blank=True)  # rota do frontend
    comment = models.TextField(blank=True)
    username = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at'], name='dashboard_cpf_created_idx'),
            models.Index(fields=['rating'], name='dashboard_cpf_rating_idx'),
        ]

    def __str__(self):
        return f"Feedback {self.rating}/5 ({self.page or '—'})"


class CopilotDigest(models.Model):
    """Digest programado do Copiloto Global (push proativo por cron/beat).
    Guarda um snapshot diário/semanal composto por briefing executivo +
    sinais proativos + qualidade do suporte, com registo do envio de email.
    Um digest por (período, dia) — corridas repetidas atualizam o mesmo
    registo em vez de duplicar."""
    id = models.AutoField(primary_key=True)
    period = models.CharField(max_length=10, default="daily")  # daily|weekly
    day = models.DateField()  # dia de referência (chave de dedupe c/ period)
    payload = models.JSONField(default=dict)  # build_digest() completo
    signals_count = models.IntegerField(default=0)
    critical_count = models.IntegerField(default=0)
    avg_rating = models.FloatField(null=True, blank=True)
    recipients = models.TextField(blank=True)  # emails para onde foi enviado
    status = models.CharField(max_length=12, default="stored")  # stored|sent|failed
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['period', 'day'],
                                    name='dashboard_digest_period_day_uq'),
        ]
        indexes = [
            models.Index(fields=['created_at'], name='dashboard_cpd_created_idx'),
        ]

    def __str__(self):
        return f"Digest {self.period} {self.day} ({self.status})"
