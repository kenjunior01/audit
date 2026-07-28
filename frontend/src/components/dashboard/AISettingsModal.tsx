"use client"

import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { X, Save, Brain, Zap, Shield, Activity } from 'lucide-react'

export default function AISettingsModal({ isOpen, onClose, onSave }: { isOpen?: boolean, onClose: () => void, onSave?: () => void }) {
  const [settings, setSettings] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!isOpen) return; // Only fetch when open
    setLoading(true)
    apiFetch('/settings/integration/current/')
      .then(r => r.json())
      .then(d => setSettings(d))
      .catch(e => console.error(e))
      .finally(() => setLoading(false))
  }, [isOpen])

  const handleSave = async () => {
    setSaving(true)
    try {
      await apiFetch('/settings/integration/current/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      })
      if (onSave) onSave()
      onClose()
    } catch (e) {
      alert('Erro ao salvar configurações')
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null
  if (loading) return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white p-6 rounded-lg shadow-xl">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
          </div>
      </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200">
        
        {/* Header */}
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-purple-400" />
            <h2 className="font-semibold text-lg">AI Control Plane</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          
          {/* Sensitivity Slider */}
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                <Shield className="w-4 h-4 text-blue-500" />
                Sensibilidade de Risco
              </label>
              <span className="text-xs font-mono bg-slate-100 px-2 py-1 rounded text-slate-600">
                {(settings?.ai_sensitivity || 0.5).toFixed(2)}
              </span>
            </div>
            <input 
              type="range" 
              min="0.0" 
              max="1.0" 
              step="0.1"
              value={settings?.ai_sensitivity || 0.5}
              onChange={(e) => setSettings({...settings, ai_sensitivity: parseFloat(e.target.value)})}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-purple-600"
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span>Conservador (Menos Alertas)</span>
              <span>Agressivo (Mais Alertas)</span>
            </div>
          </div>

          <hr className="border-slate-100" />

          {/* Active Learning Toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-500" />
                Aprendizado Ativo (Active Learning)
              </label>
              <p className="text-xs text-slate-500 max-w-[280px]">
                Permitir que a IA aprenda com seus feedbacks e ajustes de memória persistente.
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input 
                type="checkbox" 
                checked={settings?.active_learning || false}
                onChange={(e) => setSettings({...settings, active_learning: e.target.checked})}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>

          <hr className="border-slate-100" />

           {/* Auto-Resolve Toggle */}
           <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                <Activity className="w-4 h-4 text-green-500" />
                Auto-Resolução de Falsos Positivos
              </label>
              <p className="text-xs text-slate-500 max-w-[280px]">
                Fechar automaticamente alertas classificados como "Seguro" com alta confiança.
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input 
                type="checkbox" 
                checked={settings?.auto_close_enabled || false}
                onChange={(e) => setSettings({...settings, auto_close_enabled: e.target.checked})}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>

        </div>

        {/* Footer */}
        <div className="bg-slate-50 p-4 flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancelar
          </button>
          <button 
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center gap-2 shadow-sm"
          >
            {saving ? 'Salvando...' : (
                <>
                    <Save className="w-4 h-4" />
                    Salvar Configurações
                </>
            )}
          </button>
        </div>

      </div>
    </div>
  )
}