"use client"
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

export default function UploadSamplesPage() {
  useRequireToken()
  const [files, setFiles] = useState<FileList | null>(null)
  const [res, setRes] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [progress, setProgress] = useState<{processed: number, remaining: number} | null>(null)

  const submit = async () => {
    if (!files || files.length === 0) return
    setLoading(true)
    setRes(null)
    setProgress(null)
    
    const fd = new FormData()
    for (let i = 0; i < files.length; i++) {
        fd.append('files', files[i])
    }

    try {
        const r = await apiFetch('/upload/samples', { method: 'POST', body: fd })
        const data = await r.json()
        setRes(data)
    } catch (e) {
        setRes({ error: 'Failed to upload' })
    } finally {
        setLoading(false)
    }
  }

  const startAnalysis = async () => {
      setAnalyzing(true)
      let remaining = 1;
      let totalProcessed = 0;

      try {
          while (remaining > 0) {
              const r = await apiFetch('/upload/process-pending', { 
                  method: 'POST', 
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ limit: 10 }) 
              })
              const data = await r.json()
              remaining = data.remaining
              totalProcessed += data.processed
              setProgress({ processed: totalProcessed, remaining: remaining })
              
              if (data.processed === 0 && remaining > 0) {
                  // Stuck or error? Break to avoid infinite loop
                  break;
              }
          }
      } catch (e) {
          console.error(e)
      } finally {
          setAnalyzing(false)
      }
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto p-6 bg-white rounded-lg shadow">
      <div>
        <h2 className="text-xl font-semibold text-gray-800">Coleta e Análise de Amostras</h2>
        <p className="text-sm text-gray-500 mt-1">
            Faça upload de múltiplos arquivos CSV/Excel para ingestão em massa. 
            O sistema analisará cada transação usando regras, agentes e modelos de IA.
            Para importação com mapeamento assistido, use o <a href="/excel" className="text-blue-600 underline">Excel Studio</a>.
        </p>
      </div>

      <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:bg-gray-50 transition-colors">
        <input 
            type="file" 
            multiple 
            accept=".csv,.xlsx,.xlsm,.xls"
            className="hidden" 
            id="file-upload"
            onChange={e => setFiles(e.target.files)} 
        />
        <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
            <svg className="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span className="text-blue-600 font-medium hover:text-blue-700">Clique para selecionar arquivos</span>
            <span className="text-xs text-gray-500 mt-1">Suporta múltiplos CSVs e Excels</span>
        </label>
        {files && files.length > 0 && (
            <div className="mt-4 text-sm text-gray-700 bg-gray-100 p-2 rounded">
                {files.length} arquivo(s) selecionado(s)
            </div>
        )}
      </div>

      <div className="flex gap-4">
        <button 
            className={`flex-1 py-2 px-4 rounded font-medium transition-colors ${
                loading || !files ? 'bg-gray-300 text-gray-500 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
            onClick={submit} 
            disabled={loading || !files || files.length === 0}
        >
            {loading ? 'Enviando...' : 'Fazer Upload'}
        </button>

        {res && res.status === 'completed' && (
            <button 
                className={`flex-1 py-2 px-4 rounded font-medium transition-colors ${
                    analyzing ? 'bg-purple-300 text-white cursor-wait' : 'bg-purple-600 text-white hover:bg-purple-700'
                }`}
                onClick={startAnalysis}
                disabled={analyzing}
            >
                {analyzing ? 'Analisando...' : 'Iniciar Análise Completa'}
            </button>
        )}
      </div>

      {res && (
        <div className={`rounded p-4 ${res.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
            {res.error ? (
                <p>Erro: {res.error}</p>
            ) : (
                <div>
                    <p className="font-medium">Upload Concluído!</p>
                    <p className="text-sm">Transações importadas: {res.imported_count}</p>
                    {res.errors && res.errors.length > 0 && (
                        <div className="mt-2 text-xs text-red-600">
                            <p className="font-semibold">Erros:</p>
                            <ul className="list-disc pl-4">
                                {res.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </div>
      )}

      {(analyzing || progress) && (
          <div className="bg-white border rounded p-4 shadow-sm">
              <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium">Progresso da Análise</span>
                  <span>{progress?.remaining === 0 ? 'Concluído' : 'Processando...'}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div className="bg-purple-600 h-2.5 rounded-full transition-all duration-500" style={{ width: '100%' }}>
                      {/* Indeterminate or simple logic since we don't know total at start easily without extra call */}
                  </div>
              </div>
              <p className="text-xs text-gray-500 mt-2">
                  Processados nesta sessão: {progress?.processed || 0} | Pendentes: {progress?.remaining || '...'}
              </p>
          </div>
      )}
    </div>
  )
}
