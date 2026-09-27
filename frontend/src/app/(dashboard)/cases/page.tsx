'use client'

import { useState, useEffect , Suspense} from 'react'
import { useSearchParams } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  FileText, 
  Search, 
  Filter, 
  Plus, 
  AlertTriangle, 
  X,
  Download,
  FileSpreadsheet
} from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { CaseDetailsDrawer } from '@/components/dashboard/CaseDetailsDrawer'

interface AuditCase {
  id: number
  title: string
  description: string
  status: string
  priority: string
  assigned_to: string
  transaction_id: string | null
  updated_at: string
  created_by: string
  created_at?: string
  deadline?: string | null
  finding_type?: string | null
  inherent_risk?: number | null
  residual_risk?: number | null
  action_owner?: string | null
  action_plan?: string | null
  action_due_date?: string | null
}

interface CaseComment {
  id: number
  user_id: string
  comment: string
  created_at: string
}

const isOverdue = (deadline?: string | null) => {
  if (!deadline) return false
  return new Date(deadline) < new Date()
}

function CasesPageContent() {
  const [cases, setCases] = useState<AuditCase[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState<string>('All')
  const [filterPriority, setFilterPriority] = useState<string>('All')
  const [searchQuery, setSearchQuery] = useState('')
  const searchParams = useSearchParams()
  const [prefillData, setPrefillData] = useState<{title?: string, description?: string, transaction_id?: string}>({})
  
  // Modal & Drawer State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [selectedCase, setSelectedCase] = useState<AuditCase | null>(null)
  const [clustering, setClustering] = useState(false)
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [autoMessage, setAutoMessage] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)

  useEffect(() => {
    fetchCases()
    
    // Check for creation params
    if (searchParams.get('create') === 'true') {
        setPrefillData({
            title: searchParams.get('title') || '',
            description: searchParams.get('description') || '',
            transaction_id: searchParams.get('transaction_id') || ''
        })
        setIsCreateModalOpen(true)
    }
  }, [searchParams])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  const [showExportMenu, setShowExportMenu] = useState(false)

  const exportData = (format: 'excel' | 'csv') => {
    const params = new URLSearchParams()
    if (filterStatus !== 'All') params.set('status', filterStatus)
    if (filterPriority !== 'All') params.set('priority', filterPriority)
    
    const endpoint = format === 'excel' ? '/cases/export_excel/' : '/cases/export_csv/'
    
    apiFetch(`${endpoint}?${params.toString()}`)
      .then(r => r.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `casos_${new Date().getTime()}.${format === 'excel' ? 'xlsx' : 'csv'}`
        a.click()
        window.URL.revokeObjectURL(url)
        setShowExportMenu(false)
      })
      .catch(err => alert('Erro ao exportar: ' + err))
  }

  const fetchCases = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/cases/')
      if (res.ok) {
        const data = await res.json()
        setCases(data)
      }
    } catch (error) {
      console.error('Failed to fetch cases:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleAutoCluster = async () => {
    setClustering(true)
    try {
        const res = await apiFetch('/cases/auto-cluster', { method: 'POST' })
        if (res.ok) {
            const data = await res.json()
            if (data.cases_created > 0) {
                alert(`Sucesso! ${data.cases_created} casos criados a partir de ${data.processed_alerts} alertas.`)
                fetchCases()
            } else {
                alert('Nenhum agrupamento de risco encontrado nos alertas pendentes.')
            }
        } else {
            alert('Erro ao executar auto-agrupamento.')
        }
    } catch (e) {
        console.error(e)
        alert('Erro de conexão.')
    } finally {
        setClustering(false)
    }
  }

  const handleCreateCase = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    
    try {
      const res = await apiFetch('/cases/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: formData.get('title'),
          description: formData.get('description'),
          priority: formData.get('priority'),
          status: 'New',
          assigned_to: formData.get('assigned_to') || 'Unassigned',
          transaction_id: formData.get('transaction_id') || null
        })
      })
      
      if (res.ok) {
        setIsCreateModalOpen(false)
        fetchCases()
      }
    } catch (error) {
      console.error('Failed to create case:', error)
    }
  }

  const getStatusColor = (status: string) => {
    const s = status.toLowerCase()
    if (s === 'new') {
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
    }
    if (s === 'in progress') {
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
    }
    if (s === 'under review') {
      return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200'
    }
    if (s === 'resolved') {
      return 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
    }
    if (s.startsWith('closed')) {
      return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
    }
    return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
  }

  const getPriorityColor = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'critical': return 'text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
      case 'high': return 'text-orange-600 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800'
      case 'medium': return 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
      case 'low': return 'text-green-600 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
      default: return 'text-gray-600 border border-gray-200'
    }
  }

  const filteredCases = cases.filter(c => {
    const matchesStatus = filterStatus === 'All' || c.status.toLowerCase() === filterStatus.toLowerCase()
    const matchesPriority = filterPriority === 'All' || c.priority.toLowerCase() === filterPriority.toLowerCase()
    const matchesSearch = c.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          (c.transaction_id && c.transaction_id.toLowerCase().includes(searchQuery.toLowerCase())) ||
                          (c.assigned_to && c.assigned_to.toLowerCase().includes(searchQuery.toLowerCase()))
    return matchesStatus && matchesPriority && matchesSearch
  })

  const outOfScopeStats = (() => {
    if (!contextSummary || filteredCases.length === 0) {
      return { total: filteredCases.length, outOfScope: 0, inScope: filteredCases.length }
    }
    let outOfScope = 0
    for (const c of filteredCases) {
      const domain = c.finding_type
      const isOut =
        contextSummary &&
        Array.isArray(contextSummary.audit_domains) &&
        contextSummary.audit_domains.length > 0 &&
        domain &&
        !contextSummary.audit_domains.includes(domain)
      if (isOut) {
        outOfScope += 1
      }
    }
    return { total: filteredCases.length, outOfScope, inScope: filteredCases.length - outOfScope }
  })()
  const outOfScopeRatio = outOfScopeStats.total > 0 ? outOfScopeStats.outOfScope / outOfScopeStats.total : 0

  const handleEscalateOutOfScopeCases = async () => {
    if (!contextSummary || !outOfScopeStats.total) return
    setAutoLoading(true)
    setAutoMessage(null)
    try {
      const res = await apiFetch('/ai/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: 'escalate_out_of_scope_cases',
          action_type: 'create_risk_agent',
          params: {
            name: 'Escalar Casos Fora do Escopo',
            conditions: [
              {
                metric: 'finding_type',
                operator: 'not_in',
                value: Array.isArray(contextSummary.audit_domains)
                  ? contextSummary.audit_domains
                  : [],
              },
            ],
            action: 'notify_manager',
            specialization: 'CaseScope',
          },
        }),
      })
      const data = await res.json()
      setAutoMessage(data?.message || 'Fluxo automático criado para casos fora do escopo.')
    } catch (e) {
      setAutoMessage('Erro ao criar fluxo automático para casos fora do escopo.')
    } finally {
      setAutoLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 relative h-full">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-600" />
            Gestão de Casos
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Central de comando para investigações e auditorias em andamento.
          </p>
        </div>
        <div className="flex gap-3">
            <div className="relative">
              <button 
                onClick={() => setShowExportMenu(!showExportMenu)}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
              >
                <Download className="w-4 h-4" />
                Exportar
              </button>
              
              <AnimatePresence>
                {showExportMenu && (
                  <motion.div 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-gray-700 z-50 overflow-hidden"
                  >
                    <button 
                      onClick={() => exportData('excel')}
                      className="w-full text-left px-4 py-3 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-gray-700 dark:text-gray-300 flex items-center gap-3 transition-colors border-b border-gray-50 dark:border-gray-700"
                    >
                      <div className="w-8 h-8 rounded bg-green-100 dark:bg-green-900/30 flex items-center justify-center text-green-600 dark:text-green-400">
                        <FileSpreadsheet className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="font-medium">Excel (.xlsx)</p>
                        <p className="text-[10px] text-gray-500">Relatório Completo</p>
                      </div>
                    </button>
                    <button 
                      onClick={() => exportData('csv')}
                      className="w-full text-left px-4 py-3 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-gray-700 dark:text-gray-300 flex items-center gap-3 transition-colors"
                    >
                      <div className="w-8 h-8 rounded bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-600 dark:text-blue-400">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="font-medium">CSV (.csv)</p>
                        <p className="text-[10px] text-gray-500">Dados Brutos</p>
                      </div>
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <button 
              onClick={handleAutoCluster}
              disabled={clustering}
              className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors shadow-sm"
            >
              {clustering ? <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"/> : <Filter className="w-4 h-4" />}
              Auto-Agrupamento (IA)
            </button>
            <button 
              onClick={() => setIsCreateModalOpen(true)}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              Novo Caso
            </button>
        </div>
      </div>

      {contextSummary && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-3 text-xs text-indigo-900 flex flex-col gap-2">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span>
              <span className="font-semibold">País:</span> {contextSummary.country || 'Não definido'}
            </span>
            <span>
              <span className="font-semibold">Regulações:</span>{' '}
              {Array.isArray(contextSummary.regulatory_frameworks) && contextSummary.regulatory_frameworks.length > 0
                ? contextSummary.regulatory_frameworks.join(', ')
                : 'Nenhuma selecionada'}
            </span>
            <span>
              <span className="font-semibold">Domínios:</span>{' '}
              {Array.isArray(contextSummary.audit_domains) && contextSummary.audit_domains.length > 0
                ? contextSummary.audit_domains.join(', ')
                : 'Geral'}
            </span>
            <span>
              <span className="font-semibold">Apetite de Risco:</span>{' '}
              {contextSummary.risk_appetite === 'Conservative' && 'Conservador'}
              {contextSummary.risk_appetite === 'Balanced' && 'Equilibrado'}
              {contextSummary.risk_appetite === 'Aggressive' && 'Agressivo'}
              {!contextSummary.risk_appetite && 'Equilibrado'}
            </span>
          </div>
          {outOfScopeStats.total > 0 && outOfScopeStats.outOfScope > 0 && (
            <div className="space-y-1 text-[11px] text-gray-700">
              <div>
                {Math.round((outOfScopeStats.outOfScope / outOfScopeStats.total) * 100)}% dos casos exibidos estão fora dos domínios de auditoria configurados.
              </div>
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div className="h-full flex">
                  <div
                    className="bg-emerald-400"
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(100, (outOfScopeStats.inScope / outOfScopeStats.total) * 100)
                      )}%`,
                    }}
                  />
                  <div
                    className="bg-amber-400"
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(100, (outOfScopeStats.outOfScope / outOfScopeStats.total) * 100)
                      )}%`,
                    }}
                  />
                </div>
              </div>
              <div className="flex justify-between text-[10px] text-gray-500">
                <span>Dentro do escopo</span>
                <span>Fora do escopo</span>
              </div>
              {outOfScopeRatio >= 0.3 && (
                <div className="pt-1 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] text-gray-700">
                    Muitos casos estão fora do escopo. Deseja automatizar a escalada?
                  </span>
                  <button
                    onClick={handleEscalateOutOfScopeCases}
                    disabled={autoLoading}
                    className="px-3 py-1 rounded-full text-[11px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {autoLoading ? 'Configurando...' : 'Criar automação de escalonamento'}
                  </button>
                  {autoMessage && (
                    <span className="text-[11px] text-gray-500">
                      {autoMessage}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatsCard label="Total de Casos" value={cases.length} />
        <StatsCard 
          label="Em Atraso" 
          value={cases.filter(c => !c.status.toLowerCase().startsWith('closed') && isOverdue(c.deadline)).length} 
          color="text-red-600" 
        />
        <StatsCard label="Críticos" value={cases.filter(c => c.priority === 'Critical').length} color="text-red-600" />
        <StatsCard 
          label="Em Progresso" 
          value={cases.filter(c => ['in progress', 'under review'].includes(c.status.toLowerCase())).length} 
          color="text-yellow-600" 
        />
      </div>

      {/* Filters & Search */}
      <div className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-96">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input 
            type="text" 
            placeholder="Buscar por título, ID ou responsável..." 
            className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition-all text-sm"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-3 w-full md:w-auto overflow-x-auto">
          <SelectFilter 
            value={filterStatus} 
            onChange={setFilterStatus} 
            options={['All', 'New', 'In Progress', 'Under Review', 'Closed - Remediated', 'Closed - No Issue', 'Resolved', 'Closed']} 
            label="Status" 
          />
          <SelectFilter value={filterPriority} onChange={setFilterPriority} options={['All', 'Critical', 'High', 'Medium', 'Low']} label="Prioridade" />
        </div>
      </div>

      {/* Cases List */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden min-h-[400px]">
        {loading ? (
          <div className="p-8 text-center text-gray-500 flex flex-col items-center justify-center h-full">
            <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            Carregando casos...
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center h-full">
            <div className="bg-gray-100 dark:bg-gray-900 w-16 h-16 rounded-full flex items-center justify-center mb-4">
              <FileText className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Nenhum caso encontrado</h3>
            <p className="text-gray-500 mt-1">Tente ajustar os filtros ou crie um novo caso.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Caso / Título</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Relacionado A</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Prioridade</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Responsável</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Atualizado</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider w-10"></th>
                </tr>
              </thead>
              <motion.tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {filteredCases.map((c) => (
                  <motion.tr 
                    key={c.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    onClick={() => setSelectedCase(c)}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group cursor-pointer"
                  >
                    <td className="p-4">
                      <div className="flex items-start gap-3">
                        <div className="bg-indigo-100 dark:bg-indigo-900/30 p-2 rounded text-indigo-600 dark:text-indigo-400 mt-1">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-medium text-gray-900 dark:text-gray-100">#{c.id} - {c.title}</div>
                          <div className="text-xs text-gray-500 truncate max-w-[200px]">{c.description || 'Sem descrição'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      {c.transaction_id ? (
                        <div className="font-mono text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded w-fit border border-gray-200 dark:border-gray-700">
                          TX: {c.transaction_id}
                        </div>
                      ) : (
                        <span className="text-gray-400 text-sm italic">Geral</span>
                      )}
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium border ${getPriorityColor(c.priority)}`}>
                        {c.priority}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(c.status)}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900 flex items-center justify-center text-xs text-indigo-600 dark:text-indigo-300 font-bold">
                          {c.assigned_to ? c.assigned_to.charAt(0).toUpperCase() : '?'}
                        </div>
                        <span className="text-sm text-gray-700 dark:text-gray-300">{c.assigned_to || 'Não atribuído'}</span>
                      </div>
                    </td>
                    <td className="p-4 text-sm text-gray-500">
                      {new Date(c.updated_at).toLocaleDateString()}
                    </td>
                    <td className="p-4">
                      <button className="text-gray-400 hover:text-indigo-600 p-2 rounded-full hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors">
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Case Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full overflow-hidden border border-gray-200 dark:border-gray-700"
            >
              <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">Novo Caso de Auditoria</h2>
                <button onClick={() => setIsCreateModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreateCase} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Título</label>
                  <input name="title" defaultValue={prefillData.title} required type="text" className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Ex: Investigação de Fornecedor X" />
                  <input type="hidden" name="transaction_id" defaultValue={prefillData.transaction_id || ''} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
                  <textarea name="description" defaultValue={prefillData.description} rows={3} className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Detalhes iniciais do caso..."></textarea>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Prioridade</label>
                    <select name="priority" className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none">
                      <option value="Low">Baixa</option>
                      <option value="Medium" selected>Média</option>
                      <option value="High">Alta</option>
                      <option value="Critical">Crítica</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Prazo Limite (SLA)</label>
                    <input name="deadline" type="date" className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none" />
                  </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Responsável</label>
                    <input name="assigned_to" type="text" className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg outline-none" placeholder="Nome do Auditor" />
                </div>
                <div className="flex justify-end gap-3 mt-6">
                  <button type="button" onClick={() => setIsCreateModalOpen(false)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">Cancelar</button>
                  <button type="submit" className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition-colors">Criar Caso</button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Case Details Drawer */}
      <AnimatePresence>
        {selectedCase && (
          <CaseDetailsDrawer 
            auditCase={selectedCase} 
            onClose={() => setSelectedCase(null)} 
            onUpdate={() => {
              fetchCases()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function StatsCard({ label, value, color = "text-gray-900 dark:text-white" }: { label: string, value: number, color?: string }) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-shadow"
    >
      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </motion.div>
  )
}

function SelectFilter({ value, onChange, options, label }: { value: string, onChange: (v: string) => void, options: string[], label: string }) {
  return (
    <div className="flex flex-col min-w-[140px]">
       <label className="text-xs text-gray-500 mb-1 ml-1">{label}</label>
       <select 
        className="px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm outline-none cursor-pointer"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'Todos' : opt}</option>)}
      </select>
    </div>
  )
}

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <polyline points="9 18 15 12 9 6"></polyline>
    </svg>
  )
}


export default function CasesPage() {
  return (
    <Suspense fallback={null}>
      <CasesPageContent />
    </Suspense>
  )
}
