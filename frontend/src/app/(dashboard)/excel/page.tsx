"use client"
import { useState } from 'react'
import { apiFetch, apiDownload } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  FileSpreadsheet, Upload, Search, GitCompareArrows, Download,
  CheckCircle2, AlertTriangle, Info, Loader2, BarChart3, Copy,
} from 'lucide-react'

type Mapping = Record<string, string>
type SheetInfo = { name: string; rows: number; columns: string[]; mapping: Mapping }
type Preview = {
  file_name?: string
  detected_sheet: string
  sheets: SheetInfo[]
  mapping: Mapping
  missing_required: string[]
  quality: { rows: number; issues: { level: string; msg: string }[] }
  sample: any[]
  suggestion: string
}

const FIELD_LABELS: Record<string, string> = {
  transaction_id: 'Nº Documento / ID',
  vendor: 'Fornecedor',
  amount: 'Valor',
  currency: 'Moeda',
  timestamp: 'Data',
  category: 'Categoria',
  user_id: 'Usuário / Aprovador',
  status: 'Estado',
}

const TABS = [
  { id: 'import', label: 'Importar', icon: Upload },
  { id: 'analyze', label: 'Análises', icon: Search },
  { id: 'reconcile', label: 'Reconciliação', icon: GitCompareArrows },
  { id: 'export', label: 'Export Premium', icon: Download },
]

export default function ExcelStudioPage() {
  useRequireToken()
  const [tab, setTab] = useState('import')

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-blue-600 flex items-center justify-center shadow-[0_0_20px_rgba(37,99,235,0.4)]">
          <FileSpreadsheet className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Excel Studio</h1>
          <p className="text-sm text-slate-400">
            Super auxílio de documentos: importação inteligente, análises de auditor e reconciliação
          </p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-slate-800 pb-1">
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t.id ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'import' && <ImportTab />}
      {tab === 'analyze' && <AnalyzeTab />}
      {tab === 'reconcile' && <ReconcileTab />}
      {tab === 'export' && <ExportTab />}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* ABA 1 — IMPORTAR                                                    */
/* ------------------------------------------------------------------ */
function ImportTab() {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Mapping>({})
  const [sheet, setSheet] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  const selectFile = async (f: File | null) => {
    if (!f) return
    setFile(f); setPreview(null); setResult(null); setError(''); setLoading(true)
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await apiFetch('/excel/preview', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha no preview')
      setPreview(data)
      setMapping(data.mapping || {})
      setSheet(data.detected_sheet)
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }

  const doImport = async () => {
    if (!file || !preview) return
    setImporting(true); setResult(null); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file); fd.append('sheet', sheet)
      fd.append('mapping', JSON.stringify(mapping))
      const r = await apiFetch('/excel/import', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha na importação')
      setResult(data)
    } catch (e: any) { setError(e.message) } finally { setImporting(false) }
  }

  const headers = preview?.sheets.find(s => s.name === sheet)?.columns || []

  return (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6">
          <div className="border-2 border-dashed border-slate-700 rounded-xl p-10 text-center hover:border-blue-500 hover:bg-slate-800/40 transition-all cursor-pointer"
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); selectFile(e.dataTransfer.files?.[0] || null) }}>
            <input type="file" className="hidden" id="excel-file"
              accept=".xlsx,.xlsm,.xls,.csv"
              onChange={e => selectFile(e.target.files?.[0] || null)} />
            <label htmlFor="excel-file" className="cursor-pointer flex flex-col items-center gap-2">
              <Upload className="w-10 h-10 text-blue-500" />
              <span className="text-slate-200 font-medium">Arraste o ficheiro ou clique para selecionar</span>
              <span className="text-xs text-slate-500">Suporta .xlsx, .xlsm, .xls e .csv (multi-folha, até 25 MB)</span>
              {file && <span className="text-xs text-blue-400 mt-2">{file.name}</span>}
            </label>
          </div>
          {loading && <p className="text-center text-slate-400 mt-4 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> A analisar estrutura…</p>}
        </CardContent>
      </Card>

      {error && <Banner type="error" msg={error} />}

      {preview && (
        <>
          {preview.sheets.length > 1 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="p-4 flex flex-wrap items-center gap-2">
                <span className="text-sm text-slate-400 mr-2">Folha:</span>
                {preview.sheets.map(s => (
                  <button key={s.name} onClick={() => setSheet(s.name)}
                    className={`px-3 py-1.5 rounded-lg text-xs ${sheet === s.name ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
                    {s.name} ({s.rows})
                  </button>
                ))}
              </CardContent>
            </Card>
          )}

          <Card className="bg-slate-900 border-slate-800">
            <CardHeader><CardTitle className="text-white text-base flex items-center gap-2"><Copy className="w-4 h-4 text-blue-400" /> Mapeamento de colunas (edição livre)</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-slate-400">{preview.suggestion}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.keys(FIELD_LABELS).map(field => (
                  <div key={field} className="flex items-center gap-3">
                    <span className={`w-44 text-sm ${preview.missing_required.includes(field) ? 'text-red-400' : 'text-slate-300'}`}>
                      {FIELD_LABELS[field]}{['amount', 'timestamp'].includes(field) && ' *'}
                    </span>
                    <select value={mapping[field] || ''} className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200"
                      onChange={e => setMapping({ ...mapping, [field]: e.target.value })}>
                      <option value="">— ignorar —</option>
                      {headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <QualityIssues issues={preview.quality.issues} rows={preview.quality.rows} />
              <button onClick={doImport} disabled={importing}
                className="w-full mt-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium flex items-center justify-center gap-2 disabled:opacity-50">
                {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                Importar transações
              </button>
            </CardContent>
          </Card>

          {preview.sample.length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader><CardTitle className="text-white text-base">Amostra (primeiras linhas)</CardTitle></CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-xs text-slate-300">
                  <thead><tr className="text-slate-500 text-left">{Object.keys(preview.sample[0]).map(k => <th key={k} className="px-2 py-1.5 whitespace-nowrap">{k}</th>)}</tr></thead>
                  <tbody>
                    {preview.sample.map((row, i) => (
                      <tr key={i} className={i % 2 ? 'bg-slate-800/40' : ''}>
                        {Object.values(row).map((v: any, j) => <td key={j} className="px-2 py-1.5 max-w-48 truncate">{String(v ?? '—')}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {result && (
        <Card className="bg-slate-900 border-green-800/50">
          <CardContent className="p-5 space-y-2">
            <p className="flex items-center gap-2 text-green-400 font-medium"><CheckCircle2 className="w-5 h-5" /> {result.message}</p>
            <div className="grid grid-cols-3 gap-4 text-center pt-2">
              <Stat label="Importadas" value={result.imported} />
              <Stat label="Duplicados ignorados" value={result.duplicates_ignored} />
              <Stat label="Linhas inválidas" value={result.skipped?.length || 0} />
            </div>
            <p className="text-xs text-slate-500 pt-1">Registo de auditoria: job #{result.job_id} — consultável no histórico de importações.</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* ABA 2 — ANÁLISES                                                    */
/* ------------------------------------------------------------------ */
function AnalyzeTab() {
  const [days, setDays] = useState(365)
  const [threshold, setThreshold] = useState(10000)
  const [loading, setLoading] = useState(false)
  const [res, setRes] = useState<any>(null)
  const [error, setError] = useState('')

  const run = async () => {
    setLoading(true); setError(''); setRes(null)
    try {
      const r = await apiFetch(`/excel/analyze?days=${days}&threshold=${threshold}`)
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha nas análises')
      setRes(data)
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }

  return (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-4 flex flex-wrap items-end gap-4">
          <div><label className="text-xs text-slate-400 block mb-1">Período (dias)</label>
            <input type="number" value={days} onChange={e => setDays(+e.target.value)} className="w-28 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200" /></div>
          <div><label className="text-xs text-slate-400 block mb-1">Limiar de aprovação (fraccionamento)</label>
            <input type="number" value={threshold} onChange={e => setThreshold(+e.target.value)} className="w-40 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200" /></div>
          <button onClick={run} disabled={loading}
            className="py-2 px-6 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />} Executar análises
          </button>
        </CardContent>
      </Card>

      {error && <Banner type="error" msg={error} />}

      {res && (
        <>
          <div className={`rounded-xl p-4 border ${res.risk_score >= 0.6 ? 'bg-red-950/40 border-red-800' : res.risk_score >= 0.4 ? 'bg-amber-950/40 border-amber-700' : 'bg-emerald-950/40 border-emerald-800'}`}>
            <p className="text-white font-semibold">Score de risco: {Math.round(res.risk_score * 100)}%</p>
            <p className="text-sm text-slate-300">{res.verdict} · {res.rows_analyzed} transações analisadas</p>
          </div>

          {res.benford?.applicable && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader><CardTitle className="text-white text-base">Lei de Benford (1º dígito)</CardTitle></CardHeader>
              <CardContent>
                <p className={`text-sm mb-3 ${res.benford.verdict.includes('Não') ? 'text-red-400' : 'text-emerald-400'}`}>
                  MAD {res.benford.mad} — {res.benford.verdict}
                </p>
                <p className="text-xs text-slate-400 mb-3">{res.benford.insight}</p>
                <table className="w-full text-xs">
                  <thead><tr className="text-slate-500 text-left"><th className="py-1">Dígito</th><th>Observado</th><th>Esperado</th><th>Desvio</th></tr></thead>
                  <tbody className="text-slate-300">
                    {res.benford.distribution.map((d: any) => (
                      <tr key={d.digit} className={Math.abs(d.deviation_pct) > 5 ? 'text-red-400' : ''}>
                        <td className="py-1 font-semibold">{d.digit}</td>
                        <td>{d.observed_pct}%</td><td>{d.expected_pct}%</td>
                        <td>{d.deviation_pct > 0 ? '+' : ''}{d.deviation_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {res.duplicates?.exact?.length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader><CardTitle className="text-white text-base">Duplicados — mesmo fornecedor + valor</CardTitle></CardHeader>
              <CardContent className="overflow-x-auto">
                <p className="text-xs text-slate-400 mb-2">{res.duplicates.summary}</p>
                <table className="w-full text-xs">
                  <thead><tr className="text-slate-500 text-left"><th className="py-1">Fornecedor</th><th>Valor</th><th>Nº</th><th>Total</th><th>IDs</th></tr></thead>
                  <tbody className="text-slate-300">
                    {res.duplicates.exact.slice(0, 15).map((g: any, i: number) => (
                      <tr key={i}><td className="py-1">{g.vendor}</td><td>{g.amount?.toLocaleString()}</td><td>{g.count}</td><td>{g.total?.toLocaleString()}</td><td className="text-slate-500 max-w-40 truncate">{g.ids}</td></tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {res.duplicates?.fuzzy?.length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader><CardTitle className="text-white text-base">Duplicados fuzzy — fornecedores semelhantes</CardTitle></CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-slate-500 text-left"><th className="py-1">Fornecedores</th><th>Valor</th><th>Nº</th></tr></thead>
                  <tbody className="text-slate-300">
                    {res.duplicates.fuzzy.slice(0, 15).map((g: any, i: number) => (
                      <tr key={i}><td className="py-1">{g.vendors?.join(' ↔ ')}</td><td>{g.amount?.toLocaleString()}</td><td>{g.count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MiniCard title="Valores redondos" count={res.round_values?.count} hint="Múltiplos de 1.000/5.000/10.000 — padrão clássico de red flag." />
            <MiniCard title="Fim-de-semana" count={res.weekend?.count} hint="Transações registadas em sábados/domingos." />
            <MiniCard title="Fraccionamento" count={res.splits?.groups?.length || 0} hint={`Grupos abaixo de ${res.splits?.threshold?.toLocaleString()} somados acima do limiar.`} />
          </div>

          {res.splits?.groups?.length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader><CardTitle className="text-white text-base">Grupos suspeitos de fraccionamento</CardTitle></CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-slate-500 text-left"><th className="py-1">Fornecedor</th><th>Usuário</th><th>Nº</th><th>Total</th><th>Período</th></tr></thead>
                  <tbody className="text-slate-300">
                    {res.splits.groups.slice(0, 15).map((g: any, i: number) => (
                      <tr key={i}><td className="py-1">{g.vendor}</td><td>{g.user}</td><td>{g.n_transactions}</td><td>{g.total?.toLocaleString()}</td><td className="text-slate-400">{g.period}</td></tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* ABA 3 — RECONCILIAÇÃO                                               */
/* ------------------------------------------------------------------ */
function ReconcileTab() {
  const [fileA, setFileA] = useState<File | null>(null)
  const [fileB, setFileB] = useState<File | null>(null)
  const [useDbB, setUseDbB] = useState(false)
  const [tol, setTol] = useState(0.01)
  const [dtol, setDtol] = useState(3)
  const [loading, setLoading] = useState(false)
  const [res, setRes] = useState<any>(null)
  const [error, setError] = useState('')

  const run = async () => {
    if (!fileA) { setError('Selecione o ficheiro A (ex.: extrato bancário).'); return }
    if (!fileB && !useDbB) { setError('Selecione o ficheiro B ou ative "usar base de dados".'); return }
    setLoading(true); setError(''); setRes(null)
    try {
      const fd = new FormData()
      fd.append('file_a', fileA!); fd.append('amount_tol', String(tol)); fd.append('date_tol_days', String(dtol))
      if (useDbB) fd.append('use_db_b', '1'); else fd.append('file_b', fileB!)
      const r = await apiFetch('/excel/reconcile', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha na reconciliação')
      setRes(data)
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }

  const s = res?.summary
  return (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FilePicker label="Ficheiro A (ex.: extrato bancário)" file={fileA} onPick={setFileA} />
            {useDbB
              ? <div className="border-2 border-dashed border-blue-700/60 rounded-xl p-8 text-center text-sm text-blue-300 bg-blue-950/20 flex items-center justify-center">Lado B: transações da base de dados</div>
              : <FilePicker label="Ficheiro B (ex.: razão contábil)" file={fileB} onPick={setFileB} />}
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={useDbB} onChange={e => setUseDbB(e.target.checked)} className="accent-blue-600" />
              Lado B = base de dados
            </label>
            <div className="flex items-center gap-2 text-sm text-slate-300">
              Tolerância de valor: <input type="number" step="0.01" value={tol} onChange={e => setTol(+e.target.value)} className="w-24 bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-200" />
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-300">
              Janela de dias: <input type="number" value={dtol} onChange={e => setDtol(+e.target.value)} className="w-20 bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-200" />
            </div>
            <button onClick={run} disabled={loading}
              className="ml-auto py-2 px-6 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompareArrows className="w-4 h-4" />} Reconciliar
            </button>
          </div>
        </CardContent>
      </Card>

      {error && <Banner type="error" msg={error} />}

      {s && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Stat label="Correspondências" value={s.matched} accent="text-emerald-400" />
            <Stat label="Órfãs em A" value={s.unmatched_a} accent="text-red-400" />
            <Stat label="Órfãs em B" value={s.unmatched_b} accent="text-amber-400" />
            <Stat label="Matches fracos" value={s.weak_matches} accent="text-yellow-400" />
            <Stat label="Diferença total" value={s.difference?.toLocaleString()} accent="text-sky-400" />
          </div>
          {s.unmatched_a > 0 && <UnmatchedTable title="Sem correspondência em A" rows={res.unmatched_a} />}
          {s.unmatched_b > 0 && <UnmatchedTable title="Sem correspondência em B" rows={res.unmatched_b} />}
        </>
      )}
    </div>
  )
}

function UnmatchedTable({ title, rows }: { title: string; rows: any[] }) {
  if (!rows?.length) return null
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader><CardTitle className="text-white text-base">{title}</CardTitle></CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 text-left"><th className="py-1">ID</th><th>Fornecedor</th><th>Valor</th><th>Data</th></tr></thead>
          <tbody className="text-slate-300">
            {rows.slice(0, 20).map((r: any, i: number) => (
              <tr key={i}><td className="py-1">{r.transaction_id}</td><td>{r.vendor}</td><td>{r.amount}</td><td>{String(r.timestamp).slice(0, 10)}</td></tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/* ABA 4 — EXPORT PREMIUM                                              */
/* ------------------------------------------------------------------ */
function ExportTab() {
  useRequireToken()
  const [days, setDays] = useState(365)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const doExport = async (type: string, label: string) => {
    setBusy(type); setMsg(''); setError('')
    try {
      await apiDownload(`/excel/export?type=${type}&days=${days}`, `${label}_${new Date().toISOString().slice(0, 10)}.xlsx`)
      setMsg(`${label} exportado com sucesso.`)
    } catch (e: any) { setError(e.message) } finally { setBusy('') }
  }

  const cards = [
    { type: 'transactions', label: 'Transações', desc: 'Sumário + KPIs + gráficos + dados formatados' },
    { type: 'full', label: 'Relatório Completo', desc: 'Transações + folhas de duplicados, fraccionamento e valores redondos', accent: true },
    { type: 'alerts', label: 'Alertas', desc: 'Severidade colorida, materialidade com data bars e gráficos' },
    { type: 'cases', label: 'Casos', desc: 'Estado, prioridade, prazos e plano de ação' },
  ]
  return (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-4 flex items-center gap-3">
          <span className="text-sm text-slate-300">Período:</span>
          <select value={days} onChange={e => setDays(+e.target.value)} className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200">
            <option value={30}>Últimos 30 dias</option>
            <option value={90}>Últimos 90 dias</option>
            <option value={365}>Último ano</option>
            <option value={0}>Tudo</option>
          </select>
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cards.map(c => (
          <Card key={c.type} className={`bg-slate-900 ${c.accent ? 'border-blue-700' : 'border-slate-800'} hover:border-blue-500 transition-colors`}>
            <CardContent className="p-5">
              <h3 className="text-white font-semibold mb-1">{c.label}</h3>
              <p className="text-xs text-slate-400 mb-4">{c.desc}</p>
              <button onClick={() => doExport(c.type, c.label)} disabled={!!busy}
                className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
                {busy === c.type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Gerar .xlsx
              </button>
            </CardContent>
          </Card>
        ))}
      </div>
      {msg && <Banner type="ok" msg={msg} />}
      {error && <Banner type="error" msg={error} />}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Componentes utilitários                                             */
/* ------------------------------------------------------------------ */
function Stat({ label, value, accent = 'text-white' }: { label: string; value: any; accent?: string }) {
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 text-center border border-slate-700/50">
      <p className={`text-xl font-bold ${accent}`}>{value ?? '—'}</p>
      <p className="text-xs text-slate-400 mt-1">{label}</p>
    </div>
  )
}

function MiniCard({ title, count, hint }: { title: string; count?: number; hint: string }) {
  const has = !!count
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-slate-200 text-sm font-medium">{title}</h3>
          {has ? <AlertTriangle className="w-4 h-4 text-amber-400" /> : <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
        </div>
        <p className={`text-2xl font-bold ${has ? 'text-amber-400' : 'text-emerald-400'}`}>{count ?? 0}</p>
        <p className="text-xs text-slate-500 mt-1">{hint}</p>
      </CardContent>
    </Card>
  )
}

function QualityIssues({ issues, rows }: { issues: { level: string; msg: string }[]; rows: number }) {
  if (!issues.length) return <p className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> {rows} linhas sem problemas detetados.</p>
  return (
    <div className="space-y-1.5">
      {issues.map((i, k) => (
        <p key={k} className={`text-xs flex items-start gap-1.5 ${i.level === 'error' ? 'text-red-400' : i.level === 'warning' ? 'text-amber-400' : 'text-sky-400'}`}>
          {i.level === 'info' ? <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />} {i.msg}
        </p>
      ))}
    </div>
  )
}

function Banner({ type, msg }: { type: 'error' | 'ok'; msg: string }) {
  return (
    <div className={`rounded-lg p-3 text-sm ${type === 'error' ? 'bg-red-950/50 text-red-300 border border-red-800' : 'bg-emerald-950/50 text-emerald-300 border border-emerald-800'}`}>
      {msg}
    </div>
  )
}

function FilePicker({ label, file, onPick }: { label: string; file: File | null; onPick: (f: File | null) => void }) {
  const id = label.replace(/[^a-zA-Z]/g, '')
  return (
    <div className="border-2 border-dashed border-slate-700 rounded-xl p-6 text-center hover:border-blue-500 transition-colors">
      <input type="file" className="hidden" id={id} accept=".xlsx,.xlsm,.xls,.csv" onChange={e => onPick(e.target.files?.[0] || null)} />
      <label htmlFor={id} className="cursor-pointer flex flex-col items-center gap-1.5">
        <Upload className="w-6 h-6 text-blue-500" />
        <span className="text-sm text-slate-300">{label}</span>
        <span className="text-xs text-slate-500">{file ? file.name : 'Clique para selecionar (.xlsx/.csv)'}</span>
      </label>
    </div>
  )
}
