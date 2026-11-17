"use client"

import { useState, useEffect } from 'react'
import { apiFetch, getUserRole } from '@/lib/api'
import { useLang } from '@/lib/i18n'
import { X, Save, Brain, Zap, Shield, Activity, KeyRound } from 'lucide-react'

// Credenciais NVIDIA NIM + bancos de imagens por slot — encriptadas na BD.
type CredSlots = Record<string, { label: string, configured: boolean, masked: string, model: string, source: string }>
type SlotKey = 'text' | 'vision' | 'image' | 'pexels' | 'unsplash' | 'pixabay' | 'freepik'
const SLOTS: SlotKey[] = ['text', 'vision', 'image']
const BANK_SLOTS: SlotKey[] = ['pexels', 'unsplash', 'pixabay', 'freepik']
const ALL_SLOTS: SlotKey[] = [...SLOTS, ...BANK_SLOTS]
const EMPTY_INPUTS: Record<SlotKey, string> = { text: '', vision: '', image: '', pexels: '', unsplash: '', pixabay: '', freepik: '' }

export default function AISettingsModal({ isOpen, onClose, onSave }: { isOpen?: boolean, onClose: () => void, onSave?: () => void }) {
  const { t } = useLang()
  const [settings, setSettings] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // credenciais NIM na BD
  const [creds, setCreds] = useState<CredSlots | null>(null)
  const [keyInputs, setKeyInputs] = useState<Record<SlotKey, string>>(EMPTY_INPUTS)
  const [modelInputs, setModelInputs] = useState<Record<SlotKey, string>>(EMPTY_INPUTS)
  const [dirty, setDirty] = useState<Set<SlotKey>>(new Set())
  const [credsMsg, setCredsMsg] = useState('')

  useEffect(() => {
    if (!isOpen) return; // Only fetch when open
    setLoading(true)
    apiFetch('/settings/integration/current/')
      .then(r => r.json())
      .then(d => setSettings(d))
      .catch(e => console.error(e))
      .finally(() => setLoading(false))
    apiFetch('/ai/nim/credentials')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.slots) setCreds(d.slots as CredSlots) })
      .catch(() => { /* cartão informativo */ })
  }, [isOpen])

  const canEditCreds = getUserRole() === 'auditor' || getUserRole() === 'admin'

  const markDirty = (slot: SlotKey, field: 'key' | 'model', value: string) => {
    if (field === 'key') setKeyInputs(s => ({ ...s, [slot]: value }))
    else setModelInputs(s => ({ ...s, [slot]: value }))
    setDirty(prev => new Set(prev).add(slot))
    setCredsMsg('')
  }

  const saveCredentials = async () => {
    setCredsMsg('')
    const body: Record<string, string> = {}
    for (const slot of ALL_SLOTS) {
      if (!dirty.has(slot)) continue
      body[`${slot}_key`] = (keyInputs[slot] || '').trim()
      const m = (modelInputs[slot] || '').trim()
      if (m) body[`${slot}_model`] = m
    }
    if (Object.keys(body).length === 0) {
      setCredsMsg('—')
      return
    }
    setSaving(true)
    try {
      const r = await apiFetch('/ai/nim/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (r.status === 403) { setCredsMsg(t('nim.creds_forbidden')) }
      else if (r.ok) {
        const d = await r.json()
        if (d?.slots) setCreds(d.slots as CredSlots)
        setKeyInputs(EMPTY_INPUTS)
        setModelInputs(EMPTY_INPUTS)
        setDirty(new Set())
        setCredsMsg(t('nim.creds_ok'))
      } else { setCredsMsg(`${t('nim.err')} ${r.status}`) }
    } catch { setCredsMsg(t('nim.err')) }
    finally { setSaving(false) }
  }

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

  const srcBadge = (slot: string) => {
    const s = creds?.[slot]
    if (!s?.configured) return <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 text-[10px]">{t('nim.src_none')}</span>
    if (s.source === 'db') return <span className="px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 text-[10px]">{t('nim.src_db')}</span>
    return <span className="px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-[10px]">{t('nim.src_env')}</span>
  }

  const credRow = (slot: SlotKey, label: string, withModel = true) => {
    const s = creds?.[slot]
    return (
      <div key={slot} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{label}</span>
          <span className="flex items-center gap-1.5">
            {s?.configured && <code className="text-[10px] text-slate-400 font-mono">{s.masked}</code>}
            {srcBadge(slot)}
          </span>
        </div>
        <input
          type="password"
          placeholder={t('nim.api_key')}
          value={keyInputs[slot]}
          onChange={e => markDirty(slot, 'key', e.target.value)}
          disabled={!canEditCreds}
          autoComplete="off"
          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-purple-500 outline-none disabled:opacity-60"
        />
        {withModel && (
          <input
            type="text"
            placeholder={`${t('nim.model')} · ${s?.model || t('nim.model_default')}`}
            value={modelInputs[slot]}
            onChange={e => markDirty(slot, 'model', e.target.value)}
            disabled={!canEditCreds}
            autoComplete="off"
            className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-purple-500 outline-none disabled:opacity-60 font-mono"
          />
        )}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200 max-h-[92vh] flex flex-col">

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
        <div className="p-6 space-y-6 overflow-y-auto">

          {/* Sensitivity Slider */}
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <Shield className="w-4 h-4 text-blue-500" />
                Sensibilidade de Risco
              </label>
              <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-slate-600 dark:text-slate-300">
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
              className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-600"
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span>Conservador (Menos Alertas)</span>
              <span>Agressivo (Mais Alertas)</span>
            </div>
          </div>

          <hr className="border-slate-100 dark:border-slate-800" />

          {/* Credenciais NVIDIA NIM na BD */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-purple-500" />
              <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {t('nim.creds_title')}
              </label>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">{t('nim.creds_sub')}</p>
            {credRow('text', t('nim.slot_text'))}
            {credRow('vision', t('nim.slot_vision'))}
            {credRow('image', t('nim.slot_image'))}
            <div className="flex items-center justify-between gap-2">
              <span className={`text-xs ${credsMsg === t('nim.creds_ok') ? 'text-emerald-600' : 'text-red-500'}`}>{credsMsg}</span>
              <button onClick={saveCredentials} disabled={saving || !canEditCreds}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-600 hover:bg-purple-700 text-white flex items-center gap-1.5 disabled:opacity-50 transition-colors">
                {saving ? t('nim.creds_saving') : (<><Save className="w-3.5 h-3.5" />{t('nim.creds_save')}</>)}
              </button>
            </div>
          </div>

          <hr className="border-slate-100 dark:border-slate-800" />

          {/* Chaves dos bancos de imagens (opcional) */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-violet-500" />
              <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {t('nim.creds_banks_title')}
              </label>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">{t('bank.key_hint')}</p>
            {credRow('pexels', t('nim.slot_pexels'), false)}
            {credRow('unsplash', t('nim.slot_unsplash'), false)}
            {credRow('pixabay', t('nim.slot_pixabay'), false)}
            {credRow('freepik', t('nim.slot_freepik'), false)}
            <div className="flex items-center justify-end">
              <button onClick={saveCredentials} disabled={saving || !canEditCreds}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-600 hover:bg-violet-700 text-white flex items-center gap-1.5 disabled:opacity-50 transition-colors">
                {saving ? t('nim.creds_saving') : (<><Save className="w-3.5 h-3.5" />{t('nim.creds_save')}</>)}
              </button>
            </div>
          </div>

          <hr className="border-slate-100 dark:border-slate-800" />

          {/* Active Learning Toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-500" />
                Aprendizado Ativo (Active Learning)
              </label>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[280px]">
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
              <div className="w-11 h-6 bg-slate-200 dark:bg-slate-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>

          <hr className="border-slate-100 dark:border-slate-800" />

           {/* Auto-Resolve Toggle */}
           <div className="flex items-center justify-between">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <Activity className="w-4 h-4 text-green-500" />
                Auto-Resolução de Falsos Positivos
              </label>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[280px]">
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
              <div className="w-11 h-6 bg-slate-200 dark:bg-slate-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>

        </div>

        {/* Footer */}
        <div className="bg-slate-50 dark:bg-slate-800/60 p-4 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
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
