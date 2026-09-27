"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import Link from 'next/link'
import UserInsightsCard from '@/components/dashboard/UserInsightsCard'
import ForecastChart from '@/components/dashboard/ForecastChart'
import ContextRiskChart from '@/components/dashboard/ContextRiskChart'
import AIExecutiveSummary from '@/components/dashboard/AIExecutiveSummary'
import AIGovernanceDashboard from '@/components/dashboard/AIGovernanceDashboard'
import CopilotBriefingCard from '@/components/dashboard/CopilotBriefingCard'

type Stats = {
  total_transactions: number
  high_risk_alerts: number
  open_cases: number
  overdue_cases: number
  potential_savings: number
  risk_trend: string
}

type Alert = {
  id: number
  alert_type: string
  category?: string
  timestamp: string
  materiality: number
}

type Transaction = {
  id: string
  amount: number
  currency: string
  vendor?: string
  timestamp: string
}

export default function DashboardPage() {
  useRequireToken()
  const [stats, setStats] = useState<Stats | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [layoutConfig, setLayoutConfig] = useState<any>(null)
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [execSummary, setExecSummary] = useState<any | null>(null)

  const [forecast, setForecast] = useState<any>(null)
  
  useEffect(() => {
    Promise.all([
      apiFetch('/context/stats').then(r => r.json()),
      apiFetch('/alerts').then(r => r.json()),
      apiFetch('/transactions').then(r => r.json()),
      apiFetch('/ai/forecast').then(r => r.json()),
      apiFetch('/profile/me').then(r => r.json()),
      apiFetch('/context/profile/current/').then(r => r.json()).catch(() => null),
      apiFetch('/ai/executive-summary').then(r => r.json()).catch(() => null)
    ]).then(([s, a, t, f, p, ctx, es]) => {
      setStats(s)
      setAlerts((a.results || a.items || a || []).slice(0, 5))
      setTransactions((t.results || t.items || t || []).slice(0, 5))
      setForecast(f)
      setLayoutConfig(p.layout_config || {})
      setContextSummary(ctx)
      setExecSummary(es)
    }).finally(() => setLoading(false))
  }, [])

  // Simple SVG Line Chart Component
  const TrendChart = () => {
    // Mock data for demonstration - in real app, fetch from /stats/history
    const data = [12, 19, 15, 25, 22, 30, stats?.high_risk_alerts || 28]
    const max = Math.max(...data)
    const points = data.map((val, i) => {
      const x = (i / (data.length - 1)) * 100
      const y = 100 - (val / max) * 100
      return `${x},${y}`
    }).join(' ')

    return (
      <div className="h-32 w-full mt-4 relative border-b border-l border-gray-300">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full overflow-visible">
          <polyline
            fill="none"
            stroke="#2563eb"
            strokeWidth="2"
            points={points}
          />
          {data.map((val, i) => (
            <circle
              key={i}
              cx={(i / (data.length - 1)) * 100}
              cy={100 - (val / max) * 100}
              r="1.5"
              fill="#2563eb"
            />
          ))}
        </svg>
        <div className="absolute -bottom-6 left-0 text-xs text-gray-500">7 dias atrás</div>
        <div className="absolute -bottom-6 right-0 text-xs text-gray-500">Hoje</div>
      </div>
    )
  }

  if (loading) return <div className="p-4">Carregando dashboard...</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-800">Visão Geral</h1>
        <div className="text-sm text-gray-500">Última atualização: {new Date().toLocaleTimeString()}</div>
      </div>

      <CopilotBriefingCard />
      
      {contextSummary && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex flex-wrap items-center gap-4 text-sm text-indigo-900">
          <div>
            <div className="uppercase text-[11px] tracking-wide text-indigo-600 font-semibold">
              Contexto de Auditoria Ativo
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              <span><span className="font-semibold">País:</span> {contextSummary.country || 'Não definido'}</span>
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
          </div>
        </div>
      )}
      
      {layoutConfig?.welcome_message && (
        <div className="bg-blue-50 border-l-4 border-blue-500 p-4">
            <p className="font-bold text-blue-700">{layoutConfig.welcome_message}</p>
        </div>
      )}

      {/* NEW: AI Executive Summary (Top Priority) */}
      <AIExecutiveSummary />

      {/* NEW: AI Governance Dashboard (Transparency & Trust) */}
      <AIGovernanceDashboard />
      
      {/* AI & Insights Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="h-full">
            <UserInsightsCard />
          </div>
          
          {/* Forecast Insight */}
          {forecast && (
            <div className="bg-gradient-to-r from-purple-100 to-indigo-100 border border-purple-200 p-6 rounded-xl flex flex-col justify-center h-full shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="text-2xl">🔮</div>
                <h3 className="font-bold text-purple-900 text-lg">Previsão de Risco (AI)</h3>
              </div>
              <p className="text-purple-800 leading-relaxed">{forecast.insight}</p>
              <div className="mt-4 flex items-center gap-2 text-sm text-purple-700 font-medium">
                 <span>Confiança: {(forecast.confidence_interval * 100).toFixed(0)}%</span>
              </div>
            </div>
          )}
      </div>

      {/* Stats Cards */}
      {layoutConfig?.show_stats !== false && stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-white p-4 rounded-lg shadow border-l-4 border-blue-500">
            <div className="text-sm text-gray-500">Total Transações</div>
            <div className="text-2xl font-bold text-gray-800">{stats.total_transactions}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow border-l-4 border-red-500">
            <div className="text-sm text-gray-500">Alertas de Risco Alto</div>
            <div className="text-2xl font-bold text-gray-800">{stats.high_risk_alerts}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow border-l-4 border-yellow-500">
            <div className="text-sm text-gray-500">Casos Abertos</div>
            <div className="text-2xl font-bold text-gray-800">{stats.open_cases}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow border-l-4 border-orange-500">
            <div className="text-sm text-gray-500">Casos Atrasados (SLA)</div>
            <div className="text-2xl font-bold text-gray-800">{stats.overdue_cases}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow border-l-4 border-green-500">
            <div className="text-sm text-gray-500">Economia Potencial</div>
            <div className="text-2xl font-bold text-gray-800">
              {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(stats.potential_savings)}
            </div>
          </div>
          {execSummary && typeof execSummary.out_of_scope_alerts === 'number' && typeof execSummary.total_alerts_week === 'number' && execSummary.total_alerts_week > 0 && (
            <div className="bg-white p-4 rounded-lg shadow border-l-4 border-indigo-500">
              <div className="text-sm text-gray-500 flex justify-between items-center">
                <span>Escopo vs Realidade</span>
                <span className="text-[11px] uppercase tracking-wide text-indigo-600 font-semibold">
                  {execSummary.context_country || 'País não definido'}
                </span>
              </div>
              <div className="mt-1 text-2xl font-bold text-gray-800">
                {Math.round((execSummary.out_of_scope_alerts / execSummary.total_alerts_week) * 100)}%
              </div>
              <div className="text-xs text-gray-500">
                dos alertas da semana estão fora do contexto configurado.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Charts Section */}
      {layoutConfig?.show_charts !== false && (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800">Tendência Passada</h3>
          <p className="text-xs text-gray-500 mb-2">Histórico de sinais (7 dias)</p>
          <TrendChart />
        </div>
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 text-purple-700">Previsão Futura</h3>
          <p className="text-xs text-gray-500 mb-2">Projeção de Risco (12 semanas)</p>
          <ForecastChart />
        </div>
        <ContextRiskChart />
      </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Alerts */}
        {layoutConfig?.show_recent_alerts !== false && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-800">Alertas Recentes</h2>
            <Link href="/alerts" className="text-blue-600 hover:text-blue-800 text-sm">Ver todos</Link>
          </div>
          <div className="space-y-3">
            {alerts.length === 0 ? <p className="text-gray-500">Nenhum alerta recente.</p> : alerts.map(a => (
              <div key={a.id} className="flex justify-between items-center border-b pb-2 last:border-0">
                <div>
                  <div className="font-medium text-gray-800">{a.alert_type}</div>
                  <div className="text-xs text-gray-500">{new Date(a.timestamp).toLocaleDateString()} - {a.category || 'N/A'}</div>
                </div>
                <div className={`text-sm font-semibold ${a.materiality > 0.7 ? 'text-red-600' : 'text-yellow-600'}`}>
                  {(a.materiality * 100).toFixed(0)}% Risco
                </div>
              </div>
            ))}
          </div>
        </div>
        )}

        {/* Recent Transactions */}
        {layoutConfig?.show_recent_transactions !== false && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-800">Transações Recentes</h2>
            <Link href="/transactions" className="text-blue-600 hover:text-blue-800 text-sm">Ver todas</Link>
          </div>
          <div className="space-y-3">
            {transactions.length === 0 ? <p className="text-gray-500">Nenhuma transação recente.</p> : transactions.map(t => (
              <div key={t.id} className="flex justify-between items-center border-b pb-2 last:border-0">
                <div>
                  <div className="font-medium text-gray-800">{t.vendor || 'Desconhecido'}</div>
                  <div className="text-xs text-gray-500">{new Date(t.timestamp).toLocaleDateString()}</div>
                </div>
                <div className="text-sm font-mono text-gray-700">
                  {t.currency} {t.amount.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
    </div>
  )
}
