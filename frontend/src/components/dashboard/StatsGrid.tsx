"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent } from "@/components/ui/card"
import { apiFetch } from '@/lib/api'
import { ShieldAlert, FileCheck, Radio, Clock } from 'lucide-react'
import { motion } from 'framer-motion'

export default function StatsGrid() {
  const [stats, setStats] = useState<any>({})

  useEffect(() => {
    apiFetch('/context/stats')
      .then(r => r.json())
      .then(setStats)
      .catch(console.error)
  }, [])

  const items = [
    {
      label: "Casos Abertos",
      value: stats.open_cases || 0,
      icon: FileCheck,
      color: "text-blue-600",
      bg: "bg-blue-100 dark:bg-blue-900/20"
    },
    {
      label: "Casos Vencidos",
      value: stats.overdue_cases || 0,
      icon: Clock,
      color: "text-orange-600",
      bg: "bg-orange-100 dark:bg-orange-900/20"
    },
    {
      label: "Economia Potencial",
      value: `R$ ${(stats.potential_savings || 0).toLocaleString('pt-BR', { notation: 'compact' })}`,
      icon: ShieldAlert,
      color: "text-green-600",
      bg: "bg-green-100 dark:bg-green-900/20"
    },
    {
      label: "Risco Recente",
      value: stats.high_risk_alerts || 0,
      icon: Radio,
      color: "text-red-600",
      bg: "bg-red-100 dark:bg-red-900/20"
    }
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {items.map((item, i) => (
        <Card key={i} className="overflow-hidden relative border-none shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{item.label}</p>
              <motion.div 
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: i * 0.1, type: "spring", stiffness: 100 }}
                className="text-2xl font-bold mt-1"
              >
                {item.value}
              </motion.div>
            </div>
            <div className={`p-3 rounded-full ${item.bg}`}>
              <item.icon className={`h-5 w-5 ${item.color}`} />
            </div>
          </CardContent>
          {/* Decorative bar */}
          <div className={`absolute bottom-0 left-0 w-full h-1 ${item.color.replace('text-', 'bg-')} opacity-20`} />
        </Card>
      ))}
    </div>
  )
}
