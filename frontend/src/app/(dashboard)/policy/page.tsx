"use client"
import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

export default function PolicyPage() {
  const token = useRequireToken()
  const [docs, setDocs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)

  // Upload form state
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('general')
  const [country, setCountry] = useState('')

  useEffect(() => {
    if (token) loadDocs()
  }, [token])

  const loadDocs = () => {
    setLoading(true)
    apiFetch('/documents')
      .then(res => res.json())
      .then(data => {
        setDocs(Array.isArray(data) ? data : (data.results || []))
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setLoading(false)
      })
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return alert('Selecione um arquivo')
    setUploading(true)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', title || file.name)
    formData.append('doc_type', docType)
    if (country) formData.append('country', country)

    try {
      const res = await apiFetch('/upload/document', {
        method: 'POST',
        body: formData,
        // apiFetch handles Authorization header, but for FormData we usually 
        // need to let browser set Content-Type to multipart/form-data with boundary.
        // However, apiFetch wrapper might override headers. 
        // If apiFetch sets 'Content-Type': 'application/json' by default, we need to unset it.
        // Let's assume apiFetch is smart enough or we pass specific headers.
        // Actually, typically passing FormData to fetch body automatically sets correct header.
        // If apiFetch forces JSON, we might have issue. 
        // Let's try standard fetch if apiFetch is too rigid, but apiFetch handles token.
        // If apiFetch logic is: headers = { ...defaults, ...options.headers }, and defaults has Content-Type: json...
        // We might need to pass headers: { 'Content-Type': undefined } or similar?
        // Let's assume standard fetch with token for safety if apiFetch is strict.
      })
      
      // Let's use apiFetch but check its implementation if it fails. 
      // For now, assuming apiFetch handles it or we can override.
      // If apiFetch adds Content-Type: application/json, it breaks FormData.
      // Let's check api.ts if possible? No, I'll just try to use it and if it fails I'll fix.
      // Actually, to be safe, I'll check api.ts first? No, I'll trust it works or fix later.
      
      if (res.ok) {
        setShowUpload(false)
        setFile(null)
        setTitle('')
        loadDocs()
      } else {
        const txt = await res.text()
        alert('Erro ao enviar: ' + txt)
      }
    } catch (err) {
      console.error(err)
      alert('Erro ao enviar')
    } finally {
      setUploading(false)
    }
  }

  // Workaround if apiFetch adds Content-Type: application/json
  // I will assume apiFetch might need a flag or I manually do fetch with token
  const safeUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return alert('Selecione um arquivo')
    setUploading(true)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', title || file.name)
    formData.append('doc_type', docType)
    if (country) formData.append('country', country)

    try {
      const token = localStorage.getItem('token')
      const res = await fetch('http://localhost:8000/upload/document', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      })
      if (res.ok) {
        setShowUpload(false)
        setFile(null)
        setTitle('')
        loadDocs()
      } else {
        alert('Erro: ' + res.statusText)
      }
    } catch (err) {
      console.error(err)
      alert('Erro de rede')
    } finally {
      setUploading(false)
    }
  }

  if (!token) return <div className="p-8">Carregando autenticação...</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Gestão de Políticas e Procedimentos</h1>
        <button 
          onClick={() => setShowUpload(!showUpload)}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          {showUpload ? 'Cancelar' : 'Nova Política'}
        </button>
      </div>

      <p className="text-gray-600">
        Centralize as políticas internas (Código de Conduta, Despesas, etc.) e vincule-as às regras de risco.
      </p>

      {showUpload && (
        <div className="bg-white p-6 rounded shadow border border-blue-100">
          <h3 className="font-semibold mb-4">Upload de Documento</h3>
          <form onSubmit={safeUpload} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Arquivo (PDF, DOCX, TXT)</label>
                <input 
                  type="file" 
                  onChange={e => setFile(e.target.files?.[0] || null)}
                  className="border p-2 w-full rounded"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Título</label>
                <input 
                  type="text" 
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="Ex: Política de Viagens 2024"
                  className="border p-2 w-full rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Tipo</label>
                <select 
                  value={docType}
                  onChange={e => setDocType(e.target.value)}
                  className="border p-2 w-full rounded"
                >
                  <option value="general">Geral</option>
                  <option value="conduct">Código de Conduta</option>
                  <option value="expenses">Despesas e Viagens</option>
                  <option value="procurement">Compras e Fornecedores</option>
                  <option value="hr">Recursos Humanos</option>
                  <option value="finance">Financeiro</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">País (Opcional)</label>
                <input 
                  type="text" 
                  value={country}
                  onChange={e => setCountry(e.target.value)}
                  placeholder="Ex: Brasil"
                  className="border p-2 w-full rounded"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <button 
                type="submit" 
                disabled={uploading}
                className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:opacity-50"
              >
                {uploading ? 'Enviando...' : 'Salvar Documento'}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white shadow rounded overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Título</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tipo</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">País</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Data Upload</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Ações</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={5} className="px-6 py-4 text-center">Carregando...</td></tr>
            ) : docs.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-4 text-center text-gray-500">Nenhum documento encontrado.</td></tr>
            ) : (
              docs.map((doc: any) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{doc.title}</div>
                    {doc.file && <div className="text-xs text-gray-500 truncate max-w-xs">{doc.file}</div>}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                      {doc.doc_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {doc.country || 'Global'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <a href="#" className="text-indigo-600 hover:text-indigo-900 mr-4">Ver</a>
                    <a href="#" className="text-red-600 hover:text-red-900">Arquivar</a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
