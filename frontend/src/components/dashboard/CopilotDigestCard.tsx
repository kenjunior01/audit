"use client"
/**
 * Cartão "Digest Programado" para a página inicial.
 * Mostra o resumo automático gerado por cron/celery beat (push proativo):
 * headline + KPIs + sinais prioritários + qualidade do copiloto.
 * Admin pode gerar um digest imediatamente (POST /ai/copilot/digest).
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch, apiDownload } from '@/lib/api'
import { Card, CardContent } from "@/components/ui/card"
import {
  CalendarClock, Loader2, RefreshCcw, Zap, ShieldAlert, AlertTriangle,
  Info, Mail, Archive, MailX, Star, FileDown,
} from 'lucide-react'

type Signal = { level: 'critical' | 'warning' | 'info'; title: string; detail: string; action?: { label: string; href: string } }
type DigestPayload = {
  period: string
  headline: string
  narrative?: string
  kpis?: Record<string, unknown>
  signals: Signal[]
  signals_count: number
  critical_count: number
  feedback?: { total: number; avg_rating: number | null; recent_low?: { rating: number; question: string }[] }
  generated_at: string
}
type DigestRow = {
  id: number; period: string; day: string; status: string
  recipients?: string; signals_count: number; critical_count: number
  avg_rating: number | null; created_at: string; payload: DigestPayload
}

const LEVEL_STYLE: Record<string, { icon: typeof Info; cls: string }> = {
  critical: { icon: ShieldAlert, cls: 'bg-red-950/60 border-red-800 text-red-300' },
  warning: { icon: AlertTriangle, cls: 'bg-amber-950/60 border-amber-800 text-amber-300' },
  info: { icon: Info, cls: 'bg-sky-950/60 border-sky-800 text-sky-300' },
}

function StatusBadge({ status, recipients }: { status: string; recipients?: string }) {
  if (status === 'sent')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/60 border border-emerald-800 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
        <Mail className="w-3 h-3" /> Enviado{recipients ? ` · ${recipients.split(',').length} destinatário(s)` : ''}
      </span>
    )
  if (status === 'failed')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-950/60 border border-red-800 px-2 py-0.5 text-[10px] font-medium text-red-300">
        <MailX className="w-3 h-3" /> Falha no envio
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-400">
      <Archive className="w-3 h-3" /> Armazenado (sem email)
    </span>
  )
}

export default function CopilotDigestCard() {
  const router = useRouter()
  const [digest, setDigest] = useState<DigestRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [notice, setNotice] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const r = await apiFetch('/ai/copilot/digest')
      const data = await r.json()
      if (r.ok) setDigest(data.digest ?? null)
    } catch { /* silencioso — cartão é best-effort */ }
    finally { setLoading(false) }
  }

  const generate = async () => {
    setGenerating(true)
    setNotice('')
    try {
      const r = await apiFetch('/ai/copilot/digest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: 'daily' }),
      })
      const data = await r.json()
      if (r.status === 403) setNotice('Apenas administradores podem gerar o digest.')
      else if (!r.ok) setNotice(data.error || `Erro ${r.status}`)
      else { setNotice('Digest gerado com sucesso.'); await load() }
    } catch { setNotice('Não foi possível gerar o digest.') }
    finally { setGenerating(false) }
  }

  const downloadPdf = async () => {
    setDownloading(true)
    setNotice('')
    try {
      await apiDownload('/ai/copilot/digest/pdf',
        `digest-${digest?.period || 'daily'}-${digest?.day || new Date().toISOString().slice(0, 10)}.pdf`)
    } catch { setNotice('Não foi possível descarregar o PDF.') }
    finally { setDownloading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading && !digest) {
    return (
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-6 flex items-center gap-3 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
          A procurar o digest programado…
        </CardContent>
      </Card>
    )
  }

  if (!digest) {
    return (
      <Card className="bg-slate-900 border-slate-800 border-dashed">
        <CardContent className="p-6 flex flex-wrap items-center gap-3 text-sm text-slate-400">
          <CalendarClock className="w-5 h-5 text-indigo-400" />
          <span>
            Ainda não há digest programado. Agende com{' '}
            <code className="text-xs bg-slate-800 px-1.5 py-0.5 rounded">manage.py copilot_digest</code>{' '}
            ou celery beat (AUDIT_DIGEST_ENABLED=true).
          </span>
          <button onClick={generate} disabled={generating}
            className="ml-auto flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-40">
            <Zap className="w-3.5 h-3.5" /> {generating ? 'A gerar…' : 'Gerar agora'}
          </button>
        </CardContent>
      </Card>
    )
  }

  const p = digest.payload || ({} as DigestPayload)
  const signals = (p.signals || []).slice(0, 3)
  const fb = p.feedback || { total: 0, avg_rating: null }

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-6 space-y-4">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.4)]">
              <CalendarClock className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-sm">
                Digest Programado — Copiloto Global
              </h3>
              <p className="text-[11px] text-slate-500">
                Resumo automático {digest.period === 'weekly' ? 'semanal' : 'diário'} · referente a {digest.day}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={digest.status} recipients={digest.recipients} />
            <button onClick={load} disabled={loading}
              className="p-2 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-slate-800 disabled:opacity-40"
              title="Atualizar">
              <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={generate} disabled={generating}
              className="p-2 rounded-lg text-slate-400 hover:text-amber-400 hover:bg-slate-800 disabled:opacity-40"
              title="Gerar digest agora (admin)">
              <Zap className={`w-4 h-4 ${generating ? 'animate-pulse text-amber-400' : ''}`} />
            </button>
            <button onClick={downloadPdf} disabled={downloading}
              className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800 disabled:opacity-40"
              title="Descarregar PDF executivo">
              {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {notice && (
          <p className="text-xs text-amber-400 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> {notice}
          </p>
        )}

        {/* Headline */}
        <p className="text-sm font-semibold text-slate-200">{p.headline}</p>

        {/* Sinais prioritários */}
        {signals.length > 0 && (
          <div className="grid grid-cols-1 gap-2">
            {signals.map((s, i) => {
              const tone = LEVEL_STYLE[s.level] || LEVEL_STYLE.info
              const Icon = tone.icon
              return (
                <button key={i} onClick={() => s.action?.href && router.push(s.action.href)}
                  className={`rounded-xl border px-3 py-2.5 text-left ${tone.cls} ${s.action?.href ? 'cursor-pointer hover:brightness-125' : 'cursor-default'}`}>
                  <div className="flex items-start gap-2">
                    <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-semibold">{s.title}</p>
                      <p className="text-[11px] opacity-80 mt-0.5">{s.detail}</p>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Rodapé: qualidade + timestamp */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
          {fb.avg_rating !== null && fb.avg_rating !== undefined && (
            <span className="inline-flex items-center gap-1">
              <Star className="w-3 h-3 text-amber-400" />
              Qualidade do copiloto: <b className="text-slate-300">{fb.avg_rating}/5</b> ({fb.total} avaliações)
            </span>
          )}
          <span className="ml-auto">
            Gerado {new Date(digest.created_at).toLocaleString('pt-PT')}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
