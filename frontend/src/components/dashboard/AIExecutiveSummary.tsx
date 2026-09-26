"use client"
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'

type AgentReport = {
  agent: string
  specialization: string
  message: string
  priority: string
}

type SummaryData = {
  title: string
  insights: string[]
  generated_at: string
  risk_level: 'Critical' | 'Moderate' | 'Low'
  agent_reports?: AgentReport[]
  out_of_scope_alerts?: number
  total_alerts_week?: number
  context_country?: string | null
  context_domains?: string[] | null
}

export default function AIExecutiveSummary() {
  const router = useRouter()
  const [summary, setSummary] = useState<SummaryData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/ai/executive-summary')
      .then(res => res.json())
      .then(data => setSummary(data))
      .catch(err => console.error("Failed to load executive summary", err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
      <div className="space-y-3">
        <div className="h-4 bg-gray-200 rounded w-full"></div>
        <div className="h-4 bg-gray-200 rounded w-5/6"></div>
      </div>
    </div>
  )

  if (!summary) return null

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Critical': return 'border-l-red-500 bg-red-50'
      case 'Moderate': return 'border-l-yellow-500 bg-yellow-50'
      default: return 'border-l-green-500 bg-green-50'
    }
  }

  const getRiskBadge = (level: string) => {
    switch (level) {
      case 'Critical': return 'bg-red-100 text-red-800'
      case 'Moderate': return 'bg-yellow-100 text-yellow-800'
      default: return 'bg-green-100 text-green-800'
    }
  }

  return (
    <div className="space-y-6">
    <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden mb-6 transition-all hover:shadow-xl">
      <div className="bg-gradient-to-r from-gray-900 to-gray-800 p-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-blue-500/20 p-2 rounded-lg backdrop-blur-sm">
             <span className="text-2xl">🧠</span>
          </div>
          <div>
             <h2 className="text-white font-bold text-lg tracking-tight">AI Executive Insight</h2>
             <p className="text-gray-400 text-xs uppercase tracking-wider">Strategic Audit Analysis</p>
          </div>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase ${getRiskBadge(summary.risk_level)}`}>
          {summary.risk_level} Risk Posture
        </span>
      </div>
      
      <div className="p-6">
        <div className="mb-4 text-xs text-gray-400 flex justify-between">
           <span>Generated at: {summary.generated_at}</span>
           <span>Source: AuditAI Core Engine</span>
        </div>

        <div className="space-y-4">
          {summary.insights.map((insight, idx) => (
            <div key={idx} className="flex gap-3 items-start p-3 hover:bg-gray-50 rounded-lg transition-colors border-l-2 border-transparent hover:border-blue-500">
               <div className="mt-1 text-blue-600">
                 {insight.includes('⚠️') ? '⚠️' : insight.includes('✅') ? '✅' : insight.includes('⚡') ? '⚡' : insight.includes('🎯') ? '🎯' : insight.includes('🤖') ? '🤖' : 'ℹ️'}
               </div>
               <div className="text-gray-700 leading-relaxed text-sm" 
                    dangerouslySetInnerHTML={{ 
                      __html: insight
                        .replace(/⚠️|✅|⚡|🎯|ℹ️|🤖/g, '') // Remove icons from text as we use them separately
                        .replace(/\*\*(.*?)\*\*/g, '<span class="font-bold text-gray-900">$1</span>') 
                    }} 
               />
            </div>
          ))}
        </div>
      </div>
    </div>
    
    {/* Agent Reports Section */}
    {summary.agent_reports && summary.agent_reports.length > 0 && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
         {summary.agent_reports.map((report, idx) => (
             <div key={idx} className="bg-white p-4 rounded-lg shadow border border-gray-200 flex flex-col justify-between">
                 <div>
                     <div className="flex justify-between items-start mb-2">
                        <span className="font-bold text-indigo-700 flex items-center gap-2">
                            🤖 {report.agent} 
                            <span className="text-xs bg-indigo-100 px-2 py-0.5 rounded-full text-indigo-600 font-normal">{report.specialization}</span>
                        </span>
                        <span className={`text-xs px-2 py-1 rounded font-bold ${report.priority === 'High' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                            {report.priority}
                        </span>
                     </div>
                     <p className="text-sm text-gray-600 mb-4">{report.message}</p>
                 </div>
                 <button 
                    onClick={() => router.push(`/assistant?query=Investigate finding by ${report.agent}: ${report.message}`)}
                    className="text-sm bg-gray-50 hover:bg-gray-100 text-indigo-600 font-medium py-2 rounded border border-gray-200 transition-colors w-full"
                 >
                     Investigar Descoberta
                 </button>
             </div>
         ))}
      </div>
    )}
    </div>
  )
}
