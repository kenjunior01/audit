"use client"
import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Book, Brain, FileText, Upload, Trash2, Plus, AlertCircle, CheckCircle, Search, RotateCcw } from 'lucide-react'

interface ReferenceItem {
  id: number
  value: string
  code: string | null
  risk_factor: number
  metadata: any
}

interface ReferenceList {
  id: number
  name: string
  description: string
  items_count: number
  items?: ReferenceItem[]
}

interface ContextDocument {
  id: number
  title: string
  doc_type: string
  country: string | null
  processed: boolean
  chunk_count?: number
  created_at: string
}

export default function ContextPage() {
  useRequireToken()
  const [activeTab, setActiveTab] = useState<'lists' | 'documents' | 'search'>('lists')
  
  // Reference Lists State
  const [lists, setLists] = useState<ReferenceList[]>([])
  const [selectedList, setSelectedList] = useState<ReferenceList | null>(null)
  const [items, setItems] = useState<ReferenceItem[]>([])
  const [newListName, setNewListName] = useState('')
  const [loadingLists, setLoadingLists] = useState(false)
  
  // Documents State
  const [documents, setDocuments] = useState<ContextDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [docTitle, setDocTitle] = useState('')
  const [docType, setDocType] = useState('Policy')
  const [uploading, setUploading] = useState(false)

  // Search State
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)

  // New Item State
  const [newItemValue, setNewItemValue] = useState('')
  const [newItemCode, setNewItemCode] = useState('')
  const [newItemRisk, setNewItemRisk] = useState(1.0)

  // Fetch lists on mount
  useEffect(() => {
    fetchLists()
    fetchDocuments()
  }, [])

  // Fetch items when a list is selected
  useEffect(() => {
    if (selectedList) {
      fetchItems(selectedList.id)
    } else {
      setItems([])
    }
  }, [selectedList])

  const fetchLists = async () => {
    setLoadingLists(true)
    try {
      const res = await apiFetch('/reference-lists/')
      if (res.ok) {
        const data = await res.json()
        setLists(Array.isArray(data) ? data : data.results || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingLists(false)
    }
  }

  const fetchDocuments = async () => {
    setLoadingDocs(true)
    try {
      const res = await apiFetch('/documents/')
      if (res.ok) {
        const data = await res.json()
        setDocuments(Array.isArray(data) ? data : data.results || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingDocs(false)
    }
  }

  const fetchItems = async (listId: number) => {
    try {
      const res = await apiFetch(`/reference-items/?reference_list=${listId}`)
      if (res.ok) {
        const data = await res.json()
        setItems(Array.isArray(data) ? data : data.results || [])
      } else {
        // Fallback: try fetching the list detail
        const resList = await apiFetch(`/reference-lists/${listId}/`)
        if (resList.ok) {
          const dataList = await resList.json()
          if (dataList.items) setItems(dataList.items)
        }
      }
    } catch (e) {
      console.error(e)
    }
  }

  const createList = async () => {
    if (!newListName) return
    try {
      const res = await apiFetch('/reference-lists/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newListName, description: 'Created via UI' })
      })
      if (res.ok) {
        setNewListName('')
        fetchLists()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const createItem = async () => {
    if (!selectedList || !newItemValue) return
    try {
      const res = await apiFetch('/reference-items/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reference_list: selectedList.id,
          value: newItemValue,
          code: newItemCode,
          risk_factor: newItemRisk,
          metadata: {}
        })
      })
      if (res.ok) {
        setNewItemValue('')
        setNewItemCode('')
        setNewItemRisk(1.0)
        fetchItems(selectedList.id)
        fetchLists() // Update counts
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleUpload = async () => {
    if (!uploadFile) return
    setUploading(true)
    const formData = new FormData()
    formData.append('file', uploadFile)
    formData.append('title', docTitle || uploadFile.name)
    formData.append('doc_type', docType)
    
    try {
      const res = await apiFetch('/upload/document', {
        method: 'POST',
        body: formData // apiFetch handles headers for FormData if we don't set Content-Type
      })
      if (res.ok) {
        setUploadFile(null)
        setDocTitle('')
        fetchDocuments()
        alert('Upload concluído com sucesso!')
      } else {
        const errText = await res.text()
        console.error('Upload Error:', res.status, errText)
        alert(`Erro no upload: ${res.status} - ${errText}`)
      }
    } catch (e) {
      console.error(e)
      alert(`Erro no upload: ${e}`)
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteDoc = async (id: number) => {
      if(!confirm('Tem certeza?')) return
      try {
          await apiFetch(`/documents/${id}/`, { method: 'DELETE' })
          fetchDocuments()
      } catch (e) { console.error(e) }
  }

  const handleReprocessDoc = async (id: number) => {
      try {
          const res = await apiFetch(`/documents/${id}/reprocess/`, { method: 'POST' })
          if (res.ok) {
              alert('Reprocessamento iniciado!')
              fetchDocuments()
          } else {
              alert('Erro ao iniciar reprocessamento')
          }
      } catch (e) { console.error(e) }
  }

  const handleSearch = async (e: React.FormEvent) => {
      e.preventDefault()
      if (!searchQuery) return
      setSearching(true)
      try {
          const res = await apiFetch(`/documents/search/?q=${encodeURIComponent(searchQuery)}`)
          if (res.ok) {
              const data = await res.json()
              setSearchResults(data.results || [])
          }
      } catch (e) {
          console.error(e)
      } finally {
          setSearching(false)
      }
  }

  // Import Search icon which was missing in original imports but used in code
  // Wait, I need to check imports. "Search" is used in tab button.
  // Original imports: Book, Brain, FileText, Upload, Trash2, Plus, AlertCircle, CheckCircle
  // Need to add Search, RotateCcw (for reprocess)

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Gerenciamento de Contexto</h1>
          <p className="text-gray-500 mt-1">Configure o conhecimento corporativo e listas de referência para a IA.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-gray-200 dark:border-gray-700 mb-6">
        <button
          onClick={() => setActiveTab('lists')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-medium transition-colors ${
            activeTab === 'lists' 
              ? 'border-blue-500 text-blue-600 dark:text-blue-400' 
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <Book className="w-4 h-4" />
          Listas de Referência
        </button>
        <button
          onClick={() => setActiveTab('documents')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-medium transition-colors ${
            activeTab === 'documents' 
              ? 'border-purple-500 text-purple-600 dark:text-purple-400' 
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <Brain className="w-4 h-4" />
          Cérebro Corporativo (RAG)
        </button>
        <button
          onClick={() => setActiveTab('search')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-medium transition-colors ${
            activeTab === 'search' 
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' 
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <Search className="w-4 h-4" />
          Testar Busca
        </button>
      </div>

      {/* Content */}
      {activeTab === 'lists' ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Lists Sidebar */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-4 border border-gray-100 dark:border-gray-700">
            <h3 className="font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
              <Book className="w-4 h-4" /> Listas Disponíveis
            </h3>
            
            <div className="space-y-2 mb-4">
              {lists.map(list => (
                <div 
                  key={list.id}
                  onClick={() => setSelectedList(list)}
                  className={`p-3 rounded cursor-pointer transition-colors ${
                    selectedList?.id === list.id 
                      ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800' 
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <div className="font-medium text-gray-900 dark:text-white">{list.name}</div>
                  <div className="text-xs text-gray-500">{list.items_count} itens</div>
                </div>
              ))}
            </div>

            <div className="flex gap-2 mt-4 pt-4 border-t dark:border-gray-700">
              <input 
                className="flex-1 border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                placeholder="Nova Lista..."
                value={newListName}
                onChange={e => setNewListName(e.target.value)}
              />
              <button 
                onClick={createList}
                className="p-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Items Area */}
          <div className="col-span-2 bg-white dark:bg-slate-800 rounded-lg shadow p-6 border border-gray-100 dark:border-gray-700">
            {selectedList ? (
              <>
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">{selectedList.name}</h2>
                    <p className="text-sm text-gray-500">{selectedList.description}</p>
                  </div>
                  <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-gray-600 dark:text-gray-300">
                    ID: {selectedList.id}
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-300">
                      <tr>
                        <th className="px-4 py-3">Valor</th>
                        <th className="px-4 py-3">Código</th>
                        <th className="px-4 py-3">Fator Risco</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map(item => (
                        <tr key={item.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                          <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{item.value}</td>
                          <td className="px-4 py-3 text-gray-500">{item.code || '-'}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded text-xs font-bold ${
                              item.risk_factor > 1 
                                ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            }`}>
                              {item.risk_factor}x
                            </span>
                          </td>
                        </tr>
                      ))}
                      {items.length === 0 && (
                        <tr>
                          <td colSpan={3} className="px-4 py-8 text-center text-gray-500">
                            Nenhum item nesta lista.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Add Item Form */}
                <div className="mt-6 pt-6 border-t dark:border-gray-700">
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Adicionar Novo Item</h4>
                  <div className="flex gap-4 items-end">
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">Valor / Nome</label>
                      <input 
                        className="w-full border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                        placeholder="Ex: Consultoria, Dept. TI..."
                        value={newItemValue}
                        onChange={e => setNewItemValue(e.target.value)}
                      />
                    </div>
                    <div className="w-32">
                      <label className="block text-xs text-gray-500 mb-1">Código (Opcional)</label>
                      <input 
                        className="w-full border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                        placeholder="Ex: 101"
                        value={newItemCode}
                        onChange={e => setNewItemCode(e.target.value)}
                      />
                    </div>
                    <div className="w-24">
                      <label className="block text-xs text-gray-500 mb-1">Fator Risco</label>
                      <input 
                        type="number"
                        step="0.1"
                        className="w-full border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                        value={newItemRisk}
                        onChange={e => setNewItemRisk(parseFloat(e.target.value))}
                      />
                    </div>
                    <button 
                      onClick={createItem}
                      disabled={!newItemValue}
                      className="p-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-gray-400">
                <Book className="w-12 h-12 mb-2 opacity-20" />
                <p>Selecione uma lista para ver os detalhes</p>
              </div>
            )}
          </div>
        </div>
      ) : activeTab === 'search' ? (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6 border border-gray-100 dark:border-gray-700 max-w-4xl mx-auto">
            <h3 className="font-semibold text-gray-700 dark:text-gray-300 mb-6 flex items-center gap-2">
                <Search className="w-5 h-5" /> Testar Recuperação (RAG)
            </h3>
            
            <form onSubmit={handleSearch} className="flex gap-2 mb-8">
                <input 
                    className="flex-1 border p-3 rounded-lg text-base dark:bg-slate-900 dark:border-gray-600 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Faça uma pergunta ao Cérebro Corporativo..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                />
                <button 
                    type="submit"
                    disabled={searching || !searchQuery}
                    className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium flex items-center gap-2"
                >
                    {searching ? (
                        <>
                            <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                            Buscando...
                        </>
                    ) : (
                        <>
                            <Search className="w-4 h-4" />
                            Buscar
                        </>
                    )}
                </button>
            </form>

            <div className="space-y-4">
                {searchResults.length > 0 ? (
                    searchResults.map((result, idx) => (
                        <div key={idx} className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
                            <div className="flex justify-between items-start mb-2">
                                <h4 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-indigo-500" />
                                    {result.doc}
                                </h4>
                                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                                    result.score > 0.7 ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                                }`}>
                                    Relevância: {(result.score * 100).toFixed(0)}%
                                </span>
                            </div>
                            <p className="text-gray-600 dark:text-gray-300 text-sm leading-relaxed">
                                {result.summary}
                            </p>
                        </div>
                    ))
                ) : (
                    !searching && (
                        <div className="text-center py-12 text-gray-400">
                            <Brain className="w-12 h-12 mx-auto mb-3 opacity-20" />
                            <p>Digite uma pergunta acima para testar a recuperação de documentos.</p>
                        </div>
                    )
                )}
            </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Upload Area */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6 border border-gray-100 dark:border-gray-700">
             <h3 className="font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
                <Upload className="w-4 h-4" /> Upload de Documento
             </h3>
             <p className="text-sm text-gray-500 mb-4">
               Carregue políticas internas, manuais ou regulamentos. A IA irá processar e usar para análise de risco (RAG).
             </p>

             <div className="space-y-4">
                <div>
                   <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Título</label>
                   <input 
                      className="w-full border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                      placeholder="Ex: Política de Viagens 2024"
                      value={docTitle}
                      onChange={e => setDocTitle(e.target.value)}
                   />
                </div>
                <div>
                   <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tipo</label>
                   <select 
                      className="w-full border p-2 rounded text-sm dark:bg-slate-900 dark:border-gray-600"
                      value={docType}
                      onChange={e => setDocType(e.target.value)}
                   >
                      <option value="Policy">Política Interna</option>
                      <option value="Manual">Manual de Procedimentos</option>
                      <option value="Contract">Contrato Padrão</option>
                      <option value="Regulation">Regulação Externa</option>
                   </select>
                </div>
                
                <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                   <input 
                      type="file" 
                      id="file-upload" 
                      className="hidden" 
                      onChange={e => setUploadFile(e.target.files?.[0] || null)}
                   />
                   <label htmlFor="file-upload" className="cursor-pointer">
                      <div className="flex flex-col items-center">
                        <FileText className="w-8 h-8 text-gray-400 mb-2" />
                        <span className="text-sm text-blue-600 font-medium">
                           {uploadFile ? uploadFile.name : 'Clique para selecionar PDF/DOCX'}
                        </span>
                      </div>
                   </label>
                </div>

                <button 
                  onClick={handleUpload}
                  disabled={!uploadFile || uploading}
                  className={`w-full py-2 rounded text-white font-medium flex items-center justify-center gap-2 ${
                    !uploadFile || uploading ? 'bg-gray-400' : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                >
                   {uploading ? (
                     <>
                       <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                       Processando...
                     </>
                   ) : (
                     <>
                       <Upload className="w-4 h-4" />
                       Enviar para o Cérebro
                     </>
                   )}
                </button>
             </div>
          </div>

          {/* Documents List */}
          <div className="col-span-2 bg-white dark:bg-slate-800 rounded-lg shadow p-6 border border-gray-100 dark:border-gray-700">
             <h3 className="font-semibold text-gray-700 dark:text-gray-300 mb-6 flex items-center gap-2">
                <Brain className="w-4 h-4" /> Documentos no Cérebro Corporativo
             </h3>

             <div className="overflow-x-auto">
               <table className="w-full text-sm text-left">
                  <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-300">
                    <tr>
                      <th className="px-4 py-3">Documento</th>
                      <th className="px-4 py-3">Tipo</th>
                      <th className="px-4 py-3">Status RAG</th>
                      <th className="px-4 py-3">Chunks</th>
                      <th className="px-4 py-3">Data</th>
                      <th className="px-4 py-3">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map(doc => (
                      <tr key={doc.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                          <div className="flex items-center gap-2">
                             <FileText className="w-4 h-4 text-gray-400" />
                             {doc.title}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-gray-500">{doc.doc_type}</td>
                        <td className="px-4 py-3">
                           {doc.processed ? (
                              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-xs font-medium">
                                 <CheckCircle className="w-3 h-3" /> Indexado
                              </span>
                           ) : (
                              <span className="flex items-center gap-1 text-yellow-600 dark:text-yellow-400 text-xs font-medium">
                                 <div className="animate-pulse w-2 h-2 rounded-full bg-yellow-500"></div>
                                 Processando
                              </span>
                           )}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                            {doc.chunk_count !== undefined ? (
                                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs font-mono">
                                    {doc.chunk_count}
                                </span>
                            ) : '-'}
                        </td>
                        <td className="px-4 py-3 text-gray-500">{new Date(doc.created_at).toLocaleDateString()}</td>
                        <td className="px-4 py-3 flex gap-2">
                           <button 
                              onClick={() => handleReprocessDoc(doc.id)}
                              className="text-blue-500 hover:text-blue-700 p-1 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20"
                              title="Reprocessar"
                           >
                              <RotateCcw className="w-4 h-4" />
                           </button>
                           <button 
                              onClick={() => handleDeleteDoc(doc.id)}
                              className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                              title="Excluir"
                           >
                              <Trash2 className="w-4 h-4" />
                           </button>
                        </td>
                      </tr>
                    ))}
                    {documents.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-4 py-12 text-center text-gray-500">
                          <Brain className="w-12 h-12 mx-auto mb-3 opacity-20" />
                          <p>Nenhum documento carregado.</p>
                          <p className="text-xs mt-1">Faça upload de políticas para ativar a inteligência contextual.</p>
                        </td>
                      </tr>
                    )}
                  </tbody>
               </table>
             </div>
          </div>
        </div>
      )}
    </div>
  )
}
