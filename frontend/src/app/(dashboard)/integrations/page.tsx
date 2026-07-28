'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Plus, Trash2, ExternalLink, Play, TestTube2, Eye } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface ExternalSystem {
  id: number
  name: string
  system_type: string
  auth_type: string
  base_url: string | null
  webhook_url: string | null
  api_key: string | null
  api_secret: string | null
  oauth_client_id: string | null
  oauth_client_secret: string | null
  oauth_token_url: string | null
  ingest_enabled: boolean
  ingest_interval: number
  is_active: boolean
  description: string | null
  created_at: string
  updated_at: string
}

interface WebhookEvent {
  id: number
  event_type: string
  status: string
  attempt_count: number
  last_attempt_at: string | null
  created_at: string
}

export default function IntegrationsPage() {
  useRequireToken()
  const [systems, setSystems] = useState<ExternalSystem[]>([])
  const [webhooks, setWebhooks] = useState<WebhookEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingSystem, setEditingSystem] = useState<ExternalSystem | null>(null)
  const [formData, setFormData] = useState<Partial<ExternalSystem>>({
    name: '',
    system_type: 'CUSTOM',
    auth_type: 'API_KEY',
    ingest_enabled: true,
    ingest_interval: 300,
    is_active: true
  })
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const loadData = async () => {
    try {
      const [systemsRes, webhooksRes] = await Promise.all([
        apiFetch('/external-systems/'),
        apiFetch('/webhook-events/')
      ])
      const systemsData = await systemsRes.json()
      const webhooksData = await webhooksRes.json()
      setSystems(Array.isArray(systemsData) ? systemsData : (systemsData.results || []))
      setWebhooks(Array.isArray(webhooksData) ? webhooksData : (webhooksData.results || []))
    } catch (e) {
      console.error('Failed to load data:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const url = editingSystem 
        ? `/external-systems/${editingSystem.id}/` 
        : '/external-systems/'
      const method = editingSystem ? 'PATCH' : 'POST'
      
      const response = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      
      if (response.ok) {
        setToast({ 
          message: editingSystem ? 'Sistema atualizado com sucesso' : 'Sistema criado com sucesso', 
          type: 'success' 
        })
        setShowModal(false)
        setEditingSystem(null)
        setFormData({
          name: '',
          system_type: 'CUSTOM',
          auth_type: 'API_KEY',
          ingest_enabled: true,
          ingest_interval: 300,
          is_active: true
        })
        loadData()
      } else {
        setToast({ message: 'Erro ao salvar sistema', type: 'error' })
      }
    } catch (e) {
      console.error('Failed to save system:', e)
      setToast({ message: 'Erro ao salvar sistema', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Tem certeza que deseja excluir este sistema?')) return
    try {
      const response = await apiFetch(`/external-systems/${id}/`, { method: 'DELETE' })
      if (response.ok) {
        setToast({ message: 'Sistema excluído com sucesso', type: 'success' })
        loadData()
      }
    } catch (e) {
      console.error('Failed to delete system:', e)
      setToast({ message: 'Erro ao excluir sistema', type: 'error' })
    }
  }

  const handleTestConnection = async (id: number) => {
    try {
      const response = await apiFetch(`/external-systems/${id}/test_connection/`, { method: 'POST' })
      const data = await response.json()
      if (data.status === 'success') {
        setToast({ message: 'Conexão testada com sucesso!', type: 'success' })
      } else {
        setToast({ message: `Falha na conexão: ${data.message}`, type: 'error' })
      }
    } catch (e) {
      console.error('Failed to test connection:', e)
      setToast({ message: 'Erro ao testar conexão', type: 'error' })
    }
  }

  const handleTriggerIngest = async (id: number) => {
    try {
      const response = await apiFetch(`/external-systems/${id}/trigger_ingest/`, { method: 'POST' })
      const data = await response.json()
      if (data.status === 'success') {
        setToast({ message: 'Ingestão iniciada!', type: 'success' })
      }
    } catch (e) {
      console.error('Failed to trigger ingest:', e)
      setToast({ message: 'Erro ao iniciar ingestão', type: 'error' })
    }
  }

  const systemTypes = [
    { value: 'ERP', label: 'Sistema ERP' },
    { value: 'CRM', label: 'Sistema CRM' },
    { value: 'DATABASE', label: 'Banco de Dados' },
    { value: 'DOCUMENT', label: 'Sistema de Documentos' },
    { value: 'HR', label: 'Sistema RH' },
    { value: 'FINANCE', label: 'Sistema Financeiro' },
    { value: 'CUSTOM', label: 'Sistema Customizado' }
  ]

  const authTypes = [
    { value: 'API_KEY', label: 'Chave API' },
    { value: 'BEARER', label: 'Token Bearer' },
    { value: 'BASIC', label: 'Autenticação Básica' },
    { value: 'OAUTH2', label: 'OAuth 2.0' },
    { value: 'NONE', label: 'Sem Autenticação' }
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Integrações</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Conecte sistemas externos e gerencie webhooks
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={20} />
          Nova Integração
        </button>
      </div>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className={`p-4 rounded-lg ${toast.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}
          >
            {toast.message}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Systems Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {systems.map((system) => (
          <Card key={system.id} className="hover:shadow-md transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-xl">{system.name}</CardTitle>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${system.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                      {system.is_active ? 'Ativo' : 'Inativo'}
                    </span>
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                      {systemTypes.find(t => t.value === system.system_type)?.label}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleTestConnection(system.id)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                    title="Testar Conexão"
                  >
                    <TestTube2 size={18} />
                  </button>
                  <button
                    onClick={() => {
                      setEditingSystem(system)
                      setFormData(system)
                      setShowModal(true)
                    }}
                    className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg"
                    title="Editar"
                  >
                    <Eye size={18} />
                  </button>
                  <button
                    onClick={() => handleDelete(system.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                    title="Excluir"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {system.base_url && (
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <ExternalLink size={16} />
                  <span className="truncate">{system.base_url}</span>
                </div>
              )}
              {system.webhook_url && (
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <ExternalLink size={16} />
                  <span className="truncate">Webhook: {system.webhook_url}</span>
                </div>
              )}
              {system.ingest_enabled && (
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <Play size={16} />
                  <span>Ingestão: {system.ingest_interval}s</span>
                </div>
              )}
              {system.ingest_enabled && (
                <button
                  onClick={() => handleTriggerIngest(system.id)}
                  className="mt-2 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  Disparar Ingestão Manualmente
                </button>
              )}
            </CardContent>
          </Card>
        ))}
        {systems.length === 0 && (
          <div className="col-span-full text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p className="text-gray-500 dark:text-gray-400">Nenhuma integração configurada ainda</p>
          </div>
        )}
      </div>

      {/* Webhooks Log */}
      {webhooks.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Log de Webhooks</CardTitle>
            <button
              onClick={async () => {
                try {
                  const response = await apiFetch('/webhook-events/retry_all_failed/', { method: 'POST' });
                  const data = await response.json();
                  if (data.status === 'success') {
                    setToast({ message: data.message, type: 'success' });
                  }
                } catch (e) {
                  console.error(e);
                  setToast({ message: 'Erro ao agendar retry de webhooks', type: 'error' });
                }
              }}
              className="flex items-center gap-2 px-3 py-1 text-sm border rounded hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              Retry Falhos
            </button>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Evento</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Sistema</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Tentativas</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Data</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {webhooks.slice(0, 10).map((wh) => (
                    <tr key={wh.id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                      <td className="px-4 py-3 font-mono">{wh.event_type}</td>
                      <td className="px-4 py-3">{systems.find(s => s.id === wh.system)?.name || 'Desconhecido'}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          wh.status === 'SUCCESS' ? 'bg-green-100 text-green-800' :
                          wh.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                          wh.status === 'RETRYING' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {wh.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">{wh.attempt_count}</td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(wh.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        {wh.status === 'FAILED' && wh.attempt_count < 5 && (
                          <button
                            onClick={async () => {
                              try {
                                const response = await apiFetch(`/webhook-events/${wh.id}/retry/`, { method: 'POST' });
                                const data = await response.json();
                                if (data.status === 'success') {
                                  setToast({ message: data.message, type: 'success' });
                                  loadData();
                                }
                              } catch (e) {
                                console.error(e);
                                setToast({ message: 'Erro ao agendar retry', type: 'error' });
                              }
                            }}
                            className="text-indigo-600 hover:text-indigo-700 text-sm"
                          >
                            Retry
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal */}
      <AnimatePresence>
        {showModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between p-6 border-b border-gray-100 dark:border-gray-800">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  {editingSystem ? 'Editar Integração' : 'Nova Integração'}
                </h2>
                <button
                  onClick={() => {
                    setShowModal(false)
                    setEditingSystem(null)
                    setFormData({
                      name: '',
                      system_type: 'CUSTOM',
                      auth_type: 'API_KEY',
                      ingest_enabled: true,
                      ingest_interval: 300,
                      is_active: true
                    })
                  }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <Trash2 size={24} />
                </button>
              </div>
              <form onSubmit={handleSubmit} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Nome do Sistema
                  </label>
                  <input
                    required
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    placeholder="Ex: Meu ERP"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Tipo de Sistema
                    </label>
                    <select
                      value={formData.system_type}
                      onChange={(e) => setFormData({ ...formData, system_type: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                      {systemTypes.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Tipo de Autenticação
                    </label>
                    <select
                      value={formData.auth_type}
                      onChange={(e) => setFormData({ ...formData, auth_type: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                      {authTypes.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    URL Base do Sistema
                  </label>
                  <input
                    type="url"
                    value={formData.base_url || ''}
                    onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    placeholder="https://meu-sistema.com"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    URL do Webhook (receber eventos)
                  </label>
                  <input
                    type="url"
                    value={formData.webhook_url || ''}
                    onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    placeholder="https://meu-sistema.com/webhook/audit"
                  />
                </div>

                {(formData.auth_type === 'API_KEY' || formData.auth_type === 'BEARER') && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Chave API / Token
                    </label>
                    <input
                      type="password"
                      value={formData.api_key || ''}
                      onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                      placeholder="Insira a chave"
                    />
                  </div>
                )}

                {formData.auth_type === 'BASIC' && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Usuário
                      </label>
                      <input
                        type="text"
                        value={formData.api_key || ''}
                        onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="Usuário"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Senha
                      </label>
                      <input
                        type="password"
                        value={formData.api_secret || ''}
                        onChange={(e) => setFormData({ ...formData, api_secret: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="Senha"
                      />
                    </div>
                  </div>
                )}

                {formData.auth_type === 'OAUTH2' && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          Client ID
                        </label>
                        <input
                          type="text"
                          value={formData.oauth_client_id || ''}
                          onChange={(e) => setFormData({ ...formData, oauth_client_id: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          placeholder="Client ID"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          Client Secret
                        </label>
                        <input
                          type="password"
                          value={formData.oauth_client_secret || ''}
                          onChange={(e) => setFormData({ ...formData, oauth_client_secret: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          placeholder="Client Secret"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        URL do Token
                      </label>
                      <input
                        type="url"
                        value={formData.oauth_token_url || ''}
                        onChange={(e) => setFormData({ ...formData, oauth_token_url: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="https://meu-sistema.com/oauth/token"
                      />
                    </div>
                  </>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Intervalo de Ingestão (segundos)
                    </label>
                    <input
                      type="number"
                      min="60"
                      step="60"
                      value={formData.ingest_interval}
                      onChange={(e) => setFormData({ ...formData, ingest_interval: parseInt(e.target.value) || 300 })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    />
                  </div>
                  <div className="flex items-end">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.ingest_enabled}
                        onChange={(e) => setFormData({ ...formData, ingest_enabled: e.target.checked })}
                        className="w-4 h-4 text-indigo-600 rounded"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Habilitar Ingestão</span>
                    </label>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      className="w-4 h-4 text-indigo-600 rounded"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Sistema Ativo</span>
                  </label>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Descrição (opcional)
                  </label>
                  <textarea
                    value={formData.description || ''}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    placeholder="Descrição do sistema e integração"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setShowModal(false)
                      setEditingSystem(null)
                    }}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {loading ? 'Salvando...' : 'Salvar'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}