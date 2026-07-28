'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Settings, 
  User, 
  Building, 
  Globe, 
  CreditCard, 
  Save, 
  Bell, 
  Shield, 
  Key, 
  Webhook,
  Activity,
  CheckCircle,
  AlertTriangle,
  Copy
} from 'lucide-react'
import { apiFetch } from '@/lib/api'

interface AuditRule {
  id?: number
  name: string
  code: string
  domain: string
  model: string
  field: string
  operator: string
  value: string
  severity: string
  materiality: number
  description: string
  active: boolean
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('profile')
  const [loading, setLoading] = useState(false)
  const [successMsg, setSuccessMsg] = useState('')
  
  // Profile State
  const [profile, setProfile] = useState<any>({
    persona: 'Standard Auditor',
    org_structure: 'Functional',
    sector: 'Other',
    country: 'Global',
    base_currency: 'BRL',
    approval_limits: {},
    onboarding_data: {}
  })

  // Integration State
  const [webhooks, setWebhooks] = useState({
    slack: '',
    teams: '',
    email_digest: ''
  })

  // System State
  const [sensitivity, setSensitivity] = useState(0.5)

  const [rules, setRules] = useState<AuditRule[]>([])
  const [rulesLoading, setRulesLoading] = useState(false)
  const [scanLoading, setScanLoading] = useState(false)
  const [alertScanLoading, setAlertScanLoading] = useState(false)
  const [editingRule, setEditingRule] = useState<AuditRule | null>(null)
  const [filterModel, setFilterModel] = useState<string>('all')
  const [filterSeverity, setFilterSeverity] = useState<string>('all')
  const [filterActive, setFilterActive] = useState<string>('all')
  const [ruleForm, setRuleForm] = useState<AuditRule>({
    name: '',
    code: '',
    domain: 'Compras',
    model: 'transaction',
    field: 'amount',
    operator: '>=',
    value: '100000',
    severity: 'High',
    materiality: 0.9,
    description: '',
    active: true
  })

  useEffect(() => {
    fetchProfile()
  }, [])

  const fetchProfile = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/context/profile/current')
      if (res.ok) {
        const data = await res.json()
        setProfile(data)
        // Mock loading other settings for now or assume they come from profile/separate endpoint
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const fetchRules = async () => {
    setRulesLoading(true)
    try {
      const res = await apiFetch('/audit-rules/')
      if (res.ok) {
        const data = await res.json()
        setRules(data)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setRulesLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'rules') {
      fetchRules()
    }
  }, [activeTab])

  const resetRuleForm = () => {
    setEditingRule(null)
    setRuleForm({
      name: '',
      code: '',
      domain: 'Compras',
      model: 'transaction',
      field: 'amount',
      operator: '>=',
      value: '100000',
      severity: 'High',
      materiality: 0.9,
      description: '',
      active: true
    })
  }

  const handleEditRule = (rule: AuditRule) => {
    setEditingRule(rule)
    setRuleForm(rule)
  }

  const handleCloneRule = (rule: AuditRule) => {
    const suffix = '_CLONE'
    const baseCode = rule.code || ''
    const newCode = baseCode.endsWith(suffix) ? baseCode : `${baseCode}${suffix}`
    setEditingRule(null)
    setRuleForm({
      ...rule,
      id: undefined,
      name: `${rule.name} (Clone)`,
      code: newCode,
      active: false
    })
  }

  const handleToggleRuleActive = async (rule: AuditRule) => {
    const next = !rule.active
    try {
      const res = await apiFetch(`/audit-rules/${rule.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: next })
      })
      if (res.ok) {
        setRules(rules.map(r => r.id === rule.id ? { ...r, active: next } : r))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleSaveRule = async () => {
    setRulesLoading(true)
    try {
      const payload = { ...ruleForm }
      let res
      if (editingRule && editingRule.id) {
        res = await apiFetch(`/audit-rules/${editingRule.id}/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      } else {
        res = await apiFetch('/audit-rules/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      }
      if (res.ok) {
        await fetchRules()
        resetRuleForm()
        setSuccessMsg('Regra de auditoria salva com sucesso.')
        setTimeout(() => setSuccessMsg(''), 3000)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setRulesLoading(false)
    }
  }

  const handleRunTransactionRules = async () => {
    setScanLoading(true)
    try {
      const res = await apiFetch('/transactions/scan_rules/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      if (res.ok) {
        const data = await res.json()
        setSuccessMsg(`Motor aplicado em ${data.transactions_scanned} transações. ${data.alerts_created} alertas criados.`)
        setTimeout(() => setSuccessMsg(''), 4000)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setScanLoading(false)
    }
  }

  const handleRunAlertRules = async () => {
    setAlertScanLoading(true)
    try {
      const res = await apiFetch('/alerts/scan_rules/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      if (res.ok) {
        const data = await res.json()
        setSuccessMsg(`Regras aplicadas em ${data.alerts_scanned} alertas. ${data.alerts_updated} atualizados.`)
        setTimeout(() => setSuccessMsg(''), 4000)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setAlertScanLoading(false)
    }
  }

  const handleSaveProfile = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/context/profile/current/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile)
      })
      
      if (res.ok) {
        setSuccessMsg('Perfil atualizado com sucesso!')
        setTimeout(() => setSuccessMsg(''), 3000)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Settings className="w-6 h-6 text-indigo-600" />
            Configurações
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Gerencie seu perfil, integrações e preferências do sistema.
          </p>
        </div>
        {successMsg && (
            <motion.div 
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-green-100 text-green-700 px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium"
            >
                <CheckCircle className="w-4 h-4" />
                {successMsg}
            </motion.div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex overflow-x-auto gap-2 border-b border-gray-200 dark:border-gray-700 pb-1">
        <TabButton id="profile" label="Perfil & Contexto" icon={User} active={activeTab} onClick={setActiveTab} />
        <TabButton id="integrations" label="Integrações" icon={Webhook} active={activeTab} onClick={setActiveTab} />
        <TabButton id="system" label="Sistema IA" icon={Activity} active={activeTab} onClick={setActiveTab} />
        <TabButton id="rules" label="Regras de Auditoria" icon={AlertTriangle} active={activeTab} onClick={setActiveTab} />
      </div>

      {/* Content */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 min-h-[400px]">
        {loading && <div className="absolute top-0 left-0 w-full h-1 bg-indigo-100 dark:bg-gray-700 overflow-hidden"><div className="h-full bg-indigo-600 animate-progress"></div></div>}
        
        {activeTab === 'profile' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
                <SectionHeader title="Contexto Organizacional" description="Defina a estrutura da sua empresa para calibrar a IA." icon={Building} />
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <InputGroup label="Setor de Atuação">
                        <select 
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none"
                            value={profile.sector}
                            onChange={(e) => setProfile({...profile, sector: e.target.value})}
                        >
                            <option value="Manufacturing">Manufatura</option>
                            <option value="Services">Serviços/Consultoria</option>
                            <option value="SaaS">Tecnologia (SaaS)</option>
                            <option value="Retail">Varejo</option>
                            <option value="Public">Setor Público</option>
                            <option value="Financial">Financeiro</option>
                            <option value="Other">Outros</option>
                        </select>
                    </InputGroup>

                    <InputGroup label="Estrutura Organizacional">
                        <select 
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none"
                            value={profile.org_structure}
                            onChange={(e) => setProfile({...profile, org_structure: e.target.value})}
                        >
                            <option value="Functional">Funcional</option>
                            <option value="Divisional">Divisional</option>
                            <option value="Matrix">Matricial</option>
                            <option value="SME">Pequena/Média Empresa</option>
                        </select>
                    </InputGroup>

                    <InputGroup label="País / Região Principal">
                        <div className="relative">
                            <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input 
                                type="text" 
                                className="w-full pl-10 pr-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none"
                                value={profile.country || ''}
                                onChange={(e) => setProfile({...profile, country: e.target.value})}
                                placeholder="Ex: Brasil"
                            />
                        </div>
                    </InputGroup>

                    <InputGroup label="Moeda Base">
                        <div className="relative">
                            <CreditCard className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input 
                                type="text" 
                                className="w-full pl-10 pr-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none"
                                value={profile.base_currency}
                                onChange={(e) => setProfile({...profile, base_currency: e.target.value})}
                            />
                        </div>
                    </InputGroup>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                    <div className="space-y-3">
                        <SectionHeader title="Regulações Aplicáveis" description="Defina quais normas regulatórias impactam suas auditorias." icon={Shield} />
                        <div className="grid grid-cols-2 gap-2 mt-2">
                            {['SOX', 'FCPA', 'LGPD', 'GDPR', 'PCI-DSS', 'IFRS'].map(code => (
                                <label key={code} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                                    <input
                                        type="checkbox"
                                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                        checked={Array.isArray(profile.regulatory_frameworks) ? profile.regulatory_frameworks.includes(code) : false}
                                        onChange={(e) => {
                                            const current = Array.isArray(profile.regulatory_frameworks) ? profile.regulatory_frameworks : []
                                            const next = e.target.checked ? [...current, code] : current.filter((v: string) => v !== code)
                                            setProfile({ ...profile, regulatory_frameworks: next })
                                        }}
                                    />
                                    <span>{code}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    <div className="space-y-3">
                        <SectionHeader title="Domínios de Auditoria Ativos" description="Quais áreas de processo estão sob escopo de auditoria contínua." icon={Activity} />
                        <div className="grid grid-cols-2 gap-2 mt-2">
                            {['Compras', 'Despesas/Viagem', 'Folha de Pagamento', 'Receitas/Vendas', 'Contratos', 'TI', 'Compliance'].map(domain => (
                                <label key={domain} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                                    <input
                                        type="checkbox"
                                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                        checked={Array.isArray(profile.audit_domains) ? profile.audit_domains.includes(domain) : false}
                                        onChange={(e) => {
                                            const current = Array.isArray(profile.audit_domains) ? profile.audit_domains : []
                                            const next = e.target.checked ? [...current, domain] : current.filter((v: string) => v !== domain)
                                            setProfile({ ...profile, audit_domains: next })
                                        }}
                                    />
                                    <span>{domain}</span>
                                </label>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="border-t border-gray-100 dark:border-gray-700 pt-6 mt-4">
                    <SectionHeader title="Apetite de Risco" description="Orienta a calibragem das regras e da IA." icon={Shield} />
                    <div className="mt-3 flex flex-col md:flex-row md:items-center gap-4">
                        <select
                            className="w-full md:w-64 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={profile.risk_appetite || 'Balanced'}
                            onChange={(e) => setProfile({ ...profile, risk_appetite: e.target.value })}
                        >
                            <option value="Conservative">Conservador</option>
                            <option value="Balanced">Equilibrado</option>
                            <option value="Aggressive">Agressivo</option>
                        </select>
                        <p className="text-xs text-gray-500 dark:text-gray-400 max-w-xl">
                            Conservador tende a priorizar controles e compliance, gerando mais alertas.
                            Agressivo foca em fraudes e perdas materiais mais extremas, com menos ruído.
                        </p>
                    </div>
                </div>

                <div className="border-t border-gray-100 dark:border-gray-700 pt-6">
                    <SectionHeader title="Persona do Auditor" description="Como a IA deve se comportar em relação ao seu perfil." icon={User} />
                    <div className="mt-4 p-4 bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-800 rounded-lg flex items-start gap-3">
                        <div className="p-2 bg-white dark:bg-gray-800 rounded-full text-indigo-600 shadow-sm">
                            <Activity className="w-5 h-5" />
                        </div>
                        <div>
                            <h4 className="font-bold text-gray-900 dark:text-white">Persona Atual: {profile.persona}</h4>
                            <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                                O sistema identificou este perfil com base no seu histórico de feedback e aprovações.
                                {profile.persona === 'Skeptical Analyst' && ' Você tende a ser minucioso, então a IA reduziu a taxa de falsos positivos.'}
                                {profile.persona === 'High-Value Approver' && ' Você lida com grandes volumes, o foco é em anomalias financeiras.'}
                            </p>
                        </div>
                    </div>
                </div>

                <div className="flex justify-end pt-4">
                    <button 
                        onClick={handleSaveProfile}
                        disabled={loading}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg flex items-center gap-2 shadow-sm transition-colors"
                    >
                        {loading ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Save className="w-4 h-4" />}
                        Salvar Alterações
                    </button>
                </div>
            </motion.div>
        )}

        {activeTab === 'integrations' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
                <SectionHeader title="Notificações & Webhooks" description="Conecte o AuditAI às suas ferramentas de comunicação." icon={Bell} />
                
                <div className="space-y-4">
                    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-xl flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center">
                                <Webhook className="w-5 h-5 text-gray-500" />
                            </div>
                            <div>
                                <h4 className="font-bold text-gray-900 dark:text-white">Slack Webhook</h4>
                                <p className="text-xs text-gray-500">Envie alertas críticos para um canal do Slack.</p>
                            </div>
                        </div>
                        <input 
                            type="text" 
                            placeholder="https://hooks.slack.com/..." 
                            className="w-1/2 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={webhooks.slack}
                            onChange={(e) => setWebhooks({...webhooks, slack: e.target.value})}
                        />
                    </div>
                </div>

                <div className="border-t border-gray-100 dark:border-gray-700 pt-6">
                    <SectionHeader title="Chaves de API" description="Gerencie o acesso de sistemas externos." icon={Key} />
                    <div className="mt-4 p-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-100 dark:border-yellow-800 rounded-lg flex gap-3">
                        <AlertTriangle className="w-5 h-5 text-yellow-600" />
                        <div>
                            <h4 className="font-bold text-yellow-800 dark:text-yellow-500 text-sm">Acesso Restrito</h4>
                            <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
                                Para gerar novas chaves de API para ingestão de dados, entre em contato com o administrador do sistema.
                            </p>
                        </div>
                    </div>
                </div>
            </motion.div>
        )}

        {activeTab === 'system' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
                <SectionHeader title="Calibragem da IA" description="Ajuste a sensibilidade dos modelos de risco." icon={Shield} />
                
                <div className="max-w-xl">
                    <div className="flex justify-between mb-2">
                        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Sensibilidade de Risco</label>
                        <span className="text-sm font-bold text-indigo-600">{(sensitivity * 100).toFixed(0)}%</span>
                    </div>
                    <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        value={sensitivity}
                        onChange={(e) => setSensitivity(parseFloat(e.target.value))}
                        className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                    />
                    <div className="flex justify-between mt-2 text-xs text-gray-500">
                        <span>Conservador (Menos Alertas)</span>
                        <span>Agressivo (Mais Alertas)</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-4 bg-gray-50 dark:bg-gray-900 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                        Aumentar a sensibilidade resultará em mais alertas de "Falso Positivo", mas reduzirá a chance de fraudes passarem despercebidas.
                    </p>
                </div>
            </motion.div>
        )}
        {activeTab === 'rules' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
                <SectionHeader title="Regras de Auditoria" description="Defina condições de risco genéricas para diferentes domínios." icon={AlertTriangle} />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Regras Configuradas</h4>
                            <div className="hidden lg:flex items-center gap-2 text-xs">
                                <select
                                    className="px-2 py-1 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300"
                                    value={filterModel}
                                    onChange={(e) => setFilterModel(e.target.value)}
                                >
                                    <option value="all">Todos os modelos</option>
                                    <option value="transaction">Transações</option>
                                    <option value="alert">Alertas</option>
                                    <option value="case">Casos</option>
                                </select>
                                <select
                                    className="px-2 py-1 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300"
                                    value={filterSeverity}
                                    onChange={(e) => setFilterSeverity(e.target.value)}
                                >
                                    <option value="all">Todas severidades</option>
                                    <option value="Critical">Critical</option>
                                    <option value="High">High</option>
                                    <option value="Medium">Medium</option>
                                    <option value="Low">Low</option>
                                </select>
                                <select
                                    className="px-2 py-1 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300"
                                    value={filterActive}
                                    onChange={(e) => setFilterActive(e.target.value)}
                                >
                                    <option value="all">Todas</option>
                                    <option value="active">Ativas</option>
                                    <option value="inactive">Inativas</option>
                                </select>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleRunAlertRules}
                                    disabled={alertScanLoading}
                                    className="text-xs px-3 py-1 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50 disabled:opacity-50"
                                >
                                    {alertScanLoading ? 'Ajustando alertas...' : 'Aplicar em alertas'}
                                </button>
                                <button
                                    onClick={handleRunTransactionRules}
                                    disabled={scanLoading}
                                    className="text-xs px-3 py-1 rounded-lg bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50 disabled:opacity-50"
                                >
                                    {scanLoading ? 'Executando motor...' : 'Executar em transações'}
                                </button>
                                <button
                                    onClick={resetRuleForm}
                                    className="text-xs px-3 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                                >
                                    Nova Regra
                                </button>
                            </div>
                        </div>
                        <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden max-h-[360px] overflow-y-auto">
                            {rulesLoading && (
                                <div className="p-4 text-sm text-gray-500">Carregando regras...</div>
                            )}
                            {!rulesLoading && rules.length === 0 && (
                                <div className="p-4 text-sm text-gray-500">Nenhuma regra cadastrada.</div>
                            )}
                            {!rulesLoading && rules.length > 0 && (
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-gray-50 dark:bg-gray-900/40">
                                        <tr>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Nome</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Domínio</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Alvo</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Condição</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Severidade</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Ativa</th>
                                            <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase text-right">Ações</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                        {rules
                                            .filter(rule => filterModel === 'all' || rule.model === filterModel)
                                            .filter(rule => filterSeverity === 'all' || rule.severity === filterSeverity)
                                            .filter(rule => {
                                                if (filterActive === 'all') return true
                                                if (filterActive === 'active') return rule.active
                                                if (filterActive === 'inactive') return !rule.active
                                                return true
                                            })
                                            .map(rule => (
                                            <tr
                                                key={rule.id}
                                                className="hover:bg-gray-50 dark:hover:bg-gray-800/60"
                                            >
                                                <td 
                                                    className="px-3 py-2 text-gray-900 dark:text-gray-100 cursor-pointer"
                                                    onClick={() => handleEditRule(rule)}
                                                >
                                                    {rule.name}
                                                </td>
                                                <td className="px-3 py-2 text-xs text-gray-500">{rule.domain}</td>
                                                <td className="px-3 py-2 text-xs text-gray-500">{rule.model}.{rule.field}</td>
                                                <td className="px-3 py-2 text-xs text-gray-500">{rule.operator} {rule.value}</td>
                                                <td className="px-3 py-2">
                                                    <span className="inline-flex px-2 py-1 rounded-full text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200">
                                                        {rule.severity}
                                                    </span>
                                                </td>
                                                <td className="px-3 py-2">
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); handleToggleRuleActive(rule) }}
                                                        className={`text-xs px-2 py-1 rounded-full border ${
                                                            rule.active
                                                            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700 text-green-700 dark:text-green-300'
                                                            : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-500'
                                                        }`}
                                                    >
                                                        {rule.active ? 'Ativa' : 'Inativa'}
                                                    </button>
                                                </td>
                                                <td className="px-3 py-2 text-right">
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); handleCloneRule(rule) }}
                                                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                                                    >
                                                        <Copy className="w-3 h-3" />
                                                        Clonar
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                            {editingRule ? 'Editar Regra' : 'Nova Regra'}
                        </h4>
                        <div className="space-y-4">
                            <InputGroup label="Nome da Regra">
                                <input
                                    type="text"
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                    value={ruleForm.name}
                                    onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
                                />
                            </InputGroup>
                            <InputGroup label="Código (ID)">
                                <input
                                    type="text"
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm uppercase"
                                    value={ruleForm.code}
                                    onChange={(e) => setRuleForm({ ...ruleForm, code: e.target.value.toUpperCase() })}
                                    disabled={!!editingRule}
                                />
                            </InputGroup>
                            <div className="grid grid-cols-3 gap-4">
                                <InputGroup label="Modelo">
                                    <select
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.model}
                                        onChange={(e) => setRuleForm({ ...ruleForm, model: e.target.value })}
                                    >
                                        <option value="transaction">Transações</option>
                                        <option value="alert">Alertas</option>
                                        <option value="case">Casos</option>
                                    </select>
                                </InputGroup>
                                <InputGroup label="Domínio">
                                    <select
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.domain}
                                        onChange={(e) => setRuleForm({ ...ruleForm, domain: e.target.value })}
                                    >
                                        <option value="Compras">Compras</option>
                                        <option value="Despesas/Viagem">Despesas/Viagem</option>
                                        <option value="Folha de Pagamento">Folha de Pagamento</option>
                                        <option value="Receitas/Vendas">Receitas/Vendas</option>
                                        <option value="Contabilidade">Contabilidade</option>
                                        <option value="TI">TI</option>
                                        <option value="Outro">Outro</option>
                                    </select>
                                </InputGroup>
                                <InputGroup label="Campo">
                                    <input
                                        type="text"
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.field}
                                        onChange={(e) => setRuleForm({ ...ruleForm, field: e.target.value })}
                                        placeholder="amount, vendor, category"
                                    />
                                </InputGroup>
                            </div>
                            <div className="grid grid-cols-3 gap-4">
                                <InputGroup label="Operador">
                                    <select
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.operator}
                                        onChange={(e) => setRuleForm({ ...ruleForm, operator: e.target.value })}
                                    >
                                        <option value=">">{'>'}</option>
                                        <option value=">=">{'>='}</option>
                                        <option value="<">{'<'}</option>
                                        <option value="<=">{'<='}</option>
                                        <option value="==">==</option>
                                        <option value="!=">!=</option>
                                    </select>
                                </InputGroup>
                                <InputGroup label="Valor">
                                    <input
                                        type="text"
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.value}
                                        onChange={(e) => setRuleForm({ ...ruleForm, value: e.target.value })}
                                    />
                                </InputGroup>
                                <InputGroup label="Severidade">
                                    <select
                                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                        value={ruleForm.severity}
                                        onChange={(e) => setRuleForm({ ...ruleForm, severity: e.target.value })}
                                    >
                                        <option value="Low">Low</option>
                                        <option value="Medium">Medium</option>
                                        <option value="High">High</option>
                                        <option value="Critical">Critical</option>
                                    </select>
                                </InputGroup>
                            </div>
                            <InputGroup label="Materialidade (0 a 1)">
                                <input
                                    type="number"
                                    min={0}
                                    max={1}
                                    step={0.1}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                    value={ruleForm.materiality}
                                    onChange={(e) => setRuleForm({ ...ruleForm, materiality: parseFloat(e.target.value) || 0 })}
                                />
                            </InputGroup>
                            <InputGroup label="Descrição">
                                <textarea
                                    rows={3}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                                    value={ruleForm.description}
                                    onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })}
                                    placeholder="Ex: Transações acima de 100k em fornecedores críticos."
                                />
                            </InputGroup>
                            <div className="flex justify-between items-center pt-2">
                                <div className="flex items-center gap-2">
                                    <input
                                        id="rule-active"
                                        type="checkbox"
                                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                        checked={ruleForm.active}
                                        onChange={(e) => setRuleForm({ ...ruleForm, active: e.target.checked })}
                                    />
                                    <label htmlFor="rule-active" className="text-sm text-gray-700 dark:text-gray-300">
                                        Regra ativa
                                    </label>
                                </div>
                                <div className="flex gap-2">
                                    {editingRule && (
                                        <button
                                            type="button"
                                            onClick={resetRuleForm}
                                            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                                        >
                                            Cancelar
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={handleSaveRule}
                                        disabled={rulesLoading || !ruleForm.name || !ruleForm.code}
                                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm"
                                    >
                                        Salvar Regra
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </motion.div>
        )}
      </div>
    </div>
  )
}

function TabButton({ id, label, icon: Icon, active, onClick }: any) {
    return (
        <button 
            onClick={() => onClick(id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                active === id 
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400' 
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
        >
            <Icon className="w-4 h-4" />
            {label}
        </button>
    )
}

function SectionHeader({ title, description, icon: Icon }: any) {
    return (
        <div className="flex items-start gap-3">
            <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-indigo-600 dark:text-indigo-400">
                <Icon className="w-5 h-5" />
            </div>
            <div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">{title}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
            </div>
        </div>
    )
}

function InputGroup({ label, children }: any) {
    return (
        <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
            {children}
        </div>
    )
}
