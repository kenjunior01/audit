"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Plus, Trash, Zap, Play, Pause, Activity, Settings, ArrowRight, Loader2, X, Download, ExternalLink } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'

type Condition = {
    id: string
    metric: string
    operator: string
    value: string
}

type Agent = {
    id: string
    name: string
    specialization?: string
    conditions: Condition[]
    action: string
    external_action_template?: number | null
    active: boolean
    lastTriggered?: string
    created_at?: string
}

type ExternalActionTemplate = {
    id: number
    name: string
    action_type: string
    active: boolean
    description?: string
}

const METRICS = [
    { value: 'risk_score', label: 'Risco Score' },
    { value: 'vendor_trust', label: 'Trust Score Fornecedor' },
    { value: 'amount', label: 'Valor da Transação' },
    { value: 'category', label: 'Categoria' },
    { value: 'velocity', label: 'Velocidade de Aprovação' }
]

const OPERATORS = [
    { value: '>', label: 'é maior que' },
    { value: '<', label: 'é menor que' },
    { value: '=', label: 'é igual a' },
    { value: '!=', label: 'é diferente de' },
    { value: 'contains', label: 'contém' }
]

const ACTIONS = [
    { value: 'freeze_payment', label: 'Congelar Pagamento' },
    { value: 'notify_manager', label: 'Notificar Gestor (Email)' },
    { value: 'create_case_high', label: 'Criar Caso (Prioridade Alta)' },
    { value: 'require_2fa', label: 'Exigir 2FA no Próximo Login' },
    { value: 'flag_vendor', label: 'Marcar Fornecedor como Risco' },
    { value: 'auto_resolve', label: 'Auto-Resolver (Falso Positivo)' },
    { value: 'external_action', label: 'Ação Externa (Template)' }
]

export default function RuleBuilder() {
    const token = useRequireToken()
    const [agents, setAgents] = useState<Agent[]>([])
    const [externalTemplates, setExternalTemplates] = useState<ExternalActionTemplate[]>([])
    const [loading, setLoading] = useState(true)
    const [submitting, setSubmitting] = useState(false)

    const [newAgentName, setNewAgentName] = useState('')
    const [conditions, setConditions] = useState<Condition[]>([
        { id: Math.random().toString(), metric: 'risk_score', operator: '>', value: '' }
    ])
    const [action, setAction] = useState(ACTIONS[0].value)
    const [selectedExternalTemplate, setSelectedExternalTemplate] = useState<number | ''>('')

    const [suggestions, setSuggestions] = useState<any[]>([])
    const [simulationResult, setSimulationResult] = useState<{count: number, total_amount: number, matches: any[], daily_stats?: any[]} | null>(null)
    const [simulating, setSimulating] = useState(false)
    const [exporting, setExporting] = useState(false)
    const [simulationRange, setSimulationRange] = useState<'all' | '30d' | '90d' | '1y'>('all')

    useEffect(() => {
        if (token) {
            loadAgents()
            loadSuggestions()
            loadExternalTemplates()
        }
    }, [token])

    const loadExternalTemplates = async () => {
        try {
            const res = await apiFetch('/external-action-templates/')
            const data = await res.json()
            setExternalTemplates(Array.isArray(data) ? data : (data.results || []))
        } catch (e) {
            console.error(e)
        }
    }

    const loadSuggestions = () => {
        apiFetch('/ai/suggest_rules')
            .then(r => r.json())
            .then(data => setSuggestions(data.suggestions || []))
            .catch(err => console.error(err))
    }

    const loadAgents = () => {
        setLoading(true)
        apiFetch('/agents')
            .then(r => r.json())
            .then(data => {
                // Ensure conditions is always an array
                const safeData = (Array.isArray(data) ? data : (data.results || [])).map((a: any) => ({
                    ...a,
                    id: a.id.toString(),
                    conditions: typeof a.conditions === 'string' ? JSON.parse(a.conditions) : (a.conditions || [])
                }))
                setAgents(safeData)
            })
            .catch(err => console.error(err))
            .finally(() => setLoading(false))
    }

    const addCondition = () => {
        setConditions([...conditions, { id: Math.random().toString(), metric: 'risk_score', operator: '>', value: '' }])
    }

    const removeCondition = (id: string) => {
        if (conditions.length > 1) {
            setConditions(conditions.filter(c => c.id !== id))
        }
    }

    const updateCondition = (id: string, field: keyof Condition, val: string) => {
        setConditions(conditions.map(c => c.id === id ? { ...c, [field]: val } : c))
    }

    const createAgent = () => {
        if (!newAgentName || !token) return
        if (action === 'external_action' && !selectedExternalTemplate) return
        setSubmitting(true)
        
        const payload: any = {
            name: newAgentName,
            conditions: conditions,
            action: action === 'external_action' ? 'external_action' : action,
            active: true
        }

        if (action === 'external_action' && selectedExternalTemplate) {
            payload.external_action_template = parseInt(selectedExternalTemplate.toString())
        }

        apiFetch('/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(newAgent => {
             // Parse conditions if returned as string (though DRF usually returns JSON for JSONField)
             const safeAgent = {
                 ...newAgent,
                 id: newAgent.id.toString(),
                 conditions: typeof newAgent.conditions === 'string' ? JSON.parse(newAgent.conditions) : newAgent.conditions
             }
             setAgents([safeAgent, ...agents])
             // Reset form
             setNewAgentName('')
             setConditions([{ id: Math.random().toString(), metric: 'risk_score', operator: '>', value: '' }])
             setAction(ACTIONS[0].value)
             setSelectedExternalTemplate('')
        })
        .catch(err => console.error(err))
        .finally(() => setSubmitting(false))
    }

    const getSimulationDates = () => {
        if (simulationRange === 'all') return {}
        
        const end = new Date()
        const start = new Date()
        
        if (simulationRange === '30d') start.setDate(end.getDate() - 30)
        if (simulationRange === '90d') start.setDate(end.getDate() - 90)
        if (simulationRange === '1y') start.setFullYear(end.getFullYear() - 1)
        
        return {
            start_date: start.toISOString(),
            end_date: end.toISOString()
        }
    }

    const simulateRule = async () => {
        setSimulating(true)
        setSimulationResult(null)
        try {
            const dates = getSimulationDates()
            const res = await apiFetch('/ai/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conditions, ...dates })
            })
            const data = await res.json()
            setSimulationResult(data)
        } catch (e) {
            console.error(e)
        } finally {
            setSimulating(false)
        }
    }

    const exportSimulationCSV = async () => {
        if (!conditions.length) return
        setExporting(true)
        try {
            const dates = getSimulationDates()
            const res = await apiFetch('/ai/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conditions, limit: 1000, ...dates })
            })
            const data = await res.json()
            
            if (!data.matches || data.matches.length === 0) {
                alert('Nenhum dado para exportar')
                return
            }

            const headers = ['ID', 'Date', 'Vendor', 'Amount', 'Category']
            const rows = data.matches.map((m: any) => [
                m.id,
                m.date,
                `"${m.vendor}"`,
                m.amount,
                m.category
            ])
            
            const csvContent = [
                headers.join(','),
                ...rows.map((r: any[]) => r.join(','))
            ].join('\n')
            
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.setAttribute('href', url)
            link.setAttribute('download', `simulacao_regras_${new Date().toISOString().slice(0,10)}.csv`)
            link.style.visibility = 'hidden'
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
        } catch (e) {
            console.error(e)
            alert('Erro ao exportar CSV')
        } finally {
            setExporting(false)
        }
    }

    const toggleAgent = (id: string) => {
        const agent = agents.find(a => a.id === id)
        if (!agent) return
        
        // Optimistic update
        setAgents(agents.map(a => a.id === id ? { ...a, active: !a.active } : a))
        
        apiFetch(`/agents/${id}/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: !agent.active })
        }).catch(err => {
            console.error(err)
            // Revert on error
            setAgents(agents.map(a => a.id === id ? { ...a, active: agent.active } : a))
        })
    }

    const deleteAgent = (id: string) => {
        // Optimistic update
        const prevAgents = [...agents]
        setAgents(agents.filter(a => a.id !== id))
        
        apiFetch(`/agents/${id}/`, {
            method: 'DELETE'
        }).catch(err => {
            console.error(err)
            setAgents(prevAgents)
        })
    }

    const applySuggestion = (s: any) => {
        setNewAgentName(s.suggested_rule.name)
        setConditions(s.suggested_rule.conditions.map((c: any) => ({
            ...c,
            id: Math.random().toString()
        })))
        // Map suggested action to closest available action or default
        if (s.suggested_rule.action) {
             const mappedAction = ACTIONS.find(a => a.value === s.suggested_rule.action) 
                ? s.suggested_rule.action 
                : (s.suggested_rule.action === 'review' ? 'notify_manager' : 'freeze_payment')
             setAction(mappedAction)
        }
    }

    const testAgent = (agent: Agent) => {
        console.log("Testing agent", agent)
        // Placeholder for testing logic
    }

    const containerVariants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1
            }
        }
    }

    const itemVariants = {
        hidden: { opacity: 0, x: -20 },
        visible: { opacity: 1, x: 0 },
        exit: { opacity: 0, scale: 0.95 }
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Builder Column */}
            <div className="lg:col-span-2 space-y-6">
                <Card className="border-none shadow-lg bg-white dark:bg-gray-900">
                    <CardHeader className="border-b border-gray-100 dark:border-gray-800 pb-4">
                        <div className="flex items-center gap-2">
                            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                                <Settings className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                            </div>
                            <div>
                                <CardTitle>Construtor de Agentes</CardTitle>
                                <CardDescription>Configure automações baseadas em regras condicionais.</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="p-6 space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome do Agente</label>
                            <input 
                                type="text" 
                                value={newAgentName}
                                onChange={e => setNewAgentName(e.target.value)}
                                placeholder="Ex: Bloqueio de Fornecedor Suspeito"
                                className="w-full p-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 outline-none transition-all"
                            />
                        </div>

                        <div className="space-y-3">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Condições (SE)</label>
                            <div className="space-y-3 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-dashed border-gray-300 dark:border-gray-700">
                                {conditions.map((cond, idx) => (
                                    <div key={cond.id} className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                                        {idx > 0 && <span className="text-xs font-bold text-indigo-500 uppercase px-1">E</span>}
                                        <select 
                                            value={cond.metric}
                                            onChange={e => updateCondition(cond.id, 'metric', e.target.value)}
                                            className="flex-1 p-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                                        >
                                            {METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                                        </select>
                                        <select 
                                            value={cond.operator}
                                            onChange={e => updateCondition(cond.id, 'operator', e.target.value)}
                                            className="w-32 p-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                                        >
                                            {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                        </select>
                                        <input 
                                            type="text" 
                                            value={cond.value}
                                            onChange={e => updateCondition(cond.id, 'value', e.target.value)}
                                            placeholder="Valor"
                                            className="w-24 p-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                                        />
                                        <button 
                                            onClick={() => removeCondition(cond.id)}
                                            disabled={conditions.length === 1}
                                            className="p-2 text-gray-400 hover:text-red-500 disabled:opacity-30 transition-colors"
                                        >
                                            <Trash className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                                <button 
                                    onClick={addCondition}
                                    className="text-xs flex items-center gap-1 text-indigo-600 font-medium hover:underline mt-2"
                                >
                                    <Plus className="w-3 h-3" /> Adicionar Condição
                                </button>
                            </div>
                        </div>

                        <div className="flex justify-center">
                            <ArrowRight className="w-6 h-6 text-gray-300 dark:text-gray-600 rotate-90 lg:rotate-0" />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Ação (ENTÃO)</label>
                            <div className="p-4 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800">
                                <select 
                                    value={action}
                                    onChange={e => setAction(e.target.value)}
                                    className="w-full p-2 text-sm border border-indigo-200 dark:border-indigo-700 rounded-lg bg-white dark:bg-gray-800 text-indigo-900 dark:text-indigo-100 font-medium mb-3"
                                >
                                    {ACTIONS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                                </select>
                                
                                {action === 'external_action' && (
                                    <div className="space-y-2">
                                        <label className="block text-xs font-medium text-indigo-700 dark:text-indigo-400">Template de Ação Externa:</label>
                                        <div className="flex gap-2">
                                            <select 
                                                value={selectedExternalTemplate}
                                                onChange={e => setSelectedExternalTemplate(e.target.value ? parseInt(e.target.value) : '')}
                                                className="flex-1 p-2 text-sm border border-indigo-200 dark:border-indigo-700 rounded-lg bg-white dark:bg-gray-800"
                                            >
                                                <option value="">Selecione um template...</option>
                                                {externalTemplates.filter(t => t.active).map(t => (
                                                    <option key={t.id} value={t.id}>{t.name} ({t.action_type})</option>
                                                ))}
                                            </select>
                                            <a 
                                                href="/external-actions" 
                                                target="_blank" 
                                                rel="noreferrer"
                                                className="p-2 bg-white dark:bg-gray-800 border border-indigo-200 dark:border-indigo-700 rounded-lg text-indigo-600 hover:text-indigo-700"
                                                title="Gerenciar Templates"
                                            >
                                                <ExternalLink className="w-4 h-4" />
                                            </a>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Simulation Results */}
                        <AnimatePresence>
                            {simulationResult && (
                                <motion.div 
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden"
                                >
                                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-200 dark:border-blue-800 mb-4">
                                        <div className="flex justify-between items-center mb-2">
                                            <h4 className="font-bold text-blue-800 dark:text-blue-300 flex items-center gap-2">
                                                <Activity className="w-4 h-4" />
                                                Resultado da Simulação
                                            </h4>
                                            <div className="flex items-center gap-2">
                                                <button 
                                                    onClick={exportSimulationCSV}
                                                    title="Exportar CSV"
                                                    disabled={exporting}
                                                    className="p-1 hover:bg-blue-200 dark:hover:bg-blue-800 rounded text-blue-600 dark:text-blue-400 disabled:opacity-50"
                                                >
                                                    {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                                                </button>
                                                <button onClick={() => setSimulationResult(null)} className="text-blue-500 hover:text-blue-700">
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4 mb-3">
                                            <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-sm">
                                                <div className="text-xs text-gray-500">Transações Encontradas</div>
                                                <div className="text-xl font-bold text-gray-900 dark:text-white">{simulationResult.count}</div>
                                            </div>
                                            <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-sm">
                                                <div className="text-xs text-gray-500">Impacto Financeiro</div>
                                                <div className="text-xl font-bold text-gray-900 dark:text-white">
                                                    {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(simulationResult.total_amount)}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Chart */}
                                        {simulationResult.daily_stats && simulationResult.daily_stats.length > 0 && (
                                            <div className="h-32 mb-3 bg-white dark:bg-gray-800 rounded-lg p-2 shadow-sm">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <BarChart data={simulationResult.daily_stats}>
                                                        <XAxis dataKey="date" hide />
                                                        <RechartsTooltip 
                                                            contentStyle={{ borderRadius: '8px', border: 'none', fontSize: '12px' }}
                                                        />
                                                        <Bar dataKey="amount" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                                    </BarChart>
                                                </ResponsiveContainer>
                                            </div>
                                        )}

                                        {simulationResult.matches.length > 0 && (
                                            <div>
                                                <div className="flex items-center justify-between mb-2">
                                                    <div className="text-xs font-semibold text-blue-800 dark:text-blue-300">Linha do Tempo (Amostra):</div>
                                                </div>
                                                <div className="max-h-60 overflow-y-auto pr-2 custom-scrollbar">
                                                    <div className="relative pl-4 border-l-2 border-blue-200 dark:border-blue-800 space-y-4 py-2">
                                                        {simulationResult.matches.map((m: any) => (
                                                            <div key={m.id} className="relative">
                                                                <div className="absolute -left-[21px] top-1.5 w-3 h-3 rounded-full bg-blue-500 border-2 border-white dark:border-gray-900"></div>
                                                                <div className="text-[10px] text-gray-500 mb-0.5 font-mono">{new Date(m.date).toLocaleString()}</div>
                                                                <div className="text-xs font-bold text-gray-900 dark:text-white truncate">{m.vendor}</div>
                                                                <div className="text-xs text-gray-600 dark:text-gray-400 flex justify-between items-center">
                                                                    <span>{m.category}</span>
                                                                    <span className="font-mono font-medium text-blue-600 dark:text-blue-400">
                                                                        {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(m.amount)}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        <div className="flex items-center gap-2 mb-2">
                             <span className="text-xs font-medium text-gray-500">Período de Simulação:</span>
                             <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                                {['all', '30d', '90d', '1y'].map((r) => (
                                    <button
                                        key={r}
                                        onClick={() => setSimulationRange(r as any)}
                                        className={`px-2 py-1 text-xs font-medium rounded-md transition-all ${
                                            simulationRange === r 
                                            ? 'bg-white dark:bg-gray-700 shadow text-indigo-600 dark:text-indigo-300' 
                                            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                                        }`}
                                    >
                                        {r === 'all' ? 'Tudo' : r}
                                    </button>
                                ))}
                             </div>
                        </div>

                        <div className="flex gap-3">
                             <button 
                                onClick={simulateRule}
                                disabled={simulating}
                                className="flex-1 py-3 bg-white border border-indigo-200 hover:bg-indigo-50 text-indigo-700 rounded-lg font-bold shadow-sm flex items-center justify-center gap-2 transition-all hover:scale-[1.02]"
                            >
                                {simulating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
                                Simular Cenário
                            </button>
                            <button 
                                onClick={createAgent}
                                disabled={!newAgentName || submitting || (action === 'external_action' && !selectedExternalTemplate)}
                                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold shadow-lg shadow-indigo-500/30 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:scale-[1.02]"
                            >
                                {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Zap className="w-5 h-5" />}
                                Implantar Agente
                            </button>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Active Agents List */}
            <div className="space-y-4">
                {suggestions.length > 0 && (
                    <div className="mb-6">
                         <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
                            <Zap className="w-5 h-5 text-yellow-500" />
                            Sugestões Inteligentes
                        </h3>
                        <div className="space-y-3">
                            {suggestions.map(s => (
                                <div key={s.id} className="p-4 bg-gradient-to-br from-yellow-50 to-orange-50 dark:from-yellow-900/10 dark:to-orange-900/10 border border-yellow-200 dark:border-yellow-800 rounded-xl relative overflow-hidden group">
                                    <div className="absolute top-0 right-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button 
                                            onClick={() => applySuggestion(s)}
                                            className="px-3 py-1 bg-white dark:bg-gray-800 text-xs font-bold text-yellow-600 rounded-full shadow-sm hover:scale-105 transition-transform"
                                        >
                                            Usar Modelo
                                        </button>
                                    </div>
                                    <h4 className="font-bold text-yellow-800 dark:text-yellow-500 text-sm">{s.title}</h4>
                                    <p className="text-xs text-yellow-700 dark:text-yellow-600 mt-1 pr-16 leading-relaxed">
                                        {s.description}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <Activity className="w-5 h-5 text-green-500" />
                    Agentes Ativos ({agents.filter(a => a.active).length})
                </h3>
                <motion.div 
                    variants={containerVariants}
                    initial="hidden"
                    animate="visible"
                    className="space-y-4"
                >
                    <AnimatePresence mode="popLayout">
                        {agents.map(agent => (
                            <motion.div
                                key={agent.id}
                                variants={itemVariants}
                                layout
                                initial="hidden"
                                animate="visible"
                                exit="exit"
                                className={`p-4 rounded-xl border ${agent.active ? 'bg-white dark:bg-gray-900 border-indigo-100 dark:border-indigo-900 shadow-md' : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-800 opacity-70'}`}
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h4 className="font-bold text-gray-800 dark:text-gray-100 text-sm">{agent.name}</h4>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {agent.lastTriggered ? `Disparado: ${agent.lastTriggered}` : 'Aguardando gatilho...'}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button 
                                            onClick={() => testAgent(agent)}
                                            className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                            title="Testar Agente Agora"
                                        >
                                            <Play className="w-4 h-4" />
                                        </button>
                                        <button 
                                            onClick={() => toggleAgent(agent.id)}
                                            className={`p-1.5 rounded-lg ${agent.active ? 'text-green-600 bg-green-50 hover:bg-green-100' : 'text-gray-400 hover:bg-gray-200'}`}
                                            title={agent.active ? "Pausar" : "Ativar"}
                                        >
                                            {agent.active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                                        </button>
                                        <button 
                                            onClick={() => deleteAgent(agent.id)}
                                            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                                        >
                                            <Trash className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                
                                <div className="space-y-2 text-xs">
                                    <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded border border-gray-100 dark:border-gray-700">
                                        <span className="font-semibold text-gray-500 uppercase tracking-wider text-[10px]">SE</span>
                                        <div className="mt-1 space-y-1">
                                            {agent.conditions.map((c, i) => (
                                                <div key={c.id} className="text-gray-700 dark:text-gray-300 font-mono">
                                                    {i > 0 && <span className="text-indigo-500 font-bold mr-1">E</span>}
                                                    {METRICS.find(m => m.value === c.metric)?.label} {c.operator} {c.value}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded border border-indigo-100 dark:border-indigo-800">
                                        <span className="font-semibold text-indigo-500 uppercase tracking-wider text-[10px]">ENTÃO</span>
                                        <div className="mt-1 font-bold text-indigo-700 dark:text-indigo-300">
                                            {agent.external_action_template 
                                                ? `Ação Externa: ${externalTemplates.find(t => t.id === agent.external_action_template)?.name}` 
                                                : ACTIONS.find(a => a.value === agent.action)?.label}
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </motion.div>
            </div>
        </div>
    )
}
