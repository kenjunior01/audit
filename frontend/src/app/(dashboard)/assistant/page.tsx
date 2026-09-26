'use client'

import { useState, useRef, useEffect , Suspense} from 'react'
import { useSearchParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch } from '@/lib/api'
import { 
  Send, 
  Bot, 
  User, 
  Sparkles, 
  Loader2, 
  PlusCircle, 
  Check, 
  Lightbulb,
  Zap,
  ShieldAlert,
  FileText,
  BarChart3,
  Play
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  type: 'text' | 'summary' | 'list' | 'suggestions'
  data?: any
}

function AssistantPageContent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Olá! Sou seu Assistente de Auditoria Inteligente. Estou pronto para analisar riscos, gerar relatórios ou executar ações de mitigação.',
      type: 'text'
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const searchParams = useSearchParams()

  useEffect(() => {
    const q = searchParams.get('query')
    if (q) {
        setInput(q)
        sendMessage(q) // Auto-send if query param exists
    }
  }, [searchParams])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const sendMessage = async (text?: string) => {
    const content = text || input
    if (!content.trim()) return
    
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: content,
      type: 'text'
    }
    
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    
    try {
      const res = await apiFetch('/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg.content })
      })
      const data = await res.json()
      
      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.content,
        type: data.type || 'text',
        data: data.data
      }
      
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "Desculpe, tive um erro ao processar sua solicitação. Verifique sua conexão.",
        type: 'text'
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleAction = async (actionId: string, actionType: string, params: any = {}) => {
    setLoading(true)
    // Add a system message indicating action started
    setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Executando ação: ${actionType}...`,
        type: 'text'
    }])

    try {
      const res = await apiFetch('/ai/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: actionId, action_type: actionType, params })
      })
      const data = await res.json()
      
      const responseMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.success ? `✅ Ação concluída com sucesso: ${data.message}` : `❌ Falha na ação: ${data.message}`,
        type: 'text'
      }
      setMessages(prev => [...prev, responseMsg])
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "Erro crítico ao tentar executar a ação.",
        type: 'text'
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const quickCommands = [
    { icon: ShieldAlert, label: "Scan de Riscos", query: "Faça uma varredura completa por riscos altos hoje." },
    { icon: FileText, label: "Relatório Diário", query: "Gere um resumo executivo das atividades de hoje." },
    { icon: Zap, label: "Sugestões de Regras", query: "Analise padrões recentes e sugira novas regras de bloqueio." },
    { icon: BarChart3, label: "Análise de Tendência", query: "Como está a tendência de risco nos últimos 30 dias?" },
  ]

  return (
    <div className="p-6 h-[calc(100vh-80px)] max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Sidebar - Command Center */}
      <motion.div 
        initial={{ x: -50, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="lg:col-span-1 space-y-4"
      >
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Bot className="w-8 h-8 text-indigo-600" />
            Audit AI
          </h1>
          <p className="text-sm text-gray-500 mt-1">Copiloto Operacional</p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Comandos Rápidos</h3>
            <div className="space-y-2">
                {quickCommands.map((cmd, i) => (
                    <motion.button 
                        key={i}
                        whileHover={{ scale: 1.02, x: 4 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => sendMessage(cmd.query)}
                        disabled={loading}
                        className="w-full flex items-center gap-3 p-3 text-left rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-gray-700 dark:text-gray-300 transition-all border border-transparent hover:border-indigo-100 dark:hover:border-indigo-800 group"
                    >
                        <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg group-hover:bg-white dark:group-hover:bg-gray-800 text-indigo-600 transition-colors">
                            <cmd.icon className="w-4 h-4" />
                        </div>
                        <span className="text-sm font-medium">{cmd.label}</span>
                        <Play className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 text-indigo-400" />
                    </motion.button>
                ))}
            </div>
        </div>

        <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="bg-indigo-600 rounded-xl p-4 text-white shadow-lg relative overflow-hidden"
        >
            <div className="relative z-10">
                <h3 className="font-bold mb-1 flex items-center gap-2"><Sparkles className="w-4 h-4" /> Modo Proativo</h3>
                <p className="text-xs text-indigo-100 opacity-90">A IA está monitorando ativamente novos padrões de fraude em background.</p>
            </div>
            <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-white opacity-10 rounded-full blur-2xl animate-pulse"></div>
        </motion.div>
      </motion.div>

      {/* Main Chat Area */}
      <motion.div 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="lg:col-span-3 flex flex-col h-full"
      >
        <Card className="flex-1 flex flex-col overflow-hidden border-gray-200 dark:border-gray-800 shadow-xl bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm">
            <CardContent className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth" ref={scrollRef}>
            <AnimatePresence initial={false}>
                {messages.map((msg) => (
                <motion.div 
                    key={msg.id}
                    initial={{ opacity: 0, y: 10, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm ${msg.role === 'assistant' ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}>
                    {msg.role === 'assistant' ? <Bot className="w-6 h-6" /> : <User className="w-6 h-6" />}
                    </div>
                    
                    <div className={`max-w-[85%] rounded-2xl p-5 shadow-sm ${
                    msg.role === 'assistant' 
                        ? 'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 border border-gray-100 dark:border-gray-700' 
                        : 'bg-indigo-600 text-white'
                    }`}>
                    <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                    
                    {/* Specialized Content Rendering */}
                    {msg.type === 'summary' && msg.data && (
                        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="p-4 bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800">
                                <div className="text-xs text-gray-500 uppercase font-semibold">Transações Analisadas</div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{msg.data.transactions}</div>
                            </div>
                            <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-100 dark:border-red-900/30">
                                <div className="text-xs text-red-500 uppercase font-semibold">Alertas Críticos</div>
                                <div className="text-2xl font-bold text-red-600 mt-1">{msg.data.alerts}</div>
                            </div>
                        </div>
                    )}

                    {msg.type === 'list' && msg.data && (
                        <div className="mt-4 space-y-2">
                            {msg.data.map((item: any) => (
                                <div key={item.id} className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-100 dark:border-gray-700 text-sm flex justify-between items-center hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                                    <div>
                                        <div className="font-bold text-gray-900 dark:text-white">{item.vendor}</div>
                                        <div className="text-xs text-gray-500">{item.reason}</div>
                                    </div>
                                    <span className="text-red-600 font-mono font-bold">${item.amount}</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {msg.type === 'suggestions' && msg.data && (
                        <div className="mt-4 space-y-3">
                            {msg.data.map((item: any) => (
                                <div key={item.id} className="p-4 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800/50 hover:shadow-md transition-shadow">
                                    <div className="flex items-start gap-3">
                                        <div className="p-2 bg-white dark:bg-gray-800 rounded-lg text-indigo-600 shadow-sm">
                                            {item.type === 'rule_proposal' ? <PlusCircle className="w-5 h-5" /> : <Lightbulb className="w-5 h-5" />}
                                        </div>
                                        <div className="flex-1">
                                            <h4 className="font-bold text-gray-900 dark:text-white">{item.title}</h4>
                                            <p className="text-sm text-indigo-800 dark:text-indigo-300 mt-1 leading-snug">{item.description}</p>
                                            
                                            <div className="mt-3 flex gap-2">
                                                <button 
                                                    onClick={() => handleAction(item.id, item.action, item.params)}
                                                    className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors font-medium shadow-sm"
                                                >
                                                    <Check className="w-3 h-3" />
                                                    {item.type === 'rule_proposal' ? 'Aprovar e Aplicar' : 'Executar Ação'}
                                                </button>
                                                <button className="text-xs px-3 py-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
                                                    Ignorar
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    </div>
                </motion.div>
                ))}
            </AnimatePresence>
            {loading && (
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex gap-4"
                >
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center shadow-sm">
                        <Bot className="w-6 h-6" />
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-2xl border border-gray-100 dark:border-gray-700 flex items-center gap-3 shadow-sm">
                        <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                        <span className="text-sm text-gray-500 font-medium">Processando com AuditAI...</span>
                    </div>
                </motion.div>
            )}
            </CardContent>
            
            <div className="p-4 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
                <div className="relative">
                    <input 
                        className="w-full pl-5 pr-14 py-4 bg-gray-50 dark:bg-gray-800 border-none rounded-2xl focus:ring-2 focus:ring-indigo-500 transition-all text-base shadow-inner"
                        placeholder="Descreva o que você precisa investigar..."
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && sendMessage()}
                    />
                    <button 
                        onClick={() => sendMessage()}
                        disabled={!input.trim() || loading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg active:scale-95"
                    >
                        <Send className="w-5 h-5" />
                    </button>
                </div>
                <div className="mt-3 flex justify-center">
                    <p className="text-xs text-gray-400 flex items-center gap-1">
                        <ShieldAlert className="w-3 h-3" />
                        IA treinada com base nas normas internas de compliance.
                    </p>
                </div>
            </div>
        </Card>
      </motion.div>
    </div>
  )
}


export default function AssistantPage() {
  return (
    <Suspense fallback={null}>
      <AssistantPageContent />
    </Suspense>
  )
}
