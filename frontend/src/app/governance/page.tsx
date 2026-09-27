"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import AIGovernanceDashboard from '@/components/dashboard/AIGovernanceDashboard'
import { ShieldCheck, AlertCircle, CheckCircle2, XCircle, Clock, Cpu } from 'lucide-react'

type GovernanceEvent = {
  id: number
  timestamp: string
  event_type: string
  model_name: string
  status: string
  latency_ms: number
  confidence_score: number | null
  input_data: any
  output_data: any
}

export default function GovernancePage() {
  const [events, setEvents] = useState<GovernanceEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/governance/')
      .then(res => res.json())
      .then(data => setEvents(data.results || data))
      .catch(err => console.error("Failed to load governance events", err))
      .finally(() => setLoading(false))
  }, [])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'SUCCESS': return <CheckCircle2 className="w-4 h-4 text-emerald-500" />
      case 'FAILED': return <XCircle className="w-4 h-4 text-red-500" />
      case 'HALLUCINATION': return <AlertCircle className="w-4 h-4 text-amber-500" />
      default: return <Clock className="w-4 h-4 text-slate-400" />
    }
  }

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
            <ShieldCheck className="w-8 h-8 text-indigo-600" />
            Centro de Governança de IA
          </h1>
          <p className="text-slate-500 mt-1">
            Monitoramento em tempo real de integridade, precisão e conformidade ética dos modelos.
          </p>
        </div>
        <div className="flex gap-2">
          <div className="bg-emerald-50 text-emerald-700 px-4 py-2 rounded-lg border border-emerald-100 flex items-center gap-2 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Monitoramento Ativo
          </div>
        </div>
      </div>

      {/* Dashboard Overview */}
      <AIGovernanceDashboard />

      {/* Detailed Event Log */}
      <div className="bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden">
        <div className="bg-slate-50 border-b border-slate-200 p-4 flex justify-between items-center">
          <h2 className="font-bold text-slate-800 flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-600" />
            Log de Eventos de Governança
          </h2>
          <div className="text-xs text-slate-500">Exibindo os últimos {events.length} eventos</div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
              <tr>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Evento</th>
                <th className="px-6 py-3">Modelo</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Latência</th>
                <th className="px-6 py-3">Confiança</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                [1, 2, 3, 4, 5].map(i => (
                  <tr key={i} className="animate-pulse">
                    <td colSpan={6} className="px-6 py-4">
                      <div className="h-4 bg-slate-100 rounded w-full"></div>
                    </td>
                  </tr>
                ))
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400 italic">
                    Nenhum evento de governança registrado ainda.
                  </td>
                </tr>
              ) : (
                events.map(event => (
                  <tr key={event.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-slate-500 font-mono text-xs">
                      {new Date(event.timestamp).toLocaleString('pt-BR')}
                    </td>
                    <td className="px-6 py-4">
                      <span className="px-2 py-1 bg-indigo-50 text-indigo-700 rounded text-[10px] font-bold uppercase">
                        {event.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 flex items-center gap-2">
                      <Cpu className="w-3 h-3 text-slate-400" />
                      <span className="text-slate-700 font-medium">{event.model_name || 'Desconhecido'}</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(event.status)}
                        <span className={`text-xs font-bold ${
                          event.status === 'SUCCESS' ? 'text-emerald-600' : 
                          event.status === 'FAILED' ? 'text-red-600' : 'text-amber-600'
                        }`}>
                          {event.status}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {event.latency_ms}ms
                    </td>
                    <td className="px-6 py-4">
                      {event.confidence_score ? (
                        <div className="flex items-center gap-2">
                          <div className="w-12 bg-slate-100 h-1.5 rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${
                                event.confidence_score > 0.8 ? 'bg-emerald-500' : 
                                event.confidence_score > 0.5 ? 'bg-amber-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${event.confidence_score * 100}%` }}
                            ></div>
                          </div>
                          <span className="text-[10px] font-bold text-slate-600">
                            {(event.confidence_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-300 text-xs">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-indigo-900 rounded-xl p-6 text-white shadow-xl">
          <h3 className="font-bold text-lg mb-2 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-300" />
            Integridade Ética
          </h3>
          <p className="text-indigo-200 text-sm leading-relaxed">
            Todos os modelos são validados contra vieses e conformidade regulatória em cada execução. 
            O sistema de governança bloqueia automaticamente respostas que não atendem aos critérios de segurança.
          </p>
        </div>
        
        <div className="bg-slate-900 rounded-xl p-6 text-white shadow-xl">
          <h3 className="font-bold text-lg mb-2 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-blue-400" />
            Transparência XAI
          </h3>
          <p className="text-slate-300 text-sm leading-relaxed">
            A IA Explicável (XAI) garante que cada pontuação de risco e recomendação tenha uma justificativa técnica rastreável, 
            permitindo auditoria humana completa sobre as decisões automatizadas.
          </p>
        </div>

        <div className="bg-slate-800 rounded-xl p-6 text-white shadow-xl">
          <h3 className="font-bold text-lg mb-2 flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            Controle de Alucinação
          </h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Utilizamos cross-validation entre múltiplos modelos e checagem de fatos via Memória Institucional para 
            reduzir drasticamente a taxa de informações imprecisas ou inventadas pela IA.
          </p>
        </div>
      </div>
    </div>
  )
}
