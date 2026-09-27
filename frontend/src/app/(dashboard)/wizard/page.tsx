"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

export default function WizardPage() {
  useRequireToken()
  const [data, setData] = useState({
    country: '',
    region: '',
    company_type: '',
    sector: '',
    size: '',
    currency: '',
    systems: ''
  })
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setLoading(true)
    apiFetch('/profile/me')
      .then(r => r.json())
      .then(d => {
        if (d && !d.error) setData(d)
      })
      .catch(() => {}) // ignore error if profile not found
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setLoading(true)
    setMessage('')
    try {
      const res = await apiFetch('/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      if (res.ok) setMessage('Perfil salvo com sucesso!')
      else setMessage('Erro ao salvar.')
    } catch {
      setMessage('Erro ao salvar.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto bg-white p-6 shadow rounded">
      <h2 className="text-xl font-medium mb-4">Configuração de Contexto</h2>
      <p className="text-gray-600 mb-6 text-sm">Preencha os dados da sua organização para que o sistema possa calibrar riscos e regras automaticamente.</p>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">País</label>
          <input className="w-full border p-2 rounded" value={data.country || ''} onChange={e=>setData({...data, country:e.target.value})} placeholder="Ex: Brasil" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Região</label>
          <input className="w-full border p-2 rounded" value={data.region || ''} onChange={e=>setData({...data, region:e.target.value})} placeholder="Ex: Sudeste" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Tipo de Empresa</label>
          <input className="w-full border p-2 rounded" value={data.company_type || ''} onChange={e=>setData({...data, company_type:e.target.value})} placeholder="Ex: Comércio" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Setor</label>
          <input className="w-full border p-2 rounded" value={data.sector || ''} onChange={e=>setData({...data, sector:e.target.value})} placeholder="Ex: Varejo" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Porte</label>
          <input className="w-full border p-2 rounded" value={data.size || ''} onChange={e=>setData({...data, size:e.target.value})} placeholder="Ex: Média" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Moeda</label>
          <input className="w-full border p-2 rounded" value={data.currency || ''} onChange={e=>setData({...data, currency:e.target.value})} placeholder="Ex: BRL" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Sistemas</label>
          <input className="w-full border p-2 rounded" value={data.systems || ''} onChange={e=>setData({...data, systems:e.target.value})} placeholder="Ex: SAP, Oracle" />
        </div>
        
        <div className="pt-4">
          <button onClick={save} disabled={loading} className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Salvando...' : 'Salvar Configurações'}
          </button>
          {message && <span className="ml-4 text-sm font-medium text-green-600">{message}</span>}
        </div>
      </div>
    </div>
  )
}
