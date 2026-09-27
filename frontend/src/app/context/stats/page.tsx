"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

type Stats = {
  rules_active: number
  rules_pending_validation: number
  signals_pending_validation: number
  signals_last_7_days: number
  alerts_overdue_estimate: number
}

export default function ContextStatsPage() {
  useRequireToken()
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => {
    apiFetch('/context/stats').then(r => r.json()).then(setStats)
  }, [])
  return (
    <div>
      <h2 className="text-lg font-medium mb-4">KPIs de Contexto</h2>
      {!stats && <div className="text-sm text-gray-600">Carregando...</div>}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {title:'Regras ativas', value: stats.rules_active},
            {title:'Regras pendentes', value: stats.rules_pending_validation},
            {title:'Sinais pendentes', value: stats.signals_pending_validation},
            {title:'Sinais últimos 7 dias', value: stats.signals_last_7_days},
            {title:'Alertas atrasados (estim.)', value: stats.alerts_overdue_estimate}
          ].map((c, i) => (
            <div key={i} className="bg-white rounded shadow p-4">
              <div className="text-sm text-gray-500">{c.title}</div>
              <div className="text-2xl font-semibold">{c.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
