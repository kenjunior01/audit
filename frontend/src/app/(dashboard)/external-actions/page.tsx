'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Plus, Trash2, TestTube2, PlayCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface ExternalSystem {
  id: number
  name: string
  system_type: string
}

interface ExternalActionTemplate {
  id: number
  name: string
  description: string
  action_type: string
  system: ExternalSystem | null
  endpoint_url: string | null
  http_method: string
  payload_template?: any
  headers?: any
  auth_credentials?: any
  jira_project_key?: string | null
  jira_issue_type?: string | null
  email_recipients?: string | null
  email_subject_template?: string | null
  email_body_template?: string | null
  active: boolean
  created_at: string
}

interface ExternalActionExecution {
  id: number
  template: ExternalActionTemplate | null
  status: string
  created_at: string
}

export default function ExternalActionsPage() {
  useRequireToken()
  const [templates, setTemplates] = useState<ExternalActionTemplate[]>([])
  const [executions, setExecutions] = useState<ExternalActionExecution[]>([])
  const [systems, setSystems] = useState<ExternalSystem[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<ExternalActionTemplate | null>(null)
  const [formData, setFormData] = useState<Partial<ExternalActionTemplate & {
    payload_template: string
    headers: string
    auth_credentials: string
  }>>({
    name: '',
    description: '',
    action_type: 'webhook',
    http_method: 'POST',
    active: true,
    payload_template: '{}',
    headers: '{}',
    auth_credentials: '{}'
  })
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const loadData = async () => {
    try {
      const [templatesRes, executionsRes, systemsRes] = await Promise.all([
        apiFetch('/external-action-templates/'),
        apiFetch('/external-action-executions/'),
        apiFetch('/external-systems/')
      ])
      setTemplates(await templatesRes.json())
      const execData = await executionsRes.json()
      setExecutions(Array.isArray(execData) ? execData : (execData.results || []))
      const sysData = await systemsRes.json()
      setSystems(Array.isArray(sysData) ? sysData : (sysData.results || []))
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
      const data = {
        ...formData,
        payload_template: formData.payload_template ? JSON.parse(formData.payload_template) : null,
        headers: formData.headers ? JSON.parse(formData.headers) : null,
        auth_credentials: formData.auth_credentials ? JSON.parse(formData.auth_credentials) : null
      }

      const url = editingTemplate 
        ? `/external-action-templates/${editingTemplate.id}/` 
        : '/external-action-templates/'
      const method = editingTemplate ? 'PATCH' : 'POST'
      
      const response = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })

      if (response.ok) {
        setToast({ 
          message: editingTemplate ? 'Template updated successfully' : 'Template created successfully', 
          type: 'success' 
        })
        setShowModal(false)
        setEditingTemplate(null)
        setFormData({
          name: '',
          description: '',
          action_type: 'webhook',
          http_method: 'POST',
          active: true,
          payload_template: '{}',
          headers: '{}',
          auth_credentials: '{}'
        })
        loadData()
      } else {
        const error = await response.text()
        setToast({ message: `Error: ${error}`, type: 'error' })
      }
    } catch (e) {
      console.error('Failed to save template:', e)
      setToast({ message: 'Error saving template', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this template?')) return
    try {
      const response = await apiFetch(`/external-action-templates/${id}/`, { method: 'DELETE' })
      if (response.ok) {
        setToast({ message: 'Template deleted successfully', type: 'success' })
        loadData()
      }
    } catch (e) {
      console.error('Failed to delete template:', e)
      setToast({ message: 'Error deleting template', type: 'error' })
    }
  }

  const handleTest = async (id: number) => {
    try {
      const response = await apiFetch(`/external-action-templates/${id}/test/`, { method: 'POST' })
      const data = await response.json()
      if (data.status === 'success') {
        setToast({ message: 'Test execution queued! Check executions below.', type: 'success' })
        loadData()
      } else {
        setToast({ message: data.message || 'Test failed', type: 'error' })
      }
    } catch (e) {
      console.error('Failed to test template:', e)
      setToast({ message: 'Error testing template', type: 'error' })
    }
  }

  const actionTypes = [
    { value: 'webhook', label: 'Webhook' },
    { value: 'api_rest', label: 'REST API' },
    { value: 'jira_ticket', label: 'Jira Ticket' },
    { value: 'slack_message', label: 'Slack Message' },
    { value: 'email', label: 'Email' },
    { value: 'custom', label: 'Custom Action' }
  ]

  const httpMethods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

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
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">External Actions</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Create templates for actions that agents can trigger in external systems
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={20} />
          New Template
        </button>
      </div>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`p-4 rounded-lg ${toast.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}
          >
            {toast.message}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Templates Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {templates.map((template) => (
          <Card key={template.id} className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-xl flex items-center gap-2">
                    {template.name}
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${template.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                      {template.active ? 'Active' : 'Inactive'}
                    </span>
                  </CardTitle>
                  <span className="text-sm text-gray-500">
                    {actionTypes.find(t => t.value === template.action_type)?.label || template.action_type}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleTest(template.id)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                    title="Test"
                  >
                    <TestTube2 size={18} />
                  </button>
                  <button
                    onClick={() => {
                      setEditingTemplate(template)
                      setFormData({
                        ...template,
                        payload_template: JSON.stringify(template.payload_template, null, 2),
                        headers: JSON.stringify(template.headers, null, 2),
                        auth_credentials: JSON.stringify(template.auth_credentials, null, 2)
                      })
                      setShowModal(true)
                    }}
                    className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg"
                    title="Edit"
                  >
                    <PlayCircle size={18} />
                  </button>
                  <button
                    onClick={() => handleDelete(template.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                    title="Delete"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {template.description && (
                <p className="text-gray-600 dark:text-gray-400 mb-3">{template.description}</p>
              )}
              {template.endpoint_url && (
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
                  <span className="font-medium">{template.http_method}</span>
                  <span className="truncate">{template.endpoint_url}</span>
                </div>
              )}
              {template.system && (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  System: {template.system.name}
                </div>
              )}
              <div className="text-xs text-gray-400 mt-2">
                Created: {new Date(template.created_at).toLocaleString()}
              </div>
            </CardContent>
          </Card>
        ))}
        {templates.length === 0 && (
          <div className="col-span-full text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p className="text-gray-500 dark:text-gray-400">No external action templates yet</p>
            <p className="text-sm text-gray-400 mt-1">Create one to get started!</p>
          </div>
        )}
      </div>

      {/* Recent Executions */}
      {executions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Executions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">ID</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Template</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-500">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {executions.slice(0, 10).map((exec) => (
                    <tr key={exec.id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                      <td className="px-4 py-3">{exec.id}</td>
                      <td className="px-4 py-3">{exec.template?.name || 'N/A'}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          exec.status === 'success' ? 'bg-green-100 text-green-800' :
                          exec.status === 'failed' ? 'bg-red-100 text-red-800' :
                          exec.status === 'running' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {exec.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(exec.created_at).toLocaleString()}
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
                  {editingTemplate ? 'Edit Template' : 'New External Action Template'}
                </h2>
                <button
                  onClick={() => {
                    setShowModal(false)
                    setEditingTemplate(null)
                  }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <Trash2 size={24} />
                </button>
              </div>
              <form onSubmit={handleSubmit} className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Template Name
                    </label>
                    <input
                      required
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                      placeholder="e.g., Create Jira Ticket"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Action Type
                    </label>
                    <select
                      value={formData.action_type}
                      onChange={(e) => setFormData({ ...formData, action_type: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                      {actionTypes.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      System (optional)
                    </label>
                    <select
                      value={formData.system?.id || ''}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        system: systems.find(s => s.id === parseInt(e.target.value)) || null 
                      })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                      <option value="">Select a system...</option>
                      {systems.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description || ''}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={2}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    placeholder="Describe what this action does..."
                  />
                </div>

                {(formData.action_type === 'webhook' || formData.action_type === 'api_rest') && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          HTTP Method
                        </label>
                        <select
                          value={formData.http_method}
                          onChange={(e) => setFormData({ ...formData, http_method: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        >
                          {httpMethods.map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          Endpoint URL
                        </label>
                        <input
                          type="url"
                          value={formData.endpoint_url || ''}
                          onChange={(e) => setFormData({ ...formData, endpoint_url: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          placeholder="https://api.example.com/webhook"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {`Payload Template (JSON, use {{ alert.id }}, {{ case.title }}, etc.)`}
                      </label>
                      <textarea
                        value={formData.payload_template}
                        onChange={(e) => setFormData({ ...formData, payload_template: e.target.value })}
                        rows={6}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Headers (JSON, optional)
                      </label>
                      <textarea
                        value={formData.headers}
                        onChange={(e) => setFormData({ ...formData, headers: e.target.value })}
                        rows={3}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Auth Credentials (JSON, optional)
                      </label>
                      <textarea
                        value={formData.auth_credentials}
                        onChange={(e) => setFormData({ ...formData, auth_credentials: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                      />
                    </div>
                  </div>
                )}

                {formData.action_type === 'jira_ticket' && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Jira Project Key
                      </label>
                      <input
                        type="text"
                        value={formData.jira_project_key || ''}
                        onChange={(e) => setFormData({ ...formData, jira_project_key: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="PROJECT"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Issue Type
                      </label>
                      <input
                        type="text"
                        value={formData.jira_issue_type || ''}
                        onChange={(e) => setFormData({ ...formData, jira_issue_type: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="Task"
                      />
                    </div>
                  </div>
                )}

                {formData.action_type === 'email' && (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Recipients (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={formData.email_recipients || ''}
                        onChange={(e) => setFormData({ ...formData, email_recipients: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="user1@example.com, user2@example.com"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Subject Template
                      </label>
                      <input
                        type="text"
                        value={formData.email_subject_template || ''}
                        onChange={(e) => setFormData({ ...formData, email_subject_template: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        placeholder="Alert: {{ alert.alert_type }}"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Body Template
                      </label>
                      <textarea
                        value={formData.email_body_template || ''}
                        onChange={(e) => setFormData({ ...formData, email_body_template: e.target.value })}
                        rows={4}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                      />
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.active}
                      onChange={(e) => setFormData({ ...formData, active: e.target.checked })}
                      className="w-4 h-4 text-indigo-600 rounded"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Template is active</span>
                  </label>
                </div>

                <div className="flex justify-end gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setShowModal(false)
                      setEditingTemplate(null)
                    }}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {loading ? 'Saving...' : 'Save Template'}
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