"use client"
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'

type GeoRisk = {
  country: string
  risk_score: number
  alert_count: number
  coordinates: [number, number] // [lat, long]
}

export default function GeoRiskPage() {
  useRequireToken()
  const [data, setData] = useState<GeoRisk[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedRegion, setSelectedRegion] = useState<GeoRisk | null>(null)
  const [riskFilter, setRiskFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all')

  useEffect(() => {
    apiFetch('/context/geo_risks')
      .then(res => res.json())
      .then(d => {
        setData(Array.isArray(d) ? d : [])
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setLoading(false)
      })
  }, [])

  const filteredData = data.filter(item => {
    if (riskFilter === 'all') return true
    if (riskFilter === 'high') return item.risk_score > 80
    if (riskFilter === 'medium') return item.risk_score > 50 && item.risk_score <= 80
    if (riskFilter === 'low') return item.risk_score <= 50
    return true
  })

  // Simple Equirectangular projection
  const width = 800
  const height = 400
  
  const project = (lat: number, long: number) => {
    const x = (long + 180) * (width / 360)
    const y = ((-lat) + 90) * (height / 180)
    return { x, y }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Mapa de Risco Geográfico</h1>
          <p className="text-gray-500">Visualização global de alertas e exposição ao risco</p>
        </div>
        <div className="flex gap-2">
            <button 
                onClick={() => setRiskFilter('all')}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${riskFilter === 'all' ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            >
                Todos
            </button>
            <button 
                onClick={() => setRiskFilter('high')}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${riskFilter === 'high' ? 'bg-red-600 text-white' : 'bg-red-50 text-red-600 hover:bg-red-100'}`}
            >
                Alto Risco
            </button>
            <button 
                onClick={() => setRiskFilter('medium')}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${riskFilter === 'medium' ? 'bg-yellow-500 text-white' : 'bg-yellow-50 text-yellow-600 hover:bg-yellow-100'}`}
            >
                Médio
            </button>
             <button 
                onClick={() => setRiskFilter('low')}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${riskFilter === 'low' ? 'bg-green-600 text-white' : 'bg-green-50 text-green-600 hover:bg-green-100'}`}
            >
                Baixo
            </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Map Visualization */}
        <div className="lg:col-span-2 bg-white p-4 shadow rounded border border-gray-200">
          {loading ? (
            <div className="h-[400px] flex items-center justify-center text-gray-400">Carregando mapa...</div>
          ) : (
            <div className="relative w-full overflow-hidden bg-blue-50 rounded border border-blue-100">
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
                {/* Grid lines for reference */}
                <line x1="0" y1={height/2} x2={width} y2={height/2} stroke="#e0e7ff" strokeWidth="1" />
                <line x1={width/2} y1="0" x2={width/2} y2={height} stroke="#e0e7ff" strokeWidth="1" />
                
                {/* World Map Outline Placeholder (Abstract) */}
                <text x={width/2} y={height/2} textAnchor="middle" fill="#e0e7ff" fontSize="100" fontWeight="bold" opacity="0.5">MUNDO</text>

                {filteredData.map((item, i) => {
                  const { x, y } = project(item.coordinates[0], item.coordinates[1])
                  const radius = Math.max(5, Math.min(20, item.alert_count / 2))
                  const color = item.risk_score > 80 ? '#ef4444' : item.risk_score > 50 ? '#f59e0b' : '#10b981'
                  
                  return (
                    <g 
                      key={i} 
                      onClick={() => setSelectedRegion(item)} 
                      className="cursor-pointer hover:opacity-80 transition-opacity"
                    >
                      <circle cx={x} cy={y} r={radius} fill={color} fillOpacity="0.6" stroke={color} strokeWidth="1">
                        <animate attributeName="r" values={`${radius};${radius + 2};${radius}`} dur="2s" repeatCount="indefinite" />
                      </circle>
                      <text x={x} y={y + radius + 12} textAnchor="middle" fontSize="10" fill="#374151" fontWeight="bold">
                        {item.country}
                      </text>
                    </g>
                  )
                })}
              </svg>
              <div className="absolute bottom-2 right-2 text-xs text-gray-400 bg-white/80 p-1 rounded">
                *Projeção Simplificada
              </div>
            </div>
          )}
        </div>

        {/* Details Panel */}
        <div className="bg-white p-4 shadow rounded border border-gray-200">
          <h3 className="text-lg font-semibold mb-4 text-gray-800">Detalhes da Região</h3>
          
          {selectedRegion ? (
            <div className="space-y-4 animate-fade-in">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">{selectedRegion.country}</h2>
                <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                  selectedRegion.risk_score > 80 ? 'bg-red-100 text-red-800' : 
                  selectedRegion.risk_score > 50 ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'
                }`}>
                  Risco: {selectedRegion.risk_score}
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-50 p-3 rounded">
                  <div className="text-sm text-gray-500">Total de Alertas</div>
                  <div className="text-xl font-semibold">{selectedRegion.alert_count}</div>
                </div>
                <div className="bg-gray-50 p-3 rounded">
                  <div className="text-sm text-gray-500">Tendência</div>
                  <div className="text-xl font-semibold">↗ Alta</div>
                </div>
              </div>

              <div className="pt-4 border-t border-gray-100">
                <h4 className="font-medium text-gray-700 mb-2">Principais Ameaças</h4>
                <ul className="text-sm text-gray-600 space-y-2">
                  <li className="flex items-center space-x-2">
                    <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                    <span>Fraude em Fornecedores (Local)</span>
                  </li>
                  <li className="flex items-center space-x-2">
                    <span className="w-2 h-2 bg-yellow-500 rounded-full"></span>
                    <span>Conformidade Regulatória</span>
                  </li>
                </ul>
              </div>

              <button className="w-full mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors">
                Ver Todos os Alertas desta Região
              </button>
            </div>
          ) : (
            <div className="text-center py-10 text-gray-500">
              <p>Selecione uma região no mapa para ver detalhes.</p>
              <div className="mt-4 flex flex-col space-y-2">
                {filteredData.slice(0, 5).map(item => (
                   <button 
                     key={item.country}
                     onClick={() => setSelectedRegion(item)}
                     className="p-2 hover:bg-gray-50 rounded text-left flex justify-between items-center border border-transparent hover:border-gray-200"
                   >
                     <span>{item.country}</span>
                     <span className={`text-xs font-bold ${item.risk_score > 80 ? 'text-red-600' : 'text-yellow-600'}`}>{item.risk_score}</span>
                   </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
