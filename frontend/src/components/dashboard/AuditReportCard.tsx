"use client"
// Cartão do Relatório Global de Auditoria — preview de KPIs + download do PDF premium
// com capa ilustrada opcional gerada por IA (FLUX.2-klein-4B).
import { useCallback, useEffect, useState } from 'react'
import { FileText, Download, ShieldCheck, TrendingUp, AlertTriangle, Sparkles, X } from 'lucide-react'
import { apiDownload, apiFetch } from '@/lib/api'

type Summary = {
  period: { from: string, to: string }
  kpis: {
    transactions: number
    transactions_value: number
    alerts: number
    alerts_by_severity: Record<string, number>
    cases_open: number
    sla_breaches: number
    benford_mad: number | null
    data_completeness: number
    trend_7d: string
  }
  recommendations: string[]
}

const nf = new Intl.NumberFormat('pt-PT')
const money = (v: number) =>
  'BRL ' + nf.format(Math.round(v * 100) / 100)

type Cover = { id: number, image: string, source?: string }

export function AuditReportCard() {
  const [s, setS] = useState<Summary | null>(null)
  const [busy, setBusy] = useState(false)
  const [coverBusy, setCoverBusy] = useState(false)
  const [cover, setCover] = useState<Cover | null>(null)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try {
      const r = await apiFetch('/reports/audit?days=30')
      if (r.status === 403) { setErr('requer papel auditor/admin'); return }
      if (!r.ok) { setErr(`erro ${r.status}`); return }
      setS(await r.json())
    } catch { setErr('sem ligação') }
  }, [])

  useEffect(() => { load() }, [load])

  async function generateCover() {
    setCoverBusy(true)
    setErr('')
    try {
      const r = await apiFetch('/reports/ai-cover', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: 30 }),
      })
      const d = await r.json()
      if (!r.ok) setErr(d?.error || `erro ${r.status}`)
      else setCover({ id: d.id, image: d.image, source: d.source })
    } catch { setErr('falha na capa IA') }
    finally { setCoverBusy(false) }
  }

  async function download() {
    setBusy(true)
    setErr('')
    try {
      const qs = cover ? `&cover=${cover.id}` : ''
      await apiDownload(`/reports/audit/pdf?days=30${qs}`, 'relatorio_auditoria.pdf')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'falha no download')
    } finally {
      setBusy(false)
    }
  }

  const k = s?.kpis
  const crit = (k?.alerts_by_severity?.Critical || 0) + (k?.alerts_by_severity?.critical || 0)

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800
                    p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600
                           flex items-center justify-center">
            <FileText className="w-5 h-5 text-white" />
          </span>
          <div>
            <h3 className="font-semibold text-slate-900 dark:text-white">Relatório de Auditoria</h3>
            <p className="text-xs text-slate-500">
              {s ? `Período: ${s.period.from} a ${s.period.to}` : 'A carregar resumo…'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={generateCover} disabled={coverBusy}
                  title="Gerar capa ilustrada com IA (FLUX)"
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-indigo-300 dark:border-indigo-700
                             text-indigo-600 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30
                             disabled:opacity-50 text-sm font-medium transition-colors">
            {coverBusy ? <Sparkles className="w-4 h-4 animate-pulse" /> : <Sparkles className="w-4 h-4" />}
            {coverBusy ? 'A gerar capa…' : 'Capa IA'}
          </button>
          <button onClick={download} disabled={busy}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700
                             disabled:opacity-50 text-white text-sm font-medium transition-colors">
            <Download className="w-4 h-4" />
            {busy ? 'A gerar…' : 'Descarregar PDF'}
          </button>
        </div>
      </div>

      {cover && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-indigo-50/50 dark:bg-indigo-950/30 p-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={cover.image} alt="Capa gerada por IA" className="w-24 h-16 object-cover rounded-lg border border-slate-200 dark:border-slate-700" />
          <div className="flex-1">
            <p className="text-xs font-medium text-slate-700 dark:text-slate-200">Capa IA pronta</p>
            <p className="text-[11px] text-slate-500">A capa entra no PDF ao descarregar{cover.source === 'db' ? ' · motor BD' : ''}.</p>
          </div>
          <button onClick={() => setCover(null)} className="text-slate-400 hover:text-slate-600" title="Remover capa">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {err && (
        <p className="mt-3 text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5" /> {err}
        </p>
      )}

      {k && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            {[
              { label: 'Transações', value: nf.format(k.transactions), icon: FileText },
              { label: 'Alertas críticos', value: nf.format(crit), icon: AlertTriangle },
              { label: 'Casos abertos', value: nf.format(k.cases_open), icon: ShieldCheck },
              { label: 'Tendência 7d', value: k.trend_7d, icon: TrendingUp },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label}
                   className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3 border border-slate-100 dark:border-slate-700">
                <div className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                  <Icon className="w-3.5 h-3.5" /> {label}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-0.5">{value}</div>
              </div>
            ))}
          </div>

          {s?.recommendations?.length > 0 && (
            <ul className="mt-4 space-y-1.5">
              {s.recommendations.slice(0, 3).map((r, i) => (
                <li key={i} className="text-xs text-slate-600 dark:text-slate-300 flex gap-2">
                  <span className="text-blue-500 font-bold">•</span> {r}
                </li>
              ))}
            </ul>
          )}

          {k.benford_mad != null && (
            <p className="mt-3 text-[11px] text-slate-400">
              Benford MAD: {k.benford_mad.toFixed(4)} — {k.benford_mad <= 0.015 ? 'dentro' : 'acima'} do
              limiar de conformidade (0,015) · completude dos dados: {k.data_completeness}%
            </p>
          )}
        </>
      )}
    </div>
  )
}

export default AuditReportCard
