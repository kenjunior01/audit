"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import ForecastChart from '@/components/dashboard/ForecastChart'
import StatsGrid from '@/components/dashboard/StatsGrid'
import TransactionInspector from '@/components/dashboard/TransactionInspector'
import UserInsightsCard from '@/components/dashboard/UserInsightsCard'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Search, Download, Filter, ChevronLeft, ChevronRight, Eye, MoreHorizontal, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

type Tx = {
  id: string | number
  transaction_id: string
  vendor?: string | null
  category?: string | null
  amount: number
  currency?: string | null
  timestamp: string
}

export default function TransactionsPage() {
  useRequireToken()
  const [items, setItems] = useState<Tx[]>([])
  const [loading, setLoading] = useState(false)
  const [vendor, setVendor] = useState('')
  const [category, setCategory] = useState('')
  const [nextUrl, setNextUrl] = useState<string | null>(null)
  const [prevUrl, setPrevUrl] = useState<string | null>(null)
  
  // New State for Inspector
  const [selectedTx, setSelectedTx] = useState<string | null>(null)
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [autoMessage, setAutoMessage] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)

  const outOfScopeStats = (() => {
    if (!contextSummary || items.length === 0) {
      return { total: items.length, outOfScope: 0, inScope: items.length }
    }
    let outOfScope = 0
    for (const it of items) {
      const isOut =
        contextSummary &&
        Array.isArray(contextSummary.audit_domains) &&
        contextSummary.audit_domains.length > 0 &&
        it.category &&
        !contextSummary.audit_domains.includes(it.category)
      if (isOut) {
        outOfScope += 1
      }
    }
    return { total: items.length, outOfScope, inScope: items.length - outOfScope }
  })()
  const outOfScopeRatio = outOfScopeStats.total > 0 ? outOfScopeStats.outOfScope / outOfScopeStats.total : 0

  const load = () => {
    setLoading(true)
    const params = new URLSearchParams()
    params.set('page_size', '50')
    if (vendor) params.set('vendor', vendor)
    if (category) params.set('category', category)
    apiFetch(`/transactions?${params.toString()}`)
      .then(r => r.json())
      .then(d => {
        const arr = d?.results || d?.items || Array.isArray(d) ? d : []
        setItems(arr)
        setNextUrl(d?.next || null)
        setPrevUrl(d?.previous || null)
      })
      .finally(() => setLoading(false))
  }

  const loadLink = (url: string | null) => {
    if (!url) return
    setLoading(true)
    apiFetch(url).then(r=>r.json()).then(d=>{
      const arr = d?.results || d?.items || Array.isArray(d) ? d : []
      setItems(arr)
      setNextUrl(d?.next || null)
      setPrevUrl(d?.previous || null)
    }).finally(()=>setLoading(false))
  }

  const [showExportMenu, setShowExportMenu] = useState(false)

  const handleCreateScopeAgent = async () => {
    if (!contextSummary || !outOfScopeStats.total) return
    setAutoLoading(true)
    setAutoMessage(null)
    try {
      const res = await apiFetch('/ai/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: 'create_scope_guard_agent',
          action_type: 'create_risk_agent',
          params: {
            name: 'Monitorar Transações Fora do Escopo',
            conditions: [
              {
                metric: 'category',
                operator: 'not_in',
                value: Array.isArray(contextSummary.audit_domains)
                  ? contextSummary.audit_domains
                  : [],
              },
            ],
            action: 'notify_manager',
            specialization: 'ScopeGuard',
          },
        }),
      })
      const data = await res.json()
      setAutoMessage(data?.message || 'Agente de risco criado a partir do escopo atual.')
    } catch (e) {
      setAutoMessage('Erro ao criar agente de risco.')
    } finally {
      setAutoLoading(false)
    }
  }

  const exportData = (format: 'excel' | 'csv') => {
    const params = new URLSearchParams()
    if (vendor) params.set('vendor', vendor)
    if (category) params.set('category', category)
    
    const endpoint = format === 'excel' ? '/transactions/export_excel/' : '/transactions/export_csv/'
    
    apiFetch(`${endpoint}?${params.toString()}`)
      .then(r => r.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `transactions_${new Date().getTime()}.${format === 'excel' ? 'xlsx' : 'csv'}`
        a.click()
        window.URL.revokeObjectURL(url)
        setShowExportMenu(false)
      })
      .catch(err => alert('Erro ao exportar: ' + err))
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-8">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Audit Command Center</h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">Monitoramento de risco em tempo real e análise preditiva.</p>
        </div>
        <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium animate-pulse">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                Live System
            </span>
        </div>
      </div>

      {contextSummary && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs text-indigo-900 flex flex-col gap-2">
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
                {Math.round((outOfScopeStats.outOfScope / outOfScopeStats.total) * 100)}% das transações exibidas estão fora dos domínios de auditoria configurados.
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
                    Muitas transações estão fora do escopo. Deseja criar um agente automático?
                  </span>
                  <button
                    onClick={handleCreateScopeAgent}
                    disabled={autoLoading}
                    className="px-3 py-1 rounded-full text-[11px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {autoLoading ? 'Criando agente...' : 'Criar Agente de Risco de Escopo'}
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

      {/* Analytics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-4">
              <StatsGrid />
          </div>
          <div className="lg:col-span-3">
              <ForecastChart />
          </div>
          <div className="lg:col-span-1">
              <UserInsightsCard />
          </div>
      </div>

      {/* Transactions Table Section */}
      <Card className="border-none shadow-lg bg-white/80 dark:bg-gray-900/80 backdrop-blur-md">
        <CardHeader className="border-b border-gray-100 dark:border-gray-800 pb-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <CardTitle className="text-xl flex items-center gap-2">
                    Transações Recentes
                    <span className="text-xs font-normal text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">{items.length} carregados</span>
                </CardTitle>
                
                <div className="flex flex-wrap items-center gap-2">
                    <div className="relative group">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 group-focus-within:text-indigo-500 transition-colors" />
                        <input 
                            className="pl-9 pr-4 py-2 bg-gray-50 dark:bg-gray-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 w-40 md:w-64 transition-all" 
                            placeholder="Filtrar por fornecedor..." 
                            value={vendor} 
                            onChange={e=>setVendor(e.target.value)} 
                        />
                    </div>
                    <div className="relative group">
                        <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 group-focus-within:text-indigo-500 transition-colors" />
                        <input 
                            className="pl-9 pr-4 py-2 bg-gray-50 dark:bg-gray-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 w-32 md:w-48 transition-all" 
                            placeholder="Categoria..." 
                            value={category} 
                            onChange={e=>setCategory(e.target.value)} 
                        />
                    </div>
                    <button onClick={load} className="p-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-sm hover:shadow-indigo-500/30">
                        <Search className="h-4 w-4" />
                    </button>
                    <div className="relative">
                        <button 
                            onClick={() => setShowExportMenu(!showExportMenu)} 
                            className="p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition-colors flex items-center gap-2"
                            title="Exportar Dados"
                        >
                            <Download className="h-4 w-4" />
                        </button>
                        
                        <AnimatePresence>
                            {showExportMenu && (
                                <motion.div 
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: 10 }}
                                    className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-gray-700 z-50 overflow-hidden"
                                >
                                    <div className="p-2 space-y-1">
                                        <button 
                                            onClick={() => exportData('excel')}
                                            className="w-full text-left px-4 py-2 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-gray-700 dark:text-gray-300 rounded-lg transition-colors flex items-center gap-2"
                                        >
                                            <div className="w-8 h-8 rounded bg-green-100 dark:bg-green-900/30 flex items-center justify-center text-green-600 dark:text-green-400">
                                                XL
                                            </div>
                                            <div>
                                                <p className="font-medium">Excel (.xlsx)</p>
                                                <p className="text-[10px] text-gray-500">Relatório Completo</p>
                                            </div>
                                        </button>
                                        <button 
                                            onClick={() => exportData('csv')}
                                            className="w-full text-left px-4 py-2 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-gray-700 dark:text-gray-300 rounded-lg transition-colors flex items-center gap-2"
                                        >
                                            <div className="w-8 h-8 rounded bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-600 dark:text-blue-400">
                                                CSV
                                            </div>
                                            <div>
                                                <p className="font-medium">CSV (.csv)</p>
                                                <p className="text-[10px] text-gray-500">Dados Brutos</p>
                                            </div>
                                        </button>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </div>
        </CardHeader>
        <CardContent className="p-0">
            {loading && (
                <div className="p-8 text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                    <p className="mt-2 text-sm text-gray-500">Sincronizando dados...</p>
                </div>
            )}
            
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-50/50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800">
                        <tr>
                            <th className="px-6 py-3 font-medium">ID Transação</th>
                            <th className="px-6 py-3 font-medium">Fornecedor</th>
                            <th className="px-6 py-3 font-medium">Categoria</th>
                            <th className="px-6 py-3 font-medium text-right">Valor</th>
                            <th className="px-6 py-3 font-medium">Data</th>
                            <th className="px-6 py-3 font-medium text-center">Ações</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {items.map((it, idx) => {
                            const outOfScope =
                              contextSummary &&
                              Array.isArray(contextSummary.audit_domains) &&
                              contextSummary.audit_domains.length > 0 &&
                              it.category &&
                              !contextSummary.audit_domains.includes(it.category)

                            return (
                            <motion.tr 
                                key={it.id} 
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: idx * 0.03 }}
                                className="group hover:bg-indigo-50/30 dark:hover:bg-indigo-900/10 transition-colors"
                            >
                                <td className="px-6 py-4 font-mono text-xs text-gray-500">
                                    {String(it.transaction_id).substring(0, 12)}...
                                </td>
                                <td className="px-6 py-4 font-medium text-gray-900 dark:text-gray-100">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-[10px] text-white font-bold uppercase">
                                            {it.vendor?.substring(0,2) || 'NA'}
                                        </div>
                                        {it.vendor || 'Desconhecido'}
                                    </div>
                                </td>
                                <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                                    <div className="flex flex-col gap-1">
                                      <span className="inline-flex w-fit items-center px-2 py-1 rounded-md bg-gray-100 dark:bg-gray-800 text-xs">
                                          {it.category || 'Geral'}
                                      </span>
                                      {outOfScope && (
                                        <span className="inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                                          Fora do contexto configurado
                                        </span>
                                      )}
                                    </div>
                                </td>
                                <td className="px-6 py-4 text-right font-medium">
                                    <div className={`flex items-center justify-end gap-1 ${Number(it.amount) > 5000 ? 'text-orange-600 dark:text-orange-400' : 'text-gray-900 dark:text-gray-100'}`}>
                                        {it.currency || 'BRL'} {Number(it.amount).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        {Number(it.amount) > 10000 && <ArrowUpRight className="h-3 w-3" />}
                                    </div>
                                </td>
                                <td className="px-6 py-4 text-gray-500">
                                    {new Date(it.timestamp).toLocaleDateString()} 
                                    <span className="text-xs ml-1 text-gray-400">{new Date(it.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                </td>
                                <td className="px-6 py-4 text-center">
                                    <button 
                                        onClick={() => setSelectedTx(String(it.id))}
                                        className="p-1.5 text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors group-hover:scale-110 transform duration-200"
                                        title="Investigar com IA"
                                    >
                                        <Eye className="h-4 w-4" />
                                    </button>
                                </td>
                            </motion.tr>
                          )
                        })}
                    </tbody>
                </table>
            </div>
            
            {/* Pagination */}
            <div className="p-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
                <span className="text-sm text-gray-500">Mostrando {items.length} resultados</span>
                <div className="flex items-center gap-2">
                    <button 
                        onClick={()=>loadLink(prevUrl)} 
                        disabled={!prevUrl || loading}
                        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button 
                        onClick={()=>loadLink(nextUrl)} 
                        disabled={!nextUrl || loading}
                        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <ChevronRight className="h-4 w-4" />
                    </button>
                </div>
            </div>
        </CardContent>
      </Card>

      {/* Inspector Drawer */}
      <AnimatePresence>
        {selectedTx && (
          <TransactionInspector 
            transactionId={selectedTx} 
            onClose={() => setSelectedTx(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  )
}
