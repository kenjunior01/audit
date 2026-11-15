"use client"
// Motores de IA — cartão para a página de Integrações.
// Mostra a cadeia LLM (NVIDIA NIM → provider primário) com disponibilidade
// ao vivo (GET /ai/llm/status) e ping real (POST /ai/llm/test, auditor/admin).
import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { BrainCircuit, Loader2, RefreshCw, Zap, CheckCircle2, XCircle } from 'lucide-react'
import { useLang } from '@/lib/i18n'

type Provider = {
  id: string, label: string, style: string, base_url: string, model: string,
  auth: boolean, reasoning: boolean, configured: boolean, available: boolean,
  priority: number,
}
type StatusRes = { providers: Provider[], chain: string[], active_hint: string, any_available: boolean }
type TestRes = { ok: boolean, answer?: string, provider?: string, model?: string, latency_ms?: number, error?: string }

export function AiEnginesCard() {
  const { t } = useLang()
  const [status, setStatus] = useState<StatusRes | null>(null)
  const [busy, setBusy] = useState(false)
  const [testRes, setTestRes] = useState<TestRes | null>(null)
  const [testBusy, setTestBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const r = await apiFetch('/ai/llm/status')
      if (r.ok) setStatus(await r.json())
    } catch { /* cartão informativo — falha silenciosa */ }
    finally { setBusy(false) }
  }, [])
  useEffect(() => { load() /* eslint-disable-line react-hooks/exhaustive-deps */ }, [load])

  async function runTest() {
    setTestBusy(true); setTestRes(null)
    try {
      const r = await apiFetch('/ai/llm/test', { method: 'POST' })
      setTestRes(await r.json())
    } catch { setTestRes({ ok: false, error: t('ai.test_fail') }) }
    finally { setTestBusy(false) }
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-blue-600" />
          <p className="text-sm font-semibold text-gray-800 dark:text-slate-100">{t('ai.engines_title')}</p>
          <span className="text-[11px] text-slate-400">{t('ai.engines_sub')}</span>
        </div>
        <div className="flex gap-2">
          <button onClick={load} disabled={busy}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1.5 disabled:opacity-50 transition-colors">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} {t('ai.refresh')}
          </button>
          <button onClick={runTest} disabled={testBusy}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-1.5 disabled:opacity-50 transition-colors">
            {testBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />} {t('ai.test')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {(status?.providers || ([
          { id: 'nvidia', label: 'NVIDIA NIM', style: 'openai-compatible', base_url: '—', model: '—', auth: false, reasoning: false, configured: false, available: false, priority: 1 },
          { id: 'primary', label: 'Local', style: 'ollama', base_url: '—', model: '—', auth: false, reasoning: false, configured: false, available: false, priority: 2 },
        ] as Provider[])).map(p => (
          <div key={p.id} className="rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2.5 flex items-center gap-2.5">
            {p.available ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              : <XCircle className="w-4 h-4 text-slate-300 dark:text-slate-600 shrink-0" />}
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-800 dark:text-slate-200 flex items-center gap-2">
                {p.label || p.id}
                {p.auth && <span className="px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-[10px]">API key</span>}
                {p.reasoning && <span className="px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 text-[10px]">reasoning</span>}
                {p.available && <span className="text-[10px] text-emerald-600 font-medium">{t('ai.online')}</span>}
              </p>
              {'model' in p && <p className="text-[11px] text-slate-400 truncate">{p.model} · {p.base_url}</p>}
            </div>
            <span className="ml-auto text-[10px] text-slate-400 shrink-0">#{p.priority ?? p.id}</span>
          </div>
        ))}
      </div>

      {status && !status.any_available && (
        <p className="text-xs text-amber-600 mt-2">{t('ai.none_available')}</p>
      )}

      {testRes && (
        <div className={`mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 text-xs ${testRes.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-500'}`}>
          {testRes.ok ? (
            <p>
              <b>{t('ai.test_ok')}</b> {testRes.provider} · {testRes.model} · {testRes.latency_ms}ms —
              <span className="text-slate-500 dark:text-slate-400"> “{testRes.answer}”</span>
            </p>
          ) : (
            <p><b>{t('ai.test_fail')}</b> {testRes.error}</p>
          )}
        </div>
      )}
    </div>
  )
}
