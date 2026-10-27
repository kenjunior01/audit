"use client"
// MiniVisual — renderizador leve partilhado (kind + payload → gráfico).
// Usado no Q&A do BI Studio (/bi) e no Painel Auto (/studio): dado um payload
// de visual do motor BI (group/series/anomaly/forecast/waterfall/pareto/
// matrix/pie/funnel/kpi), desenha o gráfico correspondente sem configuração.
import {
  BarChart, PieChart, ComposedChart,
  Bar, Line, Pie, Cell, Scatter, XAxis, YAxis, Tooltip,
  CartesianGrid, ResponsiveContainer,
} from 'recharts'

type Row = Record<string, any>

const COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#ea580c', '#16a34a',
  '#dc2626', '#d97706', '#4f46e5', '#0d9488', '#be185d']

const fmt = (v: any) => {
  const n = Number(v)
  if (!isFinite(n)) return '—'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + 'k'
  if (Math.abs(n) < 10 && n % 1 !== 0) return n.toFixed(2)
  return n.toFixed(0)
}

export function MiniVisual({ kind, data, onPick }: { kind: string, data: any, onPick?: (dim: string, val: string) => void }) {
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
