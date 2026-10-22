"use client"
/**
 * Análise Auto do Excel Studio — a porta de entrada mais simples possível.
 * Larga UM ficheiro (ou clica "Testar com exemplo") e recebe numa resposta:
 * folha+mapeamento detetados, perfil, qualidade 0-100 com checks, risco,
 * insights e próximos passos. Importar é sempre um clique explícito.
 * Reconciliação Auto: 2 ficheiros de uma vez, ou contra a base de dados.
 * Dossiê completo: 1 clique → importa, gera o painel REA e consolida tudo.
 */
import { useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Card, CardContent } from "@/components/ui/card"
import {
  Zap, Upload, Loader2, CheckCircle2, AlertTriangle, XCircle,
  FileDown, Sparkles, Database, GitBranch, ArrowRight, FileSpreadsheet,
  GitCompareArrows, FileArchive,
} from 'lucide-react'

const MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

type Check = { id: string; label: string; status: 'pass' | 'warn' | 'fail'; detail: string }
type TopItem = { name: string; total: number; count: number; share: number }
type AutoResult = {
  file: string; sheet: string
  sheets: { name: string; rows: number }[]
  sheets_tried?: string[]
  mapping: Record<string, string>
  mapping_missing: string[]
  profile: {
    total_rows: number; valid_rows: number; skipped_rows: number
    columns: string[]; period_start: string | null; period_end: string | null
    days_span: number; vendors: number; categories: number
    total_amount: number; avg_amount: number; max_amount: number
    negatives: number; currencies: string[]
  }
  quality: { score: number; grade: string; grade_msg?: string; checks: Check[] }
  risk: {
    score: number; verdict: string; level: string; benford_applicable: boolean
    duplicates_exact: number; round_values: number; weekend: number; splits: number
  }
  insights: string[]
  top_vendors: TopItem[]
  by_category: TopItem[]
  next_steps: string[]
}
type RecMatch = {
  a_id: string; b_id: string; a_vendor?: string; b_vendor?: string
  a_date?: string; b_date?: string; amount: number; weak?: boolean
}
type ReconcileResult = {
  file_a: string; sheet_a: string; file_b: string; source_b: string
  summary: {
    rows_a: number; rows_b: number; matched: number; unmatched_a: number
    unmatched_b: number; weak_matches: number; total_a: number; total_b: number
    difference: number
  }
  verdict: string; level: string; message: string
  insights: string[]
  matches: RecMatch[]
  unmatched_a: any[]; unmatched_b: any[]
}

const GRADE_STYLE: Record<string, { ring: string; chip: string }> = {
  A: { ring: 'text-emerald-400 border-emerald-500/40', chip: 'bg-emerald-950/60 text-emerald-300 border-emerald-700' },
  B: { ring: 'text-lime-400 border-lime-500/40', chip: 'bg-lime-950/60 text-lime-300 border-lime-700' },
  C: { ring: 'text-amber-400 border-amber-500/40', chip: 'bg-amber-950/60 text-amber-300 border-amber-700' },
  D: { ring: 'text-red-400 border-red-500/40', chip: 'bg-red-950/60 text-red-300 border-red-700' },
}
const CHECK_ICON: Record<string, { Icon: any; cls: string }> = {
  pass: { Icon: CheckCircle2, cls: 'text-emerald-400' },
  warn: { Icon: AlertTriangle, cls: 'text-amber-400' },
  fail: { Icon: XCircle, cls: 'text-red-400' },
}
const LEVEL_STYLE: Record<string, string> = {
  ok: 'border-emerald-700 bg-emerald-950/50 text-emerald-200',
  warn: 'border-amber-700 bg-amber-950/50 text-amber-200',
  high: 'border-red-700 bg-red-950/50 text-red-200',
}

const fmt = (v: any) => new Intl.NumberFormat('pt-PT', { maximumFractionDigits: 2 }).format(Number(v) || 0)

function CardHeader_({ title, icon }: { title: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 pb-3 border-b border-slate-800 mb-3">
      {icon}
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
    </div>
  )
}

async function downloadPost(path: string, body: FormData, filename: string) {
  const res = await apiFetch(path, { method: 'POST', body })
  if (!res.ok) {
    let msg = `Erro ${res.status}`
    try { const d = await res.json(); if (d?.error) msg = d.error } catch { /* binário */ }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

export default function AutoTab({ onAskCopilot, onGoImport }: {
  onAskCopilot: (file: File) => void
  onGoImport: () => void
}) {
  useRequireToken()
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<AutoResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState('')
  const [reporting, setReporting] = useState(false)
  const [rec, setRec] = useState<ReconcileResult | null>(null)
  const [recLoading, setRecLoading] = useState(false)
  const [recError, setRecError] = useState('')
  const [recFileB, setRecFileB] = useState<File | null>(null)
  const [dossLoading, setDossLoading] = useState(false)
  const [dossMsg, setDossMsg] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const recInputRef = useRef<HTMLInputElement>(null)

  const analyze = async (f: File) => {
    setLoading(true); setError(''); setResult(null); setRec(null)
    setImportMsg(''); setDossMsg(''); setRecFileB(null)
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await apiFetch('/excel/auto', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
      setResult(data)
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) { setFile(f); analyze(f) }
  }

  const trySample = async () => {
    setLoading(true); setError('')
    try {
      const res = await apiFetch('/excel/sample')
      if (!res.ok) throw new Error(`Erro ${res.status} ao buscar o exemplo`)
      const blob = await res.blob()
      const f = new File([blob], 'exemplo_movimentos.xlsx', { type: MIME })
      setFile(f)
      await analyze(f)
    } catch (e: any) { setError(e.message); setLoading(false) }
  }

  const doImport = async () => {
    if (!file || !result || importing) return
    setImporting(true); setError('')
    try {
      const fd = new FormData(); fd.append('file', file)
      fd.append('sheet', result.sheet)
      fd.append('mapping', JSON.stringify(result.mapping))
      const r = await apiFetch('/excel/import', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha na importação')
      setImportMsg(data.message || `${data.imported} transações importadas.`)
    } catch (e: any) { setError(e.message) } finally { setImporting(false) }
  }

  const doReport = async () => {
    if (!file || reporting) return
    setReporting(true); setError('')
    try {
      const fd = new FormData(); fd.append('file', file)
      await downloadPost('/excel/auto/report', fd,
        `Analise_Auto_${(result?.file || 'ficheiro').replace(/\.[^.]+$/, '')}.xlsx`)
    } catch (e: any) { setError(e.message) } finally { setReporting(false) }
  }

  const doDossier = async () => {
    if (!file || dossLoading) return
    setDossLoading(true); setError(''); setDossMsg('')
    try {
      const fd = new FormData(); fd.append('file', file)
      const res = await apiFetch('/excel/auto/dossier', { method: 'POST', body: fd })
      if (!res.ok) {
        let msg = `Erro ${res.status}`
        try { const d = await res.json(); if (d?.error) msg = d.error } catch { /* binário */ }
        throw new Error(msg)
      }
      const imported = res.headers.get('X-Dossier-Imported')
      const dups = res.headers.get('X-Dossier-Duplicates')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'Dossier_Auditoria.xlsx'
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
      setDossMsg(`Dossiê completo gerado${imported !== null ? ` — ${imported} transações importadas${Number(dups) > 0 ? `, ${dups} duplicados ignorados` : ''}` : ''}.`)
    } catch (e: any) { setError(e.message) } finally { setDossLoading(false) }
  }

  const doReconcile = async (useDb: boolean) => {
    if (!file || !result || recLoading) return
    if (!useDb && !recFileB) { setRecError('Escolha o 2º ficheiro para cruzar (ou use a base de dados).'); return }
    setRecLoading(true); setRecError('')
    try {
      const fd = new FormData(); fd.append('file_a', file)
      if (useDb) fd.append('use_db_b', '1')
      else if (recFileB) fd.append('file_b', recFileB)
      const r = await apiFetch('/excel/auto/reconcile', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
      setRec(data)
    } catch (e: any) { setRecError(e.message) } finally { setRecLoading(false) }
  }

  const doRecReport = async () => {
    if (!file || recLoading) return
    setRecLoading(true); setRecError('')
    try {
      const fd = new FormData(); fd.append('file_a', file)
      if (rec?.source_b === 'ficheiro' && recFileB) fd.append('file_b', recFileB)
      else fd.append('use_db_b', '1')
      await downloadPost('/excel/auto/reconcile/report', fd, 'Reconciliacao_Auto.xlsx')
    } catch (e: any) { setRecError(e.message) } finally { setRecLoading(false) }
  }

  const p = result?.profile
  const grade = result ? GRADE_STYLE[result.quality.grade] || GRADE_STYLE.C : null

  return (
    <div className="space-y-4">
      {/* Upload */}
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6">
          <div
            onDrop={onDrop} onDragOver={e => e.preventDefault()}
            onClick={() => inputRef.current?.click()}
            className="border-2 border-dashed border-slate-700 hover:border-blue-500 rounded-xl p-8 text-center cursor-pointer transition-colors">
            <input ref={inputRef} type="file" className="hidden" accept=".xlsx,.xlsm,.xls,.csv"
              onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); analyze(f) } }} />
            <Upload className="w-8 h-8 mx-auto text-slate-500 mb-2" />
            <p className="text-slate-300 text-sm font-medium">
              Largue o ficheiro aqui — nós tratamos do resto
            </p>
            <p className="text-slate-500 text-xs mt-1">
              Excel ou CSV · deteção de folha e colunas · qualidade · risco · insights
            </p>
            <button onClick={e => { e.stopPropagation(); trySample() }} disabled={loading}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium disabled:opacity-50">
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5 text-yellow-400" />}
              Testar com exemplo
            </button>
          </div>
          {file && (
            <p className="text-xs text-slate-500 mt-2 flex items-center gap-1.5">
              <FileSpreadsheet className="w-3.5 h-3.5" /> {file.name}
              {result && <> · folha <b className="text-slate-300">{result.sheet}</b>
                {result.sheets.length > 1 && <> ({result.sheets.length} folhas detetadas)</>}</>}
            </p>
          )}
          <p className="text-xs text-slate-600 mt-3">
            Para <b className="text-slate-400">reconciliar</b>, analise primeiro o 1º ficheiro e depois use “Reconciliar” — ou largue 2 ficheiros de uma vez
          </p>
          <input ref={recInputRef} type="file" className="hidden" accept=".xlsx,.xlsm,.xls,.csv"
            onChange={e => { const f = e.target.files?.[0]; if (f) { setRecFileB(f); doReconcile(false) } }} />
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 text-red-200 px-4 py-3 text-sm">{error}</div>
      )}

      {importMsg && (
        <div className="rounded-lg border border-emerald-800 bg-emerald-950/50 text-emerald-200 px-4 py-3 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {importMsg}
          <a href="/studio" className="text-emerald-300 underline underline-offset-2 inline-flex items-center gap-1">Abrir Painel Auto <ArrowRight className="w-3 h-3" /></a>
          <a href="/dashboard" className="ml-auto text-emerald-300 underline underline-offset-2 inline-flex items-center gap-1">Ver na Visão Geral <ArrowRight className="w-3 h-3" /></a>
        </div>
      )}

      {dossMsg && (
        <div className="rounded-lg border border-violet-800 bg-violet-950/50 text-violet-200 px-4 py-3 text-sm flex items-center gap-2">
          <FileArchive className="w-4 h-4" /> {dossMsg}
          <a href="/studio" className="ml-auto text-violet-300 underline underline-offset-2 inline-flex items-center gap-1">Abrir Painel Auto <ArrowRight className="w-3 h-3" /></a>
        </div>
      )}

      {result && p && grade && (
        <>
          {/* Score + risco */}
          <div className="grid md:grid-cols-3 gap-4">
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="p-5 flex items-center gap-4">
                <div className={`w-20 h-20 rounded-full border-4 ${grade.ring} flex flex-col items-center justify-center shrink-0`}>
                  <span className="text-2xl font-bold">{result.quality.score}</span>
                  <span className="text-xs text-slate-500">/100 · {result.quality.grade}</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-200">Qualidade dos dados</p>
                  <p className="text-xs text-slate-500 mt-1">{result.quality.grade_msg}</p>
                  <span className={`inline-block mt-2 px-2 py-0.5 rounded-full text-[10px] border ${grade.chip}`}>
                    nota {result.quality.grade}
                  </span>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="p-5">
                <p className="text-sm font-semibold text-slate-200 mb-1">Risco de auditoria</p>
                <p className="text-2xl font-bold text-slate-100">{result.risk.score.toFixed(2)}</p>
                <p className="text-xs text-slate-500 mt-1">{result.risk.verdict}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {result.risk.duplicates_exact > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-950 text-red-300 border border-red-800">{result.risk.duplicates_exact} duplicados</span>}
                  {result.risk.splits > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-950 text-amber-300 border border-amber-800">{result.risk.splits} fraccionamentos</span>}
                  {result.risk.round_values > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-950 text-amber-300 border border-amber-800">{result.risk.round_values} redondos</span>}
                  {result.risk.weekend > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-300 border border-slate-700">{result.risk.weekend} weekend</span>}
                  {result.risk.benford_applicable && <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-300 border border-slate-700">Benford ✓</span>}
                </div>
              </CardContent>
            </Card>
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="p-5 space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-slate-500">Linhas válidas</span><b className="text-slate-200">{fmt(p.valid_rows)}</b></div>
                <div className="flex justify-between"><span className="text-slate-500">Ignoradas</span><b className="text-slate-200">{fmt(p.skipped_rows)}</b></div>
                <div className="flex justify-between"><span className="text-slate-500">Período</span><b className="text-slate-200">{p.period_start || '—'} → {p.period_end || '—'}</b></div>
                <div className="flex justify-between"><span className="text-slate-500">Valor total</span><b className="text-slate-200">{fmt(p.total_amount)}</b></div>
                <div className="flex justify-between"><span className="text-slate-500">Média</span><b className="text-slate-200">{fmt(p.avg_amount)}</b></div>
                <div className="flex justify-between"><span className="text-slate-500">Fornecedores</span><b className="text-slate-200">{p.vendors}</b></div>
                {p.currencies.length > 0 && <div className="flex justify-between"><span className="text-slate-500">Moedas</span><b className="text-slate-200">{p.currencies.join(', ')}</b></div>}
              </CardContent>
            </Card>
          </div>

          {/* CTAs */}
          <div className="flex flex-wrap gap-3">
            <button onClick={doImport} disabled={importing}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-50">
              {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
              Importar para a plataforma
            </button>
            <button onClick={doReport} disabled={reporting}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50">
              {reporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
              Descarregar relatório .xlsx
            </button>
            <button onClick={doDossier} disabled={dossLoading} title="Importa os dados, gera o painel REA sobre a base e consolida tudo num único workbook"
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold disabled:opacity-50">
              {dossLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileArchive className="w-4 h-4" />}
              Dossiê completo (1 clique)
            </button>
            <button onClick={() => onAskCopilot(file!)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium">
              <Sparkles className="w-4 h-4" /> Perguntar ao Copiloto
            </button>
            <button onClick={onGoImport}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-slate-400 hover:text-slate-200 text-sm">
              <FileSpreadsheet className="w-4 h-4" /> Refinar mapeamento
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            {/* Checks */}
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader_ title="Verificações automáticas" icon={<Zap className="w-4 h-4 text-blue-400" />} />
              <CardContent className="pt-0 space-y-2.5">
                {result.quality.checks.map(c => {
                  const { Icon, cls } = CHECK_ICON[c.status]
                  return (
                    <div key={c.id} className="flex gap-2.5">
                      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cls}`} />
                      <div>
                        <p className="text-xs font-medium text-slate-200">{c.label}</p>
                        <p className="text-[11px] text-slate-500">{c.detail}</p>
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>

            {/* Insights */}
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader_ title="O que os dados dizem" icon={<Sparkles className="w-4 h-4 text-violet-400" />} />
              <CardContent className="pt-0 space-y-2">
                {result.insights.map((ins, i) => (
                  <p key={i} className="text-xs text-slate-300 flex gap-2">
                    <span className="text-slate-600 mt-0.5 shrink-0">▸</span>{ins}
                  </p>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Top fornecedores */}
          {result.top_vendors.length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader_ title="Top fornecedores" icon={<GitBranch className="w-4 h-4 text-cyan-400" />} />
              <CardContent className="pt-0 space-y-2">
                {result.top_vendors.map(v => (
                  <div key={v.name} className="flex items-center gap-3">
                    <span className="text-xs text-slate-300 w-44 truncate">{v.name}</span>
                    <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
                      <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
                        style={{ width: `${Math.min(100, v.share)}%` }} />
                    </div>
                    <span className="text-xs text-slate-400 w-28 text-right">{fmt(v.total)} · {v.share}%</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Reconciliação Auto */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader_ title="Reconciliar esta fonte" icon={<GitCompareArrows className="w-4 h-4 text-purple-400" />} />
            <CardContent className="pt-0 space-y-3">
              <div className="flex flex-wrap gap-2">
                <button onClick={() => recInputRef.current?.click()} disabled={recLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold disabled:opacity-50">
                  <Upload className="w-3.5 h-3.5" /> Com outro ficheiro
                </button>
                <button onClick={() => doReconcile(true)} disabled={recLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium disabled:opacity-50">
                  <Database className="w-3.5 h-3.5" /> Com a base de dados
                </button>
                {recFileB && <span className="text-xs text-slate-500 self-center">2º ficheiro: {recFileB.name}</span>}
              </div>
              {recError && <p className="text-xs text-red-300">{recError}</p>}

              {rec && (
                <div className="space-y-3">
                  <div className={`rounded-lg border px-4 py-3 text-sm ${LEVEL_STYLE[rec.level] || LEVEL_STYLE.warn}`}>
                    <b>{rec.verdict}</b> — {rec.message}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
                    {[['Linhas A', rec.summary.rows_a], ['Linhas B', rec.summary.rows_b],
                      ['Conciliadas', rec.summary.matched], ['Só em A', rec.summary.unmatched_a],
                      ['Diferença', fmt(rec.summary.difference)]].map(([l, v]) => (
                      <div key={String(l)} className="rounded-lg bg-slate-800/60 p-2">
                        <p className="text-[10px] text-slate-500">{l}</p>
                        <p className="text-sm font-bold text-slate-200">{v}</p>
                      </div>
                    ))}
                  </div>
                  {rec.matches.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[11px]">
                        <thead><tr className="text-slate-500 border-b border-slate-800">
                          <th className="text-left py-1">Fornecedor (A)</th>
                          <th className="text-right py-1">Valor</th>
                          <th className="text-left py-1 pl-3">Data A</th>
                          <th className="text-left py-1 pl-3">Data B</th>
                          <th className="text-left py-1 pl-3">Estado</th>
                        </tr></thead>
                        <tbody>
                          {rec.matches.slice(0, 6).map((m, i) => (
                            <tr key={i} className="border-b border-slate-800/50 text-slate-300">
                              <td className="py-1">{m.a_vendor || m.a_id}</td>
                              <td className="py-1 text-right">{fmt(m.amount)}</td>
                              <td className="py-1 pl-3">{m.a_date || '—'}</td>
                              <td className="py-1 pl-3">{m.b_date || '—'}</td>
                              <td className="py-1 pl-3">{m.weak ? <span className="text-amber-400">fraca</span> : <span className="text-emerald-400">ok</span>}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {rec.matches.length > 6 && (
                        <p className="text-[10px] text-slate-600 mt-1">+ {rec.matches.length - 6} correspondências no relatório completo</p>
                      )}
                    </div>
                  )}
                  <div className="space-y-1">
                    {rec.insights.map((ins, i) => (
                      <p key={i} className="text-xs text-slate-300 flex gap-2">
                        <span className="text-purple-500 mt-0.5 shrink-0">▸</span>{ins}
                      </p>
                    ))}
                  </div>
                  <button onClick={doRecReport} disabled={recLoading}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold disabled:opacity-50">
                    <FileDown className="w-3.5 h-3.5" /> Descarregar relatório de reconciliação
                  </button>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
