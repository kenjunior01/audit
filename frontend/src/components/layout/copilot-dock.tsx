"use client"
/**
 * Copiloto Global da Plataforma (Omni Copilot)
 * ---------------------------------------------
 * Botão flutuante + painel de conversa disponível em TODAS as páginas.
 * - Perguntas em lingu natural sobre dados vivos: alertas, transações,
 *   casos, agentes IA, SLA, Excel, Benford, duplicados, previsões.
 * - Prompts contextuais consoante a página atual (rota).
 * - Respostas ricas: markdown, cartões de insight, tabelas de dados,
 *   ações navegáveis (router.push), followups.
 * - Botão "Briefing" → snapshot executivo proativo.
 * Atalho: Ctrl/Cmd + J.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Loader2, Send, X, Copy, Check, Presentation, Lightbulb,
  ArrowRight, RotateCcw, AlertTriangle, CheckCircle2, Info, ShieldAlert,
} from 'lucide-react'

/* ----------------------------- tipos ----------------------------- */
type Insight = { title: string; detail: string; tone: 'info' | 'warn' | 'danger' | 'success' }
type Action = { label: string; href: string }
type Table = { columns: string[]; rows: unknown[][]; shown: number; total: number }
type CopilotResponse = {
  answer: string
  mode: 'llm' | 'rules'
  tools_used: string[]
  insights: Insight[]
  actions: Action[]
  tables: Table[]
  followups: string[]
  latency_ms?: number
}
type Message = { role: 'user' | 'assistant'; content: string; data?: CopilotResponse }

/* ------------------- prompts contextuais por rota ------------------- */
const PAGE_PROMPTS: Record<string, string[]> = {
  '/': ['Resumo da plataforma', 'Previsão de risco para os próximos dias'],
  '/alerts': ['Alertas críticos de hoje', 'Alertas falsos positivos', 'Alertas dos últimos 7 dias'],
  '/transactions': ['Top 10 transações por valor', 'Transações maior que 10.000'],
  '/cases': ['Casos fora do prazo', 'Casos críticos abertos'],
  '/sla': ['Casos fora do prazo', 'Alertas sem primeira resposta'],
  '/agents': ['Como estão os agentes?', 'Previsão de risco'],
  '/excel': ['Importações de Excel recentes', 'Que análises o Excel Studio faz?'],
  '/governance': ['Resumo da plataforma', 'Como estão os agentes?'],
  '/graph': ['Deteta duplicados na base de dados', 'Perfil do fornecedor com mais alertas'],
  '/geo-risk': ['Resumo da plataforma', 'Alertas críticos'],
  '/automation': ['Como estão os agentes?', 'Casos abertos'],
  '/context': ['Resumo da plataforma', 'Importações de Excel'],
  '/integrations': ['Importações de Excel recentes', 'Resumo da plataforma'],
  '/external-actions': ['Como estão os agentes?', 'Casos críticos'],
  '/settings': ['Importações de Excel recentes', 'Resumo da plataforma'],
}
const DEFAULT_PROMPTS = ['Resumo da plataforma', 'Alertas críticos de hoje',
  'Casos fora do prazo', 'Deteta duplicados na base de dados']

const TONE_STYLE: Record<string, { icon: typeof Info; cls: string }> = {
  info: { icon: Info, cls: 'bg-sky-950/60 border-sky-800 text-sky-300' },
  warn: { icon: AlertTriangle, cls: 'bg-amber-950/60 border-amber-800 text-amber-300' },
  danger: { icon: ShieldAlert, cls: 'bg-red-950/60 border-red-800 text-red-300' },
  success: { icon: CheckCircle2, cls: 'bg-emerald-950/60 border-emerald-800 text-emerald-300' },
}

/* --------------------------- componente --------------------------- */
export function CopilotDock() {
  const router = useRouter()
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // páginas públicas sem copiloto
  const bare = pathname && ['/login', '/register', '/onboarding'].some(p => pathname.startsWith(p))

  const send = useCallback(async (question: string) => {
    const q = question.trim()
    if (!q || loading) return
    setError('')
    setInput('')
    const history = messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const r = await apiFetch('/ai/copilot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
      setMessages(m => [...m, { role: 'assistant', content: data.answer, data }])
    } catch (e: any) {
      setError(e.message)
      setMessages(m => (m.length > 0 && m[m.length - 1].role === 'user' ? m.slice(0, -1) : m))
    } finally { setLoading(false) }
  }, [loading, messages])

  const loadBriefing = useCallback(async () => {
    if (loading) return
    setError('')
    setMessages(m => [...m, { role: 'user', content: 'Briefing executivo de hoje' }])
    setLoading(true)
    try {
      const r = await apiFetch('/ai/copilot/briefing')
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
      setMessages(m => [...m, {
        role: 'assistant',
        content: data.briefing_md || 'Sem dados.',
        data: {
          answer: data.briefing_md, mode: data.mode, tools_used: ['briefing'],
          insights: data.insights || [], actions: data.actions || [],
          tables: [], followups: ['Alertas críticos de hoje', 'Casos fora do prazo'],
        },
      }])
    } catch (e: any) {
      setError(e.message)
      setMessages(m => (m.length > 0 && m[m.length - 1].role === 'user' ? m.slice(0, -1) : m))
    } finally { setLoading(false) }
  }, [loading])

  // auto-scroll para a última mensagem
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, open, loading])

  // atalho Ctrl/Cmd+J
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault()
        setOpen(v => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (bare) return null

  const prompts = (pathname && PAGE_PROMPTS[pathname]) || DEFAULT_PROMPTS

  return (
    <>
      {/* Botão flutuante */}
      <motion.button
        onClick={() => setOpen(v => !v)}
        className="fixed bottom-6 right-6 z-[60] w-14 h-14 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-[0_0_25px_rgba(59,130,246,0.5)] flex items-center justify-center text-white"
        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.94 }}
        title="Copiloto Global (Ctrl+J)" aria-label="Abrir Copiloto">
        {open ? <X className="w-6 h-6" /> : <Sparkles className="w-6 h-6" />}
        {!open && (
          <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-emerald-400 border-2 border-slate-900" />
        )}
      </motion.button>

      {/* Painel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, x: 40, y: 20 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            exit={{ opacity: 0, x: 40, y: 20 }}
            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            className="fixed bottom-24 right-6 z-[60] w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-8rem)] rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col overflow-hidden">
            {/* Cabeçalho */}
            <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-2 bg-gradient-to-r from-blue-950/60 to-slate-900">
              <Sparkles className="w-5 h-5 text-blue-400" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-white">Copiloto Global</p>
                <p className="text-[11px] text-slate-400">Dados vivos · toda a plataforma</p>
              </div>
              <button onClick={loadBriefing} disabled={loading}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-indigo-600/80 hover:bg-indigo-500 text-white text-xs disabled:opacity-50"
                title="Briefing executivo">
                <Presentation className="w-3.5 h-3.5" /> Briefing
              </button>
              {messages.length > 0 && (
                <button onClick={() => setMessages([])} disabled={loading}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                  title="Limpar conversa">
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Mensagens */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && !loading && (
                <div className="text-center py-6">
                  <Sparkles className="w-9 h-9 text-blue-500 mx-auto mb-3" />
                  <p className="text-slate-200 font-medium text-sm">Pergunte o que quiser à plataforma</p>
                  <p className="text-xs text-slate-500 mt-1 px-4">
                    Alertas, transações, casos, agentes IA, SLA, Benford, duplicados,
                    previsões — respondo com números reais e levo-o onde precisa.
                  </p>
                </div>
              )}

              {messages.map((m, i) => m.role === 'user' ? (
                <div key={i} className="flex justify-end">
                  <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[85%] text-sm">{m.content}</div>
                </div>
              ) : (
                <CopilotMessage key={i} data={m.data} fallback={m.content}
                  onAction={href => { router.push(href) }}
                  onFollowup={q => send(q)} />
              ))}

              {loading && (
                <div className="flex items-center gap-2 text-slate-400 text-sm px-1">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  O Copiloto está a consultar a plataforma…
                </div>
              )}
              {error && (
                <div className="rounded-lg p-2.5 text-xs bg-red-950/50 text-red-300 border border-red-800">{error}</div>
              )}
            </div>

            {/* Prompts rápidos contextuais */}
            {messages.length === 0 && (
              <div className="px-4 pb-2 flex flex-wrap gap-1.5">
                {prompts.map(p => (
                  <button key={p} onClick={() => send(p)} disabled={loading}
                    className="text-[11px] px-2.5 py-1.5 rounded-full border border-slate-700 text-slate-300 hover:border-blue-500 hover:text-blue-300 disabled:opacity-40">
                    {p}
                  </button>
                ))}
              </div>
            )}

            {/* Input */}
            <div className="border-t border-slate-800 p-3 flex gap-2">
              <input value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                placeholder="Ex.: quais os casos fora do prazo?"
                disabled={loading}
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500 disabled:opacity-50" />
              <button onClick={() => send(input)} disabled={loading || !input.trim()}
                className="px-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

/* ------------------- mensagem rica do copiloto ------------------- */
function CopilotMessage({ data, fallback, onAction, onFollowup }: {
  data?: CopilotResponse
  fallback: string
  onAction: (href: string) => void
  onFollowup: (q: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(fallback)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard indisponível */ }
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full space-y-2.5">
        <div className="bg-slate-800/70 rounded-2xl rounded-bl-sm px-3.5 py-3 text-sm text-slate-200 relative group">
          <Md text={data?.answer || fallback} />
          <button onClick={copyAnswer}
            className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded bg-slate-900/80 text-slate-400 hover:text-slate-200"
            title="Copiar resposta">
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </button>
          {data && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1.5 text-[10px] text-slate-500">
              {data.tools_used.map(t => (
                <span key={t} className="px-1.5 py-0.5 rounded-full bg-slate-900 border border-slate-700">{t}</span>
              ))}
              <span className="px-1.5 py-0.5 rounded-full bg-slate-900 border border-slate-700">
                {data.mode === 'llm' ? 'LLM' : 'regras'}
              </span>
              {data.latency_ms !== undefined && <span>{data.latency_ms} ms</span>}
            </div>
          )}
        </div>

        {/* Cartões de insight */}
        {data?.insights?.map((ins, i) => {
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

        {/* Tabelas de dados vivos */}
        {data?.tables?.map((t, i) => (
          <div key={i} className="rounded-xl border border-slate-800 bg-slate-950 p-2.5 overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-800">
                  {t.columns.map(c => <th key={c} className="py-1 px-1.5 font-medium whitespace-nowrap">{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {t.rows.map((row, ri) => (
                  <tr key={ri} className="border-b border-slate-900 text-slate-300">
                    {row.map((v, ci) => <td key={ci} className="py-1 px-1.5 whitespace-nowrap">{fmtCell(v)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            {t.total > t.shown && (
              <p className="text-[10px] text-slate-500 mt-1.5">{t.shown} de {t.total} linhas</p>
            )}
          </div>
        ))}

        {/* Ações navegáveis */}
        {data?.actions && data.actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.actions.map((a, i) => (
              <button key={i} onClick={() => onAction(a.href)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium">
                {a.label} <ArrowRight className="w-3 h-3" />
              </button>
            ))}
          </div>
        )}

        {/* Followups */}
        {data?.followups && data.followups.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.followups.map((fu, i) => (
              <button key={i} onClick={() => onFollowup(fu)}
                className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border border-blue-800 text-blue-300 hover:bg-blue-950">
                <Lightbulb className="w-3 h-3" /> {fu}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------- markdown-lite + formatação ------------------- */
function Md({ text }: { text: string }) {
  const lines = (text || '').split('\n')
  return (
    <>
      {lines.map((line, i) => {
        const t = line.trim()
        if (!t) return <div key={i} className="h-1.5" />
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
