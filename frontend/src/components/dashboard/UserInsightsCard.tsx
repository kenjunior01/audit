"use client"

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch } from '@/lib/api'
import { Brain, Sparkles, TrendingUp, UserCheck } from 'lucide-react'
import { motion } from 'framer-motion'

type InsightData = {
  title: string
  persona: string
  learning_level: number
  insights: string[]
  recommendations: string[]
  agreement_rate: number
}

export default function UserInsightsCard() {
  const [data, setData] = useState<InsightData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/ai/profile')
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <Card className="h-full animate-pulse bg-gray-50/50">
        <CardContent className="p-6">
            <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
            <div className="h-20 bg-gray-200 rounded w-full"></div>
        </CardContent>
    </Card>
  )

  if (!data) return null

  return (
    <Card className="h-full border-none shadow-sm bg-gradient-to-br from-indigo-50 to-white dark:from-indigo-950/20 dark:to-background overflow-hidden relative">
      <div className="absolute top-0 right-0 p-4 opacity-10">
        <Brain className="w-32 h-32 text-indigo-600" />
      </div>
      
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                <Brain className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <CardTitle className="text-lg font-semibold text-gray-800 dark:text-gray-100">
                {data.title}
            </CardTitle>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-6">
        {/* Persona Section */}
        <div className="flex items-center justify-between">
            <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Sua Persona Detectada</p>
                <motion.h3 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-2xl font-bold text-indigo-700 dark:text-indigo-300"
                >
                    {data.persona}
                </motion.h3>
                <div className="mt-2 inline-flex items-center px-2 py-1 rounded bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 text-xs font-medium">
                    <UserCheck className="w-3 h-3 mr-1" />
                    Calibração: {data.agreement_rate}%
                </div>
            </div>
            <div className="text-right">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Calibração da IA</p>
                <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${data.learning_level}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                        className="h-full bg-gradient-to-r from-indigo-500 to-purple-500" 
                    />
                </div>
                <p className="text-xs text-gray-400 mt-1">{data.learning_level}% Completo</p>
            </div>
        </div>

        {/* Insights List */}
        <div className="space-y-3">
            {data.insights.map((insight, i) => (
                <motion.div 
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.2 }}
                    className="flex items-start gap-3 p-3 bg-white/60 dark:bg-gray-800/40 rounded-lg backdrop-blur-sm border border-indigo-100 dark:border-indigo-900/30"
                >
                    <UserCheck className="w-4 h-4 text-indigo-500 mt-1 shrink-0" />
                    <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                        {insight}
                    </p>
                </motion.div>
            ))}
        </div>

        {/* Actionable Tip */}
        {data.recommendations?.length > 0 && (
            <div className="flex items-center gap-2 text-xs font-medium text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20 p-2 rounded border border-purple-100 dark:border-purple-800">
                <Sparkles className="w-3 h-3" />
                <span>Dica: {data.recommendations[0]}</span>
            </div>
        )}
      </CardContent>
    </Card>
  )
}
