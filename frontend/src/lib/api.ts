// Cliente API central — todas as chamadas passam pelo proxy do Next.js
// (/api/:path* → $NEXT_PUBLIC_API_BASE/django/api/:path*).

export const API_PREFIX = '/api'

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('token')
}

export function getUserRole(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('user_role')
}

export async function apiFetch(path: string, opts: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const headers = new Headers(opts.headers || {})
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const url = `${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`
  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401 && typeof window !== 'undefined') {
    // token inválido/expirado → limpa sessão (a página de login trata do redirect)
    localStorage.removeItem('token')
  }
  return res
}

// Download autenticado de ficheiros (exports Excel, PDFs, …)
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await apiFetch(path)
  if (!res.ok) {
    let msg = `Erro ${res.status}`
    try {
      const data = await res.json()
      if (data?.error) msg = data.error
    } catch { /* resposta não-JSON */ }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
