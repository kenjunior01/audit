import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  X, 
  Send, 
  Paperclip, 
  FileText, 
  User, 
  Clock, 
  AlertTriangle, 
  CheckCircle, 
  Trash2, 
  Download,
  ArrowRight
} from 'lucide-react'
import { apiFetch } from '@/lib/api'

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

interface Props {
  auditCase: AuditCase
  onClose: () => void
  onUpdate: () => void
}

export function CaseDetailsDrawer({ auditCase, onClose, onUpdate }: Props) {
  const [comments, setComments] = useState<CaseComment[]>([])
  const [newComment, setNewComment] = useState('')
  const [loadingComments, setLoadingComments] = useState(false)
  
  const [attachments, setAttachments] = useState<any[]>([])
  const [uploading, setUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  const [report, setReport] = useState<any>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  
  const [transaction, setTransaction] = useState<any>(null)
  const [loadingTransaction, setLoadingTransaction] = useState(false)

  const [exportingPdf, setExportingPdf] = useState(false)

  const [suggestedSteps, setSuggestedSteps] = useState<string | null>(null)
  const [loadingSteps, setLoadingSteps] = useState(false)

  const [status, setStatus] = useState(auditCase.status)
  const [priority, setPriority] = useState(auditCase.priority)
  const [pendingStatus, setPendingStatus] = useState<string | null>(null)
  const [findingType, setFindingType] = useState(auditCase.finding_type || '')
  const [inherentRisk, setInherentRisk] = useState<string>(auditCase.inherent_risk != null ? String(auditCase.inherent_risk) : '')
  const [residualRisk, setResidualRisk] = useState<string>(auditCase.residual_risk != null ? String(auditCase.residual_risk) : '')
  const [actionOwner, setActionOwner] = useState(auditCase.action_owner || '')
  const [actionPlan, setActionPlan] = useState(auditCase.action_plan || '')
  const [actionDueDate, setActionDueDate] = useState(
    auditCase.action_due_date ? auditCase.action_due_date.substring(0, 10) : ''
  )
  const [savingMetadata, setSavingMetadata] = useState(false)
  const [contextSummary, setContextSummary] = useState<any | null>(null)

  useEffect(() => {
    setStatus(auditCase.status)
    setPriority(auditCase.priority)
    setFindingType(auditCase.finding_type || '')
    setInherentRisk(auditCase.inherent_risk != null ? String(auditCase.inherent_risk) : '')
    setResidualRisk(auditCase.residual_risk != null ? String(auditCase.residual_risk) : '')
    setActionOwner(auditCase.action_owner || '')
    setActionPlan(auditCase.action_plan || '')
    setActionDueDate(auditCase.action_due_date ? auditCase.action_due_date.substring(0, 10) : '')
  }, [auditCase])

  const handleStatusChange = (newStatus: string) => {
    const current = status || ''
    const target = newStatus || ''
    if (current === 'New' && (target === 'Resolved' || target.startsWith('Closed'))) {
      alert('Fluxo Inválido: O caso deve estar "In Progress" antes de ser resolvido ou fechado.')
      return
    }

    if (target === 'Resolved' || target.startsWith('Closed')) {
      setPendingStatus(target)
    } else {
      updateStatus(target)
    }
  }

  const confirmStatusUpdate = () => {
      if (pendingStatus) {
          updateStatus(pendingStatus)
          setPendingStatus(null)
      }
  }

  const updateStatus = async (newStatus: string) => {
    setStatus(newStatus)
    try {
        await apiFetch(`/cases/${auditCase.id}/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        })
        onUpdate()
    } catch (e) {
        console.error(e)
    }
  }

  const updatePriority = async (newPriority: string) => {
    setPriority(newPriority)
    try {
        await apiFetch(`/cases/${auditCase.id}/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ priority: newPriority })
        })
        onUpdate()
    } catch (e) {
        console.error(e)
    }
  }

  const handleSaveMetadata = async () => {
    setSavingMetadata(true)
    try {
      const payload: any = {
        finding_type: findingType || null,
        action_owner: actionOwner || null,
        action_plan: actionPlan || null,
        action_due_date: actionDueDate ? new Date(actionDueDate).toISOString() : null,
      }
      if (inherentRisk !== '') {
        payload.inherent_risk = parseFloat(inherentRisk)
      } else {
        payload.inherent_risk = null
      }
      if (residualRisk !== '') {
        payload.residual_risk = parseFloat(residualRisk)
      } else {
        payload.residual_risk = null
      }

      await apiFetch(`/cases/${auditCase.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      onUpdate()
    } catch (e) {
      console.error(e)
    } finally {
      setSavingMetadata(false)
    }
  }
  
  useEffect(() => {
    fetchComments()
    fetchAttachments()
    if (auditCase.transaction_id) {
        fetchTransaction()
    }
  }, [auditCase.id])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  const fetchTransaction = async () => {
    setLoadingTransaction(true)
    try {
        // Try to find by transaction_id string
        const res = await apiFetch(`/transactions/?transaction_id=${auditCase.transaction_id}`)
        if (res.ok) {
            const data = await res.json()
            if (data.results && data.results.length > 0) {
                setTransaction(data.results[0])
            } else if (Array.isArray(data) && data.length > 0) {
                setTransaction(data[0])
            }
        }
    } catch (e) {
        console.error(e)
    } finally {
        setLoadingTransaction(false)
    }
  }

  const fetchComments = async () => {
    setLoadingComments(true)
    try {
      const res = await apiFetch(`/case_comments/?case=${auditCase.id}`)
      if (res.ok) {
        const data = await res.json()
        setComments(data)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingComments(false)
    }
  }

  const fetchAttachments = async () => {
    try {
      const res = await apiFetch(`/case_attachments/?case=${auditCase.id}`)
      if (res.ok) {
        const data = await res.json()
        setAttachments(data)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const uploadFile = async (file: File) => {
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('case', auditCase.id.toString())
    formData.append('file_name', file.name)
    formData.append('file_type', file.type)

    try {
      const res = await apiFetch('/case_attachments/', {
        method: 'POST',
        body: formData
      })
      if (res.ok) {
        fetchAttachments()
      }
    } catch (err) {
      console.error(err)
    } finally {
      setUploading(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return
    await uploadFile(e.target.files[0])
  }

  const handleDragOver = (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          await uploadFile(e.dataTransfer.files[0])
      }
  }

  const handleGenerateReport = async () => {
    setLoadingReport(true)
    try {
        const res = await apiFetch(`/cases/${auditCase.id}/report`)
        if (res.ok) {
            const data = await res.json()
            setReport(data)
        }
    } catch (e) {
        console.error(e)
    } finally {
        setLoadingReport(false)
    }
  }

  const handleSuggestSteps = async () => {
    setLoadingSteps(true)
    try {
        const res = await apiFetch(`/cases/${auditCase.id}/suggest_steps/`, {
            method: 'POST'
        })
        if (res.ok) {
            const data = await res.json()
            setSuggestedSteps(data.steps)
        }
    } catch (e) {
        console.error(e)
    } finally {
        setLoadingSteps(false)
    }
  }

  const handleExportPdf = async () => {
    setExportingPdf(true)
    try {
        const res = await apiFetch(`/cases/${auditCase.id}/export_pdf/`)
        if (res.ok) {
            const blob = await res.blob()
            const url = window.URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `Audit_Report_Case_${auditCase.id}.pdf`
            document.body.appendChild(a)
            a.click()
            window.URL.revokeObjectURL(url)
            document.body.removeChild(a)
        } else {
            console.error('Failed to export PDF')
        }
    } catch (e) {
        console.error(e)
    } finally {
        setExportingPdf(false)
    }
  }

  const handleAiFeedback = async (status: 'SUCCESS' | 'HALLUCINATION') => {
    try {
        await apiFetch('/governance/', {
            method: 'POST',
            body: JSON.stringify({
                event_type: 'USER_FEEDBACK',
                status: status,
                model_name: 'Frontend_AuditAI',
                prompt_tokens: 0,
                completion_tokens: 0,
                latency_ms: 0,
                confidence_score: status === 'SUCCESS' ? 1.0 : 0.0,
                metadata: {
                    case_id: auditCase.id,
                    feedback_type: status,
                    context: 'investigation_steps'
                }
            })
        })
        alert(status === 'SUCCESS' ? 'Obrigado pelo feedback!' : 'Alucinação reportada. Nossa equipe técnica irá analisar.')
    } catch (e) {
        console.error("Failed to send AI feedback", e)
    }
  }

  const handlePrintReport = () => {
    const printWindow = window.open('', '_blank')
    if (printWindow && report) {
        // Construct detailed HTML
        const xaiHtml = report.risk_analysis?.xai_explanation ? `
            <div class="section">
                <h3>Análise XAI (3 Camadas)</h3>
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1; padding: 10px; background: #fdf4ff; border: 1px solid #fae8ff;">
                        <h4 style="margin-top:0; color:#7e22ce;">Pessoal</h4>
                        <ul style="margin:0; padding-left:15px;">${report.risk_analysis.xai_explanation.feature_weights.layer_1_personal.map((f:any) => `<li>${f.replace('[Personal]', '')}</li>`).join('') || '<li>Sem fatores</li>'}</ul>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #eff6ff; border: 1px solid #dbeafe;">
                        <h4 style="margin-top:0; color:#1d4ed8;">Corporativo</h4>
                        <ul style="margin:0; padding-left:15px;">${report.risk_analysis.xai_explanation.feature_weights.layer_2_corporate.map((f:any) => `<li>${f.replace('[Corporate]', '')}</li>`).join('') || '<li>Sem fatores</li>'}</ul>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #f9fafb; border: 1px solid #e5e7eb;">
                        <h4 style="margin-top:0; color:#374151;">Global</h4>
                        <ul style="margin:0; padding-left:15px;">${report.risk_analysis.xai_explanation.feature_weights.layer_3_global.map((f:any) => `<li>${f.replace('[Global]', '')}</li>`).join('') || '<li>Sem fatores</li>'}</ul>
                    </div>
                </div>
            </div>
        ` : ''

        printWindow.document.write(`
            <html>
                <head>
                    <title>Relatório de Auditoria - Caso #${auditCase.id}</title>
                    <style>
                        body { font-family: sans-serif; padding: 40px; color: #111; max-width: 800px; margin: 0 auto; }
                        h1 { color: #333; border-bottom: 2px solid #333; padding-bottom: 10px; }
                        h3 { color: #4f46e5; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
                        .meta { margin-bottom: 30px; color: #666; font-size: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: #f9fafb; padding: 15px; border-radius: 8px; }
                        .summary { background: #f3f4f6; padding: 20px; border-radius: 8px; font-size: 14px; line-height: 1.6; border-left: 4px solid #4f46e5; }
                        .section { margin-top: 20px; }
                        ul { padding-left: 20px; }
                        li { margin-bottom: 5px; }
                        a { color: #4f46e5; text-decoration: none; }
                    </style>
                </head>
                <body>
                    <h1>Relatório de Auditoria</h1>
                    <div class="meta">
                        <div><strong>Caso:</strong> #${auditCase.id} - ${auditCase.title}</div>
                        <div><strong>Data:</strong> ${new Date().toLocaleDateString()}</div>
                        <div><strong>Responsável:</strong> ${auditCase.assigned_to}</div>
                        <div><strong>Status:</strong> ${auditCase.status}</div>
                        <div><strong>Prioridade:</strong> ${auditCase.priority}</div>
                        <div><strong>Gerado por:</strong> ${report.metadata?.generated_by || 'System'}</div>
                    </div>
                    
                    <div class="summary">
                        <strong>Resumo Executivo:</strong><br/>
                        ${report.executive_summary}
                    </div>

                    ${xaiHtml}
                    
                    <div class="section">
                        <h3>Evidências (${report.evidence?.length || 0})</h3>
                        <ul>
                            ${report.evidence?.map((e:any) => `<li><a href="${e.url}" target="_blank">${e.name}</a> <span style="color:#999; font-size:12px;">(Enviado por: ${e.uploaded_by})</span></li>`).join('') || '<li>Nenhuma evidência anexada.</li>'}
                        </ul>
                    </div>

                    <div class="section">
                        <h3>Histórico de Investigação</h3>
                        ${report.investigation_log?.map((l:any) => `
                            <div style="margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 5px;">
                                <small style="color:#666;"><strong>${l.user}</strong> em ${l.date}:</small><br/>
                                ${l.content}
                            </div>
                        `).join('') || 'Nenhum registro.'}
                    </div>
                    
                    <div style="margin-top: 50px; font-size: 12px; color: #999; text-align: center;">
                        Gerado automaticamente por AuditAI v2.1 • ${new Date().toLocaleString()}
                    </div>

                    <script>window.print();</script>
                </body>
            </html>
        `)
        printWindow.document.close()
    }
  }

  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newComment.trim()) return

    try {
      const res = await apiFetch('/case_comments/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case: auditCase.id,
          comment: newComment
        })
      })
      if (res.ok) {
        setNewComment('')
        fetchComments()
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
      />
      <motion.div 
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        className="relative w-full max-w-2xl bg-white dark:bg-gray-900 shadow-2xl h-full overflow-y-auto border-l border-gray-200 dark:border-gray-700"
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
             <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Caso #{auditCase.id}</h2>
                <p className="text-gray-500 text-sm">Criado em {new Date(auditCase.created_at || auditCase.updated_at).toLocaleDateString()}</p>
             </div>
             <div className="flex items-center gap-2">
                 <button 
                    onClick={handleSuggestSteps}
                    disabled={loadingSteps}
                    className="flex items-center gap-2 px-3 py-1.5 bg-amber-100 hover:bg-amber-200 dark:bg-amber-900/50 dark:hover:bg-amber-900/70 text-amber-700 dark:text-amber-300 rounded-lg text-sm font-medium transition-colors"
                 >
                    {loadingSteps ? <div className="w-4 h-4 border-2 border-amber-600 border-t-transparent rounded-full animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                    Sugerir Passos
                 </button>
                 <button 
                    onClick={handleGenerateReport}
                    disabled={loadingReport}
                    className="flex items-center gap-2 px-3 py-1.5 bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900/50 dark:hover:bg-indigo-900/70 text-indigo-700 dark:text-indigo-300 rounded-lg text-sm font-medium transition-colors"
                 >
                    {loadingReport ? <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /> : <FileText className="w-4 h-4" />}
                    Gerar Relatório IA
                 </button>
                 <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-500">
                   <X className="w-6 h-6" />
                 </button>
             </div>
          </div>

          {contextSummary && (
            <div className="mb-4 bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-[11px] text-indigo-900 flex flex-wrap gap-x-4 gap-y-1">
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

          <div className="space-y-6">
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                        Classificação do Achado
                    </div>
                    <select
                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                        value={findingType}
                        onChange={(e) => setFindingType(e.target.value)}
                    >
                        <option value="">Não definido</option>
                        <option value="Fraud">Fraude</option>
                        <option value="Control">Controle</option>
                        <option value="Process">Processo</option>
                        <option value="System">Sistema</option>
                        <option value="Other">Outro</option>
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            Risco Inerente
                        </div>
                        <input
                            type="number"
                            min={0}
                            max={100}
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={inherentRisk}
                            onChange={(e) => setInherentRisk(e.target.value)}
                            placeholder="0-100"
                        />
                    </div>
                    <div>
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            Risco Residual
                        </div>
                        <input
                            type="number"
                            min={0}
                            max={100}
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={residualRisk}
                            onChange={(e) => setResidualRisk(e.target.value)}
                            placeholder="0-100"
                        />
                    </div>
                </div>
             </div>
             
             <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                        Plano de Ação
                    </div>
                    <button
                        type="button"
                        onClick={handleSaveMetadata}
                        disabled={savingMetadata}
                        className="px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-2"
                    >
                        {savingMetadata ? (
                            <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : (
                            <CheckCircle className="w-3 h-3" />
                        )}
                        Salvar Plano
                    </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="md:col-span-1">
                        <div className="text-xs text-gray-500 mb-1">Responsável</div>
                        <input
                            type="text"
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={actionOwner}
                            onChange={(e) => setActionOwner(e.target.value)}
                            placeholder="Nome do responsável"
                        />
                    </div>
                    <div className="md:col-span-1">
                        <div className="text-xs text-gray-500 mb-1">Prazo do Plano</div>
                        <input
                            type="date"
                            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                            value={actionDueDate}
                            onChange={(e) => setActionDueDate(e.target.value)}
                        />
                    </div>
                </div>
                <div>
                    <div className="text-xs text-gray-500 mb-1">Descrição do Plano</div>
                    <textarea
                        rows={3}
                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-sm"
                        value={actionPlan}
                        onChange={(e) => setActionPlan(e.target.value)}
                        placeholder="Descreva as ações de remediação, responsáveis e marcos principais..."
                    />
                </div>
             </div>
             {report && (
                 <motion.div 
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 rounded-xl"
                 >
                    <div className="flex justify-between items-start mb-2">
                        <h3 className="font-bold text-indigo-900 dark:text-indigo-300 flex items-center gap-2">
                            <FileText className="w-4 h-4" />
                            Relatório Executivo (IA)
                        </h3>
                        <span className="text-xs text-indigo-400 font-mono">v2.1</span>
                    </div>
                    
                    <div className="prose dark:prose-invert text-sm max-w-none mb-4">
                        <p className="whitespace-pre-line text-gray-700 dark:text-gray-300">{report.executive_summary}</p>
                    </div>
                    
                    {/* XAI Visualization */}
                    {report.risk_analysis?.xai_explanation && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 mt-4 pt-4 border-t border-indigo-100 dark:border-indigo-800">
                            {/* Personal */}
                            <div className="bg-purple-50 dark:bg-purple-900/10 p-2 rounded border border-purple-100 dark:border-purple-900/30">
                                <h5 className="text-xs font-bold text-purple-700 dark:text-purple-400 uppercase mb-1 flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Pessoal
                                </h5>
                                <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                                    {report.risk_analysis.xai_explanation.feature_weights.layer_1_personal?.length > 0 ? 
                                        report.risk_analysis.xai_explanation.feature_weights.layer_1_personal.map((f:string, i:number) => <li key={i}>{f.replace('[Personal]', '')}</li>) :
                                        <li className="italic opacity-50">Sem fatores relevantes</li>
                                    }
                                </ul>
                            </div>
                            {/* Corporate */}
                            <div className="bg-blue-50 dark:bg-blue-900/10 p-2 rounded border border-blue-100 dark:border-blue-900/30">
                                <h5 className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase mb-1 flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span> Corporativo
                                </h5>
                                <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                                    {report.risk_analysis.xai_explanation.feature_weights.layer_2_corporate?.length > 0 ? 
                                        report.risk_analysis.xai_explanation.feature_weights.layer_2_corporate.map((f:string, i:number) => <li key={i}>{f.replace('[Corporate]', '')}</li>) :
                                        <li className="italic opacity-50">Sem fatores relevantes</li>
                                    }
                                </ul>
                            </div>
                            {/* Global */}
                            <div className="bg-gray-50 dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                <h5 className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase mb-1 flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-gray-500"></span> Global
                                </h5>
                                <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                                    {report.risk_analysis.xai_explanation.feature_weights.layer_3_global?.length > 0 ? 
                                        report.risk_analysis.xai_explanation.feature_weights.layer_3_global.map((f:string, i:number) => <li key={i}>{f.replace('[Global]', '')}</li>) :
                                        <li className="italic opacity-50">Sem fatores relevantes</li>
                                    }
                                </ul>
                            </div>
                        </div>
                    )}

                    <div className="flex justify-end gap-4">
                        <button 
                            onClick={handleExportPdf} 
                            disabled={exportingPdf}
                            className="text-xs flex items-center gap-1 text-emerald-600 hover:underline disabled:opacity-50"
                        >
                            <Download className="w-3 h-3" /> 
                            {exportingPdf ? 'Gerando PDF...' : 'Exportar PDF com Assinatura'}
                        </button>
                        <button onClick={handlePrintReport} className="text-xs flex items-center gap-1 text-indigo-600 hover:underline">
                            <FileText className="w-3 h-3" /> Imprimir Relatório Completo
                        </button>
                    </div>
                 </motion.div>
             )}

            {suggestedSteps && (
                 <motion.div 
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 rounded-xl"
                 >
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="font-bold text-amber-900 dark:text-amber-300 flex items-center gap-2">
                            <ArrowRight className="w-4 h-4" />
                            Passos de Investigação Sugeridos (IA)
                        </h3>
                        <div className="flex gap-2">
                            <button 
                                onClick={() => handleAiFeedback('SUCCESS')}
                                className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded hover:bg-emerald-200 transition-colors flex items-center gap-1"
                                title="Útil e Preciso"
                            >
                                👍 Útil
                            </button>
                            <button 
                                onClick={() => handleAiFeedback('HALLUCINATION')}
                                className="text-[10px] bg-red-100 text-red-700 px-2 py-0.5 rounded hover:bg-red-200 transition-colors flex items-center gap-1"
                                title="Relatar Alucinação ou Erro"
                            >
                                🚩 Erro/Alucinação
                            </button>
                        </div>
                    </div>
                    <div className="prose dark:prose-invert text-sm max-w-none">
                        <p className="whitespace-pre-line text-gray-700 dark:text-gray-300">{suggestedSteps}</p>
                    </div>
                 </motion.div>
            )}
            {/* Status Bar - Editable */}
            <div className="flex items-center gap-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
              <div className="flex-1">
                <div className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-1">Status</div>
                <select 
                    value={status}
                    onChange={(e) => handleStatusChange(e.target.value)}
                    className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-2 py-1 text-sm font-medium text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-indigo-500"
                >
                    <option value="New">New</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Under Review">Under Review</option>
                    <option value="Closed - Remediated">Closed - Remediated</option>
                    <option value="Closed - No Issue">Closed - No Issue</option>
                </select>
              </div>
              <div className="flex-1">
                <div className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-1">Prioridade</div>
                <select 
                    value={priority}
                    onChange={(e) => updatePriority(e.target.value)}
                    className={`w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-2 py-1 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500 ${priority === 'Critical' ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}
                >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                </select>
              </div>
              <div className="flex-1">
                 <div className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-1">Responsável</div>
                 <div className="font-medium text-gray-900 dark:text-white flex items-center gap-2">
                    <User className="w-4 h-4 text-gray-400" />
                    {auditCase.assigned_to || 'N/A'}
                 </div>
              </div>
            </div>

            {/* Description */}
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Descrição</h3>
              <div className="p-4 bg-gray-50 dark:bg-gray-800/30 rounded-xl text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 min-h-[100px]">
                {auditCase.description || 'Nenhuma descrição fornecida.'}
              </div>
            </div>

            {/* Related Transaction */}
            {auditCase.transaction_id && (
               <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Transação Relacionada</h3>
                  <div className="bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/30 rounded-xl overflow-hidden">
                     <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-indigo-100/50 dark:hover:bg-indigo-900/20 transition-colors">
                        <div className="flex items-center gap-3">
                           <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded text-indigo-600">
                              <FileText className="w-5 h-5" />
                           </div>
                           <div>
                              <div className="font-medium text-gray-900 dark:text-white">Transação #{auditCase.transaction_id}</div>
                              {loadingTransaction ? (
                                  <div className="h-3 w-24 bg-indigo-200 dark:bg-indigo-800 rounded animate-pulse mt-1" />
                              ) : transaction ? (
                                  <div className="text-sm text-gray-600 dark:text-gray-400 mt-1 flex gap-3">
                                      <span className="font-medium">{transaction.vendor}</span>
                                      <span>•</span>
                                      <span>{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(transaction.amount)}</span>
                                      <span>•</span>
                                      <span className={`${transaction.risk_score > 80 ? 'text-red-600 font-bold' : transaction.risk_score > 50 ? 'text-orange-600' : 'text-green-600'}`}>
                                          Risco: {Math.round(transaction.risk_score)}
                                      </span>
                                      {contextSummary &&
                                        Array.isArray(contextSummary.audit_domains) &&
                                        contextSummary.audit_domains.length > 0 &&
                                        transaction.category &&
                                        !contextSummary.audit_domains.includes(transaction.category) && (
                                          <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-100 text-amber-800">
                                            Fora dos domínios ativos
                                          </span>
                                      )}
                                  </div>
                              ) : (
                                  <div className="text-xs text-indigo-600 dark:text-indigo-400">Ver detalhes completos</div>
                              )}
                           </div>
                        </div>
                        <ArrowRight className="w-5 h-5 text-indigo-400" />
                     </div>
                     {transaction && (
                         <div className="px-4 pb-4 pt-0 text-xs text-gray-500 border-t border-indigo-100 dark:border-indigo-800/50 mt-2 pt-2">
                             <div className="grid grid-cols-2 gap-2 mt-2">
                                 <div>
                                     <span className="block font-semibold">Data:</span> 
                                     {new Date(transaction.timestamp).toLocaleString()}
                                 </div>
                                 <div>
                                     <span className="block font-semibold">Categoria:</span> 
                                     {transaction.category}
                                 </div>
                             </div>
                         </div>
                     )}
                  </div>
               </div>
            )}

            {/* Evidence Section */}
            <div>
               <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Evidências</h3>
               <div className="space-y-3">
                   {attachments.length > 0 && (
                       <div className="grid grid-cols-2 gap-2">
                           {attachments.map(att => (
                               <a 
                                 key={att.id} 
                                 href={att.file_url} 
                                 target="_blank" 
                                 rel="noopener noreferrer"
                                 className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg flex items-center gap-2 hover:border-indigo-300 transition-colors group"
                               >
                                   <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded text-gray-500 group-hover:text-indigo-600 transition-colors">
                                       <Paperclip className="w-4 h-4" />
                                   </div>
                                   <div className="overflow-hidden">
                                       <div className="text-sm font-medium truncate text-gray-900 dark:text-gray-200" title={att.file_name}>{att.file_name || 'Anexo sem nome'}</div>
                                       <div className="text-xs text-gray-500">{new Date(att.uploaded_at).toLocaleDateString()}</div>
                                   </div>
                               </a>
                           ))}
                       </div>
                   )}
                   
                   <label 
                       onDragOver={handleDragOver}
                       onDragLeave={handleDragLeave}
                       onDrop={handleDrop}
                       className={`flex items-center justify-center w-full p-4 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 ${
                           isDragging 
                               ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 scale-[1.02]' 
                               : 'border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                       }`}
                   >
                       <input type="file" className="hidden" onChange={handleUpload} disabled={uploading} />
                       <div className="text-center">
                           {uploading ? (
                               <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                           ) : (
                               <div className={`p-2 rounded-full w-fit mx-auto mb-2 ${isDragging ? 'bg-indigo-100 dark:bg-indigo-800 text-indigo-600' : 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-500'}`}>
                                   <Paperclip className={`w-5 h-5 ${isDragging ? 'animate-bounce' : ''}`} />
                               </div>
                           )}
                           <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                               {uploading ? 'Enviando...' : isDragging ? 'Solte o arquivo aqui' : 'Clique ou arraste para anexar evidências'}
                           </p>
                           <p className="text-xs text-gray-500 mt-1">PDF, JPG, PNG, CSV</p>
                       </div>
                   </label>
               </div>
            </div>

            {/* Comments Section */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Comentários & Notas</h3>
                <span className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-full text-gray-600 dark:text-gray-400">{comments.length}</span>
              </div>
              
              <div className="bg-gray-50 dark:bg-gray-800/30 rounded-xl border border-gray-200 dark:border-gray-700 p-4 max-h-[300px] overflow-y-auto space-y-4 mb-4">
                {loadingComments ? (
                  <div className="text-center text-gray-500 py-4">Carregando...</div>
                ) : comments.length === 0 ? (
                   <div className="text-center text-gray-400 py-8 italic">Nenhum comentário ainda.</div>
                ) : (
                  comments.map(comment => (
                    <div key={comment.id} className="flex gap-3">
                      <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex-shrink-0 flex items-center justify-center text-xs font-bold text-gray-600">
                        {comment.user_id ? comment.user_id.charAt(0).toUpperCase() : 'U'}
                      </div>
                      <div className="flex-1">
                        <div className="bg-white dark:bg-gray-800 p-3 rounded-lg rounded-tl-none border border-gray-200 dark:border-gray-700 shadow-sm">
                          <p className="text-sm text-gray-800 dark:text-gray-200">{comment.comment}</p>
                        </div>
                        <div className="mt-1 text-xs text-gray-400">
                          {new Date(comment.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <form onSubmit={handleAddComment} className="relative">
                 <input 
                    type="text" 
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    placeholder="Adicionar um comentário ou observação..." 
                    className="w-full pl-4 pr-12 py-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none shadow-sm"
                 />
                 <button 
                    type="submit"
                    disabled={!newComment.trim()}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                 >
                    <Send className="w-4 h-4" />
                 </button>
              </form>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Confirmation Modal */}
      <AnimatePresence>
        {pendingStatus && (
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
                <motion.div 
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-sm w-full p-6 border border-gray-200 dark:border-gray-700"
                >
                    <div className="flex items-center gap-3 text-amber-600 mb-4">
                        <AlertTriangle className="w-6 h-6" />
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">Confirmar alteração?</h3>
                    </div>
                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                        Você está prestes a alterar o status para <span className="font-bold">{pendingStatus}</span>. 
                        {pendingStatus === 'Closed' ? ' Isso indicará que o caso foi finalizado e não requer mais ações.' : ' Certifique-se de que todas as etapas foram concluídas.'}
                    </p>
                    <div className="flex justify-end gap-3">
                        <button 
                            onClick={() => setPendingStatus(null)}
                            className="px-4 py-2 text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        >
                            Cancelar
                        </button>
                        <button 
                            onClick={confirmStatusUpdate}
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition-colors"
                        >
                            Confirmar
                        </button>
                    </div>
                </motion.div>
            </div>
        )}
      </AnimatePresence>
    </div>
  )
}
