"use client"
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

export default function UploadPage() {
  useRequireToken()
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('general')
  const [country, setCountry] = useState('')
  const [sector, setSector] = useState('')
  const [text, setText] = useState('')
  const [res, setRes] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    setLoading(true)
    const fd = new FormData()
    if (file) fd.append('file', file)
    if (title) fd.append('title', title)
    if (docType) fd.append('doc_type', docType)
    if (country) fd.append('country', country)
    if (sector) fd.append('sector', sector)
    if (text) fd.append('text', text)
    const r = await apiFetch('/upload/document', { method: 'POST', body: fd })
    const j = await r.json()
    setRes(j)
    setLoading(false)
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <h2 className="text-lg font-medium">Upload de Documento</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <input className="border p-2" placeholder="Título" value={title} onChange={e=>setTitle(e.target.value)} />
        <select className="border p-2" value={docType} onChange={e=>setDocType(e.target.value)}>
          <option value="general">Geral</option>
          <option value="regulation">Regulação/Norma</option>
        </select>
        <input className="border p-2" placeholder="País" value={country} onChange={e=>setCountry(e.target.value)} />
        <input className="border p-2" placeholder="Setor" value={sector} onChange={e=>setSector(e.target.value)} />
        <input type="file" className="border p-2" onChange={e=>setFile(e.target.files?.[0] || null)} />
      </div>
      <textarea className="border p-2 w-full h-40" placeholder="Texto (opcional, usa se não tiver arquivo)" value={text} onChange={e=>setText(e.target.value)} />
      <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={submit} disabled={loading}>{loading ? 'Enviando...' : 'Enviar'}</button>
      {res && (
        <div className="bg-white rounded shadow p-4">
          <div className="text-sm text-gray-500">Resultado</div>
          <pre className="text-xs overflow-x-auto">{JSON.stringify(res, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
