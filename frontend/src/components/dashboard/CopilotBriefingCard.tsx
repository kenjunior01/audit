"use client"
/**
 * Cartão "Briefing IA" para a página inicial.
 * Mostra o briefing executivo proativo do Copiloto Global:
 * KPIs vivos + narrativa + insights com tons + ações navegáveis.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { Card, CardContent } from "@/components/ui/card"
import {
  Sparkles, Loader2, RefreshCcw, AlertTriangle, CheckCircle2, Info,
  ShieldAlert, ArrowRight,
} from 'lucide-react'

type Insight = { title: string; detail: string; tone: 'info' | 'warn' | 'danger' | 'success' }
type Action = { label: string; href: string }
type Briefing = {
  briefing_md: string
  kpis: {
    transactions_total: number
    transactions_amount: number
    open_alerts: number
    critical_alerts: string
    cases_open: number
    cases_overdue: number
    benford_mad?: number
    benford_verdict?: string
    trend: string
  }
  insights: Insight[]
  actions: Action[]
  generated_at: string
}

const TONE_STYLE: Record<string, { icon: typeof Info; cls: string }> = {
  info: { icon: Info, cls: 'bg-sky-950/60 border-sky-800 text-sky-300' },
  warn: { icon: AlertTriangle, cls: 'bg-amber-950/60 border-amber-800 text-amber-300' },
  danger: { icon: ShieldAlert, cls: 'bg-red-950/60 border-red-800 text-red-300' },
  success: { icon: CheckCircle2, cls: 'bg-emerald-950/60 border-emerald-800 text-emerald-300' },
}

function money(v: number): string {
  return `€${(v || 0).toLocaleString('pt-PT', { maximumFractionDigits: 0 })}`
}

export default function CopilotBriefingCard() {
  const router = useRouter()
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const r = await apiFetch('/ai/copilot/briefing')
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
      setBriefing(data)
    } catch (e: any) {
      setError(e.message)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading && !briefing) {
    return (
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6 flex items-center gap-3 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
          O Copiloto está a compilar o briefing executivo…
        </CardContent>
      </Card>
    )
  }

  if (error && !briefing) {
    return (
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6 text-sm text-amber-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Briefing indisponível: {error}
        </CardContent>
      </Card>
    )
  }

  if (!briefing) return null
  const k = briefing.kpis

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-6 space-y-4">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-[0_0_15px_rgba(59,130,246,0.4)]">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-sm">Briefing IA — Copiloto Global</h3>
              <p className="text-[11px] text-slate-500">
                Snapshot executivo dos dados vivos da plataforma
              </p>
            </div>
          </div>
          <button onClick={load} disabled={loading}
            className="p-2 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-slate-800 disabled:opacity-40"
            title="Atualizar briefing">
            <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Kpi label="Transações" value={String(k.transactions_total)}
            sub={money(k.transactions_amount)} tone="text-blue-300" />
          <Kpi label="Alertas por resolver" value={String(k.open_alerts)}
            sub={`${k.critical_alerts} críticos`}
            tone={Number(k.critical_alerts) > 0 ? 'text-red-300' : 'text-emerald-300'} />
          <Kpi label="Casos abertos" value={String(k.cases_open)}
            sub={`${k.cases_overdue} fora do prazo`}
            tone={k.cases_overdue > 0 ? 'text-amber-300' : 'text-emerald-300'} />
          <Kpi label="Tendência de risco" value={k.trend.includes('alta') ? 'Alta' : k.trend.includes('baixa') ? 'Baixa' : 'Estável'}
            sub={k.benford_mad !== undefined && k.benford_mad !== null ? `Benford MAD ${k.benford_mad}` : '7 dias'}
            tone={k.trend.includes('alta') ? 'text-red-300' : 'text-emerald-300'} />
        </div>

        {/* Insights */}
        {briefing.insights.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {briefing.insights.slice(0, 4).map((ins, i) => {
              const tone = TONE_STYLE[ins.tone] || TONE_STYLE.info
              const Icon = tone.icon
              return (
                <div key={i} className={`rounded-xl border px-3 py-2.5 ${tone.cls}`}>
                  <div className="flex items-start gap-2">
                    <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-semibold">{ins.title}</p>
                      <p className="text-[11px] opacity-80 mt-0.5">{ins.detail}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Ações */}
        <div className="flex flex-wrap items-center gap-2">
          {briefing.actions.map((a, i) => (
            <button key={i} onClick={() => router.push(a.href)}
              className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium">
              {a.label} <ArrowRight className="w-3.5 h-3.5" />
            </button>
          ))}
          <span className="text-[11px] text-slate-500 ml-auto">
            Gerado {new Date(briefing.generated_at).toLocaleString('pt-PT')}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function Kpi({ label, value, sub, tone }: {
  label: string; value: string; sub?: string; tone: string
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 px-3.5 py-3">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className={`text-xl font-bold ${tone}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  )
}
