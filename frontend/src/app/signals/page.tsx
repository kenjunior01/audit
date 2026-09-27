"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

type Signal = { 
  id: number
  title: string
  valid: boolean // 'validated_at' is used in backend, but frontend might use 'valid' derived or mapped
  country?: string
  sector?: string
  severity?: number
  source_url?: string
  suggested_by_ai?: boolean
  ai_confidence?: number
  validated_at?: string
}

export default function SignalsPage() {
  useRequireToken()
  const [items, setItems] = useState<Signal[]>([])
  const [loading, setLoading] = useState(false)
  const [country, setCountry] = useState('')
  const [sector, setSector] = useState('')
  const [contextSummary, setContextSummary] = useState<any | null>(null)
  const [contextApplied, setContextApplied] = useState(false)
  const [autoMessage, setAutoMessage] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)

  const outOfScopeStats = (() => {
    if (!contextSummary || items.length === 0) return { total: items.length, outOfScope: 0, inScope: items.length }
    let outOfScope = 0
    for (const it of items) {
      const countryOutOfScope =
        contextSummary &&
        contextSummary.country &&
        it.country &&
        it.country !== contextSummary.country

      const sectorOutOfScope =
        contextSummary &&
        Array.isArray(contextSummary.audit_domains) &&
        contextSummary.audit_domains.length > 0 &&
        it.sector &&
        !contextSummary.audit_domains.includes(it.sector)

      if (countryOutOfScope || sectorOutOfScope) {
        outOfScope += 1
      }
    }
    return { total: items.length, outOfScope, inScope: items.length - outOfScope }
  })()
  const outOfScopeRatio = outOfScopeStats.total > 0 ? outOfScopeStats.outOfScope / outOfScopeStats.total : 0

  const load = (filters?: { country?: string; sector?: string }) => {
    setLoading(true)
    const effectiveCountry = filters?.country ?? country
    const effectiveSector = filters?.sector ?? sector
    const params = new URLSearchParams()
    if (effectiveCountry) params.set('country', effectiveCountry)
    if (effectiveSector) params.set('sector', effectiveSector)
    
    apiFetch(`/signals?${params.toString()}`)
      .then(r=>r.json())
      .then(d=> setItems(d?.results || d?.items || d || []))
      .finally(()=>setLoading(false))
  }

  const handleAdjustScopeSignals = async () => {
    if (!contextSummary || !outOfScopeStats.total) return
    setAutoLoading(true)
    setAutoMessage(null)
    try {
      const res = await apiFetch('/ai/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: 'scope_signals_outside_context',
          action_type: 'adjust_sensitivity',
          params: {
            source: 'signals_page',
            out_of_scope_ratio: outOfScopeRatio,
            country: country || contextSummary.country || null,
            domains: Array.isArray(contextSummary.audit_domains) ? contextSummary.audit_domains : [],
          },
        }),
      })
      const data = await res.json()
      setAutoMessage(data?.message || 'Ajuste automático aplicado aos sinais fora de contexto.')
    } catch (e) {
      setAutoMessage('Erro ao aplicar ajuste automático.')
    } finally {
      setAutoLoading(false)
    }
  }

  const applyContextFilters = () => {
    if (!contextSummary) return
    const ctxCountry = contextSummary.country
    const ctxDomains = Array.isArray(contextSummary.audit_domains) ? contextSummary.audit_domains : []
    const nextCountry = ctxCountry || ''
    const nextSector = ctxDomains[0] || ''
    setCountry(nextCountry)
    setSector(nextSector)
    load({ country: nextCountry, sector: nextSector })
  }
  
  useEffect(()=>{ load() },[])

  useEffect(() => {
    apiFetch('/context/profile/current/')
      .then(r => r.json())
      .then(setContextSummary)
      .catch(() => setContextSummary(null))
  }, [])

  useEffect(() => {
    if (!contextSummary || contextApplied) return

    if (!country && !sector) {
      applyContextFilters()
    }
    setContextApplied(true)
  }, [contextSummary])

  return (
    <div>
      <h2 className="text-lg font-medium mb-4">Sinais de Risco (Notícias/Contexto)</h2>

      {contextSummary && (
        <div className="mb-4 bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs text-indigo-900 flex flex-wrap gap-x-4 gap-y-1">
          <span>
            <span className="font-semibold">País:</span> {contextSummary.country || 'Não definido'}
          </span>
          <span>
            <span className="font-semibold">Regulações:</span>{' '}
            {Array.isArray(contextSummary.regulatory_frameworks) && contextSummary.regulatory_frameworks.length > 0
              ? contextSummary.regulatory_frameworks.join(', ')
              : 'Nenhuma selecionada'}
          </span>
          <span>
            <span className="font-semibold">Domínios:</span>{' '}
            {Array.isArray(contextSummary.audit_domains) && contextSummary.audit_domains.length > 0
              ? contextSummary.audit_domains.join(', ')
              : 'Geral'}
          </span>
          <span>
            <span className="font-semibold">Apetite de Risco:</span>{' '}
            {contextSummary.risk_appetite === 'Conservative' && 'Conservador'}
            {contextSummary.risk_appetite === 'Balanced' && 'Equilibrado'}
            {contextSummary.risk_appetite === 'Aggressive' && 'Agressivo'}
            {!contextSummary.risk_appetite && 'Equilibrado'}
          </span>
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
          placeholder="Setor" 
          value={sector} 
          onChange={e=>setSector(e.target.value)} 
        />
        <button className="px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700" onClick={() => load()}>
          Filtrar
        </button>
        {contextSummary && (
          <button
            className="px-3 py-2 bg-indigo-50 text-indigo-700 rounded border border-indigo-200 hover:bg-indigo-100 text-sm"
            onClick={applyContextFilters}
          >
            Resetar para contexto
          </button>
        )}
      </div>

      {loading && <div className="text-sm text-gray-600 mb-2">Carregando...</div>}
      
      {contextSummary && outOfScopeStats.total > 0 && outOfScopeStats.outOfScope > 0 && (
        <div className="mb-3 space-y-1">
          <div className="text-xs text-gray-600">
            {Math.round((outOfScopeStats.outOfScope / outOfScopeStats.total) * 100)}% dos sinais exibidos estão fora do contexto configurado de auditoria.
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full flex">
              <div
                className="bg-emerald-400"
                style={{ width: `${Math.max(0, Math.min(100, (outOfScopeStats.inScope / outOfScopeStats.total) * 100))}%` }}
              />
              <div
                className="bg-amber-400"
                style={{ width: `${Math.max(0, Math.min(100, (outOfScopeStats.outOfScope / outOfScopeStats.total) * 100))}%` }}
              />
            </div>
          </div>
          <div className="flex justify-between text-[10px] text-gray-500">
            <span>Dentro do escopo</span>
            <span>Fora do escopo</span>
          </div>
          {outOfScopeRatio >= 0.3 && (
            <div className="pt-1 flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-gray-700">
                Muitos sinais estão fora do escopo. Deseja deixar a IA ajustar o foco?
              </span>
              <button
                onClick={handleAdjustScopeSignals}
                disabled={autoLoading}
                className="px-3 py-1 rounded-full text-[11px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {autoLoading ? 'Ajustando...' : 'Ajustar foco dos sinais com IA'}
              </button>
              {autoMessage && (
                <span className="text-[11px] text-gray-500">
                  {autoMessage}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      <div className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-full">
          <thead>
            <tr className="bg-gray-50">
              <th className="px-4 py-3 text-left font-medium text-gray-500">ID</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Título</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">País</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Setor</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Severidade</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Origem</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {items.map(it => {
              const countryOutOfScope =
                contextSummary &&
                contextSummary.country &&
                it.country &&
                it.country !== contextSummary.country

              const sectorOutOfScope =
                contextSummary &&
                Array.isArray(contextSummary.audit_domains) &&
                contextSummary.audit_domains.length > 0 &&
                it.sector &&
                !contextSummary.audit_domains.includes(it.sector)

              return (
                <tr key={it.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">{it.id}</td>
                  <td className="px-4 py-3 max-w-xs truncate" title={it.title}>{it.title}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <span>{it.country || '-'}</span>
                      {countryOutOfScope && (
                        <span className="inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                          Fora do país configurado
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <span>{it.sector || '-'}</span>
                      {sectorOutOfScope && (
                        <span className="inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                          Fora dos domínios ativos
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">{(it.severity || 0).toFixed(2)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs ${it.validated_at ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                      {it.validated_at ? 'Validado' : 'Pendente'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {it.suggested_by_ai ? (
                      <span title={`Confiança: ${(it.ai_confidence || 0) * 100}%`}>🤖 IA</span>
                    ) : 'Manual'}
                  </td>
                  <td className="px-4 py-3">
                    {!it.validated_at && (
                      <button 
                        className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700" 
                        onClick={async ()=>{
                          await apiFetch(`/signals/${it.id}/validate`, {method:'POST'})
                          load()
                        }}
                      >
                        Validar
                      </button>
                    )}
                    {it.source_url && (
                      <a 
                        href={it.source_url} 
                        target="_blank" 
                        className="ml-2 text-blue-600 text-sm hover:underline"
                      >
                        Fonte
                      </a>
                    )}
                  </td>
                </tr>
              )
            })}
             {items.length === 0 && !loading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                  Nenhum sinal encontrado
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
