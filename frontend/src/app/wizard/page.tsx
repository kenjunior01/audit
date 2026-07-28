"use client"
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { useRouter } from 'next/navigation'

export default function WizardPage() {
  useRequireToken()
  const router = useRouter()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  
  // Step 1: Profile
  const [profile, setProfile] = useState({
    country: '',
    sector: 'Other',
    org_structure: 'Functional',
    company_type: '', // Kept for backward compatibility or display
    base_currency: 'BRL'
  })

  // Step 2: Conversational Interview
  const [chatHistory, setChatHistory] = useState<{role: 'system'|'user', content: string}[]>([
    { role: 'system', content: 'Olá! Sou o seu Assistente de Auditoria. Para calibrar meus alertas, me diga: Qual é a sua maior preocupação de risco hoje? (Ex: Fraude em compras, Suborno, Erros operacionais)' }
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatQuestionIndex, setChatQuestionIndex] = useState(0)

  const chatQuestions = [
    "Entendi. E quais tipos de transação sua equipe costuma investigar manualmente ou considerar 'falso positivo'?",
    "Existe alguma política interna específica ou limite de alçada que eu deva priorizar?",
    "Obrigado! Por fim, cole aqui qualquer trecho de regulação importante (ou digite 'pular')."
  ]

  const next = () => setStep(s => s + 1)
  const back = () => setStep(s => s - 1)

  const saveProfile = async () => {
    setLoading(true)
    try {
        await apiFetch('/profile', { 
            method: 'POST', 
            body: JSON.stringify(profile),
            headers: {'Content-Type':'application/json'}
        })
        next()
    } catch (e) {
        console.error(e)
        alert('Erro ao salvar perfil')
    } finally {
        setLoading(false)
    }
  }

  const handleChatSubmit = async () => {
    if (!chatInput.trim()) return
    
    const newHistory = [...chatHistory, { role: 'user' as const, content: chatInput }]
    setChatHistory(newHistory)
    setChatInput('')
    
    // Save answer to profile context immediately or batch at end
    // For now, we just proceed to next question
    
    if (chatQuestionIndex < chatQuestions.length) {
        setTimeout(() => {
            setChatHistory(h => [...h, { role: 'system', content: chatQuestions[chatQuestionIndex] }])
            setChatQuestionIndex(i => i + 1)
        }, 500)
    } else {
        // Finished interview
        setLoading(true)
        // Update profile with interview data
        const interviewData = {
            risk_concern: newHistory.find((_, i) => i===1)?.content,
            manual_investigation: newHistory.find((_, i) => i===3)?.content,
            internal_policy: newHistory.find((_, i) => i===5)?.content,
            regulation_text: newHistory.find((_, i) => i===7)?.content
        }
        await apiFetch('/profile', { 
            method: 'PATCH', 
            body: JSON.stringify({ onboarding_data: interviewData }), 
            headers: {'Content-Type':'application/json'} 
        })
        setLoading(false)
        next()
    }
  }

  // Step 3: News/External Signals
  const fetchNews = async () => {
    setLoading(true)
    await apiFetch('/ai/fetch_news', { method: 'POST' })
    setLoading(false)
    router.push('/')
  }

  return (
    <div className="max-w-2xl mx-auto bg-white rounded shadow p-6 min-h-[500px] flex flex-col">
      <h1 className="text-xl font-bold mb-4">Configuração Inicial (Passo {step}/3)</h1>
      
      {step === 1 && (
        <div className="space-y-4">
          <p className="text-gray-600">Vamos configurar o contexto organizacional para calibrar a IA.</p>
          
          <div>
            <label className="block text-sm font-medium text-gray-700">País Sede</label>
            <input className="border p-2 w-full rounded" placeholder="ex: Brasil" value={profile.country} onChange={e=>setProfile({...profile, country: e.target.value})} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
                <label className="block text-sm font-medium text-gray-700">Setor de Atuação</label>
                <select className="border p-2 w-full rounded" value={profile.sector} onChange={e=>setProfile({...profile, sector: e.target.value})}>
                    <option value="Other">Outros</option>
                    <option value="Manufacturing">Manufatura (Indústria)</option>
                    <option value="Services">Serviços / Consultoria</option>
                    <option value="SaaS">Tecnologia (SaaS)</option>
                    <option value="Retail">Varejo</option>
                    <option value="Public">Setor Público</option>
                    <option value="Financial">Financeiro</option>
                </select>
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700">Estrutura Organizacional</label>
                <select className="border p-2 w-full rounded" value={profile.org_structure} onChange={e=>setProfile({...profile, org_structure: e.target.value})}>
                    <option value="Functional">Funcional (Departamentos)</option>
                    <option value="Divisional">Divisional (Unidades de Negócio)</option>
                    <option value="Matrix">Matricial (Reporte Duplo)</option>
                    <option value="SME">Pequena/Média Empresa</option>
                </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
             <div>
                <label className="block text-sm font-medium text-gray-700">Moeda Base</label>
                <select className="border p-2 w-full rounded" value={profile.base_currency} onChange={e=>setProfile({...profile, base_currency: e.target.value})}>
                    <option value="BRL">Real (BRL)</option>
                    <option value="USD">Dólar (USD)</option>
                    <option value="EUR">Euro (EUR)</option>
                </select>
             </div>
             <div>
                <label className="block text-sm font-medium text-gray-700">Nome Legal (Opcional)</label>
                <input className="border p-2 w-full rounded" placeholder="ex: Minha Empresa Ltda" value={profile.company_type} onChange={e=>setProfile({...profile, company_type: e.target.value})} />
             </div>
          </div>

          <div className="flex justify-end pt-4">
            <button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700" onClick={saveProfile} disabled={loading}>
              {loading ? 'Salvando...' : 'Salvar e Continuar'}
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="flex-1 flex flex-col">
          <p className="text-gray-600 mb-4">Entrevista de Contexto (Dados Quentes)</p>
          <div className="flex-1 border rounded p-4 mb-4 overflow-y-auto bg-gray-50 space-y-3 max-h-[300px]">
            {chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] p-3 rounded-lg ${msg.role === 'user' ? 'bg-blue-100 text-blue-900' : 'bg-white border text-gray-800 shadow-sm'}`}>
                        {msg.content}
                    </div>
                </div>
            ))}
          </div>
          
          <div className="flex gap-2">
            <input 
                className="flex-1 border p-2 rounded" 
                placeholder="Digite sua resposta..." 
                value={chatInput} 
                onChange={e=>setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleChatSubmit()}
            />
            <button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700" onClick={handleChatSubmit} disabled={loading}>
                Enviar
            </button>
          </div>
          <div className="flex justify-start mt-2">
             <button className="text-xs text-gray-400 underline" onClick={next}>Pular entrevista</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <p className="text-gray-600">Configuração concluída! Deseja ativar o monitoramento de notícias externas?</p>
          <div className="flex justify-between">
            <button className="px-4 py-2 bg-gray-200 rounded" onClick={back}>Voltar</button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={fetchNews} disabled={loading}>
              {loading ? 'Ativar e Finalizar' : 'Finalizar'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
