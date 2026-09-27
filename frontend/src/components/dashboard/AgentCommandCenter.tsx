"use client"

import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'

type Agent = {
  id: number
  name: string
  specialization: string
  persona: string
  training_instructions: string
  reputation_score: number
  active: boolean
  last_triggered: string | null
}

type RiskAgentLog = {
    id: number
    timestamp: string
    scanned_count: number
    finding_summary: string
    finding_details: any
    risk_score: number
    suggested_action: string
    action_taken: boolean
}

export default function AgentCommandCenter() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  
  // Logs State
  const [selectedAgentLogs, setSelectedAgentLogs] = useState<RiskAgentLog[]>([])
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [viewingAgentName, setViewingAgentName] = useState('')

  // Form State
  const [newName, setNewName] = useState('')
  const [newSpec, setNewSpec] = useState('Fraud')
  const [newPersona, setNewPersona] = useState('')
  
  // Training State
  const [trainingData, setTrainingData] = useState('')

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      const res = await apiFetch('/agents')
      const data = await res.json()
      setAgents(data.results || data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
        await apiFetch('/agents', {
            method: 'POST',
            body: JSON.stringify({
                name: newName,
                specialization: newSpec,
                persona: newPersona,
                conditions: [],
                action: 'notify_manager',
                active: true
            })
        })
        setShowCreate(false)
        loadAgents()
        setNewName('')
        setNewPersona('')
    } catch (e) {
        alert('Failed to create agent')
    }
  }
  
  const handleTrain = async () => {
      if (!selectedAgent) return
      try {
          await apiFetch(`/agents/${selectedAgent.id}`, {
              method: 'PATCH',
              body: JSON.stringify({
                  training_instructions: trainingData
              })
          })
          setSelectedAgent(null)
          loadAgents()
      } catch (e) {
          alert('Failed to update agent training')
      }
  }

  const openTrainModal = (agent: Agent) => {
      setSelectedAgent(agent)
      setTrainingData(agent.training_instructions || '')
  }

  const getSpecIcon = (spec: string) => {
      const s = spec.toLowerCase()
      if (s.includes('fraud')) return '🕵️‍♂️'
      if (s.includes('compliance')) return '⚖️'
      if (s.includes('it') || s.includes('tech')) return '💻'
      if (s.includes('finance')) return '💰'
      return '🤖'
  }

  const handleRunAgent = async (agent: Agent) => {
      try {
          // Optimistic UI update
          alert(`Iniciando varredura com agente ${agent.name}...`)
          
          const res = await apiFetch(`/agents/${agent.id}/run`, { method: 'POST' })
          const data = await res.json()
          
          if (data.status === 'success') {
              let msg = `Agente ${agent.name} finalizou a execução.`
              if (data.finding) {
                  msg += `\n\nResultado: ${data.finding.message}`
              } else {
                  msg += `\n\nNenhuma anomalia encontrada.`
              }
              alert(msg)
              loadAgents() // Refresh timestamps
          }
      } catch (e) {
          alert('Erro ao executar agente.')
      }
  }

  const handleViewLogs = async (agent: Agent) => {
      try {
          setViewingAgentName(agent.name)
          const res = await apiFetch(`/agent-logs?agent=${agent.id}`)
          const data = await res.json()
          setSelectedAgentLogs(data.results || data)
          setShowLogsModal(true)
      } catch (e) {
          alert('Erro ao carregar logs.')
      }
  }

  return (
    <div className="space-y-6">
        {/* Header Section */}
        <div className="bg-gradient-to-r from-indigo-900 to-slate-900 rounded-2xl p-8 text-white shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-10">
                <svg className="w-64 h-64" fill="currentColor" viewBox="0 0 20 20"><path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3zM6 8a2 2 0 11-4 0 2 2 0 014 0zM16 18v-3a5.972 5.972 0 00-.75-2.906A3.005 3.005 0 0119 15v3h-3zM4.75 12.094A5.973 5.973 0 004 15v3H1v-3a3 3 0 013.75-2.906z"></path></svg>
            </div>
            <div className="relative z-10">
                <h2 className="text-3xl font-bold mb-2">Central de Comando de Agentes</h2>
                <p className="text-indigo-200 max-w-2xl">
                    Orquestre sua equipe de inteligência artificial. Cada agente opera de forma autônoma em sua especialização, reportando descobertas críticas para a Inteligência Mãe (AuditAI).
                </p>
                <button 
                    onClick={() => setShowCreate(true)}
                    className="mt-6 bg-indigo-500 hover:bg-indigo-400 text-white px-6 py-2 rounded-lg font-semibold transition-all shadow-lg shadow-indigo-500/30 flex items-center gap-2"
                >
                    <span>+</span> Contratar Novo Agente
                </button>
            </div>
        </div>

        {/* Create Modal */}
        {showCreate && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl">
                    <h3 className="text-xl font-bold mb-4">Novo Agente Especialista</h3>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Nome do Agente</label>
                            <input 
                                value={newName}
                                onChange={e => setNewName(e.target.value)}
                                className="w-full border p-2 rounded mt-1" 
                                placeholder="Ex: Sherlock, O Guardião..."
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Especialização</label>
                            <select 
                                value={newSpec}
                                onChange={e => setNewSpec(e.target.value)}
                                className="w-full border p-2 rounded mt-1"
                            >
                                <option value="Fraud">🕵️‍♂️ Detecção de Fraude</option>
                                <option value="Compliance">⚖️ Compliance & Políticas</option>
                                <option value="IT Security">💻 Segurança de TI</option>
                                <option value="Finance">💰 Controle Financeiro</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Persona / Diretriz Primária</label>
                            <textarea 
                                value={newPersona}
                                onChange={e => setNewPersona(e.target.value)}
                                className="w-full border p-2 rounded mt-1 h-24"
                                placeholder="Descreva como este agente deve se comportar. Ex: 'Você é extremamente cético com pagamentos duplicados e busca padrões ocultos.'"
                            />
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <button onClick={() => setShowCreate(false)} className="text-gray-500 hover:text-gray-700 px-4 py-2">Cancelar</button>
                            <button onClick={handleCreate} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Criar Agente</button>
                        </div>
                    </div>
                </div>
            </div>
        )}

        {/* Training Modal */}
        {selectedAgent && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-xl p-6 w-full max-w-2xl shadow-2xl">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="text-xl font-bold">Treinar Agente: {selectedAgent.name}</h3>
                        <span className="bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded-full font-bold">
                            Reputação: {selectedAgent.reputation_score?.toFixed(2) || '1.00'}
                        </span>
                    </div>
                    <p className="text-sm text-gray-500 mb-4">
                        Forneça instruções específicas, palavras-chave ou regras de negócio para refinar a inteligência deste agente.
                        A Inteligência Mãe usará isso para guiar a investigação.
                    </p>
                    <textarea 
                        value={trainingData}
                        onChange={e => setTrainingData(e.target.value)}
                        className="w-full border p-4 rounded-lg bg-slate-50 font-mono text-sm h-64 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="Ex: 'Foque em transações aprovadas nos fins de semana. Ignore fornecedores da lista de confiança X. Se encontrar pagamentos duplicados, marque como prioridade máxima.'"
                    />
                    <div className="flex justify-end gap-2 mt-6">
                        <button onClick={() => setSelectedAgent(null)} className="text-gray-500 hover:text-gray-700 px-4 py-2">Cancelar</button>
                        <button onClick={handleTrain} className="bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-700 shadow-lg">
                            💾 Salvar Conhecimento
                        </button>
                    </div>
                </div>
            </div>
        )}

        {/* Agents Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Mother Intelligence Card */}
            <div className="col-span-full mb-4">
                 <div className="bg-white border-l-4 border-indigo-600 rounded-r-xl shadow-sm p-6 flex items-start gap-4">
                    <div className="bg-indigo-100 p-3 rounded-full">
                        <span className="text-3xl">🧠</span>
                    </div>
                    <div>
                        <h3 className="font-bold text-gray-900 text-lg">Inteligência Mãe (AuditAI)</h3>
                        <p className="text-gray-600 text-sm mt-1">
                            Ativa e monitorando. Recebendo relatórios de {agents.length} agentes especializados.
                            <span className="block mt-2 font-medium text-indigo-600">
                                ⚡ Auto-Aprendizado Ativo: A Inteligência Mãe ajusta seu nível de alerta com base na reputação dos subagentes e feedback dos resumos executivos.
                            </span>
                        </p>
                    </div>
                 </div>
            </div>

            {loading ? <p>Carregando agentes...</p> : agents.map(agent => (
                <div key={agent.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 relative group hover:shadow-md transition-all flex flex-col">
                    <div className="absolute top-4 right-4 flex items-center gap-2">
                         <div className="text-xs font-mono text-gray-400">REP: {agent.reputation_score?.toFixed(1) || '1.0'}</div>
                        <span className={`inline-block w-3 h-3 rounded-full ${agent.active ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`}></span>
                    </div>
                    <div className="flex items-center gap-4 mb-4">
                        <div className="text-4xl bg-gray-50 w-16 h-16 flex items-center justify-center rounded-2xl">
                            {getSpecIcon(agent.specialization)}
                        </div>
                        <div>
                            <h3 className="font-bold text-gray-900">{agent.name}</h3>
                            <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600 bg-indigo-50 px-2 py-1 rounded-full">
                                {agent.specialization}
                            </span>
                        </div>
                    </div>
                    <p className="text-gray-600 text-sm mb-4 min-h-[3rem] line-clamp-3">
                        {agent.persona || "Agente padrão sem persona definida."}
                    </p>
                    
                    <div className="mt-auto pt-4 border-t flex justify-between items-center gap-2">
                        <button 
                             onClick={() => handleRunAgent(agent)}
                             className="text-xs bg-green-50 text-green-700 hover:bg-green-100 px-3 py-1 rounded font-medium transition-colors flex items-center gap-1"
                        >
                            ▶ Executar
                        </button>
                        <button 
                             onClick={() => handleViewLogs(agent)}
                             className="text-xs bg-gray-50 text-gray-700 hover:bg-gray-100 px-3 py-1 rounded font-medium transition-colors"
                        >
                            📜 Logs
                        </button>
                        <button 
                            onClick={() => openTrainModal(agent)}
                            className="text-indigo-600 text-xs font-medium hover:bg-indigo-50 px-3 py-1 rounded transition-colors"
                        >
                            🎓 Treinar
                        </button>
                    </div>
                </div>
            ))}
        </div>

        {/* Logs Modal */}
        {showLogsModal && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-xl p-6 w-full max-w-4xl shadow-2xl h-[80vh] flex flex-col">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="text-xl font-bold">Histórico de Atividade: {viewingAgentName}</h3>
                        <button onClick={() => setShowLogsModal(false)} className="text-gray-500 hover:text-gray-700 text-2xl">&times;</button>
                    </div>
                    
                    <div className="flex-1 overflow-y-auto space-y-4 pr-2">
                        {selectedAgentLogs.length === 0 ? (
                            <p className="text-gray-500 text-center py-10">Nenhum registro de atividade encontrado para este agente.</p>
                        ) : (
                            selectedAgentLogs.map(log => (
                                <div key={log.id} className="border rounded-lg p-4 hover:bg-gray-50">
                                    <div className="flex justify-between items-start mb-2">
                                        <div className="flex flex-col">
                                            <span className="text-xs text-gray-400 font-mono">
                                                {new Date(log.timestamp).toLocaleString()}
                                            </span>
                                            {log.risk_score > 0 && (
                                                <div className="flex items-center gap-1 mt-1">
                                                    <span className="text-[10px] font-bold text-gray-500 uppercase">Risk Score:</span>
                                                    <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                        <div 
                                                            className={`h-full ${log.risk_score > 0.7 ? 'bg-red-500' : log.risk_score > 0.4 ? 'bg-yellow-500' : 'bg-green-500'}`}
                                                            style={{ width: `${log.risk_score * 100}%` }}
                                                        ></div>
                                                    </div>
                                                    <span className="text-[10px] font-bold text-gray-700">{(log.risk_score * 100).toFixed(0)}%</span>
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex flex-col items-end gap-1">
                                            <span className="bg-blue-100 text-blue-800 text-[10px] px-2 py-0.5 rounded-full font-bold">
                                                Scanned: {log.scanned_count}
                                            </span>
                                            {log.action_taken && (
                                                <span className="bg-green-100 text-green-800 text-[10px] px-2 py-0.5 rounded-full font-bold">
                                                    ✓ Ação Executada
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <p className="text-gray-800 font-medium">{log.finding_summary}</p>
                                    
                                    {log.suggested_action && !log.action_taken && (
                                        <div className="mt-2 flex items-center gap-2">
                                            <span className="text-[10px] font-bold text-indigo-600 uppercase">Ação Sugerida:</span>
                                            <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-100 italic">
                                                {log.suggested_action}
                                            </span>
                                        </div>
                                    )}

                                    {log.finding_details && (
                                        <div className="mt-2 bg-slate-50 p-2 rounded text-[10px] font-mono text-gray-600 overflow-x-auto border border-slate-100">
                                            <pre>{JSON.stringify(log.finding_details, null, 2)}</pre>
                                        </div>
                                    )}
                                    {log.finding_details?.priority === 'High' && (
                                        <button 
                                            onClick={async () => {
                                                if(!confirm('Criar caso de investigação para este achado?')) return;
                                                try {
                                                    await apiFetch('/cases', {
                                                        method: 'POST',
                                                        body: JSON.stringify({
                                                            title: `Investigação: ${log.finding_summary}`,
                                                            description: `Caso gerado automaticamente a partir do Agente ${viewingAgentName}.\n\nDetalhes:\n${JSON.stringify(log.finding_details, null, 2)}`,
                                                            priority: 'High',
                                                            status: 'New'
                                                        })
                                                    });
                                                    alert('Caso criado com sucesso!');
                                                } catch(e) {
                                                    alert('Erro ao criar caso.');
                                                }
                                            }}
                                            className="mt-2 text-xs bg-red-100 text-red-700 px-3 py-1 rounded hover:bg-red-200 transition-colors"
                                        >
                                            🚨 Criar Caso de Investigação
                                        </button>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        )}
    </div>
  )
}
