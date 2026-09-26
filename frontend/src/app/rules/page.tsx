"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

type Rule = {
  id: number
  country: string
  regulation: string
  alert_type: string
  active: boolean
  description?: string
  suggested_by_ai: boolean
  ai_confidence?: number
  threshold_multiplier?: number
}

export default function RulesPage() {
  useRequireToken()
  const [items, setItems] = useState<Rule[]>([])
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [country, setCountry] = useState('')
  const [alertType, setAlertType] = useState('')
  
  const load = () => {
    setLoading(true)
    setFeedback(null)
    const params = new URLSearchParams()
    if (country) params.set('country', country)
    if (alertType) params.set('alert_type', alertType)
    
    Promise.all([
      apiFetch(`/rules?${params.toString()}`).then(r=>r.json()),
      apiFetch(`/ai/suggest_rules`).then(r=>r.json()).catch(()=>[])
    ]).then(([d, s]) => {
      setItems(d?.results || d?.items || d || [])
      setSuggestions(Array.isArray(s) ? s : [])
    }).finally(()=>setLoading(false))
  }

  const applySuggestion = async (s: any) => {
    if (!s) return
    setApplyingId(s.id)
    setFeedback(null)
    try {
      if (s.type === 'optimization') {
        await apiFetch('/ai/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action_id: s.id,
            action_type: 'adjust_sensitivity',
            params: {
              source: 'rules_page',
              country: country || null,
              alert_type: alertType || null,
              current_value: s.current_value,
              suggested_value: s.suggested_value,
            },
          }),
        })
        setFeedback('Parâmetros de sensibilidade ajustados com sucesso pela IA.')
      } else if (s.type === 'new_rule') {
        await apiFetch('/rules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            country: s.country || country || 'Global',
            regulation: s.regulation || s.rule_name || 'AI Generated',
            alert_type: s.alert_type || alertType || 'General',
            description: s.description || s.reason || '',
            suggested_by_ai: true,
            ai_confidence: s.confidence || 0,
          }),
        })
        setFeedback('Nova regra regulatória criada a partir da sugestão da IA.')
        load()
      }
    } catch (e) {
      setFeedback('Erro ao aplicar sugestão. Tente novamente.')
    } finally {
      setApplyingId(null)
    }
  }
  
  useEffect(()=>{ load() },[])

  return (
    <div>
      <h2 className="text-lg font-medium mb-4">Regras Regulatórias</h2>
      
      {/* Suggestions Section */}
      {suggestions.length > 0 && (
        <div className="mb-8">
          <h3 className="text-md font-semibold text-purple-900 mb-3 flex items-center">
            <span className="mr-2">✨</span> Sugestões de Otimização (IA)
          </h3>
          {feedback && (
            <div className="mb-3 text-xs text-purple-900 bg-purple-50 border border-purple-100 rounded px-3 py-2">
              {feedback}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {suggestions.map((s: any) => (
              <div key={s.id} className="bg-gradient-to-r from-purple-50 to-indigo-50 p-4 rounded border border-purple-100 shadow-sm">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-bold text-gray-800">{s.rule_name}</h4>
                    <span className="text-xs font-semibold text-purple-700 bg-purple-100 px-2 py-0.5 rounded-full uppercase tracking-wide">
                      {s.type === 'optimization' ? 'Otimização' : 'Nova Regra'}
                    </span>
                  </div>
                  <span className="text-sm font-bold text-green-600 bg-green-50 px-2 py-1 rounded">
                    {Math.round(s.confidence * 100)}% Confiança
                  </span>
                </div>
                
                <p className="mt-2 text-sm text-gray-600">{s.reason}</p>
                
                {s.type === 'optimization' && (
                  <div className="mt-3 flex items-center text-sm">
                    <span className="text-gray-500 mr-2">Atual: <s className="text-gray-400">{s.current_value}</s></span>
                    <span className="font-bold text-purple-700">Sugerido: {s.suggested_value}</span>
                  </div>
                )}
                
                {s.type === 'new_rule' && (
                  <p className="mt-2 text-xs text-gray-500 italic">{s.description}</p>
                )}

                <div className="mt-4 flex space-x-2">
                  <button
                    className="px-3 py-1 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                    onClick={() => applySuggestion(s)}
                    disabled={!!applyingId}
                  >
                    {applyingId === s.id ? 'Aplicando...' : 'Aplicar Sugestão'}
                  </button>
                  <button className="px-3 py-1 bg-white border border-gray-300 text-gray-600 text-sm rounded hover:bg-gray-50 transition-colors">
                    Ignorar
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4 flex items-center space-x-2">
        <input 
          className="border p-2 rounded" 
          placeholder="País" 
          value={country} 
          onChange={e=>setCountry(e.target.value)} 
        />
        <input 
          className="border p-2 rounded" 
          placeholder="Tipo de Alerta" 
          value={alertType} 
          onChange={e=>setAlertType(e.target.value)} 
        />
        <button className="px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700" onClick={load}>
          Filtrar
        </button>
      </div>

      {loading && <div className="text-sm text-gray-600 mb-2">Carregando...</div>}
      
      <div className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-full">
          <thead>
            <tr className="bg-gray-50">
              <th className="px-4 py-3 text-left font-medium text-gray-500">ID</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">País</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Regulação</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Tipo Alerta</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Mult.</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Origem</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {items.map(it => (
              <tr key={it.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{it.id}</td>
                <td className="px-4 py-3">{it.country}</td>
                <td className="px-4 py-3 font-medium">{it.regulation}</td>
                <td className="px-4 py-3">{it.alert_type}</td>
                <td className="px-4 py-3">{it.threshold_multiplier?.toFixed(1)}x</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-xs ${it.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                    {it.active ? 'Ativa' : 'Inativa'}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {it.suggested_by_ai ? (
                    <span title={`Confiança: ${(it.ai_confidence || 0) * 100}%`}>🤖 IA</span>
                  ) : 'Manual'}
                </td>
                <td className="px-4 py-3">
                  {!it.active && (
                    <button 
                      className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700" 
                      onClick={async ()=>{
                        await apiFetch(`/rules/${it.id}/activate`, {method:'POST'})
                        load()
                      }}
                    >
                      Ativar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                  Nenhuma regra encontrada
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
