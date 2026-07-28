"use client"
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { X, Download, FileSpreadsheet, FileText } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

type Alert = {
  id: number
  transaction_id: string
  alert_type: string
  materiality: number
  category?: string | null
  vendor?: string | null
  timestamp: string
  context_risk?: number
  context_due_date?: string
  context_severity?: string
}

export default function AlertsPage() {
  useRequireToken()
  const searchParams = useSearchParams()
  const [items, setItems] = useState<Alert[]>([])
  const [loading, setLoading] = useState(false)
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [autoMessage, setAutoMessage] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)
  const outOfScopeStats = (() => {
    if (!contextSummary || items.length === 0) return { total: items.length, outOfScope: 0, inScope: items.length }
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
  
  // Initialize from URL params
  const [alertType, setAlertType] = useState(searchParams.get('alert_type') || '')
  const [category, setCategory] = useState(searchParams.get('category') || '')
  const [vendor, setVendor] = useState(searchParams.get('vendor') || '')
  const [department, setDepartment] = useState(searchParams.get('department') || '')
  
  const [nextUrl, setNextUrl] = useState<string | null>(null)
  const [prevUrl, setPrevUrl] = useState<string | null>(null)
  const [polling, setPolling] = useState(true)

  const load = () => {
    // If polling, don't show loading spinner to avoid flickering
    if (!polling) setLoading(true) 
    
    const params = new URLSearchParams()
    params.set('page_size', '50')
    if (alertType) params.set('alert_type', alertType)
    if (category) params.set('category', category)
    if (vendor) params.set('vendor', vendor)
    if (department) params.set('department', department)
    
    apiFetch(`/alerts?${params.toString()}`)
      .then(r => r.json())
      .then(d => {
        const arr = d?.results || d?.items || Array.isArray(d) ? d : []
        setItems(arr)
        setNextUrl(d?.next || null)
        setPrevUrl(d?.previous || null)
      })
      .finally(() => setLoading(false))
  }

  // Polling Effect
  useEffect(() => {
    if (!polling) return
    const interval = setInterval(() => {
        load()
    }, 5000)
    return () => clearInterval(interval)
  }, [polling, alertType, category, vendor, department])

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

  const handleAdjustSensitivity = async () => {
    if (!contextSummary || !outOfScopeStats.total) return
    setAutoLoading(true)
    setAutoMessage(null)
    try {
      const res = await apiFetch('/ai/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: 'scope_out_of_range_alerts',
          action_type: 'adjust_sensitivity',
          params: {
            source: 'alerts_page',
            out_of_scope_ratio: outOfScopeRatio,
          },
        }),
      })
      const data = await res.json()
      setAutoMessage(data?.message || 'Automação executada com sucesso.')
    } catch (e) {
      setAutoMessage('Erro ao executar automação.')
    } finally {
      setAutoLoading(false)
    }
  }

  const exportData = (format: 'excel' | 'csv') => {
    const params = new URLSearchParams()
    if (alertType) params.set('alert_type', alertType)
    if (category) params.set('category', category)
    if (vendor) params.set('vendor', vendor)
    if (department) params.set('department', department)
    
    const endpoint = format === 'excel' ? '/alerts/export_excel/' : '/alerts/export_csv/'
    
    apiFetch(`${endpoint}?${params.toString()}`)
      .then(r => r.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `alerts_${new Date().getTime()}.${format === 'excel' ? 'xlsx' : 'csv'}`
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
    <div>
      <h2 className="text-lg font-medium mb-4">Alertas</h2>
      {contextSummary && (
        <div className="mb-4 bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs text-indigo-900 flex flex-wrap gap-x-4 gap-y-1">
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
      )}
      {contextSummary && outOfScopeStats.total > 0 && outOfScopeStats.outOfScope > 0 && (
        <div className="mb-3 space-y-1">
          <div className="text-xs text-gray-600">
            {Math.round((outOfScopeStats.outOfScope / outOfScopeStats.total) * 100)}% dos alertas exibidos estão fora dos domínios de auditoria configurados.
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full flex">
              <div
                className="bg-emerald-400"
                style={{ width: `${Math.max(0, Math.min(100, (outOfScopeStats.inScope / outOfScopeStats.total) * 100))}%` }}
              />
              <div
                className="bg-amber-400"
                style={{ width: `${Math.max(0, Math.min(100, (outOfScopeStats.outOfScope / outOfScopeStats.total) * 100))}%` }}
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
                Muitos alertas estão fora do escopo. Deseja automatizar um ajuste?
              </span>
              <button
                onClick={handleAdjustSensitivity}
                disabled={autoLoading}
                className="px-3 py-1 rounded-full text-[11px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {autoLoading ? 'Ajustando...' : 'Ajustar sensibilidade com IA'}
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
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input className="border p-2 rounded" placeholder="Tipo" value={alertType} onChange={e=>setAlertType(e.target.value)} />
        <input className="border p-2 rounded" placeholder="Categoria" value={category} onChange={e=>setCategory(e.target.value)} />
        <input className="border p-2 rounded" placeholder="Fornecedor" value={vendor} onChange={e=>setVendor(e.target.value)} />
        {department && (
             <div className="flex items-center gap-1 bg-blue-100 text-blue-800 px-3 py-2 rounded">
                 <span className="text-sm font-medium">Depto: {department}</span>
                 <button onClick={() => setDepartment('')} className="hover:text-blue-600"><X size={14}/></button>
             </div>
        )}
        <button className="px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700" onClick={load}>Filtrar</button>
        <button 
            className={`px-3 py-2 rounded text-white transition-colors flex items-center gap-2 ${polling ? 'bg-amber-600 hover:bg-amber-700' : 'bg-gray-600 hover:bg-gray-700'}`}
            onClick={() => setPolling(!polling)}
        >
            <span className={`w-2 h-2 rounded-full ${polling ? 'bg-white animate-pulse' : 'bg-gray-400'}`} />
            {polling ? 'Pausar Atualização' : 'Iniciar Tempo Real'}
        </button>
        <div className="relative">
            <button 
                className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 flex items-center gap-2" 
                onClick={() => setShowExportMenu(!showExportMenu)}
            >
                <Download size={16} />
                Exportar
            </button>
            
            <AnimatePresence>
                {showExportMenu && (
                    <motion.div 
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 10 }}
                        className="absolute left-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded shadow-xl border border-gray-100 dark:border-gray-700 z-50 overflow-hidden"
                    >
                        <button 
                            onClick={() => exportData('excel')}
                            className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 flex items-center gap-2 border-b border-gray-50 dark:border-gray-700"
                        >
                            <FileSpreadsheet size={16} className="text-green-600" />
                            Excel (.xlsx)
                        </button>
                        <button 
                            onClick={() => exportData('csv')}
                            className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 flex items-center gap-2"
                        >
                            <FileText size={16} className="text-blue-600" />
                            CSV (.csv)
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
        <div className="flex items-center space-x-2 ml-4 border-l pl-4">
            <input 
                type="checkbox" 
                id="polling" 
                checked={polling} 
                onChange={e => setPolling(e.target.checked)} 
                className="h-4 w-4 text-blue-600 rounded" 
            />
            <label htmlFor="polling" className="text-sm text-gray-700 select-none cursor-pointer">
                Tempo Real (5s)
            </label>
        </div>
      </div>
      {loading && <div className="text-sm text-gray-600">Carregando...</div>}
      <div className="mb-3 flex items-center space-x-2">
        <button className="px-3 py-2 bg-gray-200 rounded" onClick={()=>loadLink(prevUrl)} disabled={!prevUrl || loading}>Anterior</button>
        <button className="px-3 py-2 bg-gray-200 rounded" onClick={()=>loadLink(nextUrl)} disabled={!nextUrl || loading}>Próxima</button>
      </div>
      <div className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">Transação</th>
              <th className="px-3 py-2 text-left">Tipo</th>
              <th className="px-3 py-2 text-left">Materialidade</th>
              <th className="px-3 py-2 text-left">Risco</th>
              <th className="px-3 py-2 text-left">Severidade</th>
              <th className="px-3 py-2 text-left">Prazo</th>
              <th className="px-3 py-2 text-left">Categoria</th>
              <th className="px-3 py-2 text-left">Fornecedor</th>
              <th className="px-3 py-2 text-left">Data</th>
              <th className="px-3 py-2 text-left">Ações</th>
            </tr>
          </thead>
          <tbody>
            {items.map(it => {
              const outOfScope =
                contextSummary &&
                Array.isArray(contextSummary.audit_domains) &&
                contextSummary.audit_domains.length > 0 &&
                it.category &&
                !contextSummary.audit_domains.includes(it.category)

              return (
                <tr key={it.id} className="border-t">
                  <td className="px-3 py-2">{it.id}</td>
                  <td className="px-3 py-2">{it.transaction_id}</td>
                  <td className="px-3 py-2">{it.alert_type}</td>
                  <td className="px-3 py-2">{Number(it.materiality).toFixed(2)}</td>
                  <td className="px-3 py-2">{it.context_risk ?? ''}</td>
                  <td className="px-3 py-2">{it.context_severity ?? ''}</td>
                  <td className="px-3 py-2">{it.context_due_date ?? ''}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1">
                      <span>{it.category ?? ''}</span>
                      {outOfScope && (
                        <span className="inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                          Fora do contexto configurado
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">{it.vendor ?? ''}</td>
                  <td className="px-3 py-2">{it.timestamp}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center space-x-2">
                      <Link href={`/alerts/${it.id}`} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-sm hover:bg-blue-200">Detalhes</Link>
                      <select className="border p-1 text-sm" defaultValue="" onChange={async e=>{const v=e.target.value; if(!v)return; await apiFetch(`/alerts/${it.id}/status?status=${encodeURIComponent(v)}`, {method:'POST'}); load();}}>
                        <option value="">Status</option>
                        <option value="triage">Triage</option>
                        <option value="in_progress">In Progress</option>
                        <option value="awaiting_evidence">Aguardando Evidência</option>
                        <option value="resolved">Resolvido</option>
                        <option value="closed">Fechado</option>
                      </select>
                      <input className="border p-1 text-sm" placeholder="Assign" onKeyDown={async e=>{if(e.key==='Enter'){const v=(e.target as HTMLInputElement).value; if(!v)return; await apiFetch(`/alerts/${it.id}/assign`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({assigned_to:v})}); (e.target as HTMLInputElement).value='';}}} />
                      <input className="border p-1 text-sm" placeholder="Comentar" onKeyDown={async e=>{if(e.key==='Enter'){const v=(e.target as HTMLInputElement).value; if(!v)return; await apiFetch(`/alerts/${it.id}/comment`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({comment:v})}); (e.target as HTMLInputElement).value='';}}} />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
