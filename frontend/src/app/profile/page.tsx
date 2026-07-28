"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

type Profile = {
  user_id: string
  country?: string | null
  department?: string | null
  sector: string
  org_structure: string
  base_currency: string
  persona: string
}

export default function ProfilePage() {
  useRequireToken()
  const [p, setP] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState(false)
  useEffect(() => {
    setLoading(true)
    apiFetch('/profile/me').then(r=>r.json()).then(setP).catch(()=>setError('Erro ao carregar')).finally(()=>setLoading(false))
  }, [])
  const save = async () => {
    if (!p) return
    setLoading(true)
    setOk(false)
    setError('')
    const r = await apiFetch('/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
    if (r.ok) setOk(true)
    else setError('Erro ao guardar')
    setLoading(false)
  }
  return (
    <div className="space-y-4 max-w-xl">
      <h2 className="text-lg font-medium">Meu Perfil de Contexto</h2>
      {loading && <div className="text-sm text-gray-600">Carregando...</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}
      {ok && <div className="text-sm text-green-700">Guardado</div>}
      {p && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input className="border p-2" placeholder="País" value={p.country || ''} onChange={e=>setP({...p, country: e.target.value})} />
          <input className="border p-2" placeholder="Departamento" value={p.department || ''} onChange={e=>setP({...p, department: e.target.value})} />
          <input className="border p-2" placeholder="Setor" value={p.sector || ''} onChange={e=>setP({...p, sector: e.target.value})} />
          <input className="border p-2" placeholder="Estrutura" value={p.org_structure || ''} onChange={e=>setP({...p, org_structure: e.target.value})} />
          <input className="border p-2" placeholder="Moeda Base" value={p.base_currency || ''} onChange={e=>setP({...p, base_currency: e.target.value})} />
          <input className="border p-2" placeholder="Persona" value={p.persona || ''} onChange={e=>setP({...p, persona: e.target.value})} />
        </div>
      )}
      <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={save} disabled={loading || !p}>{loading ? 'Guardando...' : 'Guardar'}</button>
    </div>
  )
}
