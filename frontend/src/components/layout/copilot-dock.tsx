"use client"
/**
 * Copiloto Global da Plataforma (Omni Copilot) — v3
 * --------------------------------------------------
 * Botão flutuante + painel de conversa disponível em TODAS as páginas.
 * - Perguntas em lingu natural sobre dados vivos: alertas, transações,
 *   casos, agentes IA, SLA, Excel, Benford, duplicados, previsões.
 * - STREAMING SSE (/ai/copilot/stream): o utilizador vê a execução
 *   agéntica em tempo real (ferramentas consultadas, duração de cada uma)
 *   com fallback automático para o endpoint síncrono.
 * - TRANSPARÊNCIA: trace agéntico por resposta (ferramenta · duração).
 * - FEEDBACK (👍/👎) por resposta → /ai/copilot/feedback (ciclo de
 *   melhoria contínua do modelo de suporte).
 * - EXPORTAR conversa em Markdown; conversa persistente por sessão.
 * - Prompts contextuais consoante a página atual (rota).
 * - INTEGRAÇÃO CONTEXTUAL: qualquer página pode chamar askCopilot(pergunta)
 *   (evento 'copilot:ask') — o painel abre e envia com contexto.
 * - VOZ: dita a pergunta com o microfone (SpeechRecognition pt-PT).
 * Atalho: Ctrl/Cmd + J.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { COPILOT_ASK_EVENT } from '@/lib/copilot'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Loader2, Send, X, Copy, Check, Presentation, Lightbulb,
  ArrowRight, RotateCcw, AlertTriangle, CheckCircle2, Info, ShieldAlert,
  Download, ThumbsUp, ThumbsDown, XCircle, Zap, Mic, MicOff,
} from 'lucide-react'

/* ----------------------------- tipos ----------------------------- */
type Insight = { title: string; detail: string; tone: 'info' | 'warn' | 'danger' | 'success' }
type Action = { label: string; href: string }
type Table = { columns: string[]; rows: unknown[][]; shown: number; total: number }
type TraceEntry = { tool: string; title: string; ok?: boolean; ms?: number }
type CopilotResponse = {
  answer: string
  mode: 'llm' | 'rules'
  tools_used: string[]
  trace?: TraceEntry[]
  insights: Insight[]
  actions: Action[]
  tables: Table[]
  followups: string[]
  latency_ms?: number
}
type Message = { role: 'user' | 'assistant'; content: string; data?: CopilotResponse; rated?: number }
type LiveTrace = TraceEntry
type Signal = {
  level: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  action: { label: string; href: string }
  question: string
}

/* ------------------- prompts contextuais por rota ------------------- */
const PAGE_PROMPTS: Record<string, string[]> = {
  '/': ['Resumo da plataforma', 'Previsão de risco para os próximos dias'],
  '/alerts': ['Alertas críticos de hoje', 'Explica o alerta mais recente', 'Alertas falsos positivos'],
  '/transactions': ['Top 10 transações por valor', 'Transações maior que 10.000', 'Compara esta semana com a semana passada'],
  '/cases': ['Casos fora do prazo', 'Explica o caso mais recente', 'Casos críticos abertos'],
  '/sla': ['Casos fora do prazo', 'Alertas sem primeira resposta', 'E agora?'],
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
const DEFAULT_PROMPTS = ['O que sabes fazer?', 'Resumo da plataforma',
  'Alertas críticos de hoje', 'Explica o alerta mais recente',
  'Casos fora do prazo']

const TONE_STYLE: Record<string, { icon: typeof Info; cls: string }> = {
  info: { icon: Info, cls: 'bg-sky-950/60 border-sky-800 text-sky-300' },
  warn: { icon: AlertTriangle, cls: 'bg-amber-950/60 border-amber-800 text-amber-300' },
  danger: { icon: ShieldAlert, cls: 'bg-red-950/60 border-red-800 text-red-300' },
  success: { icon: CheckCircle2, cls: 'bg-emerald-950/60 border-emerald-800 text-emerald-300' },
}

const SIGNAL_STYLE: Record<string, { bar: string; chip: string }> = {
  critical: { bar: 'border-l-red-500', chip: 'bg-red-950/60 border-red-800 text-red-300' },
  warning: { bar: 'border-l-amber-500', chip: 'bg-amber-950/60 border-amber-800 text-amber-300' },
  info: { bar: 'border-l-sky-500', chip: 'bg-sky-950/60 border-sky-800 text-sky-300' },
}

/* --------------------------- componente --------------------------- */
const CHAT_STORAGE_KEY = 'copilot-chat-v1'

function loadStoredMessages(): Message[] {
  // restaura a conversa entre navegações e refresh (por sessão do browser)
  try {
    if (typeof window === 'undefined') return []
    const raw = sessionStorage.getItem(CHAT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(-40) : []
  } catch { return [] }
}

export function CopilotDock() {
  const router = useRouter()
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>(loadStoredMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [liveStatus, setLiveStatus] = useState('')
  const [liveTrace, setLiveTrace] = useState<LiveTrace[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [signalsOpen, setSignalsOpen] = useState(false)
  const [listening, setListening] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const recRef = useRef<any>(null)

  // persiste a conversa (sessionStorage — sobrevive a navegação e refresh)
  useEffect(() => {
    try { sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-40))) }
    catch { /* quota/privacidade — ignora */ }
  }, [messages])

  // páginas públicas sem copiloto
  const bare = pathname && ['/login', '/register', '/onboarding'].some(p => pathname.startsWith(p))

  // sinais proativos — carregados no arranque e revalidados ao abrir o painel
  const loadSignals = useCallback(async () => {
    try {
      const r = await apiFetch('/ai/copilot/insights')
      if (!r.ok) return
      const data = await r.json()
      if (Array.isArray(data.signals)) setSignals(data.signals)
    } catch { /* sinais são best-effort — nunca bloqueiam o copiloto */ }
  }, [])

  useEffect(() => {
    if (!bare) loadSignals()
  }, [bare, loadSignals])

  const send = useCallback(async (question: string) => {
    const q = question.trim()
    if (!q || loading) return
    setError('')
    setInput('')
    const history = messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: q }])
    setLoading(true)
    setLiveTrace([])
    setLiveStatus('A interpretar a pergunta…')

    const finish = (data: CopilotResponse) => {
      setMessages(m => [...m, { role: 'assistant', content: data.answer, data }])
      setLiveTrace([])
      setLiveStatus('')
    }
    const fail = (msg: string) => {
      setLiveTrace([])
      setLiveStatus('')
      setError(msg)
      setMessages(m => (m.length > 0 && m[m.length - 1].role === 'user' ? m.slice(0, -1) : m))
    }

    try {
      /* streaming SSE — execução agéntica em tempo real */
      const res = await apiFetch('/ai/copilot/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question: q, history, page: pathname }),
      })
      if (!res.ok || !res.body) throw new Error('stream-indisponível')
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let receivedFinal = false
      while (!receivedFinal) {
        const chunk = await reader.read()
        if (chunk.done) break
        buf += decoder.decode(chunk.value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          let ev = 'message'
          let dataStr = ''
          for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) ev = line.slice(7).trim()
            else if (line.startsWith('data: ')) dataStr += line.slice(6)
          }
          if (!dataStr) continue
          let data: any
          try { data = JSON.parse(dataStr) } catch { continue }
          if (ev === 'status') {
            setLiveStatus(data.msg || 'A trabalhar…')
          } else if (ev === 'tool_start') {
            setLiveTrace(t => [...t, { tool: data.tool, title: data.title }])
          } else if (ev === 'tool_done') {
            setLiveTrace(t => {
              const idx = t.findIndex(x => x.tool === data.tool && x.ms === undefined)
              if (idx >= 0) {
                const cp = [...t]
                cp[idx] = { ...cp[idx], ok: data.ok, ms: data.ms }
                return cp
              }
              return [...t, { tool: data.tool, title: data.title, ok: data.ok, ms: data.ms }]
            })
          } else if (ev === 'final') {
            receivedFinal = true
            finish(data as CopilotResponse)
          } else if (ev === 'error') {
            throw new Error(data.error || 'Erro no copiloto')
          }
        }
      }
      if (!receivedFinal) throw new Error('Resposta incompleta do copiloto')
    } catch (e: any) {
      /* fallback: endpoint síncrono (proxies sem streaming, SSE bloqueado) */
      try {
        const r = await apiFetch('/ai/copilot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q, history, page: pathname }),
        })
        const data = await r.json()
        if (!r.ok) throw new Error(data.error || `Erro ${r.status}`)
        setError('')
        finish(data)
      } catch (e2: any) {
        fail(e2.message)
      }
    } finally { setLoading(false) }
  }, [loading, messages, pathname])

  /* -------- integração contextual: askCopilot() de qualquer página -------
   * qualquer componente dispara askCopilot('Explica o alerta 42') e o
   * dock abre e envia a pergunta com o contexto da página atual. */
  useEffect(() => {
    const onAsk = (e: Event) => {
      const q = (e as CustomEvent).detail?.question
      if (!q) return
      setOpen(true)
      send(q)
    }
    window.addEventListener(COPILOT_ASK_EVENT, onAsk)
    return () => window.removeEventListener(COPILOT_ASK_EVENT, onAsk)
  }, [send])

  /* -------- voz: dita a pergunta (SpeechRecognition, pt-PT) -------- */
  const toggleVoice = useCallback(() => {
    if (listening) {
      recRef.current?.stop()
      setListening(false)
      return
    }
    const SR = (typeof window !== 'undefined' &&
      ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition))
    if (!SR) return
    try {
      const rec = new SR()
      rec.lang = 'pt-PT'
      rec.interimResults = false
      rec.maxAlternatives = 1
      rec.onresult = (ev: any) => {
        const said = ev.results?.[0]?.[0]?.transcript || ''
        if (said) setInput(prev => (prev ? `${prev} ${said}` : said))
      }
      rec.onend = () => setListening(false)
      rec.onerror = () => setListening(false)
      recRef.current = rec
      rec.start()
      setListening(true)
    } catch { setListening(false) }
  }, [listening])
  const voiceSupported = typeof window !== 'undefined' &&
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  const rate = useCallback(async (idx: number, rating: number) => {
    const m = messages[idx]
    if (!m?.data || m.rated) return
    setMessages(list => list.map((x, i) => i === idx ? { ...x, rated: rating } : x))
    try {
      await apiFetch('/ai/copilot/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rating,
          question: messages[idx - 1]?.role === 'user' ? messages[idx - 1].content : '',
          answer: (m.data?.answer || m.content || '').slice(0, 2000),
          mode: m.data?.mode || '',
          page: pathname,
        }),
      })
    } catch { /* feedback é best-effort — não interrompe a conversa */ }
  }, [messages, pathname])

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

  // exportar conversa em Markdown
  const exportTranscript = useCallback(() => {
    if (!messages.length) return
    const lines: string[] = ['# Conversa com o Copiloto Global', '',
      `_Exportada em ${new Date().toLocaleString('pt-PT')}_`, '']
    for (const m of messages) {
      if (m.role === 'user') {
        lines.push(`**Utilizador:** ${m.content}`, '')
      } else {
        lines.push(`**Copiloto:**`, '', m.content, '')
        const tr = m.data?.trace
        if (tr?.length) {
          lines.push(
            `> Ferramentas: ${tr.map(t => `${t.title} (${t.ms ?? '—'} ms${t.ok === false ? ', falhou' : ''})`).join(' · ')}`,
            `> Modo: ${m.data?.mode === 'llm' ? 'LLM' : 'regras'}${m.data?.latency_ms !== undefined ? ` · ${m.data.latency_ms} ms` : ''}`,
            '')
        }
      }
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `copiloto-conversa-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '')}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [messages])

  // auto-scroll para a última mensagem
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, open, loading, liveTrace, liveStatus])

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
        onClick={() => setOpen(v => { const nv = !v; if (nv) loadSignals(); return nv })}
        className="fixed bottom-6 right-6 z-[60] w-14 h-14 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-[0_0_25px_rgba(59,130,246,0.5)] flex items-center justify-center text-white"
        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.94 }}
        title="Copiloto Global (Ctrl+J)" aria-label="Abrir Copiloto">
        {open ? <X className="w-6 h-6" /> : <Sparkles className="w-6 h-6" />}
        {!open && signals.length > 0 ? (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 border-2 border-slate-900 text-[10px] font-bold flex items-center justify-center">
            {signals.length}
          </span>
        ) : !open && (
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
                <p className="text-[11px] text-slate-400">Streaming agéntico · toda a plataforma · contexto da página</p>
              </div>
              <button onClick={loadBriefing} disabled={loading}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-indigo-600/80 hover:bg-indigo-500 text-white text-xs disabled:opacity-50"
                title="Briefing executivo">
                <Presentation className="w-3.5 h-3.5" /> Briefing
              </button>
              {messages.length > 0 && (
                <button onClick={exportTranscript} disabled={loading}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                  title="Exportar conversa (Markdown)">
                  <Download className="w-3.5 h-3.5" />
                </button>
              )}
              {messages.length > 0 && (
                <button onClick={() => setMessages([])} disabled={loading}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                  title="Limpar conversa">
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Sinais proativos — o copiloto avisa sem ser perguntado */}
            {signals.length > 0 && (
              <div className="border-b border-slate-800 bg-slate-950/60">
                <button onClick={() => setSignalsOpen(v => !v)}
                  className="w-full px-4 py-2 flex items-center gap-2 text-xs text-amber-300 hover:bg-slate-900 transition-colors">
                  <Zap className="w-3.5 h-3.5" />
                  <span className="flex-1 text-left font-medium">
                    {signals.length} sinal{signals.length > 1 ? 'es' : ''} precisam de atenção
                  </span>
                  <span className="text-slate-500">{signalsOpen ? '△' : '▽'}</span>
                </button>
                {signalsOpen && (
                  <div className="px-3 pb-3 space-y-2 max-h-52 overflow-y-auto">
                    {signals.map((s, i) => {
                      const st = SIGNAL_STYLE[s.level] || SIGNAL_STYLE.info
                      return (
                        <div key={i} className={`rounded-lg border border-slate-800 border-l-4 ${st.bar} bg-slate-900 p-2.5`}>
                          <p className="text-xs font-semibold text-slate-200">{s.title}</p>
                          <p className="text-[11px] text-slate-400 mt-0.5">{s.detail}</p>
                          <div className="flex flex-wrap gap-1.5 mt-1.5">
                            <button onClick={() => send(s.question)} disabled={loading}
                              className="text-[10px] px-2 py-1 rounded-md bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40">
                              Perguntar ao copiloto
                            </button>
                            <button onClick={() => { router.push(s.action.href); setOpen(false) }}
                              className="text-[10px] px-2 py-1 rounded-md border border-slate-700 text-slate-300 hover:border-blue-500 hover:text-blue-300">
                              {s.action.label}
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Mensagens */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && !loading && (
                <div className="text-center py-6">
                  <Sparkles className="w-9 h-9 text-blue-500 mx-auto mb-3" />
                  <p className="text-slate-200 font-medium text-sm">Pergunte o que quiser à plataforma</p>
                  <p className="text-xs text-slate-500 mt-1 px-4">
                    Alertas, transações, casos, agentes IA, SLA, Benford, duplicados,
                    previsões — respondo com números reais e levo-o onde precisa.
                    Vê a minha execução em tempo real e avalia as respostas com 👍/👎.
                  </p>
                </div>
              )}

              {messages.map((m, i) => m.role === 'user' ? (
                <div key={i} className="flex justify-end">
                  <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[85%] text-sm">{m.content}</div>
                </div>
              ) : (
                <CopilotMessage key={i} data={m.data} fallback={m.content}
                  rated={m.rated}
                  onRate={rating => rate(i, rating)}
                  onAction={href => { router.push(href) }}
                  onFollowup={q => send(q)} />
              ))}

              {loading && (
                <div className="space-y-1.5 px-1">
                  <div className="flex items-center gap-2.5 text-slate-400 text-sm">
                    <span className="flex gap-1 items-end h-3">
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
                    </span>
                    {liveStatus || 'O Copiloto está a consultar a plataforma…'}
                  </div>
                  {liveTrace.map((t, i) => (
                    <div key={`${t.tool}-${i}`} className="flex items-center gap-2 text-[11px] pl-1">
                      {t.ms !== undefined ? (
                        t.ok === false
                          ? <XCircle className="w-3 h-3 text-red-400 shrink-0" />
                          : <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                      ) : <Loader2 className="w-3 h-3 animate-spin text-blue-400 shrink-0" />}
                      <span className={t.ms !== undefined ? 'text-slate-400' : 'text-slate-200'}>{t.title}</span>
                      {t.ms !== undefined && <span className="text-slate-600">{t.ms} ms</span>}
                    </div>
                  ))}
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
              {voiceSupported && (
                <button onClick={toggleVoice} disabled={loading}
                  className={`px-2.5 rounded-xl border transition-colors disabled:opacity-40 ${
                    listening
                      ? 'bg-red-600 border-red-500 text-white animate-pulse'
                      : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-blue-300 hover:border-blue-500'}`}
                  title={listening ? 'A ouvir… clique para parar' : 'Ditar pergunta (voz)'}
                  aria-label="Ditar pergunta">
                  {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                </button>
              )}
              <input value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                placeholder={listening ? 'A ouvir… fale agora' : 'Ex.: quais os casos fora do prazo?'}
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
function CopilotMessage({ data, fallback, rated, onRate, onAction, onFollowup }: {
  data?: CopilotResponse
  fallback: string
  rated?: number
  onRate?: (rating: number) => void
  onAction: (href: string) => void
  onFollowup: (q: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const traceEntries: TraceEntry[] = data?.trace?.length
    ? data.trace
    : (data?.tools_used || []).map(t => ({ tool: t, title: t }))
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
              {traceEntries.map((t, i) => (
                <span key={`${t.tool}-${i}`} title={t.ms !== undefined ? `${t.ms} ms` : undefined}
                  className="px-1.5 py-0.5 rounded-full bg-slate-900 border border-slate-700">
                  {t.title}{t.ms !== undefined ? ` · ${t.ms} ms` : ''}
                </span>
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

        {/* Feedback do utilizador (ciclo de melhoria contínua) */}
        {onRate && (
          <div className="flex items-center gap-1.5">
            <button onClick={() => onRate(5)} disabled={!!rated}
              className={`p-1 rounded transition-colors ${rated === 5 ? 'text-emerald-400' : 'text-slate-600 hover:text-emerald-400 disabled:opacity-40'}`}
              title="Resposta útil">
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => onRate(1)} disabled={!!rated}
              className={`p-1 rounded transition-colors ${rated === 1 ? 'text-red-400' : 'text-slate-600 hover:text-red-400 disabled:opacity-40'}`}
              title="Resposta pouco útil">
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
            {rated && <span className="text-[10px] text-slate-500">Obrigado pelo feedback!</span>}
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
