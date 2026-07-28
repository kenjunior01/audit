"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { apiFetch } from '@/lib/api'
import { TrendingUp, TrendingDown, AlertCircle, Loader2 } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

type ForecastData = {
    forecast_dates: string[]
    predicted_risk_score: number[]
    upper_bounds: number[]
    lower_bounds: number[]
    insight: string
    confidence_interval: number
    trend_direction?: 'up' | 'up_slight' | 'down' | 'down_slight' | 'stable'
}

export default function ForecastChart() {
    const [data, setData] = useState<ForecastData | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        loadForecast()
    }, [])

    const loadForecast = () => {
        setLoading(true)
        apiFetch('/ai/forecast')
            .then(r => r.json())
            .then(setData)
            .catch(console.error)
            .finally(() => setLoading(false))
    }

    if (loading) {
        return (
            <Card className="h-[350px] flex items-center justify-center border-none shadow-sm">
                <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
            </Card>
        )
    }

    if (!data) return null

    // Transform data for Recharts
    const chartData = data.forecast_dates.map((date, i) => ({
        date: new Date(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }),
        risk: data.predicted_risk_score[i],
        // Range for confidence interval [lower, upper]
        range: [
            data.lower_bounds ? data.lower_bounds[i] : data.predicted_risk_score[i] * 0.8,
            data.upper_bounds ? data.upper_bounds[i] : data.predicted_risk_score[i] * 1.2
        ]
    }))

    const isIncreasing = data.trend_direction?.includes('up') || (chartData.length > 1 && chartData[chartData.length - 1].risk > chartData[0].risk)

    const getInsightColor = () => {
        switch (data.trend_direction) {
            case 'up': return 'bg-red-50 text-red-900 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800'
            case 'up_slight': return 'bg-orange-50 text-orange-900 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-800'
            case 'down': return 'bg-green-50 text-green-900 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
            case 'down_slight': return 'bg-emerald-50 text-emerald-900 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800'
            default: return 'bg-indigo-50 text-indigo-900 border-indigo-200 dark:bg-indigo-900/20 dark:text-indigo-300 dark:border-indigo-800'
        }
    }

    const getInsightIcon = () => {
        if (data.trend_direction?.includes('up')) return <TrendingUp className="w-5 h-5 text-red-600 dark:text-red-400" />
        if (data.trend_direction?.includes('down')) return <TrendingDown className="w-5 h-5 text-green-600 dark:text-green-400" />
        return <AlertCircle className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
    }

    return (
        <Card className="col-span-1 shadow-sm border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <CardHeader className="pb-2">
                <div className="flex justify-between items-start">
                    <div>
                        <CardTitle className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                            <TrendingUp className="w-5 h-5 text-indigo-600" />
                            Previsão de Risco (12 Semanas)
                        </CardTitle>
                        <CardDescription>
                            Projeção baseada em histórico e sazonalidade.
                        </CardDescription>
                    </div>
                    <div className={`px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1 ${
                        isIncreasing 
                            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' 
                            : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    }`}>
                        {isIncreasing ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {isIncreasing ? 'Tendência de Alta' : 'Tendência de Queda'}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <div className="h-[250px] w-full mt-4">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <defs>
                                <linearGradient id="colorRisk" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" opacity={0.5} />
                            <XAxis 
                                dataKey="date" 
                                tick={{ fontSize: 12, fill: '#64748b' }} 
                                axisLine={false}
                                tickLine={false}
                            />
                            <YAxis 
                                tick={{ fontSize: 12, fill: '#64748b' }} 
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip 
                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                labelStyle={{ color: '#64748b', marginBottom: '0.25rem' }}
                            />
                            
                            {/* Confidence Interval (Area) */}
                            {data.upper_bounds && (
                                <Area 
                                    type="monotone" 
                                    dataKey="range" 
                                    stroke="none" 
                                    fill="#94a3b8" 
                                    fillOpacity={0.2}
                                    isAnimationActive={false}
                                />
                            )}
                            
                            <Area 
                                type="monotone" 
                                dataKey="risk" 
                                stroke={isIncreasing ? "#ef4444" : "#10b981"} 
                                strokeWidth={3}
                                fillOpacity={1} 
                                fill="url(#colorRisk)" 
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
                
                <div className={`mt-4 p-3 rounded-lg flex items-start gap-3 border ${getInsightColor()}`}>
                    <div className="shrink-0 mt-0.5">{getInsightIcon()}</div>
                    <div>
                        <div className="text-xs font-bold uppercase mb-1 opacity-80">Insight da IA</div>
                        <p className="text-sm leading-relaxed font-medium">
                            {data.insight}
                        </p>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
