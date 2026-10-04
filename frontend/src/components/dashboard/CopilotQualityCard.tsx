"use client"
/**
 * Cartão "Qualidade do Copiloto" para o Centro de Governança de IA.
 * Mostra as métricas de avaliação (1-5) das respostas do Copiloto Global:
 * média geral, distribuição por estrela, por modo (LLM/regras), páginas
 * com mais avaliações e perguntas mal avaliadas recentes (revisão).
 * Apenas administradores recebem dados — outros papéis: o cartão
 * simplesmente não é renderizado.
 */
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { Card, CardContent } from "@/components/ui/card"
import { Star, Loader2, MessageSquareWarning, BarChart3, Users } from 'lucide-react'

type Stats = {
  total: number
  avg_rating: number | null
  distribution: Record<string, number>
  by_mode: { llm?: { n: number; avg: number | null }; rules?: { n: number; avg: number | null } }
  by_page: { page: string; n: number; avg: number }[]
  recent_low: { rating: number; question: string; page: string; when: string }[]
}

const LEVEL_BAR: Record<number, string> = {
  5: 'bg-emerald-500',
  4: 'bg-lime-500',
  3: 'bg-amber-400',
  2: 'bg-orange-500',
  1: 'bg-red-500',
}

export default function CopilotQualityCard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [hidden, setHidden] = useState(false) // 403 → sem permissão
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/ai/copilot/feedback/stats')
      .then(async res => {
        if (res.status === 403 || res.status === 401) { setHidden(true); return null }
        return res.json()
      })
      .then(data => { if (data) setStats(data) })
      .catch(() => setHidden(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card className="shadow-lg border-slate-200">
        <CardContent className="p-6 flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> A carregar qualidade do copiloto…
        </CardContent>
      </Card>
    )
  }
  if (hidden || !stats) return null

  const maxDist = Math.max(1, ...Object.values(stats.distribution || {}).map(Number))

  return (
    <Card className="shadow-lg border-slate-200">
      <CardContent className="p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-slate-800 flex items-center gap-2 text-lg">
            <Star className="w-5 h-5 text-amber-500" />
            Qualidade do Copiloto Global
          </h2>
          <span className="text-xs text-slate-400">avaliações 1-5 dos utilizadores</span>
        </div>

        {stats.total === 0 ? (
          <p className="text-sm text-slate-500">
            Ainda sem avaliações. Abra o Copiloto (Ctrl+J), faça uma pergunta
            e avalie a resposta com 👍/👎 — as métricas aparecem aqui.
          </p>
        ) : (
          <>
            {/* Resumo + distribuição */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className="text-4xl font-bold text-slate-800">
                    {stats.avg_rating?.toFixed(1) ?? '—'}
                    <span className="text-lg text-slate-400">/5</span>
                  </p>
                  <p className="text-xs text-slate-500">{stats.total} avaliações</p>
                </div>
                <div className="flex-1 space-y-1">
                  {[5, 4, 3, 2, 1].map(r => {
                    const n = Number(stats.distribution[String(r)] || 0)
                    return (
                      <div key={r} className="flex items-center gap-2">
                        <span className="text-[11px] text-slate-500 w-3 text-right">{r}</span>
                        <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                        <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
                          <div className={`h-full rounded-full ${LEVEL_BAR[r]}`}
                            style={{ width: `${(n / maxDist) * 100}%` }} />
                        </div>
                        <span className="text-[11px] text-slate-500 w-6">{n}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Por modo + top páginas */}
              <div className="space-y-3">
                <div className="flex gap-2">
                  <div className="flex-1 rounded-lg border border-slate-200 p-2.5">
                    <p className="text-[11px] text-slate-500 font-medium">LLM</p>
                    <p className="text-lg font-bold text-slate-800">
                      {stats.by_mode?.llm?.avg != null ? stats.by_mode.llm.avg.toFixed(2) : '—'}
                      <span className="text-[11px] text-slate-400 font-normal"> /5 · {stats.by_mode?.llm?.n ?? 0}</span>
                    </p>
                  </div>
                  <div className="flex-1 rounded-lg border border-slate-200 p-2.5">
                    <p className="text-[11px] text-slate-500 font-medium">Regras</p>
                    <p className="text-lg font-bold text-slate-800">
                      {stats.by_mode?.rules?.avg != null ? stats.by_mode.rules.avg.toFixed(2) : '—'}
                      <span className="text-[11px] text-slate-400 font-normal"> /5 · {stats.by_mode?.rules?.n ?? 0}</span>
                    </p>
                  </div>
                </div>
                {stats.by_page?.length > 0 && (
                  <div className="rounded-lg border border-slate-200 p-2.5">
                    <p className="text-[11px] text-slate-500 font-medium flex items-center gap-1 mb-1.5">
                      <BarChart3 className="w-3 h-3" /> Páginas mais avaliadas
                    </p>
                    <div className="space-y-1">
                      {stats.by_page.slice(0, 3).map(p => (
                        <div key={p.page} className="flex items-center justify-between text-[11px]">
                          <span className="text-slate-600 font-mono">{p.page}</span>
                          <span className="text-slate-500">{p.avg.toFixed(1)}/5 · {p.n}x</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Perguntas mal avaliadas — revisão de qualidade */}
            {stats.recent_low?.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-xs font-semibold text-red-700 flex items-center gap-1.5 mb-2">
                  <MessageSquareWarning className="w-4 h-4" />
                  Perguntas mal avaliadas (revisão recomendada)
                </p>
                <div className="space-y-1.5">
                  {stats.recent_low.map((q, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-bold shrink-0">
                        {q.rating}/5
                      </span>
                      <span className="text-slate-700 flex-1">{q.question || '—'}</span>
                      <span className="text-slate-400 font-mono shrink-0">{q.page}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <Users className="w-3 h-3" />
              As respostas com poucas estrelas orientam a melhoria contínua do modelo de suporte.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
