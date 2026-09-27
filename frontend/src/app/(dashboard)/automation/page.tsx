"use client"

import { useRequireToken } from '@/lib/auth'
import RuleBuilder from '@/components/dashboard/RuleBuilder'
import AgentCommandCenter from '@/components/dashboard/AgentCommandCenter'

export default function AutomationPage() {
  useRequireToken()

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-12">
      <AgentCommandCenter />
      
      <div className="border-t pt-8">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Regras de Automação (Legado)</h2>
        <RuleBuilder />
      </div>
    </div>
  )
}
