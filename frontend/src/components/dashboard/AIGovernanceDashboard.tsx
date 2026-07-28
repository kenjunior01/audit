"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'

type GovernanceMetrics = {
  total_calls_24h: number
  success_rate: number
  avg_latency_ms: number
  hallucination_rate: number
  model_distribution: { model_name: string, count: number }[]
  recent_events: { timestamp: string, status: string, confidence_score: number | null, metadata: any }[]
}

export default function AIGovernanceDashboard() {
  const [metrics, setMetrics] = useState<GovernanceMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/governance/metrics/')
      .then(res => res.json())
      .then(data => setMetrics(data))
      .catch(err => console.error("Failed to load AI governance metrics", err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-1/4 mb-4"></div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {[1, 2, 3, 4].map(i => <div key={i} className="h-20 bg-gray-100 rounded"></div>)}
      </div>
      <div className="h-40 bg-gray-50 rounded w-full"></div>
    </div>
  )

  if (!metrics) return null

  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden">
      <div className="bg-slate-900 p-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-500/20 p-2 rounded-lg">
            <span className="text-xl">🛡️</span>
          </div>
          <div>
            <h2 className="text-white font-bold text-lg">Governança de IA</h2>
            <p className="text-slate-400 text-xs uppercase tracking-wider">Monitoramento de Precisão e Ética</p>
          </div>
        </div>
        <div className="flex gap-4 text-xs font-medium">
          <div className="flex items-center gap-1 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            SISTEMAS ATIVOS
          </div>
        </div>
      </div>

      <div className="p-6">
        {/* Principais Métricas */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <p className="text-slate-500 text-xs font-semibold mb-1 uppercase">Chamadas (24h)</p>
            <p className="text-2xl font-bold text-slate-900">{metrics.total_calls_24h}</p>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <p className="text-slate-500 text-xs font-semibold mb-1 uppercase">Taxa de Sucesso</p>
            <p className="text-2xl font-bold text-emerald-600">{metrics.success_rate}%</p>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <p className="text-slate-500 text-xs font-semibold mb-1 uppercase">Latência Média</p>
            <p className="text-2xl font-bold text-slate-900">{metrics.avg_latency_ms}ms</p>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <p className="text-slate-500 text-xs font-semibold mb-1 uppercase">Taxa de Alucinação</p>
            <p className={`text-2xl font-bold ${metrics.hallucination_rate > 5 ? 'text-red-600' : 'text-slate-900'}`}>
              {metrics.hallucination_rate}%
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Distribuição por Modelo */}
          <div>
            <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
              <span className="text-indigo-500">📊</span> Distribuição de Modelos
            </h3>
            <div className="space-y-3">
              {metrics.model_distribution.length > 0 ? (
                metrics.model_distribution.map((m, idx) => (
                  <div key={idx} className="relative">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium text-slate-700">{m.model_name || 'Desconhecido'}</span>
                      <span className="text-slate-500">{m.count} chamadas</span>
                    </div>
                    <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                      <div 
                        className="bg-indigo-500 h-full rounded-full transition-all duration-500" 
                        style={{ width: `${(m.count / Math.max(metrics.total_calls_24h, 1)) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-400 italic">Nenhum dado de modelo disponível.</p>
              )}
            </div>
          </div>

          {/* Histórico Recente de Precisão */}
          <div>
            <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
              <span className="text-indigo-500">📈</span> Tendência de Confiança
            </h3>
            <div className="h-32 flex items-end gap-1 px-2 border-b border-slate-100">
              {metrics.recent_events.length > 0 ? (
                metrics.recent_events.slice(0, 20).reverse().map((e, idx) => (
                  <div 
                    key={idx} 
                    className={`flex-1 rounded-t-sm transition-all hover:opacity-80 group relative ${
                      e.status === 'SUCCESS' ? 'bg-indigo-400' : 'bg-red-400'
                    }`}
                    style={{ height: `${(e.confidence_score || 0.5) * 100}%` }}
                  >
                    <div className="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-slate-800 text-white text-[10px] py-1 px-2 rounded whitespace-nowrap z-10 shadow-xl border border-slate-700">
                      <p className="font-bold border-b border-slate-700 pb-1 mb-1">Evento AI</p>
                      <p>Confiança: {((e.confidence_score || 0) * 100).toFixed(0)}%</p>
                      <p>Status: <span className={e.status === 'SUCCESS' ? 'text-emerald-400' : 'text-red-400'}>{e.status}</span></p>
                      {e.metadata?.anomaly_flag && (
                        <p className="text-amber-400 font-bold mt-1">⚠️ ANOMALIA: {e.metadata.anomaly_flag}</p>
                      )}
                      <p className="text-slate-400 mt-1">{new Date(e.timestamp).toLocaleTimeString()}</p>
                    </div>
                    {e.metadata?.anomaly_flag && (
                        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[8px]">⚠️</div>
                    )}
                  </div>
                ))
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-slate-400 italic">
                  Aguardando eventos...
                </div>
              )}
            </div>
            <div className="flex justify-between mt-2 text-[10px] text-slate-400 uppercase font-medium">
              <span>Eventos Anteriores</span>
              <span>Mais Recentes</span>
            </div>
          </div>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-100">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="bg-slate-100 p-1 rounded">ℹ️</span>
            Os dados de governança são utilizados para recalibrar automaticamente a sensibilidade da IA e mitigar riscos de alucinação em tempo real.
          </div>
        </div>
      </div>
    </div>
  )
}
