"use client"

import { useEffect, useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { X, Search, AlertTriangle, CheckCircle, Sparkles, Share2, Briefcase, Send, User, FileText, Printer, Loader2, PlusCircle, Globe, Shield } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

type Props = {
  transactionId: string | null
  alertId?: number | null
  onClose: () => void
}

type RCAData = {
  root_cause: string
  confidence: number
  contributing_factors: string[]
  recommended_action: string
  ai_summary?: string
  ai_context?: {
    user_trust_score: number
    persona: string
    adjusted_risk_score: number
  }
  xai_explanation?: {
    model_version: string
    timestamp: string
    risk_score: number
    feature_weights: {
        layer_1_personal: string[]
        layer_2_corporate: string[]
        layer_3_global: string[]
    }
    context_snapshot: any
  }
}

type GraphData = {
  nodes: { id: string, type: string, val: number, label: string }[]
  links: { source: string, target: string }[]
}

type CaseData = {
  id: number
  title: string
  status: string
  priority: string
  comments: { id: number, user_id: string, comment: string, created_at: string }[]
  attachments: { id: number, file_name: string, file_url: string, uploaded_by: string, uploaded_at: string }[]
}

export default function TransactionInspector({ transactionId, alertId, onClose }: Props) {
  const [tab, setTab] = useState<'insights' | 'network' | 'documents' | 'case'>('insights')
  const [data, setData] = useState<RCAData | null>(null)
  const [loading, setLoading] = useState(false)
  
  // Lifted state for Agent Result to share between Insights and Case views
  const [agentResult, setAgentResult] = useState<any>(null);
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [transactionMeta, setTransactionMeta] = useState<any | null>(null)

  useEffect(() => {
    if (!alertId && !transactionId) return;
    setTab('insights') // Reset tab on new selection
    setAgentResult(null) // Reset agent result
    const targetId = alertId || transactionId;
    setLoading(true)
    apiFetch(`/ai/rca/${targetId}`)
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [transactionId, alertId])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  useEffect(() => {
    if (!transactionId) return
    apiFetch(`/transactions/${transactionId}`)
      .then(r => r.json())
      .then(setTransactionMeta)
      .catch(() => setTransactionMeta(null))
  }, [transactionId])

  const handleCreateCase = () => {
    if (!transactionId && !alertId) return
    const id = transactionId || (alertId ? `ALERT-${alertId}` : '')
    // Navigate to cases page with create modal open and prefilled data
    router.push(`/cases?create=true&transaction_id=${id}&title=Investigação: ${id}`)
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { 
      opacity: 1,
      transition: { 
        staggerChildren: 0.1,
        delayChildren: 0.2
      }
    }
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 }
  }

  const outOfScope =
    contextSummary &&
    Array.isArray(contextSummary.audit_domains) &&
    contextSummary.audit_domains.length > 0 &&
    transactionMeta?.category &&
    !contextSummary.audit_domains.includes(transactionMeta.category)

  return (
    <AnimatePresence>
      <motion.div 
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="fixed inset-y-0 right-0 w-[600px] bg-white dark:bg-slate-900 shadow-2xl border-l border-slate-200 dark:border-slate-800 z-50 overflow-y-auto flex flex-col"
      >
        {/* Header */}
        <div className="p-6 border-b border-slate-100 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
                <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-white">
                    <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                        <Search className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    Auditor AI
                </h2>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                   ID: {transactionId || alertId}
                </p>
            </motion.div>
            <div className="flex items-center gap-2">
                <button 
                    onClick={handleCreateCase}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition-colors shadow-sm"
                >
                    <PlusCircle className="w-3.5 h-3.5" />
                    Criar Caso
                </button>
                <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors">
                    <X className="h-5 w-5 text-slate-500" />
                </button>
            </div>
          </div>

          {contextSummary && (
            <div className="mt-3 bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-[11px] text-indigo-900 flex flex-col gap-2">
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
              {Array.isArray(contextSummary.audit_domains) &&
                contextSummary.audit_domains.length > 0 &&
                transactionMeta?.category && (
                  <span
                    className={`inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${
                      outOfScope ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
                    }`}
                  >
                    {outOfScope
                      ? 'Categoria da transação fora dos domínios ativos'
                      : 'Categoria da transação dentro dos domínios ativos'}
                  </span>
                )}
            </div>
          )}

          {/* Tabs */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="flex gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg"
          >
            {[
              { id: 'insights', icon: Sparkles, label: 'Insights' },
              { id: 'network', icon: Share2, label: 'Grafo' },
              { id: 'documents', icon: FileText, label: 'Docs' },
              { id: 'case', icon: Briefcase, label: 'Caso' }
            ].map((t) => (
                <button 
                  key={t.id}
                  onClick={() => setTab(t.id as any)}
                  className={`flex-1 py-2 text-sm font-medium rounded-md flex items-center justify-center gap-2 transition-all duration-200 ${
                    tab === t.id 
                    ? 'bg-white dark:bg-slate-700 shadow-sm text-indigo-600 dark:text-indigo-400 scale-105' 
                    : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  <t.icon className="w-4 h-4" />
                  {t.label}
                </button>
            ))}
          </motion.div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50 dark:bg-slate-900/50">
          {loading && tab === 'insights' ? (
             <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                <p className="text-sm text-gray-500 animate-pulse">Analisando contexto...</p>
            </div>
          ) : (
            <motion.div
              key={tab}
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-6"
            >
              {tab === 'insights' && (
                <InsightsView 
                  data={data} 
                  transactionId={transactionId} 
                  alertId={alertId} 
                  agentResult={agentResult}
                  setAgentResult={setAgentResult}
                />
              )}
              {tab === 'network' && <NetworkView transactionId={transactionId || (alertId ? String(alertId) : null)} />}
              {tab === 'documents' && <DocumentsView transactionId={transactionId || (alertId ? String(alertId) : null)} />}
              {tab === 'case' && (
                <CaseView 
                  transactionId={transactionId || (alertId ? String(alertId) : null)} 
                  agentResult={agentResult}
                />
              )}
            </motion.div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

function InsightsView({ 
  data, 
  transactionId, 
  alertId,
  agentResult,
  setAgentResult
}: { 
  data: RCAData | null, 
  transactionId: string | null, 
  alertId?: number | null,
  agentResult: any,
  setAgentResult: (res: any) => void
}) {
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [showModelDetails, setShowModelDetails] = useState(false)
  const [news, setNews] = useState<any>(null)
  const [regulation, setRegulation] = useState<any>(null)
  
  // Agent State
  const [agentLoading, setAgentLoading] = useState(false);
  const [showWorkPaper, setShowWorkPaper] = useState(false);

  useEffect(() => {
    if (transactionId) {
       apiFetch(`/transactions/${transactionId}`).then(r => r.json()).then(tx => {
         if (tx.vendor) {
           apiFetch('/ai/analyze_news', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ vendor: tx.vendor })
           }).then(r => r.json()).then(setNews).catch(console.error)
         }
         
         const text = `${tx.vendor || ''} ${tx.description || ''} ${tx.category || ''}`
         apiFetch('/ai/analyze_regulation', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ text, country: 'BR' })
         }).then(r => r.json()).then(setRegulation).catch(console.error)
      }).catch(console.error)
    }
  }, [transactionId])

  const sendFeedback = (type: 'accurate' | 'inaccurate') => {
      apiFetch('/ai/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
              transaction_id: transactionId,
              feedback_type: type,
              comment: type === 'inaccurate' ? 'User flagged as safe' : 'User confirmed risk'
          })
      }).then(() => setFeedbackSent(true))
  }

  const runAgentInvestigation = () => {
    if (!transactionId) return;
    setAgentLoading(true);
    apiFetch('/ai/agent-investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_id: transactionId })
    })
        .then(r => r.json())
        .then(setAgentResult)
        .catch(console.error)
        .finally(() => setAgentLoading(false));
  };

  if (!data) return <div className="text-center text-gray-500">Nenhum dado disponível.</div>

  return (
    <div className="space-y-6">
        {/* Confidence Score */}
        <div className="flex items-center justify-center p-6 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl">
            <div className="text-center">
                <div className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
                    {(data.confidence * 100).toFixed(0)}%
                </div>
                <div className="text-xs font-medium uppercase tracking-wider text-indigo-400">Risco Calculado</div>
            </div>
        </div>

        {/* Agent Investigation Button */}
        <div className="flex flex-col gap-4">
            <div className="flex justify-center">
                <button 
                    onClick={runAgentInvestigation}
                    disabled={agentLoading}
                    className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 text-sm font-medium disabled:opacity-50"
                >
                    {agentLoading ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Agente Autônomo Investigando...
                        </>
                    ) : (
                        <>
                            <Sparkles className="w-4 h-4" />
                            Iniciar Investigação Profunda (Agente)
                        </>
                    )}
                </button>
            </div>

            {/* Agent Result Display */}
            {agentResult && (
                <motion.div 
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="p-4 bg-slate-900 text-slate-200 rounded-lg border border-slate-700 font-mono text-xs shadow-inner"
                >
                    <h4 className="font-bold text-indigo-400 mb-2 border-b border-slate-700 pb-2 flex justify-between">
                        <span>Relatório do Agente</span>
                        <span className="text-slate-500">{new Date().toLocaleTimeString()}</span>
                    </h4>
                    <div className="space-y-1 mb-3">
                        <div className="flex justify-between">
                            <span>Decisão Final:</span>
                            <span className={`font-bold ${agentResult.decision.includes('Reject') || agentResult.decision.includes('Freeze') ? 'text-red-400' : 'text-green-400'}`}>
                                {agentResult.decision}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span>Status:</span>
                            <span>{agentResult.status}</span>
                        </div>
                        <div className="flex justify-between">
                            <span>Risco Ajustado:</span>
                            <span>{agentResult.risk_score.toFixed(2)}</span>
                        </div>
                    </div>
                    <div className="space-y-1 max-h-40 overflow-y-auto custom-scrollbar">
                        <div className="text-slate-500 mb-1 font-semibold">Logs de Execução:</div>
                        {agentResult.logs.map((log: string, i: number) => (
                            <div key={i} className="pl-2 border-l-2 border-slate-700 text-slate-300 py-0.5">
                                {log}
                            </div>
                        ))}
                    </div>

                    {/* Work Paper Action */}
                    {agentResult.work_paper && (
                        <div className="mt-3 pt-3 border-t border-slate-700">
                            <button 
                                onClick={() => setShowWorkPaper(!showWorkPaper)}
                                className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-indigo-400 text-xs font-bold rounded flex items-center justify-center gap-2 transition-colors"
                            >
                                <FileText className="w-3 h-3" />
                                {showWorkPaper ? 'Ocultar Papel de Trabalho' : 'Visualizar Papel de Trabalho (NBC TA)'}
                            </button>
                            
                            {showWorkPaper && (
                                <motion.div 
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="mt-3 p-3 bg-white text-slate-800 rounded border border-slate-300 font-sans text-sm whitespace-pre-wrap shadow-lg"
                                >
                                    <div className="flex justify-between items-center mb-2 pb-2 border-b border-gray-200">
                                        <h5 className="font-bold text-gray-900">Rascunho do Papel de Trabalho</h5>
                                        <button className="text-indigo-600 hover:underline text-xs flex items-center gap-1">
                                            <Printer className="w-3 h-3" /> Imprimir
                                        </button>
                                    </div>
                                    {agentResult.work_paper}
                                </motion.div>
                            )}
                        </div>
                    )}
                </motion.div>
            )}
        </div>

        {/* AI Context (User Adaptation) */}
        {data.ai_context && (
            <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-100 dark:border-purple-800">
                <h3 className="text-xs font-bold uppercase text-purple-600 dark:text-purple-400 mb-3 flex items-center gap-2">
                    <Sparkles className="w-3 h-3" />
                    Adaptação ao Perfil
                </h3>
                <div className="space-y-2 text-sm">
                    <div className="flex justify-between items-center">
                        <span className="text-gray-500 dark:text-gray-400">Persona:</span>
                        <span className="font-medium text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 px-2 py-0.5 rounded shadow-sm">
                            {data.ai_context.persona}
                        </span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-gray-500 dark:text-gray-400">Confiança no Usuário:</span>
                        <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                <div 
                                    className="h-full bg-purple-500" 
                                    style={{ width: `${data.ai_context.user_trust_score * 100}%` }}
                                />
                            </div>
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                                {(data.ai_context.user_trust_score * 100).toFixed(0)}%
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        )}

        {/* AI Summary */}
        {data.ai_summary && (
            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700">
                <p className="text-sm text-gray-600 dark:text-gray-300 italic">
                    "{data.ai_summary}"
                </p>
            </div>
        )}

        {/* Root Cause (Summary) */}
        <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-orange-500" />
                Padrão Principal
            </h3>
            <div className="p-3 bg-orange-50 dark:bg-orange-900/10 border border-orange-100 dark:border-orange-900/30 rounded-lg text-sm text-gray-800 dark:text-gray-200">
                {data.root_cause}
            </div>
        </div>

        {/* 3-Layer Risk Analysis */}
        {data.contributing_factors && data.contributing_factors.length > 0 && (
            <div className="space-y-4 pt-4 border-t border-gray-100 dark:border-gray-800">
                <h3 className="text-sm font-bold uppercase tracking-wider text-gray-500 mb-3">Análise de Risco em 3 Camadas</h3>
                
                {/* Layer 1: Personal */}
                {data.contributing_factors.filter(f => f.includes('[Personal]')).length > 0 && (
                    <div className="p-3 bg-purple-50 dark:bg-purple-900/10 border border-purple-100 dark:border-purple-900/30 rounded-lg">
                        <h4 className="text-xs font-bold text-purple-700 dark:text-purple-400 uppercase mb-2 flex items-center gap-2">
                            <User className="w-3 h-3" /> Camada 1: Pessoal (Persona)
                        </h4>
                        <ul className="space-y-1">
                            {data.contributing_factors.filter(f => f.includes('[Personal]')).map((factor, i) => (
                                <li key={i} className="text-sm text-gray-700 dark:text-gray-300 flex items-start gap-2">
                                    <span className="text-purple-400 mt-1">•</span>
                                    {factor.replace('[Personal]', '').trim()}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Layer 2: Corporate */}
                {data.contributing_factors.filter(f => f.includes('[Corporate]')).length > 0 && (
                    <div className="p-3 bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30 rounded-lg">
                        <h4 className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase mb-2 flex items-center gap-2">
                            <Briefcase className="w-3 h-3" /> Camada 2: Corporativo (Cérebro)
                        </h4>
                        <ul className="space-y-1">
                            {data.contributing_factors.filter(f => f.includes('[Corporate]')).map((factor, i) => (
                                <li key={i} className="text-sm text-gray-700 dark:text-gray-300 flex items-start gap-2">
                                    <span className="text-blue-400 mt-1">•</span>
                                    {factor.replace('[Corporate]', '').trim()}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Layer 3: Global */}
                {data.contributing_factors.filter(f => f.includes('[Global]')).length > 0 && (
                    <div className="p-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg">
                        <h4 className="text-xs font-bold text-slate-700 dark:text-slate-400 uppercase mb-2 flex items-center gap-2">
                            <Globe className="w-3 h-3" /> Camada 3: Global (Universal)
                        </h4>
                        <ul className="space-y-1">
                            {data.contributing_factors.filter(f => f.includes('[Global]')).map((factor, i) => (
                                <li key={i} className="text-sm text-gray-700 dark:text-gray-300 flex items-start gap-2">
                                    <span className="text-slate-400 mt-1">•</span>
                                    {factor.replace('[Global]', '').trim()}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                 {/* Uncategorized Factors */}
                 {data.contributing_factors.filter(f => !f.includes('[Personal]') && !f.includes('[Corporate]') && !f.includes('[Global]')).length > 0 && (
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg">
                        <h4 className="text-xs font-bold text-gray-600 dark:text-gray-400 uppercase mb-2">Outros Fatores</h4>
                        <ul className="space-y-1">
                            {data.contributing_factors.filter(f => !f.includes('[Personal]') && !f.includes('[Corporate]') && !f.includes('[Global]')).map((factor, i) => (
                                <li key={i} className="text-sm text-gray-700 dark:text-gray-300 flex items-start gap-2">
                                    <span className="text-gray-400 mt-1">•</span>
                                    {factor}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        )}

        {/* Regulation Analysis */}
        {regulation && regulation.matches && regulation.matches.length > 0 && (
            <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-2">
                    <Shield className="h-4 w-4 text-blue-500" />
                    Conformidade Regulatória
                </h3>
                <div className="space-y-2">
                    {regulation.matches.map((m: any, i: number) => (
                        <div key={i} className="p-3 bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30 rounded-lg text-sm">
                            <div className="font-semibold text-blue-700 dark:text-blue-300">{m.regulation} - {m.alert_type}</div>
                            <div className="text-gray-600 dark:text-gray-400 text-xs mt-1">{m.description}</div>
                        </div>
                    ))}
                </div>
            </div>
        )}

        {/* News Monitoring */}
        {news && news.news && news.news.length > 0 && (
             <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-2">
                    <Globe className="h-4 w-4 text-green-500" />
                    Monitoramento de Mídia
                </h3>
                <div className="space-y-2">
                    {news.news.map((n: any, i: number) => (
                        <div key={i} className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm shadow-sm">
                            <div className="font-medium text-gray-900 dark:text-gray-100">{n.title}</div>
                            <div className="flex justify-between mt-1 text-xs text-gray-500">
                                <span>{n.source}</span>
                                <span>{n.date}</span>
                            </div>
                            {n.sentiment === 'negative' && (
                                <div className="mt-1 text-xs text-red-500 font-medium flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" /> Sentimento Negativo Detectado
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        )}

        {/* Model Details (XAI) */}
        {data.xai_explanation ? (
            <div className="border-t border-gray-100 dark:border-gray-800 pt-4">
                <button 
                    onClick={() => setShowModelDetails(!showModelDetails)}
                    className="text-xs font-medium text-gray-500 hover:text-indigo-600 flex items-center gap-1 mb-2"
                >
                    {showModelDetails ? '▼ Ocultar Detalhes do Modelo' : '▶ Ver Detalhes do Modelo (XAI)'}
                </button>
                
                <AnimatePresence>
                    {showModelDetails && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                        >
                            <div className="bg-gray-50 dark:bg-gray-900 rounded p-3 text-xs space-y-3 border border-gray-100 dark:border-gray-800 font-mono">
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Versão do Modelo:</span>
                                    <span className="font-bold text-indigo-600">{data.xai_explanation.model_version}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Timestamp:</span>
                                    <span>{new Date(data.xai_explanation.timestamp).toLocaleString()}</span>
                                </div>
                                
                                <div className="space-y-4 pt-2 border-t border-gray-200 dark:border-gray-700">
                                    <h4 className="font-semibold text-gray-700 dark:text-gray-300">Análise de Risco em 3 Camadas (XAI)</h4>
                                    
                                    {/* Personal */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-xs font-bold text-purple-600 uppercase tracking-wider flex items-center gap-1.5">
                                                <span className="w-2 h-2 rounded-full bg-purple-500 shadow-sm shadow-purple-500/50"></span>
                                                Camada 1: Pessoal
                                            </span>
                                            <span className="text-[10px] font-mono bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-100">
                                                {data.xai_explanation.feature_weights.layer_1_personal.length} Fatores
                                            </span>
                                        </div>
                                        <div className="space-y-1.5 bg-purple-50/50 p-2 rounded border border-purple-100/50">
                                            {data.xai_explanation.feature_weights.layer_1_personal.length > 0 ? (
                                                data.xai_explanation.feature_weights.layer_1_personal.map((f: string, i: number) => (
                                                    <div key={`p-${i}`} className="text-xs text-gray-700 flex gap-2">
                                                        <span className="text-purple-400 mt-0.5">•</span>
                                                        <span>{f.replace('[Personal]', '').trim()}</span>
                                                    </div>
                                                ))
                                            ) : (
                                                <div className="text-xs text-gray-400 italic pl-1">Nenhum risco pessoal detectado.</div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Corporate */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-xs font-bold text-blue-600 uppercase tracking-wider flex items-center gap-1.5">
                                                <span className="w-2 h-2 rounded-full bg-blue-500 shadow-sm shadow-blue-500/50"></span>
                                                Camada 2: Corporativa
                                            </span>
                                            <span className="text-[10px] font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-100">
                                                {data.xai_explanation.feature_weights.layer_2_corporate.length} Fatores
                                            </span>
                                        </div>
                                        <div className="space-y-1.5 bg-blue-50/50 p-2 rounded border border-blue-100/50">
                                            {data.xai_explanation.feature_weights.layer_2_corporate.length > 0 ? (
                                                data.xai_explanation.feature_weights.layer_2_corporate.map((f: string, i: number) => (
                                                    <div key={`c-${i}`} className="text-xs text-gray-700 flex gap-2">
                                                        <span className="text-blue-400 mt-0.5">•</span>
                                                        <span>{f.replace('[Corporate]', '').trim()}</span>
                                                    </div>
                                                ))
                                            ) : (
                                                <div className="text-xs text-gray-400 italic pl-1">Nenhum risco corporativo detectado.</div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Global */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                                                <span className="w-2 h-2 rounded-full bg-slate-500 shadow-sm shadow-slate-500/50"></span>
                                                Camada 3: Global
                                            </span>
                                            <span className="text-[10px] font-mono bg-slate-50 text-slate-700 px-2 py-0.5 rounded border border-slate-100">
                                                {data.xai_explanation.feature_weights.layer_3_global.length} Fatores
                                            </span>
                                        </div>
                                        <div className="space-y-1.5 bg-slate-50/50 p-2 rounded border border-slate-100/50">
                                            {data.xai_explanation.feature_weights.layer_3_global.length > 0 ? (
                                                data.xai_explanation.feature_weights.layer_3_global.map((f: string, i: number) => (
                                                    <div key={`g-${i}`} className="text-xs text-gray-700 flex gap-2">
                                                        <span className="text-slate-400 mt-0.5">•</span>
                                                        <span>{f.replace('[Global]', '').trim()}</span>
                                                    </div>
                                                ))
                                            ) : (
                                                <div className="text-xs text-gray-400 italic pl-1">Nenhum risco global detectado.</div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        ) : (
        <div className="border-t border-gray-100 dark:border-gray-800 pt-4">
            <button 
                onClick={() => setShowModelDetails(!showModelDetails)}
                className="text-xs font-medium text-gray-500 hover:text-indigo-600 flex items-center gap-1 mb-2"
            >
                {showModelDetails ? '▼ Ocultar Detalhes do Modelo' : '▶ Ver Detalhes do Modelo (XAI)'}
            </button>
            
            <AnimatePresence>
                {showModelDetails && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                    >
                        <div className="bg-gray-50 dark:bg-gray-900 rounded p-3 text-xs space-y-2 border border-gray-100 dark:border-gray-800">
                            <h4 className="font-semibold text-gray-700 dark:text-gray-300">Pesos dos Fatores (Feature Weights)</h4>
                            {[
                                { name: 'Reputação do Fornecedor', weight: 0.35, risk: 'High' },
                                { name: 'Desvio de Valor', weight: 0.25, risk: 'Medium' },
                                { name: 'Tempo de Aprovação', weight: 0.15, risk: 'Low' },
                                { name: 'Histórico do Usuário', weight: 0.10, risk: 'Low' },
                                { name: 'Geo Incompatibilidade', weight: 0.15, risk: 'High' }
                            ].map((fw, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <span className="text-gray-600 dark:text-gray-400">{fw.name}</span>
                                    <div className="flex items-center gap-2">
                                        <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div 
                                                className={`h-full ${fw.risk === 'High' ? 'bg-red-500' : fw.risk === 'Medium' ? 'bg-yellow-500' : 'bg-green-500'}`} 
                                                style={{ width: `${fw.weight * 100}%` }} 
                                            />
                                        </div>
                                        <span className="font-mono text-gray-900 dark:text-gray-100">{(fw.weight * 100).toFixed(0)}%</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
        )}

        <button 
            onClick={() => {
                window.location.href = `/assistant?query=Investigar transação ${transactionId || alertId}`;
            }}
            className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-colors"
        >
            Investigar com IA
        </button>

        {/* Feedback Loop UI */}
        {!feedbackSent ? (
            <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800">
                <p className="text-xs text-center text-gray-500 mb-3">A análise da IA foi útil?</p>
                <div className="flex gap-2">
                    <button 
                        onClick={() => sendFeedback('accurate')}
                        className="flex-1 py-2 bg-gray-100 hover:bg-green-100 text-gray-600 hover:text-green-700 rounded-lg text-sm font-medium transition-colors"
                    >
                        👍 Sim
                    </button>
                    <button 
                        onClick={() => sendFeedback('inaccurate')}
                        className="flex-1 py-2 bg-gray-100 hover:bg-red-100 text-gray-600 hover:text-red-700 rounded-lg text-sm font-medium transition-colors"
                    >
                        👎 Não
                    </button>
                </div>
            </div>
        ) : (
            <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800 text-center">
                <p className="text-sm text-green-600 font-medium flex items-center justify-center gap-2">
                    <CheckCircle className="h-4 w-4" />
                    Feedback registrado.
                </p>
            </div>
        )}
    </div>
  )
}

function NetworkView({ transactionId }: { transactionId: string | null }) {
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [positions, setPositions] = useState<Record<string, {x: number, y: number}>>({})
  const [loading, setLoading] = useState(false)
  const [collusionRisk, setCollusionRisk] = useState<{detected: boolean, message: string} | null>(null)
  const [minRisk, setMinRisk] = useState(0)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!transactionId) return;
    setLoading(true)
    apiFetch(`/context/graph?txn=${transactionId}`)
      .then(r => r.json())
      .then((data: GraphData & { collusion_risk?: any }) => {
          const enrichedGraph = data
          // Ensure risk property exists for transactions
          enrichedGraph.nodes = enrichedGraph.nodes.map(n => ({
              ...n,
              risk: n.type === 'transaction' && typeof (n as any).risk === 'number' ? (n as any).risk : 0
          }))
          setGraph(enrichedGraph)
          
          if (data.collusion_risk && data.collusion_risk.detected) {
              setCollusionRisk(data.collusion_risk)
          } else {
              analyzeCollusion(enrichedGraph)
          }

          initializeLayout(enrichedGraph)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [transactionId])

  const initializeLayout = (data: GraphData) => {
      const width = 400;
      const height = 300;
      const centerX = width / 2;
      const centerY = height / 2;
      const newPositions: Record<string, {x: number, y: number}> = {};
      
      const vendor = data.nodes.find(n => n.type === 'vendor');
      if (vendor) newPositions[vendor.id] = { x: centerX, y: centerY };

      const txs = data.nodes.filter(n => n.type === 'transaction');
      txs.forEach((node, i) => {
        const angle = (i / txs.length) * 2 * Math.PI;
        const radius = 80;
        newPositions[node.id] = {
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius
        };
      });

      const users = data.nodes.filter(n => n.type === 'user');
      users.forEach((user, i) => {
          const linkedTxs = data.links
            .filter(l => l.source === user.id || l.target === user.id)
            .map(l => l.source === user.id ? l.target : l.source)
            .filter(id => newPositions[id]); 
          
          if (linkedTxs.length > 0) {
              const firstTxPos = newPositions[linkedTxs[0]];
              const dx = firstTxPos.x - centerX;
              const dy = firstTxPos.y - centerY;
              const angle = Math.atan2(dy, dx);
              const radius = 140;
              newPositions[user.id] = {
                  x: centerX + Math.cos(angle) * radius,
                  y: centerY + Math.sin(angle) * radius
              };
          } else {
               const angle = (i / users.length) * 2 * Math.PI;
               newPositions[user.id] = { x: centerX + Math.cos(angle) * 140, y: centerY + Math.sin(angle) * 140 };
          }
      });
      
      data.nodes.forEach(n => {
          if (!newPositions[n.id]) newPositions[n.id] = { x: centerX, y: centerY };
      });
      setPositions(newPositions)
  }

  const analyzeCollusion = (data: GraphData) => {
      // Logic: Check if one user dominates the transactions for this vendor
      const vendorNode = data.nodes.find(n => n.type === 'vendor')
      if (!vendorNode) return

      const txs = data.nodes.filter(n => n.type === 'transaction')
      const users = data.nodes.filter(n => n.type === 'user')
      
      // Map tx -> user
      const txUserMap = new Map<string, string>()
      data.links.forEach(l => {
          const sourceNode = data.nodes.find(n => n.id === l.source)
          const targetNode = data.nodes.find(n => n.id === l.target)
          
          if (sourceNode?.type === 'transaction' && targetNode?.type === 'user') {
              txUserMap.set(l.source, l.target)
          }
          if (sourceNode?.type === 'user' && targetNode?.type === 'transaction') {
              txUserMap.set(l.target, l.source)
          }
      })

      if (txs.length > 2 && users.length === 1) {
          setCollusionRisk({
              detected: true,
              message: `Alta Probabilidade de Conluio: O usuário ${users[0].label} é o único aprovador para este fornecedor em ${txs.length} transações recentes.`
          })
      } else {
          setCollusionRisk(null)
      }
  }

  const handleMouseDown = (e: React.MouseEvent, nodeId: string) => {
      e.preventDefault()
      setDraggingId(nodeId)
  }

  const handleMouseMove = (e: React.MouseEvent) => {
      if (!draggingId || !svgRef.current) return
      
      const svgRect = svgRef.current.getBoundingClientRect()
      const x = e.clientX - svgRect.left
      const y = e.clientY - svgRect.top
      
      setPositions(prev => ({
          ...prev,
          [draggingId]: { x, y }
      }))
  }

  const handleMouseUp = () => {
      setDraggingId(null)
  }

  if (loading) return <div className="text-center p-10 text-gray-500">Carregando grafo...</div>
  if (!graph || graph.nodes.length === 0) return <div className="text-center p-10 text-gray-500">Sem dados de rede.</div>

  // Filter nodes based on risk (only transactions usually have risk score)
  const filteredNodes = graph.nodes.filter(n => {
      if (n.type === 'transaction') return ((n as any).risk || 0) >= minRisk
      return true
  })
  
  // Filter links
  const filteredLinks = graph.links.filter(l => {
      const sourceExists = filteredNodes.find(n => n.id === l.source)
      const targetExists = filteredNodes.find(n => n.id === l.target)
      return sourceExists && targetExists
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between bg-white dark:bg-gray-900 p-3 rounded-lg border border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-4">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Filtro de Risco:</span>
              <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">0%</span>
                  <input 
                    type="range" 
                    min="0" 
                    max="1" 
                    step="0.1" 
                    value={minRisk}
                    onChange={(e) => setMinRisk(parseFloat(e.target.value))}
                    className="w-32 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700 accent-indigo-600"
                  />
                  <span className="text-xs text-gray-500">100%</span>
              </div>
              <span className="text-sm font-bold text-indigo-600">{(minRisk * 100).toFixed(0)}%+</span>
          </div>
          <div className="text-xs text-gray-500 flex items-center gap-2">
              <div className="group relative">
                  <span className="cursor-help text-indigo-500 font-bold border-b border-dashed border-indigo-400">?</span>
                  <div className="absolute right-0 bottom-full mb-2 w-48 p-2 bg-gray-800 text-white text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                      O sistema analisa conexões entre usuários e fornecedores para detectar padrões de aprovação exclusivos (Colusão).
                  </div>
              </div>
              Arraste os nós para organizar
          </div>
      </div>

      {collusionRisk && (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-4 shadow-sm"
          >
              <div className="p-2 bg-red-100 dark:bg-red-900/40 rounded-full">
                <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
              </div>
              <div className="flex-1">
                  <h4 className="text-sm font-bold text-red-700 dark:text-red-400">Padrão de Conluio Detectado</h4>
                  <p className="text-xs text-red-600 dark:text-red-300 mt-1 mb-3 leading-relaxed">{collusionRisk.message}</p>
                  
                  <div className="flex gap-2">
                    <button 
                        onClick={() => window.open(`/cases?create=true&title=Investigação de Conluio&description=${encodeURIComponent(collusionRisk.message)}`, '_blank')}
                        className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded-md transition-colors flex items-center gap-1 shadow-sm"
                    >
                        <ShieldAlert className="w-3 h-3" />
                        Abrir Caso de Fraude
                    </button>
                    <button 
                        onClick={() => alert("Notificação enviada ao Compliance Officer.")}
                        className="px-3 py-1.5 bg-white border border-red-200 text-red-700 hover:bg-red-50 text-xs font-medium rounded-md transition-colors"
                    >
                        Notificar Compliance
                    </button>
                  </div>
              </div>
          </motion.div>
      )}

      <div 
        className="bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-2 overflow-hidden relative"
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg 
            ref={svgRef}
            width="100%" 
            height="300" 
            viewBox="0 0 400 300"
            className="cursor-crosshair"
        >
          {/* Links */}
          {filteredLinks.map((link, i) => {
             const start = positions[link.source];
             const end = positions[link.target];
             if (!start || !end) return null;
             const isCollusionLink = collusionRisk && (
                 (graph.nodes.find(n => n.id === link.source)?.type === 'user' || graph.nodes.find(n => n.id === link.target)?.type === 'user')
             );
             return (
               <line 
                 key={i}
                 x1={start.x} y1={start.y} x2={end.x} y2={end.y} 
                 stroke={isCollusionLink ? "#F87171" : "#CBD5E1"} 
                 strokeWidth={isCollusionLink ? "2" : "1.5"}
                 strokeOpacity={isCollusionLink ? 1 : 0.6}
               />
             )
          })}
          {/* Nodes */}
          {filteredNodes.map((node) => {
             const pos = positions[node.id];
             if (!pos) return null;
             const isMain = node.type === 'transaction' && node.id === transactionId;
             const color = node.type === 'transaction' ? ((node as any).risk > 0.7 ? '#EF4444' : '#6366F1') : (node.type === 'vendor' ? '#EC4899' : '#10B981');
             
             return (
               <g 
                key={node.id} 
                transform={`translate(${pos.x},${pos.y})`}
                onMouseDown={(e) => handleMouseDown(e, node.id)}
                className="cursor-grab active:cursor-grabbing"
               >
                 {/* Shape Logic: Circle (Tx), Square (Vendor), Triangle (User) */}
                 {node.type === 'transaction' && (
                    <circle 
                        r={isMain ? 18 : 10} 
                        fill={color} 
                        stroke="#fff" 
                        strokeWidth="2"
                        className="drop-shadow-sm transition-colors"
                    />
                 )}
                 {node.type === 'vendor' && (
                     <rect
                        x={-14} y={-14}
                        width={28} height={28}
                        fill={color}
                        stroke="#fff"
                        strokeWidth="2"
                        rx={4}
                        className="drop-shadow-sm"
                     />
                 )}
                 {node.type === 'user' && (
                     <polygon
                        points="0,-15 13,10 -13,10"
                        fill={color}
                        stroke="#fff"
                        strokeWidth="2"
                        className="drop-shadow-sm"
                     />
                 )}

                 <text 
                   y={isMain ? 32 : 24} 
                   textAnchor="middle" 
                   fontSize="10" 
                   fontWeight={isMain ? "bold" : "normal"}
                   className="fill-gray-600 dark:fill-gray-300 pointer-events-none select-none"
                 >
                   {node.label}
                 </text>
               </g>
             )
          })}
        </svg>
      </div>
      <div className="text-xs text-gray-500 space-y-2">
        <div className="flex flex-wrap gap-x-4 gap-y-2">
            <span className="flex items-center gap-1 font-medium text-gray-700 dark:text-gray-300">Nós:</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-indigo-500"></div> Transação (●)</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-sm bg-pink-500"></div> Fornecedor (■)</span>
            <span className="flex items-center gap-1"><div className="w-0 h-0 border-l-[4px] border-r-[4px] border-b-[8px] border-transparent border-b-green-500"></div> Usuário (▲)</span>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-gray-200 dark:border-gray-800 pt-2">
            <span className="flex items-center gap-1 font-medium text-gray-700 dark:text-gray-300">Risco:</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-red-500"></div> Alto</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-yellow-400"></div> Médio</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-gray-300"></div> Baixo</span>
            <span className="flex items-center gap-1 ml-2 border-l pl-2 border-gray-300"><div className="w-4 h-0.5 bg-gray-400"></div> Espessura = Força</span>
        </div>
        {collusionRisk && <span className="text-xs font-bold text-red-500 animate-pulse block mt-1">● Alerta de Colusão Ativo</span>}
      </div>
    </div>
  )
}

function ReportModal({ data, onClose }: { data: any, onClose: () => void }) {
    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-white dark:bg-gray-900 w-full max-w-4xl max-h-[90vh] rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
                {/* Header */}
                <div className="p-6 border-b border-gray-200 dark:border-gray-800 flex justify-between items-start bg-gray-50 dark:bg-gray-950">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                                Relatório de Auditoria #{data.header.title}
                            </h2>
                            <span className="px-3 py-1 text-sm font-medium rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300">
                                {data.header.status}
                            </span>
                        </div>
                        <p className="text-sm text-gray-500">
                            Gerado em {data.metadata.generated_at} por {data.metadata.generated_by}
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <button 
                            onClick={() => window.print()}
                            className="p-2 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg transition-colors"
                            title="Imprimir"
                        >
                            <Printer className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                        </button>
                        <button 
                            onClick={onClose}
                            className="p-2 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-lg transition-colors group"
                        >
                            <X className="w-5 h-5 text-gray-500 group-hover:text-red-600" />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8 space-y-8 font-serif print:p-0">
                    {/* Executive Summary */}
                    <section>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 pb-2 mb-4 uppercase tracking-wider">
                            Resumo Executivo
                        </h3>
                        <p className="text-gray-700 dark:text-gray-300 leading-relaxed text-justify">
                            {data.executive_summary}
                        </p>
                    </section>

                    {/* Transaction Details */}
                    {data.transaction_details && (
                        <section>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 pb-2 mb-4 uppercase tracking-wider">
                                Detalhes da Transação
                            </h3>
                            <div className="grid grid-cols-2 gap-4 bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border border-gray-100 dark:border-gray-800">
                                <div>
                                    <span className="block text-xs font-semibold text-gray-500 uppercase">ID</span>
                                    <span className="text-gray-900 dark:text-gray-100 font-mono">{data.transaction_details.id}</span>
                                </div>
                                <div>
                                    <span className="block text-xs font-semibold text-gray-500 uppercase">Data</span>
                                    <span className="text-gray-900 dark:text-gray-100">{data.transaction_details.date}</span>
                                </div>
                                <div>
                                    <span className="block text-xs font-semibold text-gray-500 uppercase">Valor</span>
                                    <span className="text-gray-900 dark:text-gray-100 font-medium">
                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(data.transaction_details.amount)}
                                    </span>
                                </div>
                                <div>
                                    <span className="block text-xs font-semibold text-gray-500 uppercase">Fornecedor</span>
                                    <span className="text-gray-900 dark:text-gray-100">{data.transaction_details.vendor}</span>
                                </div>
                            </div>
                        </section>
                    )}

                    {/* Risk Analysis */}
                    <section>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 pb-2 mb-4 uppercase tracking-wider">
                            Análise de Risco AI
                        </h3>
                        <div className="flex gap-6 items-start">
                            <div className="bg-red-50 dark:bg-red-900/10 p-4 rounded-lg border border-red-100 dark:border-red-900/30 text-center min-w-[150px]">
                                <div className="text-3xl font-bold text-red-600 dark:text-red-400">
                                    {(data.risk_analysis.score * 100).toFixed(0)}%
                                </div>
                                <div className="text-xs font-semibold text-red-400 uppercase">Score de Risco</div>
                            </div>
                            <div className="flex-1 space-y-2">
                                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Fatores Contribuintes:</p>
                                <ul className="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300">
                                    {data.risk_analysis.factors.map((f: string, i: number) => (
                                        <li key={i}>{f}</li>
                                    ))}
                                </ul>
                                {data.risk_analysis.ai_notes?.persona && (
                                    <div className="mt-4 text-sm text-gray-500 bg-gray-50 dark:bg-gray-800 p-2 rounded">
                                        Nota: Análise adaptada para o perfil <strong>{data.risk_analysis.ai_notes.persona}</strong>.
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* XAI 3-Layer Breakdown for Report */}
                        {data.risk_analysis.xai_explanation && (
                            <div className="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
                                <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">Detalhamento por Camadas de Inteligência (XAI)</h4>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    {/* Personal Layer */}
                                    <div className="bg-purple-50 dark:bg-purple-900/10 p-3 rounded-lg border border-purple-100 dark:border-purple-900/30">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                                            <h5 className="text-xs font-bold text-purple-700 dark:text-purple-400 uppercase">Pessoal</h5>
                                        </div>
                                        {data.risk_analysis.xai_explanation.feature_weights?.layer_1_personal?.length > 0 ? (
                                            <ul className="space-y-1">
                                                {data.risk_analysis.xai_explanation.feature_weights.layer_1_personal.map((f: string, i: number) => (
                                                    <li key={i} className="text-xs text-gray-600 dark:text-gray-300 flex items-start gap-1">
                                                        <span className="text-purple-400">•</span>
                                                        {f.replace('[Personal]', '').trim()}
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : <span className="text-xs text-gray-400 italic">Sem fatores relevantes.</span>}
                                    </div>

                                    {/* Corporate Layer */}
                                    <div className="bg-blue-50 dark:bg-blue-900/10 p-3 rounded-lg border border-blue-100 dark:border-blue-900/30">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                                            <h5 className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase">Corporativo</h5>
                                        </div>
                                        {data.risk_analysis.xai_explanation.feature_weights?.layer_2_corporate?.length > 0 ? (
                                            <ul className="space-y-1">
                                                {data.risk_analysis.xai_explanation.feature_weights.layer_2_corporate.map((f: string, i: number) => (
                                                    <li key={i} className="text-xs text-gray-600 dark:text-gray-300 flex items-start gap-1">
                                                        <span className="text-blue-400">•</span>
                                                        {f.replace('[Corporate]', '').trim()}
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : <span className="text-xs text-gray-400 italic">Sem fatores relevantes.</span>}
                                    </div>

                                    {/* Global Layer */}
                                    <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="w-2 h-2 rounded-full bg-gray-500"></div>
                                            <h5 className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase">Global</h5>
                                        </div>
                                        {data.risk_analysis.xai_explanation.feature_weights?.layer_3_global?.length > 0 ? (
                                            <ul className="space-y-1">
                                                {data.risk_analysis.xai_explanation.feature_weights.layer_3_global.map((f: string, i: number) => (
                                                    <li key={i} className="text-xs text-gray-600 dark:text-gray-300 flex items-start gap-1">
                                                        <span className="text-gray-400">•</span>
                                                        {f.replace('[Global]', '').trim()}
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : <span className="text-xs text-gray-400 italic">Sem fatores relevantes.</span>}
                                    </div>
                                </div>
                            </div>
                        )}
                    </section>

                    {/* Investigation Log */}
                    {data.investigation_log.length > 0 && (
                        <section>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 pb-2 mb-4 uppercase tracking-wider">
                                Log de Investigação
                            </h3>
                            <div className="space-y-4 border-l-2 border-gray-200 dark:border-gray-700 pl-4 ml-2">
                                {data.investigation_log.map((log: any, i: number) => (
                                    <div key={i} className="relative">
                                        <div className="absolute -left-[21px] top-1.5 w-3 h-3 rounded-full bg-gray-300 dark:bg-gray-600 border-2 border-white dark:border-gray-900"></div>
                                        <div className="mb-1 flex items-center gap-2">
                                            <span className="font-semibold text-gray-900 dark:text-gray-100">{log.user}</span>
                                            <span className="text-xs text-gray-500">{log.date}</span>
                                        </div>
                                        <p className="text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                                            {log.content}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {/* Evidence */}
                    {data.evidence.length > 0 && (
                        <section>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-700 pb-2 mb-4 uppercase tracking-wider">
                                Evidências Anexadas
                            </h3>
                            <ul className="grid grid-cols-2 gap-3">
                                {data.evidence.map((ev: any, i: number) => (
                                    <li key={i} className="flex items-center gap-2 p-3 border border-gray-200 dark:border-gray-700 rounded-lg">
                                        <FileText className="w-5 h-5 text-gray-400" />
                                        <div className="overflow-hidden">
                                            <a href={ev.url} target="_blank" rel="noopener noreferrer" className="block text-sm font-medium text-indigo-600 hover:underline truncate">
                                                {ev.name}
                                            </a>
                                            <span className="text-xs text-gray-400">Enviado por {ev.uploaded_by}</span>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950 text-center text-xs text-gray-500">
                    Relatório gerado automaticamente pelo Sistema de Auditoria AI. Documento confidencial.
                </div>
            </motion.div>
        </div>
    )
}

function DocumentsView({ transactionId }: { transactionId: string | null }) {
    const [documents, setDocuments] = useState<any[]>([])
    const fileInputRef = useRef<HTMLInputElement>(null)

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            uploadAttachment(e.target.files[0])
        }
    }

    const uploadAttachment = async (file: File) => {
        const tempId = `temp-${Date.now()}`
        const newDoc = {
            id: tempId,
            name: file.name,
            status: 'uploading',
            type: file.name.split('.').pop()?.toUpperCase() || 'FILE'
        }
        setDocuments(prev => [...prev, newDoc])

        const formData = new FormData()
        formData.append('file', file)
        formData.append('title', file.name)
        formData.append('doc_type', 'PBC Support')
        if (transactionId) {
            formData.append('transaction_id', transactionId)
        }

        try {
            const res = await apiFetch('/upload/document', {
                method: 'POST',
                body: formData
            })
            const data = await res.json()
            if (data.id) {
                setDocuments(prev => prev.map(d => d.id === tempId ? { ...d, id: data.id, status: 'verified', url: '#' } : d))
            } else {
                 setDocuments(prev => prev.map(d => d.id === tempId ? { ...d, status: 'error' } : d))
            }
        } catch (e) {
            console.error(e)
            setDocuments(prev => prev.map(d => d.id === tempId ? { ...d, status: 'error' } : d))
        }
    }

    return (
      <div className="space-y-4">
        <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            onChange={handleFileSelect} 
        />
        <div 
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-8 text-center hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors cursor-pointer group"
        >
          <FileText className="w-10 h-10 text-gray-400 mx-auto mb-2 group-hover:text-indigo-500 transition-colors" />
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Arraste documentos aqui (PBC)</p>
          <p className="text-xs text-gray-500">ou clique para selecionar (PDF, PNG, JPG)</p>
        </div>
        
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Anexos Processados</h3>
          {documents.map(doc => (
            <div key={doc.id} className="flex items-center justify-between p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded ${doc.status === 'error' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
                        {doc.type}
                    </div>
                    <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{doc.name}</p>
                        <p className="text-xs text-gray-500 flex items-center gap-1">
                            {doc.status === 'uploading' && <span className="flex items-center gap-1 text-indigo-500"><Loader2 className="w-3 h-3 animate-spin" /> Enviando...</span>}
                            {doc.status === 'verified' && <span className="flex items-center gap-1 text-green-500"><CheckCircle className="w-3 h-3" /> Validação Concluída</span>}
                            {doc.status === 'error' && <span className="flex items-center gap-1 text-red-500"><X className="w-3 h-3" /> Erro no envio</span>}
                        </p>
                    </div>
                </div>
                <button className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
          ))}
          {documents.length === 0 && (
             <p className="text-sm text-gray-400 text-center py-4">Nenhum documento anexado.</p>
          )}
        </div>
      </div>
    )
}

function CaseView({ transactionId, agentResult }: { transactionId: string | null, agentResult?: any }) {
  const [cases, setCases] = useState<CaseData[]>([])
  const [loading, setLoading] = useState(false)
  const [newCaseTitle, setNewCaseTitle] = useState('')
  const [activeCaseId, setActiveCaseId] = useState<number | null>(null)
  const [newComment, setNewComment] = useState('')
  const [reportLoading, setReportLoading] = useState<number | null>(null)
  const [transactionDetails, setTransactionDetails] = useState<any>(null)

  const fetchCases = () => {
    if (!transactionId) return;
    setLoading(true)
    apiFetch(`/cases?transaction_id=${transactionId}`)
      .then(r => r.json())
      .then(data => {
        setCases(data)
        if (data.length > 0 && !activeCaseId) {
            setActiveCaseId(data[0].id)
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchCases()
    if (transactionId) {
        apiFetch(`/transactions/${transactionId}`)
            .then(r => r.json())
            .then(setTransactionDetails)
            .catch(console.error)
    }
  }, [transactionId])

  const createCase = () => {
    if (!newCaseTitle.trim()) return;
    
    // Construct a rich description including agent findings if available
    let description = transactionDetails 
        ? `Investigação de Risco: ${transactionDetails.vendor} (${transactionDetails.category}). Valor: ${transactionDetails.amount}`
        : `Investigação iniciada para transação ${transactionId}`;
        
    if (agentResult) {
        description += `\n\n[Resumo do Agente IA]\nConclusão: ${agentResult.conclusion || 'N/A'}\nRisco Calculado: ${agentResult.risk_score || 'N/A'}`;
    }

    apiFetch('/cases/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newCaseTitle,
        transaction_id: transactionId,
        description: description,
        priority: agentResult?.risk_score > 80 ? 'Critical' : 'Medium',
        status: 'New'
      })
    }).then(() => {
      setNewCaseTitle('');
      fetchCases();
    })
  }

  const addComment = (caseId: number) => {
    if (!newComment.trim()) return;
    apiFetch('/case_comments/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            case: caseId,
            comment: newComment
        })
    }).then(() => {
        setNewComment('');
        fetchCases();
    })
  }

  const uploadAttachment = (caseId: number, file: File) => {
      const formData = new FormData()
      formData.append('case', String(caseId))
      formData.append('file', file)
      
      apiFetch('/case_attachments/', {
          method: 'POST',
          body: formData
      }).then(() => {
          fetchCases();
      }).catch(err => {
          console.error("Error uploading attachment:", err)
          alert("Erro ao enviar anexo.")
      })
  }

  const [reportData, setReportData] = useState<any>(null)

  const generateReport = (caseId: number) => {
      setReportLoading(caseId)
      apiFetch(`/cases/${caseId}/report`)
        .then(r => r.json())
        .then(setReportData)
        .catch(console.error)
        .finally(() => setReportLoading(null))
  }

  return (
    <div className="space-y-6">
      {reportData && (
          <ReportModal data={reportData} onClose={() => setReportData(null)} />
      )}

      <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg">
        <h3 className="font-semibold text-blue-800 dark:text-blue-300 mb-2">Gestão de Casos</h3>
        <p className="text-sm text-blue-600 dark:text-blue-400">
          Vincule esta transação a um caso de auditoria formal para rastreamento.
        </p>
      </div>

      {/* List existing cases */}
      <div className="space-y-4">
        {cases.map(c => (
          <div key={c.id} className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
            <div 
                className="p-3 bg-gray-50 dark:bg-gray-900 flex justify-between items-start cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                onClick={() => setActiveCaseId(activeCaseId === c.id ? null : c.id)}
            >
              <div>
                <h4 className="font-medium text-sm flex items-center gap-2">
                    {c.title}
                    {activeCaseId === c.id ? <span className="text-xs text-gray-400">▼</span> : <span className="text-xs text-gray-400">▶</span>}
                </h4>
                <div className="flex gap-2 mt-1">
                  <span className="text-xs px-2 py-0.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-full">{c.status}</span>
                  <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded-full">{c.priority}</span>
                </div>
              </div>
              <div className="text-xs text-gray-400">#{c.id}</div>
            </div>

            {/* Expanded Content */}
            {activeCaseId === c.id && (
                <div className="p-3 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
                    <div className="flex justify-end mb-2">
                        <button 
                            onClick={() => generateReport(c.id)}
                            disabled={reportLoading === c.id}
                            className="text-xs flex items-center gap-1 text-gray-500 hover:text-indigo-600 disabled:opacity-50"
                        >
                            {reportLoading === c.id ? (
                                <div className="w-3 h-3 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                            ) : (
                                <Printer className="w-3 h-3" />
                            )}
                            {reportLoading === c.id ? 'Gerando...' : 'Gerar Relatório'}
                        </button>
                    </div>
                    {/* Comments */}
                    <div className="space-y-3 mb-4">
                        <h5 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Comentários</h5>
                        {c.comments && c.comments.length > 0 ? (
                            <div className="space-y-2">
                                {c.comments.map(comment => (
                                    <div key={comment.id} className="text-sm bg-gray-50 dark:bg-gray-900 p-2 rounded">
                                        <p className="text-gray-800 dark:text-gray-200">{comment.comment}</p>
                                        <div className="text-xs text-gray-400 mt-1 flex justify-between">
                                            <span>User: {comment.user_id}</span>
                                            <span>{new Date(comment.created_at).toLocaleDateString()}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-xs text-gray-400 italic">Sem comentários.</p>
                        )}
                    </div>

                     {/* Attachments (Read-only for now) */}
                     {c.attachments && c.attachments.length > 0 && (
                        <div className="space-y-2 mb-4">
                            <h5 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Anexos</h5>
                            <div className="flex flex-wrap gap-2">
                                {c.attachments.map(att => (
                                    <a 
                                        key={att.id} 
                                        href={att.file_url} 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="text-xs bg-indigo-50 text-indigo-700 px-2 py-1 rounded border border-indigo-100 hover:bg-indigo-100 flex items-center gap-1"
                                    >
                                        📄 {att.file_name}
                                    </a>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Add Comment */}
                    <div className="flex gap-2 mt-2">
                        <input 
                            type="text" 
                            value={newComment}
                            onChange={(e) => setNewComment(e.target.value)}
                            placeholder="Adicionar comentário..."
                            className="flex-1 text-sm border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-transparent"
                            onKeyDown={(e) => e.key === 'Enter' && addComment(c.id)}
                        />
                        <button 
                            onClick={() => addComment(c.id)}
                            disabled={!newComment.trim()}
                            className="bg-gray-900 dark:bg-gray-700 text-white p-2 rounded-md disabled:opacity-50 hover:bg-gray-800"
                        >
                            <Send className="w-4 h-4" />
                        </button>
                    </div>

                    <div className="mt-3 border-t border-gray-100 dark:border-gray-800 pt-2">
                        <label className="flex items-center gap-2 text-xs text-indigo-600 cursor-pointer hover:text-indigo-800 w-fit">
                            <span className="bg-indigo-50 dark:bg-indigo-900/30 p-1.5 rounded flex items-center gap-1">
                                📎 Anexar arquivo
                            </span>
                            <input 
                                type="file" 
                                className="hidden" 
                                onChange={(e) => {
                                    if (e.target.files?.[0]) {
                                        uploadAttachment(c.id, e.target.files[0]);
                                    }
                                }}
                            />
                        </label>
                    </div>
                </div>
            )}
          </div>
        ))}
        
        {cases.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-8 border-2 border-dashed border-gray-200 dark:border-gray-800 rounded-lg">
              <Briefcase className="w-12 h-12 text-gray-300 mb-2" />
              <p className="text-gray-500 text-sm mb-4">Esta transação não tem casos de auditoria.</p>
              
              <div className="w-full max-w-xs space-y-3">
                <div className="space-y-2">
                    <label className="text-xs font-semibold text-gray-500 uppercase">Criação Rápida</label>
                    <input 
                        type="text" 
                        value={newCaseTitle}
                        onChange={(e) => setNewCaseTitle(e.target.value)}
                        placeholder="Título do novo caso..."
                        className="w-full text-sm border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-gray-900"
                    />
                    <button 
                        onClick={createCase}
                        disabled={!newCaseTitle.trim()}
                        className="w-full bg-indigo-600 text-white py-2 rounded-md disabled:opacity-50 hover:bg-indigo-700 font-medium transition-colors"
                    >
                        Iniciar Investigação
                    </button>
                </div>

                <div className="relative flex py-2 items-center">
                    <div className="flex-grow border-t border-gray-200 dark:border-gray-700"></div>
                    <span className="flex-shrink-0 mx-4 text-gray-400 text-xs">OU</span>
                    <div className="flex-grow border-t border-gray-200 dark:border-gray-700"></div>
                </div>

                <button 
                    onClick={() => {
                        const params = new URLSearchParams({
                            create: 'true',
                            transaction_id: transactionId || '',
                            title: transactionDetails ? `Investigação: ${transactionDetails.vendor}` : 'Nova Investigação',
                            description: transactionDetails ? `Suspeita de risco em transação de ${transactionDetails.amount} para ${transactionDetails.vendor}.` : ''
                        })
                        window.location.href = `/cases?${params.toString()}`
                    }}
                    className="w-full bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 py-2 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 font-medium transition-colors text-sm flex items-center justify-center gap-2"
                >
                    <PlusCircle className="w-4 h-4" />
                    Criar Caso Completo
                </button>
              </div>
          </div>
        )}
      </div>

      {/* Create new case (only if cases exist) */}
      {cases.length > 0 && (
        <div className="space-y-2 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex justify-between items-center cursor-pointer" onClick={() => setNewCaseTitle(newCaseTitle ? '' : ' ')}>
                 <label className="text-xs font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1">
                    <PlusCircle className="w-3 h-3" /> Novo Caso Adicional
                 </label>
            </div>
            {newCaseTitle !== '' && (
                <div className="flex gap-2">
                <input 
                    type="text" 
                    value={newCaseTitle === ' ' ? '' : newCaseTitle}
                    onChange={(e) => setNewCaseTitle(e.target.value)}
                    placeholder="Título do caso..."
                    className="flex-1 text-sm border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-transparent"
                    autoFocus
                />
                <button 
                    onClick={createCase}
                    disabled={!newCaseTitle.trim()}
                    className="bg-indigo-600 text-white p-2 rounded-md disabled:opacity-50 hover:bg-indigo-700"
                >
                    <Send className="w-4 h-4" />
                </button>
                </div>
            )}
        </div>
      )}
    </div>
  )
}
