"use client"
// Painel Auto (Studio) — experiência simples, fácil e direta (método REA,
// passo 5: "ir além"). Um clique: o motor faz engenharia reversa dos dados,
// deduz dimensões/medidas e devolve um painel completo — KPIs, insights
// narrativos, 6 visuais e drillthrough — sem qualquer configuração.
// Utilizadores avançados continuam com o BI Studio (/bi).
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BarChart, PieChart, ComposedChart,
  Bar, Line, Pie, Cell, Area, Scatter, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer,
} from 'recharts'
import {
  Sparkles, Lightbulb, Download, Loader2, RefreshCw, Filter, X,
  FileSpreadsheet, BarChart3, Inbox,
} from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

const COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#ea580c', '#16a34a',
  '#dc2626', '#d97706', '#4f46e5', '#0d9488', '#be185d']

type Row = Record<string, any>
type AutoPayload = {
  empty: boolean, kpis: Row[], visuals: Row, insights: string[],
  recent: Row[], meta: Row,
}

const fmt = (v: any) => {
  const n = Number(v)
  if (!isFinite(n)) return '—'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + 'k'
  if (Math.abs(n) < 10 && n % 1 !== 0) return n.toFixed(2)
  return n.toFixed(0)
}

const btn = "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50"
const btnP = `${btn} bg-blue-600 hover:bg-blue-700 text-white`
const btnS = `${btn} border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800`
const card = "bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm"
const chip = "px-3 py-1.5 rounded-full text-xs font-medium border transition-colors cursor-pointer"
const chipOn = `${chip} bg-blue-600 border-blue-600 text-white`
const chipOff = `${chip} border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800`

const PERIODS = [
  { key: 'all', label: 'Tudo' },
  { key: 'year', label: 'Este ano' },
  { key: '90', label: '90 dias' },
  { key: '30', label: '30 dias' },
]

export default function StudioPage() {
  useRequireToken()
  const [period, setPeriod] = useState('all')
  const [vendorSel, setVendorSel] = useState('')
  const [data, setData] = useState<AutoPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const filters = useMemo(() => {
    const f: Row[] = []
    if (period === '30' || period === '90') {
      const d = new Date(Date.now() - Number(period) * 86400000)
      f.push({ field: 'date', op: 'gte', value: d.toISOString().slice(0, 10) })
    } else if (period === 'year') {
      f.push({ field: 'date', op: 'gte', value: `${new Date().getFullYear()}-01-01` })
    }
    if (vendorSel) f.push({ field: 'vendor', op: 'eq', value: vendorSel })
    return f
  }, [period, vendorSel])

  const generate = useCallback(async (silent = false) => {
    if (!silent) { setBusy(true) }
    setErr('')
    try {
      const r = await apiFetch('/bi/auto', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filters }),
      })
      const d = await r.json()
      if (!r.ok) { setErr(d.error || `erro ${r.status}`); return }
      setData(d)
    } catch { setErr('falha ao gerar o painel') } finally { setBusy(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  // primeira carga automática — zero cliques quando já existem dados
  useEffect(() => { generate(true) /* eslint-disable-line react-hooks/exhaustive-deps */ }, [])

  // regenera ao mudar slicers (depois da carga inicial)
  const firstRun = useMemo(() => ({ done: false }), [])
  useEffect(() => {
    if (!firstRun.done) { firstRun.done = true; return }
    generate(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  async function exportXlsx(kind: string, vis: Row, title: string) {
    if (!vis) return
    try {
      const r = await apiFetch('/bi/export/xlsx', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, data: vis, title, subtitle: 'Painel Auto' }),
      })
      if (!r.ok) { const d = await r.json(); setErr(d.error || `erro ${r.status}`); return }
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `painel-${kind}-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click(); URL.revokeObjectURL(url)
    } catch { setErr('falha na exportação') }
  }

  const barV = data?.visuals?.bar
  const pieV = data?.visuals?.pie
  const seriesV = data?.visuals?.series
  const paretoV = data?.visuals?.pareto
  const anomalyV = data?.visuals?.anomaly
  const forecastV = data?.visuals?.forecast
  const d1 = barV?.dimension || 'vendor'

  const crow = useMemo(() => {
    if (forecastV) {
      const h = (forecastV.data.history || []).map((r: Row) => ({ key: r.key, value: r.value, low: null, up: null }))
      const f = (forecastV.data.forecast || []).map((r: Row) => ({ key: r.key, value: r.value, low: r.lower, up: r.upper }))
      return [...h, ...f]
    }
    if (anomalyV) return (anomalyV.data.rows || []).map((r: Row) => ({ ...r, anom: r.anomaly ? r.value : null }))
    return (seriesV?.data.rows || []).map((r: Row) => ({ ...r, mv: r.moving_avg }))
  }, [forecastV, anomalyV, seriesV])

  const crowName = forecastV ? 'Projeção 3 meses' : anomalyV ? 'Anomalias mensais' : 'Evolução mensal'

  function clickSlicer(value: string) {
    if (!value) return
    setVendorSel(vendorSel === value ? '' : value)
  }

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ cabeçalho */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-blue-600" /> Painel Auto
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Um clique: o motor REA analisa os seus dados e monta o painel completo — KPIs, tendências, Pareto, anomalias e projeção.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <button className={btnP} onClick={() => generate()} disabled={busy}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Gerar painel
          </button>
          {data && !data.empty && (
            <>
              <button className={btnS} onClick={() => barV && exportXlsx('group', barV.data, `Volume por ${d1}`)}>
                <Download className="w-3.5 h-3.5" /> Volume (.xlsx)
              </button>
              <button className={btnS} onClick={() => seriesV && exportXlsx('series', seriesV.data, 'Evolução mensal')}>
                <Download className="w-3.5 h-3.5" /> Série (.xlsx)
              </button>
            </>
          )}
          <a className={btnS} href="/bi">
            <BarChart3 className="w-3.5 h-3.5" /> Modo avançado
          </a>
        </div>
      </div>

      {/* ------------------------------------------------- slicers */}
      <div className={`${card} flex flex-wrap items-center gap-2`}>
        <Filter className="w-3.5 h-3.5 text-slate-400" />
        {PERIODS.map(p => (
          <button key={p.key} className={period === p.key ? chipOn : chipOff}
                  onClick={() => setPeriod(p.key)}>{p.label}</button>
        ))}
        {vendorSel && (
          <span className={chipOn}>
            {vendorSel}
            <button onClick={() => setVendorSel('')} className="ml-1.5 inline-flex">
              <X className="w-3 h-3" />
            </button>
          </span>
        )}
        {data?.meta?.records ? (
          <span className="text-[11px] text-slate-400 ml-auto">
            {data.meta.records} transações {data.meta.period?.start ? `· ${data.meta.period.start} → ${data.meta.period.end}` : ''}
          </span>
        ) : null}
      </div>

      {err && <p className="text-sm text-red-500">{err}</p>}
      {busy && !data && (
        <div className={`${card} flex items-center gap-2 text-sm text-slate-500`}>
          <Loader2 className="w-4 h-4 animate-spin" /> A analisar os seus dados…
        </div>
      )}

      {/* ------------------------------------------------- vazio */}
      {data?.empty && !busy && (
        <div className={`${card} text-center py-12`}>
          <Inbox className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="text-sm text-slate-500 mb-4">
            {data.insights[0]}
          </p>
          <a className={btnP} href="/excel">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Importar Excel agora
          </a>
        </div>
      )}

      {/* ------------------------------------------------- KPIs */}
      {data && !data.empty && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {data.kpis.map((k: Row) => (
            <div key={k.key} className={card}>
              <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{k.label}</p>
              <p className="text-xl font-bold text-gray-800 dark:text-white mt-1 truncate" title={String(k.value)}>
                {k.format === 'currency' ? fmt(k.value) : k.format === 'int' ? fmt(k.value) : String(k.value ?? '—')}
              </p>
              {k.detail && <p className="text-[11px] text-blue-600 mt-0.5">{k.detail}</p>}
            </div>
          ))}
        </div>
      )}

      {/* ------------------------------------------------- insights */}
      {data && !data.empty && data.insights.length > 0 && (
        <div className={`${card} border-l-4 !border-l-amber-400`}>
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1.5 mb-2">
            <Lightbulb className="w-3.5 h-3.5 text-amber-500" /> O que os dados dizem
          </p>
          <ul className="space-y-1.5">
            {data.insights.map((s: string, i: number) => (
              <li key={i} className="text-sm text-gray-700 dark:text-slate-300 flex gap-2">
                <span className="text-amber-500">•</span> {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ------------------------------------------------- bar + pie */}
      {barV && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className={card}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold text-gray-700 dark:text-slate-200">{barV.title}</p>
              <span className="text-[10px] text-slate-400">clique para filtrar</span>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barV.data.rows} onClick={(e: any) => e?.activeLabel && clickSlicer(String(e.activeLabel))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                <XAxis dataKey={d1} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
                <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v: any) => fmt(v)} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {barV.data.rows.map((r: Row, i: number) => (
                    <Cell key={i} fill={vendorSel === r[d1] ? '#1d4ed8' : COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {pieV && (
            <div className={card}>
              <p className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">{pieV.title}</p>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={pieV.data.rows} dataKey="value" nameKey={pieV.dimension} outerRadius={110}
                       onClick={(e: any) => e?.name && pieV.dimension === 'vendor' && clickSlicer(String(e.name))}>
                    {pieV.data.rows.map((_: Row, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v: any) => fmt(v)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------- série / anomalias / projeção */}
      {crow.length > 0 && (
        <div className={card}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-700 dark:text-slate-200">{crowName}</p>
            {anomalyV?.data?.n_anomalies > 0 && (
              <span className="text-[11px] font-medium text-red-500">
                {anomalyV.data.n_anomalies} anomalia(s) detetada(s)
              </span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={crow}>
              <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
              <XAxis dataKey="key" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={50} />
              <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v: any) => (v == null ? '—' : fmt(v))} />
              <Legend />
              {forecastV && <Area dataKey="low" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.15} name="intervalo" />}
              {forecastV && <Area dataKey="up" stroke="none" fill="transparent" name="" />}
              <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }}
                    name={forecastV ? 'histórico + projeção' : 'valor'} />
              {!forecastV && <Line type="monotone" dataKey="mv" stroke="#7c3aed" strokeDasharray="5 3" dot={false} name="média móvel" />}
              {anomalyV && <Scatter dataKey="anom" fill="#dc2626" name="anomalia" shape="circle" />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ------------------------------------------------- pareto */}
      {paretoV && paretoV.data.rows.length > 0 && (
        <div className={card}>
          <p className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
            {paretoV.title}
            <span className="ml-2 text-[11px] font-normal text-slate-400">
              {paretoV.data.n_vital_few} de {paretoV.data.n_total_groups} explicam 80%
            </span>
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={paretoV.data.rows} onClick={(e: any) => e?.activeLabel && clickSlicer(String(e.activeLabel))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
              <XAxis dataKey={d1} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
              <YAxis yAxisId="l" tickFormatter={fmt} tick={{ fontSize: 10 }} />
              <YAxis yAxisId="r" orientation="right" tickFormatter={(v: any) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v: any, n: any) => n === 'cum_share' ? `${(v * 100).toFixed(1)}%` : fmt(v)} />
              <Legend />
              <Bar yAxisId="l" dataKey="value" name="Valor">
                {paretoV.data.rows.map((r: Row, i: number) => (
                  <Cell key={i} fill={r.vital_few ? '#2563eb' : '#94a3b8'} />
                ))}
              </Bar>
              <Line yAxisId="r" type="monotone" dataKey="cum_share" name="Acumulado" stroke="#dc2626" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ------------------------------------------------- transações recentes */}
      {data && !data.empty && data.recent.length > 0 && (
        <div className={card}>
          <p className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">Transações recentes</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-200 dark:border-slate-700">
                  <th className="py-1.5 pr-3 font-medium">ID</th>
                  <th className="py-1.5 pr-3 font-medium">Fornecedor</th>
                  <th className="py-1.5 pr-3 font-medium">Categoria</th>
                  <th className="py-1.5 pr-3 font-medium">Estado</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Valor</th>
                  <th className="py-1.5 font-medium text-right">Data</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((r: Row, i: number) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800 last:border-0">
                    <td className="py-1.5 pr-3 font-mono text-slate-500">{String(r.transaction_id || '').slice(0, 18)}</td>
                    <td className="py-1.5 pr-3">{r.vendor}</td>
                    <td className="py-1.5 pr-3">{r.category}</td>
                    <td className="py-1.5 pr-3">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${r.status === 'Completed' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-right font-semibold">{fmt(r.amount)} {r.currency}</td>
                    <td className="py-1.5 text-right text-slate-500">{r.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
