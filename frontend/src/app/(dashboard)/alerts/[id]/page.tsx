"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import Link from 'next/link'
import TransactionInspector from '@/components/dashboard/TransactionInspector'
import { AnimatePresence } from 'framer-motion'

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
  context_explanation?: string
  amount?: number
}

type Comment = {
  id: number
  alert_id: number
  user_id?: string
  comment: string
  created_at: string
  evidence_url?: string
}

export default function AlertDetailPage({ params }: { params: { id: string } }) {
  useRequireToken()
  const [alert, setAlert] = useState<Alert | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [rca, setRca] = useState<any>(null)
  const [loadingRca, setLoadingRca] = useState(false)
  const [loading, setLoading] = useState(false)
  const [newComment, setNewComment] = useState('')
  const [evidenceUrl, setEvidenceUrl] = useState('')
  const [showInspector, setShowInspector] = useState(false)
  const [contextSummary, setContextSummary] = useState<any | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([
      apiFetch(`/alerts/${params.id}`).then(r => r.json()),
      apiFetch(`/alerts/${params.id}/comments`).then(r => r.json())
    ]).then(([a, c]) => {
      setAlert(a)
      setComments(Array.isArray(c) ? c : [])
    }).catch(e => console.error(e)).finally(() => setLoading(false))
  }

  const runRca = async () => {
    setLoadingRca(true)
    try {
      const res = await apiFetch(`/ai/rca/${params.id}`)
      const data = await res.json()
      setRca(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingRca(false)
    }
  }

  const postComment = async () => {
    if (!newComment) return
    await apiFetch(`/alerts/${params.id}/comment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: newComment, evidence_url: evidenceUrl })
    })
    setNewComment('')
    setEvidenceUrl('')
    load()
  }

  const updateStatus = async (status: string) => {
    await apiFetch(`/alerts/${params.id}/status?status=${status}`, { method: 'POST' })
    load()
  }

  useEffect(() => { load() }, [params.id])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  if (loading && !alert) return <div>Carregando...</div>
  if (!alert) return <div>Alerta não encontrado</div>

  const outOfScope =
    contextSummary &&
    Array.isArray(contextSummary.audit_domains) &&
    contextSummary.audit_domains.length > 0 &&
    alert.category &&
    !contextSummary.audit_domains.includes(alert.category)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-medium">Alerta #{alert.id}</h2>
        <Link href="/alerts" className="text-blue-600 hover:underline">Voltar</Link>
      </div>

      {contextSummary && (
        <div className="space-y-2">
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs text-indigo-900 flex flex-wrap gap-x-4 gap-y-1">
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
          {outOfScope && (
            <div className="inline-flex items-center px-3 py-1 rounded-full text-[11px] font-medium bg-amber-50 border border-amber-200 text-amber-800">
              Categoria deste alerta não está entre os domínios ativos
            </div>
          )}
        </div>
      )}

      <div className="bg-white p-4 shadow rounded grid grid-cols-2 gap-4">
        <div>
          <div className="text-sm text-gray-500">Tipo</div>
          <div className="font-medium">{alert.alert_type}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Severidade</div>
          <div className="font-medium">{alert.context_severity}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Risco Calculado</div>
          <div className="font-medium">{alert.context_risk}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Materialidade</div>
          <div className="font-medium">{alert.materiality}</div>
        </div>
        <div className="col-span-2">
          <div className="text-sm text-gray-500">Explicação</div>
          <div className="font-medium">{alert.context_explanation}</div>
        </div>
         <div>
          <div className="text-sm text-gray-500">Data</div>
          <div className="font-medium">{new Date(alert.timestamp).toLocaleString()}</div>
        </div>
      </div>

      <div className="bg-white p-4 shadow rounded">
        <h3 className="text-lg font-medium mb-3">Ações</h3>
        <div className="flex space-x-2">
            <button onClick={()=>updateStatus('in_progress')} className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200">Iniciar Análise</button>
            <button onClick={()=>updateStatus('awaiting_evidence')} className="px-3 py-1 bg-orange-100 text-orange-800 rounded hover:bg-orange-200">Pedir Evidência</button>
            <button onClick={()=>updateStatus('resolved')} className="px-3 py-1 bg-green-100 text-green-800 rounded hover:bg-green-200">Resolver</button>
            <button onClick={()=>updateStatus('closed')} className="px-3 py-1 bg-gray-100 text-gray-800 rounded hover:bg-gray-200">Fechar</button>
            <button onClick={()=>setShowInspector(true)} className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded hover:bg-indigo-200 flex items-center gap-1">
              <span>🔍</span> Inspetor IA
            </button>
        </div>
      </div>

      {/* AI Root Cause Analysis Section */}
      <div className="bg-gradient-to-br from-indigo-50 to-purple-50 p-6 shadow rounded border border-indigo-100">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-2xl">🧠</span>
            <h3 className="text-lg font-semibold text-indigo-900">Análise de Causa Raiz (IA)</h3>
          </div>
          {!rca && (
            <button 
              onClick={runRca} 
              disabled={loadingRca}
              className="px-4 py-2 bg-indigo-600 text-white rounded shadow hover:bg-indigo-700 disabled:opacity-50 flex items-center space-x-2"
            >
              {loadingRca ? (
                <>
                  <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Analisando...</span>
                </>
              ) : (
                <span>⚡ Executar Análise</span>
              )}
            </button>
          )}
        </div>

        {rca && (
          <div className="space-y-4 animate-fade-in">
            <div className="bg-white p-4 rounded-lg border border-indigo-100 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-semibold text-gray-800">Causa Provável Identificada</h4>
                <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-bold rounded-full">
                  {Math.round(rca.confidence * 100)}% Confiança
                </span>
              </div>
              <p className="text-gray-700 text-lg">{rca.root_cause}</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white p-4 rounded-lg border border-indigo-100 shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Fatores Contribuintes</h4>
                <ul className="list-disc pl-5 space-y-1 text-gray-600">
                  {rca.contributing_factors.map((factor: string, i: number) => (
                    <li key={i}>{factor}</li>
                  ))}
                </ul>
              </div>
              
              <div className="bg-white p-4 rounded-lg border border-indigo-100 shadow-sm">
                <h4 className="font-semibold text-gray-800 mb-2">Ação Recomendada</h4>
                <div className="flex items-start space-x-2 text-indigo-700 bg-indigo-50 p-3 rounded">
                  <span>💡</span>
                  <p>{rca.recommended_action}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white p-4 shadow rounded">
        <h3 className="text-lg font-medium mb-3">Histórico de Auditoria</h3>
        <div className="space-y-6 mb-6 relative pl-4 border-l-2 border-gray-200 ml-2">
          {comments.map(c => (
            <div key={c.id} className="relative pl-6">
              <div className="absolute -left-[29px] top-0 w-4 h-4 rounded-full bg-blue-500 border-2 border-white"></div>
              <div className="flex flex-col">
                 <span className="text-xs text-gray-500 font-mono">{new Date(c.created_at).toLocaleString()}</span>
                 <span className="text-sm font-semibold text-gray-700">{c.user_id || 'Sistema'}</span>
                 <div className="bg-gray-50 p-3 rounded mt-1 text-gray-800 text-sm border border-gray-100">
                    {c.comment}
                    {c.evidence_url && (
                        <div className="mt-2 pt-2 border-t border-gray-200">
                            <a href={c.evidence_url} target="_blank" className="flex items-center text-blue-600 hover:text-blue-800 text-xs font-medium">
                                📎 Ver Evidência Anexada
                            </a>
                        </div>
                    )}
                 </div>
              </div>
            </div>
          ))}
          {comments.length === 0 && <div className="text-gray-500 italic pl-6">Nenhum registro no histórico.</div>}
        </div>
        
        <div className="border-t pt-4">
            <h4 className="text-sm font-medium mb-2 text-gray-700">Adicionar Nota ou Evidência</h4>
            <div className="space-y-2">
            <textarea 
                className="w-full border p-2 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" 
                placeholder="Descreva a ação tomada ou observação..." 
                rows={3}
                value={newComment}
                onChange={e => setNewComment(e.target.value)}
            />
            <div className="flex space-x-2">
                <input 
                    className="flex-1 border p-2 rounded text-sm" 
                    placeholder="URL da evidência (opcional)" 
                    value={evidenceUrl}
                    onChange={e => setEvidenceUrl(e.target.value)}
                />
                <button 
                    className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium"
                    onClick={postComment}
                    disabled={!newComment}
                >
                    Registrar no Histórico
                </button>
            </div>
            </div>
        </div>
      </div>
      
      <AnimatePresence>
        {showInspector && (
          <TransactionInspector 
            alertId={alert ? alert.id : null}
            transactionId={alert && alert.transaction_id ? alert.transaction_id : null}
            onClose={() => setShowInspector(false)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
