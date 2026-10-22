"use client"
// BI Studio — Power BI parity (metodologia REA): medidor DAX-like, Matrix,
// Pareto, Decomposition Tree, What-if, Drillthrough, Pipelines ETL e RLS.
// v2: Relatórios com cross-filtering, Q&A em linguagem natural, séries com
// média móvel, forecast, anomalias, waterfall, funil, KPI, alertas e export Excel.
import { useCallback, useEffect, useState } from 'react'
import {
  BarChart, LineChart, PieChart, ComposedChart,
  Bar, Line, Pie, Cell, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer, Area, Scatter,
} from 'recharts'
import {
  BarChart3, Save, Trash2, Play, Filter, ListTree,
  SlidersHorizontal, ShieldCheck, Workflow, Loader2, Layers, Table2,
  LayoutDashboard, Bell, Download, Sparkles, Pin, RefreshCw, Send,
} from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

const COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#ea580c', '#16a34a',
  '#dc2626', '#d97706', '#4f46e5', '#0d9488', '#be185d']

type Meta = { dimensions: string[], fields: string[], aggregations: string[], ops: string[] }
type Measure = { id: number, name: string, description: string, expression: any }
type Row = Record<string, any>

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
const input = "px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm w-full"
const sel = `${input} py-1.5`
const card = "bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm"
const label = "text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1 block"

export default function BIStudioPage() {
  useRequireToken()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [role, setRole] = useState('')
  const [tab, setTab] = useState<'explorer' | 'reports' | 'pipelines' | 'rls' | 'alerts'>('explorer')

  // --- medida
  const [agg, setAgg] = useState('sum')
  const [field, setField] = useState('amount')
  const [wrapMode, setWrapMode] = useState<'plain' | 'pct_of_total' | 'running_total' | 'yoy'>('plain')
  const [filters, setFilters] = useState<Row[]>([])
  const [fField, setFField] = useState('vendor')
  const [fOp, setFOp] = useState('eq')
  const [fVal, setFVal] = useState('')

  // --- visual
  const [visual, setVisual] = useState<'bar' | 'line' | 'pie' | 'pareto' | 'matrix' | 'decompose' | 'whatif' | 'waterfall' | 'funnel' | 'kpi' | 'series' | 'anomaly' | 'forecast'>('bar')
  const [dataKind, setDataKind] = useState<string>('')
  const [dimension, setDimension] = useState('vendor')
  const [rowDim, setRowDim] = useState('vendor')
  const [colDim, setColDim] = useState('month')
  const [decompDims, setDecompDims] = useState<string[]>(['vendor', 'category'])
  const [whatPct, setWhatPct] = useState(10)
  const [granularity, setGranularity] = useState('month')
  const [kpiTarget, setKpiTarget] = useState('')
  const [anomalyZ, setAnomalyZ] = useState('2.5')
  const [forecastPeriods, setForecastPeriods] = useState('3')
  const [data, setData] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [drill, setDrill] = useState<Row[] | null>(null)

  // --- Q&A (Pergunte aos dados)
  const [qText, setQText] = useState('')
  const [qaRes, setQaRes] = useState<any>(null)
  const [qaBusy, setQaBusy] = useState(false)

  // --- relatórios guardados (dashboards)
  const [dashes, setDashes] = useState<Row[]>([])
  const [dashName, setDashName] = useState('')
  const [dashResult, setDashResult] = useState<any>(null)
  const [crossFilters, setCrossFilters] = useState<Row[]>([])

  // --- alertas de medidas
  const [alerts, setAlerts] = useState<Row[]>([])
  const [alertName, setAlertName] = useState('')
  const [alertCmp, setAlertCmp] = useState('gt')
  const [alertTh, setAlertTh] = useState('')
  const [alertRun, setAlertRun] = useState<any>(null)

  // --- medidas guardadas
  const [measures, setMeasures] = useState<Measure[]>([])
  const [mName, setMName] = useState('')

  // --- pipelines
  const [pipes, setPipes] = useState<Row[]>([])
  const [pipeName, setPipeName] = useState('')
  const [pipeSteps, setPipeSteps] = useState(JSON.stringify([
    { op: 'map_columns' },
    { op: 'trim_text' },
    { op: 'dedupe', subset: ['transaction_id'] },
  ], null, 1))
  const [pipeFile, setPipeFile] = useState<File | null>(null)
  const [pipeResult, setPipeResult] = useState<any>(null)

  // --- RLS
  const [rules, setRules] = useState<Row[]>([])
  const [rlsName, setRlsName] = useState('')
  const [rlsTarget, setRlsTarget] = useState('')
  const [rlsIsRole, setRlsIsRole] = useState(false)
  const [rlsDim, setRlsDim] = useState('vendor')
  const [rlsValues, setRlsValues] = useState('')

  const loadMeta = useCallback(async () => {
    const [mr, pr, rr, gr, dr, ar] = await Promise.all([
      apiFetch('/bi/meta'), apiFetch('/bi/pipelines'), apiFetch('/bi/rls'),
      apiFetch('/bi/measures'), apiFetch('/bi/dashboards'), apiFetch('/bi/alerts')])
    if (mr.ok) setMeta(await mr.json())
    if (pr.ok) setPipes((await pr.json()).results || [])
    if (rr.ok) setRules((await rr.json()).results || [])
    if (gr.ok) setMeasures((await gr.json()).results || [])
    if (dr.ok) setDashes((await dr.json()).results || [])
    if (ar.ok) setAlerts((await ar.json()).results || [])
    setRole(localStorage.getItem('user_role') || '')
  }, [])

  useEffect(() => { loadMeta() }, [loadMeta])

  function measure(): any {
    let m: any = { op: 'agg', agg, field }
    if (wrapMode === 'pct_of_total') m = { op: 'pct_of_total', measure: m }
    else if (wrapMode === 'running_total') m = { op: 'running_total', measure: m }
    else if (wrapMode === 'yoy') m = { op: 'yoy', measure: m }
    return m
  }

  function buildBody(extra: Row = {}) {
    return { measure: measure(), filters, ...extra }
  }

  async function render() {
    setBusy(true); setErr(''); setDrill(null)
    try {
      let r: Response
      let kind = visual
      if (visual === 'matrix') {
        r = await apiFetch('/bi/matrix', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ rows: rowDim, cols: colDim })) })
      } else if (visual === 'pareto') {
        r = await apiFetch('/bi/pareto', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimension })) })
      } else if (visual === 'decompose') {
        r = await apiFetch('/bi/decompose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimensions: decompDims })) })
      } else if (visual === 'whatif') {
        r = await apiFetch('/bi/whatif', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ adjustment_pct: whatPct })) })
      } else if (visual === 'waterfall') {
        r = await apiFetch('/bi/waterfall', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimension })) })
      } else if (visual === 'funnel') {
        r = await apiFetch('/bi/funnel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimension })) })
      } else if (visual === 'kpi') {
        r = await apiFetch('/bi/kpi', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ target: kpiTarget === '' ? null : Number(kpiTarget) })) })
      } else if (visual === 'series') {
        r = await apiFetch('/bi/series', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ granularity })) })
      } else if (visual === 'anomaly') {
        r = await apiFetch('/bi/anomaly', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ granularity, z_threshold: Number(anomalyZ) || 2.5 })) })
      } else if (visual === 'forecast') {
        r = await apiFetch('/bi/forecast', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ granularity, periods: Number(forecastPeriods) || 3 })) })
      } else if (visual === 'pie') {
        r = await apiFetch('/bi/group', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimension, top_n: 8, mode: 'pct_of_total' })) })
      } else {
        r = await apiFetch('/bi/group', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody({ dimension, top_n: 20 })) })
      }
      const d = await r.json()
      if (!r.ok) setErr(d.error || `erro ${r.status}`)
      else { setData(d); setDataKind(kind) }
    } catch { setErr('sem ligação ao motor BI') } finally { setBusy(false) }
  }

  async function exportXlsx() {
    if (!data) return
    setBusy(true); setErr('')
    try {
      const r = await apiFetch('/bi/export/xlsx', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: dataKind === 'bar' || dataKind === 'line' || dataKind === 'pie' ? 'group' : dataKind, data, title: `BI — ${visual}`, subtitle: `dimensão: ${dimension}` }) })
      if (!r.ok) { const d = await r.json(); setErr(d.error || `erro ${r.status}`); return }
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `bi-${visual}-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click(); URL.revokeObjectURL(url)
    } catch { setErr('falha na exportação') } finally { setBusy(false) }
  }

  async function askQA() {
    if (!qText.trim()) return
    setQaBusy(true); setErr('')
    try {
      const r = await apiFetch('/bi/qa', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: qText }) })
      const d = await r.json()
      if (!r.ok) setErr(d.error || `erro ${r.status}`)
      else setQaRes(d)
    } catch { setErr('sem ligação ao Q&A') } finally { setQaBusy(false) }
  }

  async function createDashboard() {
    if (!dashName.trim() || !data) return
    const spec: Row = { id: 'v1', kind: visual, measure: measure(), dimension, filters, title: `${visual} · ${dimension}` }
    if (visual === 'kpi') spec.target = kpiTarget === '' ? null : Number(kpiTarget)
    if (['series', 'anomaly', 'forecast'].includes(visual)) spec.granularity = granularity
    if (visual === 'forecast') spec.periods = Number(forecastPeriods) || 3
    if (visual === 'anomaly') spec.z_threshold = Number(anomalyZ) || 2.5
    const r = await apiFetch('/bi/dashboards', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: dashName.trim(), description: 'criado a partir do Explorador', config: { visuals: [spec], slicers: [] } }) })
    const d = await r.json()
    if (!r.ok) setErr(d.error || 'erro ao guardar relatório')
    else { setDashName(''); loadMeta() }
  }

  async function runDashboard(id: number, extra: Row[] = []) {
    setBusy(true); setErr('')
    try {
      const r = await apiFetch(`/bi/dashboards/${id}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cross_filters: extra }) })
      const d = await r.json()
      if (!r.ok) setErr(d.error || `erro ${r.status}`)
      else { setDashResult(d); setCrossFilters(extra) }
    } catch { setErr('sem ligação ao relatório') } finally { setBusy(false) }
  }

  async function delDashboard(id: number) {
    await apiFetch(`/bi/dashboards/${id}`, { method: 'DELETE' })
    if (dashResult?.dashboard && dashes.find(d0 => d0.id === id)?.name === dashResult.dashboard) setDashResult(null)
    loadMeta()
  }

  async function createAlert() {
    const th = Number(alertTh)
    if (!alertName.trim() || !isFinite(th)) { setErr('alerta: nome e limiar numérico obrigatórios'); return }
    const r = await apiFetch('/bi/alerts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: alertName.trim(), measure: measure(), comparator: alertCmp, threshold: th, filters }) })
    const d = await r.json()
    if (!r.ok) setErr(d.error || 'erro ao criar alerta')
    else { setAlertName(''); setAlertTh(''); loadMeta() }
  }

  async function toggleAlert(a0: Row) {
    await apiFetch(`/bi/alerts/${a0.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: !a0.active }) })
    loadMeta()
  }

  async function delAlert(id: number) { await apiFetch(`/bi/alerts/${id}`, { method: 'DELETE' }); loadMeta() }

  async function runAlerts() {
    setBusy(true); setErr('')
    try {
      const r = await apiFetch('/bi/alerts/run', { method: 'POST' })
      const d = await r.json()
      if (!r.ok) setErr(d.error || `erro ${r.status}`)
      else { setAlertRun(d); loadMeta() }
    } catch { setErr('sem ligação') } finally { setBusy(false) }
  }

  async function drillThrough(dim: string, val: string) {
    const r = await apiFetch('/bi/drillthrough', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filters: [...filters, { field: dim, op: 'eq', value: val }], dimension: dim, value: val }) })
    if (r.ok) setDrill((await r.json()).rows || [])
  }

  async function saveMeasure() {
    if (!mName.trim()) return
    const r = await apiFetch('/bi/measures', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: mName.trim(), expression: measure() }) })
    const d = await r.json()
    if (!r.ok) setErr(d.error || 'erro ao guardar')
    else { setMName(''); loadMeta() }
  }

  async function delMeasure(id: number) {
    await apiFetch(`/bi/measures/${id}`, { method: 'DELETE' }); loadMeta()
  }

  async function createPipeline() {
    let steps: any
    try { steps = JSON.parse(pipeSteps) } catch { setErr('JSON dos passos inválido'); return }
    const r = await apiFetch('/bi/pipelines', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: pipeName.trim(), steps }) })
    const d = await r.json()
    if (!r.ok) setErr(d.error || 'erro'); else { setPipeName(''); loadMeta() }
  }

  async function runPipeline(id: number) {
    if (!pipeFile) { setErr('escolha um ficheiro para executar'); return }
    setBusy(true); setErr(''); setPipeResult(null)
    const fd = new FormData()
    fd.append('file', pipeFile)
    const r = await apiFetch(`/bi/pipelines/${id}/run?import=true`, { method: 'POST', body: fd })
    const d = await r.json()
    if (!r.ok) setErr(d.error || `erro ${r.status}`); else setPipeResult(d)
    setBusy(false)
  }

  async function delPipeline(id: number) { await apiFetch(`/bi/pipelines/${id}`, { method: 'DELETE' }); loadMeta() }

  async function createRule() {
    const body: Row = {
      name: rlsName.trim() || `RLS ${rlsDim}`, dimension: rlsDim,
      allowed_values: rlsValues.split(',').map(s => s.trim()).filter(Boolean),
    }
    if (rlsIsRole) body.role = rlsTarget.trim(); else body.user_id = rlsTarget.trim()
    const r = await apiFetch('/bi/rls', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const d = await r.json()
    if (!r.ok) setErr(d.error || 'erro'); else { setRlsName(''); setRlsValues(''); loadMeta() }
  }

  async function toggleRule(r0: Row) {
    await apiFetch(`/bi/rls/${r0.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: !r0.active }) })
    loadMeta()
  }
  async function delRule(id: number) { await apiFetch(`/bi/rls/${id}`, { method: 'DELETE' }); loadMeta() }

  // ------------------------------------------------ renderização de visuais
  const rows: Row[] = data?.rows || []

  function renderVisual() {
    if (err) return <p className="text-sm text-amber-600 dark:text-amber-400">{err}</p>
    if (busy) return <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="w-4 h-4 animate-spin" /> a avaliar…</div>
    if (!data) return <p className="text-sm text-slate-400">Configure a medida e clique <b>Avaliar</b>.</p>

    if (visual === 'matrix') {
      const cols: string[] = data.columns || []
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="bg-slate-100 dark:bg-slate-800">
              <th className="p-2 text-left">{data.row_dim}</th>
              {cols.map(c => <th key={c} className="p-2 text-right">{c}</th>)}
              <th className="p-2 text-right font-bold">Total</th>
            </tr></thead>
            <tbody>
              {data.rows.map((r: Row) => (
                <tr key={r.row} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="p-2 font-medium cursor-pointer text-blue-600" onClick={() => drillThrough(data.row_dim, r.row)}>{r.row}</td>
                  {cols.map(c => <td key={c} className="p-2 text-right">{fmt(r[c])}</td>)}
                  <td className="p-2 text-right font-semibold">{fmt(r.total)}</td>
                </tr>))}
              <tr className="bg-slate-50 dark:bg-slate-800 font-semibold">
                <td className="p-2">Total</td>
                {cols.map(c => <td key={c} className="p-2 text-right">{fmt(data.col_totals?.[c])}</td>)}
                <td className="p-2 text-right">{fmt(data.grand_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )
    }

    if (visual === 'decompose') {
      return (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">Raiz: <b className="text-slate-800 dark:text-slate-200">{fmt(data.root_value)}</b> — contribuição por nível (clique para drillthrough)</p>
          {data.tree.map((lvl: any) => (
            <div key={lvl.level}>
              <p className={label}>{lvl.dimension}</p>
              <div className="flex flex-wrap gap-2">
                {lvl.children.map((c: any, i: number) => (
                  <button key={i} onClick={() => drillThrough(lvl.dimension, c.filters[lvl.level]?.value || '')}
                          className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-blue-400 text-left">
                    <span className="block text-xs font-semibold text-slate-800 dark:text-slate-200">{c.filters[lvl.level]?.value}</span>
                    <span className="block text-[11px] text-slate-500">{fmt(c.value)} · {(c.pct_of_parent * 100).toFixed(1)}%</span>
                  </button>))}
              </div>
            </div>))}
        </div>
      )
    }

    if (visual === 'whatif') {
      return (
        <div className="grid grid-cols-3 gap-3 text-center py-4">
          {[['Base', data.base, 'text-slate-700 dark:text-slate-200'],
            [`Ajustado (${data.adjustment_pct > 0 ? '+' : ''}${data.adjustment_pct}%)`, data.adjusted, 'text-blue-600'],
            ['Delta', data.delta, data.delta >= 0 ? 'text-emerald-600' : 'text-red-600']].map(([t, v, c]) => (
            <div key={t as string} className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-4">
              <p className="text-[11px] text-slate-500">{t}</p>
              <p className={`text-xl font-bold ${c}`}>{fmt(v)}</p>
            </div>))}
        </div>
      )
    }

    if (dataKind === 'kpi' && visual === 'kpi') {
      const st = data.status || ''
      const stColor = st === 'on_track' ? 'text-emerald-600' : st === 'warn' ? 'text-amber-500' : st === 'critical' ? 'text-red-600' : 'text-slate-700 dark:text-slate-200'
      return (
        <div className="py-6 space-y-4">
          <div className="text-center">
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">Valor da medida</p>
            <p className={`text-4xl font-bold ${stColor}`}>{fmt(data.value)}</p>
            {data.target != null && (<p className="text-xs text-slate-500 mt-1">alvo {fmt(data.target)} · {(100 * (data.pct_of_target || 0)).toFixed(1)}% do alvo</p>)}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3"><p className="text-[11px] text-slate-500">Últimos 30d</p><p className="text-lg font-semibold">{fmt(data.current_30d)}</p></div>
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3"><p className="text-[11px] text-slate-500">30d anteriores</p><p className="text-lg font-semibold">{fmt(data.previous_30d)}</p></div>
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800/60 p-3"><p className="text-[11px] text-slate-500">Tendência</p><p className={`text-lg font-semibold ${(data.trend_30d || 0) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>{data.trend_30d == null ? '—' : `${(100 * data.trend_30d).toFixed(1)}%`}</p></div>
          </div>
        </div>
      )
    }

    if (dataKind === 'waterfall') {
      const wrows = (data.rows || []).map((r: Row) => ({ ...r, delta: r.value }))
      return (
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={wrows} onClick={(e: any) => e?.activeLabel && drillThrough(dimension, e.activeLabel)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey={dimension} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={70} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: any) => fmt(v)} />
            <Legend />
            <Bar dataKey="base" stackId="w" fill="transparent" name="base" />
            <Bar dataKey="delta" stackId="w" radius={[4, 4, 0, 0]} name="contribuição">
              {wrows.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )
    }

    if (dataKind === 'funnel') {
      return (
        <div className="space-y-2 py-2">
          {(data.rows || []).map((r: Row, i: number) => (
            <button key={i} onClick={() => drillThrough(dimension, r[dimension] || r.dimension)} className="w-full text-left group">
              <div className="flex items-center gap-2">
                <span className="w-6 text-[11px] text-slate-400">#{r.stage}</span>
                <div className="flex-1 h-8 rounded-lg bg-blue-600 group-hover:bg-blue-700 transition-colors" style={{ width: `${Math.max(12, 100 * (r.pct_of_first || 0))}%`, maxWidth: '100%' }}>
                  <span className="pl-2 text-[11px] leading-8 text-white font-medium">{r[dimension] || r.dimension} · {fmt(r.value)}</span>
                </div>
                <span className="text-[11px] text-slate-500 w-24 text-right">{r.stage > 1 ? `conv ${(100 * (r.conv_prev || 0)).toFixed(0)}%` : '100%'}</span>
              </div>
            </button>))}
          {(!data.rows || !data.rows.length) && <p className="text-sm text-slate-400">sem dados</p>}
        </div>
      )
    }

    if (dataKind === 'series' || dataKind === 'anomaly' || dataKind === 'forecast') {
      let crow: Row[] = data.rows || []
      if (dataKind === 'forecast') {
        const h = (data.history || []).map((r: Row) => ({ key: r.key, value: r.value, mv: null, low: null, up: null }))
        const f = (data.forecast || []).map((r: Row) => ({ key: r.key, value: r.value, mv: null, low: r.lower, up: r.upper }))
        crow = [...h, ...f]
      } else if (dataKind === 'anomaly') {
        crow = (data.rows || []).map((r: Row) => ({ ...r, mv: r.moving_avg, anom: r.anomaly ? r.value : null }))
      } else {
        crow = crow.map((r: Row) => ({ ...r, mv: r.moving_avg }))
      }
      return (
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={crow} onClick={(e: any) => e?.activeLabel && drillThrough(dimension, e.activeLabel)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey="key" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: any) => (v == null ? '—' : fmt(v))} />
            <Legend />
            {dataKind === 'forecast' && <Area dataKey="low" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.15} name="intervalo" />}
            {dataKind === 'forecast' && <Area dataKey="up" stroke="none" fill="transparent" name="" />}
            <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} name={dataKind === 'forecast' ? 'histórico + projeção' : 'valor'} />
            {dataKind !== 'forecast' && <Line type="monotone" dataKey="mv" stroke="#7c3aed" strokeDasharray="5 3" dot={false} name={dataKind === 'series' ? 'média móvel' : ''} />}
            {dataKind === 'anomaly' && <Scatter dataKey="anom" fill="#dc2626" name="anomalia" shape="circle" />}
          </ComposedChart>
        </ResponsiveContainer>
      )
    }

    if (visual === 'pareto') {
      return (
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={rows} onClick={(e: any) => e?.activeLabel && drillThrough(dimension, e.activeLabel)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey={dimension} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={70} />
            <YAxis yAxisId="l" tickFormatter={fmt} tick={{ fontSize: 10 }} />
            <YAxis yAxisId="r" orientation="right" tickFormatter={(v: any) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: any, n: any) => n === 'cum_share' ? `${(v * 100).toFixed(1)}%` : fmt(v)} />
            <Legend />
            <Bar yAxisId="l" dataKey="value" name="Valor">
              {rows.map((r, i) => <Cell key={i} fill={r.vital_few ? '#2563eb' : '#94a3b8'} />)}
            </Bar>
            <Line yAxisId="r" type="monotone" dataKey="cum_share" name="Acumulado" stroke="#dc2626" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      )
    }

    if (visual === 'line') {
      return (
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={rows} onClick={(e: any) => e?.activeLabel && drillThrough(dimension, e.activeLabel)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey={dimension} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={70} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: any) => fmt(v)} />
            <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      )
    }

    if (visual === 'pie') {
      return (
        <ResponsiveContainer width="100%" height={340}>
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey={dimension} outerRadius={120}
                 onClick={(e: any) => drillThrough(dimension, String(e.name))}>
              {rows.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: any) => `${(v * 100).toFixed(1)}%`} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )
    }

    return (
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={rows} onClick={(e: any) => e?.activeLabel && drillThrough(dimension, e.activeLabel)}>
          <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
          <XAxis dataKey={dimension} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={70} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 10 }} />
          <Tooltip formatter={(v: any) => fmt(v)} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {rows.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  const canAdmin = role === 'admin'
  const canEdit = role === 'admin' || role === 'auditor'

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-blue-600" /> BI Studio
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Power BI parity: relatórios com cross-filtering, Q&A em linguagem natural, forecast, anomalias, Matrix, Pareto, Pipelines ETL e alertas — tudo num único sítio.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {([['explorer', 'Explorador', Layers], ['reports', 'Relatórios', LayoutDashboard], ['pipelines', 'Pipelines ETL', Workflow], ['alerts', 'Alertas', Bell], ['rls', 'Segurança RLS', ShieldCheck]] as const)
            .filter(([t]) => t !== 'rls' || canAdmin)
            .map(([t, lbl, Icon]) => (
              <button key={t} onClick={() => setTab(t as any)}
                      className={`${tab === t ? btnP : btnS}`}>
                <Icon className="w-3.5 h-3.5" /> {lbl}
              </button>))}
        </div>
      </div>

      {tab === 'explorer' && (
        <>
        {/* Q&A — Pergunte aos dados */}
        <div className={`${card} space-y-3`}>
          <h2 className="text-sm font-semibold flex items-center gap-2 text-slate-800 dark:text-slate-100">
            <Sparkles className="w-4 h-4 text-amber-500" /> Pergunte aos dados (Q&A)
          </h2>
          <div className="flex gap-2">
            <input className={input} placeholder="ex.: total por fornecedor últimos 90 dias · tendência mensal · top 5 categorias por percentagem…"
                   value={qText} onChange={e => setQText(e.target.value)}
                   onKeyDown={e => { if (e.key === 'Enter') askQA() }} />
            <button className={btnP} onClick={askQA} disabled={qaBusy || !qText.trim()}>
              {qaBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Perguntar
            </button>
          </div>
          {qaRes && (
            <div className="border border-slate-100 dark:border-slate-800 rounded-xl p-3 space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span className="px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">{qaRes.spec?.visual}</span>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800">confiança {(100 * (qaRes.spec?.confidence || 0)).toFixed(0)}%</span>
                <span>{qaRes.explain}</span>
              </div>
              <MiniVisual kind={qaRes.kind} data={qaRes.data} />
            </div>)}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          {/* Construtor de medida */}
          <div className={`${card} xl:col-span-1 space-y-3`}>
            <h2 className="text-sm font-semibold flex items-center gap-2 text-slate-800 dark:text-slate-100">
              <SlidersHorizontal className="w-4 h-4 text-blue-600" /> Medida
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <div><span className={label}>Agregação</span>
                <select className={sel} value={agg} onChange={e => setAgg(e.target.value)}>
                  {(meta?.aggregations || []).map(a => <option key={a}>{a}</option>)}</select></div>
              <div><span className={label}>Campo</span>
                <select className={sel} value={field} onChange={e => setField(e.target.value)}>
                  {(meta?.fields || []).map(f => <option key={f}>{f}</option>)}</select></div>
            </div>
            <div><span className={label}>Modo</span>
              <select className={sel} value={wrapMode} onChange={e => setWrapMode(e.target.value as any)}>
                <option value="plain">Simples</option>
                <option value="pct_of_total">% do total</option>
                <option value="running_total">Acumulado</option>
                <option value="yoy">YoY (vs. ano anterior)</option>
              </select></div>

            <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
              <span className={label}><Filter className="w-3 h-3 inline" /> Filtros (filter context)</span>
              {filters.map((f, i) => (
                <div key={i} className="flex items-center gap-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1 mb-1">
                  <span className="flex-1 truncate">{f.field} {f.op} {String(f.value)}</span>
                  <button onClick={() => setFilters(filters.filter((_, j) => j !== i))} className="text-red-500"><Trash2 className="w-3 h-3" /></button>
                </div>))}
              <div className="grid grid-cols-3 gap-1">
                <select className={sel} value={fField} onChange={e => setFField(e.target.value)}>
                  {['vendor', 'category', 'status', 'currency', 'month'].map(f => <option key={f}>{f}</option>)}</select>
                <select className={sel} value={fOp} onChange={e => setFOp(e.target.value)}>
                  {['eq', 'ne', 'contains', 'in', 'gt', 'gte', 'lt', 'lte'].map(o => <option key={o}>{o}</option>)}</select>
                <input className={input} placeholder="valor" value={fVal} onChange={e => setFVal(e.target.value)} />
              </div>
              <button className={`${btnS} mt-2 w-full justify-center`}
                      onClick={() => { if (fVal !== '') setFilters([...filters, { field: fField, op: fOp, value: fVal }]); setFVal('') }}>
                + adicionar filtro
              </button>
            </div>

            {canEdit && (
              <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                <span className={label}><Save className="w-3 h-3 inline" /> Guardar medida</span>
                <div className="flex gap-1">
                  <input className={input} placeholder="nome" value={mName} onChange={e => setMName(e.target.value)} />
                  <button className={btnP} onClick={saveMeasure}>Guardar</button>
                </div>
              </div>)}

            {measures.length > 0 && (
              <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                <span className={label}>Medidas guardadas (clique para reutilizar o nome)</span>
                {measures.map(m => (
                  <div key={m.id} className="flex items-center gap-1 text-xs py-1">
                    <button className="flex-1 text-left truncate text-blue-600 hover:underline"
                            onClick={() => setMName(m.name)}
                            title={JSON.stringify(m.expression)}>{m.name}</button>
                    {canEdit && <button onClick={() => delMeasure(m.id)} className="text-red-400"><Trash2 className="w-3 h-3" /></button>}
                  </div>))}
              </div>)}
          </div>

          {/* Visual */}
          <div className={`${card} xl:col-span-3 space-y-3`}>
            <div className="flex flex-wrap gap-2">
              {([['bar', 'Barras', BarChart3], ['line', 'Linhas', BarChart3], ['pie', 'Pizza', BarChart3],
                 ['series', 'Séries', BarChart3], ['forecast', 'Forecast', BarChart3], ['anomaly', 'Anomalias', BarChart3],
                 ['waterfall', 'Waterfall', BarChart3], ['funnel', 'Funil', BarChart3], ['kpi', 'KPI', BarChart3],
                 ['pareto', 'Pareto 80/20', BarChart3], ['matrix', 'Matrix', Table2],
                 ['decompose', 'Árvore', ListTree], ['whatif', 'What-if', SlidersHorizontal]] as const)
                .map(([v, lbl, Icon]) => (
                  <button key={v} onClick={() => { setVisual(v as any); setData(null); setDataKind(''); setErr('') }}
                          className={`${visual === v ? btnP : btnS}`}><Icon className="w-3.5 h-3.5" /> {lbl}</button>))}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 items-end">
              {!['matrix', 'decompose', 'whatif', 'kpi'].includes(visual) && (
                <div><span className={label}>Dimensão</span>
                  <select className={sel} value={dimension} onChange={e => setDimension(e.target.value)}>
                    {(meta?.dimensions || []).map(d => <option key={d}>{d}</option>)}</select></div>)}
              {['series', 'anomaly', 'forecast'].includes(visual) && (
                <div><span className={label}>Granularidade</span>
                  <select className={sel} value={granularity} onChange={e => setGranularity(e.target.value)}>
                    {['day', 'week', 'month', 'quarter', 'year'].map(g => <option key={g}>{g}</option>)}</select></div>)}
              {visual === 'anomaly' && (
                <div><span className={label}>Limiar z-score</span>
                  <input className={input} type="number" step="0.5" min="1" max="5" value={anomalyZ} onChange={e => setAnomalyZ(e.target.value)} /></div>)}
              {visual === 'forecast' && (
                <div><span className={label}>Períodos a projetar</span>
                  <input className={input} type="number" min="1" max="12" value={forecastPeriods} onChange={e => setForecastPeriods(e.target.value)} /></div>)}
              {visual === 'kpi' && (
                <div><span className={label}>Alvo (opcional)</span>
                  <input className={input} type="number" placeholder="ex.: 100000" value={kpiTarget} onChange={e => setKpiTarget(e.target.value)} /></div>)}
              {visual === 'matrix' && (<>
                <div><span className={label}>Linhas</span>
                  <select className={sel} value={rowDim} onChange={e => setRowDim(e.target.value)}>
                    {(meta?.dimensions || []).map(d => <option key={d}>{d}</option>)}</select></div>
                <div><span className={label}>Colunas</span>
                  <select className={sel} value={colDim} onChange={e => setColDim(e.target.value)}>
                    {(meta?.dimensions || []).map(d => <option key={d}>{d}</option>)}</select></div></>)}
              {visual === 'decompose' && (
                <div className="col-span-2"><span className={label}>Hierarquia (ordem)</span>
                  <div className="flex flex-wrap gap-1">
                    {(meta?.dimensions || []).map(d => (
                      <button key={d} onClick={() => setDecompDims(decompDims.includes(d) ? decompDims.filter(x => x !== d) : [...decompDims, d])}
                              className={`px-2 py-1 rounded-md text-[11px] ${decompDims.includes(d) ? 'bg-blue-600 text-white' : 'px-2 py-1 rounded-md text-[11px] border border-slate-300 dark:border-slate-600'}`}>{d}</button>))}
                  </div></div>)}
              {visual === 'whatif' && (
                <div className="col-span-2">
                  <span className={label}>Ajuste do cenário: {whatPct > 0 ? '+' : ''}{whatPct}%</span>
                  <input type="range" min={-50} max={200} value={whatPct}
                         onChange={e => setWhatPct(Number(e.target.value))} className="w-full accent-blue-600" />
                </div>)}
              <button className={btnP} onClick={render} disabled={busy}>
                <Play className="w-3.5 h-3.5" /> Avaliar
              </button>
              {data && (
                <>
                  <button className={btnS} onClick={exportXlsx} disabled={busy}>
                    <Download className="w-3.5 h-3.5" /> Exportar Excel
                  </button>
                  {canEdit && (
                    <div className="flex gap-1">
                      <input className={input + ' w-40'} placeholder="nome do relatório…" value={dashName} onChange={e => setDashName(e.target.value)} />
                      <button className={btnS} onClick={createDashboard} disabled={busy || !dashName.trim()} title="Fixar visual atual num relatório guardado">
                        <Pin className="w-3.5 h-3.5" /> Fixar
                      </button>
                    </div>)}
                </>)}
            </div>

            <div className="border border-slate-100 dark:border-slate-800 rounded-xl p-2 min-h-[360px]">
              {renderVisual()}
            </div>

            {drill && (
              <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                <p className={label}><Table2 className="w-3 h-3 inline" /> Drillthrough — {drill.length} transações</p>
                <div className="overflow-x-auto max-h-56">
                  <table className="w-full text-xs">
                    <thead><tr className="bg-slate-100 dark:bg-slate-800">
                      {['ID', 'Fornecedor', 'Valor', 'Categoria', 'Estado', 'Data'].map(h => <th key={h} className="p-1.5 text-left">{h}</th>)}
                    </tr></thead>
                    <tbody>{drill.map((r, i) => (
                      <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="p-1.5">{r.transaction_id}</td>
                        <td className="p-1.5">{r.vendor}</td>
                        <td className="p-1.5 text-right">{fmt(r.amount)}</td>
                        <td className="p-1.5">{r.category}</td>
                        <td className="p-1.5">{r.status}</td>
                        <td className="p-1.5">{String(r.timestamp).slice(0, 10)}</td>
                      </tr>))}</tbody>
                  </table>
                </div>
              </div>)}
          </div>
        </div>
        </>
      )}

      {tab === 'reports' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className={card + ' space-y-2'}>
              <h2 className="text-sm font-semibold flex items-center gap-2"><LayoutDashboard className="w-4 h-4 text-blue-600" /> Relatórios guardados ({dashes.length})</h2>
              {dashes.map(d0 => (
                <div key={d0.id} className="flex items-center gap-2 border border-slate-100 dark:border-slate-800 rounded-lg p-2 text-xs">
                  <span className="font-medium flex-1 truncate">{d0.name}</span>
                  <span className="text-slate-400">{(d0.config?.visuals || []).length} visuais</span>
                  <button className={btnS} onClick={() => runDashboard(d0.id, [])} disabled={busy}><Play className="w-3.5 h-3.5" /> Abrir</button>
                  {canEdit && <button onClick={() => delDashboard(d0.id)} className="text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>}
                </div>))}
              {dashes.length === 0 && <p className="text-sm text-slate-400">Sem relatórios — fixe visuais no Explorador (botão «Fixar») para os guardar aqui.</p>}
            </div>
            <div className={card + ' space-y-2'}>
              <h2 className="text-sm font-semibold flex items-center gap-2"><Filter className="w-4 h-4 text-blue-600" /> Cross-filtering (slicers dinâmicos)</h2>
              {crossFilters.length > 0 ? (
                <div className="space-y-1">
                  {crossFilters.map((f, i) => (
                    <div key={i} className="flex items-center gap-1 text-xs bg-blue-50 dark:bg-blue-900/30 rounded-lg px-2 py-1">
                      <span className="flex-1">{f.field} = {String(f.value)}</span>
                      <button onClick={() => runDashboard(dashResult?.id || 0, crossFilters.filter((_, j) => j !== i))}
                              className="text-red-500"><Trash2 className="w-3 h-3" /></button>
                    </div>))}
                  <button className={`${btnS} w-full justify-center`} onClick={() => runDashboard(dashResult?.id || 0, [])} disabled={busy}>
                    <RefreshCw className="w-3.5 h-3.5" /> limpar filtros
                  </button>
                </div>
              ) : <p className="text-sm text-slate-400">Clique numa barra de um visual para filtrar todos os outros (estilo Power BI).</p>}
              {dashResult && <p className="text-[11px] text-slate-400">relatório ativo: <b>{dashResult.dashboard}</b></p>}
            </div>
          </div>

          {dashResult && (
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {dashResult.visuals.map((v: Row) => (
                <div key={v.id} className={card + ' space-y-2'}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{v.title}</h3>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${v.ok ? 'bg-emerald-50 dark:bg-emerald-900/40 text-emerald-600' : 'bg-red-50 dark:bg-red-900/40 text-red-600'}`}>{v.kind}</span>
                  </div>
                  {v.ok
                    ? <MiniVisual kind={v.kind} data={v.data}
                                  onPick={(dim, val) => runDashboard(dashResult.id, [...crossFilters, { field: dim, op: 'eq', value: val }])} />
                    : <p className="text-xs text-red-500">{v.error}</p>}
                </div>))}
            </div>)}
        </div>
      )}

      {tab === 'alerts' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className={card + ' space-y-3'}>
            <h2 className="text-sm font-semibold flex items-center gap-2"><Bell className="w-4 h-4 text-amber-500" /> Novo alerta de medida</h2>
            <p className="text-[11px] text-slate-400">Usa a medida configurada no Explorador (agregação, campo, filtros). Quando o valor cruza o limiar, recebe uma notificação no sino.</p>
            <input className={input} placeholder="nome do alerta" value={alertName} onChange={e => setAlertName(e.target.value)} />
            <div className="grid grid-cols-2 gap-2">
              <div><span className={label}>Condição</span>
                <select className={sel} value={alertCmp} onChange={e => setAlertCmp(e.target.value)}>
                  <option value="gt">acima de (&gt;)</option>
                  <option value="gte">acima ou igual (≥)</option>
                  <option value="lt">abaixo de (&lt;)</option>
                  <option value="lte">abaixo ou igual (≤)</option>
                </select></div>
              <div><span className={label}>Limiar</span>
                <input className={input} type="number" placeholder="ex.: 10000" value={alertTh} onChange={e => setAlertTh(e.target.value)} /></div>
            </div>
            {filters.length > 0 && <p className="text-[11px] text-slate-400">filtros ativos do explorador: {filters.map(f => `${f.field}${f.op}${String(f.value)}`).join(', ')}</p>}
            <button className={btnP} onClick={createAlert}><Save className="w-3.5 h-3.5" /> Criar alerta</button>
          </div>

          <div className={card + ' space-y-2'}>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Alertas ({alerts.length})</h2>
              {canEdit && <button className={btnS} onClick={runAlerts} disabled={busy}><Play className="w-3.5 h-3.5" /> Avaliar agora</button>}
            </div>
            {alerts.map(a0 => (
              <div key={a0.id} className="flex items-center gap-2 border border-slate-100 dark:border-slate-800 rounded-lg p-2 text-xs">
                <span className={`w-2 h-2 rounded-full ${!a0.active ? 'bg-slate-300' : a0.last_state === 'breach' ? 'bg-red-500' : a0.last_state === 'error' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                <span className="font-medium flex-1 truncate">{a0.name}</span>
                <span className="text-slate-500">{a0.comparator} {fmt(a0.threshold)}</span>
                <span className="text-slate-400">último: {a0.last_value == null ? '—' : fmt(a0.last_value)}</span>
                <button onClick={() => toggleAlert(a0)} className={btnS}>{a0.active ? 'desativar' : 'ativar'}</button>
                {canEdit && <button onClick={() => delAlert(a0.id)} className="text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>}
              </div>))}
            {alerts.length === 0 && <p className="text-sm text-slate-400">Sem alertas — crie o primeiro à esquerda.</p>}
            {alertRun && (
              <div className="text-[11px] text-slate-500 border-t border-slate-100 dark:border-slate-800 pt-2">
                última avaliação: {alertRun.evaluated} alerta(s) — {alertRun.results?.filter((r: Row) => r.state === 'breach').length} em violação
              </div>)}
          </div>
        </div>
      )}

      {tab === 'pipelines' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className={card + ' space-y-3'}>
            <h2 className="text-sm font-semibold flex items-center gap-2"><Workflow className="w-4 h-4 text-blue-600" /> Novo pipeline (applied steps)</h2>
            <input className={input} placeholder="nome do pipeline" value={pipeName} onChange={e => setPipeName(e.target.value)} />
            <textarea className={input + ' font-mono text-xs h-40'} value={pipeSteps} onChange={e => setPipeSteps(e.target.value)} />
            <p className="text-[11px] text-slate-400">Passos: map_columns, rename, filter (cmp: eq|gt|contains…), derive (month|pct_of_total|running_total|bucket…), dedupe, fillna, cast, sort, dropna, select, upper_headers, trim_text</p>
            <button className={btnP} onClick={createPipeline}><Save className="w-3.5 h-3.5" /> Criar pipeline</button>
          </div>

          <div className={card + ' space-y-3'}>
            <h2 className="text-sm font-semibold">Pipelines guardados</h2>
            {pipes.map(p => (
              <div key={p.id} className="border border-slate-100 dark:border-slate-800 rounded-lg p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm flex-1">{p.name}</span>
                  <span className="text-[11px] text-slate-400">{p.run_count} execuções</span>
                </div>
                <div className="flex items-center gap-2">
                  <input type="file" accept=".xlsx,.xls,.csv" className="text-xs" onChange={e => setPipeFile(e.target.files?.[0] || null)} />
                  <button className={btnP} onClick={() => runPipeline(p.id)} disabled={busy}><Play className="w-3.5 h-3.5" /> Executar</button>
                  <button className={btnS} onClick={() => delPipeline(p.id)}><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>))}
            {pipes.length === 0 && <p className="text-sm text-slate-400">Sem pipelines — crie o primeiro à esquerda.</p>}
          </div>

          {pipeResult && (
            <div className={`${card} lg:col-span-2 space-y-2`}>
              <h2 className="text-sm font-semibold">Resultado — {pipeResult.rows_out} linhas · {pipeResult.steps_ok}/{pipeResult.steps_total} passos OK · {pipeResult.imported} importadas</h2>
              <div className="max-h-44 overflow-y-auto text-xs space-y-1">
                {pipeResult.log.map((l: Row, i: number) => (
                  <div key={i} className="flex gap-2"><span className="text-slate-400 w-8">#{l.step}</span>
                    <span className="font-mono text-blue-600 w-28">{l.op}</span>
                    <span className="text-slate-600 dark:text-slate-300 flex-1">{l.note}</span></div>))}
              </div>
              {pipeResult.preview?.rows?.length > 0 && (
                <div className="overflow-x-auto max-h-64 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <table className="w-full text-xs">
                    <thead><tr className="bg-slate-100 dark:bg-slate-800">
                      {pipeResult.preview.columns.map((c: string) => <th key={c} className="p-1.5 text-left">{c}</th>)}
                    </tr></thead>
                    <tbody>{pipeResult.preview.rows.map((r: Row, i: number) => (
                      <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                        {pipeResult.preview.columns.map((c: string) => <td key={c} className="p-1.5">{String(r[c]).slice(0, 30)}</td>)}
                      </tr>))}</tbody>
                  </table>
                </div>)}
            </div>)}
        </div>
      )}

      {tab === 'rls' && canAdmin && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className={card + ' space-y-3'}>
            <h2 className="text-sm font-semibold flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-blue-600" /> Nova regra RLS</h2>
            <input className={input} placeholder="nome (opcional)" value={rlsName} onChange={e => setRlsName(e.target.value)} />
            <div className="grid grid-cols-2 gap-2">
              <div><span className={label}>Alvo</span>
                <select className={sel} value={rlsIsRole ? 'role' : 'user'}
                        onChange={e => setRlsIsRole(e.target.value === 'role')}>
                  <option value="user">Utilizador (email)</option>
                  <option value="role">Papel (role)</option>
                </select></div>
              <div><span className={label}>Valor do alvo</span>
                <input className={input} placeholder={rlsIsRole ? 'auditor' : 'user@empresa.pt'}
                       value={rlsTarget} onChange={e => setRlsTarget(e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><span className={label}>Dimensão</span>
                <select className={sel} value={rlsDim} onChange={e => setRlsDim(e.target.value)}>
                  {['vendor', 'category', 'status', 'currency', 'user_id'].map(d => <option key={d}>{d}</option>)}</select></div>
              <div><span className={label}>Valores permitidos (vírgula)</span>
                <input className={input} placeholder="Alfa, Beta" value={rlsValues} onChange={e => setRlsValues(e.target.value)} /></div>
            </div>
            <button className={btnP} onClick={createRule}><Save className="w-3.5 h-3.5" /> Criar regra</button>
          </div>

          <div className={card + ' space-y-2'}>
            <h2 className="text-sm font-semibold">Regras ({rules.length})</h2>
            {rules.map(r => (
              <div key={r.id} className="flex items-center gap-2 border border-slate-100 dark:border-slate-800 rounded-lg p-2 text-xs">
                <span className={`w-2 h-2 rounded-full ${r.active ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                <span className="font-medium flex-1">{r.name}</span>
                <span className="text-slate-500">{r.user_id ? r.user_id : `role:${r.role}`} → {r.dimension} [{(r.allowed_values || []).slice(0, 3).join(', ')}{(r.allowed_values || []).length > 3 ? '…' : ''}]</span>
                <button onClick={() => toggleRule(r)} className={btnS}>{r.active ? 'desativar' : 'ativar'}</button>
                <button onClick={() => delRule(r.id)} className="text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>))}
            {rules.length === 0 && <p className="text-sm text-slate-400">Sem regras — todos os utilizadores veem tudo.</p>}
          </div>
        </div>)}
    </div>
  )
}


// ------------------------------------------------ MiniVisual: renderizador
// leve usado no Q&A e nos relatórios guardados (kind + payload → gráfico).

function MiniVisual({ kind, data, onPick }: { kind: string, data: any, onPick?: (dim: string, val: string) => void }) {
  if (!data) return <p className="text-xs text-slate-400">sem dados</p>

  if (kind === 'kpi' || (data.value != null && data.status != null)) {
    return (
      <div className="text-center py-3">
        <p className="text-3xl font-bold text-slate-800 dark:text-slate-100">{fmt(data.value)}</p>
        {data.target != null && <p className="text-[11px] text-slate-500">alvo {fmt(data.target)} · {(100 * (data.pct_of_target || 0)).toFixed(0)}%</p>}
        {data.trend_30d != null && <p className={`text-[11px] ${(data.trend_30d) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>{(100 * data.trend_30d).toFixed(1)}% vs 30d</p>}
      </div>
    )
  }

  if (kind === 'series' || kind === 'anomaly' || kind === 'forecast') {
    let crow: Row[] = data.rows || []
    if (kind === 'forecast') crow = [...(data.history || []), ...(data.forecast || [])].map((r: Row) => ({ ...r }))
    return (
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={crow}>
          <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
          <XAxis dataKey="key" tick={{ fontSize: 9 }} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 9 }} />
          <Tooltip formatter={(v: any) => (v == null ? '—' : fmt(v))} />
          <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={false} />
          {(kind === 'series') && <Line type="monotone" dataKey="moving_avg" stroke="#7c3aed" strokeDasharray="5 3" dot={false} />}
          {(kind === 'anomaly') && <Scatter dataKey="anom" fill="#dc2626" />}
        </ComposedChart>
      </ResponsiveContainer>
    )
  }

  if (kind === 'waterfall') {
    const wrows = (data.rows || []).map((r: Row) => ({ ...r, delta: r.value }))
    return (
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={wrows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
          <XAxis dataKey={data.dimension} tick={{ fontSize: 9 }} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 9 }} />
          <Tooltip formatter={(v: any) => fmt(v)} />
          <Bar dataKey="base" stackId="w" fill="transparent" />
          <Bar dataKey="delta" stackId="w" radius={[3, 3, 0, 0]}>
            {wrows.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (kind === 'pareto') {
    const dim = data.dimension
    return (
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data.rows || []} onClick={(e: any) => onPick?.(dim, String(e?.activeLabel || ''))}>
          <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
          <XAxis dataKey={dim} tick={{ fontSize: 9 }} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 9 }} />
          <Tooltip formatter={(v: any, n: any) => n === 'cum_share' ? `${(v * 100).toFixed(0)}%` : fmt(v)} />
          <Bar dataKey="value">{(data.rows || []).map((r: Row, i: number) => <Cell key={i} fill={r.vital_few ? '#2563eb' : '#94a3b8'} />)}</Bar>
          <Line type="monotone" dataKey="cum_share" stroke="#dc2626" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    )
  }

  if (kind === 'matrix') {
    const cols: string[] = data.columns || []
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead><tr className="bg-slate-100 dark:bg-slate-800">
            <th className="p-1.5 text-left">{data.row_dim}</th>
            {cols.map(c => <th key={c} className="p-1.5 text-right">{c}</th>)}
          </tr></thead>
          <tbody>
            {data.rows.map((r: Row, i: number) => (
              <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                <td className="p-1.5 font-medium">{r.row}</td>
                {cols.map(c => <td key={c} className="p-1.5 text-right">{fmt(r[c])}</td>)}
              </tr>))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data.rows || []} dataKey="value" nameKey={data.dimension} outerRadius={85}>
            {(data.rows || []).map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip formatter={(v: any) => fmt(v)} />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (kind === 'funnel') {
    const first = data.first_value || 1
    return (
      <div className="space-y-1.5 py-1">
        {(data.rows || []).map((r: Row, i: number) => (
          <div key={i} className="flex items-center gap-2">
            <div className="h-6 rounded bg-blue-600/90" style={{ width: `${Math.max(10, 100 * ((r.value || 0) / first))}%` }}>
              <span className="pl-1.5 text-[10px] leading-6 text-white">{r[data.dimension]}</span>
            </div>
            <span className="text-[10px] text-slate-500">{fmt(r.value)}</span>
          </div>))}
      </div>
    )
  }

  // bar / line / genérico
  const dim = data.dimension
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data.rows || []} onClick={(e: any) => onPick?.(dim, String(e?.activeLabel || ''))}>
        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
        <XAxis dataKey={dim} tick={{ fontSize: 9 }} angle={-20} textAnchor="end" height={50} />
        <YAxis tickFormatter={fmt} tick={{ fontSize: 9 }} />
        <Tooltip formatter={(v: any) => fmt(v)} />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {(data.rows || []).map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
