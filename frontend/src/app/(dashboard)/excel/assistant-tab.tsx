"use client"
/**
 * Copiloto IA do Excel Studio — assistente conversacional NL→Excel.
 * O utilizador carrega um ficheiro e pede em linguagem natural o que quer:
 * transformações, fórmulas para automatizar, sugestões de apresentação.
 * Resposta: texto + operações aplicadas + preview + cartões de fórmula
 * (PT-PT / English) + download do workbook com KPIs vivos.
 */
import { useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Card, CardContent } from "@/components/ui/card"
import {
  Sparkles, Upload, Loader2, Send, Copy, Check, Download,
  BarChart3, PieChart, LineChart, LayoutDashboard, Sigma, X, Database,
} from 'lucide-react'

type Formula = {
  id: string; title: string; category: string
  formula_pt: string; formula_en: string
  explanation: string; where: string; needs_365: boolean; column?: string | null
}
type CopilotResponse = {
  intent: string; model_used: string; answer: string
  sheet?: string; source?: { type: string; name?: string }
  data_context?: { rows?: number; columns?: { name: string; type: string; null_pct?: number }[] }
  operations_applied: { op: string; detail: string }[]
  plan: Record<string, unknown>[]
  result: { columns: string[]; rows: unknown[][]; shown: number; total_rows: number }
  formulas: Formula[]
  charts: { type: string; title: string; description: string }[]
  followups: string[]
}
type Message = { role: 'user' | 'assistant'; content: string; data?: CopilotResponse }

const QUICK_PROMPTS = [
  'Sugere fórmulas para tornar o ficheiro automático',
  'Top 10 por valor',
  'Total por categoria',
  'Deteta duplicados',
  'Como apresentar isto num dashboard?',
  'Adiciona coluna do mês e acumulado',
]

const CATEGORY_COLORS: Record<string, string> = {
  'KPI': 'bg-blue-950 text-blue-300 border-blue-800',
  'Automação': 'bg-emerald-950 text-emerald-300 border-emerald-800',
  'Análise': 'bg-amber-950 text-amber-300 border-amber-800',
  'Apresentação': 'bg-purple-950 text-purple-300 border-purple-800',
  'Pesquisa': 'bg-sky-950 text-sky-300 border-sky-800',
  'Sugestão IA': 'bg-fuchsia-950 text-fuchsia-300 border-fuchsia-800',
}

export default function AssistantTab() {
  useRequireToken()
  const [file, setFile] = useState<File | null>(null)
  const [useDb, setUseDb] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [lang, setLang] = useState<'pt' | 'en'>('pt')
  const [copied, setCopied] = useState('')
  const [applying, setApplying] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasFile = !!file || useDb

  const selectFile = (f: File | null) => {
    setFile(f); setError('')
    if (f) setUseDb(false)
  }

  const send = async (question: string) => {
    const q = question.trim()
    if (!q || loading) return
    if (!hasFile) { setError('Carregue primeiro um ficheiro (ou use a base de dados).'); return }
    setError('')
    setInput('')
    const history = messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('question', q)
      fd.append('history', JSON.stringify(history))
      if (useDb) fd.append('use_db', '1')
      else if (file) fd.append('file', file)
      const r = await apiFetch('/excel/assistant', { method: 'POST', body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Falha no Copiloto')
      setMessages(m => [...m, { role: 'assistant', content: data.answer, data }])
    } catch (e: any) {
      setError(e.message)
      setMessages(m => (m.length > 0 && m[m.length - 1].role === 'user' ? m.slice(0, -1) : m))
    } finally { setLoading(false) }
  }

  const applyAndDownload = async () => {
    const last = [...messages].reverse().find(m => m.role === 'assistant' && m.data)
    if (!file || applying) return
    setApplying(true); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('plan', JSON.stringify(last?.data?.plan || []))
      const r = await apiFetch('/excel/assistant/apply', { method: 'POST', body: fd })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        throw new Error(data.error || `Erro ${r.status}`)
      }
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Copiloto_Excel_${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) { setError(e.message) } finally { setApplying(false) }
  }

  const copyFormula = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(id)
      setTimeout(() => setCopied(''), 1500)
    } catch { /* clipboard indisponível */ }
  }

  return (
    <div className="space-y-4">
      {/* Barra de fonte de dados */}
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <input ref={inputRef} type="file" className="hidden" id="copilot-file"
            accept=".xlsx,.xlsm,.xls,.csv"
            onChange={e => selectFile(e.target.files?.[0] || null)} />
          <button onClick={() => inputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium">
            <Upload className="w-4 h-4" /> {file ? file.name : 'Carregar ficheiro'}
          </button>
          {file && (
            <button onClick={() => setFile(null)} className="text-slate-400 hover:text-red-400" title="Remover ficheiro">
              <X className="w-4 h-4" />
            </button>
          )}
          <button onClick={() => { setUseDb(v => !v); if (!useDb) setFile(null) }}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm border ${useDb ? 'bg-emerald-900/40 border-emerald-700 text-emerald-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}>
            <Database className="w-4 h-4" /> Usar base de dados
          </button>
          <span className="text-xs text-slate-500 ml-auto">Pergunte o que quer fazer com os dados — o Copiloto responde e transforma</span>
        </CardContent>
      </Card>

      {/* Janela de conversa */}
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-0">
          <div className="max-h-[52vh] overflow-y-auto p-5 space-y-4">
            {messages.length === 0 && (
              <div className="text-center py-8">
                <Sparkles className="w-10 h-10 text-blue-500 mx-auto mb-3" />
                <p className="text-slate-300 font-medium">Pergunte o que quer fazer com os seus dados</p>
                <p className="text-sm text-slate-500 mt-1">
                  Carregue um ficheiro e escreva, por exemplo: como agrupar, filtrar, que fórmulas usar para automatizar…
                </p>
                <div className="flex flex-wrap justify-center gap-2 mt-4">
                  {QUICK_PROMPTS.map(p => (
                    <button key={p} onClick={() => send(p)} disabled={!hasFile || loading}
                      className="px-3 py-1.5 rounded-full text-xs border border-slate-700 text-slate-300 hover:border-blue-500 hover:text-blue-300 disabled:opacity-40">
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%] text-sm">{m.content}</div>
              </div>
            ) : (
              <AssistantMessage key={i} data={m.data} lang={lang} setLang={setLang}
                copied={copied} copyFormula={copyFormula}
                onFollowup={q => send(q)} />
            ))}

            {loading && (
              <div className="flex items-center gap-2 text-slate-400 text-sm px-2">
                <Loader2 className="w-4 h-4 animate-spin" /> O Copiloto está a analisar os dados…
              </div>
            )}
          </div>

          {error && <div className="mx-5 mb-3 rounded-lg p-2.5 text-sm bg-red-950/50 text-red-300 border border-red-800">{error}</div>}

          {/* Input */}
          <div className="border-t border-slate-800 p-4 flex gap-2">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
              placeholder={hasFile ? 'Ex.: filtra valores maior que 5000 e mostra por categoria…' : 'Carregue um ficheiro primeiro…'}
              disabled={!hasFile || loading}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500 disabled:opacity-50" />
            <button onClick={() => send(input)} disabled={!hasFile || loading || !input.trim()}
              className="px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Ações sobre a última resposta */}
      {messages.some(m => m.role === 'assistant' && m.data) && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={applyAndDownload} disabled={!file || applying}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium disabled:opacity-40">
            {applying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            Aplicar plano e baixar .xlsx (KPIs vivos + folha de fórmulas)
          </button>
          {!file && <span className="text-xs text-amber-400">O download exige o ficheiro original (não funciona com a base de dados).</span>}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Mensagem do assistente: texto + tabela + fórmulas + gráficos        */
/* ------------------------------------------------------------------ */
function AssistantMessage({ data, lang, setLang, copied, copyFormula, onFollowup }: {
  data?: CopilotResponse
  lang: 'pt' | 'en'
  setLang: (l: 'pt' | 'en') => void
  copied: string
  copyFormula: (id: string, text: string) => void
  onFollowup: (q: string) => void
}) {
  if (!data) return null
  const res = data.result
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] w-full space-y-3">
        <div className="bg-slate-800/70 rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-slate-200 space-y-2">
          <Md text={data.answer} />
          <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-slate-500">
            <span className="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-700">{data.intent}</span>
            <span>{data.model_used}</span>
            {data.sheet && <span>· folha: {data.sheet}</span>}
            {data.data_context?.rows !== undefined && <span>· {data.data_context.rows} linhas</span>}
          </div>
        </div>

        {data.operations_applied.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.operations_applied.map((o, i) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-sky-950 border border-sky-800 text-sky-300">
                {o.op}: {o.detail}
              </span>
            ))}
          </div>
        )}

        {res.columns.length > 0 && (
          <Card className="bg-slate-950 border-slate-800">
            <CardContent className="p-3 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-800">
                    {res.columns.map(c => <th key={c} className="py-1.5 px-2 font-medium whitespace-nowrap">{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {res.rows.map((row, i) => (
                    <tr key={i} className="border-b border-slate-900 text-slate-300">
                      {row.map((v, j) => <td key={j} className="py-1.5 px-2 whitespace-nowrap">{fmtCell(v)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-slate-500 mt-2">{res.shown} de {res.total_rows} linhas</p>
            </CardContent>
          </Card>
        )}

        {data.formulas.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-300 flex items-center gap-1.5"><Sigma className="w-4 h-4 text-blue-400" /> Fórmulas recomendadas ({data.formulas.length})</p>
              <div className="flex text-[11px] rounded-lg overflow-hidden border border-slate-700">
                <button onClick={() => setLang('pt')} className={lang === 'pt' ? 'px-2.5 py-1 bg-blue-600 text-white' : 'px-2.5 py-1 text-slate-400 hover:bg-slate-800'}>PT-PT</button>
                <button onClick={() => setLang('en')} className={lang === 'en' ? 'px-2.5 py-1 bg-blue-600 text-white' : 'px-2.5 py-1 text-slate-400 hover:bg-slate-800'}>English</button>
              </div>
            </div>
            {data.formulas.map(f => (
              <div key={f.id} className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-200">{f.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${CATEGORY_COLORS[f.category] || 'bg-slate-900 text-slate-400 border-slate-700'}`}>{f.category}</span>
                    {f.needs_365 && <span className="text-[10px] px-1.5 py-0.5 rounded border bg-amber-950 text-amber-300 border-amber-800">Excel 365</span>}
                  </div>
                  <button onClick={() => copyFormula(f.id, lang === 'pt' ? f.formula_pt : f.formula_en)}
                    className="shrink-0 flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300">
                    {copied === f.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    {copied === f.id ? 'Copiado' : 'Copiar'}
                  </button>
                </div>
                <code className="block mt-2 text-[12px] leading-relaxed bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-emerald-300 overflow-x-auto whitespace-pre-wrap">
                  {lang === 'pt' ? f.formula_pt : f.formula_en}
                </code>
                <p className="text-xs text-slate-400 mt-2">{f.explanation}</p>
                <p className="text-[11px] text-slate-500 mt-1">Onde usar: {f.where}</p>
              </div>
            ))}
          </div>
        )}

        {data.charts.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {data.charts.map((c, i) => (
              <div key={i} className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <div className="flex items-center gap-2 mb-1">
                  {c.type === 'pie' ? <PieChart className="w-4 h-4 text-purple-400" />
                    : c.type === 'line' ? <LineChart className="w-4 h-4 text-emerald-400" />
                      : c.type === 'dashboard' ? <LayoutDashboard className="w-4 h-4 text-blue-400" />
                        : <BarChart3 className="w-4 h-4 text-amber-400" />}
                  <p className="text-xs font-medium text-slate-200">{c.title}</p>
                </div>
                <p className="text-[11px] text-slate-500">{c.description}</p>
              </div>
            ))}
          </div>
        )}

        {data.followups.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.followups.map((fu, i) => (
              <button key={i} onClick={() => onFollowup(fu)}
                className="text-xs px-3 py-1.5 rounded-full border border-blue-800 text-blue-300 hover:bg-blue-950">
                {fu}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Markdown-lite: **bold**, *itálico*, `código`, listas                */
/* ------------------------------------------------------------------ */
function Md({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <>
      {lines.map((line, i) => {
        const t = line.trim()
        if (!t) return <div key={i} className="h-1" />
        const bullet = /^[-•]\s+/.test(t)
        const numbered = /^\d+[.)]\s+/.test(t)
        const content = t.replace(/^[-•]\s+/, '').replace(/^\d+[.)]\s+/, '')
        return (
          <p key={i} className={bullet || numbered ? 'flex gap-2' : ''}>
            {(bullet || numbered) && <span className="text-blue-400 shrink-0">{bullet ? '•' : (t.match(/^\d+/)?.[0] || '') + '.'}</span>}
            <span>{inline(content)}</span>
          </p>
        )
      })}
    </>
  )
}

function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} className="text-white">{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className="bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-[11px] text-emerald-300">{p.slice(1, -1)}</code>
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>
    return <span key={i}>{p}</span>
  })
}

function fmtCell(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Math.abs(v) >= 1000 ? v.toLocaleString('pt-PT', { maximumFractionDigits: 2 }) : String(Math.round(v * 100) / 100)
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return v.slice(0, 10)
  return String(v)
}
