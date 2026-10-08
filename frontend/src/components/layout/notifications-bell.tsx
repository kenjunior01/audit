"use client"
// Central de Notificações — sino no header com dropdown, polling e navegação.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Bell, CheckCheck, Info, AlertTriangle, XCircle, CheckCircle2, Inbox } from 'lucide-react'
import { apiFetch } from '@/lib/api'

type Notif = {
  id: number
  kind: string
  severity: 'info' | 'success' | 'warn' | 'critical'
  title: string
  body: string
  route: string
  unread: boolean
  created_at: string
}

const SEV_STYLE: Record<string, { icon: typeof Info, cls: string }> = {
  info: { icon: Info, cls: 'text-blue-500 bg-blue-50 dark:bg-blue-950' },
  success: { icon: CheckCircle2, cls: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950' },
  warn: { icon: AlertTriangle, cls: 'text-amber-600 bg-amber-50 dark:bg-amber-950' },
  critical: { icon: XCircle, cls: 'text-red-600 bg-red-50 dark:bg-red-950' },
}

function timeAgo(iso: string): string {
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}min`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

export function NotificationBell() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notif[]>([])
  const [unread, setUnread] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const r = await apiFetch('/notifications?limit=30')
      if (!r.ok) return
      const d = await r.json()
      setItems(d.results || [])
      setUnread(d.unread || 0)
    } catch { /* silencioso */ }
  }, [])

  useEffect(() => {
    refresh()
    const iv = setInterval(refresh, 60_000)
    return () => clearInterval(iv)
  }, [refresh])

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  async function markAll() {
    await apiFetch('/notifications/read', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: true }),
    })
    refresh()
  }

  async function markOne(id: number) {
    await apiFetch('/notifications/read', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [id] }),
    })
    refresh()
  }

  function openNotif(n: Notif) {
    if (n.unread) markOne(n.id)
    if (n.route) { setOpen(false); router.push(n.route) }
  }

  return (
    <div className="relative" ref={boxRef}>
      <button
        aria-label="Notificações"
        onClick={() => { setOpen(v => !v); if (!open) refresh() }}
        className="relative p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
      >
        <Bell className="w-5 h-5 text-slate-600 dark:text-slate-300" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center
                           rounded-full bg-red-500 text-white text-[10px] font-bold">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-[380px] max-w-[92vw] bg-white dark:bg-slate-900 rounded-xl shadow-2xl
                        border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-800">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Notificações {unread > 0 && <span className="text-red-500">({unread})</span>}
            </h3>
            <button onClick={markAll}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-600">
              <CheckCheck className="w-3.5 h-3.5" /> marcar todas
            </button>
          </div>

          <div className="max-h-[420px] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
            {items.length === 0 && (
              <div className="flex flex-col items-center py-10 text-slate-400">
                <Inbox className="w-8 h-8 mb-2" />
                <p className="text-sm">Sem notificações por agora</p>
              </div>
            )}
            {items.map(n => {
              const st = SEV_STYLE[n.severity] || SEV_STYLE.info
              const Icon = st.icon
              return (
                <button key={n.id}
                        onClick={() => openNotif(n)}
                        className={`w-full text-left flex gap-3 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/60
                                    ${n.unread ? 'bg-blue-50/40 dark:bg-blue-950/20' : ''}`}>
                  <span className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${st.cls}`}>
                    <Icon className="w-4 h-4" />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-2">
                      <span className={`text-sm truncate ${n.unread ? 'font-semibold text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300'}`}>
                        {n.title}
                      </span>
                      {n.unread && <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />}
                    </span>
                    {n.body && (
                      <span className="block text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mt-0.5">
                        {n.body}
                      </span>
                    )}
                    <span className="block text-[10px] text-slate-400 mt-1">
                      {timeAgo(n.created_at)} atrás · {n.kind}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default NotificationBell
